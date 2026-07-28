# -*- coding: utf-8 -*-
"""Read-only final regression for baseline and post-apply paths.

Strict mode validates bound evidence produced by specialist review stages. It
does not substitute sentence-length or keyword heuristics for literary
judgment.
"""
import hashlib
import json
import os
import re
import time

SCHEMA_ID = "style.final-regression-result"
SCHEMA_VERSION = "2.0.0"
CONFIG_VERSION = "strict-v2.0.0"

_SENTENCE_SPLIT = re.compile(r"(?<=[。！？；.!?;])")
_NUMBER = re.compile(r"\d{2,}|[零〇一二两三四五六七八九十百千]+年?")


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sentences(text):
    return [
        item.strip() for item in _SENTENCE_SPLIT.split(text)
        if item.strip()]


def _add_check(checks, failures, name, passed, detail, **extra):
    row = {"check": name, "passed": bool(passed), "detail": detail}
    row.update(extra)
    checks.append(row)
    if not passed:
        failures.append(name)


def _legacy_fidelity(source, candidate):
    facts = set(_NUMBER.findall(source))
    retained = facts.intersection(_NUMBER.findall(candidate))
    return len(retained) / len(facts) if facts else 1.0


def _legacy_rhythm_drift(source, candidate):
    source_sentences = _sentences(source)
    candidate_sentences = _sentences(candidate)
    source_mean = (
        sum(map(len, source_sentences)) / max(len(source_sentences), 1))
    candidate_mean = (
        sum(map(len, candidate_sentences))
        / max(len(candidate_sentences), 1))
    return abs(source_mean - candidate_mean)


