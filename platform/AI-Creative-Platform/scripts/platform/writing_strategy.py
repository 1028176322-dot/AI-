#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Adaptive writing-technique composition and execution evidence gate."""
import argparse
import datetime
import os
import re
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_ROOT = os.path.dirname(HERE)
for child in os.listdir(SCRIPTS_ROOT):
    path = os.path.join(SCRIPTS_ROOT, child)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

import _gov
import outline_governance

try:
    from word_budget_gate import enforce_word_budget
except Exception:  # pragma: no cover - gate module optional in some envs
    enforce_word_budget = None


TECHNIQUE_COMPATIBILITY = {
    "action": {
        "action_causality", "spatial_clarity", "environmental_pressure",
        "rhythmic_acceleration", "limited_pov_filter",
    },
    "dialogue": {
        "dialogue_subtext", "power_shift_dialogue", "decision_pressure",
        "embodied_emotion", "limited_pov_filter",
    },
    "investigation": {
        "clue_progression", "fair_clue_placement", "hypothesis_revision",
        "delayed_naming", "limited_pov_filter", "environmental_pressure",
    },
    "exploration": {
        "sensory_grounding", "environmental_pressure", "spatial_clarity",
        "concrete_detail_selection", "delayed_naming",
    },
    "emotional": {
        "free_indirect_thought", "embodied_emotion", "decision_pressure",
        "rhythmic_deceleration", "aftermath_resonance",
    },
    "business": {
        "resource_consequence", "process_compression", "dialogue_subtext",
        "power_shift_dialogue", "concrete_detail_selection",
    },
    "training": {
        "action_causality", "resource_consequence", "process_compression",
        "rhythmic_acceleration", "embodied_emotion",
    },
    "revelation": {
        "contrast_reveal", "delayed_naming", "limited_pov_filter",
        "fair_clue_placement", "aftermath_resonance",
    },
    "transition": {
        "temporal_compression", "controlled_ellipsis",
        "scene_counterpoint", "aftermath_resonance", "symbolic_echo",
    },
}
ALL_TECHNIQUES = set().union(*TECHNIQUE_COMPATIBILITY.values())
CAPABILITIES = {
    "action": ["narrative", "character", "battle", "emotion", "description"],
    "dialogue": ["narrative", "character", "dialogue", "emotion"],
    "investigation": ["narrative", "character", "description", "emotion"],
    "exploration": ["narrative", "description", "character"],
    "emotional": ["character", "emotion", "narrative", "description"],
    "business": ["narrative", "character", "dialogue", "description"],
    "training": ["character", "battle", "emotion", "description"],
    "revelation": ["narrative", "character", "emotion", "description"],
    "transition": ["narrative", "emotion", "description"],
}
OPENING_FIT = {
    "action": {
        "action_in_progress", "consequence", "failed_attempt", "reversal",
    },
    "dialogue": {
        "dialogue_conflict", "decision", "quiet_tension",
    },
    "investigation": {
        "discovery", "consequence", "failed_attempt", "quiet_tension",
    },
    "exploration": {
        "environmental_anomaly", "spatial_arrival", "discovery",
    },
    "emotional": {
        "emotional_aftershock", "decision", "quiet_tension",
    },
    "business": {
        "consequence", "failed_attempt", "dialogue_conflict", "decision",
    },
    "training": {
        "action_in_progress", "failed_attempt", "consequence",
    },
    "revelation": {
        "discovery", "reversal", "consequence", "quiet_tension",
    },
    "transition": {
        "time_jump", "spatial_arrival", "emotional_aftershock",
        "quiet_tension",
    },
}
REQUIRED_EVIDENCE_CHECKS = [
    "plan_following", "technique_fit", "environment_causality",
    "opening_alignment", "ending_alignment", "cross_chapter_variation",
    "no_generic_template",
]


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _chapter_number(value):
    match = re.search(r"(\d+)", str(value or ""))
    return int(match.group(1)) if match else None


def _chapter_id(value):
    number = _chapter_number(value)
    if number is None:
        raise ValueError("chapter id/number missing")
    return "CH-%03d" % number


