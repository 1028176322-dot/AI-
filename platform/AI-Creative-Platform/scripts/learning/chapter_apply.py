# -*- coding: utf-8 -*-
"""
Apply 候选修订到草稿（chapter-apply-revision，纲要 §2.4 / §2.9 / §3，实施任务 #23）。

职责
----
- 校验：APPLY_READY 状态、候选绑定哈希、fidelity 报告通过、quality 通过或 WAIVED。
- 保存 pre_apply 备份到 ``analysis/style/<ch>/<cyc>/draft-pre-apply.md``（供回滚）。
- 产出 apply-result 合规 dict（含 source_draft_sha256 / candidate_sha256 / pre_apply_ref）。
- **实际写 chapters/drafts/<ch>.md 由调用方经 Broker 的 ControlledWriter.request_write() 完成**。

本模块是候选身份校验 + 备份管理，不持有 Broker 密钥，不直接写受控目录。
"""
import hashlib
import json
import os
import time

from controlled_chapter_client import (
    broker_write, dependency_resources, resource)

SCHEMA_ID = "style.chapter-apply-result"
SCHEMA_VERSION = "1.0.0"


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_artifact(path):
    if path.lower().endswith(".json"):
        with open(path, "r", encoding="utf-8") as stream:
            return json.load(stream)
    import _gov
    return _gov.load_yaml(path) or {}


def prepare_apply(chapter_id, revision_cycle_id, producer_task_id,
                  draft_text, candidate_text, candidate_sha256,
                  protected_manifest_sha256="",
                  fidelity_report_sha256="", quality_report_sha256="",
                  source_draft_sha256=None, created_at=None):
    """产出 apply-result 合规 dict。

    参数
    ----
    draft_text : str
        当前草稿全文。
    candidate_text : str
        revision-candidate 全文。
    candidate_sha256 : str
        候选稿 SHA-256（调用方从修订结果读取）。
    source_draft_sha256 : str | None
        候选绑定的原草稿哈希。调用方传入以校验候选是否 STALE。
    fidelity_report_sha256 : str
        fidelity-review 报告哈希（表示已通过）。
    quality_report_sha256 : str
        quality-review 报告哈希（表示通过或 WAIVED）。

    返回
    ----
    dict 含 apply 元数据。actual_apply 标记=apply 准备就绪。
    """
    if source_draft_sha256 is not None:
        current_draft_sha = _sha256(draft_text)
        if current_draft_sha != source_draft_sha256:
            return {
                "schema": SCHEMA_ID, "schema_version": SCHEMA_VERSION,
                "chapter_id": chapter_id,
                "revision_cycle_id": revision_cycle_id,
                "producer_task_id": producer_task_id,
                "status": "STALE",
                "error": "draft changed since candidate was created",
                "source_draft_sha256": source_draft_sha256,
                "current_draft_sha256": current_draft_sha,
                "created_at": created_at if created_at is not None else time.time(),
            }

    pre_apply_sha = _sha256(draft_text)

    return {
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "chapter_id": chapter_id,
        "revision_cycle_id": revision_cycle_id,
        "producer_task_id": producer_task_id,
        "task_id": producer_task_id,
        "operation": "apply",
        "status": "APPLY_READY",
        "pre_apply_sha256": pre_apply_sha,
        "pre_apply_ref": "analysis/style/%s/%s/draft-pre-apply.md"
                         % (chapter_id, revision_cycle_id),
        "pre_apply_artifact_ref":
            "analysis/style/%s/%s/draft-pre-apply.md"
            % (chapter_id, revision_cycle_id),
        "candidate_sha256": candidate_sha256,
        "applied_draft_sha256": _sha256(candidate_text),
        "state_before": "APPLY_READY",
        "state_after": "APPLIED",
        "cas_verified": True,
        "source_draft_sha256": source_draft_sha256 or "",
        "protected_manifest_sha256": protected_manifest_sha256,
        "fidelity_report_sha256": fidelity_report_sha256,
        "quality_report_sha256": quality_report_sha256,
        "created_at": created_at if created_at is not None else time.time(),
    }


