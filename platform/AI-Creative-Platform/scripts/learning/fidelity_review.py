# -*- coding: utf-8 -*-
"""Fidelity gate for revision candidates.

Scripts verify hashes and verbatim must-preserve anchors deterministically.
Motivation, causality, timeline, reveal boundaries, outline outcomes and
unsupported facts must be supplied as structured AI semantic evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
import time

import _gov


SCHEMA_ID = "style.fidelity-report"
SCHEMA_VERSION = "1.0.0"
SEMANTIC_CATEGORIES = {
    "character_motivation",
    "causality",
    "timeline",
    "reveal_boundary",
    "outline_goal",
    "state_change",
    "unsupported_facts",
}


def _sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _items(manifest, level):
    node = manifest.get(level) or {}
    values = node.get("items") if isinstance(node, dict) else node
    return values if isinstance(values, list) else []


def _anchor_text(item):
    if isinstance(item, str):
        return item
    if not isinstance(item, dict):
        return ""
    return str(
        item.get("text") or item.get("fact") or item.get("content") or "")


def _semantic_checks(evidence, require, source_text="", candidate_text=""):
    rows = list(evidence or [])
    if require and not rows:
        raise ValueError(
            "production fidelity review requires AI semantic evidence")
    normalized = []
    seen = set()
    for index, raw in enumerate(rows, 1):
        missing = [
            field for field in ("category", "result", "evidence", "reason")
            if raw.get(field) in (None, "")]
        if missing:
            raise ValueError(
                "semantic fidelity evidence #%d missing: %s" %
                (index, ", ".join(missing)))
        category = raw["category"]
        if category not in SEMANTIC_CATEGORIES:
            raise ValueError(
                "unknown semantic fidelity category: %s" % category)
        if raw["result"] not in ("pass", "fail"):
            raise ValueError("semantic fidelity result must be pass/fail")
        excerpt = str(raw["evidence"])
        if len(excerpt) > 160:
            raise ValueError(
                "semantic fidelity evidence #%d exceeds 160 chars" % index)
        if excerpt not in source_text and excerpt not in candidate_text:
            raise ValueError(
                "semantic fidelity evidence #%d is not locatable" % index)
        item = dict(raw)
        item["judgment_source"] = "ai_semantic_evidence"
        normalized.append(item)
        seen.add(category)
    if require:
        missing_categories = sorted(SEMANTIC_CATEGORIES - seen)
        if missing_categories:
            raise ValueError(
                "semantic fidelity categories missing: %s" %
                ", ".join(missing_categories))
    return normalized


def review(
        chapter_id, revision_cycle_id, producer_task_id,
        source_text, candidate_text, protected_manifest,
        protected_manifest_path=None, semantic_evidence=None,
        require_semantic_evidence=False, created_at=None):
    hard = _items(protected_manifest, "hard_preserve")
    hard_anchors = [
        _anchor_text(item) for item in hard if _anchor_text(item)]
    must_anchors = [
        _anchor_text(item) for item in hard
        if isinstance(item, dict)
        and item.get("must_preserve") is True
        and _anchor_text(item)]
    missing_hard = [
        anchor for anchor in hard_anchors if anchor not in candidate_text]
    missing_must = [
        anchor for anchor in must_anchors if anchor not in candidate_text]
    semantic = _semantic_checks(
        semantic_evidence, require_semantic_evidence,
        source_text, candidate_text)
    semantic_failures = [
        item for item in semantic if item["result"] == "fail"]
    unsupported = []
    for item in semantic:
        if (
                item["category"] == "unsupported_facts"
                and item["result"] == "fail"):
            claims = item.get("unsupported_facts")
            unsupported.extend(
                claims if isinstance(claims, list) and claims
                else [item])
    hard_rate = (
        1.0 if not hard_anchors
        else (len(hard_anchors) - len(missing_hard)) / len(hard_anchors))
    must_rate = (
        1.0 if not must_anchors
        else (len(must_anchors) - len(missing_must)) / len(must_anchors))
    passed = (
        hard_rate == 1.0
        and must_rate == 1.0
        and not unsupported
        and not semantic_failures)
    stable_manifest = {
        key: value for key, value in protected_manifest.items()
        if key != "created_at"}
    manifest_sha = hashlib.sha256(json.dumps(
        stable_manifest, ensure_ascii=False, sort_keys=True
    ).encode("utf-8")).hexdigest()
    return {
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "chapter_id": chapter_id,
        "revision_cycle_id": revision_cycle_id,
        "producer_task_id": producer_task_id,
        "task_id": producer_task_id,
        "source_draft_sha256": _sha256_text(source_text),
        "candidate_sha256": _sha256_text(candidate_text),
        "protected_manifest_sha256": manifest_sha,
        "hard_fact_retention": round(hard_rate, 6),
        "must_preserve_retention": round(must_rate, 6),
        "unsupported_fact_count": len(unsupported),
        "missing_hard_anchors": missing_hard,
        "missing_must_preserve_anchors": missing_must,
        "semantic_checks": semantic,
        "result": (
            "FIDELITY_PASSED" if passed else "FIDELITY_FAILED"),
        "created_at": created_at if created_at is not None else time.time(),
    }


def persist(report, root, chapter_id, revision_cycle_id):
    directory = os.path.join(
        root, "analysis", "style", chapter_id, revision_cycle_id)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "fidelity-report.yaml")
    _gov.dump_yaml(path, report)
    return path


def validate_report(report):
    required = (
        "chapter_id", "revision_cycle_id", "producer_task_id",
        "source_draft_sha256", "candidate_sha256",
        "protected_manifest_sha256", "hard_fact_retention",
        "must_preserve_retention", "unsupported_fact_count",
        "semantic_checks", "result", "created_at")
    errors = [
        "missing field: %s" % name for name in required
        if name not in report]
    if report.get("result") not in (
            "FIDELITY_PASSED", "FIDELITY_FAILED"):
        errors.append("invalid result")
    return not errors, errors
