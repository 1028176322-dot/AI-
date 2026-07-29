# -*- coding: utf-8 -*-
"""任务系统引擎（Task System Engine）—— 平台操作中心核心。

文件系统即状态：每个任务 = tasks/<status>/<TASK-ID>.yaml。
状态转移 = 移动文件 + 更新 task.status。

提供：create_task / create_goal / promote / claim / start / submit / review /
      complete / fail / retry / route / list_tasks / show_task
所有写操作均写 audit/，并在关键转移时联动 project/status.yaml。
"""
import os
import sys
import shutil
import datetime
import re

HERE = os.path.dirname(os.path.abspath(__file__))
# [Phase2] 把 scripts 各分组目录加入 sys.path，保持跨组裸名 import 可用
_SCRIPTS = os.path.dirname(HERE)
if os.path.isdir(_SCRIPTS):
    for _d in os.listdir(_SCRIPTS):
        _p = os.path.join(_SCRIPTS, _d)
        if os.path.isdir(_p) and _p not in sys.path:
            sys.path.insert(0, _p)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _gov
import audit_log
import status_update
import task_templates as TT
import feedback_learning
import reader_panel
import project_layout

STATES = ["backlog", "ready", "claimed", "running", "submitted",
          "reviewing", "passed", "completed", "failed", "archive"]
TRANSITIONS = {
    "backlog":   ["ready", "archive"],
    "ready":     ["claimed", "archive"],
    "claimed":   ["running", "archive"],
    "running":   ["submitted", "failed", "archive"],
    "submitted": ["reviewing", "archive"],
    "reviewing": ["passed", "failed", "archive"],
    "passed":    ["completed", "archive"],
    "completed": ["archive"],
    "failed":    ["ready", "archive"],
    "archive":   [],
}
VALID_TYPES = ["chapter_write", "chapter_review", "chapter_fix", "continuity_fix",
               "chapter_publish", "nkb_update", "candidate_review", "plan_write", "goal_decompose",
               "asset_create", "experiment", "quality_score", "impact_analysis",
               "project_design", "system_maintenance", "system_verify",
               "nkb_sync", "human_gate"]
for _template_type in TT.registry():
    if _template_type not in VALID_TYPES:
        VALID_TYPES.append(_template_type)
VALID_PRIORITY = ["critical", "high", "normal", "low"]


def _outline_precheck(root, task):
    """Strict outline gate for projects that entered governed planning."""
    if not project_layout.is_strict(root):
        return
    policy = os.path.join(
        root, "sources", "outline", "_intake", "planning-policy.yaml")
    if not os.path.isfile(policy):
        return
    if (task or {}).get("type") not in (
            "chapter_write", "chapter_fix", "continuity_fix"):
        return
    try:
        import outline_governance
        chapter = (task or {}).get("chapter_ref")
        chapter_id = None
        match = re.search(r"(\d+)", str(chapter or ""))
        if match:
            chapter_id = "CH-%03d" % int(match.group(1))
        report = outline_governance.validate_project(
            root, target_chapter=chapter_id, write=False,
            require_approved=True)
    except Exception as exc:
        raise ValueError("outline governance failed: %s" % exc)
    body = report["outline_validation"]
    if body["gate"]["decision"] != "proceed":
        raise ValueError(
            "outline gate=block: %s" %
            "; ".join(body["gate"]["reasons"][:8]))
    try:
        import writing_strategy
        writing_strategy.build(
            root, chapter_id, write=True)
    except Exception as exc:
        raise ValueError(
            "writing strategy gate=block: %s" % exc)


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _tasks_dir(root):
    return os.path.join(root, "tasks")


def _state_dir(root, state):
    return os.path.join(_tasks_dir(root), state)


def _goal_dir(root):
    return os.path.join(_tasks_dir(root), "goals")


def _ensure(root):
    for s in STATES:
        os.makedirs(_state_dir(root, s), exist_ok=True)
    os.makedirs(_goal_dir(root), exist_ok=True)


def find_task(root, task_id):
    for s in STATES:
        p = os.path.join(_state_dir(root, s), task_id + ".yaml")
        if os.path.isfile(p):
            try:
                d = _gov.load_yaml(p)
            except Exception:
                continue
            if not isinstance(d, dict):
                continue
            if d.get("obsolete"):
                continue
            # 仅接受 folder 名 == 文件内 task.status 的文件，忽略残留/错位文件
            if (d.get("task") or {}).get("status") != s:
                continue
            return s, p
    return None, None


def load_task(root, task_id):
    st, p = find_task(root, task_id)
    if not p:
        return None, None
    return st, _gov.load_yaml(p)


def _state_of(root, task_id):
    st, _ = find_task(root, task_id)
    return st


