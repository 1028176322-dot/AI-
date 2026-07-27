# -*- coding: utf-8 -*-
"""
风格规则审批晋升链（style-rule-promote，纲要 §2.10 / §8 第 10 步）。

生命周期
--------
EXTRACTED → REVIEW_PENDING → APPROVED → PROMOTION_ELIGIBLE → PROMOTED → ACTIVE
                                                    └ REJECTED (终态)
ACTIVE → SUSPENDED → ACTIVE（重激活）
ACTIVE → REVOKED（终态）

晋升门禁
--------
- `promote(approval_credential)`：
  ① 校验 ``payload_sha256`` 与 credential 一致。
  ② 校验 ``event_log_entry_hash``：重放事件日志确认该审批事件存在且哈希链完整。
  ③ 审批人 role 必须是 reviewer 或 author（不可自批）。
  ④ 仅 APPROVED 态可升 PROMOTION_ELIGIBLE；PROMOTION_ELIGIBLE 升 PROMOTED 须经授权。
- `activate()`：PROMOTED → ACTIVE（写入 style card 或 runtime guidance）。
- `suspend()` / `revoke()`：ACTIVE 可控停用。
"""
import hashlib
import json
import os
import time

SCHEMA_ID = "style.rule-lifecycle"
SCHEMA_VERSION = "1.0.0"

VALID_TRANSITIONS = {
    "APPROVED": ["PROMOTION_ELIGIBLE"],
    "PROMOTION_ELIGIBLE": ["PROMOTED"],
    "PROMOTED": ["ACTIVE"],
    "ACTIVE": ["SUSPENDED", "REVOKED"],
    "SUSPENDED": ["ACTIVE"],
}


class PromotionError(Exception):
    pass


def _sha256_obj(obj):
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# 审批凭证校验
# --------------------------------------------------------------------------
def validate_approval_credential(credential, event_log=None):
    """校验审批凭证完整性。

    credential 结构（§2.10）：
      candidate_id / candidate_sha256 / source_set_hash /
      reviewer_id / reviewer_role / review_task_id / session_id /
      decision / approved_rule_ids / reason / approved_at /
      payload_sha256 / event_log_ref / event_log_entry_hash

    返回 (ok, errors)
    """
    errors = []
    required = ["candidate_id", "reviewer_id", "reviewer_role",
                "review_task_id", "decision", "payload_sha256",
                "event_log_ref", "event_log_entry_hash"]
    for k in required:
        if k not in credential:
            errors.append("missing: %s" % k)

    if credential.get("reviewer_role") not in ("reviewer", "author"):
        errors.append("reviewer_role must be reviewer or author")

    if credential.get("decision") not in ("approved", "rejected"):
        errors.append("decision must be approved or rejected")

    # payload_sha256 自校验
    payload = {k: v for k, v in credential.items()
               if k not in ("payload_sha256", "event_log_ref", "event_log_entry_hash")}
    if credential.get("payload_sha256") and credential["payload_sha256"] != _sha256_obj(payload):
        errors.append("payload_sha256 mismatch")

    # 事件日志校验
    if event_log is not None and credential.get("event_log_entry_hash"):
        events = event_log.read_events()
        found = any(e.get("event_id") == credential.get("event_log_entry_hash")
                    or event_hash(e) == credential.get("event_log_entry_hash")
                    for e in events)
        if not found:
            errors.append("event_log_entry not found in event log")

    return (len(errors) == 0, errors)


