# -*- coding: utf-8 -*-
"""validators.py — Level-1 脚本预检管线（Phase A6）

脚本先拦截低级问题，AI 只审语义。本模块输出**事实**，不下质量结论：

  platform validate schema       --file F
  platform validate frontmatter  --file F [--required k1,k2]
  platform validate chapter_length --file F [--min M] [--max M]
  platform validate terminology  --file F --project-root R
  platform validate ids          --project-root R
  platform validate references   --project-root R
  platform validate task_compliance --task T --project-root R
  platform validate runtime_policy --project-root R
  platform validate artifact     --file F --project-root R   （组合预检）

每个检查返回 findings: [{check, severity, detail}]。severity ∈ info/warn/fail。
脚本不判定小说好坏，只把低级错误提前清掉。
"""
import os
import sys
import re
import json
import argparse

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
import _gov  # 平台根解析（find_platform_root / find_workspace_root）

try:
    import yaml as _pyyaml
    def _load_yaml(path):
        with open(path, "r", encoding="utf-8") as f:
            return _pyyaml.safe_load(f)
except Exception:
    import _yaml_lite
    def _load_yaml(path):
        return _yaml_lite.load_file(path)

_ID_RE = re.compile(r"^[A-Z][A-Z0-9_-]*$")


def _emit(findings):
    print(json.dumps(findings, ensure_ascii=False, indent=2))
    return findings


def _check_schema(args):
    f = args.file
    if not os.path.isfile(f):
        return _emit([{"check": "schema", "severity": "fail", "detail": "文件不存在: %s" % f}])
    try:
        _load_yaml(f)
        return _emit([{"check": "schema", "severity": "info", "detail": "YAML 解析通过: %s" % f}])
    except Exception as e:
        return _emit([{"check": "schema", "severity": "fail", "detail": "YAML 解析失败: %s" % e}])


def _check_frontmatter(args):
    f = args.file
    findings = [{"check": "frontmatter", "severity": "info", "detail": "OK"}]
    try:
        with open(f, "r", encoding="utf-8") as fh:
            txt = fh.read()
    except Exception as e:
        return _emit([{"check": "frontmatter", "severity": "fail", "detail": "读取失败: %s" % e}])
    if not txt.lstrip().startswith("---"):
        findings = [{"check": "frontmatter", "severity": "warn", "detail": "缺少开头 --- 围栏"}]
    else:
        end = txt.find("\n---", 3)
        if end < 0:
            findings = [{"check": "frontmatter", "severity": "warn", "detail": "缺少闭合 --- 围栏"}]
        else:
            block = txt[3:end]
            keys = re.findall(r"^([A-Za-z_]+)\s*:", block, re.M)
            req = [k.strip() for k in (args.required or "").split(",") if k.strip()]
            missing = [k for k in req if k not in keys]
            if missing:
                findings = [{"check": "frontmatter", "severity": "warn",
                             "detail": "缺必填 Front Matter 键: %s" % missing}]
    return _emit(findings)


def _count_chars(f):
    with open(f, "r", encoding="utf-8") as fh:
        txt = fh.read()
    # 去空白统计有效字符
    return len(re.sub(r"\s", "", txt))


def _check_chapter_length(args):
    f = args.file
    if not os.path.isfile(f):
        return _emit([{"check": "chapter_length", "severity": "fail", "detail": "文件不存在"}])
    n = _count_chars(f)
    mn = args.min if args.min is not None else 0
    mx = args.max if args.max is not None else 10 ** 9
    if n < mn:
        sev = "warn"
        detail = "字数 %d < 下限 %d" % (n, mn)
    elif n > mx:
        sev = "warn"
        detail = "字数 %d > 上限 %d" % (n, mx)
    else:
        sev = "info"
        detail = "字数 %d（区间 %d–%d）" % (n, mn, mx)
    return _emit([{"check": "chapter_length", "severity": sev, "detail": detail, "chars": n}])


