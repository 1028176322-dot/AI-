# -*- coding: utf-8 -*-
"""Governance 共享辅助：路径解析、YAML 加载、权限判定。"""
import os
import sys
import fnmatch

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _yaml_lite as Y


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return Y.load(f.read())


def find_platform_root():
    # tools/<this>.py -> platform/AI-Creative-Platform
    return os.path.dirname(HERE)


def find_workspace_root():
    # platform/AI-Creative-Platform -> workspace root
    return os.path.dirname(os.path.dirname(find_platform_root()))


def find_project(ws_root, project_id):
    ws = load_yaml(os.path.join(ws_root, "workspace.yaml"))
    for rel in (ws.get("workspace", {}).get("projects") or []):
        pdir = os.path.join(ws_root, rel)
        py = os.path.join(pdir, "project.yaml")
        if os.path.isfile(py):
            try:
                d = load_yaml(py)
            except Exception:
                continue
            pid = d.get("id") or (d.get("project") or {}).get("id")
            if pid == project_id:
                return pdir, d
    return None, None


def _fnmatch_any(path, patterns):
    for p in (patterns or []):
        pp = p.rstrip("/")
        if fnmatch.fnmatch(path, pp) or fnmatch.fnmatch(path, pp + "/*"):
            return True
    return False


def check_permission(role, target):
    """返回 (allowed: bool, reason: str)。"""
    plat = find_platform_root()
    pol = load_yaml(os.path.join(plat, "core", "policies", "permissions.policy.yaml"))
    roles = pol.get("roles", {})
    if role not in roles:
        return False, "unknown role: %s" % role
    r = roles[role]
    deny = r.get("deny_write", [])
    allow = r.get("allow_write", [])
    if _fnmatch_any(target, deny):
        return False, "denied by deny_write of role %s" % role
    if _fnmatch_any(target, allow):
        return True, "allowed by allow_write of role %s" % role
    return False, "target not in allow_write for role %s" % role


def _scalar(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    return v


def dump_block(d, prefix=""):
    """极简 block YAML 序列化（dict / list-of-scalar / list-of-dict / scalar）。

    注意：列表中的 dict 项必须把首个键提到 dash 同行（"- key: val"），
    否则 _yaml_lite 在 strip 后会把 "  - " 变成 "-"，无法识别为序列项。
    """
    lines = []
    if isinstance(d, dict):
        for k, v in d.items():
            if isinstance(v, (dict, list)):
                lines.append("%s%s:" % (prefix, k))
                lines.append(dump_block(v, prefix + "  "))
            else:
                lines.append("%s%s: %s" % (prefix, k, _scalar(v)))
    elif isinstance(d, list):
        if not d:
            lines.append("%s[]" % prefix)
        child_pfx = prefix + "  "
        for item in d:
            if isinstance(item, dict):
                sub = dump_block(item, child_pfx).split("\n")
                first = sub[0][len(child_pfx):] if (sub and sub[0].startswith(child_pfx)) else (sub[0] if sub else "")
                lines.append("%s- %s" % (prefix, first))
                lines.extend(sub[1:])
            elif isinstance(item, list):
                lines.append("%s- " % prefix)
                lines.append(dump_block(item, child_pfx))
            else:
                lines.append("%s- %s" % (prefix, _scalar(item)))
    else:
        lines.append("%s%s" % (prefix, _scalar(d)))
    return "\n".join(lines)
