#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit_report.py — Phase C 审计汇总（审计生成器）

聚合项目 audit/audit.log.jsonl（append-only，见 audit_log.py）为结构化报告：
  总量、按 action / role / agent 计数、按日时间线、最近 N 条。
返回标准 dict；CLI：platform audit report [--days N] [--recent N] [--json]。
脚本只做确定性聚合，不替 AI 下质量结论。
"""
import os
import sys
import json
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
import audit_log


def _audit_path(project_root):
    return os.path.join(project_root, "audit", "audit.log.jsonl")


def audit_report(project_root, days=None, recent=20):
    """读取审计日志并聚合。days 限制时间窗口（按日期）；recent 返回最近 N 条。"""
    p = _audit_path(project_root)
    recs = []
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    recs.append(json.loads(line))
                except Exception:
                    continue
    if days:
        try:
            cutoff = (datetime.date.today() - datetime.timedelta(days=int(days))).isoformat()
        except Exception:
            cutoff = None
        if cutoff:
            recs = [r for r in recs if (r.get("ts") or "").split("T")[0] >= cutoff]
    by_action, by_role, by_agent, by_date = {}, {}, {}, {}
    for r in recs:
        a = r.get("action", "?")
        by_action[a] = by_action.get(a, 0) + 1
        rl = r.get("role", "?")
        by_role[rl] = by_role.get(rl, 0) + 1
        ag = r.get("agent", "?")
        by_agent[ag] = by_agent.get(ag, 0) + 1
        d = (r.get("ts") or "").split("T")[0]
        by_date[d] = by_date.get(d, 0) + 1
    return {
        "total": len(recs),
        "by_action": by_action,
        "by_role": by_role,
        "by_agent": by_agent,
        "by_date": by_date,
        "recent": recs[-recent:] if recent else [],
    }


def govern(project_root, write=False):
    """AuditGov：检查审计日志是否存在/可读（caution 若缺失，不阻断内容任务）。"""
    reasons = []
    p = _audit_path(project_root)
    n = 0
    if not os.path.isfile(p):
        reasons.append("audit/audit.log.jsonl 缺失（无操作审计记录）")
    else:
        try:
            with open(p, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        n += 1
        except Exception as _e:
            reasons.append("审计日志读取失败：%s" % _e)
    decision = "caution" if reasons else "proceed"
    health = 100 if not reasons else max(0, 100 - 12 * len(reasons))
    return {"gate": {"decision": decision, "reasons": reasons},
            "composite": {"health": health},
            "response": {"records": n}}


def render_markdown(report):
    lines = ["# 操作审计汇总", "", "- 总量：%d" % report["total"], ""]
    lines.append("## 按动作")
    for k, v in sorted(report["by_action"].items(), key=lambda x: -x[1]):
        lines.append("- %s：%d" % (k, v))
    lines.append("")
    lines.append("## 按角色")
    for k, v in sorted(report["by_role"].items(), key=lambda x: -x[1]):
        lines.append("- %s：%d" % (k, v))
    lines.append("")
    lines.append("## 按日时间线")
    for k, v in sorted(report["by_date"].items()):
        lines.append("- %s：%d" % (k, v))
    lines.append("")
    return "\n".join(lines)


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="audit", description="操作审计汇总")
    ap.add_argument("--project-root", required=True)
    ap.add_argument("verb", choices=["report", "govern"], default="report", nargs="?")
    ap.add_argument("--days", default=None)
    ap.add_argument("--recent", type=int, default=20)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--markdown", action="store_true")
    args = ap.parse_args()

    if args.verb == "govern":
        print(json.dumps(govern(args.project_root), ensure_ascii=False, indent=2))
        return
    rep = audit_report(args.project_root, days=args.days, recent=args.recent)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    elif args.markdown:
        print(render_markdown(rep))
    else:
        print("总量：%d" % rep["total"])
        print("按动作：%s" % rep["by_action"])
        print("按角色：%s" % rep["by_role"])
        print("按日：%s" % rep["by_date"])
        print("最近 %d 条动作：%s" % (args.recent,
              [r.get("action") for r in rep["recent"]]))


if __name__ == "__main__":
    main()
