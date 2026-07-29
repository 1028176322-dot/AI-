# -*- coding: utf-8 -*-
"""Deterministic event orchestration for the governed style pipeline.

The task template is the only authority for emitted events and successor
types.  This module validates the running task, output contracts, schema
shape, hashes, lease/session and single-agent policy before it closes the
source task and creates idempotent successors.
"""
from __future__ import annotations

import datetime
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
for _name in os.listdir(SCRIPTS):
    _path = os.path.join(SCRIPTS, _name)
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _gov
import audit_log
import session_bootstrap
import task_templates as TT


SUPPORTED_EVENTS = {
    "on_complete",
    "on_clean",
    "on_warning",
    "on_issues",
    "on_pass",
    "on_pass_post_nkb",
    "on_fail",
    "on_rolled_back",
    "on_conflict",
    "on_fail_baseline",
    "on_fail_post_apply",
}

OUTPUT_SCHEMAS = {
    "protected_manifest": "protected-manifest.schema.yaml",
    "diagnosis_report": "diagnosis.schema.yaml",
    "revision_result": "revision-result.schema.yaml",
    "fidelity_report": "fidelity-report.schema.yaml",
    "quality_report": "style-quality-report.schema.yaml",
    "apply_result": "chapter-apply-result.schema.yaml",
    "rollback_result": "chapter-rollback-result.schema.yaml",
    "regression_result": "final-regression-result.schema.yaml",
    "style_guidance": "style-guidance.schema.yaml",
    "nkb_sync_proof": "nkb-sync-proof.schema.yaml",
    "validation_report": "nkb-validation-report.schema.yaml",
    "review_report": "../../contracts/review-report.schema.yaml",
}

STATE_BY_EVENT = {
    ("protected-manifest-build", "on_complete"): "MANIFEST_READY",
    ("protected-manifest-build", "on_conflict"): "MANIFEST_CONFLICT",
    ("ai-diagnose", "on_clean"): "DIAGNOSED_CLEAN",
    ("ai-diagnose", "on_warning"): "DIAGNOSED_WARNING",
    ("ai-diagnose", "on_issues"): "DIAGNOSED_ISSUES",
    ("style-revise", "on_complete"): "CANDIDATE_CREATED",
    ("fidelity-review", "on_pass"): "FIDELITY_PASSED",
    ("fidelity-review", "on_fail"): "FIDELITY_FAILED",
    ("style-quality-review", "on_pass"): "QUALITY_PASSED",
    ("style-quality-review", "on_fail"): "QUALITY_FAILED",
    ("chapter-apply-revision", "on_complete"): "APPLIED",
    ("final-regression", "on_pass"): "FINAL_PASSED",
    ("final-regression", "on_pass_post_nkb"): "FINAL_PASSED",
    ("final-regression", "on_fail_baseline"): "CHAPTER_FIX_REQUIRED",
    ("final-regression", "on_fail_post_apply"): "ROLLBACK_READY",
    ("chapter-rollback-revision", "on_rolled_back"): "ROLLED_BACK",
    ("chapter-rollback-revision", "on_conflict"): "ROLLBACK_CONFLICT",
}

ENTRY_STATE_BY_TASK = {
    "protected-manifest-build": "MANIFEST_BUILDING",
    "ai-diagnose": "MANIFEST_READY",
    "style-revise": "REVISION_REQUESTED",
    "fidelity-review": "CANDIDATE_CREATED",
    "style-quality-review": "FIDELITY_PASSED",
    "chapter-apply-revision": "APPLY_READY",
    "final-regression": "FINAL_CHECK_READY",
    "chapter-rollback-revision": "ROLLBACK_READY",
    "nkb_update": "FINAL_PASSED",
    "nkb_sync": "NKB_SYNC_REQUIRED",
    "chapter_publish": "PUBLISH_READY",
}


class StyleEventError(RuntimeError):
    """A style event failed a governance or evidence check."""


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _absolute(root, value):
    if not isinstance(value, str) or not value:
        return None
    if value.startswith("inline:") or value.startswith("not-applicable:"):
        return None
    return value if os.path.isabs(value) else os.path.join(root, value)


def _schema_dir():
    return os.path.join(
        os.path.dirname(os.path.dirname(HERE)),
        "core", "learning", "schemas")


