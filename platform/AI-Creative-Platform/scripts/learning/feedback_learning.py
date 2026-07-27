# -*- coding: utf-8 -*-
"""Turn review findings into project-scoped writing and regression guidance."""
import argparse
import datetime
import hashlib
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


CATEGORY_GUIDANCE = {
    "hard_consistency": "写作前核对相关 NKB、时间线和实体状态，正文不得用推测替代事实。",
    "continuity": "写作前读取上一章交接与相关事件，明确承接点、状态变化和未完成动作。",
    "character": "每个关键行为必须能由角色目标、认知、关系和压力解释。",
    "logic": "在章纲中写明因果链、必要条件和失败代价，避免结果先于原因。",
    "terminology": "写作与修订均使用 Terminology 唯一标准名，禁用同义漂移。",
    "style": "控制重复句式、解释性旁白和抽象总结，以可观察行动承载信息。",
    "pacing": "标记场景目标、阻力、转折和退出点，删除不改变状态的段落。",
    "worldbuilding": "设定信息只在人物行动需要时释放，并保持规则、代价和边界一致。",
    "emotion": "情绪变化必须由事件触发，并通过动作、感知和选择体现。",
    "dialogue": "对白必须推进目标、关系或信息，且保持角色可辨识度。",
    "narrative": "保持 POV、时序与信息权限稳定，切换必须有明确锚点。",
    "conflict": "冲突应产生选择、代价和不可逆变化，避免只有表面争执。",
    "reader": "从读者困惑、疲劳、期待、兑现和沉浸角度重写问题段。",
    "other": "把问题转成可在下一次写作前执行的具体检查动作。",
}


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _load(path, default=None):
    try:
        value = _gov.load_yaml(path)
        return value if isinstance(value, dict) else (default or {})
    except Exception:
        return default or {}


def _signature(finding):
    category = str(finding.get("category") or "other")
    observation = str(
        finding.get("root_cause") or finding.get("reasoning")
        or finding.get("observation") or finding.get("detail") or "")
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", observation.lower())[:160]
    digest = hashlib.sha256(
        ("%s|%s" % (category, normalized)).encode("utf-8")).hexdigest()[:10]
    return "FB-%s" % digest.upper()


def _chapter_for_task(project_root, task_id):
    try:
        import task_engine
        _, data = task_engine.load_task(project_root, task_id)
        task = (data or {}).get("task") or {}
        if task.get("chapter_ref"):
            return task.get("chapter_ref")
        dependency = (task.get("dependencies") or [None])[0]
        if dependency:
            _, dep_data = task_engine.load_task(project_root, dependency)
            return ((dep_data or {}).get("task") or {}).get("chapter_ref")
    except Exception:
        pass
    return None


