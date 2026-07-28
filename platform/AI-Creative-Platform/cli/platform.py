#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
platform_cli.py — AI 创作运行平台 · 平台工程化 CLI
=================================================
让平台具备「新电脑拉取仓库即可运行」的工程能力：

  bootstrap              初始化环境：检查 Platform / Plugin / NKB / Contracts / Template
                         → 生成 workspace/.cache/manifest.json → 全 PASS 才放行
  doctor                只读诊断：逐项检查并报告 PASS / FAIL / WARN，退出码反映健康度
  check  [--project X]  单项目兼容性检查（requires vs 实际）
  init-project          在 workspace/projects/ 下脚手架新项目（实例化，非复制）
  version               打印 Platform / Core / Templates / Plugins 版本目录
  list                  列出 workspace 下登记的项目

退出码：
  0 = 全部 PASS（doctor 仅 WARN 也算 0）
  1 = 存在 FAIL（doctor 退出 1；bootstrap 直接中止，不写缓存）
  2 = 用法 / 环境问题（找不到 workspace 或 platform）

解析优先级（bootstrap / doctor 严格遵守）：
  workspace 根：--workspace > $AI_WORKSPACE_HOME > 当前目录向上查找 workspace.yaml
  platform 根：$AI_PLATFORM_HOME > workspace.platform（相对 workspace 根）

依赖：零强制依赖。若环境有 PyYAML 则优先用之，否则 fallback 到同目录 _yaml_lite。
"""
import argparse
import os
import sys
import json
import re
import datetime


def _configure_stdio():
    """Make the CLI deterministic on Windows GBK and UTF-8 terminals."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


_configure_stdio()

HERE = os.path.dirname(os.path.abspath(__file__))
PLATFORM_ROOT = os.path.dirname(HERE)
_SCRIPTS = os.path.join(PLATFORM_ROOT, "scripts")
if os.path.isdir(_SCRIPTS):
    for _d in os.listdir(_SCRIPTS):
        _p = os.path.join(_SCRIPTS, _d)
        if os.path.isdir(_p) and _p not in sys.path:
            sys.path.insert(0, _p)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
sys.path.insert(0, HERE)
try:
    import yaml as _pyyaml
    def load_yaml(path):
        with open(path, "r", encoding="utf-8") as f:
            return _pyyaml.safe_load(f)
    _YAML_BACKEND = "pyyaml"
except Exception:
    import _yaml_lite
    def load_yaml(path):
        return _yaml_lite.load_file(path)
    _YAML_BACKEND = "yaml_lite"

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"

GOV_MODULE_MAP = {
    "session": "session",
    "perm": "validate_permissions",
    "contract": "validate_contract",
    "gate": "compliance_gate",
    "handoff": "create_handoff",
    "cwrite": "controlled_write",
    "nkb": "validate_nkb_sources",
    "init": "project_init",
    "charter": "validate_charter",
    "psrc": "validate_sources",
    "genesis": "build_nkb_genesis",
    "ready": "readiness_gate",
    "design": "design_expansion",
    "outline": "outline_governance",
    "craft": "writing_strategy",
    "status": "status_update",
    "task": "task_cli",
    "ver": "version_commit",
    "impact": "impact_analyzer",
    "quality": "quality_scorer",
    "reader": "reader_simulator",
    "memory": "memory_governor",
    "asset": "asset_manager",
    "model": "model_router",
    "projects": "multi_project",
    "project": "project_installer",
    "exp": "experiment",
    "bi": "bi",
    "graph": "graph_viz",
    "market": "market",
    "compliance": "compliance_scan",
    "index": "index_builder",
    "context": "context_builder",
    "policy": "policy_compiler",
    "validate": "validators",
    "query": "nkb_query",
    "summary": "summary_builder",
    "delta": "delta_review",
    "review": "review_orchestrator",
    "learn": "reference_learning",
    "feedback": "feedback_learning",
    "reader-panel": "reader_panel",
    "layout": "project_layout",
    "audit": "audit_report",
    "report": "report_builder",
    "terminology": "terminology_check",
    "chapter": "chapter_cli",
    "style": "style_cli",
    "broker": "broker_cli",
    "selfcheck": "platform_selfcheck",
}


def die(msg, code):
    sys.stderr.write("✗ %s\n" % msg)
    sys.exit(code)


