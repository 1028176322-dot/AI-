# -*- coding: utf-8 -*-
"""
L4 作者风格学习（纲要 §7 / §8 第 10 步）。

设计要点
--------
- **span 级反馈收集**：每笔反馈记录接受/拒绝的 span（原文与修改后差异）、原因、适用场景。
- **多次独立证据门槛**：同类偏好出现 ≥3 次才生成 L4 候选规则。
- **审核晋升（不自动写入）**：候选规则须经审批流程（§2.10 同构），可 SUSPENDED / REVOKED。
- **存储**：反馈存 `runtime/learning/author-feedback/`；L4 候选存 `memory/project/style-library/`。
"""
import hashlib
import json
import os
import time
import uuid
from collections import defaultdict

SCHEMA_ID = "style.author-feedback"
SCHEMA_VERSION = "1.0.0"


class AuthorLearningError(Exception):
    pass


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _pref_key(feedback):
    """同类偏好的分组键：行为类型 + 简要描述。"""
    kind = feedback.get("kind", "unknown")
    desc = feedback.get("description", "")
    return "%s::%s" % (kind, desc)


# --------------------------------------------------------------------------
# 反馈记录
# --------------------------------------------------------------------------
def record_feedback(chapter_id, span_start, span_end,
                    original_text, revised_text, reason,
                    kind="stylistic", scene_type="",
                    accepted=True, reviewer_id="", task_id="",
                    feedback_store=None):
    """记录一次用户/作者对风格修订的反馈。

    参数
    ----
    accepted : bool  True=接受修订，False=拒绝修订
    kind : str  stylistic | pacing | vocabulary | sentence_structure | dialogue | other
    """
    entry = {
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "chapter_id": chapter_id,
        "span_start": span_start,
        "span_end": span_end,
        "original_sha256": _sha256(original_text),
        "revised_sha256": _sha256(revised_text),
        "original_text": original_text,  # span 级原文（短片段，非全章原文）
        "revised_text": revised_text,
        "reason": reason,
        "kind": kind,
        "scene_type": scene_type,
        "accepted": accepted,
        "reviewer_id": reviewer_id,
        "task_id": task_id,
        "created_at": time.time(),
    }
    if feedback_store is None:
        raise AuthorLearningError("feedback_store path required")
    os.makedirs(feedback_store, exist_ok=True)
    path = os.path.join(feedback_store, "%s-%s.json" % (task_id or "fb", uuid.uuid4().hex[:12]))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)
    return entry


# --------------------------------------------------------------------------
# 证据加载与聚类
# --------------------------------------------------------------------------
def _load_all(feedback_store):
    if not os.path.isdir(feedback_store):
        return []
    out = []
    for fn in sorted(os.listdir(feedback_store)):
        if fn.endswith(".json"):
            with open(os.path.join(feedback_store, fn), "r", encoding="utf-8") as f:
                try:
                    out.append(json.load(f))
                except json.JSONDecodeError:
                    pass
    return out


def cluster_feedback(feedback_store):
    """按 _pref_key 聚类反馈，统计每类出现次数。"""
    groups = defaultdict(list)
    for fb in _load_all(feedback_store):
        key = _pref_key(fb)
        groups[key].append(fb)
    return {k: {"count": len(v), "entries": v} for k, v in groups.items()}


# --------------------------------------------------------------------------
# L4 候选生成（≥3 次同类证据）
# --------------------------------------------------------------------------
def generate_l4_candidates(feedback_store, min_evidence=3):
    """扫描反馈聚类，满足证据门槛的生成 L4 候选规则。

    返回 [{rule_id, kind, description, confidence, evidence_count, scene_type, ...}]
    """
    clusters = cluster_feedback(feedback_store)
    candidates = []
    for key, info in clusters.items():
        if info["count"] < min_evidence:
            continue
        entries = info["entries"]
        accepted = sum(1 for e in entries if e.get("accepted"))
        rejected = sum(1 for e in entries if not e.get("accepted"))
        # 仅接受数 > 拒绝数时生成候选
        if accepted <= rejected:
            continue

        # 取第一个条目的信息作为候选描述
        first = entries[0]
        candidate = {
            "rule_id": "L4-%s" % _sha256(key)[:12],
            "kind": first.get("kind", "stylistic"),
            "description": first.get("description", key.split("::", 1)[1] if "::" in key else key),
            "confidence": min(1.0, info["count"] / 10.0),  # 10 同类→1.0
            "evidence_count": info["count"],
            "accepted_count": accepted,
            "rejected_count": rejected,
            "scene_type": first.get("scene_type", ""),
            "origin": "author_feedback",
            "status": "candidate",
            "created_at": time.time(),
        }
        candidates.append(candidate)
    return candidates


# --------------------------------------------------------------------------
# L4 候选持久化（写入 memory/project/style-library/author.card.yaml）
# --------------------------------------------------------------------------
def persist_l4_candidate(candidate, style_library_dir):
    path = os.path.join(style_library_dir, "author.card.yaml")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    existing = []
    if os.path.exists(path):
        try:
            import sys as _sys
            _sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "_common"))
            from _yaml_lite import load as _yload
            with open(path, "r", encoding="utf-8") as f:
                raw = _yload(f.read())
                if isinstance(raw, list):
                    existing = raw
        except Exception:
            pass
    existing.append(candidate)
    try:
        from _yaml_lite import dump as _ydump
        content = _ydump(existing)
    except Exception:
        content = json.dumps(existing, ensure_ascii=False, indent=2)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return path


def read_l4_candidates(style_library_dir):
    path = os.path.join(style_library_dir, "author.card.yaml")
    if not os.path.exists(path):
        return []
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "_common"))
        from _yaml_lite import load as _yload
        with open(path, "r", encoding="utf-8") as f:
            raw = _yload(f.read())
            return raw if isinstance(raw, list) else []
    except Exception:
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
                return raw if isinstance(raw, list) else []
        except Exception:
            return []