def capture_findings(project_root, task_id, findings, decision="unknown",
                     source_report=None):
    findings = [item for item in (findings or []) if isinstance(item, dict)]
    if not findings:
        return None
    memory_dir = os.path.join(
        project_root, "memory", "project", "review-feedback")
    runtime_dir = os.path.join(project_root, "runtime", "learning")
    analysis_dir = os.path.join(project_root, "analysis", "learning")
    for directory in (memory_dir, runtime_dir, analysis_dir):
        os.makedirs(directory, exist_ok=True)
    ledger_path = os.path.join(memory_dir, "feedback-ledger.yaml")
    ledger = _load(ledger_path, {
        "schema": "review-feedback-ledger@1.0.0",
        "project": os.path.basename(project_root),
        "records": [],
    })
    records = {
        item.get("id"): item for item in ledger.get("records") or []
        if isinstance(item, dict) and item.get("id")
    }
    chapter_ref = _chapter_for_task(project_root, task_id)
    touched = []
    for finding in findings:
        record_id = _signature(finding)
        category = str(finding.get("category") or "other")
        record = records.get(record_id) or {
            "id": record_id,
            "category": category,
            "problem": finding.get("observation") or finding.get("detail"),
            "root_cause": finding.get("root_cause") or finding.get("reasoning"),
            "writing_guardrail": CATEGORY_GUIDANCE.get(
                category, CATEGORY_GUIDANCE["other"]),
            "review_regression_check": finding.get("recommended_fix")
            or "复审时定位同类问题是否再次出现。",
            "occurrences": 0,
            "chapters": [],
            "tasks": [],
            "severities": [],
            "status": "active",
        }
        record["occurrences"] = int(record.get("occurrences") or 0) + 1
        if chapter_ref and chapter_ref not in record["chapters"]:
            record["chapters"].append(chapter_ref)
        if task_id not in record["tasks"]:
            record["tasks"].append(task_id)
        severity = finding.get("severity") or "warn"
        if severity not in record["severities"]:
            record["severities"].append(severity)
        record["last_seen"] = _now()
        record["promotion_candidate"] = (
            record["occurrences"] >= 2
            and len(record["chapters"]) >= 2
        )
        records[record_id] = record
        touched.append(record_id)
    ledger["records"] = sorted(
        records.values(),
        key=lambda item: (-int(item.get("occurrences") or 0), item.get("id", "")),
    )
    ledger["updated_at"] = _now()
    _gov.dump_yaml(ledger_path, ledger)

    active = [
        item for item in ledger["records"]
        if item.get("status") == "active"
    ]
    writing_path = os.path.join(runtime_dir, "writing-guidance.yaml")
    regression_path = os.path.join(runtime_dir, "review-regression.yaml")
    _gov.dump_yaml(writing_path, {
        "schema": "writing-guidance@1.0.0",
        "generated_at": _now(),
        "source": os.path.relpath(ledger_path, project_root).replace("\\", "/"),
        "guardrails": [{
            "id": item["id"],
            "category": item["category"],
            "instruction": item["writing_guardrail"],
            "occurrences": item["occurrences"],
            "chapters": item["chapters"],
        } for item in active[:30]],
    })
    _gov.dump_yaml(regression_path, {
        "schema": "review-regression@1.0.0",
        "generated_at": _now(),
        "checks": [{
            "id": item["id"],
            "category": item["category"],
            "check": item["review_regression_check"],
            "severity_history": item["severities"],
            "must_regress": True,
        } for item in active[:30]],
    })
    report_id = "FEEDBACK-%s-%s" % (
        datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
        _signature({"category": task_id, "observation": decision})[-4:],
    )
    report_path = os.path.join(analysis_dir, report_id + ".yaml")
    _gov.dump_yaml(report_path, {
        "schema": "feedback-learning-report@1.0.0",
        "task_id": task_id,
        "decision": decision,
        "source_report": source_report,
        "captured_findings": len(findings),
        "records_touched": touched,
        "writing_guidance": os.path.relpath(
            writing_path, project_root).replace("\\", "/"),
        "review_regression": os.path.relpath(
            regression_path, project_root).replace("\\", "/"),
        "generated_at": _now(),
    })
    return {
        "ledger": ledger_path,
        "writing_guidance": writing_path,
        "review_regression": regression_path,
        "report": report_path,
    }


def ingest_report(project_root, report_path):
    report = _load(report_path)
    return capture_findings(
        project_root,
        str(report.get("task_id") or report.get("review_id") or "review-import"),
        report.get("findings") or [],
        report.get("verdict") or "unknown",
        source_report=report_path,
    )


def validate_ledger(path):
    data = _load(path)
    errors = []
    if data.get("schema") != "review-feedback-ledger@1.0.0":
        errors.append("schema 非 review-feedback-ledger@1.0.0")
    for index, record in enumerate(data.get("records") or [], 1):
        for field in ("id", "category", "problem", "writing_guardrail",
                      "review_regression_check", "occurrences", "status"):
            if record.get(field) in (None, ""):
                errors.append("record #%d 缺 %s" % (index, field))
    return not errors, errors


def main():
    parser = argparse.ArgumentParser(prog="feedback")
    sub = parser.add_subparsers(dest="action", required=True)
    ingest = sub.add_parser("ingest")
    ingest.add_argument("--project-root", required=True)
    ingest.add_argument("--report", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--ledger", required=True)
    args = parser.parse_args()
    if args.action == "ingest":
        result = ingest_report(args.project_root, args.report)
        if not result:
            print("# 报告没有可反补 finding")
            return
        print("✓ feedback ledger: %s" % result["ledger"])
        print("✓ writing guidance: %s" % result["writing_guidance"])
        print("✓ review regression: %s" % result["review_regression"])
    else:
        ok, errors = validate_ledger(args.ledger)
        if not ok:
            for error in errors:
                print("FAIL: %s" % error)
            sys.exit(1)
        print("PASS: feedback ledger")


if __name__ == "__main__":
    main()