# ─────────────────────────────────────────────────────────────
# 解析：workspace / platform / versions
# ─────────────────────────────────────────────────────────────
def find_workspace(explicit):
    if explicit:
        if not os.path.isfile(os.path.join(explicit, "workspace.yaml")):
            die("workspace.yaml 不在 --workspace 指定位置：%s" % explicit, 2)
        return os.path.abspath(explicit)
    if "AI_WORKSPACE_HOME" in os.environ and os.environ["AI_WORKSPACE_HOME"].strip():
        p = os.environ["AI_WORKSPACE_HOME"].strip()
        if not os.path.isfile(os.path.join(p, "workspace.yaml")):
            die("AI_WORKSPACE_HOME 指向处无 workspace.yaml：%s" % p, 2)
        return os.path.abspath(p)
    d = os.getcwd()
    while True:
        if os.path.isfile(os.path.join(d, "workspace.yaml")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    die("未找到 workspace.yaml。请在 workspace 内运行、设置 AI_WORKSPACE_HOME，或传 --workspace。", 2)


def resolve_platform_root(ws_root, ws):
    if "AI_PLATFORM_HOME" in os.environ and os.environ["AI_PLATFORM_HOME"].strip():
        return os.path.abspath(os.environ["AI_PLATFORM_HOME"].strip())
    rel = None
    if isinstance(ws, dict):
        w = ws.get("workspace", ws)
        if isinstance(w, dict):
            rel = w.get("platform")
    if not rel:
        die("workspace.yaml 缺少 workspace.platform", 2)
    return os.path.normpath(os.path.join(ws_root, rel))


def load_versions(platform_root):
    p = os.path.join(platform_root, "registry", "versions.yaml")
    if not os.path.isfile(p):
        return None
    return load_yaml(p)


def list_projects(ws_root, ws):
    if not isinstance(ws, dict):
        return []
    w = ws.get("workspace", ws)
    if not isinstance(w, dict):
        return []
    return w.get("projects", []) or []


# ─────────────────────────────────────────────────────────────
# 版本比较
# ─────────────────────────────────────────────────────────────
def _parse_ver(v):
    v = str(v).strip().lstrip("vV")
    parts = re.split(r"[.\-+]", v)
    out = []
    for x in parts:
        try:
            out.append(int(x))
        except Exception:
            out.append(0)
    return out


def satisfies(constraint, actual):
    constraint = str(constraint).strip()
    m = re.match(r"^(>=|<=|==|>|<|\^|~)?\s*(.+)$", constraint)
    if not m:
        return False
    op = m.group(1) or "=="
    cver = _parse_ver(m.group(2))
    aver = _parse_ver(actual)
    n = max(len(cver), len(aver))
    cver += [0] * (n - len(cver))
    aver += [0] * (n - len(aver))
    if op == ">=":
        return aver >= cver
    if op == "<=":
        return aver <= cver
    if op == "==":
        return aver == cver
    if op == ">":
        return aver > cver
    if op == "<":
        return aver < cver
    if op == "^":
        return aver[0] == cver[0] and aver >= cver
    if op == "~":
        return aver[0] == cver[0] and aver[1] == cver[1] and aver >= cver
    return aver == cver


# ─────────────────────────────────────────────────────────────
# 单项检查
# ─────────────────────────────────────────────────────────────
def _read_nkb_schema(project_root, nkb_rel):
    nkb_dir = os.path.normpath(os.path.join(project_root, nkb_rel or "./NKB"))
    if not os.path.isdir(nkb_dir):
        return None, "NKB 目录缺失：%s" % nkb_rel
    yamls = [f for f in os.listdir(nkb_dir) if f.endswith(".yaml")]
    if not yamls:
        return None, "NKB 无 yaml 文件"
    # 优先读 NKB.md 中的 schema 声明；否则读首个 yaml 的 schema_version
    for cand in ("NKB.md",) + tuple(yamls):
        p = os.path.join(nkb_dir, cand)
        if not os.path.isfile(p):
            continue
        try:
            data = load_yaml(p)
        except Exception:
            continue
        if isinstance(data, dict) and "schema_version" in data:
            return str(data["schema_version"]), None
    # NKB.md 可能用 markdown 表格，退而求其次：扫描首个 yaml
    for y in yamls:
        try:
            data = load_yaml(os.path.join(nkb_dir, y))
        except Exception:
            continue
        if isinstance(data, dict) and "schema_version" in data:
            return str(data["schema_version"]), None
    return None, "NKB 未声明 schema_version"


def check_nkb(project_root, data, req):
    nkb_rel = (data.get("paths") or {}).get("nkb", "./NKB")
    ver, err = _read_nkb_schema(project_root, nkb_rel)
    if err:
        return False, err
    constraint = (req.get("nkb_schema") if isinstance(req, dict) else None) or ">=0"
    ok = satisfies(constraint, ver)
    return ok, "NKB schema %s (requires %s)" % (ver, constraint)


def check_template(platform_root, data, req):
    # 兼容两种位置：顶层 template.id（旧约定）或 platform.template.id（installer 生成）
    tpl = data.get("template") or (data.get("platform") or {}).get("template") or {}
    genre = tpl.get("id")
    if not genre:
        return False, "project.yaml 缺少 template.id"
    p = os.path.join(platform_root, "templates", genre, "profile.yaml")
    if not os.path.isfile(p):
        return False, "模板缺失：templates/%s/profile.yaml" % genre
    tdata = load_yaml(p)
    ver = str((tdata or {}).get("schema_version", "0"))
    treqs = (req.get("templates") if isinstance(req, dict) else None) or {}
    constraint = treqs.get(genre)
    if constraint is None:
        return True, "模板 %s schema %s（无版本约束）" % (genre, ver)
    ok = satisfies(constraint, ver)
    return ok, "模板 %s %s (requires %s)" % (genre, ver, constraint)


def check_plugins(platform_root, data):
    reg_path = os.path.join(platform_root, "registry", "plugins.yaml")
    if not os.path.isfile(reg_path):
        return False, "registry/plugins.yaml 缺失"
    reg = load_yaml(reg_path) or {}
    registry = reg.get("plugins", {}) or {}
    missing = []
    refs = []
    for section in ("plugins", "capabilities"):
        block = data.get(section) or {}
        if isinstance(block, dict):
            refs.extend(block.values())
    for ref in refs:
        if not isinstance(ref, str) or "@" not in ref:
            missing.append("%s(格式错误)" % ref)
            continue
        name, ver = ref.split("@", 1)
        entry = registry.get(name)
        if not isinstance(entry, dict) or "versions" not in entry:
            missing.append("%s(未注册)" % ref)
            continue
        if str(ver) not in [str(v) for v in entry["versions"].keys()]:
            missing.append("%s(版本未注册)" % ref)
    if missing:
        return False, "缺失/不匹配：" + ", ".join(missing)
    return True, "全部 plugin/capability 版本已注册（%d 项）" % len(refs)


def check_compat(project_root, platform_root, versions, silent=False):
    results = {}
    data, err = _read_project(project_root)
    if err:
        results["Project"] = (FAIL, err)
        return results, None
    req = data.get("requires", {}) or {}
    # Platform 存在性
    if not os.path.isdir(platform_root):
        results["Platform"] = (FAIL, "platform 目录不存在：%s" % platform_root)
    elif versions is None:
        results["Platform"] = (FAIL, "registry/versions.yaml 不可读")
    else:
        pv = str((versions.get("core") or {}).get("platform", "0"))
        c = req.get("platform", ">=0")
        results["Platform"] = ((PASS if satisfies(c, pv) else FAIL),
                               "platform %s (requires %s)" % (pv, c))
    # Contracts
    if versions is not None:
        cv = str((versions.get("core") or {}).get("contract", "0"))
        c = req.get("contracts", ">=0")
        results["Contracts"] = ((PASS if satisfies(c, cv) else FAIL),
                                "contract %s (requires %s)" % (cv, c))
    # NKB
    nok, ndetail = check_nkb(project_root, data, req)
    results["NKB"] = ((PASS if nok else FAIL), ndetail)
    # Template
    tok, tdetail = check_template(platform_root, data, req)
    results["Template"] = ((PASS if tok else FAIL), tdetail)
    # Plugin
    pok, pdetail = check_plugins(platform_root, data)
    results["Plugin"] = ((PASS if pok else FAIL), pdetail)
    return results, data


def _read_project(project_root):
    p = os.path.join(project_root, "project.yaml")
    if not os.path.isfile(p):
        return None, "project.yaml 缺失"
    try:
        return load_yaml(p), None
    except Exception as e:
        return None, "project.yaml 解析失败：%s" % e


# ─────────────────────────────────────────────────────────────
# 输出
# ─────────────────────────────────────────────────────────────
def _print_result(name, symbol, detail):
    mark = {"PASS": "✓", "FAIL": "✗", "WARN": "!"}.get(symbol, "?")
    print("  [%-4s] %-10s %s" % (symbol, name, detail))


def _print_block(title):
    print("\n%s" % title)
    print("  " + "─" * 56)


# ─────────────────────────────────────────────────────────────
# 命令实现
# ─────────────────────────────────────────────────────────────
def cmd_doctor(args):
    ws_root = find_workspace(args.workspace)
    ws = load_yaml(os.path.join(ws_root, "workspace.yaml"))
    platform_root = resolve_platform_root(ws_root, ws)
    versions = load_versions(platform_root)

    print("AI-Workspace 诊断（doctor）")
    print("  workspace : %s" % ws_root)
    print("  platform  : %s%s" % (platform_root,
          "  (env AI_PLATFORM_HOME)" if "AI_PLATFORM_HOME" in os.environ else ""))
    print("  yaml后端  : %s" % _YAML_BACKEND)

    _print_block("平台存在性")
    if os.path.isdir(platform_root):
        _print_result("PlatformDir", PASS, "存在")
    else:
        _print_result("PlatformDir", FAIL, "不存在：%s" % platform_root)

    overall_fail = False

    def _imp(modname):
        return __import__(modname)

    def _run_gov(block_label, result_name, gov_fn, fmt_pass, *args):
        """标准化健康块执行器：统一 decision→PASS/WARN/FAIL 映射、异常处理、overall_fail 聚合。
        fmt_pass(rep) 返回 PASS 时自定义文案（保留各模块专属细节）。各能力模块 govern() 返回
        统一契约 {gate:{decision,reasons}, composite:{health}, response:{...}}。"""
        nonlocal overall_fail
        _print_block(block_label)
        try:
            rep = gov_fn(*args)
            gate = rep.get("gate") or {}
            gd = gate.get("decision", "proceed")
            health = (rep.get("composite") or {}).get("health")
            reasons = gate.get("reasons") or []
            if gd == "block":
                overall_fail = True
                _print_result(result_name, FAIL, "：".join(reasons[:3]) if reasons else "block")
            elif gd == "caution":
                _print_result(result_name, WARN, "软问题 %d 项（健康分 %s）" % (len(reasons), health))
            else:
                _print_result(result_name, PASS,
                              fmt_pass(rep) if callable(fmt_pass) else "健康分 %s" % health)
        except Exception as _e:
            _print_result(result_name, WARN, "自检异常：%s" % _e)

    _run_gov("平台完整性（入口/注册表/契约/CLI/模板/可移植性）",
             "PlatformGov",
             lambda w: _imp("platform_selfcheck").audit(w),
             lambda r: "健康分 %s（%d 项检查）" % (
                 r["composite"]["health"], r["response"]["checks"]),
             ws_root)

    valid_proots = []
    projects = list_projects(ws_root, ws)
    if not projects:
        print("\n  （workspace.yaml 未登记任何 projects）")
    for rel in projects:
        proot = os.path.normpath(os.path.join(ws_root, rel))
        _print_block("项目：%s  (%s)" % (rel, proot))
        if not os.path.isdir(proot):
            _print_result("Project", FAIL, "项目目录不存在")
            overall_fail = True
            continue
        valid_proots.append(proot)
        results, _ = check_compat(proot, platform_root, versions)
        for name, (sym, detail) in results.items():
            _print_result(name, sym, detail)
            if sym == FAIL:
                overall_fail = True

        if getattr(args, "quick", False):
            _print_result(
                "QuickMode",
                WARN,
                "已跳过项目内容型深度体检；完整检查请运行 platform doctor",
            )
            continue

        _run_gov("资产治理（项目内容资产体检）", "AssetGov",
                 lambda p: _imp("asset_manager").govern(p),
                 lambda r: "健康分 %s" % r["composite"]["health"], proot)
        _run_gov("图谱可视化（Phase 3-5 自检）", "GraphGov",
                 lambda p: _imp("graph_viz").govern(p),
                 lambda r: "健康分 %s（%d 节点/%d 边）" % (
                     r["composite"]["health"], r["response"]["nodes"], r["response"]["edges"]), proot)
        _run_gov("市场分析（Phase 3-6 自检）", "MarketGov",
                 lambda pr, p: _imp("market").govern(pr, p),
                 lambda r: "健康分 %s（%d 信号）" % (
                     r["composite"]["health"], r["response"]["signals"]), platform_root, proot)
        _run_gov("源同步校验（txt↔md CI 检查 · Phase 审查治理）", "SyncGov",
                 lambda p: _imp("sync_check").check_txt_md_sync(p),
                 lambda r: "健康分 %s（%d 源章节 / %d 已导出 / %d 未导出）" % (
                     r["composite"]["health"], r["response"]["sources"],
                     r["response"]["checked"], len(r["response"]["missing"])), proot)
        _run_gov("项目基线健康（Project 自检 · Phase C）", "ProjectGov",
                 lambda p: _imp("project_health").govern(p),
                 lambda r: "健康分 %s（%s）" % (
                     r["composite"]["health"], r["response"].get("summary", "ok")), proot)
        _run_gov("内容版本控制（Version 自检 · Phase C）", "VersionGov",
                 lambda p: _imp("version_commit").govern(p),
                 lambda r: "健康分 %s（%d 快照）" % (
                     r["composite"]["health"], r["response"]["snapshots"]), proot)
        _run_gov("操作审计（Audit 自检 · Phase C）", "AuditGov",
                 lambda p: _imp("audit_report").govern(p),
                 lambda r: "健康分 %s（%d 记录）" % (
                     r["composite"]["health"], r["response"]["records"]), proot)
        _run_gov("状态派生（Status 自检 · Phase C）", "StatusGov",
                 lambda p: _imp("status_derive").govern(p),
                 lambda r: "健康分 %s（派生状态正常·%d 伏笔未回收）" % (
                     r["composite"]["health"], r["response"]["open_foreshadows"]), proot)
        _run_gov("报告生成器（Report 自检 · Phase C）", "ReportGov",
                 lambda p: _imp("report_builder").govern(p),
                 lambda r: "健康分 %s（报告可生成）" % r["composite"]["health"], proot)
        _run_gov("术语表（Terminology 自检 · Phase C）", "TermGov",
                 lambda p: _imp("terminology_check").govern(p),
                 lambda r: "健康分 %s（%d 记录·%d 禁用同义）" % (
                     r["composite"]["health"], r["response"]["records"], r["response"]["forbidden"]), proot)

    _run_gov("内存治理（platform/memory/ 体检）", "MemoryGov",
             lambda pr: _imp("memory_governor").govern(pr),
             lambda r: "健康分 %s" % r["composite"]["health"], platform_root)
    _run_gov("模型布线器（Phase 3-1 自检）", "ModelGov",
             lambda pr: _imp("model_router").govern(pr),
             lambda r: "健康分 %s" % r["composite"]["health"], platform_root)
    _run_gov("多项目管理（Phase 3-2 自检）", "MultiProjGov",
             lambda pr: _imp("multi_project").govern(pr),
             lambda r: "健康分 %s（%d 项目）" % (
                 r["composite"]["health"], r["response"]["projects"]), platform_root)
    _run_gov("实验系统（Phase 3-3 自检）", "ExpGov",
             lambda pr: _imp("experiment").govern(pr),
             lambda r: "健康分 %s（%d 实验）" % (
                 r["composite"]["health"], r["response"]["experiments"]), platform_root)
    _run_gov("BI 分析（Phase 3-4 自检）", "BiGov",
             lambda pr: _imp("bi").govern(pr),
             lambda r: "健康分 %s（%d 仪表盘）" % (
                 r["composite"]["health"], r["response"]["dashboards"]), platform_root)
    _run_gov("项目模板（Phase 3-7 自检）", "TemplateGov",
             lambda pr: _imp("project_template").govern(pr),
             lambda r: "健康分 %s（%d 模板 / %d 注册项目）" % (
                 r["composite"]["health"], r["response"]["templates"], r["response"]["projects"]), platform_root)

    for proot in valid_proots:
        _print_block("单 Agent 执行策略（%s · Agent Compliance Gate）" % proot)
        try:
            _gates_dir = os.path.join(platform_root, "core", "gates")
            if _gates_dir not in sys.path:
                sys.path.insert(0, _gates_dir)
            import agent_compliance_gate as _acg
            acgrep = _acg.govern(proot, write=False)
            acgd = (acgrep.get("gate") or {}).get("decision", "proceed")
            if acgd == "block":
                _print_result("AgentGov", FAIL, "单 Agent 策略违例：%s" % "；".join(acgrep["gate"]["reasons"][:3]))
                overall_fail = True
            elif acgd == "caution":
                _print_result("AgentGov", WARN, "软问题 %d 项（健康分 %s）" % (
                    len(acgrep["gate"]["reasons"]), acgrep["composite"]["health"]))
            else:
                _print_result("AgentGov", PASS, "健康分 %s" % acgrep["composite"]["health"])
        except Exception as _e:
            _print_result("AgentGov", WARN, "自检异常：%s" % _e)

        _print_block("脚本化工具链（%s · ScriptGov）" % proot)
        try:
            import json as _json
            idx_path = os.path.join(proot, "runtime", "indexes", "index.json")
            if os.path.isfile(idx_path):
                _idata = _json.load(open(idx_path, encoding="utf-8"))
                _print_result("ScriptGov", PASS, "索引已构建：实体 %d / 章节 %d / 事件 %d" % (
                    _idata.get("counts", {}).get("entities", 0),
                    _idata.get("counts", {}).get("chapters", 0),
                    _idata.get("counts", {}).get("events", 0)))
            else:
                _print_result("ScriptGov", WARN, "索引未构建（运行 platform index build 以启用输入最小化）")
        except Exception as _e:
            _print_result("ScriptGov", WARN, "自检异常：%s" % _e)

        _print_block("审查管线（%s · ReviewGov）" % proot)
        try:
            plat_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            schema_p = os.path.join(plat_root, "core", "contracts", "review-report.schema.yaml")
            plan_p = os.path.join(plat_root, "core", "review", "review-plan.yaml")
            if os.path.isfile(schema_p) and os.path.isfile(plan_p):
                rv = os.path.join(proot, "runtime", "reviews")
                n = 0
                if os.path.isdir(rv):
                    for _d in os.listdir(rv):
                        if _d.startswith("REVIEW-"):
                            n += 1
                _print_result("ReviewGov", PASS,
                              "审查契约齐备（schema+plan）；已生成 %d 份审查证据包" % n)
            else:
                _print_result("ReviewGov", WARN,
                              "审查契约缺失（review-report.schema.yaml / review-plan.yaml）")
        except Exception as _e:
            _print_result("ReviewGov", WARN, "自检异常：%s" % _e)

    print("")
    if overall_fail:
        print("结果：存在 FAIL —— 平台/项目不兼容，请先修复后再运行。")
        sys.exit(1)
    print("结果：全部 PASS（无 FAIL）。")
    sys.exit(0)


def _check_platform_manifest(platform_root):
    """校验 platform.yaml 一级入口自洽（PC-7 平台入口）。

    检查 entrypoints / registries / governance 引用的文件存在，
    memory 子目录存在。返回 [(sym, name, detail), ...]；空列表=自洽。
    """
    pf = os.path.join(platform_root, "platform.yaml")
    if not os.path.isfile(pf):
        return [(FAIL, "platform.yaml", "平台一级入口文件缺失")]
    meta = load_yaml(pf) or {}
    findings = []
    for grp in ("entrypoints", "registries", "governance"):
        for k, rel in (meta.get(grp) or {}).items():
            if rel and not os.path.isfile(os.path.join(platform_root, rel)):
                findings.append((FAIL, "%s.%s" % (grp, k), "引用文件缺失：%s" % rel))
    mem = meta.get("memory") or {}
    for k in ("global", "genre", "rejected"):
        rel = mem.get(k)
        if rel and not os.path.isdir(os.path.join(platform_root, rel)):
            findings.append((FAIL, "memory.%s" % k, "目录缺失：%s" % rel))
    return findings


def cmd_bootstrap(args):
    ws_root = find_workspace(args.workspace)
    ws = load_yaml(os.path.join(ws_root, "workspace.yaml"))
    platform_root = resolve_platform_root(ws_root, ws)
    versions = load_versions(platform_root)

    print("AI-Workspace 初始化（bootstrap）")
    print("  workspace : %s" % ws_root)
    print("  platform  : %s" % platform_root)

    _print_block("环境检查")
    if not os.path.isdir(platform_root):
        _print_result("PlatformDir", FAIL, "不存在：%s" % platform_root)
        print("\n✗ bootstrap 中止：Platform 不可用。")
        sys.exit(1)
    _print_result("PlatformDir", PASS, "存在")
    if versions is None:
        _print_result("Versions", FAIL, "registry/versions.yaml 不可读")
        print("\n✗ bootstrap 中止。")
        sys.exit(1)
    _print_result("Versions", PASS, "可读")

    # 平台一级入口自洽校验（PC-7）：platform.yaml 引用的文件/目录必须存在
    _print_block("平台入口校验（platform.yaml）")
    pm = _check_platform_manifest(platform_root)
    if pm:
        for sym, name, detail in pm:
            _print_result(name, sym, detail)
        print("\n✗ bootstrap 中止：platform.yaml 自洽校验失败。")
        sys.exit(1)
    _print_result("PlatformManifest", PASS, "自洽（entrypoints/registries/governance/memory 全部存在）")

    try:
        import platform_selfcheck as _psc
        _selfcheck = _psc.audit(ws_root)
        _errors = _selfcheck["summary"]["errors"]
        if _errors:
            _print_result("PlatformSelfcheck", FAIL,
                          "%d 个平台完整性错误" % _errors)
            print("\n✗ bootstrap 中止：平台完整性自检失败。")
            sys.exit(1)
        _print_result("PlatformSelfcheck", PASS, "入口/注册表/契约/CLI/模板/可移植性自洽")
    except Exception as _e:
        _print_result("PlatformSelfcheck", FAIL, "自检异常：%s" % _e)
        print("\n✗ bootstrap 中止：平台完整性自检异常。")
        sys.exit(1)

    manifest = {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "workspace": ws_root,
        "platform": {"root": platform_root, "versions": versions},
        "yaml_backend": _YAML_BACKEND,
        "projects": [],
    }

    overall_fail = False
    projects = list_projects(ws_root, ws)
    for rel in projects:
        proot = os.path.normpath(os.path.join(ws_root, rel))
        _print_block("项目：%s" % rel)
        if not os.path.isdir(proot):
            _print_result("Project", FAIL, "项目目录不存在")
            overall_fail = True
            continue
        results, data = check_compat(proot, platform_root, versions)
        proj_entry = {
            "id": (data.get("project") or {}).get("id", rel) if data else rel,
            "rel": rel,
            "root": proot,
            "requires": (data.get("requires") if data else None),
            "checks": {k: {"symbol": s, "detail": d} for k, (s, d) in results.items()},
        }
        for name, (sym, detail) in results.items():
            _print_result(name, sym, detail)
            if sym == FAIL:
                overall_fail = True
        manifest["projects"].append(proj_entry)

    if overall_fail:
        print("\n✗ bootstrap 中止：存在 FAIL，未生成缓存。请修复兼容性后再跑。")
        sys.exit(1)

    cache_dir = os.path.join(ws_root, ".cache")
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, "manifest.json")
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print("\n✓ bootstrap 成功：全部 PASS。缓存已写入 %s" % cache_path)
    sys.exit(0)


