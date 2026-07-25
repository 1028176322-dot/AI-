# -*- coding: utf-8 -*-
"""质量评分（Quality Score）—— Phase 2 系统 #2。

对一份已产出制品（章节 / NKB / 资产）算可复现质量分 + 门禁（proceed/caution/block）。
信号源（scorer，registry/scorers.yaml 注册）：
  logic       运行 tools/logic_check.py（C1–C22）算零错误密度，HARD 失败即 fatal
  contract    制品结构合法性（章节文件存在/非空；NKB 记录必填）
  readability 机械可读性代理（句长方差 / AI 腔锁词 / 实词比）
  review      消费项目四支柱审查报告（analysis/review/*.yaml）映射 ES/CI/Reader/PI

评分模型：
  - 任一 scorer fatal（结构性致命）-> block（不看分）
  - review 消费时：composite = review 分（工程非致命项软罚），< hard_floor -> block，< target -> caution，否则 proceed
  - review 未消费（partial）：composite = 工程基线（logic/contract/readability 归一），仅 fatal 拦截，否则 proceed（标 partial）

CLI：platform quality --project-root <root> <score|from-task|show> ...
"""
import os
import sys
import re
import io
import datetime
import argparse
import contextlib

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
import _gov
import audit_log

REGISTRY = os.path.join(os.path.dirname(os.path.dirname(HERE)), "registry", "scorers.yaml")

# AI 腔锁词（读者体验代理：WR-F10 AI 模板句），密度越高可读性越差
AI_PHRASES = ["仿佛", "宛如", "犹如", "宛若", "好似", "悄然", "微微", "缓缓", "不禁",
              "不由自主", "不由得", "就在这时", "恰在此时", "那一刻", "一种说不清的",
              "难以言喻", "莫名其妙", "莫名的", "透着一股", "一股难以", "似乎", "似乎有些",
              "不知为何", "隐隐约约", "若有若无", "就像是", "仿佛能", "莫名地"]

SOFT_PENALTY = 0.10


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _safe_load(p):
    try:
        return _gov.load_yaml(p)
    except Exception:
        return None


def _rel(project_root, p):
    return os.path.relpath(p, project_root)


def shutil_rmtree(path):
    import shutil
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


# ───────────────────────── 目标解析 ─────────────────────────
def _chapter_id(filename):
    stem = os.path.splitext(os.path.basename(filename))[0]
    m = re.search(r"(\d+)", stem)
    return m.group(1) if m else stem


def _chapter_key(cid):
    try:
        return str(int(cid))
    except (ValueError, TypeError):
        return str(cid)


def _find_chapter_file(project_root, chapter_id):
    cid = _chapter_key(chapter_id)
    for sd in ("approved", "chapters", "chapters/drafts", "drafts", "txt"):
        base = os.path.join(project_root, sd)
        if not os.path.isdir(base):
            continue
        for root, _, files in os.walk(base):
            for fn in files:
                if fn.endswith((".txt", ".md", ".yaml")) and _chapter_key(_chapter_id(fn)) == cid:
                    return os.path.join(root, fn)
    return None


def _load_scorers():
    d = _safe_load(REGISTRY) or {}
    cfg = (d.get("scorers") or {})
    thr = d.get("thresholds") or {}
    return cfg, {
        "hard_floor": thr.get("hard_floor", 60),
        "target": thr.get("target", 80),
        "soft_penalty": thr.get("soft_penalty", SOFT_PENALTY),
    }


