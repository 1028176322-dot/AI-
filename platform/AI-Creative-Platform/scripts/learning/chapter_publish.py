# -*- coding: utf-8 -*-
"""
发布章节到正式目录（chapter-publish，纲要 §2.4 / §2.9 / §3，实施任务 #23）。

职责
----
- 校验 PUBLISH_READY 状态 + FINAL_PASSED 报告的所有绑定：
  draft_sha256 / nkb_revision / nkb_snapshot_sha256 / outline_sha256 /
  protected_manifest_sha256 / style_guidance_sha256 / final_regression_config_version /
  final_regression_mode / chapter_review_report_sha256。
- 任一依赖变化 → STALE，拒绝发布。
- **实际写 chapters/approved/<ch>.md 由调用方经 Broker 完成**。
- 产出 publish-result 合规 dict。
"""
import hashlib
import json
import os
import time

from controlled_chapter_client import (
    broker_write, dependency_resources, resource)

SCHEMA_ID = "style.chapter-publish-result"
SCHEMA_VERSION = "1.0.0"


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_obj(obj):
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path):
    if path.lower().endswith(".json"):
        with open(path, "r", encoding="utf-8") as stream:
            return json.load(stream)
    import _gov
    return _gov.load_yaml(path) or {}


def prepare_publish(chapter_id, revision_cycle_id, producer_task_id,
                    draft_text, draft_sha256,
                    nkb_revision="", nkb_snapshot_sha256="",
                    outline_sha256="", protected_manifest_sha256="",
                    style_guidance_sha256="",
                    final_regression_config_version="1.0.0",
                    final_regression_mode="baseline",
                    chapter_review_report_sha256="",
                    created_at=None):
    """产出 publish-result 合规 dict（含所有 §2.9 绑定校验）。

    参数
    ----
    draft_text : str
        欲发布的草稿全文。
    draft_sha256 : str
        对应 FINAL_PASSED 报告的 draft_sha256。

    返回
    ----
    dict 含 status=PUBLISH_READY 或 STALE 错误信息。
    """
    current_draft_sha = _sha256(draft_text)

    stale = False
    stale_reasons = []

    if current_draft_sha != draft_sha256:
        stale = True
        stale_reasons.append("draft sha changed: %s != %s" % (current_draft_sha, draft_sha256))

    # 必填绑定字段：为空即判定为 STALE
    REQUIRED_BINDINGS = [
        ("nkb_revision", nkb_revision),
        ("nkb_snapshot_sha256", nkb_snapshot_sha256),
        ("outline_sha256", outline_sha256),
        ("protected_manifest_sha256", protected_manifest_sha256),
        ("style_guidance_sha256", style_guidance_sha256),
        ("final_regression_config_version",
         final_regression_config_version),
        ("chapter_review_report_sha256",
         chapter_review_report_sha256),
    ]
    for field, val in REQUIRED_BINDINGS:
        if not val:
            stale = True
            stale_reasons.append("%s is empty" % field)
    if final_regression_mode not in ("baseline", "post_apply"):
        stale = True
        stale_reasons.append(
            "invalid final_regression_mode: %s"
            % final_regression_mode)

    if stale:
        return {
            "schema": SCHEMA_ID, "schema_version": SCHEMA_VERSION,
            "chapter_id": chapter_id,
            "revision_cycle_id": revision_cycle_id,
            "producer_task_id": producer_task_id,
            "status": "STALE",
            "error": "; ".join(stale_reasons),
            "draft_sha256": current_draft_sha,
            "nkb_revision": nkb_revision,
            "nkb_snapshot_sha256": nkb_snapshot_sha256,
            "outline_sha256": outline_sha256,
            "protected_manifest_sha256": protected_manifest_sha256,
            "style_guidance_sha256": style_guidance_sha256,
            "final_regression_mode": final_regression_mode,
            "final_regression_config_version": final_regression_config_version,
            "chapter_review_report_sha256": chapter_review_report_sha256,
            "created_at": created_at if created_at is not None else time.time(),
        }

    return {
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "chapter_id": chapter_id,
        "revision_cycle_id": revision_cycle_id,
        "producer_task_id": producer_task_id,
        "status": "PUBLISH_READY",
        "draft_sha256": current_draft_sha,
        "nkb_revision": nkb_revision,
        "nkb_snapshot_sha256": nkb_snapshot_sha256,
        "outline_sha256": outline_sha256,
        "protected_manifest_sha256": protected_manifest_sha256,
        "style_guidance_sha256": style_guidance_sha256,
        "final_regression_mode": final_regression_mode,
        "final_regression_config_version": final_regression_config_version,
        "chapter_review_report_sha256": chapter_review_report_sha256,
        "created_at": created_at if created_at is not None else time.time(),
    }


