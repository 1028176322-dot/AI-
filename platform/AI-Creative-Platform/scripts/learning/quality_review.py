# -*- coding: utf-8 -*-
"""Style-quality review with versioned policy and explicit judgment sources.

Deterministic metrics are reproducible signals. POV consistency and scene fit
must be supplied as structured AI semantic scores in production. The module
never mutates chapter text.
"""
import json
import os
import re
import time

SCHEMA_ID = "style.quality-report"
SCHEMA_VERSION = "2.0.0"

_SENTENCE_SPLIT = re.compile(r"(?<=[。！？；.!?;])")

SCENE_CUES = {
    "battle": list("劈斩轰爆冲退挡握刀枪火弹阵血防攻守"),
    "dialogue": list("说道问答笑叹回应沉默"),
    "exploration": list("望寻发现走路洞林山河石径遗迹"),
    "daily": list("吃喝坐站做买卖院桌锅碗"),
    "emotion": list("心泪痛喜怒怕惊爱恨颤息"),
    "exposition": list("原因据记史传说规则原理法"),
}

try:
    import sys as _sys
    _sys.path.insert(
        0, os.path.join(os.path.dirname(__file__), "..", "_common"))
    from _yaml_lite import load as _yload
except Exception:  # pragma: no cover
    try:
        from yaml import safe_load as _yload
    except Exception:
        _yload = None


def _split_sentences(text):
    return [
        sentence.strip()
        for sentence in _SENTENCE_SPLIT.split(text)
        if sentence.strip()
    ]


def _rhythm_target(style_guidance):
    for rule in (style_guidance or {}).get("effective_rules") or []:
        value = rule.get("value") or {}
        distribution = value.get("target_distribution") or {}
        if (
                value.get("dimension") == "syntactic_rhythm"
                and distribution.get("mean_sentence_chars") is not None):
            return float(distribution["mean_sentence_chars"])
        target = value.get("target") or {}
        if target.get("metric") == "avg_sentence_len_chars":
            lower, upper = target.get("min"), target.get("max")
            if (
                    isinstance(lower, (int, float))
                    and isinstance(upper, (int, float))):
                return (lower + upper) / 2.0
    return None


def _pov_target(style_guidance):
    for rule in (style_guidance or {}).get("effective_rules") or []:
        value = rule.get("value") or {}
        if value.get("dimension") != "narrative_pov":
            continue
        target = str(
            value.get("person")
            or value.get("target_person")
            or value.get("target")
            or "")
        if target in ("first", "first_person", "第一人称"):
            return "first"
        if target in ("third", "third_person", "第三人称"):
            return "third"
    return "third"


def _validate_semantic_inputs(scores, evidence, required):
    scores = scores or {}
    evidence = evidence or []
    for metric, value in scores.items():
        if not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ValueError(
                "semantic score %s must be within [0, 1]" % metric)
    if required:
        missing = sorted(
            {"pov_consistency", "scene_style_match"} - set(scores))
        if missing or not evidence:
            raise ValueError(
                "production quality review requires semantic scores/evidence: %s"
                % ", ".join(missing or ["evidence"]))
    for index, row in enumerate(evidence, 1):
        if not isinstance(row, dict):
            raise ValueError("semantic evidence #%d must be an object" % index)
        missing = [
            field for field in (
                "metric", "location", "evidence", "reader_impact")
            if row.get(field) in (None, "")
        ]
        if missing:
            raise ValueError(
                "semantic evidence #%d missing: %s"
                % (index, ", ".join(missing)))
        if len(str(row["evidence"])) > 160:
            raise ValueError(
                "semantic evidence #%d exceeds 160 chars" % index)


