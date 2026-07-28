# -*- coding: utf-8 -*-
"""Sequential AI reader lenses plus separately governed real-reader data."""
import argparse
import datetime
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_ROOT = os.path.dirname(HERE)
for _child in os.listdir(SCRIPTS_ROOT):
    _path = os.path.join(SCRIPTS_ROOT, _child)
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

import _gov

PLATFORM_ROOT = os.path.dirname(SCRIPTS_ROOT)
REGISTRY_PATH = os.path.join(PLATFORM_ROOT, "registry", "readers.yaml")

DEFAULT_LENSES = [
    ("first_contact", "首次接触", "开篇理解成本、第一兴趣点和继续阅读意愿"),
    ("new_reader", "新读者", "不了解背景时能否理解人物、目标和局势"),
    ("genre_veteran", "类型老读者", "套路预期、创新度、可信度和审美疲劳"),
    ("plot_logic", "剧情逻辑", "因果、选择、代价、巧合与信息权限"),
    ("character_empathy", "人物共情", "动机、情绪、关系和角色能动性"),
    ("world_immersion", "世界沉浸", "设定呈现、出戏点、感官和规则边界"),
    ("pacing_fatigue", "节奏疲劳", "拖沓、跳跃、重复、负荷和停读风险"),
    ("prose_clarity", "文字清晰", "句段可读性、指代、画面、解释腔和 AI 腔"),
    ("emotion_reward", "情绪兑现", "情绪波形、期待、奖励、爽点和余韵"),
    ("serial_retention", "追读留存", "章末承诺、下一章欲望和连续阅读动力"),
    ("commercial_value", "付费价值", "获得感、稀缺性和付费/推荐意愿"),
    ("safety_accessibility", "边界与可达性", "敏感内容、刻板印象和受众障碍"),
]

HUMAN_DIMENSIONS = [
    "comprehensibility", "logic_trust", "character_empathy",
    "world_immersion", "pacing", "prose_naturalness",
    "emotion_reward", "originality", "continuation_intent",
    "recommend_score", "payment_intent", "completion_ratio",
]
REQUIRED_LENS_FIELDS = (
    "score", "observation", "evidence_location", "reading_effect",
    "expectation", "recommended_fix", "confidence",
)


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _lenses():
    data = _gov.load_yaml(REGISTRY_PATH) or {}
    configured = ((data.get("reader_panel") or {}).get("lenses") or [])
    result = []
    for item in configured:
        if isinstance(item, dict) and item.get("id"):
            result.append((
                item["id"], item.get("name") or item["id"],
                item.get("focus") or ""))
    # Ignore a fully mojibake registry entry set. The canonical built-ins are
    # safer until the registry is explicitly upgraded.
    if result and all("�" not in name for _, name, _ in result):
        return result
    return DEFAULT_LENSES


def _panel_dir(project_root, task_id):
    return os.path.join(
        project_root, "runtime", "reader-panels",
        "PANEL-%s" % task_id)