def _validate_schema(output_name, path):
    schema_name = OUTPUT_SCHEMAS.get(output_name)
    if not schema_name:
        return
    schema_path = os.path.join(_schema_dir(), schema_name)
    if not os.path.isfile(schema_path):
        raise StyleEventError(
            "schema not registered for %s: %s" % (output_name, schema_path))
    if not path.lower().endswith((".yaml", ".yml", ".json")):
        raise StyleEventError(
            "%s must be a YAML/JSON evidence artifact" % output_name)
    if path.lower().endswith(".json"):
        import json
        with open(path, "r", encoding="utf-8") as stream:
            payload = json.load(stream)
    else:
        payload = _gov.load_yaml(path) or {}
    spec = _gov.load_yaml(schema_path) or {}
    contract_required = ((spec.get("report") or {}).get("required") or [])
    contract_missing = [
        name for name in contract_required
        if name not in payload or payload.get(name) in (None, "")]
    if contract_missing:
        raise StyleEventError(
            "%s schema missing required fields: %s" %
            (output_name, ", ".join(contract_missing)))
    missing = []
    for field in spec.get("fields") or []:
        if not field.get("required"):
            continue
        name = field.get("name")
        if name not in payload or payload.get(name) in (None, ""):
            missing.append(name)
    if missing:
        raise StyleEventError(
            "%s schema missing required fields: %s" %
            (output_name, ", ".join(missing)))
    for field in spec.get("fields") or []:
        if field.get("type") != "enum":
            continue
        name = field.get("name")
        if name in payload and payload[name] not in (field.get("enum") or []):
            raise StyleEventError(
                "%s.%s has invalid enum value %r" %
                (output_name, name, payload[name]))


def _lease_valid(task, actor):
    owner = task.get("owner")
    if owner and actor not in (owner, "task-system", "orchestrator"):
        raise StyleEventError(
            "actor %s does not own task lease (%s)" % (actor, owner))
    raw = task.get("lease_expire")
    if raw:
        try:
            expiry = datetime.datetime.fromisoformat(str(raw))
        except ValueError:
            raise StyleEventError("invalid lease_expire: %s" % raw)
        if expiry < datetime.datetime.now():
            raise StyleEventError("task lease expired at %s" % raw)


def _single_agent_valid(template):
    policy = template.get("execution_policy") or {}
    if policy.get("subagent_allowed") not in (False, "false", None):
        return False
    if policy.get("delegation_allowed") not in (False, "false", None):
        return False
    if policy.get("parallel_execution_allowed") not in (
            False, "false", None):
        return False
    return int(policy.get("max_agents", 1)) == 1


def _event_contract(template, event):
    contract = (template.get("event_contracts") or {}).get(event) or {}
    required = contract.get("required_outputs")
    if required is None:
        allowed = template.get("allowed_outputs") or []
        required = [name for name in allowed if name not in (
            "conflict_report", "findings")]
    bindings = contract.get("required_bindings") or []
    return list(required), list(bindings)


def _validate_outputs(root, template, event, outputs):
    outputs = dict(outputs or {})
    allowed = set(template.get("allowed_outputs") or [])
    unknown = sorted(set(outputs) - allowed)
    if unknown:
        raise StyleEventError(
            "outputs not declared by template: %s" % ", ".join(unknown))
    required, bindings = _event_contract(template, event)
    missing = [name for name in required if outputs.get(name) in (
        None, "", False)]
    if missing:
        raise StyleEventError(
            "event %s missing outputs: %s" % (event, ", ".join(missing)))
    hashes = {}
    payloads = {}
    for name, value in outputs.items():
        path = _absolute(root, value)
        if not path or not os.path.isfile(path):
            raise StyleEventError(
                "output file missing for %s: %r" % (name, value))
        _validate_schema(name, path)
        hashes[name + "_sha256"] = _sha256(path)
        if path.lower().endswith((".yaml", ".yml")):
            payloads[name] = _gov.load_yaml(path) or {}
        elif path.lower().endswith(".json"):
            import json
            with open(path, "r", encoding="utf-8") as stream:
                payloads[name] = json.load(stream)
    combined = {}
    for payload in payloads.values():
        if isinstance(payload, dict):
            combined.update(payload)
    absent_bindings = [
        name for name in bindings
        if combined.get(name) in (None, "", False)
    ]
    if absent_bindings:
        raise StyleEventError(
            "event %s missing hash bindings: %s" %
            (event, ", ".join(absent_bindings)))
    return outputs, hashes, combined


