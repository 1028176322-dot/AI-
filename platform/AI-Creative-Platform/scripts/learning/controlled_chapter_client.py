# -*- coding: utf-8 -*-
"""Fail-closed TaskRunner client for the independent ChapterWriter Broker."""
from __future__ import annotations

import hashlib
import json
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


def _deployment_status(project_root):
    path = os.path.join(
        project_root, "runtime", "learning", "broker-status.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8-sig") as stream:
            body = json.load(stream)
        return body if isinstance(body, dict) else {}
    except Exception as exc:
        raise BrokerError(
            "broker-status.json is unreadable: %s" % exc)


def _registry_client_token(status):
    """Read the per-project IPC token from the machine-local protected key."""
    registry_path = status.get("client_registry_path")
    if not registry_path or os.name != "nt":
        return None
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, registry_path,
                0, winreg.KEY_READ) as key:
            token, _ = winreg.QueryValueEx(key, "ClientToken")
        return str(token) if token else None
    except Exception as exc:
        raise BrokerError(
            "Broker client registry configuration is unavailable: %s" % exc)


def _endpoint(project_root):
    status = _deployment_status(project_root)
    raw = os.environ.get("STYLE_BROKER_PORT")
    if not raw:
        raw = status.get("port")
    if not raw:
        raise BrokerError(
            "Broker endpoint is not configured; run `platform broker deploy "
            "--mode Apply`; strict-v2 writes fail closed")
    try:
        port = int(raw)
    except (TypeError, ValueError):
        raise BrokerError("Broker port must be an integer")
    host = (
        os.environ.get("STYLE_BROKER_HOST")
        or status.get("host")
        or "127.0.0.1")
    token = (
        os.environ.get("STYLE_BROKER_CLIENT_TOKEN")
        or _registry_client_token(status))
    if not token:
        raise BrokerError(
            "Broker client token is unavailable; strict-v2 writes fail closed")
    return host, port, token


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
    host, port, token = _endpoint(project_root)
    client = BrokerClient(
        host=host, port=port, client_token=token)
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
