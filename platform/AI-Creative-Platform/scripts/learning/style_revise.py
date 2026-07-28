# -*- coding: utf-8 -*-
"""Create an auditable revision candidate without mutating the draft."""
import hashlib
import json
import os
import re
import time

SCHEMA_ID = "style.revision-result"
SCHEMA_VERSION = "2.0.0"

_META_COMMENTARY = re.compile(
    r"(事实上|可以说|值得注意的是|毋庸置疑|显而易见的是|"
    r"总而言之|综上所述|坦白说|客观地说)")
_FILLER_PHRASE = re.compile(
    r"(在这个(?:时刻|时候|瞬间|世界|地方|节点)|"
    r"一种莫名的|一股莫名)")


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _apply_rule_transforms(draft_text, applied_style_rules):
    """Deterministic preview only; never a production literary revision."""
    text = draft_text
    changes = []
    sequence = 0
    for rule in applied_style_rules or []:
        value = rule.get("value") or {}
        kind = (
            rule.get("kind") or rule.get("target")
            or value.get("kind") or value.get("target"))
        pattern = None
        if kind in ("meta_commentary", "avoid_meta_commentary"):
            pattern = _META_COMMENTARY
        elif kind in ("filler_phrase", "avoid_filler"):
            pattern = _FILLER_PHRASE
        if pattern is None:
            continue
        for match in list(pattern.finditer(text)):
            before = match.group(0)
            text = text.replace(before, "", 1)
            changes.append({
                "span_id": "rule:%s:%d" % (
                    rule.get("rule_id", "r"), sequence),
                "before": before,
                "after": "",
                "reason": "deterministic preview for %s"
                % rule.get("rule_id", "unknown"),
            })
            sequence += 1
    return text, changes


def _validate_change_log(changes, source_text, candidate_text):
    for index, item in enumerate(changes, 1):
        if not isinstance(item, dict):
            raise ValueError(
                "AI change log #%d must be an object" % index)
        missing = [
            field for field in ("span_id", "before", "after", "reason")
            if field not in item or item.get(field) is None]
        if missing:
            raise ValueError(
                "AI change log #%d missing: %s"
                % (index, ", ".join(missing)))
        before = str(item["before"])
        after = str(item["after"])
        if before and before not in source_text:
            raise ValueError(
                "AI change log #%d before text is not locatable" % index)
        if after and after not in candidate_text:
            raise ValueError(
                "AI change log #%d after text is not locatable" % index)
        if len(before) > 240 or len(after) > 240:
            raise ValueError(
                "AI change log #%d excerpt exceeds 240 chars" % index)


def ai_revise(
        chapter_id, revision_cycle_id, producer_task_id, draft_text,
        protected_manifest_sha256="", applied_style_rules=None,
        style_guidance_sha256="",
        source_draft_sha256=None, previous_result=None, created_at=None,
        ai_candidate_text=None, ai_change_log=None,
        semantic_evidence_ref=None, require_ai_candidate=False):
    """Return a candidate/result pair description; source text is read-only."""
    source = draft_text[:]
    source_hash = _sha256(source)
    stale = bool(
        source_draft_sha256 is not None
        and source_draft_sha256 != source_hash)
    if previous_result is not None:
        previous_source = previous_result.get("source_draft_sha256")
        stale = stale or bool(
            previous_source is not None
            and previous_source != source_hash)
        if "style_guidance_sha256" in previous_result:
            stale = stale or (
                previous_result.get("style_guidance_sha256")
                != style_guidance_sha256)

    if require_ai_candidate and ai_candidate_text is None:
        raise ValueError(
            "production style revision requires AI-generated candidate text")
    if require_ai_candidate and not semantic_evidence_ref:
        raise ValueError(
            "production style revision requires semantic_evidence_ref")

    if ai_candidate_text is not None:
        candidate_text = ai_candidate_text
        changes = list(ai_change_log or [])
        if candidate_text != source and not changes:
            raise ValueError(
                "AI candidate changed the draft but has no change log")
        _validate_change_log(changes, source, candidate_text)
        revision_mode = "ai_semantic_candidate"
    else:
        candidate_text, changes = _apply_rule_transforms(
            source, applied_style_rules)
        revision_mode = "deterministic_preview_not_literary_revision"

    return {
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "chapter_id": chapter_id,
        "revision_cycle_id": revision_cycle_id,
        "producer_task_id": producer_task_id,
        "task_id": producer_task_id,
        "revision_candidate_ref":
            "analysis/style/%s/%s/revision-candidate.md"
            % (chapter_id, revision_cycle_id),
        "source_draft_sha256": source_hash,
        "candidate_sha256": _sha256(candidate_text),
        "changes": changes,
        "revision_mode": revision_mode,
        "semantic_evidence_ref": semantic_evidence_ref,
        "applied_style_rules": [
            rule.get("rule_id") for rule in applied_style_rules or []],
        "protected_manifest_sha256": protected_manifest_sha256,
        "style_guidance_sha256": style_guidance_sha256,
        "stale": stale,
        "created_at": created_at if created_at is not None else time.time(),
    }


def validate_revision_result(report):
    errors = []
    required = [
        "schema", "schema_version", "chapter_id", "revision_cycle_id",
        "producer_task_id", "task_id", "revision_candidate_ref",
        "source_draft_sha256", "candidate_sha256", "changes",
        "revision_mode", "protected_manifest_sha256", "stale",
        "style_guidance_sha256", "created_at",
    ]
    for field in required:
        if field not in report:
            errors.append("missing field: %s" % field)
    if not isinstance(report.get("changes"), list):
        errors.append("changes must be list")
    if report.get("revision_mode") not in (
            "ai_semantic_candidate",
            "deterministic_preview_not_literary_revision"):
        errors.append("invalid revision_mode")
    return not errors, errors


def calculate_dir(root, chapter_id, revision_cycle_id):
    return os.path.join(
        root, "analysis", "style", chapter_id, revision_cycle_id)


def persist(
        report, root, candidate_text, chapter_id,
        revision_cycle_id, producer_task_id):
    directory = calculate_dir(root, chapter_id, revision_cycle_id)
    os.makedirs(directory, exist_ok=True)
    candidate_path = os.path.join(directory, "revision-candidate.md")
    with open(candidate_path, "w", encoding="utf-8") as handle:
        handle.write(candidate_text)
    result_path = os.path.join(
        directory, "%s.revision-result.json" % producer_task_id)
    with open(result_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    return {
        "candidate_path": candidate_path,
        "result_path": result_path,
    }


def read_previous(root, chapter_id, revision_cycle_id):
    directory = calculate_dir(root, chapter_id, revision_cycle_id)
    if not os.path.isdir(directory):
        return None
    for filename in sorted(os.listdir(directory)):
        if filename.endswith(".revision-result.json"):
            with open(
                    os.path.join(directory, filename),
                    "r", encoding="utf-8") as handle:
                return json.load(handle)
    return None


def append_write_event(event_log, report, actor_id, task_id):
    if event_log is None:
        return None
    return event_log.append(
        "WRITE", actor_id or report.get("producer_task_id"),
        task_id or report.get("producer_task_id"),
        operation="style_revise",
        resource_refs=[report.get("revision_candidate_ref")],
        result="ok",
        details={
            "chapter_id": report.get("chapter_id"),
            "revision_cycle_id": report.get("revision_cycle_id"),
            "candidate_sha256": report.get("candidate_sha256"),
        })
