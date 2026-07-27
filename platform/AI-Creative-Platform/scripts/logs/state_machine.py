# -*- coding: utf-8 -*-
"""
候选稿状态机（纲要 §2.9，实施任务 #20）。

SSOT = ``core/learning/schemas/revision-candidate-state.schema.yaml``（#17 定义、本任务
修正为 block 风格以便平台零依赖解析器加载）。

所有状态转换**唯一**经 ``transition_state(expected_state, next_state, via, condition)``：

  - **CAS**：当前持久态必须等于 ``expected_state``，否则抛 ``CasConflict``（防并发覆盖）。
  - **via 约束**：转换的 ``via``（任务类型）必须匹配；例如 ``FINAL_PASSED`` 仅
    ``final-regression`` 可达，其他任务（style-revise 等）无法产生该态。
  - **condition 约束**：带 ``condition`` 的转换须传入完全一致的值（如 ``cas_ok`` /
    ``pass`` / ``all_bindings_ok``），否则 ``IllegalTransition``。
  - **持久化**：原子写 ``runtime/learning/state/<cycle>.state.json``。
  - **不可变事件**：追加 ``STATE_CHANGE`` 事件（``details`` 携带 from/to/condition），
    由事件日志密钥签名（仅 Broker 持有）→ 即便状态文件被替换也能由事件日志检出。

``verify_consistency(cycle_id)`` 重放事件日志得到「应然态」，与持久态比对：
直接改状态文件绕过 ``transition_state``（攻击/误用）→ 不一致 → 检出。

真实并发由 #19 的受控写 Broker 单写者保证；本模块提供 CAS + 事件检测层。
"""
import json
import os
import sys

# 同目录模块（scripts/logs 已在 sys.path）
from event_log import EventLog, KeyProvider  # noqa: E402

_PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_SCHEMA = os.path.join(
    _PLATFORM_ROOT, "core", "learning", "schemas", "revision-candidate-state.schema.yaml")


class StateMachineError(Exception):
    """状态机通用错误。"""


class CasConflict(StateMachineError):
    """当前持久态与 expected 不符（并发修改 / 旧快照）。"""


class IllegalTransition(StateMachineError):
    """转换不在 SSOT 中，或 via / condition 不匹配。"""


class StateLoadError(StateMachineError):
    """SSOT 契约加载失败。"""


def load_schema(path):
    """加载状态机 SSOT；优先平台零依赖解析器，回退 PyYAML。"""
    try:
        sys.path.insert(0, os.path.join(_PLATFORM_ROOT, "scripts", "_common"))
        import _yaml_lite as y
        return y.load(open(path, encoding="utf-8").read())
    except Exception:
        import yaml  # noqa: F401  (回退，环境通常无 PyYAML)
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)