def cmd_check(args):
    ws_root = find_workspace(args.workspace)
    ws = load_yaml(os.path.join(ws_root, "workspace.yaml"))
    platform_root = resolve_platform_root(ws_root, ws)
    versions = load_versions(platform_root)
    projects = list_projects(ws_root, ws)
    if args.project:
        target = None
        for rel in projects:
            proot = os.path.normpath(os.path.join(ws_root, rel))
            data, _ = _read_project(proot)
            if (data and (data.get("project") or {}).get("id") == args.project) or rel.endswith(args.project) or os.path.normpath(rel) == args.project:
                target = proot
                break
        if not target:
            die("未找到项目：%s" % args.project, 2)
        proots = [target]
    else:
        proots = [os.path.normpath(os.path.join(ws_root, r)) for r in projects]
    overall_fail = False
    for proot in proots:
        _print_block("项目：%s" % proot)
        results, _ = check_compat(proot, platform_root, versions)
        for name, (sym, detail) in results.items():
            _print_result(name, sym, detail)
            if sym == FAIL:
                overall_fail = True
    print("")
    sys.exit(1 if overall_fail else 0)


def cmd_version(args):
    ws_root = find_workspace(args.workspace)
    ws = load_yaml(os.path.join(ws_root, "workspace.yaml"))
    platform_root = resolve_platform_root(ws_root, ws)
    versions = load_versions(platform_root)
    if versions is None:
        die("registry/versions.yaml 不可读", 1)
    print("Platform 版本目录")
    print(json.dumps(versions, ensure_ascii=False, indent=2))
    sys.exit(0)


