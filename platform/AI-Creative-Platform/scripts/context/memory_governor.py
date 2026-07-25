# [Phase2-path] 把 scripts 各分组目录加入 sys.path，保持跨组裸名 import 可用
import os as _os, sys as _sys
_H0 = _os.path.dirname(_os.path.abspath(__file__))
_SCR0 = _os.path.dirname(_H0)
if _os.path.isdir(_SCR0):
    for _d in _os.listdir(_SCR0):
        _p = _os.path.join(_SCR0, _d)
        if _os.path.isdir(_p) and _p not in _sys.path:
            _sys.path.insert(0, _p)
"""
内存治理引擎（Memory Governance）· Phase 2 #4

对 platform/memory/ 四层经验库（global/genre/project/rejected）做体检：
  SC1 schema 合法  SC2 level↔目录一致  SC3 status↔位置一致
  SC4 晋升门槛执行  SC5 重复检测        SC6 失效引用
  SC7 孤立 README

门禁：报告式（block=结构错配→doctor FAIL；caution=软问题；不阻断 task submit）。
"""
import os
import re
import sys
import argparse
import datetime

import _gov
import audit_log

MEMORY_DIRS = ("global", "genre", "project", "rejected")
ID_RE = re.compile(r"^MEM-(G|XH|P|R)-[0-9]{3}$")
ID_PREFIX_LEVEL = {"G": "global", "XH": "genre", "P": "project", "R": "rejected"}
LEVEL_FROM_DIR = {"global": "global", "genre": "genre", "project": "project", "rejected": "rejected"}


# ─────────────────────── 共享 helper（复用 quality_scorer 模式） ───────────────────────
def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _safe_load(p):
    try:
        return _gov.load_yaml(p)
    except Exception:
        return None


def _rel(root, p):
    return os.path.relpath(p, root)


def _load_cfg():
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "registry", "memory.yaml")
    d = _safe_load(p)
    if not isinstance(d, dict):
        d = {}
    prom = d.get("promotion", {})
    ptg = prom.get("project_to_genre", {})
    gtg = prom.get("genre_to_global", {})
    ded = d.get("dedup", {})
    gate = d.get("gate", {})
    return {
        "min_genre": int(ptg.get("min_validated_projects", 2)),
        "min_global": int(gtg.get("min_validated_projects", 3)),
        "sim_threshold": float(ded.get("similarity_threshold", 0.85)),
        "fatal_penalty": int(gate.get("fatal_penalty", 40)),
        "caution_penalty": int(gate.get("caution_penalty", 5)),
        "require_readme": bool(d.get("require_readme", True)),
        "ref_check": bool((d.get("reference_check", {}) or {}).get("enabled", True)),
    }


def _normalize(text):
    if not text:
        return ""
    s = text.lower()
    # 保留中文/字母/数字，去其它
    s = re.sub(r"[^\w\u4e00-\u9fff]", "", s)
    return s


def _bigrams(s):
    return set(s[i:i + 2] for i in range(len(s) - 1)) if len(s) > 1 else set(s)


def _similarity(a, b):
    na, nb = _normalize(a), _normalize(b)
    if not na or not nb:
        return 0.0
    ba, bb = _bigrams(na), _bigrams(nb)
    if not ba or not bb:
        return 1.0 if na == nb else 0.0
    inter = len(ba & bb)
    union = len(ba | bb)
    return inter / union if union else 0.0


def _level_of_path(mem_root, fp):
    rel = _rel(mem_root, fp).replace("\\", "/")
    parts = rel.split("/")
    # rel 相对 memory/ 根：global/FILE | genre/<genre>/FILE | project/FILE | rejected/FILE
    if len(parts) >= 2:
        top = parts[0]
        if top == "genre" and len(parts) >= 3:
            return "genre", parts[1]  # genre/<genre>/file
        return top, None
    return None, None