def validate_publish_result(d):
    errors = []
    required = ["chapter_id", "revision_cycle_id", "producer_task_id",
                "status", "draft_sha256", "created_at"]
    for k in required:
        if k not in d:
            errors.append("missing field: %s" % k)
    if d.get("status") not in ("PUBLISH_READY", "STALE"):
        errors.append("invalid status: %s" % d.get("status"))
    return (len(errors) == 0, errors)


def execute_publish(
        project_root, task_id, chapter_id, revision_cycle_id,
        draft_path, approved_path, regression_result,
        protected_manifest_path, style_guidance_path,
        final_regression_path, nkb_sync_proof_path,
        outline_path, chapter_review_report_path, actor_id=None):
    """Publish through Broker; all release evidence participates in CAS."""
    with open(draft_path, "r", encoding="utf-8") as stream:
        draft_text = stream.read()
    if regression_result.get("result") != "FINAL_PASSED":
        return {
            "schema": SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "chapter_id": chapter_id,
            "revision_cycle_id": revision_cycle_id,
            "producer_task_id": task_id,
            "status": "STALE",
            "error": "FINAL_PASSED evidence is missing",
            "draft_sha256": _sha256(draft_text),
            "created_at": time.time(),
        }
    prepared = prepare_publish(
        chapter_id, revision_cycle_id, task_id, draft_text,
        regression_result.get("draft_sha256", ""),
        nkb_revision=regression_result.get("nkb_revision", ""),
        nkb_snapshot_sha256=regression_result.get(
            "nkb_snapshot_sha256", ""),
        outline_sha256=regression_result.get("outline_sha256", ""),
        protected_manifest_sha256=regression_result.get(
            "protected_manifest_sha256", ""),
        style_guidance_sha256=regression_result.get(
            "style_guidance_sha256", ""),
        final_regression_config_version=regression_result.get(
            "final_regression_config_version", ""),
        final_regression_mode=regression_result.get(
            "final_regression_mode", ""),
        chapter_review_report_sha256=regression_result.get(
            "chapter_review_report_sha256", ""))
    if prepared["status"] != "PUBLISH_READY":
        return prepared
    import manifest_build
    manifest = _load(protected_manifest_path)
    guidance = _load(style_guidance_path)
    sync_proof = _load(nkb_sync_proof_path)
    actual_bindings = {
        "protected_manifest_sha256":
            manifest_build.manifest_sha256(manifest),
        "style_guidance_sha256":
            guidance.get("style_guidance_sha256", ""),
        "outline_sha256": _sha256_file(outline_path),
        "chapter_review_report_sha256":
            _sha256_file(chapter_review_report_path),
    }
    stale = [
        "%s changed" % name
        for name, actual in actual_bindings.items()
        if regression_result.get(name) != actual]
    sync_status = (
        sync_proof.get("status")
        or sync_proof.get("result")
        or sync_proof.get("decision"))
    if sync_status not in (
            "NKB_SYNC_PASSED", "PASSED", "passed",
            "pass", "proceed"):
        stale.append("nkb_sync_proof is not passed")
    for name in ("nkb_revision", "nkb_snapshot_sha256"):
        if sync_proof.get(name) != regression_result.get(name):
            stale.append("nkb_sync_proof.%s changed" % name)
    if stale:
        prepared["status"] = "STALE"
        prepared["error"] = "; ".join(stale)
        prepared["actual_bindings"] = actual_bindings
        return prepared
    resources = [
        resource(
            "source", draft_path,
            regression_result.get("draft_sha256")),
        resource("target", approved_path),
    ]
    resources.extend(dependency_resources({
        "protected_manifest": protected_manifest_path,
        "style_guidance": style_guidance_path,
        "final_regression": final_regression_path,
        "nkb_sync_proof": nkb_sync_proof_path,
        "outline": outline_path,
        "chapter_review_report": chapter_review_report_path,
    }))
    prepared["broker_result"] = broker_write(
        project_root, task_id, "publish", resources, draft_text,
        actor_id=actor_id)
    return prepared
