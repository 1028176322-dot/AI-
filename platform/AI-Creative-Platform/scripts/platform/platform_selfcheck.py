# -*- coding: utf-8 -*-
"""Deterministic platform-wide integrity audit.

This is the fast platform gate: it validates indexes, registries, task-template
links, CLI delegation modules, Python syntax, workspace registration coherence,
and known portability hazards without touching project content.
"""
import argparse
import ast
import importlib.util
import json
import os
import re
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_ROOT = os.path.dirname(HERE)
PLATFORM_ROOT = os.path.dirname(SCRIPTS_ROOT)
for path in (
        os.path.join(SCRIPTS_ROOT, "_common"),
        os.path.join(SCRIPTS_ROOT, "tasks"),
        os.path.join(PLATFORM_ROOT, "cli")):
    if path not in sys.path:
        sys.path.insert(0, path)

import _gov
import task_templates as TT


def _finding(findings, severity, check, detail, path=None):
    item = {"severity": severity, "check": check, "detail": detail}
    if path:
        item["path"] = path.replace("\\", "/")
    findings.append(item)


def _exists_ref(base, ref):
    path = str(ref or "").split("#", 1)[0]
    return bool(path) and os.path.isfile(os.path.join(base, path))


def _check_manifest(findings):
    path = os.path.join(PLATFORM_ROOT, "platform.yaml")
    data = _gov.load_yaml(path) or {}
    for group in ("entrypoints", "registries", "governance"):
        for name, ref in (data.get(group) or {}).items():
            if not _exists_ref(PLATFORM_ROOT, ref):
                _finding(findings, "error", "manifest_ref",
                         "%s.%s 引用不存在: %s" % (group, name, ref), ref)
    for name, ref in (data.get("memory") or {}).items():
        if name in ("index", "cross_project_isolation"):
            continue
        if isinstance(ref, str) and not os.path.isdir(os.path.join(PLATFORM_ROOT, ref)):
            _finding(findings, "error", "manifest_dir",
                     "memory.%s 目录不存在: %s" % (name, ref), ref)


def _check_contract_registry(findings):
    reg_path = os.path.join(PLATFORM_ROOT, "schemas", "registry.yaml")
    data = _gov.load_yaml(reg_path) or {}
    source_dir = data.get("source_dir") or "core/contracts/"
    for section in ("schemas", "contracts", "docs"):
        for name in data.get(section) or []:
            rel = os.path.join(source_dir, name)
            if not os.path.isfile(os.path.join(PLATFORM_ROOT, rel)):
                _finding(findings, "error", "contract_registry",
                         "%s 登记文件不存在: %s" % (section, rel), rel)


def _split_plugin_ref(value):
    text = str(value or "")
    if "@" not in text:
        return text, None
    return text.rsplit("@", 1)


def _check_plugins(findings):
    path = os.path.join(PLATFORM_ROOT, "registry", "plugins.yaml")
    data = _gov.load_yaml(path) or {}
    plugins = data.get("plugins") or {}
    for plugin_id, plugin in plugins.items():
        for version, spec in (plugin.get("versions") or {}).items():
            for key in ("impl", "contract"):
                ref = (spec or {}).get(key)
                if not _exists_ref(PLATFORM_ROOT, ref):
                    _finding(findings, "error", "plugin_ref",
                             "%s@%s %s 不存在: %s" %
                             (plugin_id, version, key, ref), ref)

    caps_path = os.path.join(PLATFORM_ROOT, "registry", "capabilities.yaml")
    caps = (_gov.load_yaml(caps_path) or {}).get("capabilities") or []
    for cap in caps:
        plugin_id, version = _split_plugin_ref(cap.get("default_impl"))
        if plugin_id not in plugins or version not in (
                (plugins.get(plugin_id) or {}).get("versions") or {}):
            _finding(findings, "error", "capability_plugin",
                     "%s 的 default_impl 未注册: %s" %
                     (cap.get("id"), cap.get("default_impl")))
        if not _exists_ref(PLATFORM_ROOT, cap.get("contract")):
            _finding(findings, "error", "capability_contract",
                     "%s 的 contract 不存在: %s" %
                     (cap.get("id"), cap.get("contract")), cap.get("contract"))


def _check_templates(findings):
    path = os.path.join(PLATFORM_ROOT, "templates", "registry.yaml")
    data = _gov.load_yaml(path) or {}
    for item in data.get("templates") or []:
        if item.get("status") != "active":
            continue
        rel = item.get("path")
        base = os.path.join(PLATFORM_ROOT, "templates", rel or "")
        if not os.path.isdir(base):
            _finding(findings, "error", "genre_template",
                     "模板目录不存在: %s" % rel, rel)
        elif not os.path.isfile(os.path.join(base, "profile.yaml")):
            _finding(findings, "error", "genre_template",
                     "模板缺 profile.yaml: %s" % item.get("id"), rel)

    try:
        task_registry = TT.registry()
    except Exception as exc:
        _finding(findings, "error", "task_template_parse", str(exc))
        return
    for task_type, entry in task_registry.items():
        nxt = (entry["template"].get("next_tasks") or {})
        for event, targets in nxt.items():
            if isinstance(targets, str):
                targets = [targets]
            for target in targets or []:
                if not TT.resolve_type(target):
                    _finding(findings, "error", "task_template_link",
                             "%s.%s 悬空后继: %s" %
                             (task_type, event, target), entry["path"])


