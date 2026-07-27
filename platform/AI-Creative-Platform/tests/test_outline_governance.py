# -*- coding: utf-8 -*-
"""Tests for total-chapter-driven five-level outline governance."""
import datetime
import os
import shutil
import sys
import tempfile
import unittest


PLATFORM_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_ROOT = os.path.join(PLATFORM_ROOT, "scripts")
for child in os.listdir(SCRIPTS_ROOT):
    path = os.path.join(SCRIPTS_ROOT, child)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

import _gov
import design_expansion
import outline_governance
import project_layout
import task_cli
import task_engine
import writing_strategy


class OutlineGovernanceTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="outline_governance_")
        project_layout.scaffold_layout(self.root, "xuanhuan")
        _gov.dump_yaml(os.path.join(self.root, "project.yaml"), {
            "project": {
                "id": "outline-test",
                "name": "大纲测试",
                "type": "xuanhuan",
            },
        })

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _document(self, doc_id, doc_type, status="candidate"):
        return {
            "id": doc_id,
            "type": doc_type,
            "title": doc_id,
            "status": status,
            "version": 1,
            "updated_at": datetime.date.today().isoformat(),
            "owner": "story-architect",
            "project_id": "outline-test",
        }

    def _write_valid_candidates(self):
        outline_governance.prepare(
            self.root, 6, volume_size=10, arc_size=5,
            detailed_window=3)
        base = os.path.join(self.root, "sources", "outline")
        _gov.dump_yaml(os.path.join(
            base, "series", "series-outline.yaml"), {
                "document": self._document(
                    "SERIES-001", "series_outline"),
                "series": {
                    "id": "SERIES-001",
                    "total_chapters": 6,
                    "premise": "工程师在异世经营小镇",
                    "story_promise": "经营解题与关系成长",
                    "protagonist": "CHR-001",
                    "central_conflict": "个人秩序与旧制度冲突",
                    "ending_direction": "建立可持续的新秩序",
                    "major_truths": ["FACT-001"],
                    "major_arcs": ["ARC-001", "ARC-002"],
                    "growth_tracks": {"wealth": "zero_to_stable"},
                    "global_milestones": ["开店", "守店", "立足"],
                    "pacing_policy": {"major_payoff_every": 3},
                    "forbidden_directions": ["无代价成功"],
                },
            })
        _gov.dump_yaml(os.path.join(
            base, "volumes", "VOL-001.yaml"), {
                "document": self._document(
                    "VOL-001", "volume_outline"),
                "volume": {
                    "id": "VOL-001",
                    "number": 1,
                    "chapter_range": [1, 6],
                    "purpose": "完成第一阶段立足",
                    "objective": "取得合法经营资格",
                    "start_state": "无资源",
                    "end_state": "拥有稳定小店",
                    "main_characters": ["CHR-001", "CHR-002"],
                    "main_locations": ["LOC-001"],
                    "central_conflict": "行会阻挠",
                    "antagonist_pressure": "封锁货源",
                    "milestones": ["遇见伙伴", "首次营业", "守住小店"],
                    "midpoint_turn": "伙伴身份暴露",
                    "lowest_point": "货源断绝",
                    "climax": "公开解决供应危机",
                    "aftermath": "获得街坊信任",
                    "reader_promises": ["经营解题"],
                    "questions_opened": ["伙伴为何被追捕"],
                    "questions_answered": ["主角如何开店"],
                    "foreshadow_plan": ["FB-001"],
                    "growth_deltas": ["财富与关系增长"],
                    "next_volume_entry": "行会向上层求援",
                },
            })
        for arc_id, chapter_range in (
                ("ARC-001", [1, 3]), ("ARC-002", [4, 6])):
            _gov.dump_yaml(os.path.join(
                base, "arcs", "%s.yaml" % arc_id), {
                    "document": self._document(
                        arc_id, "arc_outline"),
                    "arc": {
                        "id": arc_id,
                        "volume_id": "VOL-001",
                        "chapter_range": chapter_range,
                        "objective": "推动经营资格",
                        "conflict_engine": "资源封锁迫使主角选择",
                        "start_state": "被动",
                        "end_state": "取得局部主动",
                        "causal_chain": ["封锁", "试错", "突破"],
                        "milestones": ["压力", "选择", "结果"],
                        "character_decisions": ["主角承担风险"],
                        "reader_experience": ["压力与解题兑现"],
                        "payoff": "经营方法获得验证",
                        "handoff": "更高层阻力出现",
                    },
                })
        roles = [
            "opening", "decision", "payoff",
            "escalation", "reversal", "climax",
        ]
        scene_types = [
            "action", "dialogue", "investigation",
            "exploration", "emotional", "business",
        ]
        dominant_techniques = [
            "action_causality", "dialogue_subtext", "clue_progression",
            "sensory_grounding", "embodied_emotion",
            "resource_consequence",
        ]
        opening_modes = [
            "action_in_progress", "dialogue_conflict", "discovery",
            "environmental_anomaly", "emotional_aftershock", "consequence",
        ]
        ending_modes = [
            "consequence", "revelation", "decision",
            "payoff", "relationship_shift", "new_goal",
        ]
        entries = []
        for number in range(1, 7):
            entries.append({
                "chapter_id": "CH-%03d" % number,
                "number": number,
                "volume_id": "VOL-001",
                "arc_id": "ARC-001" if number <= 3 else "ARC-002",
                "role": roles[number - 1],
                "purpose": "完成第%d步经营行动" % number,
                "primary_conflict": "阻力%d" % number,
                "progress": "资格进度推进%d" % number,
                "reader_value": "兑现解题变化%d" % number,
                "planned_change": "状态变化%d" % number,
                "end_hook": "问题升级%d" % number,
                "status": "planned",
            })
        _gov.dump_yaml(os.path.join(
            base, "maps", "chapter-map.yaml"), {
                "document": self._document(
                    "MAP-001", "chapter_map"),
                "chapter_map": {
                    "project_id": "outline-test",
                    "total_chapters": 6,
                    "entries": entries,
                },
            })
        for number in range(1, 7):
            chapter_id = "CH-%03d" % number
            _gov.dump_yaml(os.path.join(
                base, "chapters", "PLAN-%03d.yaml" % number), {
                    "document": self._document(
                        "PLAN-%03d" % number, "chapter_plan"),
                    "plan": {
                        "id": "PLAN-%03d" % number,
                        "chapter_id": chapter_id,
                        "number": number,
                        "volume_id": "VOL-001",
                        "arc_id": (
                            "ARC-001" if number <= 3 else "ARC-002"),
                        "status": "candidate",
                        "role": roles[number - 1],
                        "word_budget": 3000,
                    },
                    "starting_state": {
                        "time": "第一日",
                        "location": "LOC-001",
                        "protagonist_state": "资源不足",
                        "reader_knows": [],
                        "reader_does_not_know": ["伙伴身份"],
                    },
                    "objectives": {
                        "plot": "推进开店",
                        "character": "迫使主角选择",
                        "reader": "兑现一次解题",
                        "arc_progress": "推进资格线",
                    },
                    "conflict": {
                        "desire": "取得材料",
                        "opposition": "行会阻挠",
                        "stakes": "无法营业",
                        "dilemma": "冒险或放弃",
                        "escalation": "价格再次上涨",
                    },
                    "scenes": [{
                        "id": "SC-%03d" % number,
                        "type": scene_types[number - 1],
                        "purpose": "制造并处理阻力",
                        "location": "LOC-001",
                        "participants": ["CHR-001"],
                        "entry_condition": "主角需要材料",
                        "beats": ["发现阻力", "尝试方案", "承担结果"],
                        "turn": "方案产生额外代价",
                        "exit_state": "获得下一步线索",
                        "environment_function": "场地限制迫使主角改变方案",
                        "technique": {
                            "dominant":
                                dominant_techniques[number - 1],
                            "supporting": ["limited_pov_filter"],
                            "rhythm": "由慢到快",
                            "sensory_focus": ["空间距离"],
                            "information_method": "行动结果释放信息",
                            "rationale": "场景阻力需要通过行动因果呈现",
                        },
                    }],
                    "causal_chain": {
                        "prerequisites": ["需要材料"],
                        "causes": ["货源封锁"],
                        "decision": "尝试替代方案",
                        "consequences": ["获得材料但暴露能力"],
                    },
                    "reader_experience": {
                        "opening_question": "如何取得材料",
                        "anticipation": "工程方法能否奏效",
                        "payoff": "方法解决局部问题",
                        "surprise": "成功带来关注",
                        "fairness_evidence": ["先展示测量工具"],
                        "emotional_curve": "焦虑->希望->紧张",
                    },
                    "information_plan": {
                        "reveal": [], "conceal": [],
                        "misinformation": [],
                        "character_knowledge_changes": {},
                    },
                    "foreshadow": {
                        "plant": [], "reinforce": [], "payoff": [],
                    },
                    "expected_deltas": {
                        "character": ["承担风险"],
                        "relationship": [], "assets": [],
                        "world_state": [], "reader_state": [],
                    },
                    "constraints": {
                        "must_happen": ["主角主动选择"],
                        "must_not_happen": ["无代价成功"],
                        "continuity": [], "ooc_guardrails": [],
                    },
                    "ending": {
                        "hook_type": "danger",
                        "hook": "行会注意到主角",
                        "next_chapter_promise": "主角处理新的调查",
                    },
                    "flexibility": {
                        "fixed": ["选择及代价"],
                        "adjustable": ["具体对话"],
                        "fallback": "压缩次要场景",
                    },
                    "narrative_strategy": {
                        "chapter_form": scene_types[number - 1],
                        "pov": "limited_third",
                        "time_structure": "continuous",
                        "dominant_technique":
                            dominant_techniques[number - 1],
                        "supporting_techniques":
                            ["limited_pov_filter"],
                        "prose_rhythm": "由慢到快",
                        "information_density": "medium",
                        "dialogue_ratio": 0.35,
                        "sensory_focus": ["空间距离"],
                        "rationale": "依据本章场景类型和核心阻力选择",
                    },
                    "opening_design": {
                        "previous_plan_id": (
                            "ROOT" if number == 1
                            else "PLAN-%03d" % (number - 1)),
                        "continuity_anchor": "承接前章结果%d" % (
                            number - 1),
                        "entry_mode": opening_modes[number - 1],
                        "first_scene_action": "主角立即处理阻力",
                        "opening_question": "本章阻力如何解决",
                        "reader_orientation": {
                            "time": "上一章之后",
                            "place": "LOC-001",
                            "active_pressure": "经营资格继续受阻",
                        },
                        "prohibited_patterns": [
                            "天气起手", "复述上一章"],
                    },
                    "ending_design": {
                        "next_plan_id": (
                            "END" if number == 6
                            else "PLAN-%03d" % (number + 1)),
                        "closure_mode": ending_modes[number - 1],
                        "resolved_in_chapter": "完成本章经营步骤",
                        "irreversible_change": "经营状态变化%d" % number,
                        "emotional_aftertaste": "压力中出现希望",
                        "retention_driver": "下一阻力已经显现",
                        "final_image": "新取得的材料留下代价痕迹",
                        "next_chapter_bridge": "进入下一经营步骤",
                    },
                })
        return base

    def test_prepare_derives_full_coverage_skeleton(self):
        outputs = outline_governance.prepare(
            self.root, 1000, volume_size=80, arc_size=20,
            detailed_window=20)
        for path in outputs.values():
            self.assertTrue(os.path.isfile(path), path)
        skeleton = _gov.load_yaml(
            outputs["chapter_map_skeleton"])["chapter_map"]
        self.assertEqual(skeleton["total_chapters"], 1000)
        self.assertEqual(len(skeleton["entries"]), 1000)
        plan = _gov.load_yaml(
            outputs["generation_plan"])["outline_generation_plan"]
        self.assertEqual(plan["derived_structure"]["volume_count"], 13)
        self.assertEqual(plan["derived_structure"]["arc_count"], 52)
        self.assertEqual(
            plan["derived_structure"]["required_detailed_plans"], 1000)
        self.assertEqual(
            plan["derived_structure"]["chapter_plan_batch_count"], 50)

    def test_candidates_validate_then_approval_promotes(self):
        self._write_valid_candidates()
        candidate = outline_governance.validate_project(
            self.root, require_approved=False)
        self.assertEqual(
            candidate["outline_validation"]["gate"]["decision"],
            "proceed",
            candidate["outline_validation"]["errors"])
        before = outline_governance.validate_project(
            self.root, require_approved=True)
        self.assertEqual(
            before["outline_validation"]["gate"]["decision"], "block")
        _, promoted, final = outline_governance.approve_outline(
            self.root, "user", "lifecycle/design/APPROVAL_PACKET.yaml")
        self.assertTrue(promoted)
        self.assertEqual(
            final["outline_validation"]["gate"]["decision"], "proceed")
        plan = _gov.load_yaml(os.path.join(
            self.root, "sources", "outline", "chapters",
            "PLAN-001.yaml"))
        self.assertEqual(
            plan["plan"]["status"], "approved_for_writing")

    def test_anti_filler_rejects_three_repeated_chapters(self):
        base = self._write_valid_candidates()
        path = os.path.join(base, "maps", "chapter-map.yaml")
        data = _gov.load_yaml(path)
        entries = data["chapter_map"]["entries"]
        for entry in entries[:3]:
            entry["role"] = "transition"
            entry["purpose"] = "复述信息"
            entry["primary_conflict"] = "没有新冲突"
            entry["progress"] = "没有进展"
            entry["reader_value"] = "重复内容"
        _gov.dump_yaml(path, data)
        report = outline_governance.validate_project(
            self.root, require_approved=False)
        errors = report["outline_validation"]["errors"]
        self.assertTrue(any("anti-filler" in item for item in errors))

    def test_design_prepare_extracts_total_chapters(self):
        outputs = design_expansion.prepare(
            self.root, "新小说计划全书1000章，前期偏市井经营")
        self.assertTrue(os.path.isfile(
            outputs["outline_generation_plan"]))
        policy = _gov.load_yaml(
            outputs["outline_planning_policy"])["planning_policy"]
        self.assertEqual(policy["total_chapters"], 1000)
        self.assertEqual(policy["detailed_window"], 1000)
        self.assertTrue(policy["all_chapters_detailed_required"])

    def test_platform_change_has_priority_over_project_design(self):
        template, task_type, _ = task_cli._map_request(
            "修改平台，新增新项目大纲生成和审查功能")
        self.assertEqual(template, "system-maintenance")
        self.assertEqual(task_type, "system_maintenance")

    def test_chat_total_chapters_enters_project_design_task(self):
        task, _, task_type = task_cli._build_task_from_request(
            self.root, "新项目计划全书1000章", "outline-test",
            "project-producer")
        self.assertEqual(task_type, "project_design")
        self.assertEqual(
            task["inputs"]["values"]["total_chapters"], 1000)

    def test_chapter_claim_blocks_unapproved_outline(self):
        outline_governance.prepare(
            self.root, 6, volume_size=10, arc_size=5,
            detailed_window=3)
        task_engine.create_task(self.root, {
            "task": {
                "id": "TASK-WRITE-001",
                "type": "chapter_write",
                "project": "outline-test",
                "priority": "high",
                "chapter_ref": "chapters/drafts/CH-001.md",
                "inputs": {"required": []},
                "permissions": {
                    "read": ["NKB/**", "sources/outline/**"],
                    "write": ["chapters/drafts/**"],
                },
                "agent": {"required_role": "writer"},
            },
        })
        with self.assertRaisesRegex(ValueError, "outline gate=block"):
            task_engine.claim(
                self.root, "TASK-WRITE-001", "writer", "writer")

    def test_publish_completion_creates_outline_refresh_task(self):
        task_engine.create_task(self.root, {
            "task": {
                "id": "TASK-PUBLISH-001",
                "type": "chapter_publish",
                "project": "outline-test",
                "priority": "high",
                "chapter_ref": "chapters/approved/CH-001.md",
                "inputs": {"required": []},
                "permissions": {
                    "read": ["chapters/**"],
                    "write": ["chapters/approved/**"],
                },
                "agent": {"required_role": "publish_service"},
            },
        })
        task_engine.finish_service_task(
            self.root, "TASK-PUBLISH-001",
            outputs={
                "published_chapter": "chapters/approved/CH-001.md",
                "canonical_manifest": "canonical_manifest.yaml",
            })
        refresh_id = "TASK-PUBLISH-001-OUTLINE-REFRESH"
        state, data = task_engine.load_task(self.root, refresh_id)
        self.assertEqual(state, "ready")
        self.assertEqual(data["task"]["type"], "outline_refresh")
        self.assertEqual(
            data["task"]["chapter_ref"],
            "chapters/approved/CH-001.md")

    def test_all_chapters_require_detailed_plans(self):
        self._write_valid_candidates()
        os.remove(os.path.join(
            self.root, "sources", "outline", "chapters",
            "PLAN-006.yaml"))
        report = outline_governance.validate_project(
            self.root, require_approved=False)
        self.assertEqual(
            report["outline_validation"]["gate"]["decision"], "block")
        self.assertTrue(any(
            "detailed window missing plans" in item
            for item in report["outline_validation"]["errors"]))

    def test_writing_strategy_and_evidence_gate(self):
        self._write_valid_candidates()
        outline_governance.approve_outline(
            self.root, "user",
            "lifecycle/design/APPROVAL_PACKET.yaml")
        strategy_path, strategy = writing_strategy.build(
            self.root, "CH-001", write=True)
        self.assertTrue(os.path.isfile(strategy_path))
        route = strategy["writing_strategy"]["scene_routes"][0]
        self.assertEqual(route["scene_type"], "action")
        self.assertIn("battle", route["capabilities"])
        draft_rel = "chapters/drafts/CH-001.md"
        draft_path = os.path.join(self.root, draft_rel)
        with open(draft_path, "w", encoding="utf-8") as stream:
            stream.write(
                "主角抓起工具冲进后院，追兵已经封住出口。\n"
                "他借地面坡度改变水流，终于留下新的选择。\n")
        evidence_path, evidence = writing_strategy.prepare_evidence(
            self.root, "CH-001", draft_rel)
        body = evidence["writing_strategy_evidence"]
        for check in body["checks"].values():
            check["decision"] = "pass"
            check["evidence"] = ["正文具体段落与章纲相符"]
        body["gate"] = {"decision": "proceed", "reasons": []}
        _gov.dump_yaml(evidence_path, evidence)
        ok, errors, _ = writing_strategy.validate_evidence(
            evidence_path, self.root, "CH-001")
        self.assertTrue(ok, errors)

    def test_chapter_submit_requires_strategy_evidence(self):
        self._write_valid_candidates()
        outline_governance.approve_outline(
            self.root, "user",
            "lifecycle/design/APPROVAL_PACKET.yaml")
        task_engine.create_task(self.root, {
            "task": {
                "id": "TASK-WRITE-EVIDENCE",
                "type": "chapter_write",
                "project": "outline-test",
                "priority": "high",
                "chapter_ref": "chapters/drafts/CH-001.md",
                "inputs": {"required": []},
                "permissions": {
                    "read": ["NKB/**", "sources/outline/**"],
                    "write": ["chapters/drafts/**"],
                },
                "agent": {"required_role": "writer"},
            },
        })
        task_engine.claim(
            self.root, "TASK-WRITE-EVIDENCE", "writer", "writer")
        task_engine.start(
            self.root, "TASK-WRITE-EVIDENCE", "writer", "writer")
        draft_rel = "chapters/drafts/CH-001.md"
        draft_path = os.path.join(self.root, draft_rel)
        with open(draft_path, "w", encoding="utf-8") as stream:
            stream.write(
                "主角抓起工具冲进后院，追兵已经封住出口。\n"
                "他借地面坡度改变水流，终于留下新的选择。\n")
        task_outputs = os.path.join(
            self.root, "tasks", "running",
            "TASK-WRITE-EVIDENCE", "outputs")
        os.makedirs(task_outputs, exist_ok=True)
        delta_path = os.path.join(task_outputs, "facts.yaml")
        handoff_path = os.path.join(task_outputs, "handoff.yaml")
        _gov.dump_yaml(delta_path, {
            "knowledge_delta": {
                "chapter_ref": "CH-001",
                "base_snapshot": "NKB-GENESIS-001",
                "candidates": [],
                "no_change_reason": "测试正文不产生新事实",
            },
        })
        _gov.dump_yaml(handoff_path, {
            "nkb_handoff": {
                "session_id": "TEST",
                "project_id": "outline-test",
                "base_snapshot": "NKB-GENESIS-001",
                "candidate_facts": [],
                "potential_conflicts": [],
                "recommended_actions": [],
            },
        })
        outputs = {
            "chapter_draft": draft_rel,
            "candidate_facts": os.path.relpath(
                delta_path, self.root).replace("\\", "/"),
            "handoff": os.path.relpath(
                handoff_path, self.root).replace("\\", "/"),
        }
        with self.assertRaisesRegex(
                ValueError, "writing_strategy_evidence missing"):
            task_engine.submit(
                self.root, "TASK-WRITE-EVIDENCE", draft_rel,
                outputs=outputs, agent="writer", role="writer")
        evidence_path, evidence = writing_strategy.prepare_evidence(
            self.root, "CH-001", draft_rel)
        body = evidence["writing_strategy_evidence"]
        for check in body["checks"].values():
            check["decision"] = "pass"
            check["evidence"] = ["正文首尾与对应章纲字段逐项核对通过"]
        body["gate"] = {"decision": "proceed", "reasons": []}
        _gov.dump_yaml(evidence_path, evidence)
        outputs["writing_strategy_evidence"] = os.path.relpath(
            evidence_path, self.root).replace("\\", "/")
        task_engine._writing_strategy_output_precheck(
            self.root, "TASK-WRITE-EVIDENCE",
            task_engine.load_task(
                self.root, "TASK-WRITE-EVIDENCE")[1]["task"],
            outputs)


if __name__ == "__main__":
    unittest.main()