def prepare_panel(
        project_root, task_id, chapter_ref=None, chapter_path=None):
    base = _panel_dir(project_root, task_id)
    os.makedirs(base, exist_ok=True)
    report_path = os.path.join(base, "report.yaml")
    report = {
        "schema": "reader-panel@2.0.0",
        "panel_id": "PANEL-%s" % task_id,
        "task_id": task_id,
        "chapter_ref": chapter_ref,
        "evidence_mode": "ai_sequential_panel_not_human_feedback",
        "created_at": _now(),
        "source": chapter_path,
        "lenses": [{
            "id": lens_id,
            "name": name,
            "focus": focus,
            "score": None,
            "observation": None,
            "evidence_location": None,
            "evidence_excerpt": None,
            "reading_effect": None,
            "expectation": None,
            "recommended_fix": None,
            "confidence": None,
        } for lens_id, name, focus in _lenses()],
        "dropoff": {
            "risk": None, "location": None, "reason": None},
        "summary": None,
        "reader_index": None,
        "gate": {"decision": None, "reasons": []},
        "human_calibration": {
            "status": "not_provided", "report": None},
    }
    _gov.dump_yaml(report_path, report)
    brief_path = os.path.join(base, "brief.md")
    lines = [
        "# 读者面板 · %s" % task_id,
        "",
        "- 同一主 Agent 串行切换观察镜头，不创建子 Agent。",
        "- 先无解释通读，再逐镜头复核；每个判断必须给正文位置、"
        "短证据和阅读影响。",
        "- AI 面板是预测证据，不能冒充真人反馈；真人数据必须走"
        " `ingest-human`。",
        "",
        "## 观察镜头",
        "",
    ]
    for index, (lens_id, name, focus) in enumerate(_lenses(), 1):
        lines.append(
            "%d. `%s` %s：%s" % (index, lens_id, name, focus))
    lines += [
        "",
        "## 必答问题",
        "",
        "1. 最可能停读的位置在哪里，为什么？",
        "2. 此刻理解了什么、误解了什么、仍期待什么？",
        "3. 本章兑现了什么，又新增了什么承诺？",
        "4. 修复怎样改善阅读效果，而不只是改措辞？",
    ]
    with open(brief_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
    return report_path, brief_path


def _compute_gate(report):
    scores = [
        float(item["score"]) for item in report.get("lenses") or []]
    reader_index = round(sum(scores) / max(1, len(scores)), 1)
    block_lenses = [
        item["id"] for item in report.get("lenses") or []
        if float(item["score"]) < 40]
    dropoff = report.get("dropoff") or {}
    if block_lenses or dropoff.get("risk") == "certain":
        return (
            reader_index, "block",
            ["致命镜头：%s" % (block_lenses or ["certain_dropoff"])])
    if reader_index < 60 or dropoff.get("risk") == "high":
        return (
            reader_index, "caution",
            ["Reader Panel Index=%s 或停读风险高" % reader_index])
    return reader_index, "proceed", [
        "Reader Panel Index=%s" % reader_index]


def validate_panel(path, finalize=True):
    report = _gov.load_yaml(path) or {}
    errors = []
    if report.get("schema") not in (
            "reader-panel@1.0.0", "reader-panel@2.0.0"):
        errors.append("unsupported reader panel schema")
    expected = {item[0] for item in _lenses()}
    found = {
        item.get("id") for item in report.get("lenses") or []
        if isinstance(item, dict)}
    missing = sorted(expected - found)
    if missing:
        errors.append("缺读者镜头：%s" % missing)
    source_text = None
    source_path = report.get("source")
    if source_path and os.path.isfile(source_path):
        with open(source_path, "r", encoding="utf-8") as handle:
            source_text = handle.read()
    for index, lens in enumerate(report.get("lenses") or [], 1):
        if not isinstance(lens, dict):
            errors.append("lens #%d 不是对象" % index)
            continue
        for field in REQUIRED_LENS_FIELDS:
            if lens.get(field) in (None, ""):
                errors.append("lens %s 缺 %s" % (lens.get("id"), field))
        try:
            score = float(lens.get("score"))
            confidence = float(lens.get("confidence"))
            if not 0 <= score <= 100:
                errors.append("lens %s score 越界" % lens.get("id"))
            if not 0 <= confidence <= 1:
                errors.append(
                    "lens %s confidence 越界" % lens.get("id"))
        except (TypeError, ValueError):
            errors.append(
                "lens %s score/confidence 非数值" % lens.get("id"))
        if source_text is not None:
            excerpt = lens.get("evidence_excerpt")
            if not excerpt or str(excerpt) not in source_text:
                errors.append(
                    "lens %s evidence_excerpt 无法定位"
                    % lens.get("id"))
    dropoff = report.get("dropoff") or {}
    if dropoff.get("risk") not in (
            "none", "low", "medium", "high", "certain"):
        errors.append("dropoff.risk 非法")
    for field in ("location", "reason"):
        if dropoff.get(field) in (None, ""):
            errors.append("dropoff 缺 %s" % field)
    if report.get("summary") in (None, ""):
        errors.append("缺 summary")
    if errors or not finalize:
        return not errors, errors, report
    reader_index, decision, reasons = _compute_gate(report)
    report["reader_index"] = reader_index
    report["gate"] = {"decision": decision, "reasons": reasons}
    report["validated_at"] = _now()
    _gov.dump_yaml(path, report)
    return True, [], report


def prepare_human_template(project_root, task_id):
    base = _panel_dir(project_root, task_id)
    os.makedirs(base, exist_ok=True)
    path = os.path.join(base, "human-input.template.yaml")
    participant = {
        "reader_id": None,
        "segment": None,
        "independent": True,
        "scores": {dimension: None for dimension in HUMAN_DIMENSIONS},
        "dropoff_location": None,
        "dropoff_reason": None,
        "most_engaging_location": None,
        "confusing_location": None,
        "freeform_comment": None,
    }
    _gov.dump_yaml(path, {
        "schema": "human-reader-input@2.0.0",
        "task_id": task_id,
        "collection_policy": {
            "minimum_participants": 3,
            "no_ai_impersonation": True,
            "independent_before_discussion": True,
        },
        "participants": [participant, participant, participant],
    })
    return path


def _legacy_score(item, dimension):
    return item.get(dimension)


def ingest_human(project_root, task_id, feedback_path):
    feedback = _gov.load_yaml(feedback_path) or {}
    participants = feedback.get("participants") or []
    strict_v2 = feedback.get("schema") == "human-reader-input@2.0.0"
    errors = []
    if len(participants) < 3:
        errors.append("真人反馈至少需要 3 名参与者")
    values = {dimension: [] for dimension in HUMAN_DIMENSIONS}
    dropoffs = []
    segments = set()
    for index, item in enumerate(participants, 1):
        if not isinstance(item, dict) or not item.get("reader_id"):
            errors.append("participant #%d 缺 reader_id" % index)
            continue
        if strict_v2 and item.get("independent") is not True:
            errors.append(
                "participant #%d 未确认独立作答" % index)
        segments.add(str(item.get("segment") or "unspecified"))
        scores = item.get("scores") or {}
        for dimension in HUMAN_DIMENSIONS:
            raw = (
                scores.get(dimension) if strict_v2
                else _legacy_score(item, dimension))
            # Legacy v1 only required its original three dimensions.
            if raw is None and not strict_v2 and dimension not in (
                    "completion_ratio", "recommend_score",
                    "payment_intent"):
                continue
            try:
                value = float(raw)
                if not 0 <= value <= 100:
                    raise ValueError()
                values[dimension].append(value)
            except (TypeError, ValueError):
                errors.append(
                    "participant #%d %s 非 0..100"
                    % (index, dimension))
        if item.get("dropoff_location"):
            dropoffs.append({
                "location": item.get("dropoff_location"),
                "reason": item.get("dropoff_reason"),
                "segment": item.get("segment"),
            })
    if strict_v2 and len(segments) < 2:
        errors.append("真人样本至少需要 2 个读者分群")
    if errors:
        raise ValueError("；".join(errors))

    means = {
        dimension: round(statistics.mean(rows), 1)
        for dimension, rows in values.items() if rows}
    critical = {
        dimension: score for dimension, score in means.items()
        if score < 60}
    continuation = means.get("continuation_intent")
    completion = means.get("completion_ratio", 0)
    decision = (
        "revise" if critical or completion < 70
        else "proceed" if continuation is None or continuation >= 65
        else "caution")
    report = {
        "schema": (
            "human-reader-feedback@2.0.0"
            if strict_v2 else "human-reader-feedback@1.0.0"),
        "task_id": task_id,
        "evidence_mode": "verified_human_input",
        "participant_count": len(participants),
        "segments": sorted(segments),
        "metrics": {
            **means,
            "dropoff_locations": dropoffs,
        },
        "critical_dimensions": critical,
        "milestone_decision": decision,
        "source_feedback": feedback_path,
        "ingested_at": _now(),
    }
    base = _panel_dir(project_root, task_id)
    os.makedirs(base, exist_ok=True)
    out = os.path.join(base, "human-feedback.yaml")
    _gov.dump_yaml(out, report)
    panel_path = os.path.join(base, "report.yaml")
    if os.path.isfile(panel_path):
        panel = _gov.load_yaml(panel_path) or {}
        panel["human_calibration"] = {
            "status": "provided",
            "report": os.path.relpath(
                out, project_root).replace("\\", "/"),
            "participant_count": len(participants),
            "milestone_decision": decision,
        }
        _gov.dump_yaml(panel_path, panel)

    findings = [{
        "category": "reader",
        "severity": "fail" if score < 40 else "warn",
        "observation": "真人读者维度 %s 均分 %.1f" % (
            dimension, score),
        "root_cause": "需结合停读位置和自由反馈复核",
        "recommended_fix": "下一轮写作前检查 %s，并在读者回归中复测"
        % dimension,
    } for dimension, score in critical.items()]
    if findings:
        try:
            import feedback_learning
            feedback_learning.capture_findings(
                project_root, task_id, findings,
                decision=decision, source_report=out)
        except Exception as exc:
            raise ValueError(
                "human feedback back-propagation failed: %s" % exc)
    return out, report


def main():
    parser = argparse.ArgumentParser(prog="reader-panel")
    sub = parser.add_subparsers(dest="action", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--project-root", required=True)
    prepare.add_argument("--task", required=True)
    prepare.add_argument("--chapter-ref")
    prepare.add_argument("--chapter-path")
    validate = sub.add_parser("validate")
    validate.add_argument("--report", required=True)
    human_template = sub.add_parser("prepare-human")
    human_template.add_argument("--project-root", required=True)
    human_template.add_argument("--task", required=True)
    human = sub.add_parser("ingest-human")
    human.add_argument("--project-root", required=True)
    human.add_argument("--task", required=True)
    human.add_argument("--feedback", required=True)
    arguments = parser.parse_args()

    if arguments.action == "prepare":
        report, brief = prepare_panel(
            arguments.project_root, arguments.task,
            arguments.chapter_ref, arguments.chapter_path)
        print("reader panel report: %s" % report)
        print("reader panel brief: %s" % brief)
    elif arguments.action == "validate":
        ok, errors, report = validate_panel(arguments.report)
        if not ok:
            for error in errors:
                print("FAIL: %s" % error)
            sys.exit(1)
        print("PASS: reader panel gate=%s index=%s" % (
            report["gate"]["decision"], report["reader_index"]))
    elif arguments.action == "prepare-human":
        print(prepare_human_template(
            arguments.project_root, arguments.task))
    else:
        out, report = ingest_human(
            arguments.project_root, arguments.task,
            arguments.feedback)
        print("human reader feedback: %s (participants=%d)" % (
            out, report["participant_count"]))


if __name__ == "__main__":
    main()
