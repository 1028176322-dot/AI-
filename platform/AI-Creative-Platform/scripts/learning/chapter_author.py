# -*- coding: utf-8 -*-
"""Governed chapter author executor.

The platform owns orchestration and evidence validation; an environment-owned
model adapter owns semantic generation.  The adapter command receives one JSON
request on stdin and must return one JSON response on stdout.  No shell is
used, no prose is accepted from stderr, and an unconfigured adapter fails
closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_ROOT = os.path.dirname(HERE)
for _child in os.listdir(SCRIPTS_ROOT):
    _path = os.path.join(SCRIPTS_ROOT, _child)
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

import _gov
import audit_log
import model_router
import session_bootstrap
import task_engine
import task_packet


REQUIRED_RESPONSE_FIELDS = (
    "chapter_draft",
    "self_check",
    "writing_strategy_evidence",
    "candidate_facts",
    "handoff",
)
PACKET_FILES = (
    "task.yaml",
    "input-index.yaml",
    "context.md",
    "constraints.md",
    "output-contract.yaml",
    "execution-manifest.yaml",
)


class AuthorExecutorError(RuntimeError):
    """The governed author executor could not safely produce a draft."""


def _platform_root():
    return os.path.dirname(os.path.dirname(HERE))


def _config_path():
    return os.path.join(
        _platform_root(), "registry", "author-executors.yaml")


def _load_config(model_id):
    body = _gov.load_yaml(_config_path()) or {}
    default = body.get("default") or {}
    models = body.get("models")
    # The platform's dependency-free YAML reader intentionally supports only
    # flow lists; an empty flow mapping may therefore arrive as the literal
    # string "{}".  Treat any non-mapping model table as empty and fail closed
    # later if no adapter command exists.
    if not isinstance(models, dict):
        models = {}
    model_config = models.get(model_id) or {}
    if not isinstance(default, dict) or not isinstance(model_config, dict):
        raise AuthorExecutorError(
            "author executor registry entries must be mappings")
    merged = dict(default)
    merged.update(model_config)
    if merged.get("transport") != "command":
        raise AuthorExecutorError(
            "author executor transport must be command")
    return merged


def _command_from_config(config):
    raw = None
    env_name = config.get("command_env")
    if env_name:
        raw = os.environ.get(str(env_name))
    if raw:
        try:
            command = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AuthorExecutorError(
                "%s must contain a JSON command array: %s"
                % (env_name, exc))
    else:
        command = config.get("command")
    if not isinstance(command, list) or not command:
        raise AuthorExecutorError(
            "author model adapter is not configured; set %s to a JSON "
            "command array" % (env_name or "registry command"))
    if any(not isinstance(part, str) or not part for part in command):
        raise AuthorExecutorError(
            "author adapter command must be a non-empty string array")
    return command


def _chapter_id(task):
    match = re.search(
        r"(\d+)", str(task.get("chapter_ref") or task.get("id") or ""))
    if not match:
        raise AuthorExecutorError("chapter_write task has no chapter number")
    return "CH-%03d" % int(match.group(1))


def _read_packet(project_root, task_id):
    packet_root = os.path.join(
        project_root, "runtime", "task-packets", task_id)
    if not all(os.path.isfile(os.path.join(packet_root, name))
               for name in PACKET_FILES):
        task_packet.build_packet(project_root, task_id)
    result = {}
    for name in PACKET_FILES:
        path = os.path.join(packet_root, name)
        if not os.path.isfile(path):
            raise AuthorExecutorError(
                "Task Packet incomplete: %s" % name)
        with open(path, "r", encoding="utf-8") as stream:
            result[name] = stream.read()
    return packet_root, result


def build_request(project_root, task_id, model_id=None):
    state, data = task_engine.load_task(project_root, task_id)
    if state is None:
        raise AuthorExecutorError("task not found: %s" % task_id)
    task = data.get("task") or {}
    if task.get("type") != "chapter_write":
        raise AuthorExecutorError(
            "author executor only accepts chapter_write tasks")
    packet_root, packet = _read_packet(project_root, task_id)
    chapter_id = _chapter_id(task)
    if not model_id:
        resolution = model_router.resolve(
            _platform_root(), role="writer",
            task_type="chapter_write", capability="chapter_write",
            quality_tier=3)
        if not resolution:
            raise AuthorExecutorError(
                "model router cannot resolve chapter_write")
        model_id = resolution["model_id"]
    return {
        "schema": "chapter-author-request@1.0.0",
        "task_id": task_id,
        "project_root": os.path.abspath(project_root),
        "chapter_id": chapter_id,
        "chapter_ref": task.get("chapter_ref"),
        "model_id": model_id,
        "packet_root": packet_root,
        "task_packet": packet,
        "response_contract": {
            "format": "json",
            "required_fields": list(REQUIRED_RESPONSE_FIELDS),
            "chapter_draft": "complete chapter prose string",
            "self_check": (
                "mapping with constitution/planning/context = pass"),
            "writing_strategy_evidence":
                "mapping rooted at writing_strategy_evidence",
            "candidate_facts": "mapping rooted at knowledge_delta",
            "handoff": "mapping rooted at nkb_handoff",
        },
        "hard_rules": [
            "obey every resolved Task Packet input and constraint",
            "return original prose, never copy reference source wording",
            "do not claim human feedback or bypass a gate",
            "return JSON only",
        ],
    }


def _invoke(command, request, timeout_seconds):
    try:
        completed = subprocess.run(
            command,
            input=json.dumps(request, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=timeout_seconds,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AuthorExecutorError(
            "author adapter execution failed: %s" % exc)
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip()[:1000]
        raise AuthorExecutorError(
            "author adapter returned exit=%d: %s"
            % (completed.returncode, detail))
    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AuthorExecutorError(
            "author adapter stdout is not one JSON object: %s" % exc)
    if not isinstance(response, dict):
        raise AuthorExecutorError(
            "author adapter response must be a JSON object")
    return response


def _request_hash(request):
    encoded = json.dumps(
        request, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _invoke_or_reuse(
        command, request, timeout_seconds, output_root,
        regenerate=False):
    request_sha256 = _request_hash(request)
    response_path = os.path.join(
        output_root, "author-response.json")
    hash_path = os.path.join(
        output_root, "author-request.sha256")
    if not regenerate and os.path.isfile(
            response_path) and os.path.isfile(hash_path):
        with open(hash_path, "r", encoding="utf-8") as stream:
            cached_hash = stream.read().strip()
        if cached_hash == request_sha256:
            with open(response_path, "r", encoding="utf-8") as stream:
                response = json.load(stream)
            _validate_response(response)
            return response, True
    response = _invoke(command, request, timeout_seconds)
    _validate_response(response)
    os.makedirs(output_root, exist_ok=True)
    with open(
            response_path, "w", encoding="utf-8",
            newline="\n") as stream:
        json.dump(
            response, stream, ensure_ascii=False,
            sort_keys=True, indent=2)
        stream.write("\n")
    with open(hash_path, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(request_sha256 + "\n")
    return response, False


def _validate_response(response):
    missing = [
        name for name in REQUIRED_RESPONSE_FIELDS
        if response.get(name) in (None, "", False)
    ]
    if missing:
        raise AuthorExecutorError(
            "author response missing fields: %s" % ", ".join(missing))
    if not isinstance(response["chapter_draft"], str):
        raise AuthorExecutorError("chapter_draft must be a string")
    if not response["chapter_draft"].strip():
        raise AuthorExecutorError("chapter_draft must contain prose")
    for name in REQUIRED_RESPONSE_FIELDS[1:]:
        if not isinstance(response[name], dict):
            raise AuthorExecutorError("%s must be a mapping" % name)
    self_check = response["self_check"]
    missing_checks = [
        name for name in ("constitution", "planning", "context")
        if self_check.get(name) not in ("pass", True)
    ]
    if missing_checks:
        raise AuthorExecutorError(
            "self_check must pass: %s" % ", ".join(missing_checks))
    if "writing_strategy_evidence" not in response[
            "writing_strategy_evidence"]:
        raise AuthorExecutorError(
            "writing_strategy_evidence root is missing")
    if "knowledge_delta" not in response["candidate_facts"]:
        raise AuthorExecutorError("candidate_facts.knowledge_delta missing")
    if "nkb_handoff" not in response["handoff"]:
        raise AuthorExecutorError("handoff.nkb_handoff missing")


def _dump_output(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if path.lower().endswith(".txt"):
        with open(path, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(value)
        return
    _gov.dump_yaml(path, value)


def _arm_task(project_root, task_id, agent, model_id):
    state, data = task_engine.load_task(project_root, task_id)
    owner = ((data or {}).get("task") or {}).get("owner")
    if state in ("claimed", "running") and owner and owner != agent:
        raise AuthorExecutorError(
            "chapter_write task is owned by %s, not %s"
            % (owner, agent))
    if state == "ready":
        ok, report = task_engine.ready_check(project_root, task_id)
        if not ok:
            raise AuthorExecutorError(
                "chapter_write Ready Check failed: %s"
                % json.dumps(report, ensure_ascii=False))
        task_engine.claim(
            project_root, task_id, agent, "writer", model=model_id)
        state = "claimed"
    if state == "claimed":
        task_engine.start(
            project_root, task_id, agent, "writer", model=model_id)
        state = "running"
    if state != "running":
        raise AuthorExecutorError(
            "chapter_write task must be ready/claimed/running, current=%s"
            % state)


def _effective_agent(
        project_root, task_id, requested_agent=None,
        fallback="interactive-author"):
    """Use an explicit actor, otherwise inherit the live task lease owner."""
    if requested_agent:
        return requested_agent
    state, data = task_engine.load_task(project_root, task_id)
    if state is None:
        raise AuthorExecutorError("task not found: %s" % task_id)
    owner = ((data or {}).get("task") or {}).get("owner")
    return owner or fallback


def _running_output_root(project_root, task_id):
    state, data = task_engine.load_task(project_root, task_id)
    if state != "running":
        raise AuthorExecutorError(
            "chapter_write task is not running after claim/start")
    workspace = data["task"].get("workspace")
    if not workspace:
        raise AuthorExecutorError("running task has no workspace")
    return (
        workspace if os.path.isabs(workspace)
        else os.path.join(project_root, workspace))


def _finish_response(
        project_root, task_id, agent, request, response,
        response_source, reused_response=False, submit=True):
    _validate_response(response)
    model_id = request["model_id"]
    output_root = _running_output_root(project_root, task_id)
    chapter_id = request["chapter_id"]
    prose_path = os.path.join(output_root, "authored-draft.txt")
    _dump_output(prose_path, response["chapter_draft"])
    files = {
        "self_check": os.path.join(output_root, "self-check.yaml"),
        "writing_strategy_evidence": os.path.join(
            output_root, "writing-strategy-evidence.yaml"),
        "candidate_facts": os.path.join(
            output_root, "candidate-facts.yaml"),
        "handoff": os.path.join(output_root, "handoff.yaml"),
    }
    for name, path in files.items():
        _dump_output(path, response[name])

    try:
        import chapter_write
    except Exception as exc:
        raise AuthorExecutorError(
            "chapter write/Broker client is unavailable: %s" % exc)
    write_result = chapter_write.write_chapter(
        project_root, chapter_id, task_id, "writer", prose_path)
    draft_rel = write_result["target"]
    outputs = {
        "chapter_draft": draft_rel,
        **{
            name: os.path.relpath(path, project_root).replace("\\", "/")
            for name, path in files.items()
        },
    }
    result = {
        "schema": "chapter-author-result@1.0.0",
        "task_id": task_id,
        "chapter_id": chapter_id,
        "model_id": model_id,
        "response_source": response_source,
        "reused_author_response": reused_response,
        "outputs": outputs,
        "submitted": False,
    }
    if submit:
        submitted_state, successor = task_engine.submit(
            project_root, task_id, draft_rel, outputs=outputs,
            checks={
                "author_response_contract": "pass",
                "self_check": "pass",
            },
            agent=agent, role="writer", model=model_id)
        result.update({
            "submitted": submitted_state == "submitted",
            "task_state": submitted_state,
            "successor": successor,
        })
    audit_log.record(
        project_root, "chapter_author_execute", agent=agent,
        role="writer", model=model_id, task_id=task_id,
        result="success",
        detail="chapter=%s source=%s submit=%s"
        % (chapter_id, response_source, submit))
    return result


def run(project_root, task_id, agent=None,
        model_id=None, submit=True, regenerate=False):
    agent = _effective_agent(
        project_root, task_id, agent, fallback="chapter-author")
    session_bootstrap.require_session(project_root, agent=agent)
    request = build_request(project_root, task_id, model_id=model_id)
    model_id = request["model_id"]
    config = _load_config(model_id)
    command = _command_from_config(config)
    _arm_task(project_root, task_id, agent, model_id)
    task_packet.build_packet(project_root, task_id)
    request = build_request(
        project_root, task_id, model_id=model_id)
    output_root = _running_output_root(project_root, task_id)
    response, reused_response = _invoke_or_reuse(
        command, request, int(config.get("timeout_seconds", 900)),
        output_root, regenerate=regenerate)
    return _finish_response(
        project_root, task_id, agent, request, response,
        response_source="command:%s"
        % os.path.basename(command[0]),
        reused_response=reused_response, submit=submit)


def begin_interactive(
        project_root, task_id, agent=None,
        model_id=None):
    """Start the task and create the governed exchange files for chat AI."""
    agent = _effective_agent(project_root, task_id, agent)
    session_bootstrap.require_session(project_root, agent=agent)
    request = build_request(project_root, task_id, model_id=model_id)
    model_id = request["model_id"]
    _arm_task(project_root, task_id, agent, model_id)
    task_packet.build_packet(project_root, task_id)
    request = build_request(
        project_root, task_id, model_id=model_id)
    output_root = _running_output_root(project_root, task_id)
    request_path = os.path.join(
        output_root, "author-request.json")
    response_path = os.path.join(
        output_root, "author-response.json")
    with open(
            request_path, "w", encoding="utf-8",
            newline="\n") as stream:
        json.dump(
            request, stream, ensure_ascii=False,
            sort_keys=True, indent=2)
        stream.write("\n")
    return {
        "schema": "chapter-author-interactive-exchange@1.0.0",
        "task_id": task_id,
        "model_id": model_id,
        "request_file": request_path,
        "response_file": response_path,
        "next_required_action": (
            "write exactly one response-contract JSON object, then "
            "run platform author ingest"),
    }


def ingest(project_root, task_id, response_file,
           agent=None, model_id=None, submit=True):
    """Ingest a contract response authored by the current conversational AI."""
    agent = _effective_agent(project_root, task_id, agent)
    session_bootstrap.require_session(project_root, agent=agent)
    request = build_request(project_root, task_id, model_id=model_id)
    model_id = request["model_id"]
    _arm_task(project_root, task_id, agent, model_id)
    task_packet.build_packet(project_root, task_id)
    request = build_request(
        project_root, task_id, model_id=model_id)
    try:
        if response_file.lower().endswith(".json"):
            with open(response_file, "r", encoding="utf-8") as stream:
                response = json.load(stream)
        else:
            response = _gov.load_yaml(response_file) or {}
    except (OSError, ValueError) as exc:
        raise AuthorExecutorError(
            "interactive author response cannot be read: %s" % exc)
    return _finish_response(
        project_root, task_id, agent, request, response,
        response_source="interactive-response-file",
        reused_response=False, submit=submit)


def validate_config(model_id=None):
    if not model_id:
        resolution = model_router.resolve(
            _platform_root(), role="writer",
            task_type="chapter_write", capability="chapter_write",
            quality_tier=3)
        model_id = (resolution or {}).get("model_id")
    if not model_id:
        raise AuthorExecutorError("no chapter_write model resolved")
    config = _load_config(model_id)
    command = _command_from_config(config)
    return {
        "model_id": model_id,
        "transport": config.get("transport"),
        "command_configured": bool(command),
        "timeout_seconds": int(config.get("timeout_seconds", 900)),
    }


def main():
    parser = argparse.ArgumentParser(
        prog="platform author",
        description="Task Packet -> external model adapter -> governed draft")
    sub = parser.add_subparsers(dest="action", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--project-root", required=True)
    prepare.add_argument("--task", required=True)
    prepare.add_argument("--model", default=None)
    execute = sub.add_parser("run")
    execute.add_argument("--project-root", required=True)
    execute.add_argument("--task", required=True)
    execute.add_argument(
        "--agent", default=None,
        help="defaults to the task owner, or chapter-author if unclaimed")
    execute.add_argument("--model", default=None)
    execute.add_argument("--no-submit", action="store_true")
    execute.add_argument(
        "--regenerate", action="store_true",
        help="ignore a same-Task-Packet cached model response")
    begin = sub.add_parser("begin")
    begin.add_argument("--project-root", required=True)
    begin.add_argument("--task", required=True)
    begin.add_argument(
        "--agent", default=None,
        help="defaults to the task owner, or interactive-author if unclaimed")
    begin.add_argument("--model", default=None)
    interactive = sub.add_parser("ingest")
    interactive.add_argument("--project-root", required=True)
    interactive.add_argument("--task", required=True)
    interactive.add_argument("--response-file", required=True)
    interactive.add_argument(
        "--agent", default=None,
        help="defaults to the task owner, or interactive-author if unclaimed")
    interactive.add_argument("--model", default=None)
    interactive.add_argument("--no-submit", action="store_true")
    check = sub.add_parser("validate")
    check.add_argument("--model", default=None)
    arguments = parser.parse_args()
    try:
        if arguments.action == "prepare":
            result = build_request(
                arguments.project_root, arguments.task,
                model_id=arguments.model)
        elif arguments.action == "run":
            result = run(
                arguments.project_root, arguments.task,
                agent=arguments.agent, model_id=arguments.model,
                submit=not arguments.no_submit,
                regenerate=arguments.regenerate)
        elif arguments.action == "begin":
            result = begin_interactive(
                arguments.project_root, arguments.task,
                agent=arguments.agent, model_id=arguments.model)
        elif arguments.action == "ingest":
            result = ingest(
                arguments.project_root, arguments.task,
                arguments.response_file, agent=arguments.agent,
                model_id=arguments.model,
                submit=not arguments.no_submit)
        else:
            result = validate_config(arguments.model)
    except (AuthorExecutorError, OSError, RuntimeError, ValueError) as exc:
        print("REJECTED: %s" % exc)
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