def _collect_lineage_values(root, task, max_nodes=64):
    import task_engine as TE

    result = {}
    queue = [task]
    seen = set()
    while queue and len(seen) < max_nodes:
        current = queue.pop(0)
        current_id = current.get("id")
        if current_id in seen:
            continue
        if current_id:
            seen.add(current_id)
        for source in (
                ((current.get("inputs") or {}).get("values") or {}),
                (current.get("outputs") or {})):
            if not isinstance(source, dict):
                continue
            for key, value in source.items():
                if value not in (None, "", False):
                    result.setdefault(key, value)
                if not isinstance(value, str):
                    continue
                path = value if os.path.isabs(value) else os.path.join(
                    root, value)
                if not os.path.isfile(path):
                    continue
                try:
                    if path.lower().endswith((".yaml", ".yml")):
                        evidence = _gov.load_yaml(path) or {}
                    elif path.lower().endswith(".json"):
                        import json
                        with open(
                                path, "r", encoding="utf-8") as stream:
                            evidence = json.load(stream)
                    else:
                        evidence = {}
                except Exception:
                    evidence = {}
                if isinstance(evidence, dict):
                    for evidence_key, evidence_value in evidence.items():
                        if evidence_value not in (None, "", False):
                            result.setdefault(
                                evidence_key, evidence_value)
        artifact = current.get("artifact")
        if artifact and current.get("type") in (
                "chapter_write", "chapter_fix", "continuity_fix"):
            result.setdefault("chapter_draft", artifact)
        for dep in current.get("dependencies") or []:
            _, data = TE.load_task(root, dep)
            parent = (data or {}).get("task") or {}
            if parent:
                queue.append(parent)
    return result


def _successor_id(source_id, event, target, index):
    event_name = event[3:] if event.startswith("on_") else event
    suffix = target.upper().replace("_", "-")
    return "%s-%s-%s-%02d" % (
        source_id, event_name.upper().replace("_", "-"), suffix, index)


def _approved_review_event(root, source_task, max_nodes=64):
    """Resolve the reviewed chapter event from the dependency lineage."""
    import task_engine as TE

    queue = [source_task]
    seen = set()
    while queue and len(seen) < max_nodes:
        current = queue.pop(0)
        current_id = current.get("id")
        if not current_id or current_id in seen:
            continue
        seen.add(current_id)
        if current.get("type") == "chapter_review":
            history = current.get("style_event_history") or []
            approved = any(
                item.get("event") == "on_pass"
                for item in history if isinstance(item, dict))
            if approved:
                return current_id
        for dependency in current.get("dependencies") or []:
            _, data = TE.load_task(root, dependency)
            parent = (data or {}).get("task") or {}
            if parent:
                queue.append(parent)
    return None


