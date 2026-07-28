# -*- coding: utf-8 -*-
"""Reference-novel learning pipeline.

The engine extracts reproducible structural signals from user-provided TXT/MD
novels and emits writing/review candidates without copying source prose.
Candidates are advisory until a governed task explicitly promotes them into a
project's private memory; genre/global promotion remains subject to the memory
governance thresholds.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import statistics
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_ROOT = os.path.dirname(HERE)
for child in os.listdir(SCRIPTS_ROOT):
    path = os.path.join(SCRIPTS_ROOT, child)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

import _gov
import reference_fingerprint
import style_extract


SUPPORTED_EXTENSIONS = (".txt", ".md")
HOOK_WORDS = (
    "却", "竟", "突然", "不料", "危机", "秘密", "真相", "然而",
    "就在这时", "与此同时", "究竟", "谁", "为何", "尚未",
)
EMOTION_WORDS = (
    "喜", "怒", "悲", "惊", "恐", "惧", "恨", "爱", "痛", "慌",
    "愤", "怯", "妒", "伤", "狂", "颤", "凄", "欣", "松",
)
INFO_WORDS = (
    "所谓", "据闻", "传说", "规矩", "法则", "境界", "历史", "制度",
    "因为", "因此", "意味着", "换言之", "也就是说",
)


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _percentile(values, fraction):
    if not values:
        return 0
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * fraction))
    return ordered[max(0, min(len(ordered) - 1, index))]


def _safe_id(text):
    value = re.sub(r"[^A-Za-z0-9_-]+", "-", str(text or "")).strip("-")
    return value or "reference"


def _read_source(path):
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    if os.path.splitext(path)[1].lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError("仅支持 TXT/MD 参考文件: %s" % path)
    with open(path, "r", encoding="utf-8-sig") as stream:
        return stream.read()


def _semantic_evidence_for_source(path):
    """Load an optional AI semantic-evidence sidecar without storing prose.

    Supported names are ``novel.style-evidence.yaml|json`` and
    ``novel.txt.style-evidence.yaml|json``.  The sidecar must be a mapping
    keyed by the twelve style-dimension identifiers.
    """
    stem, _ = os.path.splitext(path)
    candidates = [
        stem + ".style-evidence.yaml",
        stem + ".style-evidence.json",
        path + ".style-evidence.yaml",
        path + ".style-evidence.json",
    ]
    for candidate in candidates:
        if not os.path.isfile(candidate):
            continue
        if candidate.lower().endswith(".json"):
            with open(candidate, "r", encoding="utf-8-sig") as stream:
                payload = json.load(stream)
        else:
            payload = _gov.load_yaml(candidate)
        if not isinstance(payload, dict):
            raise ValueError("语义证据 sidecar 必须是映射: %s" % candidate)
        return payload
    return {}


def _strip_markup(text):
    lines = []
    for line in text.splitlines():
        value = line.strip()
        if not value or re.fullmatch(r"[-=*]{3,}", value):
            continue
        value = re.sub(r"^#{1,6}\s*", "", value)
        value = value.strip("*_ ")
        if value:
            lines.append(value)
    return "\n".join(lines)


def _chapters(text):
    pattern = re.compile(
        r"(?m)^(?:#{1,6}\s*)?第[0-9零一二三四五六七八九十百千万两]+章[^\n]*$")
    matches = list(pattern.finditer(text))
    if not matches:
        return [text]
    result = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end():end].strip()
        if body:
            result.append(body)
    return result or [text]


def _count_words(text, words):
    return sum(text.count(word) for word in words)


def _dialogue_chars(text):
    spans = re.findall(r"[“「『][^”」』]{1,1000}[”」』]", text, flags=re.S)
    return sum(len(item) for item in spans)


def _emotion_curve(text, segments=8):
    if not text:
        return [0] * segments
    size = max(1, len(text) // segments)
    curve = []
    for index in range(segments):
        part = text[index * size:(index + 1) * size] \
            if index < segments - 1 else text[index * size:]
        curve.append(round(_count_words(part, EMOTION_WORDS) * 1000.0 /
                           max(1, len(part)), 3))
    return curve


def _metrics(text):
    clean = _strip_markup(text)
    chapters = _chapters(text)
    chapter_lengths = [len(_strip_markup(chapter)) for chapter in chapters]
    paragraphs = [item.strip() for item in clean.splitlines() if item.strip()]
    paragraph_lengths = [len(item) for item in paragraphs]
    sentences = [
        item.strip() for item in re.split(r"[。！？!?；;]", clean) if item.strip()
    ]
    sentence_lengths = [len(item) for item in sentences]
    end_hook_hits = 0
    for chapter in chapters:
        ending = _strip_markup(chapter)[-300:]
        if any(word in ending for word in HOOK_WORDS) or "？" in ending:
            end_hook_hits += 1
    opening = clean[:max(500, len(clean) // 20)]
    curve = _emotion_curve(clean)
    dialogue_ratio = _dialogue_chars(clean) / float(max(1, len(clean)))
    return {
        "characters": len(clean),
        "chapters": len(chapters),
        "chapter_length": {
            "median": int(statistics.median(chapter_lengths)) if chapter_lengths else 0,
            "p25": _percentile(chapter_lengths, 0.25),
            "p75": _percentile(chapter_lengths, 0.75),
        },
        "paragraph_length": {
            "median": int(statistics.median(paragraph_lengths)) if paragraph_lengths else 0,
            "p90": _percentile(paragraph_lengths, 0.90),
        },
        "sentence_length": {
            "mean": round(sum(sentence_lengths) / float(max(1, len(sentence_lengths))), 2),
            "p90": _percentile(sentence_lengths, 0.90),
        },
        "dialogue_ratio": round(dialogue_ratio, 4),
        "opening_hook_density": round(
            _count_words(opening, HOOK_WORDS) * 1000.0 / max(1, len(opening)), 3),
        "ending_hook_rate": round(end_hook_hits / float(max(1, len(chapters))), 4),
        "emotion_curve": curve,
        "emotion_variance": round(
            statistics.pvariance(curve) if len(curve) > 1 else 0.0, 4),
        "information_density": round(
            _count_words(clean, INFO_WORDS) * 1000.0 / max(1, len(clean)), 3),
    }


def _candidate(rule_id, target, principle, metric, value, check, action,
               source_id, source_hash, genre, confidence,
               scope_content_type="both", scope_scene_types=None):
    """生成风格规则候选（§2.3 规范 scope）。"""
    return {
        "rule_id": rule_id,
        "target": target,
        "scope": {
            "content_type": scope_content_type,        # narration | dialogue | both
            "scene_types": scope_scene_types or [],     # 空=全场景
            "character_ids": [],                        # 空=不适用
        },
        "genre": genre,
        "principle": principle,
        "evidence": {
            "source_id": source_id,
            "source_hash": source_hash,
            "metric": metric,
            "value": value,
            "raw_excerpt_copied": False,
        },
        "review_check": check,
        "writing_action": action,
        "confidence": round(confidence, 2),
        "status": "candidate",
        "requires_project_validation": True,
    }


def _derive_candidates(metrics, source_id, source_hash, genre):
    candidates = []
    chapter = metrics["chapter_length"]
    candidates.append(_candidate(
        "REF-CHAPTER-RHYTHM", "both",
        "章节容量应形成稳定区间，并允许关键章节有受控偏离。",
        "chapter_length", chapter,
        "检查章节长度是否偏离参考区间且偏离是否服务于情节。",
        "规划时给出目标区间与偏离理由，不机械复制参考书字数。",
        source_id, source_hash, genre, 0.62))
    if metrics["ending_hook_rate"] >= 0.35:
        candidates.append(_candidate(
            "REF-END-HOOK", "both",
            "连续阅读依赖章节末尾仍有未完成的行动、信息或情绪承诺。",
            "ending_hook_rate", metrics["ending_hook_rate"],
            "检查章末是否产生具体下一步期待，而非只靠突兀断章。",
            "章纲明确本章兑现与下一章承诺，正文末尾回扣该承诺。",
            source_id, source_hash, genre,
            min(0.9, 0.55 + metrics["ending_hook_rate"] * 0.3)))
    if 0.08 <= metrics["dialogue_ratio"] <= 0.55:
        candidates.append(_candidate(
            "REF-DIALOGUE-BALANCE", "both",
            "对白应承担行动、关系或信息变化，而非脱离叙事独立堆积。",
            "dialogue_ratio", metrics["dialogue_ratio"],
            "检查对白占比、角色辨识度及每段对白造成的状态变化。",
            "场景规划同时标注对白目的、潜台词和对白后的局面变化。",
            source_id, source_hash, genre, 0.66))
    if metrics["paragraph_length"]["p90"] > metrics["paragraph_length"]["median"] * 2:
        candidates.append(_candidate(
            "REF-PARAGRAPH-CONTRAST", "writing",
            "长短段落的对比可服务信息承载与节奏加速。",
            "paragraph_length", metrics["paragraph_length"],
            "检查长段是否造成认知负荷、短段是否只是碎片化。",
            "在解释、动作、转折处主动设计段落长度变化。",
            source_id, source_hash, genre, 0.58))
    if metrics["emotion_variance"] > 0:
        candidates.append(_candidate(
            "REF-EMOTION-WAVE", "both",
            "情绪应随冲突和选择产生可辨认的波形，避免全章同强度。",
            "emotion_variance", metrics["emotion_variance"],
            "按场景标记情绪起点、峰值、回落与余波。",
            "章纲预设情绪转折，写作后核对变化是否由事件触发。",
            source_id, source_hash, genre, 0.64))
    return candidates


def analyze(
        source_path, genre, output_dir, source_id=None,
        fingerprint_key_id="default", license_type="user-provided",
        semantic_evidence=None):
    text = _read_source(source_path)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    source_id = source_id or _safe_id(os.path.splitext(os.path.basename(source_path))[0])
    metrics = _metrics(text)
    fingerprint = reference_fingerprint.Fingerprinter().fingerprint(
        text, key_id=fingerprint_key_id, source_id=source_id,
        license_type=license_type)
    report = {
        "schema": "reference-learning@2.0.0",
        "meta": {
            "source_id": source_id,
            "source_name": os.path.basename(source_path),
            "source_hash": digest,
            "genre": genre,
            "analyzed_at": _now(),
            "copyright_policy": "statistics_and_principles_only",
            "license_type": license_type,
        },
        "metrics": metrics,
        "style_dimensions": style_extract.extract_source_profile(text),
        "semantic_evidence": semantic_evidence or {},
        "fingerprint": fingerprint,
        "legacy_candidates": _derive_candidates(
            metrics, source_id, digest, genre),
        "candidates": [],
        "raw_text_stored": False,
    }
    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(output_dir, "%s.profile.yaml" % _safe_id(source_id))
    _gov.dump_yaml(out, report)
    return out, report


def _normalized_weights(source_ids):
    if not source_ids:
        return {}
    weight = 1.0 / len(source_ids)
    return {source_id: round(weight, 6) for source_id in source_ids}


def _build_archetype(profiles, genre):
    source_ids = [
        (profile.get("meta") or {}).get("source_id")
        for profile in profiles]
    weights = _normalized_weights(source_ids)
    dimensions = {}
    for name in style_extract.extract_source_profile("").keys():
        nodes = [
            (profile.get("style_dimensions") or {}).get(name, {})
            for profile in profiles]
        dimensions[name] = style_extract._aggregate_nodes(nodes)
    return {
        "schema": "style-archetype@2.0.0",
        "genre": genre,
        "source_count": len(source_ids),
        "source_ids": source_ids,
        "source_contribution_vector": weights,
        "minimum_independent_sources": 3,
        "recommended_independent_sources": 5,
        "max_single_source_weight": 0.4,
        "dimensions": dimensions,
        "status": (
            "review_pending" if len(source_ids) >= 3
            else "insufficient_sources"),
        "raw_text_stored": False,
    }


def batch(
        input_dir, genre, output_dir, fingerprint_key_id="default",
        license_type="user-provided"):
    sources = []
    for name in sorted(os.listdir(input_dir)):
        path = os.path.join(input_dir, name)
        if os.path.isfile(path) and name.lower().endswith(SUPPORTED_EXTENSIONS):
            sources.append(path)
    profiles = []
    profile_payloads = []
    source_payloads = []
    for path in sources:
        profile_path, report = analyze(
            path, genre, output_dir,
            fingerprint_key_id=fingerprint_key_id,
            license_type=license_type,
            semantic_evidence=_semantic_evidence_for_source(path))
        profiles.append(os.path.basename(profile_path))
        profile_payloads.append(report)
        source_payloads.append({
            "source_id": (report.get("meta") or {}).get("source_id"),
            "text": _read_source(path),
            "semantic_evidence": report.get("semantic_evidence") or {},
        })
    weights = _normalized_weights([
        item["source_id"] for item in source_payloads])
    for item in source_payloads:
        item["weight"] = weights[item["source_id"]]
    archetype = _build_archetype(profile_payloads, genre)
    archetype_dir = os.path.join(output_dir, "style-archetypes")
    os.makedirs(archetype_dir, exist_ok=True)
    archetype_path = os.path.join(
        archetype_dir, "%s.archetype.yaml" % _safe_id(genre))
    _gov.dump_yaml(archetype_path, archetype)
    style_candidates = []
    candidate_dir = os.path.join(output_dir, "style-rule-candidates")
    if len(source_payloads) >= 3:
        extractor = style_extract.StyleExtractor(
            extractor_version="twelve-dimension-2.0.0")
        style_candidates = extractor.extract(
            source_payloads, "REFERENCE-BATCH", "REFERENCE-BATCH")
        os.makedirs(candidate_dir, exist_ok=True)
        for candidate in style_candidates:
            with open(
                    os.path.join(
                        candidate_dir,
                        "%s.json" % candidate["candidate_id"]),
                    "w", encoding="utf-8") as stream:
                json.dump(
                    candidate, stream, ensure_ascii=False, indent=2)
    summary = {
        "schema": "reference-learning-summary@2.0.0",
        "genre": genre,
        "generated_at": _now(),
        "source_profiles": profiles,
        "source_count": len(profiles),
        "archetype": os.path.relpath(
            archetype_path, output_dir).replace("\\", "/"),
        "source_contribution_vector": weights,
        "style_rule_candidate_ids": [
            item["candidate_id"] for item in style_candidates],
        "style_rule_candidates_require_review": True,
        "writing_candidates": [],
        "review_candidates": [],
        "promotion": {
            "state": "candidate",
            "rule": "参考书数量不等于项目验证数；先进入项目试验，再按 memory 晋升门槛升级。",
        },
    }
    out = os.path.join(output_dir, "learning-summary.yaml")
    _gov.dump_yaml(out, summary)
    return out, summary


def withdraw_source(summary_path, source_id, output_dir=None):
    """Withdraw a source and cascade invalidation/recomputation.

    Raw reference prose is never needed for this operation: the twelve
    dimension profiles and semantic evidence are sufficient to rebuild the
    aggregate candidates.  Every old candidate that depended on the withdrawn
    source is retained as a revoked audit record.
    """
    summary = _gov.load_yaml(summary_path) or {}
    base = output_dir or os.path.dirname(summary_path)
    remaining = []
    removed = []
    for name in summary.get("source_profiles") or []:
        path = name if os.path.isabs(name) else os.path.join(base, name)
        profile = _gov.load_yaml(path) or {}
        if (profile.get("meta") or {}).get("source_id") == source_id:
            removed.append(profile)
        else:
            remaining.append(profile)
    if not removed:
        raise ValueError("未找到可撤回来源: %s" % source_id)

    archetype = _build_archetype(
        remaining, summary.get("genre") or "unknown")
    archetype["withdrawn_source_id"] = source_id
    archetype["recomputed_at"] = _now()
    if len(remaining) < 3:
        archetype["status"] = "SUSPENDED"
        archetype["suspension_reason"] = (
            "source withdrawal reduced independent sources below 3")
    path = os.path.join(
        base, "style-archetypes",
        "%s.archetype.yaml" % _safe_id(summary.get("genre") or "unknown"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _gov.dump_yaml(path, archetype)

    candidate_dir = os.path.join(base, "style-rule-candidates")
    revoked_ids = []
    if os.path.isdir(candidate_dir):
        for filename in sorted(os.listdir(candidate_dir)):
            if not filename.endswith(".json"):
                continue
            candidate_path = os.path.join(candidate_dir, filename)
            with open(candidate_path, "r", encoding="utf-8") as stream:
                candidate = json.load(stream)
            contributions = candidate.get("source_contribution_vector") or {}
            if source_id not in contributions:
                continue
            candidate["review_status"] = "REVOKED"
            candidate["revocation"] = {
                "reason": "reference_source_withdrawn",
                "source_id": source_id,
                "at": _now(),
            }
            revoked_ids.append(candidate.get("candidate_id"))
            with open(candidate_path, "w", encoding="utf-8") as stream:
                json.dump(candidate, stream, ensure_ascii=False, indent=2)

    source_ids = [
        (profile.get("meta") or {}).get("source_id")
        for profile in remaining
    ]
    weights = _normalized_weights(source_ids)
    rebuilt = []
    if len(remaining) >= 3:
        payloads = []
        for profile in remaining:
            meta = profile.get("meta") or {}
            sid = meta.get("source_id")
            payloads.append({
                "source_id": sid,
                "text": "",
                "style_profile": profile.get("style_dimensions") or {},
                "semantic_evidence": profile.get("semantic_evidence") or {},
                "weight": weights[sid],
            })
        rebuilt = style_extract.StyleExtractor(
            extractor_version="twelve-dimension-2.0.0"
        ).extract(payloads, "REFERENCE-WITHDRAWAL", "REFERENCE-WITHDRAWAL")
        os.makedirs(candidate_dir, exist_ok=True)
        for candidate in rebuilt:
            with open(os.path.join(
                    candidate_dir, "%s.json" % candidate["candidate_id"]),
                    "w", encoding="utf-8") as stream:
                json.dump(candidate, stream, ensure_ascii=False, indent=2)

    updated_profiles = [
        os.path.basename(
            next(
                name if os.path.isabs(name) else os.path.join(base, name)
                for name in summary.get("source_profiles") or []
                if ((_gov.load_yaml(
                    name if os.path.isabs(name)
                    else os.path.join(base, name)) or {}).get("meta") or {})
                .get("source_id") == sid
            )
        )
        for sid in source_ids
    ]
    summary.update({
        "generated_at": _now(),
        "source_profiles": updated_profiles,
        "source_count": len(remaining),
        "source_contribution_vector": weights,
        "style_rule_candidate_ids": [
            item["candidate_id"] for item in rebuilt],
        "withdrawal": {
            "source_id": source_id,
            "revoked_candidate_ids": revoked_ids,
            "rebuilt_candidate_ids": [
                item["candidate_id"] for item in rebuilt],
            "status": archetype.get("status"),
            "at": _now(),
        },
    })
    _gov.dump_yaml(summary_path, summary)
    report = {
        "schema": "reference-source-withdrawal@1.0.0",
        "source_id": source_id,
        "remaining_source_count": len(remaining),
        "source_contribution_vector": weights,
        "archetype": os.path.relpath(path, base).replace("\\", "/"),
        "archetype_status": archetype.get("status"),
        "revoked_candidate_ids": revoked_ids,
        "rebuilt_candidate_ids": [
            item["candidate_id"] for item in rebuilt],
        "summary_updated": os.path.abspath(summary_path),
        "raw_text_stored": False,
        "created_at": _now(),
    }
    report_path = os.path.join(
        base, "withdrawals", "%s.withdrawal.yaml" % _safe_id(source_id))
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    _gov.dump_yaml(report_path, report)
    return report_path, report


def promote_project(summary_path, project_root, approved=False):
    if not approved:
        raise ValueError("项目级启用需要 --approved；参考规律不得无门禁改写正式规则")
    # 可选门禁：若 authorize 模块可用则通过授权校验
    try:
        from logs.authorize import authorize, TaskContext
        ctx = TaskContext(actor_role="architect",
                          session_ready=True,
                          subagent_policy="denied")
        ok, reason = authorize("promote", ctx)
        if not ok:
            raise PermissionError("门禁拒绝 promote: %s" % reason)
    except ImportError:
        pass  # 非刚性阻断：authorize 模块不可用时跳过
    summary = _gov.load_yaml(summary_path) or {}
    if summary.get("style_rule_candidate_ids"):
        raise ValueError(
            "style candidates must pass style-rule-review and "
            "style-rule-promote; direct project promotion is forbidden")
    if not summary.get("writing_candidates") and not summary.get("review_candidates"):
        raise ValueError("学习摘要没有候选规则")
    digest = hashlib.sha256(
        repr(summary).encode("utf-8")).hexdigest()[:12]
    memory_dir = os.path.join(
        project_root, "memory", "project", "reference-learning")
    runtime_dir = os.path.join(project_root, "runtime", "learning")
    os.makedirs(memory_dir, exist_ok=True)
    os.makedirs(runtime_dir, exist_ok=True)
    record = {
        "schema": "project-reference-learning@1.0.0",
        "id": "LEARN-%s" % digest.upper(),
        "genre": summary.get("genre"),
        "source_count": summary.get("source_count", 0),
        "writing_candidates": summary.get("writing_candidates") or [],
        "review_candidates": summary.get("review_candidates") or [],
        "scope": "current_project_experiment",
        "status": "active",
        "activated_at": _now(),
        "promotion_eligible": False,
    }
    memory_path = os.path.join(memory_dir, record["id"] + ".yaml")
    guidance_path = os.path.join(runtime_dir, "reference-guidance.yaml")
    _gov.dump_yaml(memory_path, record)
    _gov.dump_yaml(guidance_path, {
        "schema": "writing-review-guidance@1.0.0",
        "source": memory_path.replace("\\", "/"),
        "writing": record["writing_candidates"],
        "review": record["review_candidates"],
    })
    return memory_path, guidance_path


def validate_profile(path):
    data = _gov.load_yaml(path) or {}
    errors = []
    if data.get("schema") not in (
            "reference-learning@1.0.0", "reference-learning@2.0.0"):
        errors.append("schema 非受支持的 reference-learning 版本")
    if not (data.get("meta") or {}).get("source_hash"):
        errors.append("缺 source_hash")
    if data.get("raw_text_stored") is not False:
        errors.append("禁止在学习产物中保存原文")
    for index, candidate in enumerate(data.get("candidates") or [], 1):
        for field in ("rule_id", "target", "principle", "review_check",
                      "writing_action", "confidence", "status"):
            if candidate.get(field) in (None, ""):
                errors.append("candidate #%d 缺 %s" % (index, field))
    return not errors, errors


def main():
    parser = argparse.ArgumentParser(prog="learn")
    sub = parser.add_subparsers(dest="action", required=True)
    one = sub.add_parser("analyze")
    one.add_argument("--source", required=True)
    one.add_argument("--genre", required=True)
    one.add_argument("--output-dir", required=True)
    one.add_argument("--source-id")
    one.add_argument("--fingerprint-key-id", default="default")
    one.add_argument("--license-type", default="user-provided")
    many = sub.add_parser("batch")
    many.add_argument("--input-dir", required=True)
    many.add_argument("--genre", required=True)
    many.add_argument("--output-dir", required=True)
    many.add_argument("--fingerprint-key-id", default="default")
    many.add_argument("--license-type", default="user-provided")
    promote = sub.add_parser("promote-project")
    promote.add_argument("--summary", required=True)
    promote.add_argument("--project-root", required=True)
    promote.add_argument("--approved", action="store_true")
    validate = sub.add_parser("validate")
    validate.add_argument("--profile", required=True)
    withdraw = sub.add_parser("withdraw")
    withdraw.add_argument("--summary", required=True)
    withdraw.add_argument("--source-id", required=True)
    withdraw.add_argument("--output-dir")
    args = parser.parse_args()
    if args.action == "analyze":
        path, _ = analyze(
            args.source, args.genre, args.output_dir, args.source_id,
            fingerprint_key_id=args.fingerprint_key_id,
            license_type=args.license_type)
        print("✓ reference profile: %s" % path)
    elif args.action == "batch":
        path, report = batch(
            args.input_dir, args.genre, args.output_dir,
            fingerprint_key_id=args.fingerprint_key_id,
            license_type=args.license_type)
        print("✓ learning summary: %s (sources=%d)" %
              (path, report["source_count"]))
    elif args.action == "promote-project":
        memory, guidance = promote_project(
            args.summary, args.project_root, args.approved)
        print("✓ project learning: %s" % memory)
        print("✓ runtime guidance: %s" % guidance)
    elif args.action == "withdraw":
        path, report = withdraw_source(
            args.summary, args.source_id, args.output_dir)
        print("✓ archetype recomputed: %s (status=%s)" % (
            path, report.get("archetype_status")))
    else:
        ok, errors = validate_profile(args.profile)
        if not ok:
            for error in errors:
                print("FAIL: %s" % error)
            sys.exit(1)
        print("PASS: reference learning profile")


if __name__ == "__main__":
    main()