def _load_cli_module():
    path = os.path.join(PLATFORM_ROOT, "cli", "platform.py")
    spec = importlib.util.spec_from_file_location("_platform_cli_selfcheck", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check_cli(findings):
    try:
        module = _load_cli_module()
    except Exception as exc:
        _finding(findings, "error", "cli_import", "CLI 入口无法导入: %s" % exc)
        return
    module_map = getattr(module, "GOV_MODULE_MAP", {})
    if not module_map:
        _finding(findings, "error", "cli_registry",
                 "CLI 未暴露 GOV_MODULE_MAP，无法验证委托完整性")
        return
    for command, module_name in sorted(module_map.items()):
        if importlib.util.find_spec(module_name) is None:
            _finding(findings, "error", "cli_delegate",
                     "%s 委托模块不可导入: %s" % (command, module_name))


def _check_python_syntax(findings):
    for rel_root in ("cli", "scripts", "core", "tests"):
        base = os.path.join(PLATFORM_ROOT, rel_root)
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for filename in files:
                if not filename.endswith(".py"):
                    continue
                path = os.path.join(root, filename)
                try:
                    with open(path, "r", encoding="utf-8-sig") as f:
                        ast.parse(f.read(), filename=path)
                except Exception as exc:
                    _finding(findings, "error", "python_syntax",
                             "%s: %s" % (os.path.relpath(path, PLATFORM_ROOT), exc),
                             os.path.relpath(path, PLATFORM_ROOT))


def _check_workspace_registry(findings, workspace_root):
    ws_path = os.path.join(workspace_root, "workspace.yaml")
    reg_path = os.path.join(PLATFORM_ROOT, "registry", "projects.yaml")
    if not os.path.isfile(ws_path) or not os.path.isfile(reg_path):
        return
    ws = _gov.load_yaml(ws_path) or {}
    ws_entries = ((ws.get("workspace") or {}).get("projects") or [])
    reg = _gov.load_yaml(reg_path) or {}
    reg_entries = [p.get("path") for p in reg.get("projects") or [] if p.get("path")]
    ws_paths = {os.path.normcase(os.path.abspath(os.path.join(workspace_root, p))): p
                for p in ws_entries}
    reg_paths = {os.path.normcase(os.path.abspath(os.path.join(PLATFORM_ROOT, p))): p
                 for p in reg_entries}
    for absolute, rel in ws_paths.items():
        if not os.path.isdir(absolute):
            _finding(findings, "error", "workspace_project",
                     "workspace 登记项目不存在: %s" % rel, rel)
        if absolute not in reg_paths:
            _finding(findings, "error", "project_registry_drift",
                     "workspace 有登记但 registry/projects.yaml 无对应项: %s" % rel, rel)
    for absolute, rel in reg_paths.items():
        if absolute not in ws_paths:
            _finding(findings, "error", "project_registry_drift",
                     "registry/projects.yaml 有登记但 workspace 无对应项: %s" % rel, rel)


def _check_portability(findings):
    drive_pattern = re.compile(r"(?i)[A-Z]:[/\\]AI-Workspace|[/\\]\.workbuddy[/\\]")
    for rel_root in ("cli", "scripts", "tests"):
        base = os.path.join(PLATFORM_ROOT, rel_root)
        for root, _, files in os.walk(base):
            for filename in files:
                if not filename.endswith((".py", ".bat", ".sh")):
                    continue
                path = os.path.join(root, filename)
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
                if drive_pattern.search(text):
                    _finding(findings, "error", "hardcoded_runtime_path",
                             "发现不可移植的本机/工作区绝对路径",
                             os.path.relpath(path, PLATFORM_ROOT))
                if (filename.endswith(".sh") or
                        "git_hooks" in path.replace("\\", "/")):
                    with open(path, "rb") as f:
                        raw = f.read()
                        if b"\r\n" in raw:
                            _finding(findings, "error", "script_line_endings",
                                     "Unix/Hook 脚本必须使用 LF，CRLF 会导致 Hook 假失败",
                                     os.path.relpath(path, PLATFORM_ROOT))
                        if "git_hooks" in path.replace("\\", "/") and not raw.startswith(b"#!/bin/sh\n"):
                            _finding(findings, "error", "hook_shebang",
                                     "Git Hook 必须使用可移植的 #!/bin/sh",
                                     os.path.relpath(path, PLATFORM_ROOT))


def audit(workspace_root=None):
    findings = []
    _check_manifest(findings)
    _check_contract_registry(findings)
    _check_plugins(findings)
    _check_templates(findings)
    _check_cli(findings)
    _check_python_syntax(findings)
    _check_portability(findings)
    if workspace_root:
        _check_workspace_registry(findings, workspace_root)
    errors = sum(1 for f in findings if f["severity"] == "error")
    warnings = sum(1 for f in findings if f["severity"] == "warning")
    decision = "block" if errors else ("caution" if warnings else "proceed")
    return {
        "platform_root": PLATFORM_ROOT,
        "workspace_root": workspace_root,
        "summary": {
            "decision": decision,
            "errors": errors,
            "warnings": warnings,
            "checks": 7,
        },
        "gate": {
            "decision": decision,
            "reasons": [f["detail"] for f in findings],
        },
        "composite": {
            "health": max(0, 100 - errors * 20 - warnings * 5),
        },
        "response": {
            "checks": 7,
            "errors": errors,
            "warnings": warnings,
        },
        "findings": findings,
    }


def main():
    parser = argparse.ArgumentParser(prog="selfcheck",
                                     description="平台全链路快速完整性审计")
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    workspace = args.workspace or _gov.find_workspace_root()
    report = audit(workspace)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        summary = report["summary"]
        print("Platform Selfcheck: %s errors=%d warnings=%d" % (
            summary["decision"], summary["errors"], summary["warnings"]))
        for item in report["findings"]:
            print("  [%s] %s: %s%s" % (
                item["severity"].upper(), item["check"], item["detail"],
                (" (" + item["path"] + ")") if item.get("path") else ""))
    sys.exit(1 if report["summary"]["errors"] else 0)


if __name__ == "__main__":
    main()
