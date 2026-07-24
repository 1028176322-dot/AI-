# -*- coding: utf-8 -*-
"""读者模拟（Reader Simulation）—— Phase 2 系统 #3。

启发式读者体验模拟，对齐 core/review/审查体系.md 支柱3（RR01–RR08 + Immersion +
Emotion Curve + PI + Persona）。
- 产出 analysis/reader/*.yaml
- 自带 gate（proceed/caution/block）：Fatal B（RR04缺失/RR03平/RR06极高/情绪曲线平）→ block；
  Reader Index<60 或 PI<60 → caution；否则 proceed
- 可选被质量评分(#2)回退消费（analysis/reader/ 存在时）
- 预留 LLM 增强钩子（model != "heuristic" 时调用，本环境默认走启发式）

CLI：platform reader --project-root <root> <sim|from-task|show> ...
"""
import os
import sys
import re
import argparse
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _gov
import audit_log
import quality_scorer as _qs   # 复用 _find_chapter_file/_chapter_key/_project_id/_rel/_now/_safe_load

REGISTRY = os.path.join(os.path.dirname(HERE), "registry", "readers.yaml")

# ── 默认词表/阈值（registry 缺失时兜底）──
DEFAULT_THRESHOLDS = {
    "rr04_min": 20, "emotion_flat_max": 8, "fatigue_extreme": 80,
    "curve_flat_var": 4, "reader_index_floor": 60, "pi_floor": 60,
}
HOOK_WORDS = ["突然", "竟", "没想到", "却", "暗", "杀", "血", "危机", "阴谋", "秘密",
              "谁知", "不料", "偏偏", "就在这时", "与此同时", "一道", "只见", "轰", "嗖", "诡", "寒", "令"]
CONCLUSIVE_WORDS = ["落幕", "谢幕", "结束", "自此", "此后", "一切归于", "终于平静",
                    "尘埃落定", "皆", "全", "尽", "了", "完", "终究", "终是"]
END_HOOK_WORDS = ["却", "竟", "突然", "没想到", "原来", "未料", "悬念", "谜", "暗中", "然而",
                  "但", "可", "偏偏", "就在这时", "与此同时", "远方", "未知", "将要", "之后",
                  "尚未", "究竟", "何以", "谁能", "隐约", "似有"]
EMOTION_WORDS = ["怒", "喜", "悲", "惊", "恐", "惧", "恨", "爱", "痛", "慌", "恼", "愤",
                 "怯", "慕", "妒", "伤", "狂", "安", "松", "颤", "凛", "凄", "恸", "欣"]
REWARD_WORDS = ["终于", "得以", "成功", "化解", "揭晓", "真相", "获得", "突破", "胜", "赢",
                "报", "雪", "清白", "重获", "掌握", "顿悟", "觉醒", "晋级", "大喜", "欣喜", "如释", "喜", "悦"]
COOL_WORDS = ["打脸", "反杀", "碾压", "逆转", "扬眉", "吐气", "臣服", "震撼", "惊艳", "佩服",
              "跪", "败", "死", "灭", "吊打", "一招", "秒", "威风", "霸气", "震慑", "惊惧", "溃", "崩"]
INFO_WORDS = ["乃是", "所谓", "据闻", "传说", "规矩", "法则", "境界", "功法", "朝堂", "年号",
              "封号", "门派", "宗门", "秘籍", "灵", "妖", "魔", "仙", "阵法", "符箓", "丹",
              "兵器", "官制", "品阶", "气海", "灵根", "真元"]
DEFAULT_BLOCK_WORDS = ["手机", "电脑", "汽车", "微信", "地铁", "咖啡", "银行", "公司", "警察",
                       "法律", "科学", "物理", "化学", "实验", "数据", "网络", "互联网", "程序",
                       "代码", "系统", "人工智能", "换句话说", "简而言之", "作者", "读者", "说实话"]
DEFAULT_IMMERSION_PENALTY = 12
DEFAULT_PERSONA_WEIGHTS = {
    "veteran": [0.8, 0.9, 1.2, 1.0, 1.0, 1.0, 0.9, 1.3, 1.1],
    "newcomer": [1.4, 1.3, 1.0, 1.3, 1.0, 1.0, 1.0, 0.8, 1.0],
    "pulp": [0.9, 0.9, 1.0, 1.0, 1.3, 1.0, 1.5, 0.8, 0.9],
    "plot": [0.8, 0.9, 1.3, 1.3, 1.0, 1.0, 1.0, 1.2, 1.0],
    "worldbuilding": [0.8, 1.0, 1.0, 0.9, 0.9, 1.0, 0.8, 1.5, 1.3],
}


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _count(text, words):
    return sum(text.count(w) for w in words)


