# -*- coding: utf-8 -*-
"""Read-only style diagnosis with explicit signal/judgment separation."""
import hashlib
import json
import os
import re
import time

SCHEMA_ID = "style.diagnosis"
SCHEMA_VERSION = "2.0.0"
VALID_ACTIONS = ("revise", "skip", "human_review")

_SENTENCE_SPLIT = re.compile(r"(?<=[。！？；.!?;])")
_PATTERNS = {
    "meta_commentary": re.compile(
        r"(事实上|可以说|值得注意的是|毋庸置疑|显而易见的是|"
        r"总而言之|综上所述|坦白说|客观地说)"),
    "filler_phrase": re.compile(
        r"(在这个(?:时刻|时候|瞬间|世界|地方|节点)|"
        r"一种莫名的|一股莫名)"),
    "connector_spam": re.compile(
        r"(?:而且|并且|同时|此外|然而|于是|因此|所以)"
        r"[，,]?(?:而且|并且|同时|此外|然而|于是|因此|所以)"),
    "direct_emotion_signal": re.compile(
        r"(?:他|她|众人)?(?:感到|觉得|十分|非常)?"
        r"(愤怒|悲伤|害怕|紧张|绝望|高兴|震惊)"),
    "adjective_inflation_signal": re.compile(
        r"(?:[\u4e00-\u9fff]{1,4}的){3,}[\u4e00-\u9fff]{1,6}"),
    "environment_function_signal": re.compile(
        r"(阳光洒在|微风拂过|树叶沙沙作响|夜色如墨|月光如水)"),
}
_HEDGE = re.compile(
    r"(可能|也许|似乎|大概|某种程度上|在某种意义上|在一定程度上)")
_GENERIC_OPENING = re.compile(
    r"^(?:清晨|天刚亮|夜色如墨|窗外下着雨|"
    r"他睁开眼|她睁开眼|端起茶|放下茶杯)")
_GENERIC_ENDING = re.compile(
    r"(?:这一切才刚刚开始|命运的齿轮开始转动|"
    r"他不知道的是|真正的危险才刚刚开始)[。！？.!?]?$")


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sentences(text):
    return [
        sentence.strip()
        for sentence in _SENTENCE_SPLIT.split(text)
        if sentence.strip()]


def _signal(
        category, span_id, evidence, description, severity="low"):
    return {
        "category": category,
        "location": span_id,
        "span_id": span_id,
        "evidence": evidence[:160],
        "description": description,
        "severity": severity,
        "evidence_kind": "deterministic_signal",
        "requires_ai_confirmation": True,
        "reader_impact": "必须由 AI 按真实读者体验进行语义复核",
        "violated_style_rule": "unconfirmed",
        "requires_revision": False,
        "revision_boundary": "不得仅凭此信号自动改写",
        "protected_facts": [],
    }


def _detect_signals(draft_text, adjacent_chapters=None):
    signals = []
    sentences = _sentences(draft_text)
    total = max(len(sentences), 1)
    openers = {}
    for sentence in sentences:
        opener = sentence[:2]
        openers.setdefault(opener, []).append(sentence)
    for opener, rows in sorted(openers.items()):
        if opener and len(rows) >= 3 and len(rows) / total >= 0.15:
            signals.append(_signal(
                "repetitive_opener", "opener:%s" % opener,
                rows[0][:160],
                "连续 %d 句以“%s”开头，疑似模板化节奏"
                % (len(rows), opener), "medium"))

    for category, pattern in _PATTERNS.items():
        for match in pattern.finditer(draft_text):
            signals.append(_signal(
                category, "span:%d" % match.start(),
                match.group(0), "检测到 %s 信号" % category,
                "medium" if category in (
                    "connector_spam",
                    "adjective_inflation_signal") else "low"))

    hedges = list(_HEDGE.finditer(draft_text))
    if len(hedges) >= 5:
        signals.append(_signal(
            "hedge_overuse", "doc:hedge",
            "、".join(match.group(0) for match in hedges[:8]),
            "模糊限定词出现 %d 次" % len(hedges)))
    stripped = draft_text.strip()
    opening = _GENERIC_OPENING.search(stripped)
    if opening:
        signals.append(_signal(
            "generic_opening", "doc:opening", opening.group(0),
            "开头命中通用天气、醒来或饮茶模板信号", "medium"))
    ending = _GENERIC_ENDING.search(stripped)
    if ending:
        signals.append(_signal(
            "generic_ending_hook", "doc:ending", ending.group(0),
            "结尾命中模板化悬念信号", "medium"))

    lengths = [len(sentence) for sentence in sentences]
    if len(lengths) >= 6:
        mean = sum(lengths) / len(lengths)
        variance = sum(
            (value - mean) ** 2 for value in lengths) / len(lengths)
        if variance ** 0.5 < 2.5:
            signals.append(_signal(
                "mechanical_sentence_length_signal",
                "doc:sentence-rhythm",
                "句长=%s" % ",".join(map(str, lengths[:12])),
                "连续句长方差过低，存在机械节奏信号", "medium"))

    normalized_current = re.sub(r"\s+", "", draft_text)
    for index, item in enumerate(adjacent_chapters or [], 1):
        text = (
            item.get("text", "") if isinstance(item, dict)
            else str(item))
        normalized_adjacent = re.sub(r"\s+", "", text)
        if len(normalized_current) < 80 or len(normalized_adjacent) < 80:
            continue
        current_windows = {
            normalized_current[offset:offset + 24]
            for offset in range(0, len(normalized_current) - 23, 8)}
        adjacent_windows = {
            normalized_adjacent[offset:offset + 24]
            for offset in range(0, len(normalized_adjacent) - 23, 8)}
        overlap = current_windows.intersection(adjacent_windows)
        if overlap:
            evidence = sorted(overlap)[0]
            signals.append(_signal(
                "adjacent_chapter_repetition_signal",
                "adjacent:%d" % index, evidence,
                "与相邻章节出现 24 字重复窗口，需语义复核",
                "medium"))
    return signals


