# -*- coding: utf-8 -*-
"""delta_review.py — 增量审查（Delta Review · Phase B3）

对应审查体系.md §7.9：局部修改快审——对两个章节版本做文本 diff，
并投影「改了哪些实体 / 应触发哪些检查项」，让 AI 只跑受影响子集，
不必全量重审。命中结果仅作证据，最终判断交 AI。

  platform delta review --from F --to T --project-root R
"""
import os
import sys
import json
import argparse
import difflib

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# 关键词 → 检查项 映射（对应审查体系 §7.9 范围映射的简化版）
_KW_MAP = {
    "dialogue": (["对白", "对话", "台词", "说道"], "checks/dialogue.md"),
    "character": (["人物", "性格", "动机", "人设", "语气"], "checks/character.md"),
    "world": (["世界", "设定", "法则", "灵气", "修为", "境界"], "checks/world.md"),
    "conflict": (["冲突", "矛盾", "对立", "撕破"], "checks/conflict.md"),
    "emotion": (["情绪", "情感", "感动", "心疼"], "checks/emotion.md"),
    "narrative": (["叙事", "视角", "POV", "节奏", "场景切换"], "checks/narrative.md"),
    "reader": (["读者", "钩子", "期待", "爽点", "付费"], "checks/reader/"),
    "battle": (["战斗", "功法", "招式", "法术", "交手"], "checks/battle.md"),
    "consistency": (["时间线", "年份", "年龄", "前后", "死"], "checks/consistency.md"),
}


def _load_nkb_entities(proot):
    nkb_dir = os.path.normpath(os.path.join(proot, "NKB"))
    if not os.path.isdir(nkb_dir):
        return []
    ents = []
    for fn in sorted(os.listdir(nkb_dir)):
        if not fn.endswith(".yaml") or fn in ("CHANGELOG.md", "NKB.md"):
            continue
        try:
            import _gov
            d = _gov.load_yaml(os.path.join(nkb_dir, fn))
        except Exception:
            continue
        comp = fn[:-5]
        for r in (d.get("records") or []):
            if isinstance(r, dict) and r.get("id"):
                ents.append({"id": str(r.get("id")),
                             "name": r.get("name"),
                             "component": comp})
    return ents


def _read_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().splitlines()


def diff_chapters(project_root, from_path, to_path):
    if not os.path.isfile(from_path):
        raise RuntimeError("from 文件不存在: %s" % from_path)
    if not os.path.isfile(to_path):
        raise RuntimeError("to 文件不存在: %s" % to_path)

    a = _read_lines(from_path)
    b = _read_lines(to_path)
    sm = difflib.SequenceMatcher(None, a, b)
    changed_ranges = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        changed_ranges.append({
            "type": tag,  # replace / delete / insert
            "from_start": i1 + 1, "from_end": i2,
            "to_start": j1 + 1, "to_end": j2,
            "from_text": a[i1:i2],
            "to_text": b[j1:j2],
        })
    similarity = round(sm.ratio(), 4)

    merged = "\n".join(a) + "\n" + "\n".join(b)
    # 受影响实体（id 精确 + name 长度>=3 子串）
    ents = _load_nkb_entities(project_root)
    affected_entities = []
    for e in ents:
        hit = e["id"] in merged
        if not hit and e["name"] and len(str(e["name"])) >= 3:
            hit = str(e["name"]) in merged
        if hit:
            affected_entities.append({"id": e["id"], "name": e["name"],
                                      "component": e["component"]})

    # 受影响检查项（关键词命中）
    affected_checks = []
    for check, (kws, fpath) in _KW_MAP.items():
        if any(kw in merged for kw in kws):
            affected_checks.append({"check": check, "file": fpath,
                                    "reason": "命中关键词"})

    return {
        "from": from_path,
        "to": to_path,
        "similarity": similarity,
        "changed_range_count": len(changed_ranges),
        "changed_ranges": changed_ranges,
        "affected_entities": affected_entities,
        "affected_checks": affected_checks,
        "generated": _now_iso(),
    }


def _now_iso():
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")


def _safe_name(p):
    base = os.path.basename(p)
    return os.path.splitext(base)[0]


def main():
    ap = argparse.ArgumentParser(prog="delta", description="增量审查 Delta Review")
    ap.add_argument("action", nargs="?", default="review", choices=["review"])
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--from", dest="from_path", required=True)
    ap.add_argument("--to", dest="to_path", required=True)
    args = ap.parse_args()

    res = diff_chapters(args.project_root, args.from_path, args.to_path)
    out_dir = os.path.join(args.project_root, "runtime", "reviews", "delta")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "%s-vs-%s.yaml" % (_safe_name(args.from_path),
                                                        _safe_name(args.to_path)))
    import _gov
    _gov.dump_yaml(out_path, res)
    print(json.dumps({
        "similarity": res["similarity"],
        "changed_range_count": res["changed_range_count"],
        "affected_entities": [e["id"] for e in res["affected_entities"]],
        "affected_checks": [c["check"] for c in res["affected_checks"]],
        "report": out_path,
    }, ensure_ascii=False, indent=2))
    return res


if __name__ == "__main__":
    main()