def event_hash(event):
    return hashlib.sha256(
        json.dumps(event, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# 晋升状态管理
# --------------------------------------------------------------------------
class RuleLifecycle:
    def __init__(self, store_dir):
        self.store_dir = store_dir

    def _path(self, candidate_id):
        safe = "".join(c if (c.isalnum() or c in "._-") else "_" for c in candidate_id)
        return os.path.join(self.store_dir, "%s.lifecycle.json" % safe)

    def get_state(self, candidate_id):
        p = self._path(candidate_id)
        if not os.path.exists(p):
            return None
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f).get("current_state")

    def _set_state(self, candidate_id, state, metadata=None):
        p = self._path(candidate_id)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        data = {"candidate_id": candidate_id, "current_state": state,
                "updated_at": time.time()}
        if metadata:
            data.update(metadata)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)

    def transition(self, candidate_id, expected, next_state, metadata=None):
        current = self.get_state(candidate_id) or "EXTRACTED"
        if current != expected:
            return {"ok": False, "error": "state mismatch: %s expected %s" % (current, expected)}
        allowed = VALID_TRANSITIONS.get(expected, [])
        if next_state not in allowed:
            return {"ok": False, "error": "no transition %s->%s" % (expected, next_state)}
        self._set_state(candidate_id, next_state, metadata=metadata)
        return {"ok": True, "from": expected, "to": next_state}


# --------------------------------------------------------------------------
# 晋升（含审批凭证校验）
# --------------------------------------------------------------------------
def promote(candidate_id, approval_credential, lifecycle, event_log=None):
    """验证审批凭证后推进 APPROVED → PROMOTION_ELIGIBLE。

    返回 dict {ok, state, errors}
    """
    ok, errs = validate_approval_credential(approval_credential, event_log=event_log)
    if not ok:
        return {"ok": False, "state": "VALIDATION_FAILED", "errors": errs}

    if approval_credential.get("decision") == "rejected":
        lifecycle._set_state(candidate_id, "REJECTED",
                             metadata={"reason": approval_credential.get("reason")})
        return {"ok": True, "state": "REJECTED"}

    result = lifecycle.transition(candidate_id, "APPROVED", "PROMOTION_ELIGIBLE")
    if not result["ok"]:
        return {"ok": False, "state": lifecycle.get_state(candidate_id), "errors": [result["error"]]}

    # 同时记录 pivotal 审批元数据
    lifecycle._set_state(candidate_id, "PROMOTION_ELIGIBLE",
                         metadata={"approval": {
                             "reviewer": approval_credential.get("reviewer_id"),
                             "review_task": approval_credential.get("review_task_id"),
                             "approved_at": approval_credential.get("approved_at"),
                         }})
    return {"ok": True, "state": "PROMOTION_ELIGIBLE"}


def follow_promote(candidate_id, lifecycle):
    """推进 PROMOTION_ELIGIBLE → PROMOTED（授权步骤，纲要内默认晋升）。"""
    r = lifecycle.transition(candidate_id, "PROMOTION_ELIGIBLE", "PROMOTED")
    if not r["ok"]:
        return {"ok": False, "error": r["error"]}
    return {"ok": True, "state": "PROMOTED"}


def activate(candidate_id, lifecycle, rule_data=None, style_card_path=None):
    """推进 PROMOTED → ACTIVE，可选写入 style card。"""
    r = lifecycle.transition(candidate_id, "PROMOTED", "ACTIVE")
    if not r["ok"]:
        return {"ok": False, "error": r["error"]}

    # 可选写入 style card
    if rule_data and style_card_path:
        os.makedirs(os.path.dirname(style_card_path), exist_ok=True)
        existing = []
        if os.path.exists(style_card_path):
            with open(style_card_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        existing.append({**rule_data, "activated_at": time.time(), "status": "ACTIVE"})
        tmp = style_card_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, style_card_path)

    return {"ok": True, "state": "ACTIVE"}


def suspend(candidate_id, lifecycle, reason=""):
    r = lifecycle.transition(candidate_id, "ACTIVE", "SUSPENDED",
                              metadata={"suspend_reason": reason})
    return r


def revoke(candidate_id, lifecycle, reason=""):
    r = lifecycle.transition(candidate_id, "ACTIVE", "REVOKED",
                              metadata={"revoke_reason": reason})
    return r


# --------------------------------------------------------------------------
# 合规校验
# --------------------------------------------------------------------------
def validate_promotion_result(d):
    errors = []
    if not isinstance(d.get("ok"), bool):
        errors.append("missing ok field")
    return (len(errors) == 0, errors)