def _semantic_issues(draft_text, evidence):
    normalized = []
    required = (
        "category", "location", "evidence", "reader_impact",
        "violated_style_rule", "requires_revision",
        "revision_boundary", "protected_facts")
    for index, raw in enumerate(evidence or [], 1):
        if not isinstance(raw, dict):
            raise ValueError(
                "semantic evidence #%d must be an object" % index)
        missing = [
            field for field in required
            if field not in raw or raw.get(field) in (None, "")]
        if missing:
            raise ValueError(
                "semantic evidence #%d missing: %s"
                % (index, ", ".join(missing)))
        excerpt = str(raw["evidence"])
        if len(excerpt) > 160:
            raise ValueError(
                "semantic evidence #%d excerpt exceeds 160 chars" % index)
        if excerpt not in draft_text:
            raise ValueError(
                "semantic evidence #%d cannot be located in draft" % index)
        issue = dict(raw)
        issue["span_id"] = str(raw["location"])
        issue["description"] = str(
            raw.get("description") or raw["reader_impact"])
        issue["severity"] = str(raw.get("severity") or "medium")
        issue["evidence_kind"] = "ai_semantic_evidence"
        issue["requires_ai_confirmation"] = False
        normalized.append(issue)
    return normalized


def ai_diagnose(
        chapter_id, revision_cycle_id, task_id, draft_text,
        nkb_snapshot=None, protected_manifest_sha256="", policy=None,
        diagnosed_at=None, semantic_evidence=None, style_guidance=None,
        adjacent_chapters=None, require_semantic_evidence=False):
    del policy
    source = draft_text[:]
    nkb_copy = (
        dict(nkb_snapshot) if isinstance(nkb_snapshot, dict)
        else nkb_snapshot)
    if require_semantic_evidence and not semantic_evidence:
        raise ValueError(
            "production diagnosis requires structured AI semantic evidence")
    signals = _detect_signals(source, adjacent_chapters)
    semantic = _semantic_issues(source, semantic_evidence or [])
    actionable = [
        item for item in semantic
        if item.get("requires_revision") is True]
    has_issues = bool(actionable)
    only_warnings = bool(signals or semantic) and not has_issues
    severe = any(
        item.get("severity") == "high" for item in actionable)
    recommended = (
        "human_review" if severe or only_warnings
        else "revise" if has_issues else "skip")
    nkb_hash = (
        _sha256(json.dumps(
            nkb_copy, ensure_ascii=False, sort_keys=True))
        if nkb_copy is not None else "")
    return {
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "chapter_id": chapter_id,
        "revision_cycle_id": revision_cycle_id,
        "producer_task_id": task_id,
        "task_id": task_id,
        "diagnosed_at": (
            diagnosed_at if diagnosed_at is not None else time.time()),
        "has_issues": has_issues,
        "issue_list": semantic + signals,
        "semantic_evidence_count": len(semantic),
        "deterministic_signal_count": len(signals),
        "literary_judgment_source": (
            "ai_semantic_evidence" if semantic
            else "none; deterministic signals are not literary judgments"),
        "style_guidance_sha256": (
            (style_guidance or {}).get("style_guidance_sha256", "")
            if isinstance(style_guidance, dict) else ""),
        "adjacent_chapter_evidence": adjacent_chapters or [],
        "only_warnings": only_warnings,
        "recommended_action": recommended,
        "source_draft_sha256": _sha256(source),
        "protected_manifest_sha256": protected_manifest_sha256,
        "nkb_snapshot_sha256": nkb_hash,
    }


def validate_diagnosis(report):
    errors = []
    required = [
        "schema", "schema_version", "chapter_id", "revision_cycle_id",
        "producer_task_id", "task_id", "diagnosed_at", "has_issues",
        "issue_list", "semantic_evidence_count",
        "deterministic_signal_count", "literary_judgment_source",
        "style_guidance_sha256", "only_warnings",
        "recommended_action", "source_draft_sha256",
        "protected_manifest_sha256",
    ]
    for field in required:
        if field not in report:
            errors.append("missing field: %s" % field)
    if report.get("recommended_action") not in VALID_ACTIONS:
        errors.append(
            "invalid recommended_action: %s"
            % report.get("recommended_action"))
    if not isinstance(report.get("issue_list"), list):
        errors.append("issue_list must be list")
    for item in report.get("issue_list") or []:
        for field in (
                "category", "location", "span_id", "evidence",
                "reader_impact", "violated_style_rule",
                "requires_revision", "revision_boundary",
                "protected_facts", "evidence_kind"):
            if field not in item:
                errors.append("issue missing %s" % field)
    return not errors, errors


def calculate_path(root, chapter_id, task_id):
    return os.path.join(
        root, "analysis", "style", chapter_id, task_id,
        "diagnosis.json")


def persist(report, root, chapter_id, task_id):
    path = calculate_path(root, chapter_id, task_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    return path


def read(root, chapter_id, task_id):
    path = calculate_path(root, chapter_id, task_id)
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)
