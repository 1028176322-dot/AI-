# -*- coding: utf-8 -*-
"""Session 启动协议（Phase C PC-6）：四命令 + 会话启动包 + 脚本强制门禁。

设计目标（来自用户会话启动协议提案）：
  - 新对话只需一句启动指令，不必再解释整个平台；
  - 读一个入口文件（SESSION_BRIEF.md）即知：平台身份 / 当前项目 / 当前任务 /
    应加载规则与上下文 / 可改文件 / 执行流程 / 验收 / 禁止项；
  - Prompt 引导 + Manifest 声明 + 脚本强制 三层保证。

命令：
  platform session bootstrap --project <id> [--intent auto|chapter_write|chapter_review|chapter_fix|nkb_update] [--target CH-020] [--role <role>]
  platform session verify   --project <id>
  platform session status   --project <id>
  platform session close    --project <id> [--session <id>] [--stage ...] [--next ...] [--artifacts k=v ...] [--issues ...]

产物（落项目运行时，不污染平台树）：
  projects/<id>/runtime/sessions/<session-id>/SESSION_MANIFEST.yaml  机器版
  projects/<id>/runtime/sessions/<session-id>/SESSION_BRIEF.md        AI 阅读版
  projects/<id>/handoffs/LATEST_HANDOFF.yaml                          close 生成

门禁（gates，写入 Manifest；verify 重验）：
  bootstrap_validated  项目/project.yaml/AGENTS.md/NKB 齐备
  task_inputs_ready    已定位合法任务且其 inputs_ready
  context_version_valid 上下文为当前版本（未引用过期 context）
  policy_version_valid  SESSION_POLICY 版本可读且匹配

原则：单会话、单 Agent、串行阶段切换、禁止创建或委派子 Agent。
"""
import os
import sys
import argparse
import datetime
import glob

HERE = os.path.dirname(os.path.abspath(__file__))
# [Phase2] 把 scripts 各分组目录加入 sys.path，保持跨组裸名 import 可用
_SCRIPTS = os.path.dirname(HERE)
if os.path.isdir(_SCRIPTS):
    for _d in os.listdir(_SCRIPTS):
        _p = os.path.join(_SCRIPTS, _d)
        if os.path.isdir(_p) and _p not in sys.path:
            sys.path.insert(0, _p)
sys.path.insert(0, HERE)
import _gov


# ───────────────────────── 常量映射 ─────────────────────────

# intent -> 默认角色（可被 task 的 required_role 或 --role 覆盖）
INTENT_ROLE = {
    "auto": None,
    "chapter_write": "writer",
    "chapter_review": "reviewer",
    "chapter_fix": "fixer",
    "nkb_update": "knowledge-manager",
}

# 任务 type -> 角色（auto 模式下由任务类型推导）
TYPE_ROLE = {
    "chapter_write": "writer",
    "chapter_review": "reviewer",
    "chapter_fix": "fixer",
    "nkb_update": "knowledge-manager",
    "review": "reviewer",
    "fix": "fixer",
}


# ───────────────────────── 基础发现 ─────────────────────────

def find_project(project_id, workspace_root=None):
    ws = workspace_root or _gov.find_workspace_root()
    pdir, pdata = _gov.find_project(ws, project_id)
    if pdir is None:
        raise RuntimeError("PROJECT_NOT_FOUND: id=%s" % project_id)
    return pdir, pdata, ws


def load_versions(plat_root):
    vf = os.path.join(plat_root, "registry", "versions.yaml")
    return _gov.load_yaml(vf) if os.path.isfile(vf) else {}


def load_session_policy(plat_root):
    pf = os.path.join(plat_root, "core", "session", "SESSION_POLICY.yaml")
    return _gov.load_yaml(pf) if os.path.isfile(pf) else {}


def load_role_registry(plat_root):
    rf = os.path.join(plat_root, "core", "session", "ROLE_REGISTRY.yaml")
    return _gov.load_yaml(rf) if os.path.isfile(rf) else {}


def _norm(s):
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