def _check_schema(d, cfg):
    if not isinstance(d, dict):
        return False, "非 mapping"
    req = ["id", "level", "problem", "root_cause", "action",
           "validated_projects", "confidence", "status"]
    miss = [k for k in req if k not in d]
    if miss:
        return False, "缺字段: " + ",".join(miss)
    if not ID_RE.match(str(d.get("id", ""))):
        return False, "id 格式不符 MEM-(G|XH|P|R)-NNN"
    if str(d.get("level")) not in ("global", "genre", "project"):
        # rejected 不在 level 枚举（rejected 靠 status=deprecated 表达）；独立目录
        if _rel_dir_of(d) != "rejected":
            return False, "level 非法: %s" % d.get("level")
    if not isinstance(d.get("action"), list):
        return False, "action 非列表"
    try:
        cf = float(d.get("confidence"))
        if not (0.0 <= cf <= 1.0):
            return False, "confidence 越界"
    except (TypeError, ValueError):
        return False, "confidence 非数值"
    try:
        int(d.get("validated_projects"))
    except (TypeError, ValueError):
        return False, "validated_projects 非整数"
    if str(d.get("status")) not in ("active", "deprecated"):
        return False, "status 非法"
    if d.get("level") == "genre" and not d.get("genre"):
        return False, "genre 级缺 genre 字段"
    if d.get("level") == "project" and not d.get("scope"):
        return False, "project 级缺 scope 字段"
    return True, ""


def _rel_dir_of(d):
    # 推断条目应处的顶层目录（rejected 由 status=deprecated 判定）
    if str(d.get("status")) == "deprecated":
        return "rejected"
    return str(d.get("level"))


