# -*- coding: utf-8 -*-
"""Sequential multi-lens reader review and real-reader feedback calibration."""
import argparse
import datetime
import os
import statistics
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_ROOT = os.path.dirname(HERE)
for child in os.listdir(SCRIPTS_ROOT):
    path = os.path.join(SCRIPTS_ROOT, child)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

import _gov


PLATFORM_ROOT = os.path.dirname(SCRIPTS_ROOT)
REGISTRY_PATH = os.path.join(PLATFORM_ROOT, "registry", "readers.yaml")
DEFAULT_LENSES = [
    ("first_contact", "首次接触", "开篇理解成本、第一兴趣点与继续阅读意愿"),
    ("new_reader", "新读者", "背景知识不足时是否能理解人物、目标与局势"),
    ("genre_veteran", "类型老读者", "套路预期、创新度、可信度与审美疲劳"),
    ("plot_logic", "剧情逻辑", "因果、选择、代价、巧合与信息权限"),
    ("character_empathy", "人物共情", "动机、情绪、关系与角色能动性"),
    ("world_immersion", "世界沉浸", "设定呈现、出戏点、感官与规则边界"),
    ("pacing_fatigue", "节奏疲劳", "拖沓、跳跃、重复、长段负荷与停读风险"),
    ("prose_clarity", "文字清晰", "句段可读性、指代、画面、AI腔与赘述"),
    ("emotion_reward", "情绪兑现", "情绪波形、期待、奖励、爽点和余韵"),
    ("serial_retention", "追读留存", "章末承诺、下一章欲望与连续阅读动力"),
    ("commercial_value", "付费价值", "本章获得感、稀缺性与付费/推荐意愿"),
    ("safety_accessibility", "边界与可达性", "敏感内容、刻板印象、阅读障碍与受众边界"),
]
REQUIRED_FIELDS = (
    "score", "observation", "evidence_location", "reading_effect",
    "expectation", "recommended_fix", "confidence",
)


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _lenses():
    data = _gov.load_yaml(REGISTRY_PATH) or {}
    configured = data.get("reader_panel", {}).get("lenses") or []
    result = []
    for item in configured:
        if isinstance(item, dict) and item.get("id"):
            result.append((
                item["id"], item.get("name") or item["id"],
                item.get("focus") or "",
            ))
    return result or DEFAULT_LENSES


def _panel_dir(project_root, task_id):
    return os.path.join(
        project_root, "runtime", "reader-panels", "PANEL-%s" % task_id)