def validate_apply_result(d):
    errors = []
    required = ["chapter_id", "revision_cycle_id", "producer_task_id",
                "status", "pre_apply_sha256", "created_at"]
    for k in required:
        if k not in d:
            errors.append("missing field: %s" % k)
    return (len(errors) == 0, errors)


def persist_pre_apply(root, chapter_id, revision_cycle_id, draft_text):
    """保存预应用草稿备份到 analysis/style/<ch>/<cyc>/draft-pre-apply.md。

    不经过受控写（analysis/ 非受控根）。调用方负责在正式 apply 前调用。
    """
    out_dir = os.path.join(root, "analysis", "style", chapter_id, revision_cycle_id)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "draft-pre-apply.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(draft_text)
    return path


def read_pre_apply(root, chapter_id, revision_cycle_id):
    """读取 pre_apply 备份正文。"""
    path = os.path.join(root, "analysis", "style", chapter_id, revision_cycle_id,
                        "draft-pre-apply.md")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def execute_apply(
        project_root, task_id, chapter_id, revision_cycle_id,
        draft_path, candidate_path, source_draft_sha256,
        protected_manifest_path, style_guidance_path,
        fidelity_report_path, quality_report_path, actor_id=None):
    """Apply through Broker with all strict dependency resources bound."""
    with open(draft_path, "r", encoding="utf-8") as stream:
        draft_text = stream.read()
    with open(candidate_path, "r", encoding="utf-8") as stream:
        candidate_text = stream.read()
    candidate_sha = _sha256(candidate_text)
    fidelity = _load_artifact(fidelity_report_path)
    quality = _load_artifact(quality_report_path)
    manifest = _load_artifact(protected_manifest_path)
    guidance = _load_artifact(style_guidance_path)
    import manifest_build
    manifest_sha = manifest_build.manifest_sha256(manifest)
    if (
            fidelity.get("result") != "FIDELITY_PASSED"
            or fidelity.get("candidate_sha256") != candidate_sha
            or fidelity.get("source_draft_sha256")
            != source_draft_sha256
            or fidelity.get("protected_manifest_sha256") != manifest_sha):
        raise ValueError(
            "fidelity report is not passed or hash-bound to this candidate")
    if (
            quality.get("overall") != "QUALITY_PASSED"
            or quality.get("style_guidance_sha256")
            != guidance.get("style_guidance_sha256")):
        raise ValueError(
            "quality report is not passed or guidance-bound")
    prepared = prepare_apply(
        chapter_id, revision_cycle_id, task_id,
        draft_text, candidate_text, candidate_sha,
        protected_manifest_sha256=manifest_sha,
        fidelity_report_sha256=_sha256_file(fidelity_report_path),
        quality_report_sha256=_sha256_file(quality_report_path),
        source_draft_sha256=source_draft_sha256)
    if prepared.get("status") != "APPLY_READY":
        return prepared
    backup = persist_pre_apply(
        project_root, chapter_id, revision_cycle_id, draft_text)
    resources = [
        resource("source", draft_path, source_draft_sha256),
        resource("target", draft_path, source_draft_sha256),
        resource("candidate_or_backup", candidate_path, candidate_sha),
    ]
    resources.extend(dependency_resources({
        "protected_manifest": protected_manifest_path,
        "style_guidance": style_guidance_path,
        "fidelity_report": fidelity_report_path,
        "quality_report": quality_report_path,
    }))
    broker_result = broker_write(
        project_root, task_id, "apply", resources, candidate_text,
        actor_id=actor_id)
    prepared["broker_result"] = broker_result
    prepared["pre_apply_artifact_ref"] = os.path.relpath(
        backup, project_root).replace("\\", "/")
    prepared["applied_draft_sha256"] = _sha256(candidate_text)
    return prepared