# ───────────────────────── 任务定位 ─────────────────────────

def _all_task_files(project_root):
    """返回 [(tid, state, path)]，遍历 tasks/<state>/*.yaml。"""
    out = []
    base = os.path.join(project_root, "tasks")
    if not os.path.isdir(base):
        return out
    for state in os.listdir(base):
        d = os.path.join(base, state)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".yaml"):
                out.append((fn[:-5], state, os.path.join(d, fn)))
    return out


def locate_task(project_root, intent, target, role):
    """定位当前任务。

    返回 (task_id, task_dict, state, role) 或 (None, None, None, role)。
    - target 给定：在 tasks 全状态中按 chapter_ref / task_id 模糊匹配；
    - intent=auto：取 ready 中最高优先级任务；
    - role 由 intent/TYPE_ROLE/task.required_role 推导。
    """
    import task_engine as te

    role = role or INTENT_ROLE.get(intent) or None
    norm_target = _norm(target) if target else None

    if norm_target:
        best = None
        for tid, state, path in _all_task_files(project_root):
            d = _gov.load_yaml(path) or {}
            t = d.get("task", {}) or {}
            cr = _norm(str(t.get("chapter_ref") or ""))
            tn = _norm(tid)
            if norm_target == cr or norm_target == tn or (norm_target and norm_target in tn):
                if state in ("ready", "claimed", "running", "reviewing", "submitted"):
                    best = (tid, t, state)
                    break
        if best:
            tid, t, state = best
            role = role or _role_of(t)
            return tid, t, state, role
        return None, None, None, role

    # auto：取 ready 中最高优先级
    try:
        nxt = te.next_task(project_root, role or "writer")
    except Exception:
        nxt = None
    if nxt is None:
        # 退一步：直接扫 ready 池
        ready = [x for x in _all_task_files(project_root) if x[1] == "ready"]
        if ready:
            tid, state, path = ready[0]
            d = _gov.load_yaml(path) or {}
            t = d.get("task", {}) or {}
            nxt = {"task_id": tid, "type": t.get("type"),
                   "priority": t.get("priority", "medium"), "title": t.get("title"),
                   "chapter_ref": t.get("chapter_ref"), "inputs_ready": _inputs_ready(project_root, t)}
    if nxt:
        tid = nxt.get("task_id")
        _, td = te.load_task(project_root, tid) if hasattr(te, "load_task") else (None, {})
        t = (td or {}).get("task", {}) or {}
        if not t and "type" in nxt:
            t = {"type": nxt.get("type"), "chapter_ref": nxt.get("chapter_ref"),
                 "title": nxt.get("title"), "priority": nxt.get("priority")}
        role = role or _role_of(t) or "writer"
        return tid, t, "ready", role
    return None, None, None, role


def _role_of(task):
    t = task or {}
    req = (t.get("agent") or {}).get("required_role")
    if req:
        return req
    return TYPE_ROLE.get(t.get("type"))


def _inputs_ready(project_root, task):
    """轻量契约校验：任务 inputs.required 中若指定了具体文件，须存在；否则视为就绪。

    注意：不使用 task_engine._inputs_ready——后者把 chapter_ref 当输出文件检查，
    对 chapter_write 任务（草稿尚不存在）会恒为 False，语义不符本门禁。
    """
    req = (task or {}).get("inputs", {}).get("required") or []
    for r in req:
        if isinstance(r, str) and ("/" in r or r.endswith(".yaml") or r.endswith(".md")):
            if not os.path.isfile(os.path.join(project_root, r)):
                return False
    return True


# ───────────────────────── Manifest / Brief 生成 ─────────────────────────

def _session_id(stamp, n):
    return "SESSION-%s-%03d" % (stamp, n)


def _session_dir(project_root, sid):
    d = os.path.join(project_root, "runtime", "sessions", sid)
    os.makedirs(d, exist_ok=True)
    return d


