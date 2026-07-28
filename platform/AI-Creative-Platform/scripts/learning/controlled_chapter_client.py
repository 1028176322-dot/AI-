# -*- coding: utf-8 -*-
"""Fail-closed TaskRunner client for the independent ChapterWriter Broker."""
from __future__ import annotations

import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
for _name in os.listdir(SCRIPTS):
    _path = os.path.join(SCRIPTS, _name)
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

from authorize import TaskContext
from broker import BrokerClient, BrokerError
import session_bootstrap
import task_engine


def sha256_file(path):
    if not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resource(role, path, expected_sha256=None):
    absolute = os.path.realpath(path)
    expected = expected_sha256
    if expected is None:
        expected = sha256_file(absolute)
        if expected is None:
            expected = "absent"
    return {
        "role": role,
        "canonical_path": absolute,
        "expected_sha256": expected,
    }


def _endpoint():
    raw = os.environ.get("STYLE_BROKER_PORT")
    if not raw:
        raise BrokerError(
            "STYLE_BROKER_PORT is not configured; strict-v2 writes fail closed")
    try:
        port = int(raw)
    except ValueError:
        raise BrokerError("STYLE_BROKER_PORT must be an integer")
    return os.environ.get("STYLE_BROKER_HOST", "127.0.0.1"), port


def identity(project_root, task_id, actor_id=None, session_id=None):
    state, data = task_engine.load_task(project_root, task_id)
    if state is None:
        raise BrokerError("task not found: %s" % task_id)
    task = (data or {}).get("task") or {}
    actor = actor_id or task.get("owner")
    if not actor:
        raise BrokerError("task has no lease owner")
    session = session_bootstrap.load_session(project_root) or {}
    sid = session_id or (session.get("session") or {}).get("id")
    if not sid:
        raise BrokerError("current session not found")
    return TaskContext(
        task_id=task_id, session_id=sid, actor_id=actor)


def broker_write(
        project_root, task_id, operation, resources, content,
        actor_id=None, session_id=None):
    """Authorize and write through Broker; no direct-write fallback."""
    host, port = _endpoint()
    client = BrokerClient(host=host, port=port)
    ctx = identity(
        project_root, task_id, actor_id=actor_id,
        session_id=session_id)
    authorization = client.authz(operation, ctx, resources)
    if not authorization.get("ok"):
        raise BrokerError(
            "Broker authorization denied: %s" % authorization)
    result = client.write(authorization["capability"], content)
    if not result.get("ok"):
        raise BrokerError("Broker write failed: %s" % result)
    return result


def dependency_resources(bindings):
    """Convert {role: path or (path, expected_hash)} to CAS resources."""
    resources = []
    for role, value in (bindings or {}).items():
        if isinstance(value, (tuple, list)):
            path = value[0]
            expected = value[1] if len(value) > 1 else None
        else:
            path, expected = value, None
        resources.append(resource(role, path, expected))
    return resources
