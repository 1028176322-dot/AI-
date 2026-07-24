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

HERE = os.path.dirname(os.path.abspath(__file__))
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
    genre = (data.get("template") or {}).get("id")
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
        results, _ = check_compat(proot, platform_root, versions)
        for name, (sym, detail) in results.items():
            _print_result(name, sym, detail)
            if sym == FAIL:
                overall_fail = True

        _print_block("资产治理（项目内容资产体检）")
        try:
            import asset_manager as _am
            arep = _am.govern(proot, write=False)
            agd = (arep.get("gate") or {}).get("decision", "proceed")
            if agd == "block":
                _print_result("AssetGov", FAIL, "引用断裂：%s" % "；".join(arep["gate"]["reasons"][:3]))
                overall_fail = True
            elif agd == "caution":
                _print_result("AssetGov", WARN, "软问题 %d 项（健康分 %s）" % (
                    len(arep["gate"]["reasons"]), arep["composite"]["health"]))
            else:
                _print_result("AssetGov", PASS, "健康分 %s" % arep["composite"]["health"])
        except Exception as _e:
            _print_result("AssetGov", WARN, "自检异常：%s" % _e)

        _print_block("图谱可视化（Phase 3-5 自检）")
        try:
            import graph_viz as _gv
            gvrep = _gv.govern(proot, write=False)
            gvgd = (gvrep.get("gate") or {}).get("decision", "proceed")
            if gvgd == "block":
                _print_result("GraphGov", FAIL, "图谱结构损坏：%s" % "；".join(gvrep["gate"]["reasons"][:3]))
                overall_fail = True
            elif gvgd == "caution":
                _print_result("GraphGov", WARN, "软问题 %d 项（健康分 %s）" % (
                    len(gvrep["gate"]["reasons"]), gvrep["composite"]["health"]))
            else:
                _print_result("GraphGov", PASS, "健康分 %s（%d 节点/%d 边）" % (
                    gvrep["composite"]["health"], gvrep["response"]["nodes"], gvrep["response"]["edges"]))
        except Exception as _e:
            _print_result("GraphGov", WARN, "自检异常：%s" % _e)

        _print_block("市场分析（Phase 3-6 自检）")
        try:
            import market as _mk
            mkrep = _mk.govern(platform_root, proot, write=False)
            mkgd = (mkrep.get("gate") or {}).get("decision", "proceed")
            if mkgd == "block":
                _print_result("MarketGov", FAIL, "市场配置损坏：%s" % "；".join(mkrep["gate"]["reasons"][:3]))
                overall_fail = True
            elif mkgd == "caution":
                _print_result("MarketGov", WARN, "软问题 %d 项（健康分 %s）" % (
                    len(mkrep["gate"]["reasons"]), mkrep["composite"]["health"]))
            else:
                _print_result("MarketGov", PASS, "健康分 %s（%d 信号）" % (
                    mkrep["composite"]["health"], mkrep["response"]["signals"]))
        except Exception as _e:
            _print_result("MarketGov", WARN, "自检异常：%s" % _e)

    _print_block("内存治理（platform/memory/ 体检）")
    try:
        import memory_governor as _mg
        rep = _mg.govern(platform_root, write=False)
        gd = (rep.get("gate") or {}).get("decision", "proceed")
        if gd == "block":
            _print_result("MemoryGov", FAIL, "结构错配：%s" % "；".join(rep["gate"]["reasons"][:3]))
            overall_fail = True
        elif gd == "caution":
            _print_result("MemoryGov", WARN, "软问题 %d 项（健康分 %s）" % (
                len(rep["gate"]["reasons"]), rep["composite"]["health"]))
        else:
            _print_result("MemoryGov", PASS, "健康分 %s" % rep["composite"]["health"])
    except Exception as _e:
        _print_result("MemoryGov", WARN, "自检异常：%s" % _e)

    _print_block("模型布线器（Phase 3-1 自检）")
    try:
        import model_router as _mr
        mrep = _mr.govern(platform_root, write=False)
        mgd = (mrep.get("gate") or {}).get("decision", "proceed")
        if mgd == "block":
            _print_result("ModelGov", FAIL, "无可用模型/配置损坏：%s" % "；".join(mrep["gate"]["reasons"][:3]))
            overall_fail = True
        elif mgd == "caution":
            _print_result("ModelGov", WARN, "软问题 %d 项（健康分 %s）" % (
                len(mrep["gate"]["reasons"]), mrep["composite"]["health"]))
        else:
            _print_result("ModelGov", PASS, "健康分 %s" % mrep["composite"]["health"])
    except Exception as _e:
        _print_result("ModelGov", WARN, "自检异常：%s" % _e)

    _print_block("多项目管理（Phase 3-2 自检）")
    try:
        import multi_project as _mp
        mprep = _mp.govern(platform_root, write=False)
        mpgd = (mprep.get("gate") or {}).get("decision", "proceed")
        if mpgd == "block":
            _print_result("MultiProjGov", FAIL, "注册表损坏/项目路径缺失：%s" % "；".join(mprep["gate"]["reasons"][:3]))
            overall_fail = True
        elif mpgd == "caution":
            _print_result("MultiProjGov", WARN, "软问题 %d 项（健康分 %s）" % (
                len(mprep["gate"]["reasons"]), mprep["composite"]["health"]))
        else:
            _print_result("MultiProjGov", PASS, "健康分 %s（%d 项目）" % (
                mprep["composite"]["health"], mprep["response"]["projects"]))
    except Exception as _e:
        _print_result("MultiProjGov", WARN, "自检异常：%s" % _e)

    _print_block("实验系统（Phase 3-3 自检）")
    try:
        import experiment as _exp
        exrep = _exp.govern(platform_root, write=False)
        exgd = (exrep.get("gate") or {}).get("decision", "proceed")
        if exgd == "block":
            _print_result("ExpGov", FAIL, "实验定义损坏：%s" % "；".join(exrep["gate"]["reasons"][:3]))
            overall_fail = True
        elif exgd == "caution":
            _print_result("ExpGov", WARN, "软问题 %d 项（健康分 %s）" % (
                len(exrep["gate"]["reasons"]), exrep["composite"]["health"]))
        else:
            _print_result("ExpGov", PASS, "健康分 %s（%d 实验）" % (
                exrep["composite"]["health"], exrep["response"]["experiments"]))
    except Exception as _e:
        _print_result("ExpGov", WARN, "自检异常：%s" % _e)

    _print_block("BI 分析（Phase 3-4 自检）")
    try:
        import bi as _bi
        birep = _bi.govern(platform_root, write=False)
        bigd = (birep.get("gate") or {}).get("decision", "proceed")
        if bigd == "block":
            _print_result("BiGov", FAIL, "仪表盘定义损坏：%s" % "；".join(birep["gate"]["reasons"][:3]))
            overall_fail = True
        elif bigd == "caution":
            _print_result("BiGov", WARN, "软问题 %d 项（健康分 %s）" % (
                len(birep["gate"]["reasons"]), birep["composite"]["health"]))
        else:
            _print_result("BiGov", PASS, "健康分 %s（%d 仪表盘）" % (
                birep["composite"]["health"], birep["response"]["dashboards"]))
    except Exception as _e:
        _print_result("BiGov", WARN, "自检异常：%s" % _e)

    print("")
    if overall_fail:
        print("结果：存在 FAIL —— 平台/项目不兼容，请先修复后再运行。")
        sys.exit(1)
    print("结果：全部 PASS（无 FAIL）。")
    sys.exit(0)


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
    tpl = os.path.join(platform_root, "templates", genre)
    if not os.path.isdir(tpl):
        die("类型模板不存在：templates/%s" % genre, 2)
    name = args.name
    pid = args.id or ("novel-%s" % re.sub(r"\W+", "-", name).lower())
    proot = os.path.normpath(os.path.join(ws_root, "projects", name))
    if os.path.exists(proot):
        die("项目目录已存在：%s" % proot, 2)
    os.makedirs(proot)
    # 读模板版本
    tdata = load_yaml(os.path.join(tpl, "profile.yaml")) or {}
    tver = str(tdata.get("schema_version", "0"))
    # 生成 project.yaml
    project_yaml = (
        "project:\n"
        "  id: %s\n"
        "  name: %s\n"
        "  type: %s\n"
        "  status: active\n\n"
        "requires:\n"
        "  platform: \">=2.1.0\"\n"
        "  nkb_schema: \">=1.2.0\"\n"
        "  contracts: \">=1.0.0\"\n"
        "  templates:\n"
        "    %s: \">=%s\"\n\n"
        "template:\n"
        "  id: %s\n"
        "  version: %s\n\n"
        "plugins:\n"
        "  planner: planner.default@1.2.0\n"
        "  context: context.runtime@2.0.0\n"
        "  workflow: workflow.novel@1.4.0\n"
        "  review: review.four-pillars@4.3.0\n\n"
        "capabilities:\n"
        "  narrative: capability.narrative.default@2.0.0\n"
        "  character: capability.character.default@1.5.0\n"
        "  dialogue: capability.dialogue.ancient@1.3.0\n"
        "  battle: capability.battle.xuanhuan@2.1.0\n"
        "  emotion: capability.emotion.commercial@1.2.0\n"
        "  description: capability.description.ancient@1.1.0\n\n"
        "paths:\n"
        "  nkb: ./NKB\n"
        "  outline: ./outline.md\n"
        "  chapters: ./txt\n"
        "  artifacts: ./artifacts\n"
        "  overrides: ./overrides\n"
        "  memory: ./memory/project\n\n"
        "gates:\n"
        "  editor_score: 80\n"
        "  consistency_index: 0.95\n"
        "  reader_index: 60\n"
        "  payment_intent: 60\n"
        "  max_loop: 5\n"
    ) % (pid, name, genre, genre, tver, genre, tver)
    with open(os.path.join(proot, "project.yaml"), "w", encoding="utf-8") as f:
        f.write(project_yaml)
    # 空 NKB（从模板 schema 扩展字段读取字段名）
    nkb_dir = os.path.join(proot, "NKB")
    os.makedirs(nkb_dir)
    # 基础 11 组件
    base_components = ["Canon", "Characters", "Timeline", "WorldState", "Events",
                       "Foreshadow", "Assets", "Terminology", "StoryState",
                       "ReaderState", "Graph"]
    ext_path = os.path.join(tpl, "nkb-schema-extension.yaml")
    ext_fields = []
    if os.path.isfile(ext_path):
        ext = load_yaml(ext_path) or {}
        # extends / add_fields 仅作信息记录
        ext_fields = list((ext.get("add_fields") or {}).keys())
    idx_lines = ["# NKB 索引（schema_version 1.2.0）", "schema_version: 1.2.0",
                 "project_id: %s" % pid, "", "components:"]
    for c in base_components + ext_fields:
        fname = "%s.yaml" % c
        with open(os.path.join(nkb_dir, fname), "w", encoding="utf-8") as f:
            f.write("schema_version: 1.2.0\nproject_id: %s\nrecords: []\n" % pid)
        idx_lines.append("  - %s" % fname)
    with open(os.path.join(nkb_dir, "NKB.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(idx_lines) + "\n")
    # 空 Derived
    with open(os.path.join(nkb_dir, "Derived.yaml"), "w", encoding="utf-8") as f:
        f.write("schema_version: 1.2.0\nproject_id: %s\nrecords: []\n" % pid)
    # overrides / metrics / artifacts / memory
    for d in ("overrides", "metrics", "artifacts", "memory/project"):
        os.makedirs(os.path.join(proot, d), exist_ok=True)
        with open(os.path.join(proot, d, "README.md"), "w", encoding="utf-8") as f:
            f.write("# %s\n\n（项目私有目录，由 bootstrap 校验）\n" % d)
    # 更新 workspace.yaml 登记
    ws_path = os.path.join(ws_root, "workspace.yaml")
    cur = load_yaml(ws_path)
    w = cur.get("workspace", cur)
    plist = w.get("projects", []) or []
    new_rel = "./projects/%s" % name
    if new_rel not in plist:
        plist.append(new_rel)
        w["projects"] = plist
        # 仅追加一行，保留注释与结构
        _append_project_to_workspace(ws_path, new_rel)
    print("✓ 已脚手架项目：%s" % proot)
    print("  请运行：python tools/platform_cli.py bootstrap")
    sys.exit(0)


def _append_project_to_workspace(ws_path, new_rel):
    # 仅追加一行到 projects 列表，保留注释与既有结构（不整文件重写）
    with open(ws_path, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")
    proj_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "projects:":
            proj_idx = i
            break
    if proj_idx is None:
        # 兜底：直接附加到文件尾
        lines.append("workspace:")
        lines.append("  platform: ./platform/AI-Creative-Platform")
        lines.append("  projects:")
        lines.append("    - %s" % new_rel)
        with open(ws_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return
    indent = "    "
    last_item_idx = proj_idx
    for j in range(proj_idx + 1, len(lines)):
        s = lines[j]
        if s.strip().startswith("- "):
            last_item_idx = j
            indent = s[: len(s) - len(s.lstrip(" "))]
        elif s.strip() == "":
            continue
        else:
            # 下一个顶层键或注释结束列表
            if j > proj_idx + 1:
                break
    lines.insert(last_item_idx + 1, "%s- %s" % (indent, new_rel))
    with open(ws_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


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
    sub.add_parser("doctor", help="只读诊断兼容性，退出码反映健康度")
    c = sub.add_parser("check", help="单项目兼容性检查")
    c.add_argument("--project", help="项目 id 或相对路径")
    sub.add_parser("version", help="打印版本目录")
    sub.add_parser("list", help="列出登记项目")
    ip = sub.add_parser("init-project", help="脚手架新项目")
    ip.add_argument("--name", required=True, help="项目目录名（如 小说B）")
    ip.add_argument("--type", required=True, help="类型模板 id（如 xuanhuan）")
    ip.add_argument("--id", help="项目 id（默认 novel-<name>）")

    # ── 治理层（AI 执行控制）──
    gs = sub.add_parser("session", help="Session Bootstrap：生成会话清单（强制入口）")
    gs.add_argument("--role", required=True)
    gs.add_argument("--project", required=True)

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

    gm2 = sub.add_parser("model", help="模型布线器：任务→模型路由与降级链（resolve/validate）")
    gm2.add_argument("--platform-root", required=True)
    gm2.add_argument("rest", nargs=argparse.REMAINDER)

    gpj = sub.add_parser("projects", help="多项目管理：跨项目注册/隔离解析/统一 dispatch（list/register/query/dispatch/validate）")
    gpj.add_argument("--platform-root", required=True)
    gpj.add_argument("rest", nargs=argparse.REMAINDER)

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
                      "init", "charter", "psrc", "genesis", "ready",
                      "status", "task", "ver", "impact", "quality", "reader", "memory", "asset", "model", "projects", "exp", "bi", "graph", "market"):
        _delegate_gov(args.cmd, args)
    else:
        die("未知子命令：%s" % args.cmd, 2)


def _delegate_gov(cmd, args):
    """把治理子命令委托给 tools/ 下对应模块（复用其 main + argparse）。

    直接沿用用户原始命令行 flag（sys.argv[2:]），避免 dest 名与模块不一致。
    platform <cmd> --flag a  =>  <module> --flag a
    """
    import importlib
    mod_map = {
        "session": "session_bootstrap",
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
        "exp": "experiment",
        "bi": "bi",
        "graph": "graph_viz",
        "market": "market",
    }
    sys.argv = [mod_map[cmd]] + sys.argv[2:]
    mod = importlib.import_module(mod_map[cmd])
    mod.main()


if __name__ == "__main__":
    main()
