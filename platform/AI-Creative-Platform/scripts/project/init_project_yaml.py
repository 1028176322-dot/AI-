#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""init_project_yaml.py — 生成 project.yaml / project.lock.yaml / config/*（Section V/VI.4）

project.yaml 是项目唯一启动入口（编排器只读取它）。
config/* 由 spec.writing / spec.runtime 派生，不复制平台默认值。

用法：python init_project_yaml.py --staging <dir> --id X --genre xuanhuan
API：  init(spec, lock, staging, platform_root) -> (ok, err)
"""
import os
import sys
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _installer_common as C


def init(spec, lock, staging, platform_root):
    proj = spec.get("project") or {}
    tpl = spec.get("template") or {}
    writing = spec.get("writing") or {}
    runtime = spec.get("runtime") or {}
    title = proj.get("title") or spec.get("title") or "未命名项目"
    genre = tpl.get("id") or tpl.get("genre") or spec.get("genre") or "xuanhuan"
    language = proj.get("language") or spec.get("language") or "zh-CN"
    pid = proj.get("id") or C.derive_pid(title)

    resolved = lock.get("resolved", {})
    core_ver = resolved.get("core", "0")
    tpl_ver = (resolved.get("template") or "").split("@", 1)[-1] if resolved.get("template") else "0"
    nkb_ver = resolved.get("nkb_schema", "0")
    plugins = resolved.get("plugins", {})
    caps = resolved.get("capabilities", [])

    # ── project.yaml ──
    rt_mode = runtime.get("agent_mode", "single")
    project_yaml = (
        "# 由 project_installer 从 spec + lock 生成（唯一启动入口）\n"
        "# 编排器只读取本文件，不扫描整个项目目录。\n"
        "project:\n"
        "  id: %s\n"
        "  title: %s\n"
        "  type: novel\n"
        "  language: %s\n"
        "  lifecycle: initializing\n\n"
        "platform:\n"
        "  core: \"%s\"\n"
        "  template:\n"
        "    id: %s\n"
        "    version: \"%s\"\n"
        "  nkb_schema: \"%s\"\n\n"
        "requires:\n"
        "  platform: \">=2.1.0\"\n"
        "  nkb_schema: \"%s\"\n"
        "  contracts: \">=1.4.0\"\n"
        "  templates:\n"
        "    %s: \">=%s\"\n\n"
        "runtime:\n"
        "  agent_mode: %s\n"
        "  subagents_enabled: %s\n"
        "  delegation_allowed: %s\n"
        "  parallel_agents_allowed: %s\n"
        "  max_active_agents: %s\n\n"
        "paths:\n"
        "  nkb: NKB/\n"
        "  planning: planning/\n"
        "  tasks: tasks/\n"
        "  artifacts: artifacts/\n"
        "  memory: memory/project/\n"
        "  sessions: sessions/\n"
        "  overrides: overrides/\n"
        "  runtime: runtime/\n\n"
        "authority:\n"
        "  facts: NKB/\n"
        "  project_decisions: planning/decisions/\n"
        "  task_state: tasks/\n"
        "  canonical_builds: artifacts/builds/\n\n"
        "memory:\n"
        "  allowed:\n"
        "    - global\n"
        "    - genre:%s\n"
        "    - project:%s\n"
        "  forbidden:\n"
        "    - other_projects\n\n"
        "plugins:\n"
        "%s\n\n"
        "capabilities:\n"
        "%s\n\n"
        "quality_gates:\n"
        "  initialization: required\n"
        "  planning: required\n"
        "  script_precheck: required\n"
        "  ai_semantic_review: required\n"
        "  regression_review: required\n"
    ) % (
        pid, title, language,
        core_ver, genre, tpl_ver, nkb_ver,
        nkb_ver, genre, tpl_ver,
        rt_mode,
        str(runtime.get("subagents_enabled", False)).lower(),
        str(runtime.get("delegation_allowed", False)).lower(),
        str(runtime.get("parallel_agents_allowed", False)).lower(),
        runtime.get("max_active_agents", 1),
        genre, pid,
        "\n".join("  %s: %s" % (k, v) for k, v in plugins.items()),
        "\n".join("  %s: %s" % (c.split("@", 1)[0].split(".", 1)[-1] if "." in c else c, c) for c in caps),
    )
    C.write_text(os.path.join(staging, "project.yaml"), project_yaml)

    # ── project.lock.yaml ──
    C.dump_yaml(os.path.join(staging, "project.lock.yaml"), lock)

    # ── config/writing.yaml ──
    writing_yaml = {
        "schema_version": "1.0.0",
        "target_words": writing.get("target_words", 1800000),
        "volume_count": writing.get("volume_count", 6),
        "pov": writing.get("pov", "third_person_limited"),
        "audience": writing.get("audience", "male_frequency"),
        "note": "由 spec.writing 派生；不复制平台默认值。",
    }
    C.dump_yaml(os.path.join(staging, "config", "writing.yaml"), writing_yaml)

    # ── config/quality-gates.yaml ──
    qg = {
        "schema_version": "1.0.0",
        "initialization": "required",
        "planning": "required",
        "script_precheck": "required",
        "ai_semantic_review": "required",
        "regression_review": "required",
    }
    C.dump_yaml(os.path.join(staging, "config", "quality-gates.yaml"), qg)

    # ── config/context-budget.yaml ──
    cb = {
        "schema_version": "1.0.0",
        "token_budget": 32000,
        "filter": "enabled",
        "priority": "nkb_first",
        "compress": "enabled",
        "note": "上下文引擎预算；详见 core/context-engine。",
    }
    C.dump_yaml(os.path.join(staging, "config", "context-budget.yaml"), cb)

    return True, None


def main():
    ap = argparse.ArgumentParser(description="生成 project.yaml/lock/config")
    ap.add_argument("--staging", required=True)
    ap.add_argument("--spec")
    ap.add_argument("--id")
    ap.add_argument("--title")
    ap.add_argument("--genre", default="xuanhuan")
    args = ap.parse_args()
    spec = {"project": {}, "template": {}, "writing": {}, "runtime": {}}
    if args.spec:
        spec = C.load_yaml(args.spec)
    spec.setdefault("project", {})["id"] = args.id or (spec.get("project") or {}).get("id")
    spec.setdefault("project", {})["title"] = args.title or (spec.get("project") or {}).get("title")
    spec.setdefault("template", {})["genre"] = args.genre
    platform_root = C.find_platform_root()
    import resolve_dependencies as RD
    lock, lerr = RD.resolve(spec, platform_root)
    if lerr:
        C.die(lerr, 2)
    ok, err = init(spec, lock, args.staging, platform_root)
    if not ok:
        C.die(err or "init_project_yaml 失败", 2)
    print("✓ project.yaml / project.lock.yaml / config/* 已生成")
    sys.exit(0)


if __name__ == "__main__":
    main()