def _create_successors(
        root, source_task, event, outputs, hashes, evidence,
        actor, model):
    import task_engine as TE

    created = []
    inherited = _collect_lineage_values(root, source_task)
    inherited.update(outputs)
    inherited.update(hashes)
    inherited.update({
        key: value for key, value in evidence.items()
        if key.endswith("_sha256") or key in (
            "revision_cycle_id", "source_draft_sha256",
            "nkb_revision", "final_regression_mode",
            "chapter_review_report_sha256")
    })
    if (source_task.get("type") == "nkb_sync"
            and event == "on_pass"):
        # NKB update may have advanced the canonical snapshot. The successor
        # tail must bind the final snapshot before publish.
        inherited["post_nkb_sync"] = True
        if inherited.get("nkb_snapshot_after"):
            inherited["nkb_snapshot"] = inherited["nkb_snapshot_after"]
    inherited["source_task"] = source_task.get("id")
    inherited["source_event"] = event
    inherited.setdefault(
        "revision_cycle_id",
        source_task.get("revision_cycle_id")
        or "RC-%s" % source_task.get("id"))
    if source_task.get("type") == "chapter_review":
        inherited.setdefault("approved_event", source_task.get("id"))
        if outputs.get("review_report"):
            inherited.setdefault(
                "chapter_review_report", outputs["review_report"])
    if event == "on_pass" and source_task.get("type") == (
            "style-quality-review"):
        inherited.setdefault("apply_readiness", {
            "source_task": source_task.get("id"),
            "decision": "APPLY_READY",
        })
    if event == "on_fail_post_apply":
        inherited.setdefault("rollback_readiness", {
            "source_task": source_task.get("id"),
            "decision": "ROLLBACK_READY",
        })

    for index, target in enumerate(TT.next_types(
            source_task.get("type"), event), 1):
        if target == "nkb_update" and not inherited.get(
                "approved_event"):
            approved_event = _approved_review_event(
                root, source_task)
            if not approved_event:
                raise StyleEventError(
                    "nkb_update successor requires an approved "
                    "chapter_review event in lineage")
            inherited["approved_event"] = approved_event
        task_id = (
            TE.stable_publish_task_id(source_task)
            if target == "chapter_publish" else None)
        task_id = task_id or _successor_id(
            source_task.get("id"), event, target, index)
        existing_state, _ = TE.load_task(root, task_id)
        if existing_state:
            created.append(task_id)
            continue
        target_template = TT.load(target)
        required = target_template.get("required_inputs") or []
        values = {
            name: inherited[name] for name in required
            if inherited.get(name) not in (None, "", False)
        }
        values.update({
            "source_task": source_task.get("id"),
            "source_event": event,
            "revision_cycle_id": inherited["revision_cycle_id"],
        })
        if inherited.get("post_nkb_sync"):
            values["post_nkb_sync"] = True
        if target == "human_gate":
            values["gate_context"] = {
                "schema": "human-gate-context@1.0.0",
                "kind": "quality_exception",
                "source_task": source_task.get("id"),
                "source_type": source_task.get("type"),
                "source_event": event,
                "chapter_ref": source_task.get("chapter_ref"),
                "source_output_hashes": hashes,
            }
        if target == "final-regression":
            values["final_regression_mode"] = (
                "post_apply"
                if source_task.get("type") == "chapter-apply-revision"
                else "baseline")
        for name in (
                "style_guidance_sha256",
                "protected_manifest_sha256",
                "source_draft_sha256",
                "chapter_review_report_sha256"):
            if inherited.get(name):
                values[name] = inherited[name]
        successor = {
            "id": task_id,
            "version": 1,
            "project": source_task.get("project"),
            "type": target,
            "title": "%s %s 后继 %s" % (
                source_task.get("id"), event, target),
            "priority": source_task.get("priority", "high"),
            "goal": source_task.get("goal"),
            "chapter_ref": source_task.get("chapter_ref"),
            "conversation_request_id":
                source_task.get("conversation_request_id"),
            "revision_cycle_id": inherited["revision_cycle_id"],
            "style_state": ENTRY_STATE_BY_TASK.get(target),
            "source_task": source_task.get("id"),
            "source_event": event,
            "dependencies": [source_task.get("id")],
            "inputs": {"required": list(required), "values": values},
            "expected_outputs":
                target_template.get("allowed_outputs") or [],
            "acceptance": {
                "criteria": ["按 %s 模板及事件契约完成" % target],
            },
            "permissions": target_template.get("permissions") or {},
            "agent": {
                "required_role":
                    target_template.get("required_role")
                    or "task-scheduler",
            },
            "execution_policy":
                target_template.get("execution_policy") or {},
        }
        if target == "chapter_publish":
            draft = inherited.get("chapter_draft")
            if not draft:
                raise StyleEventError(
                    "chapter_publish successor requires chapter_draft")
            successor["publish_target"] = TE.resolve_canonical_target(
                draft, root)
            successor["knowledge_snapshot"] = (
                inherited.get("nkb_snapshot_after")
                or inherited.get("nkb_revision"))
            values["publish_authorization"] = (
                "operations/grants/%s.yaml" % task_id)
        TE.create_task(
            root, successor, model=model, author="style-orchestrator")
        if target == "chapter_publish":
            TE._grant_for_publish(
                root, task_id, successor["publish_target"])
            # Grant is created after the task so persist its reference and
            # rebuild the packet with every required input now resolvable.
            _, created_data = TE.load_task(root, task_id)
            created_task = (created_data or {}).get("task") or {}
            created_task.setdefault(
                "inputs", {}).setdefault("values", {}).update(values)
            TE._move(root, task_id, created_data, "ready")
            TE._ensure_task_packet(root, task_id)
        created.append(task_id)
    return created