def cmd_list(args):
    ws_root = find_workspace(args.workspace)
    ws = load_yaml(os.path.join(ws_root, "workspace.yaml"))
    projects = list_projects(ws_root, ws)
    print("Workspace 登记项目：")
    if not projects:
        print("  （无）")
    for rel in projects:
        proot = os.path.normpath(os.path.join(ws_root, rel))
        data, _ = _read_project(proot)
        pid = (data.get("project") or {}).get("id", "?") if data else "?"
        pname = (data.get("project") or {}).get("name", "?") if data else "?"
        print("  - %s  (id=%s, name=%s)" % (rel, pid, pname))
    sys.exit(0)


def cmd_init_project(args):
    ws_root = find_workspace(args.workspace)
    ws = load_yaml(os.path.join(ws_root, "workspace.yaml"))
    platform_root = resolve_platform_root(ws_root, ws)
    genre = args.type
    name = args.name
    pid = args.id
    import project_template as _pt
    ok, errs, proot = _pt.scaffold(
        platform_root, ws_root, name, genre, pid=pid, write=True)
    if not ok:
        die("; ".join(errs), 2)
    rok, rerrs, _ = _pt.register_multi_project(
        platform_root, ws_root, name, genre, pid=pid, proot=proot, write=True)
    if not rok:
        sys.stderr.write(
            "⚠ 多项目注册未完成：%s（项目已脚手架，可重试 platform projects register）\n"
            % "; ".join(rerrs))
    print("✓ 已脚手架项目：%s" % proot)
    print("  请运行：python cli/platform.py bootstrap")
    sys.exit(0)


