# -*- coding: utf-8 -*-
"""Strict, reusable directory contract for projects created by the platform."""
import argparse
import datetime
import os
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_ROOT = os.path.dirname(HERE)
for child in os.listdir(SCRIPTS_ROOT):
    path = os.path.join(SCRIPTS_ROOT, child)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

import _gov


LAYOUT_VERSION = "2.0.0"
STYLE_ENFORCEMENT_VERSION = "strict-v2"
REQUIRED_DIRS = [
    "NKB",
    "sources/references/inbox",
    "sources/references/manifests",
    "sources/research/market",
    "sources/design/story",
    "sources/design/world",
    "sources/design/characters",
    "sources/design/_intake",
    "sources/design/_candidates",
    "sources/design/factions",
    "sources/design/locations",
    "sources/design/items",
    "sources/design/abilities",
    "sources/design/conflicts",
    "sources/design/arcs",
    "sources/design/foreshadow",
    "sources/outline",
    "sources/outline/_intake",
    "sources/outline/series",
    "sources/outline/volumes",
    "sources/outline/arcs",
    "sources/outline/maps",
    "sources/outline/chapters",
    "chapters/drafts",
    "chapters/approved",
    "artifacts/plans",
    "artifacts/context",
    "artifacts/reviews",
    "artifacts/fix-proposals",
    "artifacts/fix-logs",
    "artifacts/builds",
    "analysis/quality",
    "analysis/reader",
    "analysis/impact",
    "analysis/learning",
    "analysis/design",
    "analysis/outline",
    "analysis/writing-strategy",
    "analysis/style",
    "summaries/chapters",
    "summaries/volumes",
    "summaries/arcs",
    "memory/project/reference-learning",
    "memory/project/review-feedback",
    "memory/project/style-library",
    "learning/candidates",
    "learning/candidates/style-profiles",
    "learning/candidates/style-archetypes",
    "runtime/sessions",
    "runtime/task-packets",
    "runtime/context",
    "runtime/reviews",
    "runtime/reader-panels",
    "runtime/indexes",
    "runtime/learning",
    "runtime/design",
    "runtime/outline",
    "runtime/outline/templates",
    "runtime/writing-strategies",
    "runtime/policies",
    "tasks/backlog",
    "tasks/ready",
    "tasks/claimed",
    "tasks/running",
    "tasks/submitted",
    "tasks/reviewing",
    "tasks/passed",
    "tasks/completed",
    "tasks/failed",
    "tasks/archive",
    "tasks/goals",
    "operations",
    "audit",
    "versions/snapshots",
    "publish/staging",
    "overrides",
    "metrics",
    "lifecycle",
    "lifecycle/design",
    "lifecycle/outline",
    "operations/design",
    "operations/outline",
    "project",
]
ALLOWED_TOP_LEVEL = {
    "AGENTS.md", "PROJECT_LAYOUT.yaml", "project.yaml", ".gitignore",
    "NKB", "sources", "chapters", "artifacts", "analysis", "memory",
    "learning", "runtime", "tasks", "operations", "audit", "versions",
    "publish", "overrides", "metrics", "lifecycle", "project", "summaries", "handoffs",
    "canonical_manifest.yaml",
    # create 事务式安装（render/init_*）生成的标准顶层产物，需纳入严格目录契约
    "checkpoints", "config", "indexes", "planning", "sessions",
    "deployment-manifest.yaml", "project.lock.yaml",
}
STORAGE = {
    "raw_reference_books": "sources/references/inbox/",
    "reference_manifests": "sources/references/manifests/",
    "learning_candidates": "learning/candidates/",
    "design_intake": "sources/design/_intake/",
    "design_candidates": "sources/design/_candidates/",
    "design_analysis": "analysis/design/",
    "design_lifecycle": "lifecycle/design/",
    "outline_intake": "sources/outline/_intake/",
    "outline_series": "sources/outline/series/",
    "outline_volumes": "sources/outline/volumes/",
    "outline_arcs": "sources/outline/arcs/",
    "outline_maps": "sources/outline/maps/",
    "outline_chapter_plans": "sources/outline/chapters/",
    "outline_analysis": "analysis/outline/",
    "writing_strategy_analysis": "analysis/writing-strategy/",
    "writing_strategies": "runtime/writing-strategies/",
    "outline_operations": "operations/outline/",
    "project_learning": "memory/project/",
    "writing_drafts": "chapters/drafts/",
    "approved_chapters": "chapters/approved/",
    "plans": "artifacts/plans/",
    "contexts": "artifacts/context/",
    "reviews": "artifacts/reviews/",
    "fix_logs": "artifacts/fix-logs/",
    "generated_runtime": "runtime/",
    "task_records": "tasks/",
    "conversation_requests": "tasks/goals/",
    "operation_manifests": "operations/",
    "audit_records": "audit/",
    "summaries": "summaries/",
    "version_snapshots": "versions/snapshots/",
    "style_profiles": "learning/candidates/style-profiles/",
    "style_archetypes": "learning/candidates/style-archetypes/",
    "style_analysis": "analysis/style/",
    "style_library": "memory/project/style-library/",
    "style_guidance": "runtime/learning/style-guidance.yaml",
}