def finish_with_event(
        project_root, task_id, event, outputs, checks=None,
        actor="unknown", role=None, model="unknown"):
    """Validate and consume one template-declared style event.

    Returns a stable result dictionary.  Replaying the same event is
    idempotent and never creates a second successor.
    """
    import task_engine as TE

    if event not in SUPPORTED_EVENTS:
        raise StyleEventError("unsupported style event: %s" % event)
    state, data = TE.load_task(project_root, task_id)
    if state is None:
        raise StyleEventError("task not found: %s" % task_id)
    task = data.get("task") or {}
    template = TT.load(task.get("type"))
    declared = template.get("next_tasks") or {}
    if event not in declared:
        raise StyleEventError(
            "%s is not declared by %s template" %
            (event, task.get("type")))

    history = task.get("style_event_history") or []
    for item in history:
        if item.get("event") == event:
            return {
                "task_id": task_id,
                "event": event,
                "style_state": item.get("style_state"),
                "successors": item.get("successors") or [],
                "idempotent": True,
            }
    if history:
        raise StyleEventError(
            "task already emitted terminal event %s" %
            history[-1].get("event"))
    if state not in ("running", "submitted", "reviewing", "passed"):
        raise StyleEventError(
            "event requires an active task, current state=%s" % state)

    session = session_bootstrap.require_session(project_root, agent=actor)
    session_body = session.get("session") or {}
    _lease_valid(task, actor)
    expected_role = (
        (task.get("agent") or {}).get("required_role")
        or template.get("required_role"))
    if role and expected_role and role not in (
            expected_role, "task-scheduler", "orchestrator"):
        raise StyleEventError(
            "role mismatch: expected %s, got %s" %
            (expected_role, role))
    if not _single_agent_valid(template):
        raise StyleEventError(
            "single-agent execution policy is not enforceable")
    failed_checks = [
        name for name, value in (checks or {}).items()
        if value not in ("pass", True)
    ]
    if failed_checks:
        raise StyleEventError(
            "event checks failed: %s" % ", ".join(failed_checks))

    if task.get("type") == "human_gate":
        try:
            import human_gate_auth
            human_gate_auth.verify_task_authorization(
                project_root, task, outputs, event)
        except Exception as exc:
            raise StyleEventError(
                "human gate authorization failed: %s" % exc)

    clean_outputs, hashes, evidence = _validate_outputs(
        project_root, template, event, outputs)
    task["outputs"] = clean_outputs
    task["output_hashes"] = hashes
    task["artifact"] = next(iter(clean_outputs.values()), None)
    task["submission"] = {
        "checks": checks or {},
        "at": _now(),
        "session_id": session_body.get("id"),
    }
    style_state = STATE_BY_EVENT.get(
        (task.get("type"), event), event[3:].upper())
    task["style_state"] = style_state

    # Close first so successor dependencies are deterministically ready.
    TE._move(project_root, task_id, data, "completed")
    successors = _create_successors(
        project_root, task, event, clean_outputs, hashes, evidence,
        actor, model)
    task["style_event_history"] = [{
        "event": event,
        "style_state": style_state,
        "successors": successors,
        "actor": actor,
        "role": role or expected_role,
        "session_id": session_body.get("id"),
        "emitted_at": _now(),
        "output_hashes": hashes,
    }]
    TE._move(project_root, task_id, data, "completed")
    audit_log.record(
        project_root, "task_style_event", agent=actor,
        role=role or expected_role, model=model, task_id=task_id,
        result="success",
        detail="%s state=%s successors=%s" %
        (event, style_state, successors))
    return {
        "task_id": task_id,
        "event": event,
        "style_state": style_state,
        "successors": successors,
        "idempotent": False,
        "output_hashes": hashes,
    }
