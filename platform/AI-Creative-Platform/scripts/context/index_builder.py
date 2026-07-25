# -*- coding: utf-8 -*-
"""index_builder.py — 文件/实体/章节/事件/术语/依赖 索引构建器（Phase A0）

把"AI 反复搜索文件、判断最新版、阅读重复内容"脚本化：
  platform index build  [--project-root X]
  platform index find   [--project-root X] <chapter_id|entity_id|name>

产物落 <project>/runtime/indexes/：
  files.json       项目关键文件（含章节）路径/类型/状态/版本/hash
  entities.json    NKB 各组件记录（id/name/type）
  chapters.json    章节编号/路径/状态/版本
  terminology.json 术语（含 deprecated 别名）
  events.json      事件（章节/参与者）
  dependencies.json 实体关系边

设计约束：所有 YAML 用单行纯标量（_yaml_lite 不支持折叠标量/多行流列表）。
"""
import os
import sys
import re
import json
import hashlib
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
    def load_yaml(path):
        with open(path, "r", encoding="utf-8") as f:
            return _pyyaml.safe_load(f)
    _BACKEND = "pyyaml"
except Exception:
    import _yaml_lite
    def load_yaml(path):
        return _yaml_lite.load_file(path)
    _BACKEND = "yaml_lite"

_CHAPTER_RE = re.compile(r"第\s*(\d+)\s*章")
_EXCLUDE_DIRS = {".git", "runtime", "tasks", "analysis", "audit", "NKB", "memory",
                 "sources", "overrides", "artifacts", "operations", "handoffs",
                 "sessions", ".cache", "templates", "node_modules", "__pycache__"}
_EXCLUDE_KW = ("审读", "评分卡", "大纲", "批注", "修复", "目录", "总纲", "摘要", "索引")


def _read_project(project_root):
    p = os.path.join(project_root, "project.yaml")
    if not os.path.isfile(p):
        return {}
    return load_yaml(p) or {}


def _nkb_dir(project_root):
    data = _read_project(project_root)
    rel = (data.get("paths") or {}).get("nkb", "./NKB")
    return os.path.normpath(os.path.join(project_root, rel))


def _load_nkb_components(nkb_dir):
    """返回 {component_name: [records...]}。排除 CHANGELOG.md / NKB.md。"""
    comps = {}
    if not os.path.isdir(nkb_dir):
        return comps
    for fn in sorted(os.listdir(nkb_dir)):
        if not fn.endswith(".yaml"):
            continue
        if fn in ("CHANGELOG.md", "NKB.md"):
            continue
        path = os.path.join(nkb_dir, fn)
        try:
            data = load_yaml(path)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        name = fn[:-5]
        recs = data.get("records") or []
        if isinstance(recs, list):
            comps[name] = recs
    return comps


def _hash_file(path):
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()[:12]
    except Exception:
        return ""


def scan_chapters(project_root):
    """递归扫描章节文件，返回 [{id, number, path, status, version}]。"""
    out = []
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDE_DIRS]
        for fn in filenames:
            if not (fn.endswith(".md") or fn.endswith(".txt")):
                continue
            if any(k in fn for k in _EXCLUDE_KW):
                continue
            m = _CHAPTER_RE.search(fn)
            if not m:
                continue
            num = int(m.group(1))
            full = os.path.normpath(os.path.join(dirpath, fn))
            rev = _parse_version_suffix(fn)
            # 状态：在 approved 目录视为 approved，否则 exported(draft)
            status = "approved" if os.sep + "approved" + os.sep in full.replace("/", os.sep) else "exported"
            out.append({
                "id": "CH-%03d" % num,
                "number": num,
                "path": full,
                "rel": os.path.relpath(full, project_root),
                "status": status,
                "version": rev,
            })
    out.sort(key=lambda x: x["number"])
    return out


def _parse_version_suffix(name):
    """从文件名解析版本号：无后缀=0；_v2=2；_final/_new=视为草稿(0，但标记)。"""
    m = re.search(r"_v(\d+)", name)
    if m:
        return int(m.group(1))
    if re.search(r"_final|_new|_草稿|_改", name):
        return 0
    return 0


def detect_latest_version(project_root, chapter_number):
    """给定章节号，返回 canonical 版本：优先无后缀文件，否则最高版本号。"""
    chs = scan_chapters(project_root)
    cands = [c for c in chs if c["number"] == int(chapter_number)]
    if not cands:
        return {"chapter_id": "CH-%03d" % int(chapter_number), "revision": None, "path": None}
    # 无后缀优先
    base = [c for c in cands if c["version"] == 0 and not re.search(r"_v\d|_final|_new", c["path"])]
    if base:
        pick = base[0]
        return {"chapter_id": pick["id"], "revision": 0, "path": pick["path"]}
    pick = max(cands, key=lambda c: c["version"])
    return {"chapter_id": pick["id"], "revision": pick["version"], "path": pick["path"]}


