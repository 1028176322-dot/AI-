#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Governed five-level outline planning and validation.

The user may supply only a total chapter count. ``prepare`` converts that
constraint into a deterministic coverage skeleton and an AI generation plan.
The AI fills the creative fields; this module validates coverage, writeability,
reader value and anti-filler invariants before chapter writing may start.
"""
import argparse
import datetime
import math
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


SCHEMA_VERSION = "outline-governance@2.0.0"
ROLES = {
    "opening", "setup", "escalation", "discovery", "decision", "reversal",
    "payoff", "climax", "aftermath", "transition",
}
COMMON_DOCUMENT = [
    "id", "type", "title", "status", "version", "updated_at", "owner",
    "project_id",
]
SERIES_REQUIRED = [
    "id", "total_chapters", "premise", "story_promise", "protagonist",
    "central_conflict", "ending_direction", "major_truths", "major_arcs",
    "growth_tracks", "global_milestones", "pacing_policy",
    "forbidden_directions",
]
VOLUME_REQUIRED = [
    "id", "number", "chapter_range", "purpose", "objective", "start_state",
    "end_state", "main_characters", "main_locations", "central_conflict",
    "antagonist_pressure", "milestones", "midpoint_turn", "lowest_point",
    "climax", "aftermath", "reader_promises", "questions_opened",
    "questions_answered", "foreshadow_plan", "growth_deltas",
    "next_volume_entry",
]
ARC_REQUIRED = [
    "id", "volume_id", "chapter_range", "objective", "conflict_engine",
    "start_state", "end_state", "causal_chain", "milestones",
    "character_decisions", "reader_experience", "payoff", "handoff",
]
MAP_REQUIRED = [
    "chapter_id", "number", "volume_id", "arc_id", "role", "purpose",
    "primary_conflict", "progress", "reader_value", "planned_change",
    "end_hook", "status",
]
PLAN_SECTIONS = {
    "plan": [
        "id", "chapter_id", "number", "volume_id", "arc_id", "status",
        "role", "word_budget",
    ],
    "starting_state": [
        "time", "location", "protagonist_state", "reader_knows",
        "reader_does_not_know",
    ],
    "objectives": ["plot", "character", "reader", "arc_progress"],
    "conflict": ["desire", "opposition", "stakes", "dilemma", "escalation"],
    "causal_chain": ["prerequisites", "causes", "decision", "consequences"],
    "reader_experience": [
        "opening_question", "anticipation", "payoff", "surprise",
        "fairness_evidence", "emotional_curve",
    ],
    "information_plan": [
        "reveal", "conceal", "misinformation",
        "character_knowledge_changes",
    ],
    "foreshadow": ["plant", "reinforce", "payoff"],
    "expected_deltas": [
        "character", "relationship", "assets", "world_state", "reader_state",
    ],
    "constraints": [
        "must_happen", "must_not_happen", "continuity", "ooc_guardrails",
    ],
    "ending": ["hook_type", "hook", "next_chapter_promise"],
    "flexibility": ["fixed", "adjustable", "fallback"],
}
PLAN_ALLOW_EMPTY = {
    "starting_state": {"reader_knows"},
    "information_plan": {
        "reveal", "conceal", "misinformation",
        "character_knowledge_changes",
    },
    "foreshadow": {"plant", "reinforce", "payoff"},
    "expected_deltas": {
        "character", "relationship", "assets", "world_state", "reader_state",
    },
    "constraints": {"continuity", "ooc_guardrails"},
}
SCENE_REQUIRED = [
    "id", "type", "purpose", "location", "participants",
    "entry_condition", "beats", "turn", "exit_state",
    "environment_function", "technique",
]
SCENE_TYPES = {
    "action", "dialogue", "investigation", "exploration", "emotional",
    "business", "training", "revelation", "transition",
}
TECHNIQUE_REQUIRED = [
    "dominant", "supporting", "rhythm", "sensory_focus",
    "information_method", "rationale",
]
OPENING_MODES = {
    "action_in_progress", "consequence", "decision", "dialogue_conflict",
    "discovery", "environmental_anomaly", "emotional_aftershock",
    "time_jump", "spatial_arrival", "failed_attempt", "reversal",
    "quiet_tension",
}
ENDING_MODES = {
    "danger", "revelation", "decision", "consequence", "payoff",
    "emotional_afterglow", "relationship_shift", "cognitive_reversal",
    "new_goal", "world_state_change", "quiet_anomaly",
    "action_commitment",
}
PLAN_SECTIONS.update({
    "narrative_strategy": [
        "chapter_form", "pov", "time_structure", "dominant_technique",
        "supporting_techniques", "prose_rhythm", "information_density",
        "dialogue_ratio", "sensory_focus", "rationale",
    ],
    "opening_design": [
        "previous_plan_id", "continuity_anchor", "entry_mode", "first_scene_action",
        "opening_question", "reader_orientation", "prohibited_patterns",
    ],
    "ending_design": [
        "next_plan_id", "closure_mode", "resolved_in_chapter", "irreversible_change",
        "emotional_aftertaste", "retention_driver", "final_image",
        "next_chapter_bridge",
    ],
})


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _project(root):
    data = _gov.load_yaml(os.path.join(root, "project.yaml")) or {}
    body = data.get("project") or data
    return body.get("id"), body.get("name"), body.get("type")


def _ensure_dirs(root):
    for rel in (
            "sources/outline/_intake", "sources/outline/series",
            "sources/outline/volumes", "sources/outline/arcs",
            "sources/outline/maps", "sources/outline/chapters",
            "runtime/outline/templates", "analysis/outline",
            "lifecycle/outline", "operations/outline"):
        os.makedirs(os.path.join(root, rel), exist_ok=True)


def _rel(path, root):
    return os.path.relpath(path, root).replace("\\", "/")


def _chapter_id(number):
    return "CH-%03d" % number


def _balanced_ranges(total, target_size):
    count = max(1, int(math.ceil(float(total) / target_size)))
    base, extra = divmod(total, count)
    ranges = []
    start = 1
    for index in range(count):
        size = base + (1 if index < extra else 0)
        end = start + size - 1
        ranges.append((start, end))
        start = end + 1
    return ranges


def _volume_for(number, ranges):
    for index, (start, end) in enumerate(ranges, 1):
        if start <= number <= end:
            return "VOL-%03d" % index
    return None


def _arc_ranges(volume_ranges, target_size):
    result = []
    arc_no = 1
    for volume_no, (vstart, vend) in enumerate(volume_ranges, 1):
        total = vend - vstart + 1
        local = _balanced_ranges(total, target_size)
        for start, end in local:
            result.append({
                "id": "ARC-%03d" % arc_no,
                "volume_id": "VOL-%03d" % volume_no,
                "start": vstart + start - 1,
                "end": vstart + end - 1,
            })
            arc_no += 1
    return result


def _arc_for(number, arcs):
    for arc in arcs:
        if arc["start"] <= number <= arc["end"]:
            return arc["id"]
    return None


def prepare(root, total_chapters, volume_size=80, arc_size=20,
            detailed_window=None, allowed_variance=0,
            plan_batch_size=None):
    """Create planning policy, full coverage skeleton and AI work plan."""
    root = os.path.abspath(root)
    _ensure_dirs(root)
    project_id, project_name, genre = _project(root)
    if not project_id:
        raise ValueError("project.yaml missing project.id")
    total_chapters = int(total_chapters)
    volume_size = int(volume_size)
    arc_size = int(arc_size)
    plan_batch_size = int(
        plan_batch_size or detailed_window or 20)
    detailed_window = total_chapters
    if total_chapters < 1:
        raise ValueError("total_chapters must be positive")
    if not 10 <= volume_size <= 200:
        raise ValueError("volume_size must be between 10 and 200")
    if not 5 <= arc_size <= volume_size:
        raise ValueError("arc_size must be between 5 and volume_size")
    if not 1 <= plan_batch_size <= 100:
        raise ValueError("plan_batch_size must be between 1 and 100")

    volume_ranges = _balanced_ranges(total_chapters, volume_size)
    arcs = _arc_ranges(volume_ranges, arc_size)
    policy_path = os.path.join(
        root, "sources", "outline", "_intake", "planning-policy.yaml")
    policy = {
        "planning_policy": {
            "schema": SCHEMA_VERSION,
            "project_id": project_id,
            "total_chapters": total_chapters,
            "allowed_chapter_variance": int(allowed_variance),
            "target_volume_size": volume_size,
            "target_arc_size": arc_size,
            "detailed_window": detailed_window,
            "all_chapters_detailed_required": True,
            "generation_batch_size": plan_batch_size,
            "max_consecutive_transition_chapters": 2,
            "rolling_refresh": {
                "enabled": True,
                "trigger": "each_approved_chapter",
                "refresh_from": "approved_chapter_handoff",
                "preserve_executed_history": True,
                "minimum_future_detailed_plans": total_chapters,
            },
            "generation_authority": {
                "creative_detail_owner": "AI",
                "user_required_inputs": ["total_chapters"],
                "high_impact_decisions":
                    "follow sources/design/_intake/autonomy-policy.yaml",
            },
            "created_at": _now(),
        },
    }
    _gov.dump_yaml(policy_path, policy)

    map_entries = []
    for number in range(1, total_chapters + 1):
        map_entries.append({
            "chapter_id": _chapter_id(number),
            "number": number,
            "volume_id": _volume_for(number, volume_ranges),
            "arc_id": _arc_for(number, arcs),
            "role": "",
            "purpose": "",
            "primary_conflict": "",
            "progress": "",
            "reader_value": "",
            "planned_change": "",
            "end_hook": "",
            "status": "unplanned",
        })
    skeleton_path = os.path.join(
        root, "runtime", "outline", "templates",
        "chapter-map-skeleton.yaml")
    _gov.dump_yaml(skeleton_path, {
        "document": {
            "id": "MAP-SKELETON-001",
            "type": "chapter_map",
            "title": "%s 全书章节地图骨架" % (project_name or project_id),
            "status": "draft",
            "version": 1,
            "updated_at": datetime.date.today().isoformat(),
            "owner": "story-architect",
            "project_id": project_id,
        },
        "chapter_map": {
            "project_id": project_id,
            "total_chapters": total_chapters,
            "entries": map_entries,
        },
    })

    plan_path = os.path.join(
        root, "runtime", "outline", "generation-plan.yaml")
    batches = [{
        "order": 1,
        "level": "series",
        "range": [1, total_chapters],
        "output": "sources/outline/series/series-outline.yaml",
        "contract": "outline.schema.yaml#series_outline",
    }]
    order = 2
    for number, (start, end) in enumerate(volume_ranges, 1):
        batches.append({
            "order": order,
            "level": "volume",
            "id": "VOL-%03d" % number,
            "range": [start, end],
            "output": "sources/outline/volumes/VOL-%03d.yaml" % number,
            "contract": "outline.schema.yaml#volume_outline",
        })
        order += 1
    for arc in arcs:
        batches.append({
            "order": order,
            "level": "arc",
            "id": arc["id"],
            "volume_id": arc["volume_id"],
            "range": [arc["start"], arc["end"]],
            "output": "sources/outline/arcs/%s.yaml" % arc["id"],
            "contract": "outline.schema.yaml#arc_outline",
        })
        order += 1
    batches.append({
        "order": order,
        "level": "chapter_map",
        "range": [1, total_chapters],
        "input_skeleton": _rel(skeleton_path, root),
        "output": "sources/outline/maps/chapter-map.yaml",
        "contract": "outline.schema.yaml#chapter_map",
    })
    order += 1
    for start in range(1, total_chapters + 1, plan_batch_size):
        end = min(total_chapters, start + plan_batch_size - 1)
        batches.append({
            "order": order,
            "level": "chapter_plan_batch",
            "range": [start, end],
            "output":
                "sources/outline/chapters/PLAN-<chapter-number>.yaml",
            "contract": "outline.schema.yaml#chapter_plan",
            "all_chapters_detailed_required": True,
            "generation_batch_size": plan_batch_size,
        })
        order += 1
    _gov.dump_yaml(plan_path, {
        "outline_generation_plan": {
            "schema": SCHEMA_VERSION,
            "project_id": project_id,
            "genre": genre or "unspecified",
            "created_at": _now(),
            "execution_mode": "single_agent_sequential",
            "user_inputs": {"total_chapters": total_chapters},
            "derived_structure": {
                "volume_count": len(volume_ranges),
                "arc_count": len(arcs),
                "required_detailed_plans": total_chapters,
                "chapter_plan_batch_count":
                    int(math.ceil(
                        float(total_chapters) / plan_batch_size)),
            },
            "inputs": {
                "inspiration_brief":
                    "sources/design/_intake/inspiration-brief.yaml",
                "autonomy_policy":
                    "sources/design/_intake/autonomy-policy.yaml",
                "approved_design_sources": "sources/design/",
                "planning_policy": _rel(policy_path, root),
            },
            "batches": batches,
            "ai_instructions": [
                "先完成总纲，再完成卷纲和剧情弧，最后填写全书章节地图",
                "所有章节必须产生剧情进展、人物选择、读者收益和状态变化",
                "全书每一章都必须生成可直接写作的详细章纲；只允许分批生成，不允许降低未来章节细化程度",
                "禁止以重复冲突、重复打脸、信息复述或无状态变化章节填充章节数",
                "每章审查通过后读取 handoff 和 canonical NKB，刷新未执行的后续计划",
                "已执行历史只能引用，不能被未来规划倒写",
            ],
            "completion_gate": "platform outline validate",
        },
    })
    return {
        "planning_policy": policy_path,
        "generation_plan": plan_path,
        "chapter_map_skeleton": skeleton_path,
    }


def _nonempty(value):
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return bool(value)
    return True


def _required(body, fields, prefix, allow_empty=None):
    allow_empty = set(allow_empty or [])
    return [
        "%s.%s missing" % (prefix, field)
        for field in fields
        if (field not in body
            or (field not in allow_empty and not _nonempty(body.get(field))))
    ]


def _scan_yaml(directory):
    result = []
    if not os.path.isdir(directory):
        return result
    for current, _, files in os.walk(directory):
        for filename in files:
            if filename.lower().endswith((".yaml", ".yml")):
                result.append(os.path.join(current, filename))
    return sorted(result)


def _load_typed(path, expected_type, require_approved=True):
    data = _gov.load_yaml(path) or {}
    errors = _required(data.get("document") or {}, COMMON_DOCUMENT, "document")
    document = data.get("document") or {}
    if document.get("type") != expected_type:
        errors.append(
            "document.type must be %s" % expected_type)
    allowed = (
        ("approved", "approved_for_writing", "executed")
        if require_approved else
        ("candidate", "approved", "approved_for_writing", "executed"))
    if document.get("status") not in allowed:
        errors.append(
            "document.status is not %s" % (
                "approved" if require_approved
                else "candidate/approved"))
    return data, errors


def _find_series(root):
    candidates = [
        os.path.join(root, "sources", "outline", "series",
                     "series-outline.yaml"),
        os.path.join(root, "sources", "outline", "series-outline.yaml"),
        os.path.join(root, "sources", "outline", "series.yaml"),
    ]
    return next((path for path in candidates if os.path.isfile(path)), None)


def _find_map(root):
    candidates = [
        os.path.join(root, "sources", "outline", "maps",
                     "chapter-map.yaml"),
        os.path.join(root, "sources", "outline", "chapter-map.yaml"),
    ]
    return next((path for path in candidates if os.path.isfile(path)), None)


def _parse_range(value, label, errors):
    if (not isinstance(value, list) or len(value) != 2
            or not all(isinstance(item, int) for item in value)):
        errors.append("%s must be [start,end] integers" % label)
        return None
    start, end = value
    if start < 1 or end < start:
        errors.append("%s is invalid" % label)
        return None
    return start, end


def _coverage(ranges, total, label, errors):
    counts = [0] * (total + 1)
    for item_id, start, end in ranges:
        if start < 1 or end > total:
            errors.append("%s %s outside 1..%d" % (
                label, item_id, total))
            continue
        for number in range(start, end + 1):
            counts[number] += 1
    gaps = [number for number in range(1, total + 1)
            if counts[number] == 0]
    overlaps = [number for number in range(1, total + 1)
                if counts[number] > 1]
    if gaps:
        errors.append("%s coverage gaps: %s" % (
            label, gaps[:20]))
    if overlaps:
        errors.append("%s coverage overlaps: %s" % (
            label, overlaps[:20]))
    return not gaps and not overlaps


def validate_chapter_plan(
        path, expected_chapter=None, require_approved=True):
    data, errors = _load_typed(
        path, "chapter_plan", require_approved=require_approved)
    for section, fields in PLAN_SECTIONS.items():
        body = data.get(section)
        if not isinstance(body, dict):
            errors.append("%s missing" % section)
            continue
        errors.extend(_required(
            body, fields, section, PLAN_ALLOW_EMPTY.get(section)))
    plan = data.get("plan") or {}
    allowed_plan_status = (
        ("approved_for_writing", "executed")
        if require_approved else
        ("candidate", "approved_for_writing", "executed"))
    if plan.get("status") not in allowed_plan_status:
        errors.append(
            "plan.status must be %s" % (
                "approved_for_writing" if require_approved
                else "candidate/approved_for_writing"))
    if expected_chapter and plan.get("chapter_id") != expected_chapter:
        errors.append("plan.chapter_id does not match requested chapter")
    if plan.get("role") not in ROLES:
        errors.append("plan.role invalid")
    try:
        if int(plan.get("word_budget") or 0) <= 0:
            errors.append("plan.word_budget must be positive")
    except (TypeError, ValueError):
        errors.append("plan.word_budget must be positive")
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        errors.append("scenes requires at least one scene")
    else:
        for index, scene in enumerate(scenes):
            if not isinstance(scene, dict):
                errors.append("scenes[%d] invalid" % index)
                continue
            errors.extend(_required(
                scene, SCENE_REQUIRED, "scenes[%d]" % index))
            if scene.get("type") not in SCENE_TYPES:
                errors.append("scenes[%d].type invalid" % index)
            technique = scene.get("technique")
            if not isinstance(technique, dict):
                errors.append("scenes[%d].technique invalid" % index)
            else:
                errors.extend(_required(
                    technique, TECHNIQUE_REQUIRED,
                    "scenes[%d].technique" % index))
    deltas = data.get("expected_deltas") or {}
    if isinstance(deltas, dict) and not any(
            _nonempty(deltas.get(name)) for name in (
                "character", "relationship", "assets",
                "world_state", "reader_state")):
        errors.append("expected_deltas must contain at least one real change")
    opening = data.get("opening_design") or {}
    if opening.get("entry_mode") not in OPENING_MODES:
        errors.append("opening_design.entry_mode invalid")
    orientation = opening.get("reader_orientation")
    if not isinstance(orientation, dict):
        errors.append("opening_design.reader_orientation invalid")
    else:
        errors.extend(_required(
            orientation, ["time", "place", "active_pressure"],
            "opening_design.reader_orientation"))
    ending_design = data.get("ending_design") or {}
    if ending_design.get("closure_mode") not in ENDING_MODES:
        errors.append("ending_design.closure_mode invalid")
    strategy = data.get("narrative_strategy") or {}
    try:
        ratio = float(strategy.get("dialogue_ratio"))
        if not 0 <= ratio <= 1:
            errors.append(
                "narrative_strategy.dialogue_ratio must be 0..1")
    except (TypeError, ValueError):
        errors.append(
            "narrative_strategy.dialogue_ratio must be 0..1")
    try:
        import writing_strategy
        technique_ok, technique_errors = (
            writing_strategy.validate_plan_techniques(data))
        if not technique_ok:
            errors.extend(technique_errors)
    except Exception as exc:
        errors.append("writing technique validation failed: %s" % exc)
    return not errors, errors, data


def _chapter_number(chapter_id):
    match = re.search(r"(\d+)", str(chapter_id or ""))
    return int(match.group(1)) if match else None


def _chapter_plans(root):
    result = {}
    directory = os.path.join(root, "sources", "outline", "chapters")
    for path in _scan_yaml(directory):
        data = _gov.load_yaml(path) or {}
        chapter_id = (data.get("plan") or {}).get("chapter_id")
        number = _chapter_number(chapter_id)
        if number:
            result[number] = path
    return result


def validate_project(
        root, target_chapter=None, write=False, require_approved=True):
    """Validate full outline coverage and optionally a target chapter plan."""
    root = os.path.abspath(root)
    errors = []
    warnings = []
    policy_path = os.path.join(
        root, "sources", "outline", "_intake", "planning-policy.yaml")
    policy = (
        (_gov.load_yaml(policy_path) or {}).get("planning_policy") or {}
        if os.path.isfile(policy_path) else {})
    errors.extend(_required(policy, [
        "project_id", "total_chapters", "allowed_chapter_variance",
        "target_volume_size", "target_arc_size", "detailed_window",
        "all_chapters_detailed_required", "generation_batch_size",
        "max_consecutive_transition_chapters", "rolling_refresh",
    ], "planning_policy"))
    try:
        total = int(policy.get("total_chapters") or 0)
    except (TypeError, ValueError):
        total = 0
    if total < 1:
        errors.append("planning_policy.total_chapters must be positive")
    if policy.get("all_chapters_detailed_required") is not True:
        errors.append(
            "planning_policy.all_chapters_detailed_required must be true")
    if total and policy.get("detailed_window") != total:
        errors.append(
            "planning_policy.detailed_window must equal total_chapters")

    series_path = _find_series(root)
    if not series_path:
        errors.append("series outline missing")
        series = {}
    else:
        series_data, series_errors = _load_typed(
            series_path, "series_outline", require_approved)
        errors.extend(series_errors)
        series = series_data.get("series") or {}
        errors.extend(_required(series, SERIES_REQUIRED, "series"))
        if total and series.get("total_chapters") != total:
            errors.append("series.total_chapters mismatches planning policy")

    volume_ranges = []
    volume_files = _scan_yaml(os.path.join(
        root, "sources", "outline", "volumes"))
    if not volume_files:
        errors.append("volume outlines missing")
    for path in volume_files:
        data, file_errors = _load_typed(
            path, "volume_outline", require_approved)
        errors.extend(["%s: %s" % (_rel(path, root), item)
                       for item in file_errors])
        body = data.get("volume") or {}
        errors.extend(_required(body, VOLUME_REQUIRED, "volume"))
        parsed = _parse_range(
            body.get("chapter_range"),
            "%s.volume.chapter_range" % _rel(path, root), errors)
        if parsed:
            volume_ranges.append((
                body.get("id") or os.path.basename(path),
                parsed[0], parsed[1]))
        if isinstance(body.get("milestones"), list) and len(
                body.get("milestones")) < 3:
            errors.append("%s needs at least three milestones" %
                          _rel(path, root))

    arc_ranges = []
    arc_files = _scan_yaml(os.path.join(
        root, "sources", "outline", "arcs"))
    if not arc_files:
        errors.append("arc outlines missing")
    for path in arc_files:
        data, file_errors = _load_typed(
            path, "arc_outline", require_approved)
        errors.extend(["%s: %s" % (_rel(path, root), item)
                       for item in file_errors])
        body = data.get("arc") or {}
        errors.extend(_required(body, ARC_REQUIRED, "arc"))
        parsed = _parse_range(
            body.get("chapter_range"),
            "%s.arc.chapter_range" % _rel(path, root), errors)
        if parsed:
            arc_ranges.append((
                body.get("id") or os.path.basename(path),
                parsed[0], parsed[1]))

    coverage = {
        "volumes": (
            _coverage(volume_ranges, total, "volume", errors)
            if total else False),
        "arcs": (
            _coverage(arc_ranges, total, "arc", errors)
            if total else False),
        "chapter_map": False,
    }
    map_path = _find_map(root)
    entries = []
    if not map_path:
        errors.append("chapter map missing")
    else:
        map_data, map_errors = _load_typed(
            map_path, "chapter_map", require_approved)
        errors.extend(map_errors)
        map_body = map_data.get("chapter_map") or {}
        errors.extend(_required(
            map_body, ["project_id", "total_chapters", "entries"],
            "chapter_map"))
        entries = map_body.get("entries") or []
        if map_body.get("total_chapters") != total:
            errors.append("chapter_map.total_chapters mismatches policy")
        numbers = []
        fingerprints = []
        consecutive_transition = 0
        max_transition = int(
            policy.get("max_consecutive_transition_chapters") or 2)
        for index, entry in enumerate(entries):
            prefix = "chapter_map.entries[%d]" % index
            if not isinstance(entry, dict):
                errors.append("%s invalid" % prefix)
                continue
            errors.extend(_required(entry, MAP_REQUIRED, prefix))
            number = entry.get("number")
            if isinstance(number, int):
                numbers.append(number)
                if entry.get("chapter_id") != _chapter_id(number):
                    errors.append("%s.chapter_id/number mismatch" % prefix)
            if entry.get("role") not in ROLES:
                errors.append("%s.role invalid" % prefix)
            if entry.get("role") == "transition":
                consecutive_transition += 1
                if consecutive_transition > max_transition:
                    errors.append(
                        "anti-filler: transition chapters exceed maximum at %s"
                        % entry.get("chapter_id"))
            else:
                consecutive_transition = 0
            fingerprint = tuple(str(entry.get(name) or "").strip() for name in (
                "purpose", "primary_conflict", "progress", "reader_value"))
            fingerprints.append(fingerprint)
            if (len(fingerprints) >= 3
                    and fingerprint == fingerprints[-2]
                    and fingerprint == fingerprints[-3]):
                errors.append(
                    "anti-filler: repeated chapter function at %s"
                    % entry.get("chapter_id"))
        expected = list(range(1, total + 1)) if total else []
        coverage["chapter_map"] = sorted(numbers) == expected
        if not coverage["chapter_map"]:
            missing = sorted(set(expected) - set(numbers))
            duplicates = sorted({
                number for number in numbers if numbers.count(number) > 1})
            errors.append(
                "chapter map coverage invalid; missing=%s duplicates=%s"
                % (missing[:20], duplicates[:20]))

    plans = _chapter_plans(root)
    detailed_window = min(
        total, int(policy.get("detailed_window") or 0)) if total else 0
    missing_plans = [
        number for number in range(1, detailed_window + 1)
        if number not in plans]
    if missing_plans:
        errors.append("detailed window missing plans: %s" % missing_plans)
    plan_errors = {}
    opening_modes = []
    ending_modes = []
    detailed_data = {}
    for number in range(1, detailed_window + 1):
        path = plans.get(number)
        if not path:
            continue
        ok, current_errors, _ = validate_chapter_plan(
            path, _chapter_id(number), require_approved)
        if not ok:
            plan_errors[_chapter_id(number)] = current_errors
            errors.extend([
                "%s: %s" % (_chapter_id(number), item)
                for item in current_errors])
        plan_data = _gov.load_yaml(path) or {}
        detailed_data[number] = plan_data
        opening_modes.append(
            (plan_data.get("opening_design") or {}).get("entry_mode"))
        ending_modes.append(
            (plan_data.get("ending_design") or {}).get("closure_mode"))
    for label, modes in (
            ("opening", opening_modes), ("ending", ending_modes)):
        for index in range(2, len(modes)):
            if (modes[index] and modes[index] == modes[index - 1]
                    and modes[index] == modes[index - 2]):
                errors.append(
                    "anti-template: %s mode repeats for %s-%s" % (
                        label, _chapter_id(index - 1),
                        _chapter_id(index + 1)))
    for number in range(1, detailed_window + 1):
        current = detailed_data.get(number)
        if not current:
            continue
        previous_expected = (
            "ROOT" if number == 1
            else ((detailed_data.get(number - 1) or {}).get("plan") or {})
            .get("id"))
        next_expected = (
            "END" if number == total
            else ((detailed_data.get(number + 1) or {}).get("plan") or {})
            .get("id"))
        opening = current.get("opening_design") or {}
        ending = current.get("ending_design") or {}
        plan_body = current.get("plan") or {}
        map_entry = next((
            item for item in entries
            if isinstance(item, dict)
            and item.get("number") == number), {})
        for field in ("chapter_id", "volume_id", "arc_id", "role"):
            if (map_entry and
                    plan_body.get(field) != map_entry.get(field)):
                errors.append(
                    "%s plan.%s mismatches chapter map" % (
                        _chapter_id(number), field))
        if opening.get("previous_plan_id") != previous_expected:
            errors.append(
                "%s opening previous_plan_id mismatch" %
                _chapter_id(number))
        if ending.get("next_plan_id") != next_expected:
            errors.append(
                "%s ending next_plan_id mismatch" %
                _chapter_id(number))

    if target_chapter:
        target_number = _chapter_number(target_chapter)
        target_path = plans.get(target_number)
        if not target_path:
            errors.append("%s approved chapter plan missing" % target_chapter)
        else:
            ok, current_errors, _ = validate_chapter_plan(
                target_path, _chapter_id(target_number), require_approved)
            if not ok:
                errors.extend([
                    "%s: %s" % (target_chapter, item)
                    for item in current_errors])

    decision = "proceed" if not errors else "block"
    report = {
        "outline_validation": {
            "schema": SCHEMA_VERSION,
            "checked_at": _now(),
            "project_root": root,
            "total_chapters": total,
            "target_chapter": target_chapter,
            "require_approved": require_approved,
            "coverage": coverage,
            "counts": {
                "volumes": len(volume_files),
                "arcs": len(arc_files),
                "chapter_map_entries": len(entries),
                "detailed_plans": len(plans),
                "required_detailed_plans": detailed_window,
            },
            "anti_filler": {
                "max_consecutive_transition_chapters":
                    policy.get("max_consecutive_transition_chapters"),
                "decision": "pass" if not any(
                    "anti-filler" in item for item in errors) else "block",
            },
            "errors": errors[:200],
            "warnings": warnings,
            "gate": {"decision": decision, "reasons": errors[:20]},
        },
    }
    if write:
        _ensure_dirs(root)
        _gov.dump_yaml(os.path.join(
            root, "analysis", "outline", "OUTLINE_VALIDATION.yaml"), report)
    return report


def approve_outline(root, approved_by, evidence):
    """Promote structurally valid outline candidates after design approval."""
    preliminary = validate_project(
        root, write=False, require_approved=False)
    body = preliminary["outline_validation"]
    if body["gate"]["decision"] != "proceed":
        raise ValueError(
            "outline candidates invalid: %s" %
            "; ".join(body["gate"]["reasons"]))
    promoted = []
    outline_root = os.path.join(root, "sources", "outline")
    for path in _scan_yaml(outline_root):
        relative = _rel(path, root)
        if "/_intake/" in ("/" + relative):
            continue
        data = _gov.load_yaml(path) or {}
        document = data.get("document")
        if not isinstance(document, dict):
            continue
        document_type = document.get("type")
        if document_type not in (
                "series_outline", "volume_outline", "arc_outline",
                "chapter_map", "chapter_plan"):
            continue
        desired = (
            "approved_for_writing"
            if document_type == "chapter_plan" else "approved")
        document["status"] = desired
        document["approved_by"] = approved_by
        document["approved_at"] = _now()
        document["approval_evidence"] = evidence
        if document_type == "chapter_plan":
            data.setdefault("plan", {})["status"] = (
                "approved_for_writing")
        _gov.dump_yaml(path, data)
        promoted.append(relative)
    operation_path = os.path.join(
        root, "operations", "outline",
        "OUTLINE-APPROVAL-%s.yaml" %
        datetime.datetime.now().strftime("%Y%m%d%H%M%S%f"))
    _gov.dump_yaml(operation_path, {
        "operation": {
            "type": "outline_candidate_approval",
            "approved_by": approved_by,
            "approved_at": _now(),
            "evidence": evidence,
            "promoted": promoted,
        },
    })
    final = validate_project(
        root, write=True, require_approved=True)
    if final["outline_validation"]["gate"]["decision"] != "proceed":
        raise ValueError(
            "approved outline validation failed: %s" % "; ".join(
                final["outline_validation"]["gate"]["reasons"]))
    return operation_path, promoted, final


def extract_total_chapters(text):
    """Extract an explicit whole-book chapter count from conversational text."""
    patterns = [
        r"(?:全书|整本|整部|总共|共|计划)?\s*(\d{1,6})\s*章",
        r"章节数\s*(?:为|是|[:：])?\s*(\d{1,6})",
    ]
    for pattern in patterns:
        match = re.search(pattern, str(text or ""))
        if match:
            value = int(match.group(1))
            if value > 0:
                return value
    return None


def main():
    parser = argparse.ArgumentParser(
        prog="platform outline",
        description="总章节数 -> 五级大纲生成计划 -> 覆盖/可写性/防注水门禁")
    sub = parser.add_subparsers(dest="action", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--project-root", required=True)
    prepare_parser.add_argument("--total-chapters", type=int, required=True)
    prepare_parser.add_argument("--volume-size", type=int, default=80)
    prepare_parser.add_argument("--arc-size", type=int, default=20)
    prepare_parser.add_argument(
        "--detailed-window", type=int,
        help="兼容旧参数；现在表示单批生成章数，不再减少详细章纲覆盖")
    prepare_parser.add_argument("--batch-size", type=int, default=20)
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--project-root", required=True)
    validate_parser.add_argument("--chapter")
    check_parser = sub.add_parser("chapter-check")
    check_parser.add_argument("--project-root", required=True)
    check_parser.add_argument("--chapter", required=True)
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            outputs = prepare(
                args.project_root, args.total_chapters,
                args.volume_size, args.arc_size, args.detailed_window,
                plan_batch_size=args.batch_size)
            for name, path in outputs.items():
                print("%s: %s" % (name, path))
        else:
            report = validate_project(
                args.project_root, args.chapter, write=True)
            body = report["outline_validation"]
            print("outline: %s total=%s volumes=%d arcs=%d map=%d plans=%d/%d" % (
                body["gate"]["decision"], body["total_chapters"],
                body["counts"]["volumes"], body["counts"]["arcs"],
                body["counts"]["chapter_map_entries"],
                body["counts"]["detailed_plans"],
                body["counts"]["required_detailed_plans"]))
            for reason in body["gate"]["reasons"]:
                print("  - %s" % reason)
            if body["gate"]["decision"] == "block":
                sys.exit(1)
    except (OSError, ValueError) as exc:
        print("ERROR: %s" % exc)
        sys.exit(2)


if __name__ == "__main__":
    main()
