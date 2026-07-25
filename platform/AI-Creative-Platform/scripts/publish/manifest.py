# -*- coding: utf-8 -*-
"""canonical_manifest — 正式正文真相源索引（编辑≠发布：发布后确定性更新）。

项目根 canonical_manifest.yaml 记录每个已发布章节的真相元数据：
  - path         canonical 相对路径（如 第一卷_道生/第001章_道生.md）
  - status       章节生命周期态（approved/publishing/published/completed）
  - revision     修订号（每次发布 +1，初版 = 1）
  - hash         内容 SHA-256（revision_guard / 完整性校验，防篡改）
  - source       产出该版本的 Build 来源（draft 相对路径 / 任务 id）
  - published_at ISO 时间戳
  - versions[]   历史版本（revision, hash, source, published_at）

为什么用 _yaml_lite.dump 而不是 _gov.dump_block：
  dump_block 对「多键 list-of-dict」（如 versions 历史）生成的格式，
  _yaml_lite.load 无法重新解析（第二项起的键会破坏序列解析）。
  本模块改用 _yaml_lite.dump 发射，保证与 _yaml_lite.load（_gov.load_yaml）往返一致。
"""
import os
import sys
import hashlib
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
import _gov
import _yaml_lite as Y


MANIFEST_NAME = "canonical_manifest.yaml"


def manifest_path(project_root):
    return os.path.join(project_root, MANIFEST_NAME)


def _empty():
    return {
        "canonical_manifest": {
            "schema_version": "1.0.0",
            "generated_by": "publish_service",
            "entries": {},
        }
    }


def load(project_root):
    p = manifest_path(project_root)
    if not os.path.isfile(p):
        return _empty()
    try:
        d = _gov.load_yaml(p)
    except Exception:
        return _empty()
    if not isinstance(d, dict) or "canonical_manifest" not in d:
        return _empty()
    cm = d["canonical_manifest"]
    if not isinstance(cm, dict):
        return _empty()
    cm.setdefault("entries", {})
    return d


def save(project_root, data):
    p = manifest_path(project_root)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(Y.dump(data))
    return p


def hash_content(content):
    """内容 SHA-256（revision_guard / 完整性校验）。"""
    if not isinstance(content, str):
        content = "" if content is None else str(content)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def get_entry(project_root, path):
    path = path.replace("\\", "/")
    d = load(project_root)
    return d["canonical_manifest"]["entries"].get(path)


def list_entries(project_root):
    d = load(project_root)
    return dict(d["canonical_manifest"]["entries"])


def record_publish(project_root, path, source, content, prev_status=None):
    """原子发布后落盘 Manifest：revision +1、hash、source、versions 追加。

    返回更新后的 entry dict。revision_guard 由 Publish Service 在调用前比对旧 hash。
    """
    path = path.replace("\\", "/")
    content = content if isinstance(content, str) else ""
    h = hash_content(content)
    d = load(project_root)
    cm = d["canonical_manifest"]
    entries = cm.setdefault("entries", {})
    prev = entries.get(path)
    if prev:
        revision = int(prev.get("revision", 0)) + 1
    else:
        revision = 1
    now = datetime.datetime.now().isoformat(timespec="seconds")
    versions = list(prev.get("versions", [])) if prev else []
    versions.append({
        "revision": revision,
        "hash": h,
        "source": source,
        "published_at": now,
    })
    entry = {
        "path": path,
        "status": "published",
        "revision": revision,
        "hash": h,
        "source": source,
        "published_at": now,
        "versions": versions,
    }
    entries[path] = entry
    save(project_root, d)
    return entry


def set_status(project_root, path, status):
    path = path.replace("\\", "/")
    d = load(project_root)
    e = d["canonical_manifest"]["entries"].get(path)
    if not e:
        return None
    e["status"] = status
    save(project_root, d)
    return e


def snapshot_versions(project_root, path):
    """返回该 path 历史版本列表（供回滚选择）。"""
    e = get_entry(project_root, path)
    return (e or {}).get("versions", []) if e else []


def rollback(project_root, path, to_revision, new_content, new_status="published"):
    """回滚到历史 revision：写新 revision（不删历史），记录 rollback 来源。

    回滚也是一次「新发布」（revision 递增），而非覆盖历史，保证可追溯。
    """
    path = path.replace("\\", "/")
    new_content = new_content if isinstance(new_content, str) else ""
    h = hash_content(new_content)
    d = load(project_root)
    cm = d["canonical_manifest"]
    entries = cm.setdefault("entries", {})
    prev = entries.get(path)
    if not prev:
        raise KeyError("无 manifest 条目可回滚: %s" % path)
    revision = int(prev.get("revision", 0)) + 1
    now = datetime.datetime.now().isoformat(timespec="seconds")
    versions = list(prev.get("versions", []))
    versions.append({
        "revision": revision,
        "hash": h,
        "source": "rollback->r%d" % to_revision,
        "published_at": now,
    })
    entry = dict(prev)
    entry["revision"] = revision
    entry["hash"] = h
    entry["status"] = new_status
    entry["published_at"] = now
    entry["versions"] = versions
    entries[path] = entry
    save(project_root, d)
    return entry


if __name__ == "__main__":
    import sys as _sys
    if len(_sys.argv) > 1 and _sys.argv[1] == "show":
        root = _sys.argv[2] if len(_sys.argv) > 2 else "."
        for k, v in list_entries(root).items():
            print("%s  r%d  %s  %s" % (k, v.get("revision"), v.get("status"), v.get("hash", "")[:10]))