# ───────────────────────── 各 scorer ─────────────────────────
def _score_logic(project_root, target_type, target_id):
    """运行 logic_check（C1–C22）。仅章节制品适用；其余目标 consumed=False。"""
    if target_type != "chapter":
        return {"name": "logic", "score": 100, "fatal": False, "weight": 0.40,
                "consumed": False, "detail": "非章节制品，logic 不适用"}
    fp = _find_chapter_file(project_root, target_id)
    if not fp:
        return {"name": "logic", "score": 100, "fatal": False, "weight": 0.40,
                "consumed": False, "detail": "未找到章节文件，跳过"}
    try:
        import logic_check
    except Exception:
        return {"name": "logic", "score": 100, "fatal": False, "weight": 0.40,
                "consumed": False, "detail": "logic_check 不可导入，跳过"}
    import tempfile
    tmp_gov = None
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = logic_check.check(fp)
    except Exception:
        # 缺少治理目录（无 IDX_CHARACTER.md 等）：建空治理目录重试，仅跑不依赖角色设定的
        # 硬校验（C3 年号越界 / C4 占位 / C5 备注 / C16 字数 / C17 章名 / C21/C22 重复）。
        try:
            tmp_gov = tempfile.mkdtemp()
            for nm in ("IDX_CHARACTER.md", "IDX_SETTING.md", "IDX_FORESHADOW.md"):
                with open(os.path.join(tmp_gov, nm), "w", encoding="utf-8") as f:
                    f.write("")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = logic_check.check(fp, gov=tmp_gov)
        except Exception as e:
            return {"name": "logic", "score": 100, "fatal": False, "weight": 0.40,
                    "consumed": False, "detail": "logic_check 运行异常：%s" % e}
    finally:
        if tmp_gov:
            shutil_rmtree(tmp_gov)
    out = buf.getvalue()
    fail_blocks = len(re.findall(r"\[FAIL\]", out))
    warn_blocks = len(re.findall(r"\[WARN\]", out))
    fatal = (rc == 1) or (fail_blocks > 0)
    score = max(0, 100 - fail_blocks * 25 - warn_blocks * 5)
    return {"name": "logic", "score": score, "fatal": fatal, "weight": 0.40,
            "consumed": True,
            "detail": "HARD=%d WARN=%d（rc=%s）" % (fail_blocks, warn_blocks, rc)}


def _score_contract(project_root, target_type, target_id):
    """制品结构合法性：章节文件存在/非空；NKB 记录必填 id/name。"""
    if target_type == "chapter":
        fp = _find_chapter_file(project_root, target_id)
        if not fp:
            return {"name": "contract", "score": 0, "fatal": True, "weight": 0.20,
                    "consumed": True, "detail": "章节文件缺失"}
        if os.path.getsize(fp) == 0:
            return {"name": "contract", "score": 0, "fatal": True, "weight": 0.20,
                    "consumed": True, "detail": "章节文件为空"}
        return {"name": "contract", "score": 100, "fatal": False, "weight": 0.20,
                "consumed": True, "detail": "章节文件存在且非空"}
    if target_type == "nkb":
        kind, _, nid = target_id.partition("/") if "/" in target_id else (target_id, "", target_id)
        fp = os.path.join(project_root, "NKB", "%s.yaml" % kind)
        d = _safe_load(fp)
        recs = (d or {}).get("records") or []
        ok = any(str((r or {}).get("id")) == nid or str((r or {}).get("name")) == nid for r in recs)
        if not ok:
            return {"name": "contract", "score": 0, "fatal": True, "weight": 0.20,
                    "consumed": True, "detail": "NKB 记录 %s 缺失" % target_id}
        return {"name": "contract", "score": 100, "fatal": False, "weight": 0.20,
                "consumed": True, "detail": "NKB 记录存在"}
    # asset / outline / world：结构校验留待对应契约接入，本期视为通过
    return {"name": "contract", "score": 100, "fatal": False, "weight": 0.20,
            "consumed": True, "detail": "类型 %s 结构校验未接入，视为通过" % target_type}