class StateMachine:
    def __init__(self, schema_path=None, event_log=None, state_dir=None, key=None):
        self.schema_path = schema_path or DEFAULT_SCHEMA
        try:
            self._schema = load_schema(self.schema_path)
        except Exception as e:
            raise StateLoadError("cannot load state schema %s: %s" % (self.schema_path, e))
        self.states = set(self._schema.get("states", []))
        self.initial = self._schema.get("initial")
        self.transitions = self._schema.get("transitions", [])
        if not self.initial or not self.states:
            raise StateLoadError("state schema missing initial/states")
        self.event_log = event_log or EventLog(
            os.path.join(state_dir or ".", "task-events.log"),
            KeyProvider(key=key))
        self.state_dir = state_dir or os.path.join(".", "runtime", "learning", "state")

    # ------------------------------------------------------------------
    # 持久态（每修订周期一个文件）
    # ------------------------------------------------------------------
    @staticmethod
    def _safe_name(cycle_id):
        # 仅允许安全字符，避免路径穿越
        return "".join(c if (c.isalnum() or c in "._-") else "_" for c in cycle_id)

    def _state_path(self, cycle_id):
        return os.path.join(self.state_dir, "%s.state.json" % self._safe_name(cycle_id))

    def get_state(self, cycle_id):
        p = self._state_path(cycle_id)
        if not os.path.exists(p):
            return None
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f).get("current_state")

    def _set_state(self, cycle_id, state):
        p = self._state_path(cycle_id)
        os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"current_state": state}, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)

    # ------------------------------------------------------------------
    # 转换匹配
    # ------------------------------------------------------------------
    def find_transition(self, frm, to, via, condition):
        for t in self.transitions:
            if t.get("from") != frm or t.get("to") != to or t.get("via") != via:
                continue
            tc = t.get("condition")
            if tc is None:
                # 该转换不限定 condition：调用方须传 None/空/"ok"
                if condition in (None, "", "ok"):
                    return t
            elif condition == tc:
                return t
        return None

    def legal_transitions(self, frm):
        return [t for t in self.transitions if t.get("from") == frm]

    # ------------------------------------------------------------------
    # 核心：CAS + via + condition + 持久化 + 不可变事件
    # ------------------------------------------------------------------
    def transition_state(self, cycle_id, expected_state, next_state, via,
                         condition=None, actor_id=None, task_id=None):
        # ① 当前持久态（未初始化视为 initial）
        current = self.get_state(cycle_id) or self.initial
        # ② CAS：期望态必须等于当前态
        if current != expected_state:
            raise CasConflict(
                "cas conflict: current=%s expected=%s (cycle=%s)" %
                (current, expected_state, cycle_id))
        # ③ 合法性 + via + condition 三者须同时匹配 SSOT
        t = self.find_transition(expected_state, next_state, via, condition)
        if t is None:
            raise IllegalTransition(
                "no legal transition %s->%s via=%s condition=%s (cycle=%s)" %
                (expected_state, next_state, via, condition, cycle_id))
        # ④ 签名追加 STATE_CHANGE 事件（权威提交点，仅 Broker 可成功）
        ev = self.event_log.append(
            "STATE_CHANGE", actor_id or "system", task_id or cycle_id,
            operation=via, resource_refs=[cycle_id],
            details={"from": expected_state, "to": next_state, "condition": condition})
        # ⑤ 持久化新态（原子写）
        self._set_state(cycle_id, next_state)
        return {"cycle_id": cycle_id, "from": expected_state, "to": next_state,
                "via": via, "condition": condition, "event_id": ev["event_id"]}

    # ------------------------------------------------------------------
    # 一致性校验：重放事件日志得到应然态，与持久态比对
    # ------------------------------------------------------------------
    def verify_consistency(self, cycle_id):
        expected = self.initial
        events = [e for e in self.event_log.read_events()
                  if e.get("event_type") == "STATE_CHANGE"
                  and cycle_id in (e.get("resource_refs") or [])]
        for e in events:
            d = e.get("details") or {}
            frm = d.get("from")
            to = d.get("to")
            if frm != expected:
                return {"consistent": False,
                        "error": "replay discontinuity at event %s" % e.get("event_id"),
                        "replayed": expected, "persisted": self.get_state(cycle_id)}
            expected = to
        persisted = self.get_state(cycle_id) or self.initial
        if expected != persisted:
            return {"consistent": False,
                    "error": "persisted state %s != replayed %s (cycle=%s)" %
                             (persisted, expected, cycle_id),
                    "replayed": expected, "persisted": persisted}
        return {"consistent": True, "current_state": expected, "events": len(events)}


def local_state_machine(root, key=None, schema_path=None):
    """便捷：以 ephemeral 密钥构造本地状态机（测试 / 单进程演示）。"""
    state_dir = os.path.join(root, "runtime", "learning", "state")
    log_path = os.path.join(root, "runtime", "learning", "task-events.log")
    el = EventLog(log_path, KeyProvider(key=key))
    return StateMachine(schema_path=schema_path, event_log=el, state_dir=state_dir, key=key)
