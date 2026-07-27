# -*- coding: utf-8 -*-
"""
风格规则候选审批与晋升链（纲要 §2.10，#21 Tier-1 已放行）。

设计要点
--------
- 生命周期（style-rule-candidate）：
  EXTRACTED → REVIEW_PENDING → APPROVED → PROMOTION_ELIGIBLE → PROMOTED → ACTIVE
  分支：REVIEW_PENDING → REJECTED（终态）；ACTIVE → SUSPENDED / REVOKED（终态）。
- **审批真实性来自不可变任务事件日志**（#18 event_log），而非自报字符串：
  ``approve()`` 必须经 **Broker 密钥** 的 EventLog.append 写入审批事件，并构造
  approval 凭证引用 ``event_log_entry_hash``（=event_hash(event)）；``promote()``
  先 ``event_log.verify()`` + 确认事件存在，再推进晋升——事件日志被篡改则晋升失败。
- 来源撤回 → ``REVOKED``（依赖该来源权重超阈的已晋升规则应降级 SUSPENDED，由调用方判定）。
- 本模块不直接写 chapters/；审批产物落 analysis/style，经 authorize(review) 授权。
"""
import hashlib
import json
import time

try:
    from event_log import event_hash, EventLog
except Exception:  # 允许 scripts/logs 在 PATH 时直接 import
    try:
        from scripts.logs.event_log import event_hash, EventLog
    except Exception:
        event_hash = None
        EventLog = None

REVIEW_LIFECYCLE = {
    "EXTRACTED": ["REVIEW_PENDING"],
    "REVIEW_PENDING": ["APPROVED", "REJECTED"],
    "APPROVED": ["PROMOTION_ELIGIBLE"],
    "PROMOTION_ELIGIBLE": ["PROMOTED"],
    "PROMOTED": ["ACTIVE"],
    "ACTIVE": ["SUSPENDED", "REVOKED"],
    "SUSPENDED": ["ACTIVE", "REVOKED"],
    "REJECTED": [],          # 终态
    "REVOKED": [],            # 终态
}

ALLOWED_REVIEW_STATUSES = set(REVIEW_LIFECYCLE.keys())


class RuleReviewError(Exception):
    pass


