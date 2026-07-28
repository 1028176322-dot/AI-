# -*- coding: utf-8 -*-
"""Legacy conversation chain compatibility: review feedback -> publish.

The strict-v2 style lifecycle has its own 20-case E2E suite.  This fixture is
explicitly marked as a non-migrated project so it continues to verify that the
platform does not silently force existing projects onto the new chain.
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile


PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_ROOT = os.path.join(PLATFORM_ROOT, "scripts")
for child in os.listdir(SCRIPTS_ROOT):
    path = os.path.join(SCRIPTS_ROOT, child)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

import _gov
import project_layout
import publish_chapter
import reader_panel
import review_orchestrator
import status_update
import task_engine


NKB_COMPONENTS = [
    "Canon", "Characters", "Locations", "Organizations", "Timeline",
    "WorldState", "Events", "Foreshadow", "Assets", "Terminology",
    "StoryState", "ReaderState", "Graph", "Derived",
]


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def setup_project(root):
    project_layout.scaffold_layout(root, "xuanhuan")
    layout_path = os.path.join(root, "PROJECT_LAYOUT.yaml")
    layout = _gov.load_yaml(layout_path)
    layout["style_system"] = {
        "enabled": False,
        "enforcement_profile": "legacy-unmigrated",
        "full_chapter_chain_required": False,
        "broker_fail_closed": False,
    }
    _gov.dump_yaml(layout_path, layout)
    _gov.dump_yaml(os.path.join(root, "project.yaml"), {
        "project": {"id": "chain-test", "name": "链路测试", "type": "xuanhuan"},
        "requires": {"platform": ">=2.1.0"},
        "paths": {
            "nkb": "./NKB", "outline": "./sources/outline",
            "chapters": "./chapters", "artifacts": "./artifacts",
            "memory": "./memory/project",
        },
        "gates": {
            "editor_score": 80, "consistency_index": 0.95,
            "reader_index": 60, "payment_intent": 60,
        },
    })
    with open(os.path.join(root, "sources", "outline", "main.md"),
              "w", encoding="utf-8") as stream:
        stream.write("# 主线\n少年下山，发现钟声与旧案相关。\n")
    for component in NKB_COMPONENTS:
        _gov.dump_yaml(os.path.join(root, "NKB", "%s.yaml" % component), {
            "schema_version": "1.3.0",
            "project_id": "chain-test",
            "records": [],
        })
    _gov.dump_yaml(os.path.join(root, "NKB", "manifest.yaml"), {
        "nkb": {
            "project_id": "chain-test",
            "schema_version": "1.3.0",
            "snapshot_id": "NKB-BASE-001",
            "status": "active",
            "authoritative": True,
        },
        "components": {
            component: {
                "file": "%s.yaml" % component,
                "version": 0,
            }
            for component in NKB_COMPONENTS
        },
        "integrity": {
            "unresolved_conflicts": 0,
            "broken_references": 0,
            "pending_candidates": 0,
        },
    })
    status_update.init(root, project_id="chain-test", stage="writing")
    session_dir = os.path.join(
        root, "runtime", "sessions", "SESSION-E2E46")
    os.makedirs(session_dir, exist_ok=True)
    _gov.dump_yaml(os.path.join(session_dir, "SESSION_MANIFEST.yaml"), {
        "session": {"id": "SESSION-E2E46"},
        "project": {"id": "chain-test"},
        "ready": True,
    })


def fill_reader_panel(path):
    report = _gov.load_yaml(path)
    evidence_excerpt = None
    if report.get("source") and os.path.isfile(report["source"]):
        with open(report["source"], "r", encoding="utf-8") as stream:
            source_text = stream.read()
        # Keep the fixture evidence YAML-lite-safe while still proving that
        # every lens points to text that exists in the chapter.
        evidence_excerpt = "1" if "1" in source_text else source_text.strip()[:1]
    for lens in report["lenses"]:
        lens.update({
            "score": 78,
            "observation": "目标与阻力清楚",
            "evidence_location": "第2段",
            "reading_effect": "愿意继续阅读",
            "expectation": "期待钟声真相",
            "recommended_fix": "保留因果和章末承诺",
            "confidence": 0.82,
            "evidence_excerpt": evidence_excerpt,
        })
    report["dropoff"] = {
        "risk": "low", "location": "无明显停读点", "reason": "场景持续变化"}
    report["summary"] = "可读，具备继续阅读动机"
    _gov.dump_yaml(path, report)
    ok, errors, _ = reader_panel.validate_panel(path)
    check(ok, "reader panel invalid: %s" % errors)


def main():
    root = tempfile.mkdtemp(prefix="e2e46_project_")
    try:
        setup_project(root)
        cli = os.path.join(PLATFORM_ROOT, "cli", "platform.py")
        command = [
            sys.executable, cli, "task", "--project-root", root,
            "dispatch", "--request", "写两章并审查",
            "--project", "chain-test", "--agent", "e2e46", "--model", "test",
        ]
        process = subprocess.run(
            command, cwd=PLATFORM_ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace")
        check(process.returncode == 0, process.stdout + process.stderr)

        goals = glob.glob(os.path.join(root, "tasks", "goals", "GOAL-REQ-*.yaml"))
        check(len(goals) == 1, "conversation goal not created")
        goal = _gov.load_yaml(goals[0])["goal"]
        task_ids = goal["task_ids"]
        check(len(task_ids) == 2, "expected two plan tasks")
        first_plan, second_plan = task_ids
        check(task_engine.load_task(root, first_plan)[0] == "ready",
              "first plan must be ready")
        check(task_engine.load_task(root, second_plan)[0] == "backlog",
              "second plan must wait for first publish")
        for task_id in task_ids:
            packet = os.path.join(root, "runtime", "task-packets", task_id)
            check(os.path.isfile(os.path.join(packet, "task.yaml")),
                  "Task Packet missing for %s" % task_id)

        ok, report = task_engine.ready_check(root, first_plan)
        check(ok, "plan ready check failed: %s" % report)
        task_engine.claim(root, first_plan, "architect", "story-architect")
        task_engine.start(root, first_plan, "architect", "story-architect")
        plan_rel = "tasks/running/%s/outputs/chapter-plan.md" % first_plan
        with open(os.path.join(root, plan_rel), "w", encoding="utf-8") as stream:
            stream.write("# CH-001\n目标：追查钟声。阻力：山门封闭。章末：门后有人回应。\n")
        write_id = task_engine.submit(
            root, first_plan, plan_rel,
            outputs={"chapter_plan": plan_rel},
            checks={"plan_contract": "pass"},
            agent="architect", role="story-architect")[1]
        check(task_engine.load_task(root, write_id)[0] == "ready",
              "write successor must be ready")
        check(os.path.isfile(os.path.join(
            root, "runtime", "task-packets", write_id, "task.yaml")),
            "write successor packet missing")

        task_engine.claim(root, write_id, "writer", "writer")
        task_engine.start(root, write_id, "writer", "writer")
        draft_rel = "chapters/drafts/CH-001.md"
        paragraphs = []
        for index in range(1, 45):
            paragraphs.append(
                "第%d次钟声落下，少年沿石阶向上。他观察门缝里的灯影，"
                "没有急着推门，而是先问守门人昨夜谁曾经过。守门人沉默片刻，"
                "终于说出一个与旧案相关的名字。这个答案让下一步选择更危险。" % index)
        # Keep the sample inside the platform's 2500-3000 character contract
        # while ensuring every sentence carries unique evidence. This makes
        # the real quality gate meaningful instead of bypassing it in the E2E.
        paragraphs = [
            (
                "第%d次钟声落下时，少年沿山门石阶向上，先比较两侧苔痕的新旧。"
                "第%d次观察里，他发现门缝灯影向左偏移，便没有贸然推门。"
                "第%d次询问时，守门人先否认昨夜有人来过，随后却避开旧案姓名。"
                "第%d次判断让少年改变路线，决定从藏经阁账册验证这句矛盾证词。"
            ) % (index, index, index, index)
            for index in range(1, 29)
        ]
        with open(os.path.join(root, draft_rel), "w", encoding="utf-8") as stream:
            stream.write("# 第一章 山门钟声\n\n" + "\n\n".join(paragraphs))
        candidate_rel = (
            "tasks/running/%s/outputs/candidate-facts.yaml" % write_id)
        _gov.dump_yaml(os.path.join(root, candidate_rel), {
            "knowledge_delta": {
                "chapter_ref": "CH-001",
                "base_snapshot": "NKB-BASE-001",
                "candidates": [{
                    "id": "CAND-CH-001-001",
                    "target_component": "Events",
                    "operation": "create",
                    "target_id": "EVT-CH-001-BELL",
                    "field": "record",
                    "value": {"name": "山门钟声调查"},
                    "source": {
                        "type": "approved_manuscript",
                        "file": draft_rel,
                        "build_id": write_id,
                    },
                    "classification": {
                        "fact_type": "occurred",
                        "confidence": 0.95,
                        "requires_author_decision": False,
                        "contains_inference": False,
                    },
                    "effects": {
                        "create_event": "EVT-CH-001-BELL",
                        "rebuild": ["Timeline", "WorldState"],
                    },
                    "status": "pending_validation",
                }],
            },
        })
        handoff_rel = "tasks/running/%s/outputs/nkb-handoff.yaml" % write_id
        _gov.dump_yaml(os.path.join(root, handoff_rel), {
            "nkb_handoff": {
                "session_id": "SESSION-E2E46",
                "project_id": "chain-test",
                "base_snapshot": "NKB-BASE-001",
                "candidate_facts": candidate_rel,
                "potential_conflicts": [],
                "recommended_actions": ["accept EVT-CH-001-BELL"],
            },
        })
        review_id = task_engine.submit(
            root, write_id, draft_rel,
            outputs={
                "chapter_draft": draft_rel,
                "candidate_facts": candidate_rel,
                "handoff": handoff_rel,
            },
            checks={"self_check": "pass"},
            agent="writer", role="writer")[1]
        check(task_engine.load_task(root, review_id)[0] == "ready",
              "review successor must be ready")
        check(os.path.isfile(os.path.join(
            root, "runtime", "task-packets", review_id, "task.yaml")),
            "review successor packet missing")

        task_engine.claim(root, review_id, "reviewer", "reviewer")
        task_engine.start(root, review_id, "reviewer", "reviewer")
        review_orchestrator.run_review(root, review_id)
        panel_path = os.path.join(
            root, "runtime", "reader-panels",
            "PANEL-%s" % review_id, "report.yaml")
        fill_reader_panel(panel_path)
        report_path = os.path.join(
            root, "runtime", "reviews", "REVIEW-%s" % review_id,
            "report.yaml")
        review_report = _gov.load_yaml(report_path)
        finding = {
            "id": "F-1", "category": "logic", "severity": "warn",
            "location": "第3段", "observation": "线索触发略快",
            "evidence": "守门人立即给出名字", "reasoning": "缺少交换条件",
            "impact": "读者可能觉得信息获得过易",
            "recommended_fix": "后续章节补充守门人的交换动机",
        }
        review_report["findings"] = [finding]
        review_report["verdict"] = "pass_with_fixes"
        _gov.dump_yaml(report_path, review_report)
        valid, errors = review_orchestrator.validate_report(root, review_id)
        check(valid, "review report invalid: %s" % errors)
        task_engine.review(
            root, review_id, "pass", findings=[finding],
            reviewer="reviewer", role="reviewer",
            outputs={"review_report": report_path})

        feedback = os.path.join(
            root, "runtime", "learning", "writing-guidance.yaml")
        check(os.path.isfile(feedback), "review finding did not feed writing")
        publish_id = "%s-PUBLISH" % write_id
        nkb_update_id = "%s-NKB-UPDATE" % write_id
        check(task_engine.load_task(root, nkb_update_id)[0] == "ready",
              "NKB update task missing")
        check(task_engine.load_task(root, publish_id)[0] == "backlog",
              "publish must wait for NKB sync")
        task_engine.claim(
            root, nkb_update_id, "knowledge-manager", "knowledge-manager")
        task_engine.start(
            root, nkb_update_id, "knowledge-manager", "knowledge-manager")
        event_path = os.path.join(root, "NKB", "Events.yaml")
        event_data = _gov.load_yaml(event_path)
        event_data["records"].append({
            "id": "EVT-CH-001-BELL",
            "name": "山门钟声调查",
            "chapter": "CH-001",
            "participants": [],
            "cause": "少年追查旧案线索",
            "effect": "确定藏经阁账册为下一调查目标",
            "state_deltas": ["调查路线改变"],
            "truth_status": "occurred",
            "source": {
                "source_type": "chapter",
                "source_file": draft_rel,
                "source_anchor": "全文",
                "source_version": 1,
                "approval_status": "approved",
            },
        })
        _gov.dump_yaml(event_path, event_data)
        manifest_path = os.path.join(root, "NKB", "manifest.yaml")
        manifest = _gov.load_yaml(manifest_path)
        manifest["nkb"]["snapshot_id"] = "NKB-CH-001-001"
        manifest["components"]["Events"]["version"] = 1
        _gov.dump_yaml(manifest_path, manifest)
        change_rel = (
            "tasks/running/%s/outputs/nkb-change.yaml" % nkb_update_id)
        operation_rel = (
            "tasks/running/%s/outputs/operation-manifest.yaml" %
            nkb_update_id)
        _gov.dump_yaml(os.path.join(root, change_rel), {
            "nkb_change": {
                "accepted": ["EVT-CH-001-BELL"],
                "rejected": [],
                "snapshot_after": "NKB-CH-001-001",
            },
        })
        _gov.dump_yaml(os.path.join(root, operation_rel), {
            "operation": {
                "source_task": nkb_update_id,
                "approved_event": review_id,
                "files": ["NKB/Events.yaml", "NKB/manifest.yaml"],
            },
        })
        sync_id = task_engine.submit(
            root, nkb_update_id, change_rel,
            outputs={
                "nkb_change": change_rel,
                "operation_manifest": operation_rel,
                "nkb_snapshot_after": "NKB/manifest.yaml",
            },
            checks={"candidate_disposition": "pass"},
            agent="knowledge-manager", role="knowledge-manager")[1]
        check(task_engine.load_task(root, sync_id)[0] == "ready",
              "NKB sync review task missing")
        task_engine.claim(
            root, sync_id, "reviewer", "reviewer")
        task_engine.start(
            root, sync_id, "reviewer", "reviewer")
        sync_report_rel = (
            "tasks/running/%s/outputs/nkb-review-report.yaml" % sync_id)
        _gov.dump_yaml(os.path.join(root, sync_report_rel), {
            "nkb_review": {
                "decision": "pass",
                "snapshot": "NKB-CH-001-001",
                "findings": [],
            },
        })
        task_engine.submit(
            root, sync_id, sync_report_rel,
            outputs={
                "nkb_sync_proof": sync_report_rel,
                "validation_report": sync_report_rel,
            },
            checks={"canonical_validation": "pass"},
            agent="reviewer", role="reviewer")
        task_engine.review(
            root, sync_id, "pass",
            reviewer="reviewer", role="reviewer")
        check(task_engine.load_task(root, publish_id)[0] == "ready",
              "publish was not unlocked after NKB sync")
        check(os.path.isfile(os.path.join(
            root, "runtime", "task-packets", publish_id, "task.yaml")),
            "publish task packet missing")
        entry = publish_chapter.publish(root, publish_id)
        approved = os.path.join(root, "chapters", "approved", "CH-001.md")
        check(os.path.isfile(approved), "strict project publish target missing")
        check(entry["path"] == "chapters/approved/CH-001.md",
              "unexpected canonical target: %s" % entry["path"])
        check(task_engine.load_task(root, first_plan)[0] == "completed",
              "plan task was stranded")
        check(task_engine.load_task(root, second_plan)[0] == "ready",
              "next chapter was not promoted after publish")
        check(project_layout.validate(root)["gate"]["decision"] == "proceed",
              "strict layout drifted during real workflow")
        print("PASS: conversation -> write -> reader review -> NKB sync -> publish -> next")
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