def run_regression(
        mode, chapter_id, revision_cycle_id, producer_task_id,
        draft_text=None, pre_apply_text=None, applied_draft_text=None,
        nkb_revision="", nkb_snapshot_sha256="",
        protected_manifest_sha256="", outline_sha256="",
        chapter_review_report_sha256="", style_guidance_sha256="",
        fidelity_report=None, quality_report=None,
        require_report_bindings=False, checkers=None, created_at=None,
        model_id="", prompt_hash=""):
    """Produce the only artifact allowed to assert FINAL_PASSED."""
    del checkers  # Deprecated injection point; strict-v2 consumes reports.
    if mode not in ("baseline", "post_apply"):
        return {
            "schema": SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "mode": mode,
            "final_regression_mode": mode,
            "chapter_id": chapter_id,
            "revision_cycle_id": revision_cycle_id,
            "producer_task_id": producer_task_id,
            "task_id": producer_task_id,
            "input_refs": {},
            "checks": [],
            "failures": ["invalid_mode"],
            "result": "FINAL_FAILED",
            "overall": "FINAL_FAILED",
            "draft_sha256": "",
            "nkb_revision": nkb_revision,
            "nkb_snapshot_sha256": nkb_snapshot_sha256,
            "outline_sha256": outline_sha256,
            "protected_manifest_sha256": protected_manifest_sha256,
            "style_guidance_sha256": style_guidance_sha256,
            "chapter_review_report_sha256":
                chapter_review_report_sha256,
            "final_regression_config_version": CONFIG_VERSION,
            "model_id": model_id,
            "prompt_hash": prompt_hash,
            "error": "invalid mode: %s" % mode,
            "created_at": created_at or time.time(),
        }

    text = (
        draft_text or "" if mode == "baseline"
        else applied_draft_text or "")
    draft_hash = _sha256(text)
    checks = []
    failures = []
    input_refs = {
        "current_draft_sha256": draft_hash,
        "pre_apply_sha256": (
            _sha256(pre_apply_text or "")
            if mode == "post_apply" else ""),
    }

    bindings = {
        "nkb_revision": nkb_revision,
        "nkb_snapshot_sha256": nkb_snapshot_sha256,
        "outline_sha256": outline_sha256,
        "protected_manifest_sha256": protected_manifest_sha256,
        "style_guidance_sha256": style_guidance_sha256,
        "chapter_review_report_sha256": chapter_review_report_sha256,
    }
    always_required = {
        "nkb_revision", "nkb_snapshot_sha256",
        "protected_manifest_sha256"}
    if mode == "baseline":
        always_required.add("chapter_review_report_sha256")
    for name, value in bindings.items():
        required = require_report_bindings or name in always_required
        _add_check(
            checks, failures, "%s_binding" % name,
            bool(value) or not required,
            "present" if value else (
                "missing" if required else "legacy_optional"))

    if mode == "post_apply":
        if require_report_bindings:
            fidelity = fidelity_report or {}
            fidelity_ok = (
                fidelity.get("result") == "FIDELITY_PASSED"
                and fidelity.get("candidate_sha256") == draft_hash
                and (
                    not protected_manifest_sha256
                    or fidelity.get("protected_manifest_sha256")
                    == protected_manifest_sha256))
            _add_check(
                checks, failures, "fidelity_report_binding", fidelity_ok,
                "specialist fidelity report must pass and bind hashes",
                report_result=fidelity.get("result"),
                candidate_sha256=fidelity.get("candidate_sha256"))

            quality = quality_report or {}
            quality_ok = (
                quality.get("overall") == "QUALITY_PASSED"
                and (
                    not style_guidance_sha256
                    or quality.get("style_guidance_sha256")
                    == style_guidance_sha256))
            _add_check(
                checks, failures, "quality_report_binding", quality_ok,
                "specialist quality report must pass and bind guidance",
                report_result=quality.get("overall"))
        else:
            # Compatibility diagnostics for unmigrated tests/projects. These
            # are explicitly non-literary signals and are never used by the
            # strict-v2 path.
            retention = _legacy_fidelity(
                pre_apply_text or "", text)
            _add_check(
                checks, failures, "fidelity",
                retention >= 0.95,
                "legacy deterministic fact-retention signal",
                fact_retention=round(retention, 4),
                pre_apply_digest=_sha256(pre_apply_text or ""),
                applied_digest=draft_hash)
            drift = _legacy_rhythm_drift(
                pre_apply_text or "", text)
            _add_check(
                checks, failures, "quality_regression",
                drift <= 15.0,
                "legacy deterministic rhythm-drift signal",
                style_drift=round(drift, 4),
                pre_apply_digest=_sha256(pre_apply_text or ""),
                applied_digest=draft_hash)

    result = "FINAL_PASSED" if not failures else "FINAL_FAILED"
    return {
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "final_regression_mode": mode,
        "chapter_id": chapter_id,
        "revision_cycle_id": revision_cycle_id,
        "producer_task_id": producer_task_id,
        "task_id": producer_task_id,
        "input_refs": input_refs,
        "checks": checks,
        "failures": failures,
        "result": result,
        "overall": result,
        "draft_sha256": draft_hash,
        "nkb_revision": nkb_revision,
        "nkb_snapshot_sha256": nkb_snapshot_sha256,
        "outline_sha256": outline_sha256,
        "protected_manifest_sha256": protected_manifest_sha256,
        "style_guidance_sha256": style_guidance_sha256,
        "chapter_review_report_sha256":
            chapter_review_report_sha256,
        "final_regression_config_version": CONFIG_VERSION,
        "model_id": model_id,
        "prompt_hash": prompt_hash,
        "created_at": created_at or time.time(),
    }


def validate_result(report):
    errors = []
    required = [
        "schema", "schema_version", "mode", "final_regression_mode",
        "chapter_id", "revision_cycle_id", "producer_task_id", "task_id",
        "input_refs", "checks", "failures", "result",
        "draft_sha256", "nkb_revision", "nkb_snapshot_sha256",
        "outline_sha256", "protected_manifest_sha256",
        "style_guidance_sha256", "chapter_review_report_sha256",
        "final_regression_config_version", "created_at",
    ]
    for field in required:
        if field not in report:
            errors.append("missing field: %s" % field)
    if report.get("result") not in ("FINAL_PASSED", "FINAL_FAILED"):
        errors.append("invalid result: %s" % report.get("result"))
    if report.get("overall") not in ("FINAL_PASSED", "FINAL_FAILED"):
        errors.append("invalid overall: %s" % report.get("overall"))
    if not isinstance(report.get("checks"), list):
        errors.append("checks must be list")
    if not isinstance(report.get("failures"), list):
        errors.append("failures must be list")
    return not errors, errors


def calculate_path(root, chapter_id, revision_cycle_id, task_id):
    return os.path.join(
        root, "analysis", "style", chapter_id, revision_cycle_id,
        "%s.final-regression-result.json" % task_id)


def persist(report, root, chapter_id, revision_cycle_id, task_id):
    path = calculate_path(
        root, chapter_id, revision_cycle_id, task_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    return path