def _density(text, words):
    n = max(1, len(text))
    return _count(text, words) / (n / 1000.0)


def _repeat_ratio(body):
    clean = re.sub(r"\s+", "", body)
    if len(clean) < 4:
        return 0.0
    bigs = [clean[i:i + 2] for i in range(len(clean) - 1)]
    rep = sum(1 for i in range(1, len(bigs)) if bigs[i] == bigs[i - 1])
    return rep / max(1, len(bigs))


def _emotion_curve(body, words):
    L = len(body)
    if L == 0:
        return [0] * 6
    k = 6
    seg = max(1, L // k)
    out = []
    for i in range(k):
        s = body[i * seg:(i + 1) * seg] if i < k - 1 else body[i * seg:]
        if not s:
            out.append(0)
            continue
        c = _count(s, words) + s.count("「") * 0.5 + (s.count("！") + s.count("!")) * 0.5
        out.append(int(_clamp(c / (len(s) / 1000.0) * 7, 0, 100)))
    return out


def _read_chapter_body(fp):
    with open(fp, "r", encoding="utf-8") as f:
        text = f.read()
    lines = text.split("\n")
    if lines and (re.match(r"^[《「]", lines[0].strip()) or 0 < len(lines[0].strip()) < 25):
        return "\n".join(lines[1:])
    return text


def _load_cfg():
    d = _qs._safe_load(REGISTRY) or {}
    thr = dict(DEFAULT_THRESHOLDS)
    thr.update(d.get("thresholds") or {})
    persona = d.get("persona_weights") or DEFAULT_PERSONA_WEIGHTS
    block_words = d.get("immersion_block_words") or DEFAULT_BLOCK_WORDS
    penalty = d.get("immersion_penalty_per_hit") or DEFAULT_IMMERSION_PENALTY
    return {"thresholds": thr, "persona": persona, "block_words": block_words,
            "immersion_penalty": penalty}


def _compute(body, cfg):
    thr = cfg["thresholds"]
    persona_weights = cfg["persona"]
    block_words = cfg["block_words"]
    penalty = cfg["immersion_penalty"]
    n = max(1, len(body))

    sentences = [s for s in re.split(r"[。！？!?；;]", body) if s.strip()]
    slens = [len(s) for s in sentences] or [0]
    avg_len = sum(slens) / len(slens)
    long_ratio = sum(1 for x in slens if x > 60) / max(1, len(slens))
    var = statistics.pvariance(slens) if len(slens) > 1 else 0.0

    paras = [p for p in re.split(r"\n+", body) if p.strip()]
    long_para_ratio = sum(1 for p in paras if len(p) > 400) / max(1, len(paras))
    dialogue_ratio = (body.count("「") + body.count("“")) / max(1, len(paras))

    # RR01 第一印象（前 200 字）
    head = body[:200]
    hh = sum(head.count(w) for w in HOOK_WORDS) + (1 if head.lstrip()[:1] in "「\"" else 0)
    rr01 = _clamp(60 + hh * 10, 0, 100)

    # RR02 阅读流畅
    fluency_pen = long_ratio * 50 + max(0.0, 5 - var) * 2 + max(0.0, avg_len - 45) * 0.4
    rr02 = _clamp(100 - fluency_pen, 0, 100)

    # RR03 情绪体验
    emo_count = _count(body, EMOTION_WORDS) + body.count("「") * 0.5 + (body.count("！") + body.count("!")) * 0.5
    emo_density = emo_count / (n / 1000.0)
    rr03 = _clamp(emo_density * 7, 0, 100)
    rr03_flat = rr03 < thr["emotion_flat_max"]

    # RR04 期待值（末 300 字）
    tail = body[-300:]
    has_conclusive = any(w in tail for w in CONCLUSIVE_WORDS)
    hook_hits = _count(tail, END_HOOK_WORDS)
    if has_conclusive and hook_hits == 0:
        rr04 = 10.0
        rr04_missing = True
    else:
        rr04 = _clamp(40 + hook_hits * 20, 0, 100)
        rr04_missing = rr04 < thr["rr04_min"]

    # RR05 奖励感
    rr05 = _clamp(_density(body, REWARD_WORDS) * 9, 0, 100)

    # RR06 疲劳度(raw)
    info_density = _density(body, INFO_WORDS)
    repeat_ratio = _repeat_ratio(body)
    fatigue = long_para_ratio * 60 + min(30.0, info_density * 1.2) * (1 - dialogue_ratio) + repeat_ratio * 40
    rr06 = _clamp(fatigue, 0, 100)
    rr06_extreme = rr06 > thr["fatigue_extreme"]

    # RR07 爽点兑现
    rr07 = _clamp(_density(body, COOL_WORDS) * 12, 0, 100)

    # RR08 信息获取
    rr08 = _clamp(min(80.0, _density(body, INFO_WORDS) * 8), 0, 100)

    # Immersion
    imm_hits = sum(body.count(w) for w in block_words)
    immersion = _clamp(100 - imm_hits * penalty, 0, 100)

    # Emotion Curve
    curve = _emotion_curve(body, EMOTION_WORDS)
    curve_flat = (statistics.pvariance(curve) if len(curve) > 1 else 0.0) < thr["curve_flat_var"]

    # PI 付费意愿
    pi = _clamp(0.35 * rr04 + 0.25 * rr05 + 0.25 * rr07 + 0.15 * (100 - rr06), 0, 100)

    # Reader Index（9 维均值，对齐审查体系 §4.2）
    dims = [rr01, rr02, rr03, rr04, rr05, 100 - rr06, rr07, rr08, immersion]
    reader_index = round(sum(dims) / len(dims), 1)

    # Persona-Weighted RI（仅参考）
    persona = {}
    for role, w in persona_weights.items():
        sw = sum(w)
        persona[role] = round(sum(d * wi for d, wi in zip(dims, w)) / sw, 1)

    fatal_b = rr04_missing or rr03_flat or rr06_extreme or curve_flat
    return {
        "signals": {
            "rr01_first_impression": round(rr01, 1),
            "rr02_fluency": round(rr02, 1),
            "rr03_emotion": round(rr03, 1),
            "rr04_anticipation": round(rr04, 1),
            "rr05_reward": round(rr05, 1),
            "rr06_fatigue_raw": round(rr06, 1),
            "rr07_coolpoint": round(rr07, 1),
            "rr08_info": round(rr08, 1),
            "immersion": round(immersion, 1),
            "emotion_curve": curve,
            "persona": persona,
            "_flags": {"rr04_missing": rr04_missing, "rr03_flat": rr03_flat,
                       "rr06_extreme": rr06_extreme, "curve_flat": curve_flat},
        },
        "reader_index": reader_index,
        "pi": round(pi, 1),
        "fatal": fatal_b,
    }


def _decide(ri, pi, fatal_b, thr):
    if fatal_b:
        return "block", ["读者侧致命（RR04缺失/RR03平/RR06极高/情绪曲线平）"]
    if ri < thr["reader_index_floor"] or pi < thr["pi_floor"]:
        return "caution", ["Reader Index=%s 或 PI=%s 低于阈值(%s/%s)" % (
            ri, pi, thr["reader_index_floor"], thr["pi_floor"])]
    return "proceed", ["读者体验达标（RI=%s PI=%s）" % (ri, pi)]


def simulate(project_root, target_type, target_id, model="heuristic",
             write=True, proposed_by="unknown"):
    target_type = str(target_type)
    if target_type == "chapter":
        target_id = _qs._chapter_key(target_id)
        fp = _qs._find_chapter_file(project_root, target_id)
        if not fp:
            return {"error": "chapter_not_found", "target_id": target_id}
        body = _read_chapter_body(fp)
        artifact_path = _qs._rel(project_root, fp)
    else:
        return {"error": "unsupported_target", "target_type": target_type}

    cfg = _load_cfg()
    res = _compute(body, cfg)
    signals = res["signals"]
    reader_index = res["reader_index"]
    pi = res["pi"]
    fatal_b = res["fatal"]
    decision, reasons = _decide(reader_index, pi, fatal_b, cfg["thresholds"])
    report = {
        "meta": {"simulator": "heuristic", "simulated_at": _qs._now(),
                 "project": _qs._project_id(project_root), "model": model},
        "target": {"target_type": target_type, "target_id": str(target_id),
                   "artifact_path": artifact_path},
        "signals": signals,
        "reader_index": reader_index,
        "pi": pi,
        "fatal": fatal_b,
        "gate": {"decision": decision, "reasons": reasons},
    }
    if write:
        rid = _write_report(project_root, report, target_type, target_id, proposed_by, model)
        report["meta"]["report_id"] = rid
    return report


def simulate_task(project_root, task_id, **kw):
    import task_engine
    _, data = task_engine.load_task(project_root, task_id)
    if not data:
        raise FileNotFoundError(task_id)
    t = data["task"]
    target = None
    if t.get("chapter_ref"):
        target = ("chapter", str(t["chapter_ref"]))
    elif (t.get("target") or {}).get("type"):
        target = (t["target"]["type"], t["target"]["id"])
    elif t.get("type") == "nkb_update":
        target = ("nkb", t.get("nkb_ref") or (t.get("inputs") or {}).get("nkb_id") or task_id)
    elif t.get("type") == "asset_create":
        target = ("asset", t.get("asset_ref") or task_id)
    if not target:
        target = ("chapter", str(t.get("id", task_id)))
    return simulate(project_root, target[0], target[1], **kw)


def _write_report(project_root, report, target_type, target_id, proposed_by, model):
    d = os.path.join(project_root, "analysis", "reader")
    os.makedirs(d, exist_ok=True)
    seq = 1
    prefix = "READ-%s-%s" % (target_type, str(target_id).replace("/", "-"))
    while os.path.isfile(os.path.join(d, "%s-%02d.yaml" % (prefix, seq))):
        seq += 1
    rid = "%s-%02d" % (prefix, seq)
    report["meta"]["report_id"] = rid
    p = os.path.join(d, rid + ".yaml")
    with open(p, "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(report))
    audit_log.record(project_root, "reader_sim", agent=proposed_by, model=model,
                     files=[_qs._rel(project_root, p)], result="success",
                     detail="gate=%s target=%s/%s" % (report["gate"]["decision"], target_type, target_id))
    return rid


def _print_report(rep):
    if "error" in rep:
        print("错误：%s" % rep["error"])
        return
    g = rep.get("gate", {})
    print("门禁：%s" % g.get("decision"))
    print("Reader Index：%s   PI：%s   fatal=%s" % (rep.get("reader_index"), rep.get("pi"), rep.get("fatal")))
    for r in g.get("reasons", []):
        print("  理由：%s" % r)
    s = rep.get("signals", {})
    for k in ("rr01_first_impression", "rr02_fluency", "rr03_emotion", "rr04_anticipation",
              "rr05_reward", "rr06_fatigue_raw", "rr07_coolpoint", "rr08_info", "immersion"):
        print("  %s = %s" % (k, s.get(k)))
    print("  情绪曲线 = %s" % s.get("emotion_curve"))
    print("  Persona = %s" % s.get("persona"))


def main():
    ap = argparse.ArgumentParser(prog="reader", description="读者模拟")
    ap.add_argument("--project-root", required=True)
    ap.add_argument("verb", choices=["sim", "from-task", "show"])
    ap.add_argument("--target-type", default="chapter")
    ap.add_argument("--target-id", default=None)
    ap.add_argument("--task-id", default=None)
    ap.add_argument("--model", default="heuristic")
    args = ap.parse_args()

    root = args.project_root
    if args.verb == "sim":
        if not args.target_id:
            print("sim 需要 --target-id")
            sys.exit(2)
        rep = simulate(root, args.target_type, args.target_id, model=args.model)
        _print_report(rep)
    elif args.verb == "from-task":
        if not args.task_id:
            print("from-task 需要 --task-id")
            sys.exit(2)
        rep = simulate_task(root, args.task_id, model=args.model)
        _print_report(rep)
    elif args.verb == "show":
        d = os.path.join(root, "analysis", "reader")
        if not os.path.isdir(d):
            print("无读者模拟报告（analysis/reader/ 不存在）")
            sys.exit(0)
        reps = [f for f in os.listdir(d) if f.endswith(".yaml")]
        if not reps:
            print("无读者模拟报告")
            sys.exit(0)
        reps.sort(key=lambda f: os.path.getmtime(os.path.join(d, f)), reverse=True)
        rep = _qs._safe_load(os.path.join(d, reps[0])) or {}
        _print_report(rep)


if __name__ == "__main__":
    main()
