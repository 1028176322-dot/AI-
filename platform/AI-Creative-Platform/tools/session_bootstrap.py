# -*- coding: utf-8 -*-
"""Session Bootstrap: 加载平台+项目，生成 Session Manifest。未生成前禁止写操作。"""
import os
import sys
import argparse
import datetime
import glob

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _gov


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--role", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--workspace", default=None)
    args = ap.parse_args()

    ws_root = args.workspace or _gov.find_workspace_root()
    plat_root = _gov.find_platform_root()

    role_file = os.path.join(plat_root, "core", "session", "ROLE_REGISTRY.yaml")
    if not os.path.isfile(role_file):
        print("ERROR: ROLE_REGISTRY.yaml missing at %s" % role_file)
        sys.exit(2)
    roles = _gov.load_yaml(role_file).get("roles", {})
    if args.role not in roles:
        print("ERROR: unknown role '%s' (known: %s)" % (args.role, ", ".join(roles.keys())))
        sys.exit(2)

    pdir, pdata = _gov.find_project(ws_root, args.project)
    if pdir is None:
        print("ERROR: project '%s' not found in workspace" % args.project)
        sys.exit(2)

    ver_file = os.path.join(plat_root, "registry", "versions.yaml")
    versions = _gov.load_yaml(ver_file) if os.path.isfile(ver_file) else {}
    core = versions.get("core", {}) if isinstance(versions.get("core"), dict) else {}

    plat_ver = core.get("platform", "unknown")
    con_ver = core.get("contract", "unknown")
    req = pdata.get("requires", {})
    proj_ver = (pdata.get("template") or {}).get("version") or (req.get("templates") or {}).get("xuanhuan", "unknown")
    pol_ver = "1.3.0"

    now = datetime.datetime.now()
    stamp = now.strftime("%Y%m%d")
    sess_dir = os.path.join(pdir, "sessions")
    os.makedirs(sess_dir, exist_ok=True)
    n = len(glob.glob(os.path.join(sess_dir, "SES-%s-*.yaml" % stamp))) + 1
    sid = "SES-%s-%03d" % (stamp, n)

    manifest = {
        "session": {
            "id": sid,
            "project_id": args.project,
            "role": args.role,
            "platform_version": plat_ver,
            "project_version": proj_ver,
            "policy_version": pol_ver,
            "contracts_version": con_ver,
            "created": now.strftime("%Y-%m-%dT%H:%M:%S"),
            "loaded": {
                "constitution": True,
                "specification": True,
                "project_yaml": True,
                "nkb": True,
                "role_policy": True,
                "workflow": True,
            },
        },
        "permissions": {
            "read": roles[args.role].get("may_write", []) + ["NKB/**", "outline/**", "chapters/**"],
            "write": roles[args.role].get("may_write", []),
            "forbidden": roles[args.role].get("may_not_write", []),
        },
        # ── Phase4 Step3.3：任务系统强制模式（从 project.yaml 读取）──
        "task_mode": _derive_task_mode(pdata),
        # ── 单 Agent 执行策略（Phase5）：锁定运行时，不可变字段见 locks ──
        "agent_runtime": _derive_agent_runtime(pdata),
        "locks": [
            "agent_runtime.agent_mode",
            "agent_runtime.subagents_enabled",
            "agent_runtime.delegation_enabled",
            "agent_runtime.background_execution_enabled",
            "agent_runtime.max_active_agents",
        ],
    }
    out = os.path.join(sess_dir, "%s.yaml" % sid)
    with open(out, "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(manifest))
    print("SESSION MANIFEST: %s" % out)
    print("role=%s project=%s platform=%s policy=%s contracts=%s" % (args.role, args.project, plat_ver, pol_ver, con_ver))
    print("task_mode.enforced=%s direct_execution_allowed=%s" % (
        manifest["task_mode"]["enforced"], manifest["task_mode"]["direct_execution_allowed"]))
    _ar = manifest["agent_runtime"]
    print("agent_runtime.mode=%s max_agents=%d subagents=%s delegation=%s bg=%s" % (
        _ar["agent_mode"], _ar["max_active_agents"], _ar["subagents_enabled"],
        _ar["delegation_enabled"], _ar["background_execution_enabled"]))
    print("OK")
    sys.exit(0)


def _derive_task_mode(pdata):
    """从 project.yaml 的 task_system 段推导任务强制模式。"""
    ts = (pdata or {}).get("task_system") or {}
    mode = ts.get("enforcement_mode", "off")
    return {
        "enforced": mode in ("strict", "warn"),
        "enforcement_mode": mode,
        "direct_execution_allowed": False,
    }


def _derive_agent_runtime(pdata):
    """从 project.yaml 的 runtime 段推导单 Agent 运行时锁定（不可变）。"""
    rt = (pdata or {}).get("runtime") or {}
    conc = rt.get("concurrency") or {}

    def _flag(section, key, default=False):
        v = rt.get(section)
        if isinstance(v, dict):
            return bool(v.get(key, default))
        return default

    return {
        "primary_agent": "current_session",
        "agent_mode": rt.get("agent_mode", "single"),
        "subagents_enabled": _flag("subagents", "enabled"),
        "delegation_enabled": _flag("delegation", "enabled"),
        "parallel_execution_enabled": False,
        "background_execution_enabled": _flag("background", "enabled"),
        "max_active_agents": int(conc.get("max_active_agents", 1)),
    }


def load_session(project_root):
    """返回项目最新一份 Session Manifest dict；无则返回 None。"""
    sdir = os.path.join(project_root, "sessions")
    if not os.path.isdir(sdir):
        return None
    files = sorted(glob.glob(os.path.join(sdir, "SES-*.yaml")), reverse=True)
    for f in files:
        try:
            d = _gov.load_yaml(f)
        except Exception:
            continue
        if isinstance(d, dict) and "session" in d:
            return d
    return None


def require_session(project_root, agent=None):
    """未 bootstrap（无 Session Manifest）时禁止项目工具运行。

    返回 manifest；若不存在则抛 RuntimeError（调用方转 REJECTED）。
    """
    d = load_session(project_root)
    if not d:
        raise RuntimeError(
            "NO_ACTIVE_SESSION: 项目 %s 无 Session Manifest（sessions/SES-*.yaml）。"
            "请先运行 `platform session --role <role> --project <project>` 建立会话，"
            "再执行项目写/变更类工具。" % project_root)
    return d


if __name__ == "__main__":
    main()