def is_strict(project_root):
    return os.path.isfile(os.path.join(project_root, "PROJECT_LAYOUT.yaml"))


def is_style_strict(project_root):
    """Return true only for projects explicitly provisioned as strict-v2."""
    marker_path = os.path.join(project_root, "PROJECT_LAYOUT.yaml")
    if not os.path.isfile(marker_path):
        return False
    marker = _gov.load_yaml(marker_path) or {}
    style = marker.get("style_system") or {}
    return (
        style.get("enabled") is True
        and style.get("enforcement_profile") == STYLE_ENFORCEMENT_VERSION
        and style.get("full_chapter_chain_required") is True
    )


def scaffold_layout(project_root, genre):
    for rel in REQUIRED_DIRS:
        os.makedirs(os.path.join(project_root, rel), exist_ok=True)
    marker = {
        "schema": "project-layout@2.0.0",
        "layout_version": LAYOUT_VERSION,
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "genre": genre,
        "strict": True,
        "existing_project_migration_required": False,
        "task_system": {
            "enforcement_mode": "strict",
            "no_task_no_write": True,
            "session_required": True,
        },
        "style_system": {
            "enabled": True,
            "enforcement_profile": STYLE_ENFORCEMENT_VERSION,
            "full_chapter_chain_required": True,
            "broker_fail_closed": True,
        },
        "review": {
            "reader_panel_required": True,
            "feedback_to_writing_required": True,
            "human_feedback_supported": True,
            "human_feedback_required_at": [
                "pilot", "volume_end", "paid_boundary", "major_revision"],
        },
        "learning": {
            "reference_candidates_project_scoped": True,
            "raw_text_copy_forbidden": True,
            "genre_global_promotion_governed": True,
        },
        "storage": STORAGE,
        "required_directories": REQUIRED_DIRS,
        "allowed_top_level": sorted(ALLOWED_TOP_LEVEL),
    }
    _gov.dump_yaml(os.path.join(project_root, "PROJECT_LAYOUT.yaml"), marker)
    _gov.dump_yaml(os.path.join(
        project_root, "runtime", "learning",
        "broker-deployment.yaml"), {
            "schema": "style-broker-deployment@1.0.0",
            "deployment_state": "BLOCKED_NOT_DEPLOYED",
            "reason": (
                "Windows service identities and NTFS ACL require "
                "administrator-approved deployment"),
            "deployment_tool":
                "scripts/logs/deploy_broker_windows.ps1",
            "strict_writes_fail_closed": True,
        })
    agents = """# Single-Agent Execution Policy

（单 Agent 串行执行；禁止子 Agent、委派与并行 Agent。以下规则覆盖会话/任务/编排器/工具四层。）

1. 对话中的“写 N 章 / 审查第 A-B 章”等请求必须先执行 `platform task dispatch --request ...`，生成 Goal、Task 和 Task Packet 后才能工作。
2. 所有写入必须关联当前 Session 中处于 claimed/running 的 Task。
3. 禁止直接修改 `chapters/approved/`；正式发布只能走 Publish Service。
4. 参考小说原文只放 `sources/references/inbox/`，学习产物不得复制原文。
5. 写作必须读取 `runtime/learning/writing-guidance.yaml`（若存在）。
6. 审查必须完成 Reader Panel，并把 findings 反补进项目写作指导。
7. 文件必须按 `PROJECT_LAYOUT.yaml` 的 storage 映射存放，禁止在根目录随意落文件。
8. 单 Agent 串行执行；禁止子 Agent、委派和并行 Agent。
9. 新项目必须先执行 `platform design prepare`；AI 设计候选通过六视角审查和审批后，
   才允许执行 NKB Genesis，聊天内容不得直接写入 NKB。
10. 用户只提供总章节数时，先执行 `platform outline prepare`；全书章节地图必须完整覆盖，
    每一章都必须具有完整场景级详细章纲并通过可写性和防注水门禁后，才允许写正文。
11. 正文开写前必须执行 `platform craft build`；提交时必须附写作手法执行证据，
    开头、场景手法和结尾与章纲不匹配或近章模板化时不得通过审查。
"""
    with open(os.path.join(project_root, "AGENTS.md"), "w", encoding="utf-8") as stream:
        stream.write(agents)
    gitignore = """# User-provided copyrighted reference originals
sources/references/inbox/*
!sources/references/inbox/README.md

# Regenerable runtime caches
runtime/indexes/
runtime/context/
"""
    with open(os.path.join(project_root, ".gitignore"), "w", encoding="utf-8") as stream:
        stream.write(gitignore)
    readmes = {
        "sources/references/inbox/README.md":
            "# 参考原著投放区\n\n仅放用户合法提供的 TXT/MD 原著；默认不进 Git。\n",
        "sources/references/manifests/README.md":
            "# 参考资料清单\n\n保存哈希、来源标识和学习状态，不复制原文。\n",
        "learning/candidates/README.md":
            "# 学习候选\n\n统计规律和写作/审查候选，未经项目验证不得晋升类型/全局规则。\n",
        "memory/project/review-feedback/README.md":
            "# 审查反补记忆\n\n审查 findings 聚合为下一轮写作约束与回归检查。\n",
        "chapters/drafts/README.md":
            "# 工作草稿\n\n仅 Writer/Fixer 在受控 Task 中写入。\n",
        "chapters/approved/README.md":
            "# 正式章节\n\n仅 Publish Service 写入。\n",
    }
    for rel, content in readmes.items():
        path = os.path.join(project_root, rel)
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(content)
    return os.path.join(project_root, "PROJECT_LAYOUT.yaml")


