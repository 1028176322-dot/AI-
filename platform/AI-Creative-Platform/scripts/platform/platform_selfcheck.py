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
import socket
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_ROOT = os.path.dirname(HERE)
PLATFORM_ROOT = os.path.dirname(SCRIPTS_ROOT)
for path in (
        os.path.join(SCRIPTS_ROOT, "_common"),
        os.path.join(SCRIPTS_ROOT, "tasks"),
        os.path.join(SCRIPTS_ROOT, "learning"),
        os.path.join(SCRIPTS_ROOT, "logs"),
        os.path.join(SCRIPTS_ROOT, "project"),
        os.path.join(PLATFORM_ROOT, "cli")):
    if path not in sys.path:
        sys.path.insert(0, path)

import _gov
import task_templates as TT


REQUIRED_STYLE_EVENTS = {
    "on_complete", "on_clean", "on_warning", "on_issues", "on_pass",
    "on_fail", "on_rolled_back", "on_conflict", "on_fail_baseline",
    "on_fail_post_apply",
}
REQUIRED_STYLE_INPUTS = {
    "protected_manifest", "style_guidance", "diagnosis_report",
    "applied_style_rules", "revision_candidate", "revision_result",
    "fidelity_report", "quality_policy", "quality_report",
    "apply_readiness", "pre_apply_backup", "rollback_readiness",
    "regression_result", "chapter_review_report",
}
REQUIRED_STYLE_COMMANDS = {
    "style_guidance_build", "style_manifest_build", "style_diagnose",
    "style_revise", "style_fidelity_review", "style_quality_review",
    "style_apply", "style_final_regression", "style_rollback",
    "style_author_feedback", "style_event_verify", "style_status",
    "broker_serve", "broker_status", "broker_acl_plan",
    "broker_acl_apply", "broker_acl_verify",
}


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


def _check_style_system(findings):
    try:
        import style_orchestrator
        import task_packet
    except Exception as exc:
        _finding(findings, "error", "style_import",
                 "风格编排/Task Packet 无法导入: %s" % exc)
        return

    missing_events = sorted(
        REQUIRED_STYLE_EVENTS - style_orchestrator.SUPPORTED_EVENTS)
    if missing_events:
        _finding(findings, "error", "style_event_handler",
                 "风格事件没有统一处理器: %s" %
                 ", ".join(missing_events))

    declared_events = set()
    for entry in TT.registry().values():
        declared_events.update(
            (entry["template"].get("next_tasks") or {}).keys())
    unhandled = sorted(
        (declared_events & REQUIRED_STYLE_EVENTS)
        - style_orchestrator.SUPPORTED_EVENTS)
    if unhandled:
        _finding(findings, "error", "style_event_handler",
                 "模板声明事件未被处理: %s" % ", ".join(unhandled))

    with open(task_packet.__file__, "r", encoding="utf-8") as handle:
        packet_source = handle.read()
    unresolved = sorted(
        name for name in REQUIRED_STYLE_INPUTS
        if (
            name not in task_packet.STYLE_FILE_INPUTS
            and ('name == "%s"' % name) not in packet_source
            and ('"%s"' % name) not in packet_source
        ))
    if unresolved:
        _finding(findings, "error", "style_input_resolver",
                 "Task Packet 缺确定性解析器: %s" %
                 ", ".join(unresolved))

    platform = _gov.load_yaml(
        os.path.join(PLATFORM_ROOT, "platform.yaml")) or {}
    commands = platform.get("commands") or {}
    missing_commands = sorted(REQUIRED_STYLE_COMMANDS - set(commands))
    if missing_commands:
        _finding(findings, "error", "style_command_registry",
                 "platform.yaml 缺命令登记: %s" %
                 ", ".join(missing_commands))

    cli = _load_cli_module()
    module_map = getattr(cli, "GOV_MODULE_MAP", {})
    for command in ("style", "broker"):
        if command not in module_map:
            _finding(findings, "error", "style_cli_delegate",
                     "platform CLI 缺 %s 委托" % command)

    learning_registry_path = os.path.join(
        PLATFORM_ROOT, "registry", "learning.yaml")
    learning = _gov.load_yaml(learning_registry_path) or {}
    style = learning.get("style_system") or {}
    schema_dir = os.path.join(
        PLATFORM_ROOT, style.get("schema_dir") or
        "core/learning/schemas")
    for schema in style.get("schemas") or []:
        if not os.path.isfile(os.path.join(schema_dir, schema)):
            _finding(findings, "error", "style_schema_registry",
                     "已登记风格 Schema 不存在: %s" % schema, schema)

    publish = TT.load("chapter_publish")
    required = set(publish.get("required_inputs") or [])
    publish_required = {
        "regression_result", "protected_manifest_sha256",
        "style_guidance_sha256", "nkb_sync_proof",
        "chapter_review_report",
    }
    missing_publish = sorted(publish_required - required)
    if missing_publish:
        _finding(findings, "error", "style_publish_gate",
                 "发布模板缺强制证据: %s" %
                 ", ".join(missing_publish))


