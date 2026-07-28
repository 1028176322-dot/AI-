# -*- coding: utf-8 -*-
"""
回滚候选修订（chapter-rollback-revision，纲要 §2.4 / §2.9 / §3，实施任务 #23）。

职责
----
- 检测 ROLLBACK_READY 状态后回滚到 pre_apply 版本。
- CAS 检测：当前草稿哈希 == applied_draft_sha256 → ROLLED_BACK；
  当前草稿哈希 ≠ applied_draft_sha256（apply 后又被改动）→ ROLLBACK_CONFLICT → BLOCKED。
- **实际写 chapters/drafts/<ch>.md 由调用方经 Broker 完成**。
- 产出 rollback-result 合规 dict（含 pre_apply_ref / pre_apply_sha256 / applied_draft_sha256）。
"""
import hashlib
import json
import os
import time

from controlled_chapter_client import (
    broker_write, dependency_resources, resource)

SCHEMA_ID = "style.chapter-rollback-result"
SCHEMA_VERSION = "1.0.0"


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prepare_rollback(chapter_id, revision_cycle_id, producer_task_id,
                     pre_apply_text, applied_draft_sha256,
                     current_draft_text, created_at=None):
    """产出 rollback-result 合规 dict。

    参数
    ----
    pre_apply_text : str
        pre_apply 备份正文（从 draft-pre-apply.md 读取）。
    applied_draft_sha256 : str
        apply 后的草稿哈希（从 apply-result 记录）。
    current_draft_text : str
        当前（欲回滚）草稿正文。

    返回
    ----
    dict 含 result=ROLLED_BACK|ROLLBACK_CONFLICT。
    """
    current_sha = _sha256(current_draft_text)
    pre_apply_sha = _sha256(pre_apply_text)

    # CAS 检测：当前哈希是否 == applied 时的哈希
    if current_sha != applied_draft_sha256:
        return {
            "schema": SCHEMA_ID, "schema_version": SCHEMA_VERSION,
            "chapter_id": chapter_id,
            "revision_cycle_id": revision_cycle_id,
            "producer_task_id": producer_task_id,
            "task_id": producer_task_id,
            "operation": "rollback",
            "result": "ROLLBACK_CONFLICT",
            "error": "draft changed since apply; current %s != applied %s"
                     % (current_sha, applied_draft_sha256),
            "pre_apply_sha256": pre_apply_sha,
            "applied_draft_sha256": applied_draft_sha256,
            "current_draft_sha256": current_sha,
            "created_at": created_at if created_at is not None else time.time(),
            "rollback_task_id": producer_task_id,
            "pre_apply_artifact_ref":
                "analysis/style/%s/%s/draft-pre-apply.md" %
                (chapter_id, revision_cycle_id),
            "state_before": "ROLLBACK_READY",
            "state_after": "ROLLBACK_CONFLICT",
            "conflict_detected": True,
        }

    return {
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "chapter_id": chapter_id,
        "revision_cycle_id": revision_cycle_id,
        "producer_task_id": producer_task_id,
        "task_id": producer_task_id,
        "operation": "rollback",
        "result": "ROLLED_BACK",
        "pre_apply_sha256": pre_apply_sha,
        "pre_apply_ref": "analysis/style/%s/%s/draft-pre-apply.md"
                         % (chapter_id, revision_cycle_id),
        "applied_draft_sha256": applied_draft_sha256,
        "current_draft_sha256": current_sha,
        "created_at": created_at if created_at is not None else time.time(),
        "rollback_task_id": producer_task_id,
        "pre_apply_artifact_ref":
            "analysis/style/%s/%s/draft-pre-apply.md" %
            (chapter_id, revision_cycle_id),
        "state_before": "ROLLBACK_READY",
        "state_after": "ROLLED_BACK",
        "conflict_detected": False,
    }


def validate_rollback_result(d):
    errors = []
    required = ["chapter_id", "revision_cycle_id", "producer_task_id",
                "result", "pre_apply_sha256", "applied_draft_sha256",
                "current_draft_sha256", "created_at"]
    for k in required:
        if k not in d:
            errors.append("missing field: %s" % k)
    if d.get("result") not in ("ROLLED_BACK", "ROLLBACK_CONFLICT"):
        errors.append("invalid result: %s" % d.get("result"))
    return (len(errors) == 0, errors)


def calculate_backup_path(root, chapter_id, revision_cycle_id):
    """pre_apply 备份路径（由 chapter_apply 写入）。"""
    return os.path.join(root, "analysis", "style", chapter_id, revision_cycle_id,
                        "draft-pre-apply.md")


def execute_rollback(
        project_root, task_id, chapter_id, revision_cycle_id,
        draft_path, backup_path, applied_draft_sha256,
        final_regression_path, actor_id=None):
    with open(draft_path, "r", encoding="utf-8") as stream:
        current = stream.read()
    with open(backup_path, "r", encoding="utf-8") as stream:
        backup = stream.read()
    result = prepare_rollback(
        chapter_id, revision_cycle_id, task_id, backup,
        applied_draft_sha256, current)
    if result["result"] != "ROLLED_BACK":
        return result
    resources = [
        resource("source", backup_path, _sha256(backup)),
        resource("target", draft_path, applied_draft_sha256),
    ]
    resources.extend(dependency_resources({
        "final_regression": final_regression_path,
    }))
    result["broker_result"] = broker_write(
        project_root, task_id, "rollback", resources, backup,
        actor_id=actor_id)
    return result