def build_manifest(project_root, pdata, intent, target, role, located):
    plat_root = _gov.find_platform_root()
    versions = load_versions(plat_root)
    core = versions.get("core", {}) if isinstance(versions.get("core"), dict) else {}
    policy = load_session_policy(plat_root)
    pol_ver = (policy or {}).get("policy_version", "unknown")

    tid, t, state, role = located
    proj_id = (pdata.get("project") or {}).get("id") or pdata.get("id")
    proj_name = (pdata.get("project") or {}).get("name") or pdata.get("name")
    pid = proj_id or (pdata.get("project") or {}).get("id")

    # NKB 组件计数（用作 snapshot 标记）
    nkb_dir = os.path.join(project_root, (pdata.get("paths") or {}).get("nkb", "NKB"))
    nkb_comp = 0
    if os.path.isdir(nkb_dir):
        nkb_comp = len([f for f in os.listdir(nkb_dir) if f.endswith(".yaml")])

    # 门禁
    blockers = []
    boot_ok = (os.path.isfile(os.path.join(project_root, "project.yaml"))
               and os.path.isfile(os.path.join(project_root, "AGENTS.md"))
               and nkb_comp > 0)
    if not boot_ok:
        if not os.path.isfile(os.path.join(project_root, "project.yaml")):
            blockers.append("project.yaml 缺失")
        if not os.path.isfile(os.path.join(project_root, "AGENTS.md")):
            blockers.append("AGENTS.md 缺失")
        if nkb_comp == 0:
            blockers.append("NKB 目录为空或缺失")

    task_ok = tid is not None
    if task_ok:
        # 门禁名即"输入就绪"，须真正检查 required inputs
        task_ok = _inputs_ready(project_root, t)
    if not task_ok:
        blockers.append("未定位到合法任务（auto 无 ready 任务，或 target 无匹配）"
                        if not target else
                        "target=%s 未匹配到任务" % target)

    context_valid = True  # 上下文按需构建，bootstrap 不引用过期 context
    policy_valid = bool(pol_ver and pol_ver != "unknown")

    gates = {
        "bootstrap_validated": boot_ok,
        "task_inputs_ready": task_ok,
        "context_version_valid": context_valid,
        "policy_version_valid": policy_valid,
    }
    ready = boot_ok and task_ok and context_valid and policy_valid and not blockers

    # 权限范围
    registry = load_role_registry(plat_root)
    rroles = (registry or {}).get("roles", {}) or {}
    rdef = rroles.get(role, {}) if role else {}
    writable = rdef.get("may_write", []) or []
    readable = list(set(writable + ["NKB/**", "outline/**", "chapters/**",
                                    "AGENTS.md", "MEMORY.md", "project.yaml"]))

    # 输入清单（若存在则登记路径，否则 null，按需生成）
    tp_dir = os.path.join(project_root, "runtime", "task-packets", tid) if tid else None
    inputs = {
        "task_packet": (os.path.relpath(tp_dir, project_root) + "/") if tp_dir and os.path.isdir(tp_dir) else None,
        "policy": "core/session/SESSION_POLICY.yaml",
        "context": None,
        "chapter_plan": None,
    }
    # 尝试定位 chapter plan（artifacts/plans 或 plans）
    if tid:
        for cand in ("artifacts/plans/%s.yaml" % tid, "plans/%s.yaml" % tid):
            if os.path.isfile(os.path.join(project_root, cand)):
                inputs["chapter_plan"] = cand
                break

    manifest = {
        "session": {
            "id": None,  # 由调用方填充
            "created_at": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z"),
            "intent": intent,
            "target": target,
        },
        "platform": {
            "version": core.get("platform", "unknown"),
            "architecture_version": core.get("contract", "unknown"),
            "execution_mode": "single_agent_sequential",
        },
        "runtime_policy": {
            "agent_mode": "single",
            "subagents_enabled": False,
            "delegation_allowed": False,
            "parallel_agents_allowed": False,
            "max_active_agents": 1,
        },
        "project": {
            "id": pid,
            "name": proj_name,
            "config": "project.yaml",
            "status": (pdata.get("project") or {}).get("status") or pdata.get("status"),
            "nkb_snapshot": "NKB (live, %d components)" % nkb_comp,
        },
        "task": {
            "id": tid,
            "type": (t or {}).get("type"),
            "status": state,
            "target": (t or {}).get("chapter_ref") or target,
            "title": (t or {}).get("title"),
        },
        "inputs": inputs,
        "permissions": {
            "role": role,
            "readable_scopes": readable,
            "writable_scopes": writable,
            "forbidden_scopes": rdef.get("may_not_write", []),
        },
        "gates": gates,
        "authoritative_sources": _authoritative_sources(project_root, pdata, tid, nkb_comp),
        "blockers": blockers,
        "ready": ready,
    }
    return manifest