def _load_nkb(proot):
    nkb_dir = os.path.normpath(os.path.join(proot, "NKB"))
    comps = {}
    if not os.path.isdir(nkb_dir):
        return comps
    for fn in sorted(os.listdir(nkb_dir)):
        if not fn.endswith(".yaml") or fn in ("CHANGELOG.md", "NKB.md"):
            continue
        try:
            d = _load_yaml(os.path.join(nkb_dir, fn))
        except Exception:
            continue
        if isinstance(d, dict):
            comps[fn[:-5]] = d.get("records") or []
    return comps


def _collect_terminology(proot):
    comps = _load_nkb(proot)
    out = []
    for r in comps.get("Terminology", []):
        forb = r.get("forbidden")
        if forb is None:
            forb = r.get("deprecated") or r.get("aliases")
        if isinstance(forb, str):
            forb = [forb]
        if not isinstance(forb, list):
            forb = []
        for token in forb:
            if token:
                out.append({"token": str(token), "canonical": r.get("name")})
    return out


def _check_terminology(args):
    proot = args.project_root
    terms = _collect_terminology(proot)
    if not os.path.isfile(args.file):
        return _emit([{"check": "terminology", "severity": "fail", "detail": "文件不存在"}])
    with open(args.file, "r", encoding="utf-8") as fh:
        lines = fh.readlines()
    hits = []
    for i, line in enumerate(lines, 1):
        for t in terms:
            if t["token"] in line:
                hits.append({"line": i, "found": t["token"], "canonical": t["canonical"]})
    sev = "warn" if hits else "info"
    return _emit([{"check": "terminology", "severity": sev,
                   "detail": "命中废弃术语 %d 处" % len(hits), "hits": hits}])


def _check_ids(args):
    comps = _load_nkb(args.project_root)
    findings = []
    for comp, recs in comps.items():
        seen = set()
        for r in recs:
            rid = r.get("id")
            if not rid:
                findings.append({"check": "ids", "severity": "fail",
                                 "detail": "%s 记录缺失 id" % comp})
            elif not _ID_RE.match(str(rid)):
                findings.append({"check": "ids", "severity": "warn",
                                 "detail": "%s id 格式异常: %s" % (comp, rid)})
            elif rid in seen:
                findings.append({"check": "ids", "severity": "fail",
                                 "detail": "%s 重复 id: %s" % (comp, rid)})
            seen.add(rid)
    if not findings:
        findings = [{"check": "ids", "severity": "info", "detail": "全部组件 id 合规"}]
    return _emit(findings)


def _check_references(args):
    comps = _load_nkb(args.project_root)
    ids = {comp: {str(r.get("id")) for r in recs} for comp, recs in comps.items()}
    all_ids = set()
    for component_ids in ids.values():
        all_ids.update(component_ids)
    findings = []
    # Events may involve characters, organizations, locations, or other
    # registered entities. Validate existence across the whole NKB.
    for e in comps.get("Events", []):
        for p in (e.get("participants") or []):
            if p not in all_ids:
                findings.append({"check": "references", "severity": "warn",
                                 "detail": "%s 参与者 %s 不在 NKB" % (e.get("id"), p)})
    # Character relationships may also point to organizations or locations.
    for c in comps.get("Characters", []):
        for rel in (c.get("relationships") or []):
            t = rel.get("target") if isinstance(rel, dict) else None
            if t and t not in all_ids:
                findings.append({"check": "references", "severity": "warn",
                                 "detail": "%s 关系目标 %s 不在 NKB" % (c.get("id"), t)})
    if not findings:
        findings = [{"check": "references", "severity": "info", "detail": "引用完整性 OK"}]
    return _emit(findings)


