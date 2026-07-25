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
    findings = []
    # Events participants → Characters
    char_ids = ids.get("Characters", set())
    for e in comps.get("Events", []):
        for p in (e.get("participants") or []):
            if p not in char_ids:
                findings.append({"check": "references", "severity": "warn",
                                 "detail": "%s 参与者 %s 不在 Characters" % (e.get("id"), p)})
    # Characters relationships target → Characters
    for c in comps.get("Characters", []):
        for rel in (c.get("relationships") or []):
            t = rel.get("target") if isinstance(rel, dict) else None
            if t and t not in char_ids:
                findings.append({"check": "references", "severity": "warn",
                                 "detail": "%s 关系目标 %s 不在 Characters" % (c.get("id"), t)})
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


def main():
    ap = argparse.ArgumentParser(prog="validate", description="Level-1 脚本预检")
    sub = ap.add_subparsers(dest="check")
    for name in ("schema", "frontmatter", "chapter_length", "terminology",
                 "ids", "references", "task_compliance", "runtime_policy", "artifact"):
        sp = sub.add_parser(name)
        sp.add_argument("--file", default=None)
        sp.add_argument("--project-root", default=None)
        sp.add_argument("--required", default="")
        sp.add_argument("--min", type=int, default=None)
        sp.add_argument("--max", type=int, default=None)
        sp.add_argument("--task", default=None)
    args = ap.parse_args()
    dispatch = {
        "schema": _check_schema, "frontmatter": _check_frontmatter,
        "chapter_length": _check_chapter_length, "terminology": _check_terminology,
        "ids": _check_ids, "references": _check_references,
        "task_compliance": _check_task_compliance, "runtime_policy": _check_runtime_policy,
        "artifact": _check_artifact,
    }
    fn = dispatch.get(args.check)
    if not fn:
        ap.print_help()
        sys.exit(2)
    fn(args)


if __name__ == "__main__":
    main()