def _check_controlled_writes(findings):
    try:
        import scan_controlled_write
        broker = os.path.normpath(os.path.join(
            PLATFORM_ROOT, "scripts", "logs", "broker.py"))
        allowed = {
            broker,
            os.path.normpath(scan_controlled_write.__file__),
        }
        for name in (
                "diagnosis.py", "style_extract.py", "rule_review.py",
                "style_revise.py", "manifest_build.py",
                "quality_review.py", "final_regression.py",
                "chapter_apply.py", "chapter_rollback.py",
                "chapter_publish.py", "style_rule_promote.py",
                "style_hitrate.py", "author_learning.py"):
            allowed.add(os.path.normpath(os.path.join(
                PLATFORM_ROOT, "scripts", "learning", name)))
        violations = scan_controlled_write.scan_dirs(
            scan_controlled_write._default_scan_dirs(PLATFORM_ROOT),
            allow_files=allowed)
        for path, line, _, source in violations:
            _finding(findings, "error", "controlled_write_bypass",
                     "受控正文疑似直写: %s:%d %s" %
                     (os.path.relpath(path, PLATFORM_ROOT), line, source),
                     os.path.relpath(path, PLATFORM_ROOT))
    except Exception as exc:
        _finding(findings, "error", "controlled_write_scan",
                 "受控写扫描失败: %s" % exc)

    required_clients = {
        "scripts/learning/chapter_write.py",
        "scripts/learning/chapter_fix.py",
        "scripts/learning/chapter_apply.py",
        "scripts/learning/chapter_rollback.py",
        "scripts/learning/chapter_publish.py",
    }
    for relative in sorted(required_clients):
        path = os.path.join(PLATFORM_ROOT, relative)
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
        if "broker_write(" not in text:
            _finding(findings, "error", "strict_broker_client",
                     "strict-v2 正式写入未调用 Broker: %s" %
                     relative, relative)


def _workspace_project_roots(workspace_root):
    path = os.path.join(workspace_root, "workspace.yaml")
    data = _gov.load_yaml(path) if os.path.isfile(path) else {}
    entries = ((data or {}).get("workspace") or {}).get("projects") or []
    return [
        os.path.abspath(os.path.join(workspace_root, entry))
        for entry in entries
        if os.path.isdir(os.path.join(workspace_root, entry))
    ]


def _is_style_strict(project_root):
    path = os.path.join(project_root, "PROJECT_LAYOUT.yaml")
    marker = _gov.load_yaml(path) if os.path.isfile(path) else {}
    style = (marker or {}).get("style_system") or {}
    return (
        style.get("enabled") is True
        and style.get("enforcement_profile") == "strict-v2"
        and style.get("full_chapter_chain_required") is True)


def _broker_reachable(project_root):
    path = os.path.join(
        project_root, "runtime", "learning", "broker-status.json")
    if not os.path.isfile(path):
        return False, "broker-status.json 不存在"
    try:
        body = json.load(open(path, "r", encoding="utf-8"))
        port = int(body.get("port") or 0)
        connection = socket.create_connection(
            (body.get("host") or "127.0.0.1", port), timeout=1.5)
        connection.sendall(b'{"op":"status"}\n')
        response = json.loads(connection.recv(65536).decode("utf-8"))
        connection.close()
        return (
            response.get("ok") is True
            and response.get("state") == "RUNNING",
            response)
    except Exception as exc:
        return False, str(exc)


def _check_style_deployment(findings, workspace_root):
    try:
        from broker import verify_ntfs_acl
    except Exception as exc:
        _finding(findings, "error", "broker_deployment",
                 "Broker ACL 验证器无法导入: %s" % exc)
        return
    for project_root in _workspace_project_roots(workspace_root):
        if not _is_style_strict(project_root):
            continue
        label = os.path.basename(project_root)
        report_path = os.path.join(
            project_root, "runtime", "learning",
            "broker-deployment.json")
        yaml_report = os.path.join(
            project_root, "runtime", "learning",
            "broker-deployment.yaml")
        if os.path.isfile(report_path):
            report = json.load(open(
                report_path, "r", encoding="utf-8-sig"))
        elif os.path.isfile(yaml_report):
            report = _gov.load_yaml(yaml_report) or {}
            report_path = yaml_report
        else:
            report = {}
        if report.get("deployment_state") != "DEPLOYED_VERIFIED":
            _finding(findings, "error", "broker_deployment",
                     "%s: BLOCKED_NOT_DEPLOYED（缺已验证部署报告）" %
                     label, report_path)
        reachable, detail = _broker_reachable(project_root)
        if not reachable:
            _finding(findings, "error", "broker_runtime",
                     "%s: Broker 未运行或不可达: %s" %
                     (label, detail))
        acl = verify_ntfs_acl(
            os.path.join(project_root, "chapters", "drafts"),
            os.path.join(project_root, "chapters", "approved"),
            "SVC_TaskRunner", "SVC_ChapterWriter")
        if not acl.get("verified"):
            _finding(findings, "error", "broker_acl",
                     "%s: 身份或 ACL 复读验证未通过" % label)
        if report.get("taskrunner_direct_write_denied") is not True:
            _finding(findings, "error", "broker_os_bypass",
                     "%s: 缺 TaskRunner 真实身份直写拒绝证明" % label)


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
    _check_style_system(findings)
    _check_cli(findings)
    _check_python_syntax(findings)
    _check_portability(findings)
    _check_controlled_writes(findings)
    if workspace_root:
        _check_workspace_registry(findings, workspace_root)
        _check_style_deployment(findings, workspace_root)
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
            "checks": 10,
        },
        "gate": {
            "decision": decision,
            "reasons": [f["detail"] for f in findings],
        },
        "composite": {
            "health": max(0, 100 - errors * 20 - warnings * 5),
        },
        "response": {
            "checks": 10,
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
