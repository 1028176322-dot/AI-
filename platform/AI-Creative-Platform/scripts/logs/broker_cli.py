# -*- coding: utf-8 -*-
"""Operations CLI for the independent strict-v2 ChapterWriter Broker."""
import argparse
import json
import os
import socket
import sys
import time

from broker import (
    BrokerKeyVault, BrokerServer, ControlledWriter,
    apply_ntfs_acl, verify_ntfs_acl,
)


def _status_path(project_root):
    return os.path.join(
        project_root, "runtime", "learning", "broker-status.json")


def _write_status(project_root, body):
    path = _status_path(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(body, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)
    return path


def _probe(host, port, token=None):
    message = {"op": "status"}
    if token:
        message["client_token"] = token
    try:
        connection = socket.create_connection((host, port), timeout=2)
        connection.sendall(
            (json.dumps(message) + "\n").encode("utf-8"))
        response = connection.recv(65536)
        connection.close()
        body = json.loads(response.decode("utf-8"))
        return {
            "reachable": body.get("ok") is True
            and body.get("state") == "RUNNING",
            "response": body,
        }
    except Exception as exc:
        return {"reachable": False, "error": str(exc)}


def _serve(arguments):
    if not os.environ.get("STYLE_BROKER_KEY"):
        raise SystemExit(
            "REJECTED: STYLE_BROKER_KEY must be injected into the Broker "
            "service environment")
    token = os.environ.get("STYLE_BROKER_CLIENT_TOKEN")
    if not token:
        raise SystemExit(
            "REJECTED: STYLE_BROKER_CLIENT_TOKEN is required")
    writer = ControlledWriter(
        arguments.project_root,
        key_vault=BrokerKeyVault(),
        strict_dependencies=True)
    server = BrokerServer(
        writer, host=arguments.host, port=arguments.port,
        client_token=token)
    port = server.start()
    status = {
        "schema": "style-broker-status@1.0.0",
        "state": "RUNNING",
        "pid": os.getpid(),
        "host": arguments.host,
        "port": port,
        "project_root": os.path.realpath(arguments.project_root),
        "strict_dependencies": True,
        "trusted_context_source": "task_session_ssot",
        "endpoint_authentication": "shared_service_token",
        "key_source": "service_environment",
        "started_at": time.time(),
    }
    path = _write_status(arguments.project_root, status)
    print(json.dumps({"status": path, **status}, ensure_ascii=False))
    try:
        while server._thread and server._thread.is_alive():
            server._thread.join(timeout=1.0)
    except KeyboardInterrupt:
        server.shutdown()
    finally:
        status["state"] = "STOPPED"
        status["stopped_at"] = time.time()
        _write_status(arguments.project_root, status)


def _show_status(arguments):
    path = _status_path(arguments.project_root)
    if not os.path.isfile(path):
        result = {
            "state": "NOT_DEPLOYED", "reachable": False,
            "status_path": path,
        }
    else:
        with open(path, "r", encoding="utf-8") as handle:
            result = json.load(handle)
        probe = _probe(
            result.get("host", "127.0.0.1"),
            int(result.get("port") or 0),
            os.environ.get("STYLE_BROKER_CLIENT_TOKEN"))
        result.update(probe)
        if not probe["reachable"]:
            result["state"] = "STALE_OR_STOPPED"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("reachable") else 1


def _acl_paths(arguments):
    return (
        os.path.join(arguments.project_root, "chapters", "drafts"),
        os.path.join(arguments.project_root, "chapters", "approved"),
    )


def main():
    parser = argparse.ArgumentParser(prog="broker")
    subparsers = parser.add_subparsers(dest="action", required=True)

    serve = subparsers.add_parser("serve")
    serve.add_argument("--project-root", required=True)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=0)

    status = subparsers.add_parser("status")
    status.add_argument("--project-root", required=True)

    plan = subparsers.add_parser("acl-plan")
    plan.add_argument("--project-root", required=True)
    plan.add_argument("--taskrunner", default="SVC_TaskRunner")
    plan.add_argument("--writer", default="SVC_ChapterWriter")

    verify = subparsers.add_parser("acl-verify")
    verify.add_argument("--project-root", required=True)
    verify.add_argument("--taskrunner", default="SVC_TaskRunner")
    verify.add_argument("--writer", default="SVC_ChapterWriter")

    deploy = subparsers.add_parser("acl-apply")
    deploy.add_argument("--project-root", required=True)
    deploy.add_argument("--taskrunner", default="SVC_TaskRunner")
    deploy.add_argument("--writer", default="SVC_ChapterWriter")
    deploy.add_argument(
        "--confirm-real-change", action="store_true", required=True)

    arguments = parser.parse_args()
    if arguments.action == "serve":
        _serve(arguments)
        return
    if arguments.action == "status":
        sys.exit(_show_status(arguments))

    drafts, approved = _acl_paths(arguments)
    if arguments.action == "acl-plan":
        result = apply_ntfs_acl(
            drafts, approved, arguments.taskrunner, arguments.writer)
    elif arguments.action == "acl-verify":
        result = verify_ntfs_acl(
            drafts, approved, arguments.taskrunner, arguments.writer)
    else:
        result = apply_ntfs_acl(
            drafts, approved, arguments.taskrunner, arguments.writer,
            apply=True, dry_run=False)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if arguments.action == "acl-verify" and not result.get("verified"):
        sys.exit(1)


if __name__ == "__main__":
    main()
