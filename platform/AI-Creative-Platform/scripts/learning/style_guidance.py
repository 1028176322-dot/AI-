# -*- coding: utf-8 -*-
"""Build deterministic runtime style guidance from governed L0-L4 cards.

The composer never promotes candidates.  It includes only approved/active
rules, keeps L3 dialogue-only, records every conflict and produces a stable
hash consumed by writing, diagnosis, revision, review and publish gates.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
for _name in os.listdir(SCRIPTS):
    _path = os.path.join(SCRIPTS, _name)
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import _gov


SCHEMA_VERSION = "1.0.0"
ACTIVE_STATUSES = {"ACTIVE", "APPROVED", "active", "approved"}
INACTIVE_STATUSES = {
    "SUSPENDED", "REVOKED", "SUPPRESSED", "REJECTED",
    "suspended", "revoked", "suppressed", "rejected",
}


def _sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")


def _load(path):
    if not path or not os.path.isfile(path):
        return {}
    return _gov.load_yaml(path) or {}


def _portable_path(root, absolute):
    try:
        return os.path.relpath(absolute, root).replace("\\", "/")
    except ValueError:
        platform_root = _gov.find_platform_root()
        real = os.path.realpath(absolute)
        platform = os.path.realpath(platform_root)
        if real == platform or real.startswith(platform + os.sep):
            relative = os.path.relpath(real, platform).replace("\\", "/")
            return "platform://%s" % relative
        return "external://%s" % os.path.basename(real)


def _binding(root, path):
    if not path:
        return None
    absolute = path if os.path.isabs(path) else os.path.join(root, path)
    if not os.path.isfile(absolute):
        return {
            "path": _portable_path(root, absolute),
            "status": "missing",
        }
    return {
        "path": _portable_path(root, absolute),
        "sha256": _sha256_file(absolute),
        "status": "loaded",
    }


def _tree_binding(root, directory):
    if not os.path.isdir(directory):
        return {"path": os.path.relpath(directory, root), "status": "missing"}
    entries = []
    for current, dirs, files in os.walk(directory):
        dirs.sort()
        for filename in sorted(files):
            path = os.path.join(current, filename)
            rel = os.path.relpath(path, root).replace("\\", "/")
            entries.append({"path": rel, "sha256": _sha256_file(path)})
    return {
        "path": os.path.relpath(directory, root).replace("\\", "/"),
        "sha256": _sha256_bytes(_canonical(entries)),
        "file_count": len(entries),
        "status": "loaded",
    }


def _as_rules(value):
    if value in (None, "", False):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        if isinstance(value.get("rules"), list):
            return value["rules"]
        return [
            {"rule_id": str(key), "value": item}
            for key, item in sorted(value.items())
        ]
    return [{"value": value}]


def _scope_matches(scope, scene_types, character_ids):
    scope = scope or {}
    scoped_scenes = set(scope.get("scene_types") or [])
    scoped_characters = set(scope.get("character_ids") or [])
    if scoped_scenes and not scoped_scenes.intersection(scene_types):
        return False
    if scoped_characters and not scoped_characters.intersection(
            character_ids):
        return False
    return True


def _rule_status(rule):
    return (
        rule.get("lifecycle_state")
        or rule.get("status")
        or rule.get("review_status")
        or "APPROVED")


def _field_key(rule):
    scope = rule.get("scope") or {}
    return (
        rule.get("field")
        or rule.get("metric")
        or rule.get("target")
        or rule.get("rule_id")
        or _sha256_bytes(_canonical(rule))[:16],
        scope.get("content_type", "both"),
        tuple(sorted(scope.get("scene_types") or [])),
        tuple(sorted(scope.get("character_ids") or [])),
    )


def _priority(layer, rule):
    content_type = (rule.get("scope") or {}).get("content_type", "both")
    rule_class = rule.get("rule_class", "style_preference")
    if rule_class in ("project_constraint", "candidate_project_constraint"):
        return 900 if layer == "L0" else 500
    if content_type == "dialogue":
        return {
            "L0": 800, "L3": 700, "L2": 600, "L4": 500, "L1": 400,
        }.get(layer, 100)
    return {
        "L0": 800, "L2": 700, "L4": 600, "L1": 500, "L3": 0,
    }.get(layer, 100)


def _card_rules(card, layer, scene_types, character_ids):
    collected = []
    for bucket, rule_class in (
            ("project_constraints", "project_constraint"),
            ("style_preferences", "style_preference"),
            ("style_targets", "style_target")):
        for index, raw in enumerate(_as_rules(card.get(bucket)), 1):
            rule = dict(raw) if isinstance(raw, dict) else {"value": raw}
            status = _rule_status(rule)
            if status in INACTIVE_STATUSES or (
                    status not in ACTIVE_STATUSES
                    and status not in ("extracted", "review_pending")):
                continue
            # Extracted/review-pending rules never become effective.
            if status in ("extracted", "review_pending"):
                continue
            rule.setdefault(
                "rule_id", "%s-%s-%03d" % (layer, bucket, index))
            rule.setdefault("rule_class", rule_class)
            rule.setdefault("scope", card.get("scope") or {
                "content_type": "both",
                "scene_types": [],
                "character_ids": [],
            })
            if layer == "L3":
                rule["scope"] = dict(rule["scope"])
                rule["scope"]["content_type"] = "dialogue"
            if not _scope_matches(
                    rule.get("scope"), scene_types, character_ids):
                continue
            rule["source_layer"] = layer
            rule["source_card_id"] = card.get("card_id")
            rule["effective_priority"] = _priority(layer, rule)
            collected.append(rule)
    return collected


def _safe_card(path, expected_layer):
    card = _load(path)
    if not card:
        return {}
    if card.get("layer") != expected_layer:
        raise ValueError(
            "style card layer mismatch: %s expected=%s actual=%s" %
            (path, expected_layer, card.get("layer")))
    return card


def _active_reference_card(root):
    """Bridge governed ACTIVE legacy JSON candidates into the L4 composer.

    Existing projects promoted reference-learning rules before L0-L4 YAML
    cards existed.  Keeping this read-only bridge prevents those approved
    abstractions from becoming inert while preserving their original source
    file and lifecycle status.
    """
    path = os.path.join(
        root, "memory", "project", "style-library",
        "style-cards.json")
    if not os.path.isfile(path):
        return path, {}
    try:
        with open(path, "r", encoding="utf-8") as stream:
            rows = json.load(stream)
    except (OSError, ValueError):
        return path, {}
    if not isinstance(rows, list):
        return path, {}
    rules = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        candidate_id = row.get("candidate_id")
        lifecycle_path = os.path.join(
            os.path.dirname(path),
            "%s.lifecycle.json" % candidate_id) if candidate_id else None
        lifecycle = {}
        if lifecycle_path and os.path.isfile(lifecycle_path):
            try:
                with open(
                        lifecycle_path, "r",
                        encoding="utf-8") as stream:
                    lifecycle = json.load(stream) or {}
            except (OSError, ValueError):
                lifecycle = {}
        status = lifecycle.get("current_state") or _rule_status(row)
        if status not in ACTIVE_STATUSES:
            continue
        value = row.get("value")
        field = (
            ((row.get("scope") or {}).get("span_selector"))
            or (value.get("dimension") if isinstance(value, dict) else None)
            or row.get("rule_id"))
        rules.append({
            "rule_id": row.get("rule_id") or row.get("candidate_id"),
            "field": field,
            "status": status,
            "scope": row.get("scope") or {
                "content_type": "both",
                "scene_types": [],
                "character_ids": [],
            },
            "value": value,
            "confidence": row.get("confidence"),
            "evidence_count": row.get("evidence_count"),
            "source_candidate_id": candidate_id,
            "source_set_hash": row.get("source_set_hash"),
        })
    return path, {
        "card_id": "L4-ACTIVE-REFERENCE-BRIDGE",
        "layer": "L4",
        "scope": {
            "content_type": "both",
            "scene_types": [],
            "character_ids": [],
        },
        "project_constraints": [],
        "style_preferences": [],
        "style_targets": rules,
    }


def _outline_path(root):
    project = _load(os.path.join(root, "project.yaml"))
    rel = ((project.get("paths") or {}).get("outline") or "").lstrip("./")
    if rel:
        return os.path.join(root, rel)
    return os.path.join(root, "sources", "outline")


def _default_card_paths(root, genre, scene_types, character_ids):
    base = os.path.join(root, "memory", "project", "style-library")
    result = [
        ("L0", os.path.join(base, "project-style.card.yaml")),
        ("L1", os.path.join(base, "genre", "%s.card.yaml" % genre)),
    ]
    result.extend(
        ("L2", os.path.join(base, "scene", "%s.card.yaml" % scene))
        for scene in sorted(scene_types)
    )
    result.extend(
        ("L3", os.path.join(
            base, "character", "%s.card.yaml" % character))
        for character in sorted(character_ids)
    )
    result.append(("L4", os.path.join(base, "author.card.yaml")))
    return result


def _valid_overrides(root, task_id):
    path = os.path.join(
        root, "runtime", "learning", "style-overrides.yaml")
    body = _load(path)
    accepted, rejected = [], []
    for item in body.get("overrides") or []:
        required = ("override_rule_id", "authorized_by", "reason")
        if any(not item.get(name) for name in required):
            rejected.append(dict(item, rejection="missing_authorization"))
            continue
        expires = item.get("expires_after_task")
        if expires not in (True, task_id):
            rejected.append(dict(item, rejection="invalid_expiry"))
            continue
        accepted.append(item)
    return path, accepted, rejected


def build(
        project_root, chapter_id, revision_cycle_id, scene_types=None,
        character_ids=None, task_id=None, writing_strategy_path=None,
        diagnosis_path=None, protected_manifest_path=None, output=None):
    scene_types = set(scene_types or ["daily"])
    character_ids = set(character_ids or [])
    project = _load(os.path.join(project_root, "project.yaml"))
    project_id = ((project.get("project") or {}).get("id")
                  or project.get("id") or "unknown")
    genre = ((project.get("project") or {}).get("type")
             or project.get("genre") or "unknown")
    platform_root = _gov.find_platform_root()
    governance = os.path.join(
        platform_root, "core", "policies", "compliance.policy.yaml")

    source_bindings = {
        "governance_policy": _binding(project_root, governance),
        "nkb_snapshot": _tree_binding(
            project_root, os.path.join(project_root, "NKB")),
        "outline": (
            _binding(project_root, _outline_path(project_root))
            if os.path.isfile(_outline_path(project_root))
            else _tree_binding(project_root, _outline_path(project_root))),
    }
    cards = []
    for layer, path in _default_card_paths(
            project_root, genre, scene_types, character_ids):
        card = _safe_card(path, layer)
        binding = _binding(project_root, path)
        binding["layer"] = layer
        source_bindings.setdefault("style_cards", []).append(binding)
        if card:
            cards.append((layer, card))
    reference_path, reference_card = _active_reference_card(project_root)
    source_bindings["active_reference_rules"] = _tree_binding(
        project_root, os.path.dirname(reference_path))
    if reference_card:
        cards.append(("L4", reference_card))

    strategy = _load(writing_strategy_path) if writing_strategy_path else {}
    diagnosis = _load(diagnosis_path) if diagnosis_path else {}
    manifest = (
        _load(protected_manifest_path)
        if protected_manifest_path else {})
    for key, path in (
            ("writing_strategy", writing_strategy_path),
            ("diagnosis", diagnosis_path),
            ("protected_manifest", protected_manifest_path)):
        if path:
            source_bindings[key] = _binding(project_root, path)

    feedback_paths = {
        "writing_guidance": os.path.join(
            project_root, "runtime", "learning", "writing-guidance.yaml"),
        "review_regression": os.path.join(
            project_root, "runtime", "learning", "review-regression.yaml"),
    }
    feedback = {}
    for name, path in feedback_paths.items():
        feedback[name] = _load(path)
        source_bindings[name] = _binding(project_root, path)

    all_rules = []
    for layer, card in cards:
        all_rules.extend(_card_rules(
            card, layer, scene_types, character_ids))
    override_path, overrides, rejected_overrides = _valid_overrides(
        project_root, task_id)
    source_bindings["explicit_overrides"] = _binding(
        project_root, override_path)
    override_ids = {
        item["override_rule_id"]: item for item in overrides}

    winners = {}
    suppressed = []
    for rule in sorted(
            all_rules,
            key=lambda item: (
                -item["effective_priority"], item["rule_id"])):
        rule_id = rule.get("rule_id")
        if rule_id in override_ids:
            suppressed.append({
                "rule": rule,
                "reason": "explicit_task_override",
                "authorization": override_ids[rule_id],
            })
            continue
        key = _field_key(rule)
        winner = winners.get(key)
        if winner is None:
            winners[key] = rule
            continue
        suppressed.append({
            "rule": rule,
            "reason": "lower_priority_same_field_and_scope",
            "winner_rule_id": winner.get("rule_id"),
        })
    suppressed.extend(rejected_overrides)

    immutable = []
    if manifest:
        for level in (
                "hard_preserve", "functional_preserve", "soft_preserve"):
            immutable.append({
                "level": level,
                "source": "protected_manifest",
                "items": manifest.get(level) or {},
            })
    else:
        immutable.extend([
            {
                "level": "hard",
                "source": "NKB",
                "sha256": source_bindings["nkb_snapshot"].get("sha256"),
            },
            {
                "level": "hard",
                "source": "outline",
                "sha256": source_bindings["outline"].get("sha256"),
            },
        ])

    payload = {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "chapter_id": chapter_id,
        "revision_cycle_id": revision_cycle_id,
        "source_bindings": source_bindings,
        "governance_constraints": [
            {
                "rule_id": "GOV-NKB-FACTS",
                "policy_ref": "core/policies/compliance.policy.yaml",
                "effect": "deny_style_override",
            },
            {
                "rule_id": "GOV-OUTLINE-OUTCOME",
                "policy_ref": "core/policies/compliance.policy.yaml",
                "effect": "deny_style_override",
            },
            {
                "rule_id": "GOV-L3-DIALOGUE-ONLY",
                "policy_ref": "core/learning/风格系统与去AI味实施纲要.md",
                "effect": "deny_narration_scope",
            },
        ],
        "immutable_requirements": immutable,
        "effective_rules": sorted(
            winners.values(),
            key=lambda item: (
                -item["effective_priority"], item["rule_id"])),
        "suppressed_rules": suppressed,
        "explicit_overrides": overrides,
        "writing_strategy": strategy,
        "review_feedback": feedback,
        "current_diagnosis": diagnosis,
        "scene_types": sorted(scene_types),
        "character_ids": sorted(character_ids),
    }
    payload["style_guidance_sha256"] = _sha256_bytes(_canonical(payload))
    if output:
        os.makedirs(os.path.dirname(output), exist_ok=True)
        _gov.dump_yaml(output, payload)
    return payload


def main():
    parser = argparse.ArgumentParser(prog="style-guidance")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--chapter", required=True)
    parser.add_argument("--cycle", required=True)
    parser.add_argument("--task")
    parser.add_argument("--scene", action="append", default=[])
    parser.add_argument("--character", action="append", default=[])
    parser.add_argument("--writing-strategy")
    parser.add_argument("--diagnosis")
    parser.add_argument("--protected-manifest")
    parser.add_argument("--output")
    args = parser.parse_args()
    output = args.output or os.path.join(
        args.project_root, "runtime", "learning", "style-guidance.yaml")
    result = build(
        args.project_root, args.chapter, args.cycle,
        scene_types=args.scene or ["daily"],
        character_ids=args.character, task_id=args.task,
        writing_strategy_path=args.writing_strategy,
        diagnosis_path=args.diagnosis,
        protected_manifest_path=args.protected_manifest,
        output=output)
    print(json.dumps({
        "output": output,
        "style_guidance_sha256": result["style_guidance_sha256"],
        "effective_rules": len(result["effective_rules"]),
        "suppressed_rules": len(result["suppressed_rules"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