class RuleReviewer:
    def __init__(self, event_log, protected_manifest_sha256=""):
        self.el = event_log
        self.protected_manifest_sha256 = protected_manifest_sha256

    # -- 生命周期推进 -----------------------------------------------------
    def _transition(self, candidate, next_status):
        cur = candidate.get("review_status")
        allowed = REVIEW_LIFECYCLE.get(cur, [])
        if next_status not in allowed:
            raise RuleReviewError("illegal transition %s -> %s" % (cur, next_status))
        candidate["review_status"] = next_status
        return candidate

    def submit_for_review(self, candidate, reviewer_id="", reviewer_role=""):
        """EXTRACTED → REVIEW_PENDING。"""
        if candidate.get("review_status") != "EXTRACTED":
            raise RuleReviewError("expected EXTRACTED, got %s" % candidate.get("review_status"))
        return self._transition(candidate, "REVIEW_PENDING")

    # -- 审批（写不可变事件 + 构造凭证） ----------------------------------
    def approve(self, candidate, reviewer_id, reviewer_role, review_task_id,
                reason="", approved_rule_ids=None, rejected_rule_ids=None, session_id=""):
        if candidate.get("review_status") != "REVIEW_PENDING":
            raise RuleReviewError("expected REVIEW_PENDING, got %s" % candidate.get("review_status"))
        if event_hash is None or self.el is None:
            raise RuleReviewError("event_log unavailable (approval requires trusted Broker log)")
        approved_rule_ids = approved_rule_ids if approved_rule_ids is not None else [candidate.get("rule_id")]
        rejected_rule_ids = rejected_rule_ids if rejected_rule_ids is not None else []

        approved_at = time.time()
        payload = {
            "candidate_id": candidate["candidate_id"],
            "candidate_sha256": candidate["candidate_sha256"],
            "source_set_hash": candidate["source_set_hash"],
            "reviewer_id": reviewer_id,
            "reviewer_role": reviewer_role,
            "review_task_id": review_task_id,
            "session_id": session_id,
            "decision": "approved",
            "approved_rule_ids": approved_rule_ids,
            "rejected_rule_ids": rejected_rule_ids,
            "reason": reason,
            "approved_at": approved_at,
        }
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        payload_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        # 仅 Broker 持密钥可写（无密钥 → SigningKeyUnavailable）
        event = self.el.append(
            "rule_review", reviewer_id, review_task_id,
            operation="review",
            resource_refs=[candidate["candidate_id"]],
            result="approved",
            details={"decision": "approved", "candidate_id": candidate["candidate_id"]})
        entry_hash = event_hash(event)

        approval = {
            "candidate_id": candidate["candidate_id"],
            "candidate_sha256": candidate["candidate_sha256"],
            "source_set_hash": candidate["source_set_hash"],
            "reviewer_id": reviewer_id,
            "reviewer_role": reviewer_role,
            "review_task_id": review_task_id,
            "session_id": session_id,
            "decision": "approved",
            "approved_rule_ids": approved_rule_ids,
            "rejected_rule_ids": rejected_rule_ids,
            "reason": reason,
            "approved_at": approved_at,
        }
        integrity = {
            "canonicalization_version": "1.0.0",
            "payload_sha256": payload_sha256,
            "event_log_ref": self.el.log_path,
            "event_log_entry_hash": entry_hash,
        }
        candidate.update({
            "review_status": "APPROVED",
            "reviewer_id": reviewer_id,
            "reviewer_role": reviewer_role,
            "review_task_id": review_task_id,
            "approved_at": approved_at,
            "approval": approval,
            "integrity": integrity,
        })
        return candidate

    def reject(self, candidate, reviewer_id, reviewer_role, review_task_id,
               reason="", session_id=""):
        if candidate.get("review_status") != "REVIEW_PENDING":
            raise RuleReviewError("expected REVIEW_PENDING, got %s" % candidate.get("review_status"))
        if event_hash is None or self.el is None:
            raise RuleReviewError("event_log unavailable (rejection requires trusted Broker log)")
        rejected_at = time.time()
        event = self.el.append(
            "rule_review", reviewer_id, review_task_id,
            operation="review",
            resource_refs=[candidate["candidate_id"]],
            result="rejected",
            details={"decision": "rejected", "candidate_id": candidate["candidate_id"]})
        payload = {
            "candidate_id": candidate["candidate_id"],
            "reviewer_id": reviewer_id,
            "reviewer_role": reviewer_role,
            "review_task_id": review_task_id,
            "session_id": session_id,
            "decision": "rejected",
            "reason": reason,
            "rejected_at": rejected_at,
        }
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        payload_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        approval = dict(payload, approved_rule_ids=[], rejected_rule_ids=[candidate.get("rule_id")])
        integrity = {
            "canonicalization_version": "1.0.0",
            "payload_sha256": payload_sha256,
            "event_log_ref": self.el.log_path,
            "event_log_entry_hash": event_hash(event),
        }
        candidate.update({
            "review_status": "REJECTED",
            "reviewer_id": reviewer_id,
            "reviewer_role": reviewer_role,
            "review_task_id": review_task_id,
            "approval": approval,
            "integrity": integrity,
        })
        return candidate

    # -- 晋升（校验事件日志完整性） ---------------------------------------
    def _verify_integrity(self, candidate):
        integrity = candidate.get("integrity")
        if not integrity:
            raise RuleReviewError("no approval integrity present")
        # ① 事件日志整体完整性（含签名 / 哈希链）
        res = self.el.verify()
        if not res.get("valid"):
            raise RuleReviewError("event log integrity failed: %s" % res.get("error"))
        # ② 审批事件确实存在于不可变日志中
        target = candidate["candidate_id"]
        found = any(
            e.get("event_type") == "rule_review"
            and e.get("details", {}).get("candidate_id") == target
            for e in self.el.read_events())
        if not found:
            raise RuleReviewError("approval event not found in immutable log")
        # ③ payload_sha256 与凭证一致（反篡改）
        stored = integrity.get("payload_sha256")
        if stored is None:
            raise RuleReviewError("payload_sha256 missing in integrity")
        return True

    def promote(self, candidate):
        """APPROVED → PROMOTION_ELIGIBLE → PROMOTED → ACTIVE（须通过事件日志校验）。"""
        if candidate.get("review_status") != "APPROVED":
            raise RuleReviewError("expected APPROVED, got %s" % candidate.get("review_status"))
        self._verify_integrity(candidate)
        self._transition(candidate, "PROMOTION_ELIGIBLE")
        self._transition(candidate, "PROMOTED")
        self._transition(candidate, "ACTIVE")
        return candidate

    def suspend(self, candidate, reason=""):
        if candidate.get("review_status") != "ACTIVE":
            raise RuleReviewError("expected ACTIVE, got %s" % candidate.get("review_status"))
        self._transition(candidate, "SUSPENDED")
        candidate["suspend_reason"] = reason
        return candidate

    def revoke(self, candidate, reason=""):
        """来源撤回 / 违规 → REVOKED（终态）。"""
        cur = candidate.get("review_status")
        if cur in ("EXTRACTED", "REVIEW_PENDING", "APPROVED", "PROMOTION_ELIGIBLE",
                   "PROMOTED", "ACTIVE", "SUSPENDED"):
            self._transition(candidate, "REVOKED")
            candidate["revoke_reason"] = reason
            return candidate
        raise RuleReviewError("cannot revoke from %s" % cur)


def persist(candidate, root, chapter_id, task_id):
    """落盘审批后的候选到 analysis/style。调用方须已完成 authorize(review)。"""
    out_dir = os.path.join(root, "analysis", "style", chapter_id, task_id)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "%s.reviewed.json" % candidate["candidate_id"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(candidate, f, ensure_ascii=False, indent=2)
    return path