def _check_task_compliance(args):
    sys.path.insert(0, HERE)
    import task_engine as TE
    st, data = TE.load_task(args.project_root, args.task)
    if st is None:
        return _emit([{"check": "task_compliance", "severity": "fail", "detail": "任务不存在"}])
    ep = (data.get("task") or {}).get("execution_policy") or {}
    findings = []
    if ep.get("max_agents") != 1:
        findings.append({"check": "task_compliance", "severity": "fail", "detail": "max_agents != 1"})
    if ep.get("subagent_allowed") not in (False, "false"):
        findings.append({"check": "task_compliance", "severity": "fail", "detail": "subagent_allowed 未禁用"})
    if ep.get("delegation_allowed") not in (False, "false"):
        findings.append({"check": "task_compliance", "severity": "fail", "detail": "delegation_allowed 未禁用"})
    if not findings:
        findings = [{"check": "task_compliance", "severity": "info", "detail": "单 Agent 策略合规"}]
    return _emit(findings)


def _check_runtime_policy(args):
    p = os.path.join(args.project_root, "project.yaml")
    if not os.path.isfile(p):
        return _emit([{"check": "runtime_policy", "severity": "fail", "detail": "project.yaml 缺失"}])
    d = _load_yaml(p) or {}
    rt = d.get("runtime") or {}
    findings = []
    if rt.get("agent_mode") != "single":
        findings.append({"check": "runtime_policy", "severity": "fail", "detail": "agent_mode != single"})
    conc = rt.get("concurrency") or {}
    if conc.get("max_active_agents") != 1:
        findings.append({"check": "runtime_policy", "severity": "warn", "detail": "max_active_agents != 1"})
    if conc.get("max_parallel_tool_calls") != 1:
        findings.append({"check": "runtime_policy", "severity": "warn", "detail": "max_parallel_tool_calls != 1"})
    if not findings:
        findings = [{"check": "runtime_policy", "severity": "info", "detail": "单 Agent 运行时策略合规"}]
    return _emit(findings)


def _check_artifact(args):
    allf = []
    for fn in (_check_schema, _check_frontmatter, _check_chapter_length, _check_terminology):
        try:
            if fn is _check_chapter_length:
                allf += fn(type("A", (), {"file": args.file, "min": args.min, "max": args.max})())
            elif fn is _check_terminology:
                allf += fn(type("A", (), {"file": args.file, "project_root": args.project_root})())
            else:
                allf += fn(type("A", (), {"file": args.file, "required": args.required})())
        except Exception as e:
            allf.append({"check": "artifact", "severity": "fail", "detail": "%s 异常: %s" % (fn.__name__, e)})
    return _emit(allf)


def _auth_dir():
    return os.path.join(_gov.find_platform_root(), "core", "authorization")