def govern(platform_root, write=True, proposed_by="unknown", model="unknown"):
    """对 platform_root/memory/ 做体检，返回 report dict。"""
    cfg = _load_cfg()
    mem_root = os.path.join(platform_root, "memory")
    if not os.path.isdir(mem_root):
        return {"meta": {"scorer": "memory-governor", "scored_at": _now(),
                         "platform": os.path.basename(platform_root)},
                "target": {"target_type": "memory", "memory_root": _rel(platform_root, mem_root)},
                "signals": [], "composite": {"health": 0}, "fatal": True,
                "gate": {"decision": "block", "reasons": ["memory/ 目录不存在"]},
                "duplicates": [], "recommendations": ["创建 memory/ 四层目录与 晋升机制.md"]}

    files = []
    for dp, _, fns in os.walk(mem_root):
        for fn in fns:
            if fn.endswith(".yaml") and fn != "晋升机制.md":
                files.append(os.path.join(dp, fn))
    files.sort()

    signals = []
    fatal = False
    cautions = []
    sc2_hits = []
    sc3_hits = []
    parsed = []  # (fp, d, dir_level, genre_sub)

    for fp in files:
        d = _safe_load(fp)
        if d is None:
            signals.append({"name": "SC1_schema", "ok": False, "detail": "%s 解析失败" % _rel(platform_root, fp)})
            fatal = True
            cautions.append("%s 解析失败" % _rel(platform_root, fp))
            continue
        ok, msg = _check_schema(d, cfg)
        if not ok:
            signals.append({"name": "SC1_schema", "ok": False, "detail": "%s: %s" % (_rel(platform_root, fp), msg)})
            fatal = True
            cautions.append("%s schema: %s" % (_rel(platform_root, fp), msg))
            continue
        dir_level, genre_sub = _level_of_path(mem_root, fp)
        parsed.append((fp, d, dir_level, genre_sub))
        # SC2 level↔dir
        expect_dir = _rel_dir_of(d)
        if dir_level != expect_dir:
            sc2_hits.append("%s: 文件在 %s/ 但 level/status=%s" % (_rel(platform_root, fp), dir_level, expect_dir))
        if d.get("level") == "genre" and genre_sub and d.get("genre") and genre_sub != d.get("genre"):
            sc2_hits.append("%s: 目录题材 %s ≠ genre 字段 %s" % (_rel(platform_root, fp), genre_sub, d.get("genre")))
        # SC3 status↔位置（deprecated 必在 rejected/）
        if str(d.get("status")) == "deprecated" and dir_level != "rejected":
            sc3_hits.append("%s: status=deprecated 但不在 rejected/" % _rel(platform_root, fp))
        if str(d.get("status")) == "active" and dir_level == "rejected":
            sc3_hits.append("%s: status=active 却在 rejected/" % _rel(platform_root, fp))

    # SC4 晋升门槛
    sc4_hits = []
    for fp, d, dl, gs in parsed:
        lvl = str(d.get("level"))
        vp = int(d.get("validated_projects"))
        if lvl == "genre" and vp < cfg["min_genre"]:
            sc4_hits.append("%s: genre 级 validated_projects=%d < %d" % (_rel(platform_root, fp), vp, cfg["min_genre"]))
        if lvl == "global" and vp < cfg["min_global"]:
            sc4_hits.append("%s: global 级 validated_projects=%d < %d" % (_rel(platform_root, fp), vp, cfg["min_global"]))

    # SC5 重复检测（同 level 同 genre 内）
    sc5_dups = []
    groups = {}
    for fp, d, dl, gs in parsed:
        key = (str(d.get("level")), gs or "")
        groups.setdefault(key, []).append((fp, d))
    for (lvl, gs), items in groups.items():
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                sim = _similarity(items[i][1].get("problem"), items[j][1].get("problem"))
                if sim >= cfg["sim_threshold"]:
                    sc5_dups.append({
                        "a": _rel(platform_root, items[i][0]),
                        "b": _rel(platform_root, items[j][0]),
                        "similarity": round(sim, 3),
                        "problem_a": items[i][1].get("problem"),
                        "problem_b": items[j][1].get("problem"),
                    })

    # SC6 失效引用（action 中相对路径存在性）
    sc6_hits = []
    if cfg["ref_check"]:
        for fp, d, dl, gs in parsed:
            base = os.path.dirname(fp)
            for act in (d.get("action") or []):
                if isinstance(act, str) and (".md" in act or "../" in act or "./" in act):
                    cand = os.path.normpath(os.path.join(base, act))
                    if not os.path.exists(cand):
                        sc6_hits.append("%s: action 引用缺失 %s" % (_rel(platform_root, fp), act))

    # SC7 孤立 README：直接存放 MEM-*.yaml 的目录须有 README
    sc7_hits = []
    if cfg["require_readme"]:
        for dp, _, fns in os.walk(mem_root):
            if any(fn.endswith(".yaml") and fn.startswith("MEM-") for fn in fns):
                if not os.path.isfile(os.path.join(dp, "README.md")):
                    sc7_hits.append("%s/ 缺 README.md" % _rel(platform_root, dp))

    # 汇总 signals
    signals.append({"name": "SC1_schema", "ok": not fatal, "detail": "解析与字段校验"})
    signals.append({"name": "SC2_level_dir", "ok": not sc2_hits, "detail": "; ".join(sc2_hits) or "一致"})
    signals.append({"name": "SC3_status_pos", "ok": not sc3_hits, "detail": "; ".join(sc3_hits) or "一致"})
    signals.append({"name": "SC4_promotion", "ok": not sc4_hits, "detail": "; ".join(sc4_hits) or "达标"})
    signals.append({"name": "SC5_dedup", "ok": not sc5_dups, "detail": "%d 对重复" % len(sc5_dups)})
    signals.append({"name": "SC6_reference", "ok": not sc6_hits, "detail": "; ".join(sc6_hits) or "无失效引用"})
    signals.append({"name": "SC7_readme", "ok": not sc7_hits, "detail": "; ".join(sc7_hits) or "各级 README 齐备"})

    for h in sc2_hits:
        cautions.append("FATAL " + h)
    for h in sc3_hits:
        cautions.append("FATAL " + h)
    for h in sc4_hits:
        cautions.append(h)
    for h in sc5_dups:
        cautions.append("重复 %s ~ %s (%.2f)" % (h["a"], h["b"], h["similarity"]))
    for h in sc6_hits:
        cautions.append(h)
    for h in sc7_hits:
        cautions.append(h)

    fatal = fatal or bool(sc2_hits) or bool(sc3_hits)
    caution_count = len(sc4_hits) + len(sc5_dups) + len(sc6_hits) + len(sc7_hits)
    health = max(0, 100 - (cfg["fatal_penalty"] if fatal else 0) - caution_count * cfg["caution_penalty"])

    if fatal:
        decision = "block"
    elif caution_count > 0:
        decision = "caution"
    else:
        decision = "proceed"

    recs = []
    if sc2_hits or sc3_hits:
        recs.append("移动错配条目到正确目录（按 level/status 归位）")
    if sc4_hits:
        recs.append("未达晋升门槛的条目应降级（global→genre 或 genre→project）")
    if sc5_dups:
        recs.append("合并重复条目，保留置信度高者，其余移 rejected/")
    if sc6_hits:
        recs.append("修正或删除失效引用的 action")
    if sc7_hits:
        recs.append("补各级 README.md")

    report = {
        "meta": {"scorer": "memory-governor", "scored_at": _now(),
                 "platform": os.path.basename(platform_root)},
        "target": {"target_type": "memory",
                   "target_id": os.path.basename(platform_root),
                   "memory_root": _rel(platform_root, mem_root)},
        "signals": signals,
        "composite": {"health": health},
        "fatal": fatal,
        "gate": {"decision": decision, "reasons": cautions},
        "duplicates": sc5_dups,
        "recommendations": recs,
    }

    if write:
        _write_report(platform_root, report, proposed_by, model)
    return report


