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
    desc = feedback.get("description") or feedback.get("reason", "")
    return "%s::%s" % (kind, desc)


# --------------------------------------------------------------------------
# 反馈记录
# --------------------------------------------------------------------------
def record_feedback(chapter_id, span_start, span_end,
                    original_text, revised_text, reason,
                    kind="stylistic", scene_type="",
                    accepted=True, reviewer_id="", task_id="",
                    feedback_store=None, description=""):
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
        "description": description or reason,
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
            "status": "EXTRACTED",
            "lifecycle_state": "EXTRACTED",
            "rule_class": "style_preference",
            "scope": {
                "content_type": (
                    "dialogue"
                    if first.get("kind") == "dialogue" else "both"),
                "scene_types": sorted({
                    item.get("scene_type") for item in entries
                    if item.get("scene_type")}),
                "character_ids": [],
            },
            "evidence_refs": [{
                "task_id": item.get("task_id"),
                "chapter_id": item.get("chapter_id"),
                "original_sha256": item.get("original_sha256"),
                "revised_sha256": item.get("revised_sha256"),
                "accepted": item.get("accepted"),
            } for item in entries],
            "requires_human_review": True,
            "created_at": time.time(),
        }
        candidates.append(candidate)
    return candidates


# --------------------------------------------------------------------------
# L4 候选持久化（写入 memory/project/style-library/author.card.yaml）
# --------------------------------------------------------------------------
def persist_l4_candidate(candidate, style_library_dir):
    path = os.path.join(style_library_dir, "author.candidates.yaml")
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
                elif isinstance(raw, dict):
                    existing = raw.get("candidates") or []
        except Exception:
            pass
    existing.append(candidate)
    try:
        from _yaml_lite import dump as _ydump
        content = _ydump({
            "schema": "style.author-candidates@2.0.0",
            "candidates": existing,
        })
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
    path = os.path.join(style_library_dir, "author.candidates.yaml")
    if not os.path.exists(path):
        return []
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "_common"))
        from _yaml_lite import load as _yload
        with open(path, "r", encoding="utf-8") as f:
            raw = _yload(f.read())
            if isinstance(raw, list):
                return raw
            return (raw or {}).get("candidates") or []
    except Exception:
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
                return raw if isinstance(raw, list) else []
        except Exception:
            return []


def _load_yaml(path):
    from _yaml_lite import load as yaml_load
    with open(path, "r", encoding="utf-8") as handle:
        return yaml_load(handle.read())


def _dump_yaml(path, value):
    from _yaml_lite import dump as yaml_dump
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        handle.write(yaml_dump(value))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


def promote_l4_candidate(
        candidate_ref, style_library_dir, approved_by,
        approval_evidence):
    """Promote one reviewed author preference into a compliant L4 card.

    Promotion is impossible without an attributable human decision. The
    candidate remains separate from the active card until this function
    succeeds.
    """
    if not approved_by or not approval_evidence:
        raise AuthorLearningError(
            "approved_by and approval_evidence are required")
    candidates_path = os.path.join(
        style_library_dir, "author.candidates.yaml")
    candidates = read_l4_candidates(style_library_dir)
    if os.path.isfile(str(candidate_ref)):
        loaded = _load_yaml(candidate_ref)
        candidate = (
            loaded if isinstance(loaded, dict)
            and loaded.get("rule_id") else None)
    else:
        candidate = next(
            (row for row in candidates
             if row.get("rule_id") == candidate_ref), None)
    if not candidate:
        raise AuthorLearningError("author candidate not found")
    if candidate.get("lifecycle_state") in ("REVOKED", "REJECTED"):
        raise AuthorLearningError(
            "terminal candidate cannot be promoted")

    card_path = os.path.join(style_library_dir, "author.card.yaml")
    if os.path.isfile(card_path):
        card = _load_yaml(card_path) or {}
    else:
        card = {
            "card_id": "L4-AUTHOR",
            "layer": "L4",
            "scope": {
                "content_type": "both",
                "scene_types": [],
                "character_ids": [],
            },
            "project_constraints": [],
            "style_preferences": [],
            "style_targets": [],
            "governance_policy_ref":
                "core/learning/自主学习与反馈闭环.md",
            "governance_policy_sha256": "runtime-bound",
            "conflict_policy": {
                "higher_layer_wins": True,
                "record_suppressed_rules": True,
            },
            "effective_priority": "L4",
            "author_id": approved_by,
        }
    if card.get("layer") != "L4":
        raise AuthorLearningError("existing author card is not L4")
    preferences = card.setdefault("style_preferences", [])
    if not any(
            row.get("rule_id") == candidate["rule_id"]
            for row in preferences):
        preferences.append({
            "rule_id": candidate["rule_id"],
            "rule_class": "style_preference",
            "status": "ACTIVE",
            "lifecycle_state": "ACTIVE",
            "scope": candidate.get("scope") or {},
            "value": {
                "dimension": {
                    "dialogue": "dialogue_method",
                    "pacing": "syntactic_rhythm",
                    "sentence_structure": "syntactic_rhythm",
                    "vocabulary": "description_selection",
                }.get(candidate.get("kind"), "prohibited_patterns"),
                "instruction": candidate.get("description"),
            },
            "source": {
                "origin": "author_feedback",
                "candidate_id": candidate["rule_id"],
                "evidence_count": candidate.get("evidence_count"),
                "approved_by": approved_by,
                "approval_evidence": approval_evidence,
            },
        })
    card["updated_at"] = time.time()
    os.makedirs(style_library_dir, exist_ok=True)
    _dump_yaml(card_path, card)

    for row in candidates:
        if row.get("rule_id") == candidate["rule_id"]:
            row["status"] = "PROMOTED"
            row["lifecycle_state"] = "PROMOTED"
            row["approved_by"] = approved_by
            row["approval_evidence"] = approval_evidence
            row["promoted_at"] = time.time()
    if candidates:
        _dump_yaml(candidates_path, {
            "schema": "style.author-candidates@2.0.0",
            "candidates": candidates,
        })
    return {
        "candidate_id": candidate["rule_id"],
        "card": card_path,
        "lifecycle_state": "ACTIVE",
        "approved_by": approved_by,
        "approval_evidence": approval_evidence,
    }