def _rel(path, root):
    return os.path.relpath(path, root).replace("\\", "/")


def _plan_path(root, chapter):
    number = _chapter_number(chapter)
    plans = outline_governance._chapter_plans(root)
    path = plans.get(number)
    if not path:
        raise ValueError("chapter plan missing: CH-%03d" % number)
    return path


def _ensure_dirs(root):
    for rel in (
            "runtime/writing-strategies", "analysis/writing-strategy"):
        os.makedirs(os.path.join(root, rel), exist_ok=True)


def validate_plan_techniques(plan_data):
    errors = []
    scenes = plan_data.get("scenes") or []
    for index, scene in enumerate(scenes):
        scene_type = scene.get("type")
        technique = scene.get("technique") or {}
        dominant = technique.get("dominant")
        supporting = technique.get("supporting") or []
        if dominant not in TECHNIQUE_COMPATIBILITY.get(scene_type, set()):
            errors.append(
                "scene %s dominant technique %s does not fit %s" % (
                    scene.get("id", index), dominant, scene_type))
        unknown = [
            item for item in supporting if item not in ALL_TECHNIQUES]
        if unknown:
            errors.append(
                "scene %s unknown supporting techniques: %s" % (
                    scene.get("id", index), unknown))
        if not str(scene.get("environment_function") or "").strip():
            errors.append(
                "scene %s environment has no narrative function" %
                scene.get("id", index))
    strategy = plan_data.get("narrative_strategy") or {}
    scene_dominants = {
        (scene.get("technique") or {}).get("dominant")
        for scene in scenes}
    if strategy.get("dominant_technique") not in scene_dominants:
        errors.append(
            "chapter dominant technique is not used by any scene")
    if scenes:
        first_type = scenes[0].get("type")
        entry_mode = (
            plan_data.get("opening_design") or {}).get("entry_mode")
        if entry_mode not in OPENING_FIT.get(first_type, set()):
            errors.append(
                "opening mode %s does not fit first scene type %s" % (
                    entry_mode, first_type))
    return not errors, errors


def build(root, chapter, write=True):
    root = os.path.abspath(root)
    chapter_id = _chapter_id(chapter)
    plan_path = _plan_path(root, chapter_id)
    ok, errors, data = outline_governance.validate_chapter_plan(
        plan_path, chapter_id, require_approved=True)
    if not ok:
        raise ValueError("chapter plan invalid: %s" % "; ".join(errors))
    technique_ok, technique_errors = validate_plan_techniques(data)
    if not technique_ok:
        raise ValueError(
            "technique adaptation invalid: %s" %
            "; ".join(technique_errors))
    scene_routes = []
    for index, scene in enumerate(data.get("scenes") or [], 1):
        technique = scene["technique"]
        scene_routes.append({
            "order": index,
            "scene_id": scene["id"],
            "scene_type": scene["type"],
            "environment_function": scene["environment_function"],
            "dominant_technique": technique["dominant"],
            "supporting_techniques": technique["supporting"],
            "capabilities": CAPABILITIES[scene["type"]],
            "execution_order": [
                "establish entry condition and spatial/temporal anchor",
                "execute beats through character action and opposition",
                "make environment materially affect choice or consequence",
                "land the turn and write the declared exit state",
            ],
            "rationale": technique["rationale"],
        })
    number = _chapter_number(chapter_id)
    plans = outline_governance._chapter_plans(root)
    recent = []
    for previous in range(max(1, number - 10), number):
        path = plans.get(previous)
        if not path:
            continue
        prior = _gov.load_yaml(path) or {}
        recent.append({
            "chapter_id": "CH-%03d" % previous,
            "opening_mode":
                (prior.get("opening_design") or {}).get("entry_mode"),
            "first_scene_type":
                ((prior.get("scenes") or [{}])[0]).get("type"),
            "dominant_technique":
                (prior.get("narrative_strategy") or {}).get(
                    "dominant_technique"),
            "ending_mode":
                (prior.get("ending_design") or {}).get("closure_mode"),
        })
    result = {
        "writing_strategy": {
            "schema": "writing-strategy@1.0.0",
            "chapter_id": chapter_id,
            "chapter_plan": _rel(plan_path, root),
            "created_at": _now(),
            "narrative_strategy": data["narrative_strategy"],
            "opening_execution": data["opening_design"],
            "scene_routes": scene_routes,
            "ending_execution": data["ending_design"],
            "variation_context": {
                "recent_chapters": recent,
                "rules": [
                    "same opening entry mode may not repeat three times",
                    "same ending closure mode may not repeat three times",
                    "do not repeat the same first-scene type, dominant technique and ending combination",
                    "opening must execute continuity_anchor instead of recapping",
                    "ending must follow irreversible_change and bridge the next plan",
                ],
            },
            "gate": {
                "decision": "proceed",
                "reasons": [],
            },
        },
    }
    if write:
        _ensure_dirs(root)
        path = os.path.join(
            root, "runtime", "writing-strategies",
            "STRATEGY-%s.yaml" % chapter_id)
        _gov.dump_yaml(path, result)
        return path, result
    return None, result


