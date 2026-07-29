# -*- coding: utf-8 -*-
"""Unified CLI for the strict-v2 style and anti-template lifecycle."""
import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_ROOT = os.path.dirname(HERE)
for _child in os.listdir(SCRIPTS_ROOT):
    _path = os.path.join(SCRIPTS_ROOT, _child)
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

import _gov
import author_learning
import chapter_apply
import chapter_rollback
import diagnosis
import fidelity_review
import final_regression
import manifest_build
import project_layout
import quality_review
import style_guidance
import style_revise
import task_engine


def _load(path, default=None):
    if not path:
        return default
    if path.lower().endswith(".json"):
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    return _gov.load_yaml(path)


def _text(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _print(result):
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _manifest_build(arguments):
    result = manifest_build.build_manifest(
        arguments.chapter, arguments.cycle, arguments.task,
        _text(arguments.draft),
        nkb_snapshot=_load(arguments.nkb, {}),
        outline_text=_text(arguments.outline) if arguments.outline else "",
        model_id=arguments.model,
        prompt_hash=arguments.prompt_hash)
    persisted = manifest_build.persist(
        result, arguments.project_root,
        arguments.chapter, arguments.cycle)
    if result.get("manifest"):
        persisted["protected_manifest_sha256"] = (
            manifest_build.manifest_sha256(result["manifest"]))
    _print(persisted)
    return 0 if result["status"] == "MANIFEST_READY" else 1


def _diagnose(arguments):
    manifest = _load(arguments.manifest, {}) or {}
    guidance = _load(arguments.guidance, {}) or {}
    chapter_review = _load(arguments.chapter_review, None)
    semantic_clearance = (
        diagnosis.clearance_from_review(
            chapter_review,
            _sha256_file(arguments.chapter_review))
        if chapter_review else None)
    report = diagnosis.ai_diagnose(
        arguments.chapter, arguments.cycle, arguments.task,
        _text(arguments.draft),
        protected_manifest_sha256=(
            manifest_build.manifest_sha256(manifest)
            if manifest else ""),
        semantic_evidence=_load(arguments.semantic_evidence, []),
        style_guidance=guidance,
        semantic_clearance=semantic_clearance,
        require_semantic_evidence=not arguments.preview_signals_only)
    path = diagnosis.persist(
        report, arguments.project_root,
        arguments.chapter, arguments.task)
    _print({"report": path, "event": (
        "on_issues" if report["has_issues"]
        else "on_warning" if report["only_warnings"]
        else "on_clean"), **report})
    return 0


def _revise(arguments):
    draft = _text(arguments.draft)
    candidate = _text(arguments.candidate) if arguments.candidate else None
    guidance = _load(arguments.guidance, {}) or {}
    manifest = _load(arguments.manifest, {}) or {}
    report = style_revise.ai_revise(
        arguments.chapter, arguments.cycle, arguments.task, draft,
        protected_manifest_sha256=(
            manifest_build.manifest_sha256(manifest)
            if manifest else ""),
        applied_style_rules=guidance.get("effective_rules") or [],
        style_guidance_sha256=guidance.get(
            "style_guidance_sha256", ""),
        source_draft_sha256=hashlib.sha256(
            draft.encode("utf-8")).hexdigest(),
        ai_candidate_text=candidate,
        ai_change_log=_load(arguments.change_log, []),
        semantic_evidence_ref=arguments.semantic_evidence,
        require_ai_candidate=not arguments.preview)
    outputs = style_revise.persist(
        report, arguments.project_root,
        candidate if candidate is not None else draft,
        arguments.chapter, arguments.cycle, arguments.task)
    _print({**outputs, **report})
    return 0


def _fidelity(arguments):
    report = fidelity_review.review(
        arguments.chapter, arguments.cycle, arguments.task,
        _text(arguments.source), _text(arguments.candidate),
        _load(arguments.manifest, {}) or {},
        semantic_evidence=_load(arguments.semantic_evidence, []),
        require_semantic_evidence=not arguments.preview)
    path = fidelity_review.persist(
        report, arguments.project_root,
        arguments.chapter, arguments.cycle)
    _print({"report": path, **report})
    return 0 if report["result"] == "FIDELITY_PASSED" else 1


def _quality(arguments):
    guidance = _load(arguments.guidance, {}) or {}
    report = quality_review.review(
        arguments.chapter, arguments.cycle, arguments.task, arguments.task,
        arguments.scene, _text(arguments.candidate),
        quality_review.load_policy(arguments.policy),
        applied_style_rules=[
            row.get("rule_id")
            for row in guidance.get("effective_rules") or []],
        style_guidance=guidance,
        semantic_scores=_load(arguments.semantic_scores, {}),
        semantic_evidence=_load(arguments.semantic_evidence, []),
        require_semantic_evidence=not arguments.preview)
    path = quality_review.persist(
        report, arguments.project_root,
        arguments.chapter, arguments.cycle, arguments.task)
    _print({"report": path, **report})
    return 0 if report["overall"] == "QUALITY_PASSED" else 1


def _apply(arguments):
    result = chapter_apply.execute_apply(
        arguments.project_root, arguments.task,
        arguments.chapter, arguments.cycle,
        arguments.draft, arguments.candidate,
        arguments.expected_sha256, arguments.manifest,
        arguments.guidance, arguments.fidelity,
        arguments.quality, actor_id=arguments.actor)
    _print(result)
    return 0 if result.get("status") == "APPLY_READY" else 1


def _final_regression(arguments):
    manifest = _load(arguments.manifest, {}) or {}
    guidance = _load(arguments.guidance, {}) or {}
    if (
            arguments.mode == "post_apply"
            and not arguments.preview
            and (not arguments.pre_apply
                 or not arguments.fidelity
                 or not arguments.quality)):
        raise ValueError(
            "strict post_apply requires pre-apply, fidelity and quality")
    kwargs = {
        "nkb_revision": arguments.nkb_revision,
        "nkb_snapshot_sha256": arguments.nkb_snapshot_sha256,
        "protected_manifest_sha256":
            manifest_build.manifest_sha256(manifest),
        "outline_sha256": _sha256_file(arguments.outline),
        "style_guidance_sha256":
            guidance.get("style_guidance_sha256", ""),
        "chapter_review_report_sha256": _sha256_file(arguments.chapter_review),
        "fidelity_report": _load(arguments.fidelity, None),
        "quality_report": _load(arguments.quality, None),
        "require_report_bindings": not arguments.preview,
    }
    if arguments.mode == "baseline":
        kwargs["draft_text"] = _text(arguments.draft)
    else:
        kwargs["pre_apply_text"] = _text(arguments.pre_apply)
        kwargs["applied_draft_text"] = _text(arguments.draft)
    report = final_regression.run_regression(
        arguments.mode, arguments.chapter,
        arguments.cycle, arguments.task, **kwargs)
    path = final_regression.persist(
        report, arguments.project_root,
        arguments.chapter, arguments.cycle, arguments.task)
    _print({"report": path, **report})
    return 0 if report.get("result") == "FINAL_PASSED" else 1


def _rollback(arguments):
    report = chapter_rollback.execute_rollback(
        arguments.project_root, arguments.task,
        arguments.chapter, arguments.cycle,
        arguments.draft, arguments.backup,
        arguments.applied_sha256, arguments.regression,
        actor_id=arguments.actor)
    _print(report)
    return 0 if report.get("result") == "ROLLED_BACK" else 1


def _author_feedback(arguments):
    store = os.path.join(
        arguments.project_root, "runtime", "learning", "author-feedback")
    if arguments.feedback_action == "record":
        entry = author_learning.record_feedback(
            arguments.chapter, arguments.span_start, arguments.span_end,
            _text(arguments.original), _text(arguments.revised),
            arguments.reason, kind=arguments.kind,
            scene_type=arguments.scene,
            accepted=arguments.accepted,
            reviewer_id=arguments.author,
            task_id=arguments.task, feedback_store=store,
            description=arguments.description)
        _print(entry)
        return 0
    candidates = author_learning.generate_l4_candidates(
        store, min_evidence=arguments.min_evidence)
    if arguments.feedback_action == "generate":
        paths = [
            author_learning.persist_l4_candidate(
                candidate,
                os.path.join(
                    arguments.project_root,
                    "memory", "project", "style-library"))
            for candidate in candidates
        ]
        _print({"candidate_count": len(candidates), "paths": paths})
        return 0
    result = author_learning.promote_l4_candidate(
        arguments.candidate,
        os.path.join(
            arguments.project_root,
            "memory", "project", "style-library"),
        approved_by=arguments.author,
        approval_evidence=arguments.approval_evidence)
    _print(result)
    return 0


def _event(arguments):
    outputs = _load(arguments.outputs, {}) or {}
    result = task_engine.finish_with_event(
        arguments.project_root, arguments.task, arguments.event,
        outputs, checks={"style_cli": "pass"},
        actor=arguments.actor, role=arguments.role,
        model=arguments.model)
    _print(result)
    return 0


def _status(arguments):
    strict = project_layout.is_style_strict(arguments.project_root)
    guidance = os.path.join(
        arguments.project_root, "runtime", "learning",
        "style-guidance.yaml")
    broker = os.path.join(
        arguments.project_root, "runtime", "learning",
        "broker-status.json")
    result = {
        "project_root": os.path.realpath(arguments.project_root),
        "strict_layout": strict,
        "style_system": "strict-v2" if strict else "legacy_or_unmarked",
        "style_guidance_present": os.path.isfile(guidance),
        "broker_status_present": os.path.isfile(broker),
        "deployment_state": (
            "VERIFY_BROKER_STATUS"
            if os.path.isfile(broker) else "BLOCKED_NOT_DEPLOYED"),
    }
    _print(result)
    return 0 if strict else 1


def _common(subparser):
    subparser.add_argument("--project-root", required=True)
    subparser.add_argument("--chapter", required=True)
    subparser.add_argument("--cycle", required=True)
    subparser.add_argument("--task", required=True)


def main():
    parser = argparse.ArgumentParser(prog="style")
    sub = parser.add_subparsers(dest="action", required=True)

    guidance = sub.add_parser("guidance-build")
    _common(guidance)
    guidance.add_argument("--scene", action="append", default=[])
    guidance.add_argument("--character", action="append", default=[])
    guidance.add_argument("--writing-strategy")
    guidance.add_argument("--diagnosis")
    guidance.add_argument("--protected-manifest")
    guidance.add_argument("--output")

    manifest = sub.add_parser("manifest-build")
    _common(manifest)
    manifest.add_argument("--draft", required=True)
    manifest.add_argument("--nkb")
    manifest.add_argument("--outline")
    manifest.add_argument("--model", default="")
    manifest.add_argument("--prompt-hash", default="")

    diagnose_parser = sub.add_parser("diagnose")
    _common(diagnose_parser)
    diagnose_parser.add_argument("--draft", required=True)
    diagnose_parser.add_argument("--manifest", required=True)
    diagnose_parser.add_argument("--guidance", required=True)
    diagnose_parser.add_argument("--semantic-evidence")
    diagnose_parser.add_argument("--chapter-review")
    diagnose_parser.add_argument(
        "--preview-signals-only", action="store_true")

    revise = sub.add_parser("revise")
    _common(revise)
    revise.add_argument("--draft", required=True)
    revise.add_argument("--candidate")
    revise.add_argument("--change-log")
    revise.add_argument("--semantic-evidence")
    revise.add_argument("--guidance", required=True)
    revise.add_argument("--manifest", required=True)
    revise.add_argument("--preview", action="store_true")

    fidelity = sub.add_parser("fidelity-review")
    _common(fidelity)
    fidelity.add_argument("--source", required=True)
    fidelity.add_argument("--candidate", required=True)
    fidelity.add_argument("--manifest", required=True)
    fidelity.add_argument("--semantic-evidence")
    fidelity.add_argument("--preview", action="store_true")

    quality = sub.add_parser("quality-review")
    _common(quality)
    quality.add_argument("--candidate", required=True)
    quality.add_argument("--scene", required=True)
    quality.add_argument("--guidance", required=True)
    quality.add_argument("--policy", required=True)
    quality.add_argument("--semantic-scores")
    quality.add_argument("--semantic-evidence")
    quality.add_argument("--preview", action="store_true")

    apply_parser = sub.add_parser("apply")
    _common(apply_parser)
    apply_parser.add_argument("--draft", required=True)
    apply_parser.add_argument("--candidate", required=True)
    apply_parser.add_argument("--expected-sha256", required=True)
    apply_parser.add_argument("--manifest", required=True)
    apply_parser.add_argument("--guidance", required=True)
    apply_parser.add_argument("--fidelity", required=True)
    apply_parser.add_argument("--quality", required=True)
    apply_parser.add_argument("--actor")

    regression = sub.add_parser("final-regression")
    _common(regression)
    regression.add_argument(
        "--mode", choices=["baseline", "post_apply"], required=True)
    regression.add_argument("--draft", required=True)
    regression.add_argument("--pre-apply")
    regression.add_argument("--manifest", required=True)
    regression.add_argument("--guidance", required=True)
    regression.add_argument("--outline", required=True)
    regression.add_argument("--chapter-review", required=True)
    regression.add_argument("--fidelity")
    regression.add_argument("--quality")
    regression.add_argument("--nkb-revision", required=True)
    regression.add_argument("--nkb-snapshot-sha256", required=True)
    regression.add_argument("--preview", action="store_true")

    rollback = sub.add_parser("rollback")
    _common(rollback)
    rollback.add_argument("--draft", required=True)
    rollback.add_argument("--backup", required=True)
    rollback.add_argument("--applied-sha256", required=True)
    rollback.add_argument("--regression", required=True)
    rollback.add_argument("--actor")

    feedback = sub.add_parser("author-feedback")
    feedback.add_argument(
        "feedback_action", choices=["record", "generate", "promote"])
    feedback.add_argument("--project-root", required=True)
    feedback.add_argument("--chapter")
    feedback.add_argument("--task", default="author-feedback")
    feedback.add_argument("--span-start", type=int, default=0)
    feedback.add_argument("--span-end", type=int, default=0)
    feedback.add_argument("--original")
    feedback.add_argument("--revised")
    feedback.add_argument("--reason", default="")
    feedback.add_argument("--description", default="")
    feedback.add_argument("--kind", default="stylistic")
    feedback.add_argument("--scene", default="")
    feedback.add_argument("--accepted", action="store_true")
    feedback.add_argument("--author", required=True)
    feedback.add_argument("--min-evidence", type=int, default=3)
    feedback.add_argument("--candidate")
    feedback.add_argument("--approval-evidence")

    event = sub.add_parser("event-verify")
    event.add_argument("--project-root", required=True)
    event.add_argument("--task", required=True)
    event.add_argument("--event", required=True)
    event.add_argument("--outputs", required=True)
    event.add_argument("--actor", required=True)
    event.add_argument("--role", required=True)
    event.add_argument("--model", default="unknown")

    status = sub.add_parser("status")
    status.add_argument("--project-root", required=True)

    arguments = parser.parse_args()
    actions = {
        "manifest-build": _manifest_build,
        "diagnose": _diagnose,
        "revise": _revise,
        "fidelity-review": _fidelity,
        "quality-review": _quality,
        "apply": _apply,
        "final-regression": _final_regression,
        "rollback": _rollback,
        "author-feedback": _author_feedback,
        "event-verify": _event,
        "status": _status,
    }
    if arguments.action == "guidance-build":
        output = arguments.output or os.path.join(
            arguments.project_root, "runtime", "learning",
            "style-guidance", "%s.yaml" % arguments.task)
        result = style_guidance.build(
            arguments.project_root, arguments.chapter, arguments.cycle,
            scene_types=arguments.scene or ["daily"],
            character_ids=arguments.character,
            task_id=arguments.task,
            writing_strategy_path=arguments.writing_strategy,
            diagnosis_path=arguments.diagnosis,
            protected_manifest_path=arguments.protected_manifest,
            output=output)
        _print({"output": output, **result})
        return
    sys.exit(actions[arguments.action](arguments))


if __name__ == "__main__":
    main()
