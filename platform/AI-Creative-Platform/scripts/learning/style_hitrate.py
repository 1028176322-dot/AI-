# -*- coding: utf-8 -*-
"""
防模板味命中率系统（style-hitrate，纲要 §2.6 / §8 第 10 步）。

设计要点
--------
- **仅对 style_preferences 计命中率**：governance_constraints（硬治理）与 functional_preserve
  （保真基线）**永不被命中率抑制**。
- **追加式事件日志**（append-only event log）：`record_hit(rule_id, scope, result)` 追加一条
  HIT 事件；`aggregate(rule_id)` 从事件日志聚合命中率（分母=符合使用条件的机会数，非全章字数）。
- **命中率抑制回调**：当 style_preference 命中率 > 阈值时，可回调标记该规则为 `SUPPRESSED`，
  实际写作时降低其权重。非硬规则可因命中率过高停执行，但治理硬规则不受影响。
- **多场景统计**：通过 scope.scene_types 按场景统计。
"""
import json
import os
import time

try:
    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "logs"))
    from event_log import EventLog, KeyProvider
except Exception:  # pragma: no cover
    pass


DEFAULT_HIT_LOG = "runtime/learning/style-hitrate.log"
DEFAULT_SUPPRESSION_THRESHOLD = 0.85  # 超过 85% 命中率可抑制


class HitrateError(Exception):
    pass


# --------------------------------------------------------------------------
# 命中率日志（追加式，兼容 style_revise 可用事件日志，也可独立文件）
# --------------------------------------------------------------------------
class HitrateLog:
    def __init__(self, path=None, event_log=None):
        self.path = path or DEFAULT_HIT_LOG
        self.event_log = event_log  # 可选：接入不可变事件日志（仅 Broker 持密钥可写）

    def record_hit(self, rule_id, scene_type="", usage_count=1,
                   hit_count=1, chapter_id="", task_id=""):
        """追加一条命中记录。

        参数
        ----
        rule_id : str  风格规则 ID
        scene_type : str  场景类型（battle/dialogue 等），空=全场景
        usage_count : int  本次机会数（语句/段落数）
        hit_count : int  本次命中次数
        """
        entry = {
            "rule_id": rule_id,
            "scene_type": scene_type,
            "usage_count": usage_count,
            "hit_count": hit_count,
            "chapter_id": chapter_id,
            "task_id": task_id,
            "timestamp": time.time(),
        }
        if self.event_log is not None:
            # 经不可变事件日志追加（需 Broker 密钥）
            self.event_log.append("STYLE_HITRATE", task_id or "system", task_id or "hitrate",
                                  operation="style_hitrate",
                                  resource_refs=[rule_id],
                                  details=entry)
        else:
            # 独立追加式日志（非不可变，但同样 append-only，防多章并发覆盖）
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _load_entries(self):
        if not os.path.exists(self.path):
            return []
        out = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return out

    def aggregate(self, rule_id=None, scene_type=None, hard_rule_ids=None):
        """从追加日志聚合命中率。

        返回 {rule_id: {"opportunities": N, "hits": M, "hitrate": float}}
        过滤：hard_rule_ids（硬治理规则）不出现在结果中（永不抑制）。
        """
        hard = set(hard_rule_ids or [])
        entries = self._load_entries()
        stats = {}
        for e in entries:
            rid = e.get("rule_id")
            if not rid or rid in hard:
                continue
            if rule_id and rid != rule_id:
                continue
            st = e.get("scene_type", "")
            if scene_type and st != scene_type:
                continue
            if rid not in stats:
                stats[rid] = {"opportunities": 0, "hits": 0,
                              "scene_type": st}
            stats[rid]["opportunities"] += e.get("usage_count", 1)
            stats[rid]["hits"] += e.get("hit_count", 0)

        for rid, s in stats.items():
            s["hitrate"] = (s["hits"] / s["opportunities"]
                            if s["opportunities"] > 0 else 0.0)
            s["suppressed"] = s["hitrate"] >= DEFAULT_SUPPRESSION_THRESHOLD
        return stats

    def suppressed_rules(self, hard_rule_ids=None):
        """返回命中率过高应抑制的规则 ID 列表（仅 style_preferences）。"""
        stats = self.aggregate(hard_rule_ids=hard_rule_ids)
        return [rid for rid, s in stats.items() if s.get("suppressed")]


# --------------------------------------------------------------------------
# 命中率回调（集成到 writing_strategy / style_revise 的基础设施）
# --------------------------------------------------------------------------
def should_suppress(hitrate, suppression_threshold=None):
    th = suppression_threshold if suppression_threshold is not None else DEFAULT_SUPPRESSION_THRESHOLD
    return hitrate >= th


def calibrate_suppressed_weights(stats, weights_map):
    """受抑制的 style_preference 权重减半。返回 {rule_id: weight}。"""
    out = dict(weights_map)
    for rid in stats:
        if stats[rid].get("suppressed"):
            if rid in out:
                out[rid] = out[rid] * 0.5
    return out