def _check_authorization(args):
    """校验 core/authorization 五 YAML 的内部一致性（编辑≠发布基线）。"""
    d = _auth_dir()
    import _yaml_lite
    def L(n):
        p = os.path.join(d, n)
        return _yaml_lite.load_file(p) if os.path.isfile(p) else {}
    acts = (L("actions.yaml") or {}).get("actions", {})
    res = (L("resources.yaml") or {}).get("layers", {})
    roles = (L("roles.yaml") or {}).get("roles", {})
    st = L("state-permissions.yaml") or {}
    imm_full = L("immutable-policies.yaml") or {}
    imm = imm_full.get("authorization") or {}
    findings = []
    layers = set(res.keys())
    # 动作资源层存在
    for an, a in acts.items():
        rl = a.get("resource_layer")
        if rl not in layers:
            findings.append({"check": "authorization", "severity": "fail",
                             "detail": "动作 %s 的 resource_layer %s 未定义" % (an, rl)})
    # 角色 capability / resource_layers 存在
    for rn, r in roles.items():
        for cap in (r.get("capabilities") or []):
            if cap not in acts:
                findings.append({"check": "authorization", "severity": "fail",
                                 "detail": "角色 %s 的 capability %s 未定义" % (rn, cap)})
        for rl in (r.get("resource_layers") or []):
            if rl not in layers:
                findings.append({"check": "authorization", "severity": "fail",
                                 "detail": "角色 %s 的 resource_layer %s 未定义" % (rn, rl)})
    # 默认拒绝基线
    if imm.get("default") != "deny":
        findings.append({"check": "authorization", "severity": "fail",
                         "detail": "immutable-policies.authorization.default != deny（基线被破坏）"})
    # 11 个标准错误码齐全（error_codes 在 immutable-policies.yaml 顶层，不在 authorization 块内）
    required_codes = {"WRITE_TASK_REQUIRED", "ROLE_CAPABILITY_DENIED", "TASK_GRANT_MISSING",
                      "TASK_STATE_WRITE_DENIED", "RESOURCE_OUT_OF_SCOPE", "CANONICAL_DIRECT_WRITE_FORBIDDEN",
                      "BUILD_FROZEN", "PUBLISH_GATE_FAILED", "REVISION_CONFLICT",
                      "SERVICE_IDENTITY_REQUIRED", "PERMISSION_DENIED"}
    have = set((imm_full.get("error_codes") or {}).keys())
    missing = required_codes - have
    if missing:
        findings.append({"check": "authorization", "severity": "fail",
                         "detail": "缺标准错误码: %s" % sorted(missing)})
    # canonical 层 writer_identity 必须为 publish_service（编辑≠发布）
    cw = (res.get("canonical") or {}).get("writer_identity")
    if cw != "publish_service":
        findings.append({"check": "authorization", "severity": "fail",
                         "detail": "canonical 层 writer_identity=%s（应为 publish_service）" % cw})
    if not findings:
        findings = [{"check": "authorization", "severity": "info", "detail": "授权基线一致（编辑≠发布）"}]
    return _emit(findings)


def _check_chapter_workflow(args):
    """校验 13 态状态机一致性 + service_only 动作仅出现在发布相关态。"""
    d = _auth_dir()
    import _yaml_lite
    st = _yaml_lite.load_file(os.path.join(d, "state-permissions.yaml")) or {}
    findings = []
    states = st.get("states") or []
    defined = set(states)
    trans = st.get("transitions") or {}
    sp = st.get("state_permissions") or {}
    # 所有 state 都被 transitions 与 state_permissions 引用
    for s in states:
        if s not in trans:
            findings.append({"check": "chapter_workflow", "severity": "warn", "detail": "态 %s 无 transitions" % s})
        if s not in sp:
            findings.append({"check": "chapter_workflow", "severity": "warn", "detail": "态 %s 无 state_permissions" % s})
    # transitions 只引用已定义态
    for s, nxt in trans.items():
        for n in (nxt or []):
            if n not in defined:
                findings.append({"check": "chapter_workflow", "severity": "fail",
                                 "detail": "transitions[%s] 引用未定义态 %s" % (s, n)})
    # service_only 动作（chapter.publish / canonical.rollback）只出现在 approved/publishing/published/completed
    import _yaml_lite as _Y
    acts = _Y.load_file(os.path.join(d, "actions.yaml")) or {}
    acts = acts.get("actions", {})
    svc_actions = [an for an, a in acts.items() if a.get("service_only")]
    allowed_states = {"approved", "publishing", "published", "completed"}
    for an in svc_actions:
        for s, allowed in sp.items():
            if an in (allowed or []) and s not in allowed_states:
                findings.append({"check": "chapter_workflow", "severity": "fail",
                                 "detail": "service_only 动作 %s 出现在非发布态 %s" % (an, s)})
    # task_state_to_chapter_state 覆盖全部任务态
    mapping = st.get("task_state_to_chapter_state") or {}
    for ts in ("backlog", "ready", "claimed", "running", "submitted", "reviewing",
               "passed", "completed", "failed", "archive"):
        if ts not in mapping:
            findings.append({"check": "chapter_workflow", "severity": "warn",
                             "detail": "task_state_to_chapter_state 缺映射: %s" % ts})
    if not findings:
        findings = [{"check": "chapter_workflow", "severity": "info", "detail": "13 态状态机一致"}]
    return _emit(findings)