def compute_metrics(
        text, scene_type, style_guidance=None, semantic_scores=None):
    """Return deterministic signals and any supplied semantic judgments."""
    sentences = _split_sentences(text)
    sentence_count = max(len(sentences), 1)

    lengths = [len(sentence) for sentence in sentences]
    rhythm_target = _rhythm_target(style_guidance)
    rhythm_distance = (
        sum(abs(length - rhythm_target) for length in lengths)
        / sentence_count
        if rhythm_target is not None else None)

    third = sum(
        1 for sentence in sentences
        if ("他" in sentence or "她" in sentence or "它" in sentence))
    first = sum(
        1 for sentence in sentences
        if ("我" in sentence or "我们" in sentence))
    pov_total = third + first
    expected = first if _pov_target(style_guidance) == "first" else third
    pov_signal = expected / pov_total if pov_total else 1.0

    grams = [
        sentence[index:index + 4]
        for sentence in sentences
        for index in range(max(len(sentence) - 3, 0))
    ]
    gram_count = max(len(grams), 1)
    redundancy = (gram_count - len(set(grams))) / gram_count

    cues = SCENE_CUES.get(scene_type, [])
    scene_matches = sum(
        1 for sentence in sentences
        if any(cue in sentence for cue in cues))
    scene_signal = scene_matches / sentence_count

    semantic_scores = semantic_scores or {}
    return {
        "rhythm_distance": rhythm_distance,
        "pov_consistency": semantic_scores.get(
            "pov_consistency", pov_signal),
        "redundancy": semantic_scores.get(
            "redundancy", redundancy),
        "scene_style_match": semantic_scores.get(
            "scene_style_match", scene_signal),
    }, {
        "rhythm_distance": len(sentences),
        "pov_consistency": len(sentences),
        "redundancy": len(grams),
        "scene_style_match": len(sentences),
    }


def _compare(value, comparator, warning, failure):
    if comparator in ("lt", "lte"):
        if value < warning:
            return "pass", None
        if value < failure:
            return "warn", "near failure"
        return "fail", "exceeds failure_threshold"
    if comparator in ("gt", "gte"):
        if value > warning:
            return "pass", None
        if value > failure:
            return "warn", "near failure"
        return "fail", "below failure_threshold"
    if comparator == "range":
        lower, upper = sorted((failure, warning))
        if lower <= value <= upper:
            return "pass", None
        return "fail", "outside range [%s,%s]" % (lower, upper)
    return "fail", "unknown comparator: %s" % comparator


def load_policy(path):
    if _yload is None:
        raise RuntimeError("no yaml loader available")
    with open(path, "r", encoding="utf-8") as handle:
        return _yload(handle.read())


def _metric_report(name, row, value, sample_size, passed, detail):
    return {
        "name": name,
        "comparator": row["comparator"],
        "value": None if value is None else round(value, 4),
        "warning_threshold": row["warning_threshold"],
        "failure_threshold": row["failure_threshold"],
        "sample_size": sample_size,
        "passed": passed,
        "detail": detail,
    }