def _write_report(platform_root, report, proposed_by, model):
    d = os.path.join(platform_root, "analysis", "memory")
    os.makedirs(d, exist_ok=True)
    seq = 1
    while os.path.isfile(os.path.join(d, "MEM-%02d.yaml" % seq)):
        seq += 1
    rid = "MEM-%02d" % seq
    report["meta"]["report_id"] = rid
    p = os.path.join(d, rid + ".yaml")
    with open(p, "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(report))
    audit_log.record(platform_root, "memory_gov", agent=proposed_by, model=model,
                     files=[_rel(platform_root, p)], result="success",
                     detail="gate=%s" % report["gate"]["decision"])
    return rid


def _print_report(rep):
    g = rep.get("gate", {})
    comp = rep.get("composite", {})
    print("门禁：%s" % g.get("decision", "?"))
    print("健康分：%s" % comp.get("health"))
    print("信号：")
    for s in rep.get("signals", []):
        flag = "OK " if s.get("ok") else "FAIL"
        print("  [%s] %s | %s" % (flag, s["name"], s.get("detail")))
    for r in g.get("reasons", []):
        print("  理由：%s" % r)
    for dup in rep.get("duplicates", []):
        print("  重复：%s ~ %s (sim=%.2f)" % (dup["a"], dup["b"], dup["similarity"]))
    for rc in rep.get("recommendations", []):
        print("  建议：%s" % rc)


def main():
    p = argparse.ArgumentParser(prog="memory_governor")
    p.add_argument("--platform-root", required=True)
    p.add_argument("cmd", choices=["validate", "report", "dedup"])
    p.add_argument("--no-write", action="store_true")
    p.add_argument("--proposed-by", default="unknown")
    p.add_argument("--model", default="unknown")
    args = p.parse_args()
    rep = govern(args.platform_root, write=not args.no_write,
                 proposed_by=args.proposed_by, model=args.model)
    if args.cmd == "dedup":
        for dup in rep.get("duplicates", []):
            print("%s ~ %s (sim=%.2f)" % (dup["a"], dup["b"], dup["similarity"]))
        print("重复对数：%d" % len(rep.get("duplicates", [])))
    else:
        _print_report(rep)
    sys.exit(0 if rep["gate"]["decision"] != "block" else 1)


if __name__ == "__main__":
    main()