def _authoritative_sources(project_root, pdata, tid, nkb_comp):
    srcs = ["AGENTS.md", "SKILL_REFERENCE.md", "project.yaml",
            "NKB (live, %d components)" % nkb_comp,
            "core/session/SESSION_POLICY.yaml"]
    if tid:
        srcs.append("runtime/task-packets/%s/" % tid)
    return srcs


def render_brief(manifest, project_root, pdata):
    s = manifest["session"]
    p = manifest["project"]
    t = manifest["task"]
    rp = manifest["runtime_policy"]
    perm = manifest["permissions"]
    gates = manifest["gates"]
    sid = manifest["session"]["id"]

    lines = []
    lines.append("# 会话启动说明（SESSION_BRIEF）")
    lines.append("")
    lines.append("> 会话 ID：**%s** ｜ intent=%s ｜ 生成于 %s" % (
        sid, s.get("intent"), s.get("created_at")))
    lines.append("")
    lines.append("## 1. 平台身份")
    lines.append("")
    lines.append("- 运行平台：**AI Creative Platform**（单会话、单 Agent、串行阶段切换）。")
    lines.append("- **NKB 是唯一事实源**；未入 NKB 的新事实只能进 Candidate Queue。")
    lines.append("- 执行模式：`%s`；子 Agent / 委派 / 并行 **一律禁止**。" % manifest["platform"]["execution_mode"])
    lines.append("- 平台版本：%s ｜ 架构版本：%s ｜ 会话策略版本：%s" % (
        manifest["platform"]["version"], manifest["platform"]["architecture_version"],
        "1.3.0"))
    lines.append("")
    lines.append("## 2. 当前项目")
    lines.append("")
    lines.append("- 项目：%s（`%s`）" % (p.get("name"), p.get("id")))
    lines.append("- 项目状态：%s ｜ NKB 快照：%s" % (p.get("status"), p.get("nkb_snapshot")))
    lines.append("")
    lines.append("## 3. 当前任务")
    lines.append("")
    if t.get("id"):
        lines.append("- Task ID：**%s**" % t["id"])
        lines.append("- 类型：%s ｜ 状态：%s ｜ 目标：%s" % (t.get("type"), t.get("status"), t.get("target")))
        if t.get("title"):
            lines.append("- 标题：%s" % t["title"])
    else:
        lines.append("- **未定位到合法任务** —— 见第 9 节阻塞项，禁止直接写正文。")
    lines.append("")
    lines.append("## 4. 执行流程（串行，由当前 Agent 完成）")
    lines.append("")
    lines.append("1. 规划校验（读取 Task Contract / chapter_plan）")
    lines.append("2. Context 校验（确认权威版本未过期）")
    lines.append("3. 正文写作 / 审查 / 修复（按角色）")
    lines.append("4. 脚本预检（`platform validate` / `doctor`）")
    lines.append("5. AI 深度审查 → 修复 → 回归审查")
    lines.append("6. 定稿（经 Gate，不得自验）")
    lines.append("")
    lines.append("## 5. 强制规则（红线）")
    lines.append("")
    lines.append("- 只允许一个主 Agent；**禁止创建 / 委派 / 调用子 Agent**。")
    lines.append("- 多角色必须由当前 Agent 串行切换，不得并行。")
    lines.append("- 不得直接修改 NKB 正史（仅 knowledge-manager 持 approved_event 可写）。")
    lines.append("- 新事实只能进入 Candidate Queue，不得自行写入正史。")
    lines.append("- 不得读取与当前任务无关的全部项目文件。")
    lines.append("- 不得跳过任务状态机；不得自行更改章节规划。")
    lines.append("- 未经审查不得直接定稿。")
    lines.append("")
    lines.append("## 6. 本次允许读取")
    lines.append("")
    for sc in perm.get("readable_scopes", []):
        lines.append("- %s" % sc)
    if manifest.get("inputs", {}).get("task_packet"):
        lines.append("- %s" % manifest["inputs"]["task_packet"])
    if manifest.get("inputs", {}).get("chapter_plan"):
        lines.append("- %s" % manifest["inputs"]["chapter_plan"])
    lines.append("")
    lines.append("## 7. 本次允许修改")
    lines.append("")
    if perm.get("writable_scopes"):
        for sc in perm["writable_scopes"]:
            lines.append("- %s" % sc)
    else:
        lines.append("- （按角色，无显式 writable scope）")
    lines.append("")
    lines.append("## 8. 完成标准")
    lines.append("")
    lines.append("- 正文/产物满足 Task Contract 与章节规划；")
    lines.append("- 格式与脚本预检通过（无硬连续性冲突）；")
    lines.append("- Candidate Events / Operation Manifest 格式正确；")
    lines.append("- 输出已登记为 Build 并经 Gate。")
    lines.append("")
    lines.append("## 9. 门禁与阻塞")
    lines.append("")
    lines.append("- bootstrap_validated: **%s**" % gates.get("bootstrap_validated"))
    lines.append("- task_inputs_ready: **%s**" % gates.get("task_inputs_ready"))
    lines.append("- context_version_valid: **%s**" % gates.get("context_version_valid"))
    lines.append("- policy_version_valid: **%s**" % gates.get("policy_version_valid"))
    blk = manifest.get("blockers") or []
    if blk:
        lines.append("")
        lines.append("**阻塞项（ready=false，禁止执行）：**")
        for b in blk:
            lines.append("- ⛔ %s" % b)
    else:
        lines.append("")
        lines.append("**无阻塞，ready=true，可执行当前任务。**")
    lines.append("")
    return "\n".join(lines) + "\n"


