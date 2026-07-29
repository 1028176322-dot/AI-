# -*- coding: utf-8 -*-
"""Scoped and context-bound authorization for human_gate tasks."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import hmac
import json
import os
import secrets
import sys

import _gov


SECRET_ENV = "AI_CREATIVE_HUMAN_APPROVAL_SECRET"
READER_GATE_KIND = "human_reader_milestone"


class HumanGateAuthorizationError(RuntimeError):
    """A human-gate grant is missing, stale, untrusted or out of scope."""


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def _canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")


def _sha256_bytes(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _secret():
    value = os.environ.get(SECRET_ENV, "")
    if len(value.encode("utf-8")) < 32:
        raise HumanGateAuthorizationError(
            "%s is missing or shorter than 32 bytes" % SECRET_ENV)
    return value.encode("utf-8")


def _signature(payload):
    return hmac.new(
        _secret(), _canonical(payload), hashlib.sha256).hexdigest()


def _absolute(root, value):
    if not isinstance(value, str) or not value:
        return None
    return value if os.path.isabs(value) else os.path.join(root, value)


def _project_scope(project_root):
    project_file = os.path.join(project_root, "project.yaml")
    body = _gov.load_yaml(project_file) if os.path.isfile(
        project_file) else {}
    project_id = (
        (body.get("project") or {}).get("id")
        if isinstance(body, dict) else None)
    project_id = project_id or (
        body.get("id") if isinstance(body, dict) else None)
    if project_id:
        return "project-id:%s" % project_id
    return "project-path:%s" % os.path.normcase(
        os.path.abspath(project_root))


def gate_context(task, project_root):
    values = ((task.get("inputs") or {}).get("values") or {})
    value = values.get("gate_context")
    if isinstance(value, dict):
        return value, _sha256_bytes(value)
    path = _absolute(project_root, value)
    if path and os.path.isfile(path):
        return _gov.load_yaml(path) or {}, _sha256_file(path)
    raise HumanGateAuthorizationError(
        "human_gate task has no resolvable gate_context")


def _load_decision(project_root, outputs):
    path = _absolute(project_root, (outputs or {}).get("gate_decision"))
    if not path or not os.path.isfile(path):
        raise HumanGateAuthorizationError("gate_decision file missing")
    body = _gov.load_yaml(path) or {}
    if body.get("decision") not in ("pass", "revise", "reject"):
        raise HumanGateAuthorizationError(
            "gate_decision.decision must be pass/revise/reject")
    if not body.get("gate_context_sha256"):
        raise HumanGateAuthorizationError(
            "gate_decision.gate_context_sha256 missing")
    return body


def _verify_reader_evidence(project_root, outputs):
    path = _absolute(
        project_root, (outputs or {}).get("human_reader_report"))
    if not path or not os.path.isfile(path):
        raise HumanGateAuthorizationError(
            "human reader milestone requires human_reader_report")
    body = _gov.load_yaml(path) or {}
    if body.get("evidence_mode") != "verified_human_input":
        raise HumanGateAuthorizationError(
            "human_reader_report is not verified human input")
    if int(body.get("participant_count") or 0) < 3:
        raise HumanGateAuthorizationError(
            "human_reader_report requires at least 3 participants")
    if len(body.get("segments") or []) < 2:
        raise HumanGateAuthorizationError(
            "human_reader_report requires at least 2 reader segments")


def verify_task_authorization(project_root, task, outputs, event):
    if task.get("type") != "human_gate":
        return None
    context, context_hash = gate_context(task, project_root)
    decision = _load_decision(project_root, outputs)
    if decision["gate_context_sha256"] != context_hash:
        raise HumanGateAuthorizationError(
            "gate decision context hash does not match current task")
    values = ((task.get("inputs") or {}).get("values") or {})
    grant_value = (
        values.get("human_authorization")
        or decision.get("human_authorization"))
    grant_path = _absolute(project_root, grant_value)
    if not grant_path or not os.path.isfile(grant_path):
        raise HumanGateAuthorizationError(
            "signed human_authorization grant missing")
    grant_doc = _gov.load_yaml(grant_path) or {}
    grant = grant_doc.get("human_authorization") or {}
    signature = grant.get("signature_sha256")
    payload = dict(grant)
    payload.pop("signature_sha256", None)
    if not signature or not hmac.compare_digest(
            signature, _signature(payload)):
        raise HumanGateAuthorizationError(
            "human authorization signature is invalid")
    try:
        expiry = datetime.datetime.fromisoformat(
            str(payload.get("expires_at")))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError):
        raise HumanGateAuthorizationError(
            "human authorization expiry is invalid")
    if expiry <= _now():
        raise HumanGateAuthorizationError(
            "human authorization has expired")
    if payload.get("project_scope") != _project_scope(project_root):
        raise HumanGateAuthorizationError(
            "human authorization belongs to another project")
    bindings = payload.get("bindings") or []
    if not any(
            item.get("task_id") == task.get("id")
            and item.get("gate_context_sha256") == context_hash
            for item in bindings):
        raise HumanGateAuthorizationError(
            "human authorization is not scoped to this task/context")
    if payload.get("decision") != decision.get("decision"):
        raise HumanGateAuthorizationError(
            "human authorization decision mismatch")
    expected_event = (
        "on_pass" if decision.get("decision") == "pass"
        else "on_complete")
    if event != expected_event:
        raise HumanGateAuthorizationError(
            "human authorization does not permit event %s" % event)
    if context.get("kind") == READER_GATE_KIND:
        if len(bindings) != 1:
            raise HumanGateAuthorizationError(
                "human reader milestones cannot use batch authorization")
        _verify_reader_evidence(project_root, outputs)
    return {
        "authorization_id": payload.get("authorization_id"),
        "authorized_by": payload.get("authorized_by"),
        "gate_context_sha256": context_hash,
    }


def _task_binding(project_root, task_id):
    import task_engine

    state, data = task_engine.load_task(project_root, task_id)
    if state is None:
        raise HumanGateAuthorizationError(
            "task not found: %s" % task_id)
    task = data.get("task") or {}
    if task.get("type") != "human_gate":
        raise HumanGateAuthorizationError(
            "%s is not a human_gate task" % task_id)
    context, context_hash = gate_context(task, project_root)
    return state, data, context, {
        "task_id": task_id,
        "gate_context_sha256": context_hash,
    }


def authorize(project_root, task_ids, decision, authorized_by,
              reason, expires_minutes=60):
    if decision not in ("pass", "revise", "reject"):
        raise HumanGateAuthorizationError(
            "decision must be pass/revise/reject")
    if not str(authorized_by or "").strip():
        raise HumanGateAuthorizationError("authorized_by is required")
    if not str(reason or "").strip():
        raise HumanGateAuthorizationError("reason is required")
    if expires_minutes < 1 or expires_minutes > 1440:
        raise HumanGateAuthorizationError(
            "expires_minutes must be 1..1440")
    if not task_ids or len(set(task_ids)) != len(task_ids):
        raise HumanGateAuthorizationError(
            "authorization requires unique explicit task ids")
    rows = [_task_binding(project_root, item) for item in task_ids]
    if any(row[2].get("kind") == READER_GATE_KIND for row in rows):
        if len(rows) != 1:
            raise HumanGateAuthorizationError(
                "human reader milestones cannot be batch-authorized")
    now = _now()
    authorization_id = "HGA-%s-%s" % (
        now.strftime("%Y%m%d%H%M%S"),
        secrets.token_hex(4).upper())
    payload = {
        "schema": "human-gate-authorization@1.0.0",
        "authorization_id": authorization_id,
        "authorized_by": authorized_by,
        "issuer_type": "verified_human_surface",
        "project_scope": _project_scope(project_root),
        "decision": decision,
        "reason": reason,
        "issued_at": now.isoformat(timespec="seconds"),
        "expires_at": (
            now + datetime.timedelta(minutes=expires_minutes)
        ).isoformat(timespec="seconds"),
        "bindings": [row[3] for row in rows],
        "nonce": secrets.token_hex(16),
    }
    payload["signature_sha256"] = _signature(payload)
    relative = "operations/grants/human/%s.yaml" % authorization_id
    path = os.path.join(project_root, relative)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _gov.dump_yaml(path, {"human_authorization": payload})

    import task_engine
    for state, data, _, _ in rows:
        task = data["task"]
        values = task.setdefault("inputs", {}).setdefault("values", {})
        values["human_authorization"] = relative
        task_engine._move(project_root, task["id"], data, state)
        task_engine._ensure_task_packet(project_root, task["id"])
    return path, payload


def main():
    parser = argparse.ArgumentParser(prog="platform human-gate")
    sub = parser.add_subparsers(dest="action", required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--project-root", required=True)
    inspect.add_argument("--task", required=True)
    approve = sub.add_parser("authorize")
    approve.add_argument("--project-root", required=True)
    approve.add_argument("--task", action="append", required=True)
    approve.add_argument(
        "--decision", choices=["pass", "revise", "reject"],
        required=True)
    approve.add_argument("--authorized-by", required=True)
    approve.add_argument("--reason", required=True)
    approve.add_argument("--expires-minutes", type=int, default=60)
    arguments = parser.parse_args()
    try:
        if arguments.action == "inspect":
            _, _, context, binding = _task_binding(
                arguments.project_root, arguments.task)
            result = {"context": context, "binding": binding}
        else:
            path, payload = authorize(
                arguments.project_root, arguments.task,
                arguments.decision, arguments.authorized_by,
                arguments.reason, arguments.expires_minutes)
            result = {
                "authorization": path,
                "authorization_id": payload["authorization_id"],
                "bindings": payload["bindings"],
                "expires_at": payload["expires_at"],
            }
    except (HumanGateAuthorizationError, OSError, ValueError) as exc:
        print("REJECTED: %s" % exc)
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