# _append_project_to_workspace 已迁移至 scripts/project/project_template.py（_append_to_workspace）


# ─────────────────────────────────────────────────────────────
# 入口
# ─────────────────────────────────────────────────────────────
def build_parser():
    p = argparse.ArgumentParser(
        prog="platform",
        description="AI 创作运行平台 · 平台工程化 CLI")
    p.add_argument("--workspace", help="workspace 根（覆盖环境变量与自动查找）")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("bootstrap", help="初始化环境并生成缓存（全 PASS 才放行）")
    doctor_parser = sub.add_parser(
        "doctor", help="只读诊断兼容性，退出码反映健康度")
    doctor_parser.add_argument(
        "--quick",
        action="store_true",
        help="跳过项目内容型深度体检，保留平台、兼容性和执行治理检查",
    )
    c = sub.add_parser("check", help="单项目兼容性检查")
    c.add_argument("--project", help="项目 id 或相对路径")
    sub.add_parser("version", help="打印版本目录")
    sub.add_parser("list", help="列出登记项目")
    ip = sub.add_parser("init-project", help="脚手架新项目")
    ip.add_argument("--name", required=True, help="项目目录名（如 小说B）")
    ip.add_argument("--type", required=True, help="类型模板 id（如 xuanhuan）")
    ip.add_argument("--id", help="项目 id（默认 novel-<name>）")

    # ── 治理层（AI 执行控制）──
    gs = sub.add_parser("session", help="会话启动协议：bootstrap/verify/status/close（强制入口）")
    gs.add_argument("verb", choices=["bootstrap", "verify", "status", "close"])
    gs.add_argument("--project", default=None)
    gs.add_argument("--intent", default="auto")
    gs.add_argument("--target", default=None)
    gs.add_argument("--role", default=None)
    gs.add_argument("--workspace", default=None)
    gs.add_argument("--session", default=None)
    gs.add_argument("--stage", default=None)
    gs.add_argument("--next", default=None)
    gs.add_argument("--artifacts", nargs="*", default=[])
    gs.add_argument("--issues", nargs="*", default=[])

    gp = sub.add_parser("perm", help="校验角色对目标路径的写权限")
    gp.add_argument("--role", required=True)
    gp.add_argument("--target", required=True)

    gc = sub.add_parser("contract", help="校验操作 payload 是否满足契约")
    gc.add_argument("--contract", required=True)
    gc.add_argument("--payload", required=True)

    gg = sub.add_parser("gate", help="合规门：平台合规检查（不查文学质量）")
    gg.add_argument("--session", required=True)
    gg.add_argument("--operation", default=None)
    gg.add_argument("--role", default=None)
    gg.add_argument("--handoff", default=None)

    gh = sub.add_parser("handoff", help="生成跨对话交接文件")
    gh.add_argument("--from", dest="from_role", required=True)
    gh.add_argument("--to", dest="to_role", required=True)
    gh.add_argument("--project", required=True)
    gh.add_argument("--chapter", default=None)
    gh.add_argument("--session", required=True)
    gh.add_argument("--artifacts", nargs="*", default=[])
    gh.add_argument("--risks", nargs="*", default=[])

    gx = sub.add_parser("cwrite", help="受控写：AI 只能通过它改项目文件")
    gx.add_argument("--role", required=True)
    gx.add_argument("--target", required=True)
    gx.add_argument("--project", required=True)
    gx.add_argument("--content-file", default=None)
    gx.add_argument("--nkb-version", default=None)
    gx.add_argument("--context-hash", default=None)
    gx.add_argument("--contract-version", default="2.0.0")
    gx.add_argument("--policy-version", default="1.3.0")
    gx.add_argument("--session", default="SES-unknown")

    gn = sub.add_parser("nkb", help="NKB 源文件/候选事实质量门禁校验")
    gn.add_argument("--project-root", help="项目根（自动推导 sources/ 与 NKB/candidates/）")
    gn.add_argument("--project", help="期望 project_id")
    gn.add_argument("--sources", help="sources 目录（覆盖默认）")
    gn.add_argument("--candidates", help="候选事实目录（覆盖默认）")

    gi = sub.add_parser("init", help="脚手架项目生命周期目录 + status.yaml（P0 入口）")
    gi.add_argument("--project-root", required=True)
    gi.add_argument("--title", default="未命名项目")
    gi.add_argument("--genre", default="xuanhuan")
    gi.add_argument("--id", default=None)
    gi.add_argument("--stage", default="idea")
    gi.add_argument("--legacy", action="store_true", help="祖父化：直接置 writing + legacy_backfill_required")

    gch = sub.add_parser("charter", help="校验 P0/P1/P2 生命周期制品契约")
    gch.add_argument("--project-root", required=True)
    gch.add_argument("--file", default=None)

    gps = sub.add_parser("psrc", help="校验 P3 创作设计源门禁（sources/design+canon）")
    gps.add_argument("--project-root", required=True)
    gps.add_argument("--src", default=None)

    gg2 = sub.add_parser("genesis", help="从 sources 构建 NKB-GENESIS-001（P4）")
    gg2.add_argument("--project-root", required=True)

    gr = sub.add_parser("ready", help="开写验收 P5 + 编排器 pre-flight")
    gr.add_argument("--project-root", required=True)
    gr.add_argument("--preflight", action="store_true", help="仅做编排器前置检查（JSON 输出）")
    gr.add_argument("--approve", action="store_true", help="验收通过并置 ready_for_writing")
    gdesign = sub.add_parser("design", help="对话灵感结构化、AI 设计扩展、审查审批与 Genesis 前置门禁")
    gdesign.add_argument("rest", nargs=argparse.REMAINDER)
    goutline = sub.add_parser("outline", help="总章节数驱动的五级大纲生成计划、覆盖与可写性门禁")
    goutline.add_argument("rest", nargs=argparse.REMAINDER)
    gcraft = sub.add_parser("craft", help="按章纲和场景自适应编排写作手法并校验正文执行证据")
    gcraft.add_argument("rest", nargs=argparse.REMAINDER)

    # ── 项目管理平面（Phase 1 必须项）──
    gst = sub.add_parser("status", help="项目状态管理：project/status.yaml（init/show/set/block）")
    gst.add_argument("--project-root", required=True)
    gst.add_argument("rest", nargs=argparse.REMAINDER)

    gt = sub.add_parser("task", help="任务系统操作中心（create/claim/submit/review/...）")
    gt.add_argument("--project-root", required=True)
    gt.add_argument("rest", nargs=argparse.REMAINDER)

    gv = sub.add_parser("ver", help="内容版本控制（commit/log/rollback）")
    gv.add_argument("--project-root", required=True)
    gv.add_argument("rest", nargs=argparse.REMAINDER)

    gi2 = sub.add_parser("impact", help="冲击分析仪：变更影响分析（analyze/from-task/index/show）")
    gi2.add_argument("--project-root", required=True)
    gi2.add_argument("rest", nargs=argparse.REMAINDER)

    gq = sub.add_parser("quality", help="质量评分：内容质量评分与门禁（score/from-task/show）")
    gq.add_argument("--project-root", required=True)
    gq.add_argument("rest", nargs=argparse.REMAINDER)

    gr = sub.add_parser("reader", help="读者模拟：读者体验模拟与门禁（sim/from-task/show）")
    gr.add_argument("--project-root", required=True)
    gr.add_argument("rest", nargs=argparse.REMAINDER)

    gm = sub.add_parser("memory", help="内存治理：对 platform/memory/ 四层经验库体检（validate/report/dedup）")
    gm.add_argument("--platform-root", required=True)
    gm.add_argument("rest", nargs=argparse.REMAINDER)

    ga = sub.add_parser("asset", help="资产管理：对项目内容资产盘点与引用完整性体检（inventory/report/orphans/missing/dedup）")
    ga.add_argument("--project-root", required=True)
    ga.add_argument("rest", nargs=argparse.REMAINDER)

    gau = sub.add_parser("audit", help="操作审计汇总（report/govern）")
    gau.add_argument("--project-root", required=True)
    gau.add_argument("rest", nargs=argparse.REMAINDER)

    gm2 = sub.add_parser("model", help="模型布线器：任务→模型路由与降级链（resolve/validate）")
    gm2.add_argument("--platform-root", required=True)
    gm2.add_argument("rest", nargs=argparse.REMAINDER)

    gpj = sub.add_parser("projects", help="多项目管理：跨项目注册/隔离解析/统一 dispatch（list/register/query/dispatch/validate）")
    gpj.add_argument("--platform-root", required=True)
    gpj.add_argument("rest", nargs=argparse.REMAINDER)

    gpi = sub.add_parser("project", help="项目事务式安装器：create/doctor/reconcile/upgrade（确定性部署，不复制平台内容）")
    gpi.add_argument("rest", nargs=argparse.REMAINDER)

    gx2 = sub.add_parser("exp", help="实验系统：A/B 对照定义/分配/回收/判定（define/run/sample/report/validate）")
    gx2.add_argument("--platform-root", required=True)
    gx2.add_argument("rest", nargs=argparse.REMAINDER)

    gbi = sub.add_parser("bi", help="BI 分析：质量/读者/实验统一 rollup 与 dashboard（rollup/dashboard/validate）")
    gbi.add_argument("--platform-root", required=True)
    gbi.add_argument("--project-root", required=True)
    gbi.add_argument("rest", nargs=argparse.REMAINDER)

    ggv = sub.add_parser("graph", help="图谱可视化：NKB→graph JSON + HTML 渲染（build/render/validate）")
    ggv.add_argument("--project-root", required=True)
    ggv.add_argument("rest", nargs=argparse.REMAINDER)

    gmkt = sub.add_parser("market", help="市场分析：摄取市场信号→机会打分→brief（ingest/score/brief/sync/validate）")
    gmkt.add_argument("--platform-root", required=True)
    gmkt.add_argument("--project-root", required=True)
    gmkt.add_argument("rest", nargs=argparse.REMAINDER)

    grp = sub.add_parser("report", help="报告生成器：project-status/chapter-quality/open-foreshadow/task-progress/nkb-health/all")
    grp.add_argument("--project-root", required=True)
    grp.add_argument("rest", nargs=argparse.REMAINDER)

    gterm = sub.add_parser("terminology", help="术语全量词表检查（接入 NKB Terminology）：scan(单文件/全稿件) + govern")
    gterm.add_argument("--project-root", default=None)
    gterm.add_argument("--file", default=None)
    gterm.add_argument("--json", action="store_true")
    gterm.add_argument("rest", nargs=argparse.REMAINDER)

    gcs = sub.add_parser("compliance", help="任务系统强制层旁路检测：越权改动扫描 + 回滚（scan [--rollback]）")
    gcs.add_argument("--project-root", required=True)
    gcs.add_argument("--rollback", action="store_true", help="显式回滚越权改动（破坏性）")

    # ── Phase A 脚本化工具链（输入最小化）──
    gi3 = sub.add_parser("index", help="索引构建与查询（files/entities/chapters/events/terminology/dependencies）")
    gi3.add_argument("--project-root", default=None)
    gi3.add_argument("rest", nargs=argparse.REMAINDER)
    gc2 = sub.add_parser("context", help="最小上下文构建（Context Package，预算过滤 NKB）")
    gc2.add_argument("--project-root", default=None)
    gc2.add_argument("rest", nargs=argparse.REMAINDER)
    gp3 = sub.add_parser("policy", help="编译最小规则包（Policy Compiler）")
    gp3.add_argument("--project-root", default=None)
    gp3.add_argument("rest", nargs=argparse.REMAINDER)
    gv2 = sub.add_parser("validate", help="Level-1 脚本预检管线（schema/ids/references/terminology/...）")
    gv2.add_argument("--project-root", default=None)
    gv2.add_argument("rest", nargs=argparse.REMAINDER)
    gq2 = sub.add_parser("query", help="NKB 查询/投影接口（get/state/events/foreshadow/reader-known/project）")
    gq2.add_argument("--project-root", default=None)
    gq2.add_argument("rest", nargs=argparse.REMAINDER)
    # ── 编辑≠发布：Publish Service 与 canonical 诊断 ──
    gch2 = sub.add_parser("chapter", help="章节发布与生命周期（publish/workflow/canonical-writes/rollback）")
    gch2.add_argument("--project-root", default=None)
    gch2.add_argument("rest", nargs=argparse.REMAINDER)
    gstyle = sub.add_parser(
        "style", help="风格与去 AI 味 strict-v2 全链路")
    gstyle.add_argument("rest", nargs=argparse.REMAINDER)
    gbroker = sub.add_parser(
        "broker", help="独立受控写 Broker 运维与 ACL 验证")
    gbroker.add_argument("rest", nargs=argparse.REMAINDER)
    # ── Phase B 审查管线增强 ──
    gs2 = sub.add_parser("summary", help="章节/卷/弧/滚动摘要落盘（AI 填字段→脚本落盘）")
    gs2.add_argument("--project-root", default=None)
    gs2.add_argument("rest", nargs=argparse.REMAINDER)
    gd2 = sub.add_parser("delta", help="增量审查 Delta Review（章节 diff + 受影响实体/规则投影）")
    gd2.add_argument("--project-root", default=None)
    gd2.add_argument("rest", nargs=argparse.REMAINDER)
    gr2 = sub.add_parser("review", help="单 Agent 多阶段审查编排（证据包 + 空报告模板）")
    gr2.add_argument("--project-root", default=None)
    gr2.add_argument("rest", nargs=argparse.REMAINDER)
    glearn = sub.add_parser("learn", help="参考小说结构学习与项目级候选晋升")
    glearn.add_argument("rest", nargs=argparse.REMAINDER)
    gfeedback = sub.add_parser("feedback", help="审查问题反补写作与回归检查")
    gfeedback.add_argument("rest", nargs=argparse.REMAINDER)
    gpanel = sub.add_parser("reader-panel", help="多观察点读者面板与真人反馈校准")
    gpanel.add_argument("rest", nargs=argparse.REMAINDER)
    glayout = sub.add_parser("layout", help="新项目严格目录契约检查")
    glayout.add_argument("rest", nargs=argparse.REMAINDER)
    gself = sub.add_parser("selfcheck", help="平台全链路快速完整性审计")
    gself.add_argument("--workspace", dest="selfcheck_workspace", default=None)
    gself.add_argument("--json", dest="selfcheck_json", action="store_true")
    return p


