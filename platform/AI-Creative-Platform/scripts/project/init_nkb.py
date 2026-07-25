#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""init_nkb.py — 从 NKB Schema 初始化空结构（Section VI.4）

- 按 schemas/nkb/nkb-manifest.yaml 的 components 生成空 NKB（records: []）。
- NKB/manifest.yaml 记录组件清单（索引）。
- seed 策略：题材术语种子以 candidate 身份导入 Terminology（status: candidate，
  source: seed），不直接成为正史；力量体系种子落入 planning/decisions/ 作为候选参考。
- 严禁从其他小说复制人物/地点/剧情。

用法：python init_nkb.py --staging <dir> --id X --genre xuanhuan
API：  init(spec, staging, platform_root) -> (ok, err)
"""
import os
import sys
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _installer_common as C


def init(spec, staging, platform_root):
    proj = spec.get("project") or {}
    tpl = spec.get("template") or {}
    title = proj.get("title") or spec.get("title") or "未命名"
    genre = tpl.get("id") or tpl.get("genre") or spec.get("genre") or "xuanhuan"
    pid = proj.get("id") or C.derive_pid(title)

    core_m, tpl_m, nkb_m, merr = C.load_manifests(platform_root, genre)
    if merr:
        return False, merr

    nkb_dir = os.path.join(staging, "NKB")
    C.ensure_dir(nkb_dir)
    schema_ver = str(nkb_m.get("schema_version", "0"))

    components = nkb_m.get("components") or []
    comp_names = []
    for comp in components:
        name = comp.get("name")
        comp_names.append(name)
        text = (
            "# NKB 组件：%s（schema %s）\n"
            "schema_version: %s\n"
            "project_id: %s\n"
            "records: []\n"
            "# 本作品私有事实；世界观/人物/故事须经规划确认（TASK-004~008）方可填充。\n"
        ) % (name, schema_ver, schema_ver, pid)
        C.write_text(os.path.join(nkb_dir, "%s.yaml" % name), text)

    # NKB/manifest.yaml 索引
    idx = {
        "schema_version": schema_ver,
        "project_id": pid,
        "generated_by": "project_installer",
        "components": comp_names,
        "note": "组件清单索引；具体事实各组件独立 yaml。",
    }
    C.dump_yaml(os.path.join(nkb_dir, "manifest.yaml"), idx)

    # ── seed：术语候选导入 Terminology（status: candidate）──
    seeds = (tpl_m.get("seeds") or {})
    term_seed = seeds.get("terminology")
    if term_seed:
        tpath = os.path.join(platform_root, "templates", genre, term_seed)
        if os.path.isfile(tpath):
            tdata = C.load_yaml(tpath) or {}
            cands = tdata.get("candidates") or []
            term_records = []
            for c in cands:
                term_records.append({
                    "term": c.get("term"),
                    "gloss": c.get("gloss"),
                    "status": "candidate",
                    "source": "seed:%s" % genre,
                })
            term_text = (
                "# NKB 组件：Terminology（seed 候选导入）\n"
                "schema_version: %s\n"
                "project_id: %s\n"
                "records:\n" % (schema_ver, pid)
            )
            for r in term_records:
                term_text += "  - term: %s\n    gloss: %s\n    status: candidate\n    source: seed:%s\n" % (
                    r["term"], r["gloss"], genre)
            term_text += "# 以上为题材候选种子，须经 TASK-008 NKB 审查确认后晋升正史。\n"
            C.write_text(os.path.join(nkb_dir, "Terminology.yaml"), term_text)

    # ── seed：力量体系落入 planning/decisions/ 作为候选参考 ──
    ps_seed = seeds.get("power_system_schema")
    if ps_seed:
        ppath = os.path.join(platform_root, "templates", genre, ps_seed)
        if os.path.isfile(ppath):
            import shutil as _sh
            dest = os.path.join(staging, "planning", "decisions", "power-system-seed.yaml")
            C.ensure_dir(os.path.dirname(dest))
            _sh.copyfile(ppath, dest)
            # 顶部加注 candidate 标记
            with open(dest, "r", encoding="utf-8") as f:
                body = f.read()
            with open(dest, "w", encoding="utf-8") as f:
                f.write("# SEED 候选（非正史）：力量体系骨架，TASK-005 设计后替换为自有体系。\n" + body)

    return True, None


def main():
    ap = argparse.ArgumentParser(description="初始化空 NKB（从 schema）")
    ap.add_argument("--staging", required=True)
    ap.add_argument("--spec")
    ap.add_argument("--id")
    ap.add_argument("--title")
    ap.add_argument("--genre", default="xuanhuan")
    args = ap.parse_args()
    spec = {"project": {}, "template": {}}
    if args.spec:
        spec = C.load_yaml(args.spec)
    spec.setdefault("project", {})["id"] = args.id or (spec.get("project") or {}).get("id")
    spec.setdefault("project", {})["title"] = args.title or (spec.get("project") or {}).get("title")
    spec.setdefault("template", {})["genre"] = args.genre
    platform_root = C.find_platform_root()
    ok, err = init(spec, args.staging, platform_root)
    if not ok:
        C.die(err or "init_nkb 失败", 2)
    print("✓ 空 NKB 已生成（含 seed 候选）")
    sys.exit(0)


if __name__ == "__main__":
    main()