def _check_canonical_writes(args):
    """审计 canonical 正式正文：是否全部经 Publish Service 落盘、有无篡改。"""
    root = args.project_root
    if not root or not os.path.isdir(root):
        return _emit([{"check": "canonical_writes", "severity": "fail", "detail": "缺 --project-root 或目录不存在"}])
    sys.path.insert(0, os.path.join(_gov.find_platform_root(), "scripts", "publish"))
    import manifest as MF
    import re
    files = []
    for dn in sorted(os.listdir(root)):
        dp = os.path.join(root, dn)
        if not os.path.isdir(dp) or not re.match(r"^第.卷_", dn):
            continue
        for fn in sorted(os.listdir(dp)):
            if fn.endswith(".md") or fn.endswith(".txt"):
                files.append("%s/%s" % (dn, fn))
    entries = MF.list_entries(root)
    findings = []
    for f in files:
        e = entries.get(f)
        af = os.path.join(root, f)
        cur = MF.hash_content(open(af, "r", encoding="utf-8").read()) if os.path.isfile(af) else None
        if not e:
            findings.append({"check": "canonical_writes", "severity": "fail",
                             "detail": "canonical %s 不在 manifest（疑似未经验 Publish Service 直写）" % f})
        elif cur != e.get("hash"):
            findings.append({"check": "canonical_writes", "severity": "fail",
                             "detail": "canonical %s hash 不一致（疑似篡改）" % f})
        else:
            findings.append({"check": "canonical_writes", "severity": "info",
                             "detail": "canonical %s 经 Publish Service 落盘 r%d" % (f, e.get("revision"))})
    for k in entries:
        if k not in files and not os.path.isfile(os.path.join(root, k)):
            findings.append({"check": "canonical_writes", "severity": "warn",
                             "detail": "manifest 记录 %s 但文件缺失" % k})
    if not findings:
        findings = [{"check": "canonical_writes", "severity": "info", "detail": "无 canonical 文件"}]
    return _emit(findings)


def main():
    ap = argparse.ArgumentParser(prog="validate", description="Level-1 脚本预检")
    sub = ap.add_subparsers(dest="check")
    for name in ("schema", "frontmatter", "chapter_length", "terminology",
                 "ids", "references", "task_compliance", "runtime_policy", "artifact",
                 "authorization", "chapter-workflow", "canonical-writes"):
        sp = sub.add_parser(name)
        sp.add_argument("--file", default=None)
        sp.add_argument("--project-root", default=None)
        sp.add_argument("--required", default="")
        sp.add_argument("--min", type=int, default=None)
        sp.add_argument("--max", type=int, default=None)
        sp.add_argument("--task", default=None)
    # all：聚合（平台相关 + 项目相关）
    spa = sub.add_parser("all")
    spa.add_argument("--project-root", default=None)
    args = ap.parse_args()
    dispatch = {
        "schema": _check_schema, "frontmatter": _check_frontmatter,
        "chapter_length": _check_chapter_length, "terminology": _check_terminology,
        "ids": _check_ids, "references": _check_references,
        "task_compliance": _check_task_compliance, "runtime_policy": _check_runtime_policy,
        "artifact": _check_artifact,
        "authorization": _check_authorization, "chapter-workflow": _check_chapter_workflow,
        "canonical-writes": _check_canonical_writes,
    }
    if args.check == "all":
        out = []
        for fn in (_check_authorization, _check_chapter_workflow, _check_canonical_writes,
                   _check_ids, _check_references, _check_runtime_policy):
            try:
                out += fn(args)
            except Exception as e:
                out.append({"check": "all", "severity": "fail", "detail": "%s 异常: %s" % (fn.__name__, e)})
        return _emit(out)
    fn = dispatch.get(args.check)
    if not fn:
        ap.print_help()
        sys.exit(2)
    fn(args)


if __name__ == "__main__":
    main()
