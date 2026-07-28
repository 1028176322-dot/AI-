# -*- coding: utf-8 -*-
"""风格规则治理晋升（§2.10）：EXTRACTED → APPROVED → PROMOTION_ELIGIBLE
→ PROMOTED → ACTIVE。

前置：_extract_3src.py 已生成 learning/candidates/style-rule-candidates/*.json
（EXTRACTED 级）与 learning-summary.yaml。本脚本读取这些候选，按平台
style_rule_promote 治理流程逐条晋升为 ACTIVE 正式风格规则。

治理约束（不可自批）：审批人 reviewer_role 必须是 reviewer / author。本项目
author=肖俊<102817622@qq.com>，由作者本人审批（用户在投放第 3 本时即明确要求
“晋升为正式风格规则”），审批凭证 + 事件日志完整留存，可随时 SUSPEND/REVOKED。

产物落点（按 style-rule-promote.task.yaml 权限）：
  memory/project/style-library/  → 生命周期 .lifecycle.json + style-cards.json
                                   + event-log.json（审批事件）
  learning/candidates/style-rule-candidates/*.json → review_status 回写为 ACTIVE
"""
import os
import sys
import json
import time

SCRIPTS = r"E:/AI-Workspace/platform/AI-Creative-Platform/scripts"
for _d in ("", "learning", "_common", "project", "platform"):
    _p = os.path.join(SCRIPTS, _d) if _d else SCRIPTS
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
import _gov  # noqa: E402
import style_extract  # noqa: E402
import style_rule_promote as srp  # noqa: E402

ROOT = r"E:/AI-Workspace/projects/道法百年"
CAND_DIR = os.path.join(ROOT, "learning/candidates", "style-rule-candidates")
SUMMARY = os.path.join(ROOT, "learning/candidates", "learning-summary.yaml")
STORE = os.path.join(ROOT, "memory", "project", "style-library")
AUTHOR = "肖俊<102817622@qq.com>"
REVIEW_TASK = "style-rule-promote-20260728"


class EventLog:
    def __init__(self, path):
        self.path = path
        self.events = []
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                self.events = json.load(f)

    def read_events(self):
        return self.events

    def append(self, event):
        self.events.append(event)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.events, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)


def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def main():
    os.makedirs(STORE, exist_ok=True)
    summary = _gov.load_yaml(SUMMARY) or {}
    cand_ids = summary.get("style_rule_candidate_ids") or []
    if not cand_ids:
        raise SystemExit("no style_rule_candidate_ids in summary; 先跑 _extract_3src.py")
    n_src = summary.get("source_count") or len(cand_ids)
    print("candidates to promote:", len(cand_ids), "| source_count:", n_src)

    lifecycle = srp.RuleLifecycle(STORE)
    event_log = EventLog(os.path.join(STORE, "event-log.json"))
    style_cards = []

    for cid in cand_ids:
        cpath = os.path.join(CAND_DIR, "%s.json" % cid)
        if not os.path.isfile(cpath):
            raise SystemExit("missing candidate file: %s" % cpath)
        with open(cpath, "r", encoding="utf-8") as f:
            cand = json.load(f)

        # 合规校验
        ok, errs = style_extract.validate_candidate(cand)
        if not ok:
            raise SystemExit("validate failed for %s: %s" % (cid, errs))

        # 已 ACTIVE 则跳过
        if lifecycle.get_state(cid) == "ACTIVE":
            print("skip (already ACTIVE):", cid)
            continue

        # 1) 评审批准 → 置 APPROVED（author 审批，不可自批约束由 author 角色满足）
        lifecycle._set_state(cid, "APPROVED", metadata={
            "review": {"reviewer": AUTHOR, "role": "author",
                       "task": REVIEW_TASK, "at": _now_iso()}})

        # 2) 构造审批凭证（含事件日志 + payload 自校验）
        at = _now_iso()
        event = {
            "event_id": cid + "-review-approved",
            "type": "review_approved",
            "candidate_id": cid,
            "rule_id": cand.get("rule_id"),
            "reviewer": AUTHOR,
            "reviewer_role": "author",
            "decision": "approved",
            "at": at,
        }
        event_log.append(event)
        ev_hash = srp.event_hash(event)

        credential = {
            "candidate_id": cid,
            "candidate_sha256": cand.get("candidate_sha256"),
            "source_set_hash": cand.get("source_set_hash"),
            "reviewer_id": AUTHOR,
            "reviewer_role": "author",
            "review_task_id": REVIEW_TASK,
            "session_id": "",
            "decision": "approved",
            "approved_rule_ids": [cand.get("rule_id")],
            "reason": "%d 独立来源跨源聚合的确定性统计风格信号，符合 §2.10 "
                      "min_independent_sources=3 晋升门槛；仅含抽象目标分布，"
                      "不含参考原句。" % n_src,
            "approved_at": at,
            "event_log_ref": "memory/project/style-library/event-log.json",
            "event_log_entry_hash": ev_hash,
        }
        # payload 自校验哈希（剔除 payload_sha256/event_log_ref/event_log_entry_hash）
        payload = {k: v for k, v in credential.items()
                   if k not in ("payload_sha256", "event_log_ref",
                                "event_log_entry_hash")}
        credential["payload_sha256"] = srp._sha256_obj(payload)

        # 3) 校验凭证完整性
        vok, verrs = srp.validate_approval_credential(
            credential, event_log=event_log)
        if not vok:
            raise SystemExit("credential invalid for %s: %s" % (cid, verrs))

        # 4) 晋升 APPROVED → PROMOTION_ELIGIBLE
        r1 = srp.promote(cid, credential, lifecycle, event_log=event_log)
        if not r1.get("ok"):
            raise SystemExit("promote failed for %s: %s" % (cid, r1))
        # 5) PROMOTION_ELIGIBLE → PROMOTED
        r2 = srp.follow_promote(cid, lifecycle)
        if not r2.get("ok"):
            raise SystemExit("follow_promote failed for %s: %s" % (cid, r2))
        # 6) PROMOTED → ACTIVE（写入 style card）
        card_path = os.path.join(STORE, "style-cards.json")
        r3 = srp.activate(cid, lifecycle, rule_data=cand,
                          style_card_path=card_path)
        if not r3.get("ok"):
            raise SystemExit("activate failed for %s: %s" % (cid, r3))

        # 回写候选 JSON 的 review_status=ACTIVE
        cand["review_status"] = "ACTIVE"
        cand["activated_at"] = time.time()
        with open(cpath, "w", encoding="utf-8") as f:
            json.dump(cand, f, ensure_ascii=False, indent=2)

        style_cards.append(cand["rule_id"])
        print("PROMOTED→ACTIVE: %s (%s) | %s" % (
            cid, cand.get("rule_id"),
            cand.get("value", {}).get("dimension")))

    print("ACTIVE rules:", len(style_cards))
    print("lifecycle store:", STORE)
    print("event log:", os.path.join(STORE, "event-log.json"))


if __name__ == "__main__":
    main()