def review(
        chapter_id, revision_cycle_id, producer_task_id, task_id, scene_type,
        draft_text, policy, applied_style_rules=None,
        quality_policy_version=None, human_override=False, created_at=None,
        style_guidance=None, semantic_scores=None, semantic_evidence=None,
        require_semantic_evidence=False):
    """Evaluate a candidate without changing it."""
    policy_version = policy.get("quality_policy_version")
    if (
            quality_policy_version is not None
            and quality_policy_version != policy_version):
        raise ValueError(
            "quality_policy_version mismatch: report=%s policy=%s"
            % (quality_policy_version, policy_version))
    _validate_semantic_inputs(
        semantic_scores, semantic_evidence, require_semantic_evidence)

    values, samples = compute_metrics(
        draft_text, scene_type, style_guidance, semantic_scores)
    reports = []
    failures = []
    hard_failures = []
    non_waivable = []
    warnings = []

    for row in policy.get("thresholds", []):
        if row.get("scene_type") != scene_type:
            continue
        metric = row["metric"]
        if metric not in values:
            continue
        value = values[metric]
        sample_size = samples.get(metric, 0)
        hard = bool(row.get("hard_gate"))
        override_allowed = bool(row.get("human_override_allowed"))
        missing_policy = row["missing_data_policy"]

        if value is None:
            detail = "style guidance has no target for metric"
            failed = missing_policy == "fail"
            if missing_policy == "skip":
                continue
            reports.append(_metric_report(
                metric, row, None, 0, not failed, detail))
            (failures if failed else warnings).append(metric)
            if failed and hard:
                hard_failures.append(metric)
            if failed and not override_allowed:
                non_waivable.append(metric)
            continue

        if sample_size < row["minimum_sample_size"]:
            detail = "sample too small (%s)" % missing_policy
            failed = missing_policy == "fail"
            if missing_policy == "skip":
                continue
            reports.append(_metric_report(
                metric, row, value, sample_size, not failed, detail))
            (failures if failed else warnings).append(metric)
            if failed and hard:
                hard_failures.append(metric)
            if failed and not override_allowed:
                non_waivable.append(metric)
            continue

        verdict, detail = _compare(
            value, row["comparator"], row["warning_threshold"],
            row["failure_threshold"])
        reports.append(_metric_report(
            metric, row, value, sample_size, verdict != "fail", detail))
        if verdict == "warn":
            warnings.append(metric)
        elif verdict == "fail":
            failures.append(metric)
            if hard:
                hard_failures.append(metric)
            if not override_allowed:
                non_waivable.append(metric)

    if failures:
        overall = (
            "QUALITY_WAIVED"
            if human_override and not hard_failures and not non_waivable
            else "QUALITY_FAILED")
    else:
        overall = "QUALITY_PASSED"

    return {
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "chapter_id": chapter_id,
        "revision_cycle_id": revision_cycle_id,
        "producer_task_id": producer_task_id,
        "task_id": task_id,
        "scene_type": scene_type,
        "quality_policy_version": policy_version,
        "metrics": reports,
        "overall": overall,
        "human_override": bool(
            human_override and failures
            and not hard_failures and not non_waivable),
        "applied_style_rules": applied_style_rules or [],
        "style_guidance_sha256": (
            (style_guidance or {}).get("style_guidance_sha256", "")),
        "hard_gate_failures": sorted(set(hard_failures)),
        "quality_failures": sorted(
            set(failures) - set(hard_failures)),
        "warnings": sorted(set(warnings)),
        "waivable_failures": sorted(
            set(failures) - set(non_waivable)),
        "non_waivable_failures": sorted(set(non_waivable)),
        "semantic_evidence": semantic_evidence or [],
        "judgment_sources": {
            "deterministic_signals": [
                "rhythm_distance", "redundancy", "pov_proxy",
                "scene_cue_proxy"],
            "ai_semantic": sorted((semantic_scores or {}).keys()),
        },
        "created_at": created_at if created_at is not None else time.time(),
    }


def validate_report(report):
    errors = []
    required = [
        "schema", "schema_version", "chapter_id", "revision_cycle_id",
        "producer_task_id", "task_id", "scene_type",
        "quality_policy_version", "metrics", "overall",
        "style_guidance_sha256", "hard_gate_failures",
        "quality_failures", "warnings", "waivable_failures",
        "non_waivable_failures", "semantic_evidence",
        "judgment_sources", "created_at",
    ]
    for field in required:
        if field not in report:
            errors.append("missing field: %s" % field)
    if report.get("overall") not in (
            "QUALITY_PASSED", "QUALITY_FAILED", "QUALITY_WAIVED"):
        errors.append("invalid overall: %s" % report.get("overall"))
    if not isinstance(report.get("metrics"), list):
        errors.append("metrics must be list")
    for item in report.get("metrics") or []:
        for field in (
                "name", "comparator", "value", "sample_size", "passed"):
            if field not in item:
                errors.append("metric missing %s" % field)
    return not errors, errors


def calculate_path(root, chapter_id, revision_cycle_id, task_id):
    return os.path.join(
        root, "analysis", "style", chapter_id, revision_cycle_id,
        "%s.quality-report.json" % task_id)


def persist(report, root, chapter_id, revision_cycle_id, task_id):
    path = calculate_path(root, chapter_id, revision_cycle_id, task_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    return path
