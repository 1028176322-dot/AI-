# -*- coding: utf-8 -*-
"""Resumable single-command chapter governance driver.

This driver advances only deterministic or already-evidenced work. It pauses
for prose, semantic review, revision, NKB disposition, human authorization or
outline decisions. Re-running ``platform chapter-flow run`` resumes from the
real task state; no stage list is kept only in conversational memory.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
for child in os.listdir(HERE):
    path = os.path.join(HERE, child)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

import _gov
import chapter_author
import diagnosis
import final_regression
import manifest_build
import nkb_validator
import project_layout
import publish_chapter
import reader_panel
import review_orchestrator
import style_orchestrator
import task_engine


ACTIVE_STATES = (
    "running", "claimed", "ready", "submitted",
    "reviewing", "passed", "backlog")
SEMANTIC_TYPES = {
    "chapter_plan",
    "plan_write",
    "chapter_fix",
    "continuity_fix",
    "style-revise",
    "fidelity-review",
    "style-quality-review",
    "chapter-apply-revision",
    "chapter-rollback-revision",
    "human_gate",
    "human-reader-validation",
    "outline_refresh",
}
# Planning still needs model judgment, but task ownership/lease transitions are
# deterministic.  Arm these stages before yielding the semantic work order so
# the AI never has to bypass chapter-flow merely to claim/start the task.
AUTO_ARM_SEMANTIC_TYPES = {
    "chapter_plan",
    "plan_write",
}
WORK_ORDER_INSTRUCTIONS = {
    "SEMANTIC_AUTHOR_REQUIRED": (
        "读取 request_file，按其中 response_contract 一次性填写 "
        "response_file；不得直接写 chapters/drafts。"),
    "SEMANTIC_REVIEW_REQUIRED": (
        "同一 AI 一次完成深度审查报告和 12 镜头读者面板；"
        "evidence_excerpt 可使用有序片段列表或省略号分隔的跨句片段。"),
    "SEMANTIC_DIAGNOSIS_REQUIRED": (
        "章节审查没有形成可复用的 clean clearance。填写 "
        "semantic-evidence.yaml；证据必须可在正文定位。"),
    "NKB_DISPOSITION_REQUIRED": (
        "逐条接受、拒绝或标冲突，并通过 knowledge-manager 受控更新 NKB；"
        "approved_event 已由任务谱系自动绑定，不得手工伪造。"),
    "SEMANTIC_STAGE_REQUIRED": (
        "此阶段需要当前主 AI 的语义判断；按 Task Packet 使用平台声明的该任务"
        "执行器完成提交/事件后，再重新运行 chapter-flow。不得手改 task 状态。"),
}


class FlowBlocked(RuntimeError):
    def __init__(self, code, message, work_order=None):
        super().__init__(message)
        self.code = code
        self.work_order = work_order or {}


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _chapter_id(value):
    match = re.search(r"(\d+)", str(value or ""))
    if not match:
        raise FlowBlocked(
            "CHAPTER_ID_INVALID", "Chapter must contain a number")
    return "CH-%03d" % int(match.group(1))


def _chapter_number(value):
    return int(_chapter_id(value).split("-")[1])


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _absolute(root, value):
    if not isinstance(value, str) or not value:
        return None
    return value if os.path.isabs(value) else os.path.join(root, value)


def _relative(root, path):
    return os.path.relpath(path, root).replace("\\", "/")


def _load(path):
    if not path or not os.path.isfile(path):
        return {}
    if path.lower().endswith(".json"):
        with open(path, "r", encoding="utf-8") as stream:
            return json.load(stream)
    return _gov.load_yaml(path) or {}


def _task_matches(task, chapter):
    """Match chapter identity without treating dates in task IDs as chapters."""
    expected = _chapter_number(chapter)
    chapter_ref = str(task.get("chapter_ref") or "")
    ref_match = re.search(
        r"(?:^|[/\\])CH-0*(\d+)(?:\.[A-Za-z0-9]+)?$", chapter_ref,
        re.IGNORECASE)
    if not ref_match:
        ref_match = re.fullmatch(
            r"CH-0*(\d+)", chapter_ref, re.IGNORECASE)
    if ref_match and int(ref_match.group(1)) == expected:
        return True

    title = str(task.get("title") or "")
    title_match = re.search(
        r"(?:CH-0*(\d+)|第\s*0*(\d+)\s*章)", title,
        re.IGNORECASE)
    if title_match:
        number = title_match.group(1) or title_match.group(2)
        if int(number) == expected:
            return True

    task_id = str(task.get("id") or "")
    id_match = re.search(
        r"(?:^|[-_])CH-?0*(\d+)(?:[-_]|$)", task_id,
        re.IGNORECASE)
    if id_match and int(id_match.group(1)) == expected:
        return True
    return False


def _tasks(root, chapter):
    rows = []
    for state in task_engine.STATES:
        directory = os.path.join(root, "tasks", state)
        if not os.path.isdir(directory):
            continue
        for name in os.listdir(directory):
            if not name.endswith((".yaml", ".yml")):
                continue
            body = _gov.load_yaml(os.path.join(directory, name)) or {}
            task = body.get("task") or {}
            if _task_matches(task, chapter):
                rows.append({
                    "state": state,
                    "task": task,
                    "path": os.path.join(directory, name),
                })
    return rows


def _frontier(root, chapter):
    rows = _tasks(root, chapter)
    for state in ACTIVE_STATES:
        candidates = [
            row for row in rows if row["state"] == state]
        if candidates:
            candidates.sort(key=lambda row: (
                str(row["task"].get("created") or ""),
                str(row["task"].get("id") or "")))
            return candidates[0], rows
    return None, rows


def _arm(root, row, agent, model):
    state = row["state"]
    task = row["task"]
    role = (
        (task.get("agent") or {}).get("required_role")
        or "task-scheduler")
    if state == "ready":
        task_engine.claim(
            root, task["id"], agent, role, model=model)
        state = "claimed"
    if state == "claimed":
        task_engine.start(
            root, task["id"], agent, role, model=model)
        state = "running"
    state, data = task_engine.load_task(root, task["id"])
    return {
        "state": state,
        "task": (data or {}).get("task") or task,
    }, role


def _lineage(root, task):
    values = style_orchestrator._collect_lineage_values(root, task)
    values.update(
        ((task.get("inputs") or {}).get("values") or {}))
    values.update(task.get("outputs") or {})
    return values


def _input_path(root, task, name, default=None):
    value = _lineage(root, task).get(name)
    path = _absolute(root, value)
    if path and os.path.isfile(path):
        return path
    fallback = _absolute(root, default)
    if fallback and os.path.isfile(fallback):
        return fallback
    return None


def _outline_path(root, task):
    direct = _input_path(root, task, "outline")
    if direct:
        return direct
    chapter = _chapter_id(task.get("chapter_ref") or task.get("id"))
    candidates = [
        os.path.join(
            root, "sources", "outline", "chapters",
            "PLAN-%03d.yaml" % _chapter_number(chapter)),
        os.path.join(
            root, "sources", "outline", "chapters",
            "%s.yaml" % chapter),
        os.path.join(
            root, "sources", "outline", "chapters",
            "PLAN-%03d.md" % _chapter_number(chapter)),
        os.path.join(
            root, "sources", "outline", "chapters",
            "%s.md" % chapter),
        os.path.join(root, "sources", "outline", "main.md"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def _write_checkpoint(root, chapter, body):
    directory = os.path.join(
        root, "runtime", "chapter-pipeline", chapter)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "state.json")
    payload = dict(body)
    payload.update({
        "schema": "chapter-flow-state@1.0.0",
        "chapter_id": chapter,
        "updated_at": _now(),
    })
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return path


def _work_order(
        root, chapter, task, code, instructions, files=None,
        task_state=None):
    directory = os.path.join(
        root, "runtime", "chapter-pipeline", chapter)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "NEXT_ACTION.json")
    body = {
        "schema": "chapter-flow-work-order@1.0.0",
        "chapter_id": chapter,
        "task_id": task.get("id"),
        "task_type": task.get("type"),
        "task_state": task_state,
        "required_role": (
            (task.get("agent") or {}).get("required_role")),
        "code": code,
        "instructions": WORK_ORDER_INSTRUCTIONS.get(code, instructions),
        "expected_outputs": task.get("expected_outputs") or [],
        "files": files or {},
        "resume_command": (
            "platform chapter-flow run --project-root <PROJECT_ROOT> "
            "--chapter %s" % chapter),
        "generated_at": _now(),
    }
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        json.dump(body, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return path, body


def _event(root, task, event, outputs, agent, role, model):
    return task_engine.finish_with_event(
        root, task["id"], event, outputs,
        checks={"chapter_flow": "pass"},
        actor=agent, role=role, model=model)


def _handle_author(root, row, chapter, agent, model):
    task = row["task"]
    output_root = os.path.join(
        root, "tasks", "running", task["id"], "outputs")
    response = os.path.join(output_root, "author-response.json")
    if row["state"] == "running" and os.path.isfile(response):
        return {
            "action": "AUTHOR_INGESTED",
            "result": chapter_author.ingest(
                root, task["id"], response,
                agent=agent, model_id=model, submit=True),
        }
    config = None
    try:
        config = chapter_author.validate_config(model)
    except chapter_author.AuthorExecutorError:
        pass
    if config and config.get("command_configured"):
        try:
            result = chapter_author.run(
                root, task["id"], agent=agent,
                model_id=model, submit=True)
            return {"action": "AUTHOR_EXECUTED", "result": result}
        except chapter_author.AuthorExecutorError as exc:
            raise FlowBlocked(
                "AUTHOR_EXECUTOR_FAILED", str(exc))
    exchange = chapter_author.begin_interactive(
        root, task["id"], agent=agent, model_id=model)
    work_path, work = _work_order(
        root, chapter, task, "SEMANTIC_AUTHOR_REQUIRED",
        "读取 request_file，按其中 response_contract 一次性填写 "
        "response_file；不得直接写 chapters/drafts。",
        {
            "request": exchange["request_file"],
            "response": exchange["response_file"],
        })
    raise FlowBlocked(
        "SEMANTIC_AUTHOR_REQUIRED",
        "Chapter prose requires the configured model adapter or "
        "one interactive response file",
        {"path": work_path, **work})


def _handle_review(root, row, chapter, agent, model):
    armed, role = _arm(root, row, agent, model)
    task = armed["task"]
    review_dir = os.path.join(
        root, "runtime", "reviews", "REVIEW-%s" % task["id"])
    report_path = os.path.join(review_dir, "report.yaml")
    panel_path = os.path.join(
        root, "runtime", "reader-panels",
        "PANEL-%s" % task["id"], "report.yaml")
    if not os.path.isfile(report_path):
        review_orchestrator.run_review(root, task["id"])
    report_ok, report_errors = review_orchestrator.validate_report(
        root, task["id"])
    panel_ok = False
    panel_errors = ["reader panel has not been completed"]
    if os.path.isfile(panel_path):
        panel_ok, panel_errors, _ = reader_panel.validate_panel(
            panel_path, finalize=False)
    if not report_ok or not panel_ok:
        work_path, work = _work_order(
            root, chapter, task, "SEMANTIC_REVIEW_REQUIRED",
            "同一 AI 一次完成深度审查报告和 12 镜头读者面板；"
            "evidence_excerpt 可使用有序片段列表或省略号分隔的跨句片段。",
            {
                "review_report": report_path,
                "reader_panel": panel_path,
                "review_errors": report_errors,
                "reader_errors": panel_errors,
            })
        raise FlowBlocked(
            "SEMANTIC_REVIEW_REQUIRED",
            "Review evidence is incomplete",
            {"path": work_path, **work})
    report = _gov.load_yaml(report_path) or {}
    verdict = report.get("verdict")
    decision = (
        "pass" if verdict in ("pass", "pass_with_fixes")
        else "fail")
    state, result = task_engine.review(
        root, task["id"], decision,
        findings=report.get("findings") or [],
        reviewer=agent, role=role, model=model,
        outputs={"review_report": _relative(root, report_path)})
    return {
        "action": "REVIEW_CONSUMED",
        "state": state,
        "result": result,
    }


def _handle_manifest(root, row, agent, model):
    armed, role = _arm(root, row, agent, model)
    task = armed["task"]
    draft = _input_path(root, task, "chapter_draft")
    nkb = _input_path(
        root, task, "nkb_snapshot", "NKB/manifest.yaml")
    outline = _outline_path(root, task)
    missing = [
        name for name, path in (
            ("chapter_draft", draft),
            ("nkb_snapshot", nkb),
            ("outline", outline)) if not path]
    if missing:
        raise FlowBlocked(
            "DETERMINISTIC_INPUT_MISSING",
            "Manifest inputs missing: %s" % ", ".join(missing))
    result = manifest_build.build_manifest(
        _chapter_id(task.get("chapter_ref")),
        task.get("revision_cycle_id") or "RC-%s" % task["id"],
        task["id"],
        open(draft, "r", encoding="utf-8").read(),
        nkb_snapshot=_load(nkb),
        outline_text=open(outline, "r", encoding="utf-8").read(),
        model_id=model)
    persisted = manifest_build.persist(
        result, root, _chapter_id(task.get("chapter_ref")),
        task.get("revision_cycle_id") or "RC-%s" % task["id"])
    event = (
        "on_complete" if result["status"] == "MANIFEST_READY"
        else "on_conflict")
    output_name = (
        "protected_manifest"
        if event == "on_complete" else "conflict_report")
    routed = _event(
        root, task, event,
        {output_name: _relative(root, persisted["path"])},
        agent, role, model)
    return {
        "action": "MANIFEST_BUILT",
        "status": result["status"],
        "result": routed,
    }


def _handle_diagnosis(root, row, chapter, agent, model):
    armed, role = _arm(root, row, agent, model)
    task = armed["task"]
    draft = _input_path(root, task, "chapter_draft")
    manifest_path = _input_path(root, task, "protected_manifest")
    guidance_path = _input_path(root, task, "style_guidance")
    review_path = _input_path(root, task, "chapter_review_report")
    missing = [
        name for name, path in (
            ("chapter_draft", draft),
            ("protected_manifest", manifest_path),
            ("style_guidance", guidance_path)) if not path]
    if missing:
        raise FlowBlocked(
            "DETERMINISTIC_INPUT_MISSING",
            "Diagnosis inputs missing: %s" % ", ".join(missing))
    evidence_path = os.path.join(
        root, "tasks", "running", task["id"],
        "outputs", "semantic-evidence.yaml")
    evidence = _load(evidence_path).get("evidence", []) \
        if os.path.isfile(evidence_path) else []
    review = _load(review_path)
    clearance = diagnosis.clearance_from_review(
        review, _sha256_file(review_path) if review_path else "")
    if not evidence and not clearance:
        work_path, work = _work_order(
            root, chapter, task, "SEMANTIC_DIAGNOSIS_REQUIRED",
            "章节审查没有形成可复用的 clean clearance。填写 "
            "semantic-evidence.yaml；证据必须可在正文定位。",
            {"semantic_evidence": evidence_path})
        raise FlowBlocked(
            "SEMANTIC_DIAGNOSIS_REQUIRED",
            "Style diagnosis requires semantic evidence",
            {"path": work_path, **work})
    report = diagnosis.ai_diagnose(
        _chapter_id(task.get("chapter_ref")),
        task.get("revision_cycle_id") or "RC-%s" % task["id"],
        task["id"], open(draft, "r", encoding="utf-8").read(),
        protected_manifest_sha256=manifest_build.manifest_sha256(
            _load(manifest_path)),
        semantic_evidence=evidence,
        style_guidance=_load(guidance_path),
        require_semantic_evidence=True,
        semantic_clearance=clearance)
    path = diagnosis.persist(
        report, root, _chapter_id(task.get("chapter_ref")),
        task["id"])
    event = (
        "on_issues" if report["has_issues"]
        else "on_warning" if report["only_warnings"]
        else "on_clean")
    routed = _event(
        root, task, event,
        {"diagnosis_report": _relative(root, path)},
        agent, role, model)
    return {
        "action": "DIAGNOSIS_COMPLETED",
        "event": event,
        "result": routed,
    }


def _nkb_revision(snapshot):
    return manifest_build._nkb_revision(snapshot)


def _handle_regression(root, row, agent, model):
    armed, role = _arm(root, row, agent, model)
    task = armed["task"]
    draft = _input_path(root, task, "chapter_draft")
    manifest_path = _input_path(root, task, "protected_manifest")
    guidance_path = _input_path(root, task, "style_guidance")
    review_path = _input_path(root, task, "chapter_review_report")
    nkb_path = _input_path(
        root, task, "nkb_snapshot", "NKB/manifest.yaml")
    outline = _outline_path(root, task)
    paths = {
        "chapter_draft": draft,
        "protected_manifest": manifest_path,
        "style_guidance": guidance_path,
        "chapter_review_report": review_path,
        "nkb_snapshot": nkb_path,
        "outline": outline,
    }
    missing = [name for name, path in paths.items() if not path]
    if missing:
        raise FlowBlocked(
            "DETERMINISTIC_INPUT_MISSING",
            "Final regression inputs missing: %s" % ", ".join(missing))
    snapshot = _load(nkb_path)
    guidance = _load(guidance_path)
    guidance_hash = guidance.get("style_guidance_sha256")
    if not guidance_hash:
        raise FlowBlocked(
            "STYLE_GUIDANCE_BINDING_MISSING",
            "style guidance does not declare style_guidance_sha256")
    mode = (
        ((task.get("inputs") or {}).get("values") or {}).get(
            "final_regression_mode")
        or "baseline")
    if mode != "baseline":
        raise FlowBlocked(
            "POST_APPLY_REGRESSION_REQUIRES_EVIDENCE",
            "Post-apply regression remains semantic/evidence-bound")
    report = final_regression.run_regression(
        "baseline", _chapter_id(task.get("chapter_ref")),
        task.get("revision_cycle_id") or "RC-%s" % task["id"],
        task["id"],
        draft_text=open(draft, "r", encoding="utf-8").read(),
        nkb_revision=_nkb_revision(snapshot),
        nkb_snapshot_sha256=hashlib.sha256(json.dumps(
            snapshot, ensure_ascii=False, sort_keys=True
        ).encode("utf-8")).hexdigest(),
        protected_manifest_sha256=manifest_build.manifest_sha256(
            _load(manifest_path)),
        outline_sha256=_sha256_file(outline),
        style_guidance_sha256=guidance_hash,
        chapter_review_report_sha256=_sha256_file(review_path),
        require_report_bindings=True)
    path = final_regression.persist(
        report, root, _chapter_id(task.get("chapter_ref")),
        task.get("revision_cycle_id") or "RC-%s" % task["id"],
        task["id"])
    post_nkb_sync = bool(_lineage(root, task).get("post_nkb_sync"))
    event = (
        ("on_pass_post_nkb" if post_nkb_sync else "on_pass")
        if report.get("result") == "FINAL_PASSED"
        else "on_fail_baseline")
    routed = _event(
        root, task, event,
        {"regression_result": _relative(root, path)},
        agent, role, model)
    return {
        "action": "FINAL_REGRESSION_COMPLETED",
        "event": event,
        "result": routed,
    }


def _handle_nkb_update(root, row, chapter, agent, model):
    armed, _ = _arm(root, row, agent, model)
    task = armed["task"]
    output_root = os.path.join(
        root, "tasks", "running", task["id"], "outputs")
    declared = task.get("outputs") or {}
    expected = {
        "nkb_change": (
            _absolute(root, declared.get("nkb_change"))
            or os.path.join(output_root, "nkb-change.yaml")),
        "operation_manifest": (
            _absolute(root, declared.get("operation_manifest"))
            or os.path.join(output_root, "operation-manifest.yaml")),
        "nkb_snapshot_after": (
            _absolute(root, declared.get("nkb_snapshot_after"))
            or os.path.join(root, "NKB", "manifest.yaml")),
    }
    if all(os.path.isfile(path) for path in expected.values()):
        state, successor = task_engine.submit(
            root, task["id"], _relative(
                root, expected["nkb_change"]),
            outputs={
                name: _relative(root, path)
                for name, path in expected.items()},
            checks={"approved_event": "pass",
                    "candidate_disposition": "pass"},
            agent=agent, role="knowledge-manager", model=model)
        return {
            "action": "NKB_UPDATE_CONSUMED",
            "state": state,
            "successor": successor,
        }
    work_path, work = _work_order(
        root, chapter, task, "NKB_DISPOSITION_REQUIRED",
        "逐条接受、拒绝或标冲突，并通过 knowledge-manager 受控更新 NKB；"
        "approved_event 已由任务谱系自动绑定，不得手工伪造。",
        {name: path for name, path in expected.items()})
    raise FlowBlocked(
        "NKB_DISPOSITION_REQUIRED",
        "NKB candidate disposition is the next semantic step",
        {"path": work_path, **work})


def _handle_nkb_sync(root, row, agent, model):
    armed, role = _arm(root, row, agent, model)
    task = armed["task"]
    values = _lineage(root, task)
    operation = _absolute(
        root, values.get("operation_manifest"))
    manifest_path = _input_path(
        root, task, "nkb_snapshot_after", "NKB/manifest.yaml")
    if not operation or not os.path.isfile(operation) or not manifest_path:
        raise FlowBlocked(
            "NKB_SYNC_INPUT_MISSING",
            "NKB sync inputs are incomplete")
    report = nkb_validator.validate_project(root)
    decision = (report.get("gate") or {}).get("decision")
    snapshot = _load(manifest_path)
    revision = _nkb_revision(snapshot)
    snapshot_hash = hashlib.sha256(json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True
    ).encode("utf-8")).hexdigest()
    output_root = os.path.join(
        root, "tasks", "running", task["id"], "outputs")
    os.makedirs(output_root, exist_ok=True)
    validation_path = os.path.join(
        output_root, "validation-report.yaml")
    proof_path = os.path.join(output_root, "nkb-sync-proof.yaml")
    validation_passed = decision == "proceed"
    validation = {
        "task_id": task["id"],
        "status": "PASS" if validation_passed else "FAIL",
        "checks": report.get("findings") or [],
        "nkb_revision": revision,
        "nkb_snapshot_sha256": snapshot_hash,
        "created_at": _now(),
    }
    proof = {
        "task_id": task["id"],
        "status": (
            "NKB_SYNC_PASSED"
            if validation_passed else "NKB_SYNC_FAILED"),
        "nkb_revision": revision,
        "nkb_snapshot_sha256": snapshot_hash,
        "operation_manifest_sha256": _sha256_file(operation),
        "created_at": _now(),
    }
    _gov.dump_yaml(validation_path, validation)
    _gov.dump_yaml(proof_path, proof)
    if not validation_passed:
        raise FlowBlocked(
            "NKB_SYNC_FAILED",
            "Canonical NKB validation is blocked",
            {"validation_report": validation_path})
    outputs = {
        "nkb_sync_proof": _relative(root, proof_path),
        "validation_report": _relative(root, validation_path),
    }
    task_engine.submit(
        root, task["id"], outputs["validation_report"],
        outputs=outputs, checks={"canonical_validation": "pass"},
        agent=agent, role=role, model=model)
    state, result = task_engine.review(
        root, task["id"], "pass",
        reviewer=agent, role=role, model=model,
        outputs=outputs)
    return {
        "action": "NKB_SYNC_COMPLETED",
        "state": state,
        "result": result,
    }


def _handle_publish(root, row, agent, model):
    task = row["task"]
    entry = publish_chapter.publish(
        root, task["id"], role="publish_service",
        agent=agent, model=model)
    return {"action": "CHAPTER_PUBLISHED", "entry": entry}


def _advance(root, row, chapter, agent, model):
    task_type = row["task"].get("type")
    if task_type == "chapter_write":
        return _handle_author(root, row, chapter, agent, model)
    if task_type == "chapter_review":
        return _handle_review(root, row, chapter, agent, model)
    if task_type == "protected-manifest-build":
        return _handle_manifest(root, row, agent, model)
    if task_type == "ai-diagnose":
        return _handle_diagnosis(
            root, row, chapter, agent, model)
    if task_type == "final-regression":
        return _handle_regression(root, row, agent, model)
    if task_type == "nkb_update":
        return _handle_nkb_update(
            root, row, chapter, agent, model)
    if task_type == "nkb_sync":
        return _handle_nkb_sync(root, row, agent, model)
    if task_type == "chapter_publish":
        return _handle_publish(root, row, agent, model)
    if task_type in SEMANTIC_TYPES:
        if (
                task_type in AUTO_ARM_SEMANTIC_TYPES
                and row["state"] in ("ready", "claimed")):
            row, _ = _arm(root, row, agent, model)
        task = row["task"]
        work_path, work = _work_order(
            root, chapter, task, "SEMANTIC_STAGE_REQUIRED",
            "此阶段需要当前主 AI 的语义判断；完成 Task Packet 的"
            " expected_outputs 后重新运行 chapter-flow。",
            {"task_packet": os.path.join(
                root, "runtime", "task-packets", task["id"])},
            task_state=row["state"])
        raise FlowBlocked(
            "SEMANTIC_STAGE_REQUIRED",
            "Semantic task cannot be fabricated by a script",
            {"path": work_path, **work})
    raise FlowBlocked(
        "UNSUPPORTED_TASK_TYPE",
        "Chapter flow has no executor for %s" % task_type)


def run_flow(root, chapter, agent, model, max_steps=32):
    root = os.path.abspath(root)
    chapter = _chapter_id(chapter)
    if not project_layout.is_style_strict(root):
        raise FlowBlocked(
            "STRICT_V2_REQUIRED",
            "chapter-flow requires a strict-v2 project")
    history = []
    for _ in range(max_steps):
        frontier, rows = _frontier(root, chapter)
        if frontier is None:
            published = [
                row for row in rows
                if row["task"].get("type") == "chapter_publish"
                and row["state"] == "completed"]
            outline_refreshed = [
                row for row in rows
                if row["task"].get("type") == "outline_refresh"
                and row["state"] == "completed"]
            if published and not outline_refreshed:
                raise FlowBlocked(
                    "OUTLINE_REFRESH_INCOMPLETE",
                    "Chapter publish exists but outline_refresh is missing "
                    "or not completed")
            decision = (
                "COMPLETE"
                if published and outline_refreshed
                else "NO_ACTIVE_TASK")
            checkpoint = _write_checkpoint(root, chapter, {
                "decision": decision,
                "history": history,
                "tasks": [{
                    "id": row["task"].get("id"),
                    "type": row["task"].get("type"),
                    "state": row["state"],
                } for row in rows],
            })
            return {
                "decision": decision,
                "chapter_id": chapter,
                "history": history,
                "checkpoint": checkpoint,
            }
        if frontier["state"] == "backlog":
            raise FlowBlocked(
                "WAITING_DEPENDENCY",
                "Next chapter task is waiting for its dependency",
                {"task_id": frontier["task"].get("id")})
        result = _advance(
            root, frontier, chapter, agent, model)
        history.append({
            "task_id": frontier["task"].get("id"),
            "task_type": frontier["task"].get("type"),
            **result,
        })
        _write_checkpoint(root, chapter, {
            "decision": "RUNNING",
            "history": history,
        })
    raise FlowBlocked(
        "STEP_LIMIT_REACHED",
        "Chapter flow exceeded max deterministic steps",
        {"max_steps": max_steps})


def status(root, chapter):
    chapter = _chapter_id(chapter)
    frontier, rows = _frontier(os.path.abspath(root), chapter)
    return {
        "decision": "STATUS",
        "chapter_id": chapter,
        "frontier": ({
            "state": frontier["state"],
            "task_id": frontier["task"].get("id"),
            "task_type": frontier["task"].get("type"),
        } if frontier else None),
        "tasks": [{
            "state": row["state"],
            "task_id": row["task"].get("id"),
            "task_type": row["task"].get("type"),
        } for row in rows],
    }


def main():
    parser = argparse.ArgumentParser(prog="chapter-flow")
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("run", "status"):
        command = sub.add_parser(action)
        command.add_argument("--project-root", required=True)
        command.add_argument("--chapter", required=True)
        if action == "run":
            command.add_argument(
                "--agent", default="chapter-flow")
            command.add_argument("--model", default=None)
            command.add_argument("--max-steps", type=int, default=32)
    args = parser.parse_args()
    try:
        if args.action == "status":
            result = status(args.project_root, args.chapter)
        else:
            result = run_flow(
                args.project_root, args.chapter,
                args.agent, args.model, args.max_steps)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except FlowBlocked as exc:
        result = {
            "decision": "PAUSED" if exc.code.startswith(
                ("SEMANTIC_", "NKB_DISPOSITION")) else "BLOCK",
            "code": exc.code,
            "message": str(exc),
            "work_order": exc.work_order,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(2 if result["decision"] == "BLOCK" else 10)
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({
            "decision": "BLOCK",
            "code": "CHAPTER_FLOW_EXECUTOR_ERROR",
            "message": str(exc),
        }, ensure_ascii=False, indent=2))
        raise SystemExit(2)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