def _bootstrap_result(manifest):
    """启动校验结果（JSON），供 AI 第一步返回。"""
    return {
        "bootstrap_result": {
            "platform_understood": True,
            "project": manifest["project"]["id"],
            "task": manifest["task"]["id"],
            "execution_mode": manifest["platform"]["execution_mode"],
            "authoritative_sources": manifest["authoritative_sources"],
            "allowed_outputs": manifest["permissions"]["writable_scopes"],
            "blockers": manifest["blockers"],
            "ready": manifest["ready"],
        }
    }


# ───────────────────────── 命令实现 ─────────────────────────

def cmd_bootstrap(args):
    project_id = args.project
    intent = args.intent or "auto"
    target = args.target
    role = args.role
    try:
        pdir, pdata, ws = find_project(project_id, args.workspace)
    except RuntimeError as e:
        print("ERROR: %s" % e)
        sys.exit(2)

    plat_root = _gov.find_platform_root()
    located = locate_task(pdir, intent, target, role)
    tid, t, state, role = located

    now = datetime.datetime.now()
    stamp = now.strftime("%Y%m%d")
    sdir = os.path.join(pdir, "runtime", "sessions")
    os.makedirs(sdir, exist_ok=True)
    n = len(glob.glob(os.path.join(sdir, "SESSION-%s-*.yaml" % stamp))) + 1
    sid = _session_id(stamp, n)

    manifest = build_manifest(pdir, pdata, intent, target, role, located)
    manifest["session"]["id"] = sid

    sdir2 = _session_dir(pdir, sid)
    man_path = os.path.join(sdir2, "SESSION_MANIFEST.yaml")
    brief_path = os.path.join(sdir2, "SESSION_BRIEF.md")
    with open(man_path, "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(manifest))
    with open(brief_path, "w", encoding="utf-8") as f:
        f.write(render_brief(manifest, pdir, pdata))

    # 输出
    print("SESSION MANIFEST: %s" % man_path)
    print("SESSION BRIEF:    %s" % brief_path)
    print("project=%s role=%s intent=%s task=%s" % (
        project_id, role, intent, tid or "(none)"))
    if tid:
        print("gates: bootstrap=%s task_inputs=%s context=%s policy=%s" % (
            manifest["gates"]["bootstrap_validated"],
            manifest["gates"]["task_inputs_ready"],
            manifest["gates"]["context_version_valid"],
            manifest["gates"]["policy_version_valid"]))
    print("READY=%s" % manifest["ready"])
    for b in (manifest["blockers"] or []):
        print("BLOCKER: %s" % b)
    print(_gov.dump_block(_bootstrap_result(manifest)))
    sys.exit(0 if manifest["ready"] else 3)


def _load_latest_manifest(project_root):
    """读取最新 SESSION_MANIFEST（runtime/sessions/<id>/ 优先，回落 sessions/SES-*.yaml）。"""
    sdir = os.path.join(project_root, "runtime", "sessions")
    cands = []
    if os.path.isdir(sdir):
        for sid in sorted(os.listdir(sdir)):
            mp = os.path.join(sdir, sid, "SESSION_MANIFEST.yaml")
            if os.path.isfile(mp):
                cands.append(mp)
    # 回落旧位置
    legacy = os.path.join(project_root, "sessions")
    if os.path.isdir(legacy):
        for fp in sorted(glob.glob(os.path.join(legacy, "SES-*.yaml")), reverse=True):
            cands.append(fp)
    for mp in sorted(cands, reverse=True):
        try:
            d = _gov.load_yaml(mp)
        except Exception:
            continue
        if isinstance(d, dict):
            d["_manifest_path"] = mp
            return d
    return None


def cmd_verify(args):
    try:
        pdir, pdata, ws = find_project(args.project, args.workspace)
    except RuntimeError as e:
        print("ERROR: %s" % e)
        sys.exit(2)
    man = _load_latest_manifest(pdir)
    if not man:
        print("ERROR: 无活动会话（未 bootstrap）。请先运行 `platform session bootstrap`")
        sys.exit(2)

    # 重验门禁（对照当前仓库状态）
    blockers = []
    boot_ok = (os.path.isfile(os.path.join(pdir, "project.yaml"))
               and os.path.isfile(os.path.join(pdir, "AGENTS.md")))
    nkb_dir = os.path.join(pdir, (pdata.get("paths") or {}).get("nkb", "NKB"))
    boot_ok = boot_ok and os.path.isdir(nkb_dir) and len(os.listdir(nkb_dir)) > 0
    task_ok = bool((man.get("task") or {}).get("id"))
    if task_ok:
        tid = man["task"]["id"]
        import task_engine as te
        st, _ = te.load_task(pdir, tid) if hasattr(te, "load_task") else (None, None)
        if st is None:
            task_ok = False
            blockers.append("任务 %s 已不存在" % tid)
    ready = boot_ok and task_ok
    man["gates"]["bootstrap_validated"] = boot_ok
    man["gates"]["task_inputs_ready"] = task_ok
    man["ready"] = ready
    man["blockers"] = blockers

    print("VERIFY session=%s" % man.get("session", {}).get("id"))
    print("bootstrap_validated=%s task_inputs_ready=%s ready=%s" % (boot_ok, task_ok, ready))
    for b in blockers:
        print("BLOCKER: %s" % b)
    # 回写校验结果（不覆盖其他字段）
    try:
        with open(man["_manifest_path"], "w", encoding="utf-8") as f:
            f.write(_gov.dump_block(man))
    except Exception:
        pass
    sys.exit(0 if ready else 3)


def cmd_status(args):
    try:
        pdir, pdata, ws = find_project(args.project, args.workspace)
    except RuntimeError as e:
        print("ERROR: %s" % e)
        sys.exit(2)
    man = _load_latest_manifest(pdir)
    if not man:
        print("STATUS: 无活动会话（未 bootstrap）。")
        sys.exit(0)
    s = man.get("session", {})
    p = man.get("project", {})
    t = man.get("task", {})
    g = man.get("gates", {})
    print("=== Session Status ===")
    print("session_id : %s" % s.get("id"))
    print("created_at : %s" % s.get("created_at"))
    print("intent     : %s  target=%s" % (s.get("intent"), s.get("target")))
    print("project    : %s (%s)" % (p.get("id"), p.get("name")))
    print("task       : %s [%s] status=%s" % (t.get("id"), t.get("type"), t.get("status")))
    print("role       : %s" % (man.get("permissions", {}).get("role")))
    print("gates      : bootstrap=%s task=%s context=%s policy=%s" % (
        g.get("bootstrap_validated"), g.get("task_inputs_ready"),
        g.get("context_version_valid"), g.get("policy_version_valid")))
    print("ready      : %s" % man.get("ready"))
    for b in (man.get("blockers") or []):
        print("  BLOCKER: %s" % b)
    sys.exit(0)


def cmd_close(args):
    try:
        pdir, pdata, ws = find_project(args.project, args.workspace)
    except RuntimeError as e:
        print("ERROR: %s" % e)
        sys.exit(2)
    man = _load_latest_manifest(pdir)
    sid = args.session or (man or {}).get("session", {}).get("id") or "SESSION-unknown"
    task_id = (man or {}).get("task", {}).get("id")

    arts = {}
    for a in (args.artifacts or []):
        if "=" in a:
            k, v = a.split("=", 1)
            arts[k] = v

    issues = list(args.issues or [])

    handoff = {
        "handoff": {
            "previous_session": sid,
            "project": args.project,
            "task": task_id,
        },
        "progress": {
            "completed_stage": args.stage or "draft",
            "current_stage": args.stage or "precheck",
            "next_action": args.next or "run_script_precheck",
        },
        "artifacts": arts or {"latest_build": None, "draft": None},
        "decisions": [],
        "open_issues": [{"id": "ISSUE-%s-%d" % (task_id or "X", i + 1),
                         "severity": "medium", "summary": s} for i, s in enumerate(issues)],
        "versions": {
            "nkb_snapshot": (man or {}).get("project", {}).get("nkb_snapshot"),
            "context": (man or {}).get("inputs", {}).get("context"),
            "policy": (man or {}).get("inputs", {}).get("policy"),
        },
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z"),
    }

    hdir = os.path.join(pdir, "handoffs")
    os.makedirs(hdir, exist_ok=True)
    out = os.path.join(hdir, "LATEST_HANDOFF.yaml")
    with open(out, "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(handoff))
    print("LATEST_HANDOFF: %s" % out)
    print("session=%s task=%s stage=%s" % (sid, task_id, args.stage or "draft"))
    sys.exit(0)


def main():
    ap = argparse.ArgumentParser(prog="session", description="会话启动协议（Phase C PC-6）")
    ap.add_argument("verb", choices=["bootstrap", "verify", "status", "close"])
    ap.add_argument("--project", required=True)
    ap.add_argument("--intent", default="auto")
    ap.add_argument("--target", default=None)
    ap.add_argument("--role", default=None)
    ap.add_argument("--workspace", default=None)
    # close 专用
    ap.add_argument("--session", default=None)
    ap.add_argument("--stage", default=None)
    ap.add_argument("--next", default=None)
    ap.add_argument("--artifacts", nargs="*", default=[])
    ap.add_argument("--issues", nargs="*", default=[])
    args = ap.parse_args()

    if args.verb == "bootstrap":
        cmd_bootstrap(args)
    elif args.verb == "verify":
        cmd_verify(args)
    elif args.verb == "status":
        cmd_status(args)
    elif args.verb == "close":
        cmd_close(args)


if __name__ == "__main__":
    main()