def prepare_panel(project_root, task_id, chapter_ref=None, chapter_path=None):
    base = _panel_dir(project_root, task_id)
    os.makedirs(base, exist_ok=True)
    report_path = os.path.join(base, "report.yaml")
    report = {
        "schema": "reader-panel@1.0.0",
        "panel_id": "PANEL-%s" % task_id,
        "task_id": task_id,
        "chapter_ref": chapter_ref,
        "evidence_mode": "ai_sequential_panel",
        "created_at": _now(),
        "source": chapter_path,
        "lenses": [{
            "id": lens_id,
            "name": name,
            "focus": focus,
            "score": None,
            "observation": None,
            "evidence_location": None,
            "reading_effect": None,
            "expectation": None,
            "recommended_fix": None,
            "confidence": None,
        } for lens_id, name, focus in _lenses()],
        "dropoff": {
            "risk": None,
            "location": None,
            "reason": None,
        },
        "summary": None,
        "reader_index": None,
        "gate": {"decision": None, "reasons": []},
        "human_calibration": {
            "status": "not_provided",
            "report": None,
        },
    }
    _gov.dump_yaml(report_path, report)
    brief_path = os.path.join(base, "brief.md")
    lines = [
        "# 读者面板 · %s" % task_id,
        "",
        "- 模式：同一主 Agent 串行切换观察镜头，不创建子 Agent。",
        "- 先无解释通读，再逐镜头复核；每个判断必须给正文位置与阅读影响。",
        "- AI 面板是预测证据，不能冒充真人反馈；真人数据另走 ingest-human。",
        "",
        "## 观察镜头",
        "",
    ]
    for index, (lens_id, name, focus) in enumerate(_lenses(), 1):
        lines.append("%d. `%s` %s：%s" % (index, lens_id, name, focus))
    lines += [
        "",
        "## 必答问题",
        "",
        "1. 我在哪一处最想停读，为什么？",
        "2. 我此刻理解了什么、误解了什么、仍在期待什么？",
        "3. 本章兑现了什么，新增了什么承诺？",
        "4. 修复建议如何改善阅读效果，而不是只改措辞？",
    ]
    with open(brief_path, "w", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")
    return report_path, brief_path


def _compute_gate(report):
    scores = [float(item["score"]) for item in report.get("lenses") or []]
    reader_index = round(sum(scores) / max(1, len(scores)), 1)
    reasons = []
    block_lenses = [
        item["id"] for item in report.get("lenses") or []
        if float(item["score"]) < 40
    ]
    dropoff = report.get("dropoff") or {}
    if block_lenses or dropoff.get("risk") == "certain":
        decision = "block"
        reasons.append("读者致命镜头: %s" % (block_lenses or ["certain_dropoff"]))
    elif reader_index < 60 or dropoff.get("risk") == "high":
        decision = "caution"
        reasons.append("Reader Panel Index=%s 或停读风险高" % reader_index)
    else:
        decision = "proceed"
        reasons.append("Reader Panel Index=%s" % reader_index)
    return reader_index, decision, reasons


def validate_panel(path, finalize=True):
    report = _gov.load_yaml(path) or {}
    errors = []
    if report.get("schema") != "reader-panel@1.0.0":
        errors.append("schema 非 reader-panel@1.0.0")
    expected = {item[0] for item in _lenses()}
    found = {
        item.get("id") for item in report.get("lenses") or []
        if isinstance(item, dict)
    }
    missing = sorted(expected - found)
    if missing:
        errors.append("缺读者镜头: %s" % missing)
    for index, lens in enumerate(report.get("lenses") or [], 1):
        if not isinstance(lens, dict):
            errors.append("lens #%d 不是对象" % index)
            continue
        for field in REQUIRED_FIELDS:
            if lens.get(field) in (None, ""):
                errors.append("lens %s 缺 %s" % (lens.get("id"), field))
        try:
            score = float(lens.get("score"))
            confidence = float(lens.get("confidence"))
            if not 0 <= score <= 100:
                errors.append("lens %s score 越界" % lens.get("id"))
            if not 0 <= confidence <= 1:
                errors.append("lens %s confidence 越界" % lens.get("id"))
        except (TypeError, ValueError):
            errors.append("lens %s score/confidence 非数值" % lens.get("id"))
    dropoff = report.get("dropoff") or {}
    if dropoff.get("risk") not in ("none", "low", "medium", "high", "certain"):
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


def ingest_human(project_root, task_id, feedback_path):
    feedback = _gov.load_yaml(feedback_path) or {}
    participants = feedback.get("participants") or []
    errors = []
    if len(participants) < 3:
        errors.append("真人反馈至少需要 3 名参与者，低于此值不得作为校准证据")
    completions = []
    recommendation = []
    payments = []
    dropoffs = []
    for index, item in enumerate(participants, 1):
        if not isinstance(item, dict) or not item.get("reader_id"):
            errors.append("participant #%d 缺 reader_id" % index)
            continue
        for field, bucket in (
                ("completion_ratio", completions),
                ("recommend_score", recommendation),
                ("payment_intent", payments)):
            try:
                value = float(item.get(field))
                if not 0 <= value <= 100:
                    raise ValueError()
                bucket.append(value)
            except (TypeError, ValueError):
                errors.append("participant #%d %s 非 0..100" % (index, field))
        if item.get("dropoff_location"):
            dropoffs.append(item.get("dropoff_location"))
    if errors:
        raise ValueError("；".join(errors))
    report = {
        "schema": "human-reader-feedback@1.0.0",
        "task_id": task_id,
        "participant_count": len(participants),
        "segments": sorted({
            str(item.get("segment") or "unspecified") for item in participants}),
        "metrics": {
            "completion_mean": round(statistics.mean(completions), 1),
            "recommend_mean": round(statistics.mean(recommendation), 1),
            "payment_intent_mean": round(statistics.mean(payments), 1),
            "dropoff_locations": dropoffs,
        },
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
            "report": os.path.relpath(out, project_root).replace("\\", "/"),
            "participant_count": len(participants),
        }
        _gov.dump_yaml(panel_path, panel)
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
    human = sub.add_parser("ingest-human")
    human.add_argument("--project-root", required=True)
    human.add_argument("--task", required=True)
    human.add_argument("--feedback", required=True)
    args = parser.parse_args()
    if args.action == "prepare":
        report, brief = prepare_panel(
            args.project_root, args.task, args.chapter_ref, args.chapter_path)
        print("✓ reader panel report: %s" % report)
        print("✓ reader panel brief: %s" % brief)
    elif args.action == "validate":
        ok, errors, report = validate_panel(args.report)
        if not ok:
            for error in errors:
                print("FAIL: %s" % error)
            sys.exit(1)
        print("PASS: reader panel gate=%s index=%s" % (
            report["gate"]["decision"], report["reader_index"]))
    else:
        out, report = ingest_human(
            args.project_root, args.task, args.feedback)
        print("✓ human reader feedback: %s (participants=%d)" %
              (out, report["participant_count"]))


if __name__ == "__main__":
    main()