def main():
    args = build_parser().parse_args()
    if not args.cmd:
        build_parser().print_help()
        sys.exit(2)
    if args.cmd == "bootstrap":
        cmd_bootstrap(args)
    elif args.cmd == "doctor":
        cmd_doctor(args)
    elif args.cmd == "check":
        cmd_check(args)
    elif args.cmd == "version":
        cmd_version(args)
    elif args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "init-project":
        cmd_init_project(args)
    elif args.cmd in ("session", "perm", "contract", "gate", "handoff", "cwrite", "nkb",
        "init", "charter", "psrc", "genesis", "ready", "design", "outline", "craft",
        "status", "task", "ver", "impact", "quality", "reader", "memory", "asset", "model", "projects", "project", "exp", "bi", "graph", "market", "compliance",
                      "index", "context", "policy", "validate", "query",
                      "summary", "delta", "review", "learn", "feedback", "reader-panel", "layout",
                      "report", "audit", "terminology", "chapter",
                      "style", "broker",
                      "selfcheck"):
        _delegate_gov(args.cmd, args)
    else:
        die("未知子命令：%s" % args.cmd, 2)


def _delegate_gov(cmd, args):
    """把治理子命令委托给 scripts/ 下对应模块（复用其 main + argparse）。

    直接沿用用户原始命令行 flag（sys.argv[2:]），避免 dest 名与模块不一致。
    platform <cmd> --flag a  =>  <module> --flag a
    """
    import importlib
    if cmd == "selfcheck":
        forwarded = []
        if args.selfcheck_workspace:
            forwarded += ["--workspace", args.selfcheck_workspace]
        if args.selfcheck_json:
            forwarded.append("--json")
        sys.argv = [GOV_MODULE_MAP[cmd]] + forwarded
    else:
        forwarded = list(sys.argv[2:])
        rest = list(getattr(args, "rest", []) or [])
        # Many delegated modules use argparse subparsers. The façade accepts
        # shared flags before the action (for example:
        # ``platform index --project-root X build``), but a nested parser
        # requires ``build`` first. Move only the declared action token while
        # preserving every remaining user argument.
        if rest and not str(rest[0]).startswith("-"):
            action = rest[0]
            try:
                forwarded.remove(action)
                forwarded.insert(0, action)
            except ValueError:
                pass
        sys.argv = [GOV_MODULE_MAP[cmd]] + forwarded
    mod = importlib.import_module(GOV_MODULE_MAP[cmd])
    mod.main()


if __name__ == "__main__":
    main()
