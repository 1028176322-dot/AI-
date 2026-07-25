#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""project_template.py — Phase 3-7 项目模板（Project Templates）

从 genre 模板脚手架新项目实例（project.yaml + 空 NKB + sources + overrides +
lifecycle），并落地两处集成：
  - P3-6 市场钩子：在 sources/research/market/ 生成投放区 + 填表模板（.yaml.example，
    不污染 market.ingest）。
  - P3-2 多项目注册：写 registry/projects.yaml + 更新 workspace.yaml。

零依赖：复用同目录 _gov / _yaml_lite / multi_project。
不做创作，只做脚手架与注册。
"""
import os
import re
import sys
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
# [Phase2] 把 scripts 各分组目录加入 sys.path，保持跨组裸名 import 可用
_SCRIPTS = os.path.dirname(HERE)
if os.path.isdir(_SCRIPTS):
    for _d in os.listdir(_SCRIPTS):
        _p = os.path.join(_SCRIPTS, _d)
        if os.path.isdir(_p) and _p not in sys.path:
            sys.path.insert(0, _p)
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _yaml_lite
import _gov
import multi_project

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")

# 基础 11 NKB 组件（与既有 init-project 保持一致）
_BASE_NKB_COMPONENTS = ["Canon", "Characters", "Timeline", "WorldState", "Events",
                        "Foreshadow", "Assets", "Terminology", "StoryState",
                        "ReaderState", "Graph"]


# ── 模板读取 ────────────────────────────────────────────────
def template_dir(platform_root, genre):
    return os.path.join(platform_root, "templates", genre)


def load_template(platform_root, genre):
    """读取 genre 模板。返回 (dict, err)。err 非空表示不可用。"""
    tpl = template_dir(platform_root, genre)
    if not os.path.isdir(tpl):
        return None, "类型模板不存在：templates/%s" % genre
    profile = _yaml_lite.load_file(os.path.join(tpl, "profile.yaml")) or {}
    ext = {}
    ext_path = os.path.join(tpl, "nkb-schema-extension.yaml")
    if os.path.isfile(ext_path):
        ext = _yaml_lite.load_file(ext_path) or {}
    return {"dir": tpl, "profile": profile, "extension": ext}, None


def derive_pid(name, pid=None):
    if pid:
        return pid
    # 仅保留 ASCII 字母数字，其余（含中文/标点/空格）替换为 -，并去除首尾 -
    # 保证 id 满足 ^[a-z0-9][a-z0-9_-]*$（multi_project.register 强制要求）
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        slug = "novel"
    return "novel-%s" % slug


# ── 脚手架 ──────────────────────────────────────────────────
def scaffold(platform_root, ws_root, name, genre, pid=None, write=True):
    """脚手架新项目实例。返回 (ok, errors, proot)。write=False 仅校验不落盘。"""
    errors = []
    tpl, terr = load_template(platform_root, genre)
    if terr:
        return False, [terr], None
    pid = derive_pid(name, pid)
    if not _ID_RE.match(str(pid)):
        return False, ["id 非法（须 ^[a-z0-9][a-z0-9_-]*$）"], None
    proot = os.path.normpath(os.path.join(ws_root, "projects", name))
    if os.path.exists(proot):
        return False, ["项目目录已存在：%s" % proot], None
    if not write:
        return True, [], proot

    os.makedirs(proot)
    tver = str((tpl["profile"] or {}).get("schema_version", "0"))
    _write_project_yaml(proot, pid, name, genre, tver, tpl.get("profile") or {})

    # 空 NKB（含模板扩展字段）
    nkb_dir = os.path.join(proot, "NKB")
    os.makedirs(nkb_dir)
    ext = (tpl["extension"] or {})
    add_fields = ext.get("add_fields") or {}
    if not isinstance(add_fields, dict):
        # _yaml_lite 可能把 flow map `{}` 解析成字符串，做防御
        add_fields = {}
    ext_fields = list(add_fields.keys())
    _write_nkb(nkb_dir, pid, _BASE_NKB_COMPONENTS + ext_fields)

    # 市场钩子（P3-6）
    seed_market_hook(proot, genre)

    # overrides / metrics / artifacts / memory / lifecycle
    for d in ("overrides", "metrics", "artifacts", "memory/project", "lifecycle"):
        dd = os.path.join(proot, d)
        os.makedirs(dd, exist_ok=True)
        with open(os.path.join(dd, "README.md"), "w", encoding="utf-8") as f:
            f.write("# %s\n\n（项目私有目录，由 bootstrap 校验）\n" % d)

    return True, [], proot


# 平台级基线（题材无关，genre 模板通常不覆盖；profile.defaults 可局部覆盖）
_PLATFORM_BASE_DEFAULTS = {
    "plugins": {
        "planner": "planner.default@1.2.0",
        "context": "context.runtime@2.0.0",
        "workflow": "workflow.novel@1.4.0",
        "review": "review.four-pillars@4.3.0",
    },
    "gates": {
        "editor_score": 80,
        "consistency_index": 0.95,
        "reader_index": 60,
        "payment_intent": 60,
        "max_loop": 5,
    },
    "capabilities": [
        "capability.narrative.default@2.0.0",
        "capability.character.default@1.5.0",
        "capability.dialogue.ancient@1.3.0",
        "capability.battle.xuanhuan@2.1.0",
        "capability.emotion.commercial@1.2.0",
        "capability.description.ancient@1.1.0",
    ],
}


def _cap_key(cap_str):
    """从 capability 字符串解析映射键：capability.narrative.default@2.0.0 -> narrative。"""
    try:
        body = cap_str.split("capability.", 1)[1].split("@", 1)[0]
        return body.split(".")[0]
    except Exception:
        return cap_str


def _write_project_yaml(proot, pid, name, genre, tver, profile=None):
    """写 project.yaml。题材注入：优先采用模板 profile.defaults 的 gates/capabilities/plugins，
    缺失时回落到平台基线（_PLATFORM_BASE_DEFAULTS）。保证 genre 模板是题材设置的唯一事实源。"""
    profile = profile or {}
    defaults = profile.get("defaults") or {}
    gates = dict(_PLATFORM_BASE_DEFAULTS["gates"])
    gates.update(defaults.get("gates") or {})
    caps = defaults.get("capabilities") or _PLATFORM_BASE_DEFAULTS["capabilities"]
    plugins = dict(_PLATFORM_BASE_DEFAULTS["plugins"])
    plugins.update(defaults.get("plugins") or {})

    display = profile.get("display_name") or genre
    desc = profile.get("description") or ""

    cap_lines = "\n".join("  %s: %s" % (_cap_key(c), c) for c in caps)
    gate_lines = "\n".join("  %s: %s" % (k, v) for k, v in gates.items())
    plugin_lines = "\n".join("  %s: %s" % (k, v) for k, v in plugins.items())

    project_yaml = (
        "# 由 platform init-project 从模板 %s 生成（题材注入：gates/capabilities/plugins）\n"
        "# display_name: %s\n"
        "# description: %s\n"
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
        "%s\n\n"
        "capabilities:\n"
        "%s\n\n"
        "paths:\n"
        "  nkb: ./NKB\n"
        "  outline: ./outline.md\n"
        "  chapters: ./txt\n"
        "  artifacts: ./artifacts\n"
        "  overrides: ./overrides\n"
        "  memory: ./memory/project\n\n"
        "gates:\n"
        "%s\n"
    ) % (genre, display, desc, pid, name, genre, genre, tver, genre, tver,
         plugin_lines, cap_lines, gate_lines)
    with open(os.path.join(proot, "project.yaml"), "w", encoding="utf-8") as f:
        f.write(project_yaml)


def _write_nkb(nkb_dir, pid, components):
    idx_lines = ["# NKB 索引（schema_version 1.2.0）", "schema_version: 1.2.0",
                 "project_id: %s" % pid, "", "components:"]
    for c in components:
        fname = "%s.yaml" % c
        with open(os.path.join(nkb_dir, fname), "w", encoding="utf-8") as f:
            f.write("schema_version: 1.2.0\nproject_id: %s\nrecords: []\n" % pid)
        idx_lines.append("  - %s" % fname)
    with open(os.path.join(nkb_dir, "NKB.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(idx_lines) + "\n")
    # 空 Derived
    with open(os.path.join(nkb_dir, "Derived.yaml"), "w", encoding="utf-8") as f:
        f.write("schema_version: 1.2.0\nproject_id: %s\nrecords: []\n" % pid)


def seed_market_hook(proot, genre):
    """生成 sources/research/market/ 投放区 + 填表模板（.yaml.example，不被 ingest 摄取）。"""
    d = os.path.join(proot, "sources", "research", "market")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "README.md"), "w", encoding="utf-8") as f:
        f.write(
            "# 市场分析钩子（Market Hook）\n\n"
            "本目录为 `%s` 类型项目的市场信号投放区（Phase 3-6 Market Analysis），\n"
            "由 `platform init-project` 自动生成。\n\n"
            "## 用法\n"
            "- 在此放置 `*.yaml` 市场信号：字段 `genre` + `metrics{trend_score, competition, reader_demand}`（均 0..1）。\n"
            "- `TEMPLATE-%s.yaml.example` 为填表模板；复制为 `.yaml` 并填入真实指标后即被 `platform market ingest` 摄取。\n"
            "- `platform market score` 查看机会分；`platform market sync` 写入 NKB Market 组件。\n"
            % (genre, genre)
        )
    example = {
        "schema_version": "1.0.0",
        "genre": genre,
        "source": "market-analyst",
        "metrics": {
            "trend_score": 0.5,
            "competition": 0.5,
            "reader_demand": 0.5,
        },
        "note": "示例占位；请由 market-analyst 替换为真实指标后再改名为 .yaml",
    }
    with open(os.path.join(d, "TEMPLATE-%s.yaml.example" % genre), "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(example) + "\n")
    return d


# ── 多项目注册 ──────────────────────────────────────────────
def register_multi_project(platform_root, ws_root, name, genre, pid=None,
                           proot=None, write=True):
    """向 registry/projects.yaml 注册 + 更新 workspace.yaml。返回 (ok, errors, entry)。"""
    pid = derive_pid(name, pid)
    if proot is None:
        proot = os.path.normpath(os.path.join(ws_root, "projects", name))
    rel = os.path.relpath(proot, platform_root).replace(os.sep, "/")
    entry = {
        "id": pid,
        "name": name,
        "path": rel,
        "type": genre,
        "genre": genre,
        "status": "active",
        "created": datetime.date.today().isoformat(),
    }
    ok, errs, clean = multi_project.register(platform_root, entry, write=write)
    if not ok:
        return False, errs, None
    if write:
        _append_to_workspace(ws_root, "./projects/%s" % name)
    return True, [], clean


def _append_to_workspace(ws_root, new_rel):
    """仅追加一行到 workspace.yaml 的 projects 列表，保留注释与既有结构（不整文件重写）。"""
    ws_path = os.path.join(ws_root, "workspace.yaml")
    with open(ws_path, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")
    proj_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "projects:":
            proj_idx = i
            break
    if proj_idx is None:
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
            if j > proj_idx + 1:
                break
    lines.insert(last_item_idx + 1, "%s- %s" % (indent, new_rel))
    with open(ws_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ── doctor 自检（TemplateGov）──────────────────────────────
def govern(platform_root, write=False):
    """检查模板完整性 + 已注册项目 genre 是否有对应模板。report-style：caution→WARN。"""
    reasons = []
    tpl_root = os.path.join(platform_root, "templates")
    templates = []
    if not os.path.isdir(tpl_root):
        reasons.append("templates/ 目录缺失（init-project 将无法脚手架任何项目）")
    else:
        for g in sorted(os.listdir(tpl_root)):
            # 跳过下划线前缀的内部/遗留目录（如 _legacy_profiles_md）
            if g.startswith("_"):
                continue
            gp = os.path.join(tpl_root, g, "profile.yaml")
            if os.path.isfile(gp):
                templates.append(g)
            else:
                reasons.append("模板 %s 缺 profile.yaml" % g)

    projects = multi_project.list_projects(platform_root)
    missing = []
    for p in projects:
        if not isinstance(p, dict):
            continue
        g = p.get("genre") or p.get("type")
        if g and g not in templates:
            missing.append("%s(genre=%s)" % (p.get("id", "?"), g))
    if missing:
        reasons.append("已注册项目缺对应模板：%s" % "、".join(missing[:5]))

    decision = "caution" if reasons else "proceed"
    health = 100 if not reasons else max(0, 100 - 12 * len(reasons))
    return {
        "gate": {"decision": decision, "reasons": reasons},
        "composite": {"health": health},
        "response": {"templates": len(templates), "projects": len(projects)},
    }


if __name__ == "__main__":
    # 简单 CLI 自检（非主入口；主入口为 platform_cli.py init-project）
    import json
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    print(json.dumps(govern(root), ensure_ascii=False, indent=2))