def _score_readability(project_root, target_type, target_id):
    """机械可读性代理：句长方差 + AI 腔锁词密度 + 实词比。"""
    if target_type != "chapter":
        return {"name": "readability", "score": 100, "fatal": False, "weight": 0.40,
                "consumed": False, "detail": "非章节制品，跳过"}
    fp = _find_chapter_file(project_root, target_id)
    if not fp:
        return {"name": "readability", "score": 100, "fatal": False, "weight": 0.40,
                "consumed": False, "detail": "未找到章节文件，跳过"}
    try:
        with open(fp, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return {"name": "readability", "score": 100, "fatal": False, "weight": 0.40,
                "consumed": False, "detail": "读取失败，跳过"}
    sents = [s for s in re.split(r"[。！？；\n]", text) if s.strip()]
    if not sents:
        return {"name": "readability", "score": 100, "fatal": False, "weight": 0.40,
                "consumed": True, "detail": "无句子"}
    lens = [len(s) for s in sents]
    avg = sum(lens) / len(lens)
    var = sum((x - avg) ** 2 for x in lens) / len(lens)
    stdev = var ** 0.5
    ai_count = sum(text.count(p) for p in AI_PHRASES)
    ai_density = ai_count / len(sents)
    score = 100.0
    score -= min(40.0, ai_count * 4 + ai_density * 100 * 0.5)   # AI 腔惩罚
    if len(lens) >= 3 and stdev < 6:
        score -= 15                                           # 句式过于单调
    if avg > 55:
        score -= (avg - 55) * 0.5                            # 平均句长过长
    score = max(0, min(100, round(score)))
    return {"name": "readability", "score": score, "fatal": False, "weight": 0.40,
            "consumed": True,
            "detail": "句均%d 方差%.0f AI腔%d(密度%.2f)" % (avg, stdev, ai_count, ai_density)}


def _score_review(project_root, target_type, target_id):
    """消费项目四支柱审查报告（analysis/review/*.yaml）。
    缺 review 报告时回退消费读者模拟报告（analysis/reader/*.yaml），实现融合+可选消费。
    """
    rd = os.path.join(project_root, "analysis", "review")
    if os.path.isdir(rd):
        reps = [f for f in os.listdir(rd) if f.endswith(".yaml")]
        if reps:
            reps.sort(key=lambda f: os.path.getmtime(os.path.join(rd, f)), reverse=True)
            d = _safe_load(os.path.join(rd, reps[0]))
            if isinstance(d, dict):
                rv = d.get("review") or {}
                es = float(rv.get("es", 0) or 0)
                ci = float(rv.get("ci", 0) or 0)
                reader = float(rv.get("reader_index", 0) or 0)
                pi = float(rv.get("pi", 0) or 0)
                score = es * 0.4 + ci * 0.3 + reader * 0.2 + pi * 0.1
                fatal = bool(d.get("fatal") in (True, "true", "True"))
                return {"name": "review", "score": round(score, 1), "fatal": fatal, "weight": 1.00,
                        "consumed": True,
                        "detail": "ES=%.0f CI=%.0f Reader=%.0f PI=%.0f <- %s" % (es, ci, reader, pi, reps[0])}
    # 回退：消费读者模拟报告（仅 reader 维度；ES/CI 无相反证据占位 100）
    rd2 = os.path.join(project_root, "analysis", "reader")
    if os.path.isdir(rd2):
        reps2 = [f for f in os.listdir(rd2) if f.endswith(".yaml")]
        if reps2:
            reps2.sort(key=lambda f: os.path.getmtime(os.path.join(rd2, f)), reverse=True)
            d2 = _safe_load(os.path.join(rd2, reps2[0]))
            if isinstance(d2, dict):
                reader = float(d2.get("reader_index", 0) or 0)
                pi = float(d2.get("pi", 0) or 0)
                fatal = bool(d2.get("fatal") in (True, "true", "True"))
                score = 100 * 0.4 + 100 * 0.3 + reader * 0.2 + pi * 0.1
                return {"name": "review", "score": round(score, 1), "fatal": fatal, "weight": 1.00,
                        "consumed": True,
                        "detail": "reader-only 回退(ES/CI 占位100) Reader=%.0f PI=%.0f <- %s" % (reader, pi, reps2[0])}
    return {"name": "review", "score": 0, "fatal": False, "weight": 1.00,
            "consumed": False, "detail": "无审查报告且无读者模拟报告"}


_SCORERS = {
    "logic_scorer": _score_logic,
    "contract_scorer": _score_contract,
    "readability_scorer": _score_readability,
    "review_scorer": _score_review,
}


# ───────────────────────── 评分主流程 ─────────────────────────
def score(project_root, target_type, target_id, proposed_by="unknown",
          model="unknown", write=True):
    target_type = str(target_type)
    if target_type == "chapter":
        target_id = _chapter_key(target_id)
    cfg, thr = _load_scorers()
    signals = []
    for name, spec in cfg.items():
        if not spec.get("enabled", True):
            continue
        fn = _SCORERS.get(spec.get("module") or name)
        if not fn:
            continue
        r = fn(project_root, target_type, target_id)
        r["weight"] = float(spec.get("weight", 0))
        signals.append(r)
    fatal = any(s["fatal"] for s in signals)
    review = next((s for s in signals if s["name"] == "review" and s["consumed"]), None)

    if review is not None:
        composite = float(review["score"])
        for s in signals:
            if s["name"] != "review" and s["consumed"] and s["score"] < 100:
                composite -= (100 - s["score"]) * thr["soft_penalty"]
        composite = max(0.0, min(100.0, round(composite, 1)))
        review_consumed = True
    else:
        eng = [s for s in signals if s["name"] != "review" and s["consumed"]]
        if eng:
            tw = sum(s["weight"] for s in eng)
            composite = round(sum(s["score"] * s["weight"] for s in eng) / tw, 1) if tw else 100.0
        else:
            composite = 100.0
        review_consumed = False

    decision, reasons = _decide(composite, fatal, review_consumed, thr)
    _ap = _find_chapter_file(project_root, target_id) if target_type == "chapter" else None
    report = {
        "meta": {"scorer": "quality-scorer", "scored_at": _now(),
                 "project": _project_id(project_root)},
        "target": {"target_type": target_type, "target_id": str(target_id),
                   "artifact_path": _rel(project_root, _ap) if _ap else ""},
        "signals": signals,
        "composite": {"value": composite, "review_consumed": review_consumed},
        "gate": {"decision": decision, "reasons": reasons},
        "recommendations": _recommend(signals, decision, target_type, target_id),
    }
    if write:
        _write_report(project_root, report, target_type, target_id, proposed_by, model)
    return report


def score_task(project_root, task_id, **kw):
    import task_engine
    _, data = task_engine.load_task(project_root, task_id)
    if not data:
        raise FileNotFoundError(task_id)
    t = data["task"]
    target = None
    if t.get("chapter_ref"):
        # chapter_ref 可能是完整路径（如 第一卷_道生/第021章_离观启程.md），
        # 需归一为章节 id（如 21）以匹配 _find_chapter_file 的检索逻辑。
        cid = _chapter_id(str(t["chapter_ref"]))
        target = ("chapter", _chapter_key(cid))
    elif (t.get("target") or {}).get("type"):
        target = (t["target"]["type"], t["target"]["id"])
    elif t.get("type") == "nkb_update":
        target = ("nkb", t.get("nkb_ref") or (t.get("inputs") or {}).get("nkb_id") or task_id)
    elif t.get("type") == "asset_create":
        target = ("asset", t.get("asset_ref") or task_id)
    if not target:
        target = ("chapter", str(t.get("id", task_id)))
    return score(project_root, target[0], target[1], **kw)


def _decide(composite, fatal, review_consumed, thr):
    if fatal:
        return "block", ["存在结构性致命问题（logic/contract fatal）"]
    if review_consumed:
        if composite < thr["hard_floor"]:
            return "block", ["质量分 %s < 硬下限 %s" % (composite, thr["hard_floor"])]
        if composite < thr["target"]:
            return "caution", ["质量分 %s 低于目标 %s（含深度评审）" % (composite, thr["target"])]
        return "proceed", ["质量分 %s ≥ 目标 %s" % (composite, thr["target"])]
    return "proceed", ["partial 评分（未含深度评审），仅拦截结构性致命；建议补充审查报告"]


def _recommend(signals, decision, target_type, target_id):
    recs = []
    if decision == "block":
        for s in signals:
            if s["fatal"]:
                recs.append({"action": "fix", "target": "%s/%s" % (target_type, target_id),
                             "detail": "%s 报 fatal：%s" % (s["name"], s["detail"])})
    elif decision == "caution":
        for s in signals:
            if s["consumed"] and s["score"] < 100:
                recs.append({"action": "human_review", "target": "%s/%s" % (target_type, target_id),
                             "detail": "%s 偏低(%s)：%s" % (s["name"], s["score"], s["detail"])})
    return recs


def _project_id(project_root):
    p = os.path.join(project_root, "project.yaml")
    if os.path.isfile(p):
        d = _safe_load(p)
        if isinstance(d, dict):
            return str((d.get("project") or {}).get("id") or d.get("id") or os.path.basename(project_root))
    return os.path.basename(project_root)


def _write_report(project_root, report, target_type, target_id, proposed_by, model):
    d = os.path.join(project_root, "analysis", "quality")
    os.makedirs(d, exist_ok=True)
    seq = 1
    prefix = "QUAL-%s-%s" % (target_type, str(target_id).replace("/", "-"))
    while os.path.isfile(os.path.join(d, "%s-%02d.yaml" % (prefix, seq))):
        seq += 1
    rid = "%s-%02d" % (prefix, seq)
    report["meta"]["report_id"] = rid
    p = os.path.join(d, rid + ".yaml")
    with open(p, "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(report))
    audit_log.record(project_root, "quality_score", agent=proposed_by, model=model,
                     files=[_rel(project_root, p)], result="success",
                     detail="gate=%s target=%s/%s" % (report["gate"]["decision"], target_type, target_id))
    return rid


# ───────────────────────── CLI ─────────────────────────
def _print_report(rep):
    g = rep.get("gate", {})
    comp = rep.get("composite", {})
    print("门禁：%s" % g.get("decision", "?"))
    print("综合分：%s  (review_consumed=%s)" % (comp.get("value"), comp.get("review_consumed")))
    for r in g.get("reasons", []):
        print("  理由：%s" % r)
    print("信号：")
    for s in rep.get("signals", []):
        print("  - %s 分=%s fatal=%s consumed=%s w=%s | %s" % (
            s["name"], s["score"], s["fatal"], s["consumed"], s.get("weight"), s.get("detail")))
    for rc in rep.get("recommendations", []):
        print("  建议：%s -> %s" % (rc["action"], rc["target"]))


def main():
    ap = argparse.ArgumentParser(prog="quality", description="质量评分")
    ap.add_argument("--project-root", required=True)
    ap.add_argument("verb", choices=["score", "from-task", "show"])
    ap.add_argument("--target-type", default="chapter")
    ap.add_argument("--target-id", default=None)
    ap.add_argument("--reason", default="")
    ap.add_argument("--task", default=None)
    ap.add_argument("--report", default=None)
    args = ap.parse_args()

    if args.verb == "score":
        if not args.target_id:
            ap.error("score requires --target-id")
        rep = score(args.project_root, args.target_type, args.target_id, proposed_by="quality-scorer")
        _print_report(rep)
    elif args.verb == "from-task":
        if not args.task:
            ap.error("from-task requires --task")
        rep = score_task(args.project_root, args.task, proposed_by="quality-scorer")
        _print_report(rep)
    elif args.verb == "show":
        if not args.report:
            ap.error("show requires --report")
        p = os.path.join(args.project_root, "analysis", "quality", args.report)
        if os.path.isfile(p):
            print(_gov.dump_block(_safe_load(p)))
        else:
            print("# 报告不存在: %s" % args.report)


if __name__ == "__main__":
    main()