def build_index(project_root, out_dir=None):
    if out_dir is None:
        out_dir = os.path.join(project_root, "runtime", "indexes")
    os.makedirs(out_dir, exist_ok=True)
    nkb_dir = _nkb_dir(project_root)
    comps = _load_nkb_components(nkb_dir)

    entities = {}
    dependencies = []
    terminology = []
    events = []
    for name, recs in comps.items():
        if name == "Terminology":
            for r in recs:
                terminology.append({
                    "id": r.get("id"),
                    "name": r.get("name"),
                    "deprecated": r.get("deprecated") or r.get("aliases") or [],
                })
            continue
        if name == "Events":
            for r in recs:
                ch = str(r.get("chapter", ""))
                cm = _CHAPTER_RE.search(ch)
                events.append({
                    "id": r.get("id"),
                    "name": r.get("name"),
                    "chapter": ch,
                    "chapter_num": int(cm.group(1)) if cm else None,
                    "participants": r.get("participants") or [],
                })
            continue
        # 通用实体（Characters / Assets / Canon / WorldState / ReaderState / StoryState / Graph / Timeline / Derived）
        lst = []
        for r in recs:
            lst.append({"id": r.get("id"), "name": r.get("name"), "type": name})
            if name == "Characters":
                for rel in (r.get("relationships") or []):
                    if isinstance(rel, dict) and rel.get("target"):
                        dependencies.append({
                            "source": r.get("id"),
                            "target": rel.get("target"),
                            "kind": rel.get("kind"),
                        })
        entities[name] = lst

    chapters = scan_chapters(project_root)

    files = []
    for c in chapters:
        files.append({
            "path": c["rel"],
            "type": "manuscript",
            "status": c["status"],
            "version": c["version"],
            "hash": _hash_file(c["path"]),
            "related_entities": [],
        })

    index = {
        "generated": _now_iso(),
        "backend": _BACKEND,
        "entities": entities,
        "dependencies": dependencies,
        "terminology": terminology,
        "events": events,
        "chapters": chapters,
        "files": files,
        "counts": {
            "entities": sum(len(v) for v in entities.values()),
            "chapters": len(chapters),
            "events": len(events),
            "terminology": len(terminology),
            "dependencies": len(dependencies),
        },
    }
    for k, v in index.items():
        if k in ("generated", "backend"):
            continue
        with open(os.path.join(out_dir, "%s.json" % k), "w", encoding="utf-8") as f:
            json.dump(v, f, ensure_ascii=False, indent=2)
    # 总体 manifest
    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump({
            "generated": index["generated"],
            "backend": _BACKEND,
            "components": sorted(comps.keys()),
            "counts": {
                "entities": sum(len(v) for v in entities.values()),
                "chapters": len(chapters),
                "events": len(events),
                "terminology": len(terminology),
                "dependencies": len(dependencies),
            },
        }, f, ensure_ascii=False, indent=2)
    return index


def _now_iso():
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")


def query_index(out_dir, key):
    """简单索引查询：chapter_id / entity_id / name 片段。"""
    out_dir = out_dir or os.path.join(os.getcwd(), "runtime", "indexes")
    results = []
    # entity by id or name
    ep = os.path.join(out_dir, "entities.json")
    if os.path.isfile(ep):
        ents = json.load(open(ep, encoding="utf-8"))
        for comp, lst in ents.items():
            for e in lst:
                if e.get("id") == key or (e.get("name") and key in str(e.get("name"))):
                    results.append({"kind": "entity", "component": comp, "hit": e})
    # chapter by id or number
    cp = os.path.join(out_dir, "chapters.json")
    if os.path.isfile(cp):
        chs = json.load(open(cp, encoding="utf-8"))
        for c in chs:
            if c.get("id") == key or str(c.get("number")) == key.lstrip("CH-0").lstrip("CH-"):
                results.append({"kind": "chapter", "hit": c})
    return results


def main():
    ap = argparse.ArgumentParser(prog="index", description="索引构建与查询")
    ap.add_argument("--project-root", default=None)
    sub = ap.add_subparsers(dest="action")
    b = sub.add_parser("build", help="构建索引")
    b.add_argument("--project-root", required=True)
    b.add_argument("--out", default=None)
    f = sub.add_parser("find", help="查询索引")
    f.add_argument("--project-root", required=True)
    f.add_argument("--out", default=None)
    f.add_argument("key", help="chapter_id / entity_id / name 片段")
    args = ap.parse_args()
    if args.action == "build":
        idx = build_index(args.project_root, args.out)
        print("✓ 索引已构建：%s" % os.path.join(args.out or os.path.join(args.project_root, "runtime", "indexes")))
        print("  实体 %d / 章节 %d / 事件 %d / 术语 %d / 依赖 %d" % (
            idx["counts"]["entities"], idx["counts"]["chapters"],
            idx["counts"]["events"], idx["counts"]["terminology"],
            idx["counts"]["dependencies"]))
    elif args.action == "find":
        out_dir = args.out or os.path.join(args.project_root, "runtime", "indexes")
        res = query_index(out_dir, args.key)
        if not res:
            print("# 无匹配：%s" % args.key)
            return
        for r in res:
            print("[%s] %s" % (r["kind"], json.dumps(r["hit"], ensure_ascii=False)))
    else:
        ap.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