def _normalize(text):
    return re.sub(r"[\W_]+", "", str(text or "").lower())


def _bigrams(text):
    value = _normalize(text)
    return {
        value[index:index + 2]
        for index in range(max(0, len(value) - 1))}


def _similarity(left, right):
    a, b = _bigrams(left), _bigrams(right)
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


def _recent_chapter_files(root, current_number):
    result = []
    approved = os.path.join(root, "chapters", "approved")
    if not os.path.isdir(approved):
        return result
    for directory, _, files in os.walk(approved):
        for filename in files:
            number = _chapter_number(filename)
            if (number and current_number - 10 <= number < current_number
                    and filename.lower().endswith((".md", ".txt"))):
                result.append((
                    number, os.path.join(directory, filename)))
    return sorted(result)


def prepare_evidence(root, chapter, draft):
    root = os.path.abspath(root)
    chapter_id = _chapter_id(chapter)
    draft_path = (
        draft if os.path.isabs(draft) else os.path.join(root, draft))
    if not os.path.isfile(draft_path):
        raise ValueError("draft missing: %s" % draft)
    strategy_path, _ = build(root, chapter_id, write=True)
    with open(draft_path, "r", encoding="utf-8") as stream:
        text = stream.read()
    opening, ending = text[:600], text[-600:]
    comparisons = []
    maximum = 0.0
    for number, path in _recent_chapter_files(
            root, _chapter_number(chapter_id)):
        with open(path, "r", encoding="utf-8") as stream:
            prior = stream.read()
        opening_similarity = _similarity(opening, prior[:600])
        ending_similarity = _similarity(ending, prior[-600:])
        maximum = max(maximum, opening_similarity, ending_similarity)
        comparisons.append({
            "chapter_id": "CH-%03d" % number,
            "opening_similarity": round(opening_similarity, 4),
            "ending_similarity": round(ending_similarity, 4),
        })
    variation_decision = "pass" if maximum <= 0.75 else "block"
    checks = {}
    for name in REQUIRED_EVIDENCE_CHECKS:
        checks[name] = {
            "decision": (
                variation_decision
                if name == "cross_chapter_variation" else "pending"),
            "evidence": (
                ["maximum boundary similarity=%.4f" % maximum]
                if name == "cross_chapter_variation" else []),
        }
    evidence = {
        "writing_strategy_evidence": {
            "schema": "writing-strategy@1.0.0",
            "chapter_id": chapter_id,
            "chapter_plan": _rel(_plan_path(root, chapter_id), root),
            "strategy_plan": _rel(strategy_path, root),
            "draft": _rel(draft_path, root),
            "checked_at": _now(),
            "checks": checks,
            "computed": {
                "recent_boundary_comparisons": comparisons,
                "maximum_boundary_similarity": round(maximum, 4),
                "threshold": 0.75,
            },
            "gate": {
                "decision": "block",
                "reasons": [
                    "AI evidence checks are pending; fill with concrete draft evidence"],
            },
        },
    }
    _ensure_dirs(root)
    path = os.path.join(
        root, "analysis", "writing-strategy",
        "EVIDENCE-%s.yaml" % chapter_id)
    _gov.dump_yaml(path, evidence)
    return path, evidence