def _move(root, task_id, data, new_state):
    old_st, old_p = find_task(root, task_id)
    new_p = os.path.join(_state_dir(root, new_state), task_id + ".yaml")
    data = dict(data)
    t = dict(data.get("task", {}))
    t["status"] = new_state
    data["task"] = t
    os.makedirs(os.path.dirname(new_p), exist_ok=True)
    with open(new_p, "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(data))
    # 删除旧文件：优先 os.remove；若被安全删除拦截（沙箱可能 sys.exit），
    # 退化为 rename 为 .obsolete；再失败则把旧文件标记为 obsolete 覆盖写。
    # 三种情况下 find_task 都会忽略 obsolete / folder≠status 的残留文件。
    if old_p and os.path.isfile(old_p) and os.path.abspath(old_p) != os.path.abspath(new_p):
        try:
            os.remove(old_p)
        except BaseException:
            try:
                os.rename(old_p, old_p + ".obsolete")
            except BaseException:
                try:
                    with open(old_p, "w", encoding="utf-8") as f:
                        f.write(_gov.dump_block({"obsolete": True, "superseded_by": new_p}))
                except BaseException:
                    pass
    return new_p


def _ensure_task_packet(root, task_id):
    """Build or refresh the reusable execution packet for a governed task."""
    # Local import avoids the task_engine <-> task_packet module cycle.
    import task_packet
    return task_packet.build_packet(root, task_id)


def _deps_completed(root, task_id, deps):
    for d in (deps or []):
        if _state_of(root, d) != "completed":
            return False
    return True


def _deps_ready(root, task_id, deps, task_type=None):
    """Review successors consume submitted work; ordinary tasks require completion."""
    review_types = {
        "chapter_write", "chapter_review", "candidate_review", "system_verify", "nkb_sync",
    }
    allowed = (
        {"submitted", "reviewing", "passed", "completed"}
        if task_type in review_types else {"completed"}
    )
    for dependency in (deps or []):
        if _state_of(root, dependency) not in allowed:
            return False
    return True


def _mark_resolved_failures(root, resolver_task):
    """Close failed-task blockers explicitly superseded by a completed task."""
    resolver_id = (resolver_task or {}).get("id")
    for failed_id in (resolver_task or {}).get("resolves") or []:
        state, data = load_task(root, failed_id)
        if state != "failed" or not data:
            continue
        failure = data["task"].setdefault("failure", {})
        failure["resolved_by"] = resolver_id
        failure["resolved_at"] = _now()
        _move(root, failed_id, data, "failed")
        audit_log.record(
            root,
            "task_resolve_failure",
            agent="task-system",
            task_id=failed_id,
            result="success",
            detail="resolved_by=%s" % resolver_id,
        )


def _impact_precheck(root, task_id, t):
    """强制预检：claim/start 前对内容型任务跑冲击分析，gate=block 则阻断。

    仅对内容型任务（chapter_write/chapter_fix/continuity_fix/nkb_update/asset_create）
    生效；其余任务跳过。工具缺失或分析异常时放行（不阻断主流程）。
    """
    tt = (t or {}).get("type")
    if tt not in ("chapter_write", "chapter_fix", "continuity_fix", "nkb_update", "asset_create"):
        return
    try:
        import impact_analyzer
    except Exception:
        return
    try:
        rep = impact_analyzer.analyze_task(root, task_id, diff_summary="pre-claim/start gate", write=False)
    except Exception:
        return
    if (rep.get("gate") or {}).get("decision") == "block":
        reasons = (rep.get("gate") or {}).get("reasons") or ["影响已发布内容"]
        raise ValueError("冲击分析 gate=block：%s；需 human_gate 任务放行" % "；".join(reasons))


def _quality_precheck(root, task_id, t):
    """强制预检：submit 前对章节文本型任务跑质量评分，gate=block 则阻断提交。

    仅对章节文本型任务（chapter_write/chapter_fix/continuity_fix/asset_create）
    生效；nkb_update（数据型）与其余任务跳过——NKB 数据改动不应被章节质量门禁 block。
    工具缺失或评分异常时放行（不阻断主流程）。
    """
    tt = (t or {}).get("type")
    if tt not in ("chapter_write", "chapter_fix", "continuity_fix", "asset_create"):
        return
    try:
        import quality_scorer
    except Exception:
        return
    try:
        rep = quality_scorer.score_task(root, task_id, proposed_by="quality-scorer", write=False)
    except Exception:
        return
    if (rep.get("gate") or {}).get("decision") == "block":
        reasons = (rep.get("gate") or {}).get("reasons") or ["质量不达标"]
        raise ValueError("质量评分 gate=block：%s；须修复后重新 submit 或 human_gate 放行" % "；".join(reasons))


def _reader_precheck(root, task_id, t):
    """强制预检：submit 前对章节文本型任务跑读者模拟，gate=block 则阻断提交。

    仅对章节文本型任务（chapter_write/chapter_fix/continuity_fix/asset_create）
    生效；nkb_update（数据型）与其余任务跳过。
    工具缺失或评分异常时放行（不阻断主流程）。
    """
    tt = (t or {}).get("type")
    if tt not in ("chapter_write", "chapter_fix", "continuity_fix", "asset_create"):
        return
    try:
        import reader_simulator
    except Exception:
        return
    try:
        rep = reader_simulator.simulate_task(root, task_id, proposed_by="reader-sim", write=False)
    except Exception:
        return
    if (rep.get("gate") or {}).get("decision") == "block":
        reasons = (rep.get("gate") or {}).get("reasons") or ["读者体验致命"]
        raise ValueError("读者模拟 gate=block：%s；须修复后重新 submit 或 human_gate 放行" % "；".join(reasons))


def _knowledge_output_precheck(root, task_id, task, artifact, outputs):
    """Strict projects require an explicit chapter knowledge delta and handoff."""
    if not project_layout.is_strict(root):
        return
    if (task or {}).get("type") not in (
            "chapter_write", "chapter_fix", "continuity_fix"):
        return
    outputs = outputs or {}
    required = {
        "chapter_draft": outputs.get("chapter_draft") or artifact,
        "candidate_facts": outputs.get("candidate_facts"),
        "handoff": outputs.get("handoff"),
    }
    missing = []
    for name, value in required.items():
        path = value if value and os.path.isabs(value) else (
            os.path.join(root, value) if value else None)
        if not path or not os.path.isfile(path):
            missing.append(name)
    if missing:
        raise ValueError(
            "chapter knowledge outputs missing: %s" % ", ".join(missing))
    candidate_path = required["candidate_facts"]
    if not os.path.isabs(candidate_path):
        candidate_path = os.path.join(root, candidate_path)
    delta = _gov.load_yaml(candidate_path) or {}
    body = delta.get("knowledge_delta")
    if not isinstance(body, dict):
        raise ValueError("candidate_facts must contain knowledge_delta")
    for field in ("chapter_ref", "base_snapshot", "candidates"):
        if body.get(field) is None:
            raise ValueError("knowledge_delta missing field: %s" % field)
    if not isinstance(body.get("candidates"), list):
        raise ValueError("knowledge_delta.candidates must be a list")
    if not body["candidates"] and not body.get("no_change_reason"):
        raise ValueError(
            "empty knowledge_delta requires no_change_reason")
    if body["candidates"]:
        platform_root = _gov.find_platform_root()
        candidate_schema = _gov.load_yaml(os.path.join(
            platform_root, "core", "contracts",
            "nkb-candidate.schema.yaml")) or {}
        for index, candidate in enumerate(body["candidates"]):
            label = "knowledge_delta.candidates[%d]" % index
            if not isinstance(candidate, dict):
                raise ValueError("%s must be a mapping" % label)
            for field in candidate_schema.get("required") or []:
                if candidate.get(field) is None:
                    raise ValueError("%s missing field: %s" % (
                        label, field))
            if candidate.get("operation") not in (
                    candidate_schema.get("allowed_operations") or []):
                raise ValueError("%s operation is invalid" % label)
            if candidate.get("target_component") not in (
                    candidate_schema.get(
                        "allowed_target_components") or []):
                raise ValueError(
                    "%s target_component is invalid" % label)
            if candidate.get("status") not in (
                    candidate_schema.get("allowed_status") or []):
                raise ValueError("%s status is invalid" % label)
            source = candidate.get("source")
            if not isinstance(source, dict):
                raise ValueError("%s.source must be a mapping" % label)
            for field in candidate_schema.get("source_required") or []:
                if source.get(field) is None:
                    raise ValueError("%s.source missing field: %s" % (
                        label, field))
            classification = candidate.get("classification")
            if not isinstance(classification, dict):
                raise ValueError(
                    "%s.classification must be a mapping" % label)
            for field in candidate_schema.get(
                    "classification_required") or []:
                if classification.get(field) is None:
                    raise ValueError(
                        "%s.classification missing field: %s" % (
                            label, field))
            if classification.get("fact_type") not in (
                    candidate_schema.get("allowed_fact_types") or []):
                raise ValueError(
                    "%s.classification.fact_type is invalid" % label)
    handoff_path = required["handoff"]
    if not os.path.isabs(handoff_path):
        handoff_path = os.path.join(root, handoff_path)
    handoff = _gov.load_yaml(handoff_path) or {}
    hbody = handoff.get("nkb_handoff")
    if not isinstance(hbody, dict):
        raise ValueError("handoff must contain nkb_handoff")
    for field in (
            "session_id", "project_id", "base_snapshot",
            "candidate_facts", "potential_conflicts", "recommended_actions"):
        if hbody.get(field) is None:
            raise ValueError("nkb_handoff missing field: %s" % field)


def _writing_strategy_output_precheck(
        root, task_id, task, outputs):
    """Governed outline projects require evidence that craft matched plan."""
    if not project_layout.is_strict(root):
        return
    if (task or {}).get("type") not in (
            "chapter_write", "chapter_fix", "continuity_fix"):
        return
    policy = os.path.join(
        root, "sources", "outline", "_intake",
        "planning-policy.yaml")
    if not os.path.isfile(policy):
        return
    value = (outputs or {}).get("writing_strategy_evidence")
    path = (
        value if value and os.path.isabs(value)
        else os.path.join(root, value) if value else None)
    if not path or not os.path.isfile(path):
        raise ValueError("writing_strategy_evidence missing")
    try:
        import writing_strategy
        ok, errors, _ = writing_strategy.validate_evidence(
            path, root, (task or {}).get("chapter_ref"))
    except Exception as exc:
        raise ValueError(
            "writing strategy evidence validation failed: %s" % exc)
    if not ok:
        raise ValueError(
            "writing strategy evidence gate=block: %s" %
            "; ".join(errors[:8]))


# ───────────────────────── 创建 ─────────────────────────
def create_task(root, task_dict, model="unknown", author="planner-agent"):
    """创建任务。无依赖或依赖已 completed -> ready；否则 backlog。返回 (state, path)。"""
    _ensure(root)
    t = dict(task_dict.get("task", task_dict))
    task_id = t.get("id")
    if not task_id:
        raise ValueError("task.id 必填")
    if t.get("type") and t["type"] not in VALID_TYPES:
        raise ValueError("未知 task.type: %s" % t["type"])
    if t.get("priority") and t["priority"] not in VALID_PRIORITY:
        raise ValueError("未知 task.priority: %s" % t["priority"])
    t.setdefault("version", 1)
    t.setdefault("created", _now())
    t.setdefault("created_by", author)
    t.setdefault("urgency", "normal")
    deps = t.get("dependencies") or []
    # 循环依赖浅检：依赖必须在 tasks 中存在或为合法 id
    init_state = "ready" if _deps_ready(
        root, task_id, deps, t.get("type")) else "backlog"
    t["status"] = init_state
    data = {"task": t}
    p = _move(root, task_id, data, init_state)
    _ensure_task_packet(root, task_id)
    audit_log.record(root, "task_create", agent=author, model=model,
                     task_id=task_id, files=[os.path.relpath(p, root)],
                     result="success", detail="type=%s -> %s" % (t.get("type"), init_state))
    return init_state, p


def create_goal(root, goal_dict, model="unknown", author="planner-agent"):
    _ensure(root)
    g = dict(goal_dict.get("goal", goal_dict))
    gid = g.get("id")
    if not gid:
        raise ValueError("goal.id 必填")
    g.setdefault("status", "active")
    g.setdefault("created", _now())
    g.setdefault("created_by", author)
    g.setdefault("success", [])
    os.makedirs(_goal_dir(root), exist_ok=True)
    p = os.path.join(_goal_dir(root), gid + ".yaml")
    with open(p, "w", encoding="utf-8") as f:
        f.write(_gov.dump_block({"goal": g}))
    audit_log.record(root, "task_create", agent=author, model=model,
                     task_id=gid, files=[os.path.relpath(p, root)],
                     result="success", detail="goal created")
    return p


# ───────────────────────── 流转 ─────────────────────────
def promote(root, task_id, model="unknown", author="task-scheduler"):
    """backlog -> ready（依赖全部 completed）。"""
    st, data = load_task(root, task_id)
    if st is None:
        raise FileNotFoundError(task_id)
    if st != "backlog":
        return st, "已是 %s，无需 promote" % st
    deps = (data.get("task") or {}).get("dependencies") or []
    task_type = (data.get("task") or {}).get("type")
    if not _deps_ready(root, task_id, deps, task_type):
        return st, "依赖尚未满足，停留 backlog"
    if task_type == "chapter_publish" and project_layout.is_strict(root):
        manifest_path = os.path.join(root, "NKB", "manifest.yaml")
        manifest = _gov.load_yaml(manifest_path) if os.path.isfile(
            manifest_path) else {}
        snapshot = ((manifest or {}).get("nkb") or {}).get("snapshot_id")
        if not snapshot:
            return st, "NKB sync completed but snapshot_id is missing"
        data["task"]["knowledge_snapshot"] = snapshot
        values = data["task"].setdefault("inputs", {}).setdefault(
            "values", {})
        values["nkb_snapshot_after"] = snapshot
    _move(root, task_id, data, "ready")
    _ensure_task_packet(root, task_id)
    if task_type == "chapter_publish":
        target = (data.get("task") or {}).get("publish_target")
        if target:
            _grant_for_publish(root, task_id, target)
    audit_log.record(root, "task_create", agent=author, model=model, task_id=task_id,
                     result="success", detail="promoted backlog->ready")
    return "ready", "promoted"


def ready_check(root, task_id):
    """Ready Check：任务进入 claimed 前的就绪校验。返回 (ok, report)。

    检查：依赖完成 / 必填输入存在 / contract 解析 / role 可用 /
    permissions 有效 / project 状态 / nkb_snapshot(approved_event) / output_path 可用。
    """
    st, data = load_task(root, task_id)
    if st is None:
        return False, {"error": "task not found"}
    t = (data or {}).get("task", {})
    tt = t.get("type")
    report = {"task_id": task_id, "status": st, "checks": {}}
    ok = True
    # 1. 依赖完成
    deps = t.get("dependencies") or []
    dep_ok = _deps_ready(root, task_id, deps, tt)
    report["checks"]["dependencies_complete"] = dep_ok
    ok = ok and dep_ok
    # 2. 必填输入存在：统一复用 Task Packet 的解析器，避免 Ready Check
    # 与 input-index 对同一输入给出相反结论。
    inp = (t.get("inputs") or {}).get("required") or []
    try:
        import task_packet as _task_packet
        missing = []
        resolved_inputs = {}
        for item in inp:
            path, resolved = _task_packet._resolve_input(root, item, t)
            resolved_inputs[item] = {"path": path, "resolved": bool(resolved)}
            if not resolved:
                missing.append(item)
    except Exception as exc:
        missing = list(inp)
        resolved_inputs = {"error": str(exc)}
    inp_ok = not missing
    report["checks"]["required_inputs_exist"] = inp_ok
    report["checks"]["missing_inputs"] = missing
    report["checks"]["resolved_inputs"] = resolved_inputs
    ok = ok and inp_ok
    # 3. contract 解析（type 必须在 VALID_TYPES）
    report["checks"]["contract_resolved"] = tt in VALID_TYPES
    ok = ok and report["checks"]["contract_resolved"]
    # 4. role 可用（required_role 已声明）
    report["checks"]["role_available"] = bool((t.get("agent") or {}).get("required_role"))
    ok = ok and report["checks"]["role_available"]
    # 5. permissions 有效
    perms = t.get("permissions") or {}
    perm_ok = ("write" in perms) or ("read" in perms)
    report["checks"]["permissions_valid"] = perm_ok
    ok = ok and perm_ok
    # 6. project 状态有效（占位：始终有效）
    report["checks"]["project_state_valid"] = True
    # 7. nkb_snapshot / approved_event（nkb_update 须持 approved_event）
    if tt == "nkb_update":
        req_inputs = ((t.get("inputs") or {}).get("required") or [])
        has_ae = (t.get("approved_event") is not None) or any(
            isinstance(i, str) and "approved_event" in i.lower() for i in req_inputs
        )
        report["checks"]["approved_event_present"] = has_ae
        ok = ok and has_ae
    # 8. output_path 可用（workspace 已建或处于 ready）
    report["checks"]["output_path_available"] = bool(t.get("workspace")) or (st == "ready")
    ok = ok and report["checks"]["output_path_available"]
    # 9. 单 Agent 执行策略校验（agent-execution.policy.yaml + 任务 execution_policy）
    ep = t.get("execution_policy") or {}
    if not ep and tt:
        # 任务未内联时从模板继承，确保模板策略被强制
        try:
            _plat = _gov.find_platform_root()
            _tmpl = TT.load(tt)
            ep = _tmpl.get("execution_policy") or {}
        except Exception:
            ep = {}
    _policy_ok = True
    if ep:
        _ma = ep.get("max_agents")
        if _ma is not None and int(_ma) != 1:
            _policy_ok = False
        if ep.get("subagent_allowed") not in (False, "false"):
            _policy_ok = False
        if ep.get("delegation_allowed") not in (False, "false"):
            _policy_ok = False
    report["checks"]["single_agent_policy"] = _policy_ok
    ok = ok and _policy_ok
    return ok, report


def claim(root, task_id, agent, role, model="unknown", lease_min=60):
    st, data = load_task(root, task_id)
    if st is None:
        raise FileNotFoundError(task_id)
    if st != "ready":
        raise ValueError("claim 要求状态 ready，当前 %s" % st)
    t = data["task"]
    _outline_precheck(root, t)
    req_role = (t.get("agent") or {}).get("required_role")
    if req_role and role != req_role and role != "task-scheduler":
        raise ValueError("角色不匹配：task 需 %s，agent 为 %s" % (req_role, role))
    owner = t.get("owner")
    if owner and owner != agent:
        raise ValueError("任务已被 %s 接取，不能重复 claim" % owner)
    _impact_precheck(root, task_id, t)
    t["owner"] = agent
    t["claimed_at"] = _now()
    t["lease_expire"] = (datetime.datetime.now() + datetime.timedelta(minutes=lease_min)).isoformat(timespec="seconds")
    _move(root, task_id, data, "claimed")
    # 状态联动：章节写作任务进入 write 步
    if t.get("type") == "chapter_write":
        status_update.set_step(root, chapter=t.get("chapter_ref"), step="write", by="task-system")
    audit_log.record(root, "task_claim", agent=agent, role=role, model=model,
                     task_id=task_id, result="success", detail="claimed by %s" % agent)
    return "claimed"


def start(root, task_id, agent, role="unknown", model="unknown"):
    st, data = load_task(root, task_id)
    if st != "claimed":
        raise ValueError("start 要求 claimed，当前 %s" % st)
    _impact_precheck(root, task_id, data["task"])
    _move(root, task_id, data, "running")
    # 任务工作区隔离：产物先落 tasks/running/<id>/outputs/，Gate 后再移入正式目录
    ws = os.path.join(_state_dir(root, "running"), task_id, "outputs")
    os.makedirs(ws, exist_ok=True)
    data["task"]["status"] = "running"
    data["task"]["workspace"] = os.path.relpath(ws, root)
    with open(os.path.join(_state_dir(root, "running"), task_id + ".yaml"), "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(data))
    audit_log.record(root, "task_start", agent=agent, role=role, model=model,
                     task_id=task_id, result="success",
                     detail="running; workspace=%s" % data["task"]["workspace"])
    return "running"


def submit(root, task_id, artifact, outputs=None, checks=None,
           agent="unknown", role="unknown", model="unknown"):
    st, data = load_task(root, task_id)
    if st != "running":
        raise ValueError("submit 要求 running，当前 %s" % st)
    outputs = outputs or {}
    if data["task"].get("type") in (
            "chapter_write", "chapter_fix", "continuity_fix"):
        outputs.setdefault("chapter_draft", artifact)
    _knowledge_output_precheck(
        root, task_id, data["task"], artifact, outputs)
    _writing_strategy_output_precheck(
        root, task_id, data["task"], outputs)
    _quality_precheck(root, task_id, data["task"])
    _reader_precheck(root, task_id, data["task"])
    checks = checks or {}
    failed = [k for k, v in checks.items() if v not in ("pass", True)]
    if failed:
        _move(root, task_id, data, "failed")
        data["task"]["failure"] = {"reason": "self_check_failed", "checks": checks}
        _move(root, task_id, data, "failed")
        audit_log.record(root, "task_submit", agent=agent, role=role, model=model,
                         task_id=task_id, result="fail", detail="checks 未全 pass: %s" % failed)
        return "failed", "self-check 未通过"
    t = data["task"]
    t["artifact"] = artifact
    t["outputs"] = outputs
    t["submission"] = {"checks": checks, "at": _now()}
    _move(root, task_id, data, "submitted")
    # 自动后继链：以 task template.next_tasks.on_submit 为唯一事实源。
    next_types = TT.next_types(t.get("type"), "on_submit")
    next_type = next_types[0] if next_types else None
    created_next = None
    if next_type and next_type in VALID_TYPES:
        next_template = TT.load(next_type)
        next_role = next_template.get("required_role") or "task-scheduler"
        nid = "%s-%s" % (task_id, next_type.upper().replace("_", "-"))
        next_required = next_template.get("required_inputs") or [artifact]
        next_values = {
            "source_task": task_id,
            "source_artifact": artifact,
        }
        source_input_values = (
            (t.get("inputs") or {}).get("values") or {})
        for output_name in next_required:
            if outputs.get(output_name):
                next_values[output_name] = outputs[output_name]
            elif source_input_values.get(output_name) not in (
                    None, "", False):
                next_values[output_name] = source_input_values[output_name]
        if next_type == "chapter_review":
            next_values.setdefault("chapter_draft", artifact)
        next_task = {
            "task": {
                "id": nid,
                "version": 1,
                "project": t.get("project"),
                "type": next_type,
                "title": "%s 后继 %s" % (task_id, next_type),
                "status": "ready",
                "priority": t.get("priority", "high"),
                "created": _now(),
                "created_by": "task-system",
                "goal": t.get("goal"),
                "chapter_ref": t.get("chapter_ref"),
                "conversation_request_id": t.get("conversation_request_id"),
                "dependencies": [task_id],
                "inputs": {
                    "required": next_required,
                    "values": next_values,
                },
                "expected_outputs": next_template.get("allowed_outputs") or ["next-output"],
                "acceptance": {"criteria": ["按 %s 模板完成" % next_type]},
                "permissions": next_template.get("permissions") or {
                    "read": ["tasks/**"],
                    "write": ["tasks/running/<id>/outputs/**"],
                    "forbidden": [],
                },
                "agent": {"required_role": next_role},
                "execution_policy": next_template.get("execution_policy") or {},
            }
        }
        _move(root, nid, next_task, "ready")
        _ensure_task_packet(root, nid)
        created_next = nid
    audit_log.record(root, "task_submit", agent=agent, role=role, model=model,
                     task_id=task_id, result="success",
                     detail="artifact=%s next=%s" % (artifact, created_next))
    return "submitted", created_next


def _create_on_pass_successors(root, source_id, source_task, model, author):
    """Instantiate template-declared on_pass successors after real review."""
    created = []
    for next_type in TT.next_types(source_task.get("type"), "on_pass"):
        # Legacy publish is created by the dedicated content-review branch.
        # strict-v2 publish is allowed here only after the governed NKB sync.
        if (next_type == "chapter_publish"
                and not project_layout.is_style_strict(root)):
            continue
        next_template = TT.load(next_type)
        task_id = "%s-%s" % (
            source_id, next_type.upper().replace("_", "-"))
        existing, _ = load_task(root, task_id)
        if existing:
            created.append(task_id)
            continue
        required = next_template.get("required_inputs") or []
        outputs = source_task.get("outputs") or {}
        values = {
            "source_task": source_id,
            "source_artifact": source_task.get("artifact"),
        }
        source_input_values = (
            (source_task.get("inputs") or {}).get("values") or {})
        for name in required:
            if outputs.get(name) not in (None, "", False):
                values[name] = outputs[name]
            elif source_input_values.get(name) not in (
                    None, "", False):
                values[name] = source_input_values[name]
        successor = {
            "task": {
                "id": task_id,
                "version": 1,
                "project": source_task.get("project"),
                "type": next_type,
                "title": "%s 审批后继 %s" % (source_id, next_type),
                "status": "ready",
                "priority": source_task.get("priority", "high"),
                "created": _now(),
                "created_by": "task-system",
                "goal": source_task.get("goal"),
                "chapter_ref": source_task.get("chapter_ref"),
                "conversation_request_id":
                    source_task.get("conversation_request_id"),
                "dependencies": [source_id],
                "inputs": {
                    "required": required,
                    "values": values,
                },
                "expected_outputs":
                    next_template.get("allowed_outputs") or [],
                "acceptance": {
                    "criteria": ["按 %s 模板完成" % next_type],
                },
                "permissions": next_template.get("permissions") or {},
                "agent": {
                    "required_role":
                        next_template.get("required_role") or
                        "task-scheduler",
                },
                "execution_policy":
                    next_template.get("execution_policy") or {},
            },
        }
        _move(root, task_id, successor, "ready")
        _ensure_task_packet(root, task_id)
        audit_log.record(
            root, "task_create", agent=author, model=model,
            task_id=task_id, result="success",
            detail="created from %s on_pass" % source_id)
        created.append(task_id)
    return created


def review(root, task_id, decision, findings=None, reviewer="unknown",
           role="reviewer", model="unknown", outputs=None):
    """对审查任务做决策。pass -> 原任务 completed；fail -> 建 FIX 任务。"""
    st, data = load_task(root, task_id)
    if st not in ("submitted", "reviewing", "running", "claimed"):
        # 允许 reviewer 直接对 review 任务判（review 任务通常在 ready/claimed/running）
        pass
    t = data["task"]
    if outputs:
        t["outputs"] = dict(outputs)
        t["artifact"] = (
            outputs.get("review_report")
            or next(iter(outputs.values()), None))
    # 找被审查的原任务
    dep = (t.get("dependencies") or [None])[0]
    dep_type = None
    if dep:
        _, _dep_data = load_task(root, dep)
        dep_type = ((_dep_data or {}).get("task") or {}).get("type")

    # New strict projects require an evidence-complete reader panel before a
    # content review may pass. Projects without PROJECT_LAYOUT.yaml stay legacy.
    is_content_review = (
        t.get("type") == "chapter_review"
        and (dep_type is None or dep_type in (
            "chapter_write", "chapter_fix", "continuity_fix"))
    )
    if decision == "pass" and project_layout.is_strict(root) and is_content_review:
        panel_path = os.path.join(
            root, "runtime", "reader-panels",
            "PANEL-%s" % task_id, "report.yaml")
        if not os.path.isfile(panel_path):
            raise ValueError("reader panel missing: %s" % panel_path)
        panel_ok, panel_errors, panel_report = reader_panel.validate_panel(panel_path)
        if not panel_ok:
            raise ValueError("reader panel incomplete: %s" % "; ".join(panel_errors))
        if (panel_report.get("gate") or {}).get("decision") == "block":
            raise ValueError("reader panel gate is block")
        if dep:
            _, source_data = load_task(root, dep)
            source_task = (source_data or {}).get("task") or {}
            policy = os.path.join(
                root, "sources", "outline", "_intake",
                "planning-policy.yaml")
            if os.path.isfile(policy):
                evidence_value = (
                    (source_task.get("outputs") or {}).get(
                        "writing_strategy_evidence"))
                evidence_path = (
                    evidence_value if evidence_value and os.path.isabs(
                        evidence_value)
                    else os.path.join(root, evidence_value or ""))
                try:
                    import writing_strategy
                    evidence_ok, evidence_errors, _ = (
                        writing_strategy.validate_evidence(
                            evidence_path, root,
                            source_task.get("chapter_ref")))
                except Exception as exc:
                    raise ValueError(
                        "writing strategy review failed: %s" % exc)
                if not evidence_ok:
                    raise ValueError(
                        "writing strategy review gate=block: %s" %
                        "; ".join(evidence_errors[:8]))

    is_nkb_sync_review = (
        t.get("type") == "nkb_sync" and dep_type == "nkb_update")
    if decision == "pass" and project_layout.is_strict(
            root) and is_nkb_sync_review:
        try:
            import nkb_validator
            nkb_report = nkb_validator.validate_project(root)
        except Exception as exc:
            raise ValueError("canonical NKB validation failed: %s" % exc)
        if (nkb_report.get("gate") or {}).get("decision") == "block":
            messages = [
                item.get("detail", item.get("code", "unknown"))
                for item in nkb_report.get("findings", [])
                if item.get("severity") == "fail"
            ]
            raise ValueError(
                "canonical NKB validation failed: %s" %
                "; ".join(messages[:8]))
        manifest_path = os.path.join(root, "NKB", "manifest.yaml")
        manifest = _gov.load_yaml(manifest_path) if os.path.isfile(
            manifest_path) else {}
        if not ((manifest or {}).get("nkb") or {}).get("snapshot_id"):
            raise ValueError(
                "canonical NKB validation failed: manifest snapshot_id missing")

    if decision == "pass" and t.get("type") == "design_review":
        try:
            import design_expansion
            review_output = (
                (t.get("outputs") or {}).get("design_review_report")
                or t.get("artifact"))
            review_path = (
                review_output if review_output and os.path.isabs(
                    review_output)
                else os.path.join(root, review_output or ""))
            review_ok, review_errors, _ = (
                design_expansion.validate_review(review_path))
        except Exception as exc:
            raise ValueError("design review validation failed: %s" % exc)
        if not review_ok:
            raise ValueError(
                "design review cannot pass: %s" %
                "; ".join(review_errors[:8]))

    if decision == "pass" and t.get("type") == "design_approval":
        try:
            import design_expansion
            _, design_gate_report = design_expansion.design_gate(root)
        except Exception as exc:
            raise ValueError("design approval gate failed: %s" % exc)
        if design_gate_report["design_approval"]["decision"] != "pass":
            raise ValueError(
                "design approval gate is block: %s" %
                "; ".join(
                    design_gate_report["design_approval"]["reasons"]))

    if decision == "pass" and t.get("type") == "outline_refresh":
        try:
            import outline_governance
            outline_governance.approve_outline(
                root,
                approved_by=reviewer,
                evidence="task:%s" % task_id)
        except Exception as exc:
            raise ValueError(
                "outline refresh cannot pass: %s" % exc)

    # Findings become project-private writing guardrails and future regression
    # checks. Empty finding sets produce no memory entry.
    if findings and (
            is_content_review or dep_type in (
                "chapter_write", "chapter_fix", "continuity_fix")):
        feedback_learning.capture_findings(
            root, task_id, findings, decision=decision)
    # strict-v2 uses the template event router. An older PROJECT_LAYOUT marker
    # is not an implicit migration and therefore remains on the legacy path.
    style_strict = project_layout.is_style_strict(root)
    if decision == "pass" and style_strict and (
            is_content_review or is_nkb_sync_review):
        event_outputs = dict(t.get("outputs") or {})
        if is_content_review:
            review_report = (
                event_outputs.get("review_report") or t.get("artifact"))
            if not review_report:
                raise ValueError(
                    "strict-v2 chapter review requires review_report output")
            event_outputs = {"review_report": review_report}
        else:
            required_sync = ("nkb_sync_proof", "validation_report")
            missing_sync = [
                name for name in required_sync
                if not event_outputs.get(name)]
            if missing_sync:
                raise ValueError(
                    "strict-v2 NKB sync review missing outputs: %s" %
                    ", ".join(missing_sync))
            event_outputs = {
                name: event_outputs[name] for name in required_sync}
        if dep:
            dep_state, dep_data = load_task(root, dep)
            if dep_state and dep_state not in (
                    "completed", "failed", "archive"):
                dep_data["task"]["review"] = {
                    "decision": "pass", "at": _now()}
                _move(root, dep, dep_data, "completed")
                _mark_resolved_failures(root, dep_data["task"])
        result = finish_with_event(
            root, task_id, "on_pass", event_outputs,
            checks={"review_gate": "pass"}, actor=reviewer,
            role=role, model=model)
        audit_log.record(
            root, "task_review", agent=reviewer, role=role, model=model,
            task_id=task_id, result="success",
            detail="strict-v2 PASS; successors=%s" %
            result.get("successors"))
        return "completed", result
    if decision == "pass":
        _move(root, task_id, data, "passed")
        _move(root, task_id, data, "completed")
        pb_task_id = None
        if dep:
            dst, ddata = load_task(root, dep)
            if dst and dst not in ("completed", "failed", "archive", "passed"):
                ddata["task"]["review"] = {"decision": "pass", "at": _now()}
                _move(root, dep, ddata, "passed")
                _move(root, dep, ddata, "completed")
                # A chapter plan is accepted by the successful review of the
                # chapter produced from it. Close that planning parent so the
                # conversational task graph has no stranded submitted nodes.
                for plan_id in (ddata["task"].get("dependencies") or []):
                    plan_state, plan_data = load_task(root, plan_id)
                    if (plan_state in ("submitted", "passed")
                            and ((plan_data or {}).get("task") or {}).get("type")
                            == "plan_write"):
                        _move(root, plan_id, plan_data, "completed")
                        audit_log.record(
                            root, "task_complete", agent="task-system",
                            task_id=plan_id, result="success",
                            detail="accepted by reviewed chapter %s" % dep)
                _mark_resolved_failures(root, ddata["task"])
                if (ddata.get("task") or {}).get("type") in (
                        "chapter_write", "chapter_fix", "continuity_fix"):
                    status_update.set_step(root, step="done", blocked=False, by="task-system")
                _promote_dependents(root, dep, model, role)
                # 内容型任务审查通过：
                # strict 项目必须先回补 NKB、完成 canonical 校验，再开放发布；
                # legacy 项目维持原有直接发布兼容链。
                dep_type = (ddata.get("task") or {}).get("type")
                if dep_type in ("chapter_write", "chapter_fix", "continuity_fix"):
                    strict = project_layout.is_strict(root)
                    draft = (ddata.get("task") or {}).get("artifact") \
                        or (ddata.get("task") or {}).get("chapter_ref")
                    if not draft:
                        outs = (ddata.get("task") or {}).get("outputs") or {}
                        draft = outs.get("draft") or outs.get("build")
                    canon = resolve_canonical_target(draft, root) if draft else None
                    publish_dependencies = [dep]
                    publish_state = "ready"
                    nkb_update_id = None
                    if strict:
                        source_outputs = (
                            (ddata.get("task") or {}).get("outputs") or {})
                        candidate_facts = source_outputs.get(
                            "candidate_facts")
                        if not candidate_facts:
                            raise ValueError(
                                "strict chapter review cannot pass without "
                                "candidate_facts output")
                        update_template = TT.load("nkb_update")
                        nkb_update_id = "%s-NKB-UPDATE" % dep
                        update_task = {
                            "task": {
                                "id": nkb_update_id,
                                "version": 1,
                                "project": ddata["task"].get("project"),
                                "type": "nkb_update",
                                "title": "回补 %s 的候选事实到 NKB" % dep,
                                "status": "ready",
                                "priority": "high",
                                "created": _now(),
                                "created_by": "task-system",
                                "goal": ddata["task"].get("goal"),
                                "chapter_ref": ddata["task"].get(
                                    "chapter_ref"),
                                "dependencies": [dep],
                                "approved_event": task_id,
                                "inputs": {
                                    "required": [
                                        "candidate_facts",
                                        "approved_event",
                                    ],
                                    "values": {
                                        "candidate_facts": candidate_facts,
                                        "approved_event": task_id,
                                    },
                                },
                                "expected_outputs": update_template.get(
                                    "allowed_outputs") or [
                                        "nkb_change",
                                        "operation_manifest",
                                        "nkb_snapshot_after",
                                    ],
                                "acceptance": {
                                    "criteria": [
                                        "候选事实逐项接受、拒绝或标记冲突",
                                        "NKB snapshot_id 更新或显式确认无变化",
                                        "生成可审计 operation manifest",
                                    ],
                                },
                                "permissions": update_template.get(
                                    "permissions") or {},
                                "agent": {
                                    "required_role":
                                        update_template.get(
                                            "required_role") or
                                        "knowledge-manager",
                                },
                                "execution_policy": update_template.get(
                                    "execution_policy") or {},
                            }
                        }
                        _move(root, nkb_update_id, update_task, "ready")
                        _ensure_task_packet(root, nkb_update_id)
                        sync_id = "%s-NKB-SYNC" % nkb_update_id
                        publish_dependencies = [sync_id]
                        publish_state = "backlog"
                    pb_task_id = (
                        stable_publish_task_id(ddata["task"])
                        or "%s-PUBLISH" % dep)
                    review_artifact = t.get("artifact") or task_id
                    pb_task = {
                        "task": {
                            "id": pb_task_id,
                            "version": 1,
                            "project": ddata["task"].get("project"),
                            "type": "chapter_publish",
                            "title": "发布 %s 到正式正文" % dep,
                            "status": publish_state,
                            "priority": "high",
                            "created": _now(),
                            "created_by": "task-system",
                            "goal": ddata["task"].get("goal"),
                            "dependencies": publish_dependencies,
                            "inputs": {
                                "required": [draft] if draft else [],
                                "values": {
                                    "chapter_draft": draft,
                                    "review_report": review_artifact,
                                },
                            },
                            "publish_target": canon,
                            "expected_outputs": ["published-chapter"],
                            "acceptance": {"criteria": ["Publish Service 原子发布成功", "Manifest 更新"]},
                            "permissions": {"read": ["chapters/*", "NKB/*"], "write": [canon] if canon else ["第一卷_道生/*"], "forbidden": []},
                            "agent": {"required_role": "publish_service"},
                        }
                    }
                    _move(root, pb_task_id, pb_task, publish_state)
                    _ensure_task_packet(root, pb_task_id)
                    if canon and not strict:
                        _grant_for_publish(root, pb_task_id, canon)
        # The current review task itself may be a dependency (notably
        # nkb_sync -> chapter_publish), so promote against both the reviewed
        # source and the review node.
        _promote_dependents(root, task_id, model, role)
        _create_on_pass_successors(
            root, task_id, t, model, reviewer)
        audit_log.record(root, "task_review", agent=reviewer, role=role, model=model,
                         task_id=task_id, result="success", detail="PASS; publish=%s" % pb_task_id)
        return "completed", ("原任务已完成; publish=%s" % pb_task_id) if pb_task_id else "原任务已完成"
    else:
        _move(root, task_id, data, "failed")
        # 建 FIX 任务
        fix_id = None
        if dep:
            dst, ddata = load_task(root, dep)
            # 原任务保持在 submitted/reviewing，等待修复后重审
            sev = "high"
            cats = []
            for f in (findings or []):
                cats.append(f.get("category"))
            dep_type = (ddata.get("task") or {}).get("type")
            declared_fail_types = TT.next_types(t.get("type"), "on_fail")
            if declared_fail_types:
                # Template-declared remediation is authoritative.  In
                # particular, design/readiness failures return to
                # project_design instead of leaking into chapter fixes.
                fix_type = declared_fail_types[0]
                fix_template = TT.load(fix_type)
                fix_role = (
                    fix_template.get("required_role") or "task-scheduler")
                fix_id = "%s-%s" % (
                    task_id, fix_type.upper().replace("_", "-"))
                fix_dependencies = []
                fix_required = fix_template.get("required_inputs") or []
                fix_values = {
                    "source_task": dep,
                    "failed_review_task": task_id,
                    "review_findings": findings or [],
                }
                for source in (
                        ((ddata.get("task") or {}).get("inputs") or {}).get(
                            "values") or {},
                        (t.get("inputs") or {}).get("values") or {},
                        (t.get("outputs") or {})):
                    for name in fix_required:
                        if (name not in fix_values
                                and source.get(name) not in (
                                    None, "", False)):
                            fix_values[name] = source[name]
            elif dep_type == "system_maintenance":
                fix_id = "%s-FIX" % dep
                fix_type, fix_role = "system_maintenance", "system-maintainer"
            elif dep_type == "nkb_update":
                fix_id = "%s-FIX" % dep
                fix_type, fix_role = "nkb_update", "knowledge-manager"
            else:
                fix_id = "%s-FIX" % dep
                fix_type = "chapter_fix" if dep_type == "chapter_write" else "continuity_fix"
                fix_role = "fixer"
            if not declared_fail_types:
                fix_template = TT.load(fix_type)
                fix_dependencies = [dep]
                fix_required = [dep]
                fix_values = {}
            fix_task = {
                "task": {
                    "id": fix_id,
                    "version": 1,
                    "project": ddata["task"].get("project"),
                    "type": fix_type,
                    "title": "修复 %s" % dep,
                    "status": "ready",
                    "priority": "high",
                    "created": _now(),
                    "created_by": "task-system",
                    "goal": ddata["task"].get("goal"),
                    "dependencies": fix_dependencies,
                    "inputs": {
                        "required": fix_required,
                        "values": fix_values,
                    },
                    "expected_outputs": fix_template.get("allowed_outputs") or ["fixed-draft"],
                    "acceptance": {"criteria": ["修复 finding", "复审通过"]},
                    "permissions": fix_template.get("permissions") or {
                        "read": ["chapters/*", "NKB/*"],
                        "write": ["chapters/drafts/*"],
                        "forbidden": ["NKB/*", "core/*"],
                    },
                    "agent": {"required_role": fix_role},
                    "execution_policy": fix_template.get("execution_policy") or {},
                    "source_findings": findings or [],
                    "resolves": [dep, task_id],
                }
            }
            _move(root, fix_id, fix_task, "ready")
            _ensure_task_packet(root, fix_id)
            status_update.set_step(root, blocked=True, reason="review failed: %s" % (cats or ["unknown"]), by="task-system")
        audit_log.record(root, "task_review", agent=reviewer, role=role, model=model,
                         task_id=task_id, result="fail", detail="FAILED; fix=%s" % fix_id)
        return "failed", fix_id


def complete(root, task_id, model="unknown", author="task-scheduler"):
    st, data = load_task(root, task_id)
    if st != "passed":
        if st == "completed":
            return "completed", "已是 completed"
        raise ValueError("complete 要求 passed，当前 %s" % st)
    _move(root, task_id, data, "completed")
    _mark_resolved_failures(root, data["task"])
    audit_log.record(root, "task_complete", agent=author, model=model,
                     task_id=task_id, result="success", detail="completed")
    # 推进下游依赖
    _promote_dependents(root, task_id, model, author)
    return "completed"


def finish_service_task(
        root, task_id, model="unknown", author="publish_service",
        outputs=None):
    """服务任务（publish_service / nkb_commit_service）确定性收口。

    与 complete() 的区别：服务任务不经 review 生命周期（其产出由平台脚本确定性执行），
    因此从任意 live 态（ready/claimed/running/submitted/reviewing/passed）直接置 completed，
    不做依赖副作用（其依赖项通常已是 terminal）。用于发布/提交后闭环。
    """
    st, data = load_task(root, task_id)
    if st is None:
        raise FileNotFoundError(task_id)
    if st == "completed":
        return "completed"
    if outputs:
        data["task"]["outputs"] = outputs
        data["task"]["artifact"] = (
            outputs.get("published_chapter")
            or next(iter(outputs.values()), None))
    _move(root, task_id, data, "completed")
    audit_log.record(root, "task_complete", agent=author, model=model,
                     task_id=task_id, result="success", detail="service task finished")
    _promote_dependents(root, task_id, model, author)
    if outputs:
        _create_on_pass_successors(
            root, task_id, data["task"], model, author)
    return "completed"


def finish_with_event(
        root, task_id, event, outputs, checks=None, actor="unknown",
        role=None, model="unknown"):
    """Consume a template-declared style event through the governed router."""
    import style_orchestrator
    return style_orchestrator.finish_with_event(
        root, task_id, event, outputs, checks=checks, actor=actor,
        role=role, model=model)


def _promote_dependents(root, done_id, model, author):
    for s in ("backlog", "ready"):
        d = _state_dir(root, s)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith(".yaml"):
                continue
            tid = fn[:-5]
            _, td = load_task(root, tid)
            deps = (td.get("task") or {}).get("dependencies") or []
            if done_id in deps and s == "backlog":
                promote(root, tid, model, author)


def fail(root, task_id, reason, strategy="reload_context", max_retry=3,
         model="unknown", author="task-system"):
    st, data = load_task(root, task_id)
    if st in ("completed", "archive"):
        raise ValueError("终态不可 fail")
    data["task"]["failure"] = {"reason": reason, "strategy": strategy, "max_retry": max_retry}
    data["task"]["retry_count"] = data["task"].get("retry_count", 0)
    _move(root, task_id, data, "failed")
    status_update.set_step(root, blocked=True, reason="task failed: %s" % reason, by="task-system")
    audit_log.record(root, "task_fail", agent=author, model=model, task_id=task_id,
                     result="fail", detail=reason)
    return "failed"


def retry(root, task_id, model="unknown", author="task-scheduler"):
    st, data = load_task(root, task_id)
    if st != "failed":
        raise ValueError("retry 要求 failed，当前 %s" % st)
    rc = data["task"].get("retry_count", 0) + 1
    max_r = (data["task"].get("failure") or {}).get("max_retry", 3)
    if rc > max_r:
        raise ValueError("超过 max_retry(%d)，转人工" % max_r)
    data["task"]["retry_count"] = rc
    data["task"]["owner"] = None
    data["task"]["failure"] = None
    _move(root, task_id, data, "ready")
    status_update.set_step(root, blocked=False, by="task-system")
    audit_log.record(root, "task_create", agent=author, model=model, task_id=task_id,
                     result="success", detail="retry #%d -> ready" % rc)
    return "ready"


def route(root, role, capabilities):
    """扫描 ready/ 池，返回该 role+capabilities 可接取的任务列表。"""
    caps = set(capabilities or [])
    out = []
    d = _state_dir(root, "ready")
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".yaml"):
            continue
        tid = fn[:-5]
        _, td = load_task(root, tid)
        t = td.get("task", {})
        req_role = (t.get("agent") or {}).get("required_role")
        if req_role and req_role != role:
            continue
        if t.get("type") not in caps:
            continue
        out.append({
            "task_id": tid,
            "type": t.get("type"),
            "priority": t.get("priority"),
            "goal": t.get("goal"),
            "title": t.get("title"),
        })
    return out


def resolve_canonical_target(draft_rel, project_root):
    """把工作副本草稿路径解析为 canonical 正式正文路径。

    规则：
      - 若某卷目录下已存在同名词章文件 → 沿用其卷（修订/重发布保持原位）。
      - 否则落到第一个存在的卷目录（默认 第一卷_道生/；不存在则新建 第一卷_道生/）。
    草稿 chapters/drafts/第001章_道生.md → 第一卷_道生/第001章_道生.md
    """
    import re as _re
    fname = os.path.basename(draft_rel.replace("\\", "/"))
    if os.path.isfile(os.path.join(project_root, "PROJECT_LAYOUT.yaml")):
        return "chapters/approved/%s" % fname
    stem = os.path.splitext(fname)[0]
    vols = []
    if os.path.isdir(project_root):
        for d in sorted(os.listdir(project_root)):
            dp = os.path.join(project_root, d)
            if os.path.isdir(dp) and _re.match(r"^第.卷_", d):
                vols.append(d)
                # 已存在同名词章 → 直接沿用该卷
                if os.path.isfile(os.path.join(dp, fname)):
                    return "%s/%s" % (d, fname)
    if vols:
        return "%s/%s" % (vols[0], fname)
    return "第一卷_道生/%s" % fname


def stable_publish_task_id(task):
    """Return a request-scoped publish ID that does not depend on route shape."""
    request_id = (task or {}).get("conversation_request_id")
    chapter_ref = str((task or {}).get("chapter_ref") or "")
    match = re.search(r"(\d+)", chapter_ref)
    if request_id and match:
        return "%s-PUBLISH-CH%03d" % (
            request_id, int(match.group(1)))
    return None


def _grant_for_publish(root, publish_task_id, canonical_target):
    """为 chapter_publish 任务生成动态授权 grant（task_grant 因子实体）。

    仅在审查通过（Build 冻结、待发布）时由本函数生成，确保发布门禁未过则无 grant。
    """
    try:
        import auth_engine as AE
        AE.generate_grant(root, publish_task_id, "publish_service",
                          "chapter.publish", "canonical", [canonical_target])
    except Exception:
        pass


def _inputs_ready(root, t):
    """轻量输入就绪校验：若任务引用章节文件，该文件须存在（md/txt 均可）。"""
    chapter_ref = t.get("chapter_ref")
    if not chapter_ref:
        return True
    for cand in (chapter_ref, chapter_ref.replace(".md", ".txt"), chapter_ref + ".md"):
        if os.path.isfile(os.path.join(root, cand)):
            return True
    return False


def next_task(root, role, capabilities=None, types=None):
    """返回该 role 下一个可接取的 ready 任务（最高优先级），含 inputs_ready。

    用于 `platform task next --role writer`：AI 只读这一个目标任务，
    而不是扫描 tasks/backlog/ready/running/review 全池。
    """
    caps = set(capabilities or [])
    typs = set(types or [])
    d = _state_dir(root, "ready")
    if not os.path.isdir(d):
        return None
    prio_order = {"high": 0, "medium": 1, "low": 2}
    cands = []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".yaml"):
            continue
        tid = fn[:-5]
        _, td = load_task(root, tid)
        t = td.get("task", {})
        req_role = (t.get("agent") or {}).get("required_role")
        if req_role and req_role != role:
            continue
        if typs and t.get("type") not in typs:
            continue
        if caps and t.get("type") not in caps:
            continue
        cands.append({
            "task_id": tid,
            "type": t.get("type"),
            "priority": t.get("priority", "medium"),
            "title": t.get("title"),
            "chapter_ref": t.get("chapter_ref"),
            "inputs_ready": _inputs_ready(root, t),
        })
    if not cands:
        return None
    cands.sort(key=lambda c: prio_order.get(c["priority"], 1))
    return cands[0]


def list_tasks(root, state=None):
    out = {}
    states = [state] if state else STATES
    for s in states:
        d = _state_dir(root, s)
        if not os.path.isdir(d):
            continue
        ids = [f[:-5] for f in os.listdir(d) if f.endswith(".yaml")]
        if ids:
            out[s] = sorted(ids)
    return out


def show_task(root, task_id):
    st, data = load_task(root, task_id)
    if st is None:
        print("# 任务不存在: %s" % task_id)
        return
    print("状态: %s" % st)
    print(_gov.dump_block(data))


if __name__ == "__main__":
    print("task_engine 仅作库使用；CLI 见 task_cli.py")
