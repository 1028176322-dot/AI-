# -*- coding: utf-8 -*-
"""Native Windows Service host for the strict-v2 ChapterWriter Broker.

This host talks directly to the Service Control Manager through ``ctypes`` so
the deployment does not depend on pywin32 or an untracked third-party service
wrapper.  Secrets are read only from the service process environment.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_ROOT = os.path.dirname(HERE)
for _child in os.listdir(SCRIPTS_ROOT):
    _path = os.path.join(SCRIPTS_ROOT, _child)
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

from broker import BrokerKeyVault, BrokerServer, ControlledWriter


SERVICE_WIN32_OWN_PROCESS = 0x00000010
SERVICE_START_PENDING = 0x00000002
SERVICE_STOP_PENDING = 0x00000003
SERVICE_RUNNING = 0x00000004
SERVICE_STOPPED = 0x00000001
SERVICE_ACCEPT_STOP = 0x00000001
SERVICE_CONTROL_STOP = 0x00000001
NO_ERROR = 0


class SERVICE_STATUS(ctypes.Structure):
    _fields_ = [
        ("dwServiceType", wintypes.DWORD),
        ("dwCurrentState", wintypes.DWORD),
        ("dwControlsAccepted", wintypes.DWORD),
        ("dwWin32ExitCode", wintypes.DWORD),
        ("dwServiceSpecificExitCode", wintypes.DWORD),
        ("dwCheckPoint", wintypes.DWORD),
        ("dwWaitHint", wintypes.DWORD),
    ]


HANDLER_CALLBACK = ctypes.WINFUNCTYPE(None, wintypes.DWORD)
SERVICE_MAIN_CALLBACK = ctypes.WINFUNCTYPE(
    None, wintypes.DWORD, ctypes.POINTER(wintypes.LPWSTR))


class SERVICE_TABLE_ENTRY(ctypes.Structure):
    _fields_ = [
        ("lpServiceName", wintypes.LPWSTR),
        ("lpServiceProc", SERVICE_MAIN_CALLBACK),
    ]


_ADVAPI = ctypes.WinDLL("advapi32", use_last_error=True)
_ADVAPI.RegisterServiceCtrlHandlerW.argtypes = [
    wintypes.LPCWSTR, HANDLER_CALLBACK]
_ADVAPI.RegisterServiceCtrlHandlerW.restype = wintypes.HANDLE
_ADVAPI.SetServiceStatus.argtypes = [
    wintypes.HANDLE, ctypes.POINTER(SERVICE_STATUS)]
_ADVAPI.SetServiceStatus.restype = wintypes.BOOL
_ADVAPI.StartServiceCtrlDispatcherW.argtypes = [
    ctypes.POINTER(SERVICE_TABLE_ENTRY)]
_ADVAPI.StartServiceCtrlDispatcherW.restype = wintypes.BOOL


_CONFIG = None
_STATUS_HANDLE = None
_STATUS = SERVICE_STATUS()
_STOP_EVENT = threading.Event()
_SERVER = None


def _status_path(project_root):
    return os.path.join(
        project_root, "runtime", "learning", "broker-status.json")


def _write_status(project_root, payload):
    path = _status_path(project_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _set_service_state(state, exit_code=NO_ERROR, wait_hint=0):
    global _STATUS
    _STATUS.dwServiceType = SERVICE_WIN32_OWN_PROCESS
    _STATUS.dwCurrentState = state
    _STATUS.dwControlsAccepted = (
        SERVICE_ACCEPT_STOP if state == SERVICE_RUNNING else 0)
    _STATUS.dwWin32ExitCode = exit_code
    _STATUS.dwServiceSpecificExitCode = 0
    _STATUS.dwCheckPoint = (
        _STATUS.dwCheckPoint + 1
        if state in (SERVICE_START_PENDING, SERVICE_STOP_PENDING) else 0)
    _STATUS.dwWaitHint = wait_hint
    if _STATUS_HANDLE:
        _ADVAPI.SetServiceStatus(
            _STATUS_HANDLE, ctypes.byref(_STATUS))


@HANDLER_CALLBACK
def _service_control(control):
    if control != SERVICE_CONTROL_STOP:
        return
    _set_service_state(SERVICE_STOP_PENDING, wait_hint=10000)
    _STOP_EVENT.set()


@SERVICE_MAIN_CALLBACK
def _service_main(_argc, _argv):
    global _STATUS_HANDLE, _SERVER
    _STATUS_HANDLE = _ADVAPI.RegisterServiceCtrlHandlerW(
        _CONFIG.service_name, _service_control)
    if not _STATUS_HANDLE:
        return
    _set_service_state(SERVICE_START_PENDING, wait_hint=15000)
    try:
        if not os.environ.get("STYLE_BROKER_KEY"):
            raise RuntimeError("STYLE_BROKER_KEY is not injected")
        token = os.environ.get("STYLE_BROKER_CLIENT_TOKEN")
        if not token:
            raise RuntimeError(
                "STYLE_BROKER_CLIENT_TOKEN is not injected")
        writer = ControlledWriter(
            _CONFIG.project_root,
            key_vault=BrokerKeyVault(),
            strict_dependencies=True)
        _SERVER = BrokerServer(
            writer, host=_CONFIG.host, port=_CONFIG.port,
            client_token=token)
        port = _SERVER.start()
        if not port:
            raise RuntimeError("Broker did not bind its IPC port")
        _write_status(_CONFIG.project_root, {
            "schema": "style-broker-status@1.0.0",
            "state": "RUNNING",
            "service_name": _CONFIG.service_name,
            "pid": os.getpid(),
            "host": _CONFIG.host,
            "port": port,
            "project_root": os.path.realpath(_CONFIG.project_root),
            "strict_dependencies": True,
            "trusted_context_source": "task_session_ssot",
            "endpoint_authentication":
                "service-token-for-authz-and-write",
            "key_source": "windows-service-environment",
            "started_at": time.time(),
        })
        _set_service_state(SERVICE_RUNNING)
        _STOP_EVENT.wait()
        _SERVER.shutdown()
        _write_status(_CONFIG.project_root, {
            "schema": "style-broker-status@1.0.0",
            "state": "STOPPED",
            "service_name": _CONFIG.service_name,
            "stopped_at": time.time(),
        })
        _set_service_state(SERVICE_STOPPED)
    except Exception as exc:
        try:
            _write_status(_CONFIG.project_root, {
                "schema": "style-broker-status@1.0.0",
                "state": "FAILED",
                "service_name": _CONFIG.service_name,
                "error": str(exc),
                "failed_at": time.time(),
            })
        finally:
            _set_service_state(SERVICE_STOPPED, exit_code=1)


def main():
    if os.name != "nt":
        raise SystemExit("Windows Service host requires Windows")
    parser = argparse.ArgumentParser(prog="broker-windows-service")
    parser.add_argument("--service-name", default="AIStyleChapterWriter")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=48731)
    arguments = parser.parse_args()
    arguments.project_root = os.path.abspath(arguments.project_root)
    global _CONFIG
    _CONFIG = arguments
    table = (SERVICE_TABLE_ENTRY * 2)()
    table[0].lpServiceName = arguments.service_name
    table[0].lpServiceProc = _service_main
    table[1].lpServiceName = None
    table[1].lpServiceProc = SERVICE_MAIN_CALLBACK()
    if not _ADVAPI.StartServiceCtrlDispatcherW(table):
        code = ctypes.get_last_error()
        raise SystemExit(
            "StartServiceCtrlDispatcherW failed: %d" % code)


if __name__ == "__main__":
    main()