def validate(project_root):
    if not is_strict(project_root):
        return {
            "gate": {"decision": "proceed",
                     "reasons": ["legacy project: 未启用严格目录契约，按用户要求不迁移"]},
            "composite": {"health": 100},
            "response": {"strict": False, "missing": [], "unexpected": []},
        }
    marker = _gov.load_yaml(
        os.path.join(project_root, "PROJECT_LAYOUT.yaml")) or {}
    required = marker.get("required_directories") or REQUIRED_DIRS
    allowed = set(marker.get("allowed_top_level") or ALLOWED_TOP_LEVEL)
    missing = [
        rel for rel in required
        if not os.path.isdir(os.path.join(project_root, rel))
    ]
    unexpected = [
        name for name in os.listdir(project_root)
        if name not in allowed
    ]
    errors = []
    if marker.get("schema") != "project-layout@2.0.0":
        errors.append("PROJECT_LAYOUT schema/version 非 2.0.0")
    if marker.get("strict") is not True:
        errors.append("strict 未启用")
    if missing:
        errors.append("缺必需目录: %s" % missing)
    if unexpected:
        errors.append("根目录存在未登记文件/目录: %s" % unexpected)
    decision = "block" if errors else "proceed"
    return {
        "gate": {"decision": decision, "reasons": errors},
        "composite": {"health": max(0, 100 - len(errors) * 25)},
        "response": {
            "strict": True,
            "layout_version": marker.get("layout_version"),
            "missing": missing,
            "unexpected": unexpected,
        },
    }


def main():
    parser = argparse.ArgumentParser(prog="layout")
    sub = parser.add_subparsers(dest="action", required=True)
    check = sub.add_parser("validate")
    check.add_argument("--project-root", required=True)
    args = parser.parse_args()
    report = validate(args.project_root)
    print("layout: %s strict=%s missing=%d unexpected=%d" % (
        report["gate"]["decision"], report["response"]["strict"],
        len(report["response"]["missing"]),
        len(report["response"]["unexpected"])))
    for reason in report["gate"]["reasons"]:
        print("  - %s" % reason)
    if report["gate"]["decision"] == "block":
        sys.exit(1)


if __name__ == "__main__":
    main()
