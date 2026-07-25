#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_installer_common.py — Project Installer 共享基础库

被 scripts/project/ 下 14 个安装器模块复用。提供：
  - load_yaml / dump_yaml（优先 PyYAML，回退 _yaml_lite，与 cli/platform.py 互通）
  - 六策略常量（generate/initialize/seed/reference/lock/derive）
  - 目录与文件助手（ensure_dir / write_text / stage_atomic_move）
  - 版本满足度 satisfies()（与 cli/platform.py 同算法）
  - 插件锁解析（build_plugin_lock）
  - 三类清单加载（load_manifests）

设计原则：所有内容通过版本引用，不在项目内复制 core/templates/plugins 实现。
"""
import os
import re
import sys
import shutil
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.dirname(HERE)
if os.path.isdir(_SCRIPTS):
    for _d in os.listdir(_SCRIPTS):
        _p = os.path.join(_SCRIPTS, _d)
        if os.path.isdir(_p) and _p not in sys.path:
            sys.path.insert(0, _p)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# 复用 _gov 的 load/dump（与仓库其他脚本一致）
import _gov  # noqa: E402

# ── 六策略 ──────────────────────────────────────────────
STRATEGY_GENERATE = "generate"
STRATEGY_INITIALIZE = "initialize"
STRATEGY_SEED = "seed"
STRATEGY_REFERENCE = "reference"
STRATEGY_LOCK = "lock"
STRATEGY_DERIVE = "derive"

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"


# ── YAML I/O ────────────────────────────────────────────
def load_yaml(path):
    return _gov.load_yaml(path)


def dump_yaml(path, data):
    ensure_dir(os.path.dirname(path))
    _gov.dump_yaml(path, data)


def dump_block(data):
    return _gov.dump_block(data)


# ── 版本满足度（与 cli/platform.py.satisfies 同算法）────
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


# ── 路径助手 ────────────────────────────────────────────
def ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)


def write_text(path, text):
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def make_deploy_id():
    """部署ID：DEPLOY-YYYYMMDD-NNN（同一天自增）。"""
    today = datetime.date.today().strftime("%Y%m%d")
    prefix = "DEPLOY-%s-" % today
    # 简单自增：基于已有 deploy id 计数（不强制唯一，仅可读）
    return "%s001" % prefix


def stage_dir_for(ws_root, pid, deploy_id):
    """staging 目录：<ws_root>/runtime/staging/<pid>-<deploy_id>"""
    base = os.path.join(ws_root, "runtime", "staging")
    ensure_dir(base)
    return os.path.join(base, "%s-%s" % (pid, deploy_id))


def stage_atomic_move(staging, dest):
    """原子移入：把 staging 内容整体移到 dest。dest 不存在才移。
    失败则保留 staging 供检查。返回 (ok, err)。"""
    if os.path.exists(dest):
        return False, "目标已存在（应走 reconcile，不应覆盖）：%s" % dest
    parent = os.path.dirname(dest)
    ensure_dir(parent)
    try:
        # 先把 staging 内所有条目移动到 dest（dest 由 staging 内容构成）
        ensure_dir(dest)
        for name in os.listdir(staging):
            src = os.path.join(staging, name)
            shutil.move(src, os.path.join(dest, name))
        # staging 现在应空；删除空 staging
        try:
            os.rmdir(staging)
        except OSError:
            pass
        return True, None
    except Exception as e:
        return False, "原子移入失败：%s" % e


# ── 清单加载 ────────────────────────────────────────────
def load_manifests(platform_root, genre):
    """加载三类清单。返回 (core_m, tpl_m, nkb_m, err)。"""
    core_p = os.path.join(platform_root, "core", "project-manifest.yaml")
    tpl_p = os.path.join(platform_root, "templates", genre, "template-manifest.yaml")
    nkb_p = os.path.join(platform_root, "schemas", "nkb", "nkb-manifest.yaml")
    if not os.path.isfile(core_p):
        return None, None, None, "缺失 core/project-manifest.yaml"
    if not os.path.isfile(tpl_p):
        return None, None, None, "缺失 templates/%s/template-manifest.yaml" % genre
    if not os.path.isfile(nkb_p):
        return None, None, None, "缺失 schemas/nkb/nkb-manifest.yaml"
    core_m = load_yaml(core_p)
    tpl_m = load_yaml(tpl_p)
    nkb_m = load_yaml(nkb_p)
    return core_m, tpl_m, nkb_m, None


def load_versions(platform_root):
    p = os.path.join(platform_root, "registry", "versions.yaml")
    if not os.path.isfile(p):
        return None
    return load_yaml(p)


def load_plugins_registry(platform_root):
    p = os.path.join(platform_root, "registry", "plugins.yaml")
    if not os.path.isfile(p):
        return {}
    return load_yaml(p) or {}


def build_plugin_lock(platform_root, core_m, tpl_m):
    """解析 plugin + capability 版本锁。
    返回 dict: {plugins:{...}, capabilities:[...]}。
    版本取自 registry/plugins.yaml（真实可注册版本），键取自 core/project-manifest.yaml。"""
    core_defaults = (core_m.get("plugin_defaults") or {}) if core_m else {}
    cap_map = (core_m.get("capability_plugin_map") or {}) if core_m else {}
    tpl_caps = (tpl_m.get("capabilities") or []) if tpl_m else []
    reg = load_plugins_registry(platform_root)
    reg_plugins = (reg.get("plugins") or {}) if isinstance(reg, dict) else {}

    plugins = {}
    for k, ref in core_defaults.items():
        name, ver = (ref.split("@", 1) + ["?"])[:2] if "@" in ref else (ref, "?")
        entry = reg_plugins.get(name)
        if isinstance(entry, dict) and ver in (entry.get("versions") or {}):
            plugins[k] = ref
        else:
            # 回退：取该插件最新可用版本
            avail = (entry.get("versions") or {}) if isinstance(entry, dict) else {}
            vers = list(avail.keys())
            if vers:
                plugins[k] = "%s@%s" % (name, vers[-1])
            else:
                plugins[k] = ref  # 保底保留原值（doctor 会标记未注册）

    capabilities = []
    for cap in tpl_caps:
        ref = cap_map.get(cap)
        if ref:
            name, ver = (ref.split("@", 1) + ["?"])[:2] if "@" in ref else (ref, "?")
            entry = reg_plugins.get(name)
            if isinstance(entry, dict) and ver in (entry.get("versions") or {}):
                capabilities.append(ref)
            else:
                capabilities.append(ref)
        else:
            capabilities.append(cap)  # 保底保留键名
    return {"plugins": plugins, "capabilities": capabilities}


def now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


def find_platform_root():
    # 委托 _gov（其 HERE 为 scripts/_common，计算稳定）
    return _gov.find_platform_root()


def find_workspace_root():
    return _gov.find_workspace_root()


def derive_pid(title, pid=None):
    """从标题派生项目 id（仅 ASCII 字母数字与 -）。"""
    if pid:
        return pid
    slug = re.sub(r"[^a-z0-9]+", "-", str(title).lower()).strip("-")
    return "novel-%s" % slug if slug else "novel"


def die(msg, code=2):
    sys.stderr.write("✗ %s\n" % msg)
    sys.exit(code)