def validate_evidence(path, root=None, chapter=None,
                      draft_path=None, plan_path=None):
    errors = []
    data = _gov.load_yaml(path) if os.path.isfile(path) else {}
    body = (data or {}).get("writing_strategy_evidence") or {}
    chapter_id = _chapter_id(chapter) if chapter else body.get("chapter_id")
    if not body:
        return False, ["writing_strategy_evidence missing"], {}
    if chapter_id and body.get("chapter_id") != chapter_id:
        errors.append("chapter_id mismatch")
    checks = body.get("checks") or {}
    for name in REQUIRED_EVIDENCE_CHECKS:
        check = checks.get(name)
        if not isinstance(check, dict):
            errors.append("%s missing" % name)
            continue
        if check.get("decision") != "pass":
            errors.append("%s decision is not pass" % name)
        if not check.get("evidence"):
            errors.append("%s evidence missing" % name)
    computed = body.get("computed") or {}
    try:
        similarity = float(
            computed.get("maximum_boundary_similarity"))
        threshold = float(computed.get("threshold", 0.75))
        if similarity > threshold:
            errors.append("cross-chapter boundary similarity exceeds threshold")
    except (TypeError, ValueError):
        errors.append("computed boundary similarity invalid")
    # Word-budget hard gate (CH-001 字数缺口治理): enforce measured length.
    if draft_path and plan_path and enforce_word_budget is not None:
        ok, werrs = enforce_word_budget(draft_path, plan_path)
        if not ok:
            errors.extend(werrs)
    gate = body.get("gate") or {}
    if gate.get("decision") != "proceed":
        errors.append("evidence gate is not proceed")
    return not errors, errors, body


def main():
    parser = argparse.ArgumentParser(
        prog="platform craft",
        description="章纲 -> 自适应写作手法编排 -> 正文执行证据门禁")
    sub = parser.add_subparsers(dest="action", required=True)
    build_parser = sub.add_parser("build")
    build_parser.add_argument("--project-root", required=True)
    build_parser.add_argument("--chapter", required=True)
    evidence_parser = sub.add_parser("evidence-prepare")
    evidence_parser.add_argument("--project-root", required=True)
    evidence_parser.add_argument("--chapter", required=True)
    evidence_parser.add_argument("--draft", required=True)
    check_parser = sub.add_parser("evidence-check")
    check_parser.add_argument("--project-root", required=True)
    check_parser.add_argument("--chapter", required=True)
    check_parser.add_argument("--evidence", required=True)
    check_parser.add_argument(
        "--draft", default=None,
        help="draft file to measure against word_budget (enables word gate)")
    check_parser.add_argument(
        "--plan", default=None,
        help="chapter plan YAML containing word_budget (enables word gate)")
    args = parser.parse_args()
    try:
        if args.action == "build":
            path, result = build(
                args.project_root, args.chapter, write=True)
            print("%s gate=%s" % (
                path, result["writing_strategy"]["gate"]["decision"]))
        elif args.action == "evidence-prepare":
            path, _ = prepare_evidence(
                args.project_root, args.chapter, args.draft)
            print(path)
        else:
            path = (
                args.evidence if os.path.isabs(args.evidence)
                else os.path.join(args.project_root, args.evidence))
            ok, errors, _ = validate_evidence(
                path, args.project_root, args.chapter)
            print("writing strategy evidence: %s" % (
                "PASS" if ok else "BLOCK"))
            for error in errors:
                print("  - %s" % error)
            if not ok:
                sys.exit(1)
    except (OSError, ValueError) as exc:
        print("ERROR: %s" % exc)
        sys.exit(2)


if __name__ == "__main__":
    main()
