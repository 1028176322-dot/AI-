# -*- coding: utf-8 -*-
"""Governed AI design expansion for new projects.

This layer turns a user's free-form direction into an inspiration brief,
autonomy policy, design gap matrix and generation plan. The conversational AI
creates full design candidates from that plan; this module validates, reviews,
approves and promotes those candidates before NKB Genesis may run.
"""
import argparse
import datetime
import os
import re
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_ROOT = os.path.dirname(HERE)
for child in os.listdir(SCRIPTS_ROOT):
    path = os.path.join(SCRIPTS_ROOT, child)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

import _gov
import outline_governance


DOMAIN_REQUIREMENTS = [
    {"domain": "story_core", "types": ["story_core"], "minimum": 1,
     "purpose": "故事承诺、主题、核心冲突与终局方向"},
    {"domain": "world_and_canon", "types": ["world", "canon_rule"], "minimum": 3,
     "purpose": "第一卷必需世界边界与不可变规则"},
    {"domain": "characters", "types": ["character"], "minimum": 3,
     "purpose": "主角、第一阶段对手与核心关系人物"},
    {"domain": "organizations", "types": ["faction", "organization"], "minimum": 1,
     "purpose": "第一卷主要势力及目标关系"},
    {"domain": "locations", "types": ["location"], "minimum": 2,
     "purpose": "开篇活动区与第一卷关键地点"},
    {"domain": "assets_and_abilities", "types": ["item", "ability"], "minimum": 2,
     "purpose": "初始资产、能力、代价与限制"},
    {"domain": "conflict_system", "types": ["conflict"], "minimum": 3,
     "purpose": "内外部冲突和可持续升级来源"},
    {"domain": "arcs", "types": ["arc"], "minimum": 1,
     "purpose": "主角多维成长弧"},
    {"domain": "information_design", "types": ["foreshadow"], "minimum": 3,
     "purpose": "核心真相、伏笔与回收窗口"},
    {"domain": "reader_state", "types": ["reader_state"], "minimum": 1,
     "purpose": "读者初始已知、未知与错误预期"},
    {"domain": "initial_state", "types": ["world_state"], "minimum": 1,
     "purpose": "开篇世界状态及其来源"},
    {"domain": "terminology", "types": ["terminology"], "minimum": 5,
     "purpose": "核心专名、标准写法与禁用混写"},
    {"domain": "outline", "types": ["__outline__"], "minimum": 3,
     "purpose": "全书方向、第一卷结构与前三章详细计划"},
]

AUTONOMY = {
    "conservative": {
        "delegated_domains": ["terminology", "locations"],
        "author_decision_domains": [
            "story_core", "world_and_canon", "characters", "organizations",
            "assets_and_abilities", "conflict_system", "arcs",
            "information_design", "reader_state", "initial_state", "outline",
        ],
        "impact_requires_author": ["medium", "high", "fatal"],
    },
    "balanced": {
        "delegated_domains": [
            "locations", "organizations", "terminology",
            "assets_and_abilities", "initial_state",
        ],
        "author_decision_domains": [
            "story_core", "world_and_canon", "characters",
            "conflict_system", "arcs", "information_design", "reader_state",
            "outline",
        ],
        "impact_requires_author": ["high", "fatal"],
    },
    "autonomous": {
        "delegated_domains": [
            item["domain"] for item in DOMAIN_REQUIREMENTS
            if item["domain"] not in ("story_core", "world_and_canon")
        ],
        "author_decision_domains": ["story_core", "world_and_canon"],
        "impact_requires_author": ["fatal"],
    },
}

REVIEW_LENSES = [
    "consistency", "writeability", "character_drive", "reader_value",
    "long_form_capacity", "originality",
]


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _load(path):
    return _gov.load_yaml(path) if os.path.isfile(path) else {}


def _project(project_root):
    data = _load(os.path.join(project_root, "project.yaml")) or {}
    body = data.get("project") or data
    return body.get("id"), body.get("name"), body.get("type")


def _ensure_dirs(project_root):
    for rel in (
            "sources/design/_intake", "sources/design/_candidates",
            "analysis/design", "runtime/design", "lifecycle/design",
            "operations/design"):
        os.makedirs(os.path.join(project_root, rel), exist_ok=True)


def _sentences(text):
    return [
        item.strip(" \t\r\n。；;")
        for item in re.split(r"[。！？!?\n；;]+", str(text or ""))
        if item.strip(" \t\r\n。；;")
    ]


def prepare(project_root, raw_direction, title=None, genre=None,
            mode="balanced", source="user_conversation",
            total_chapters=None):
    """Create the governed inputs the AI needs for serial design expansion."""
    if mode not in AUTONOMY:
        raise ValueError("autonomy mode must be one of %s" % sorted(AUTONOMY))
    _ensure_dirs(project_root)
    project_id, project_name, project_genre = _project(project_root)
    if not project_id:
        raise ValueError("project.yaml missing project.id")
    parts = _sentences(raw_direction)
    forbidden = [
        item for item in parts
        if any(word in item for word in (
            "不要", "禁止", "不能", "不允许", "避免", "拒绝"))
    ]
    preferences = [
        item for item in parts
        if any(word in item for word in (
            "希望", "想要", "偏", "喜欢", "倾向", "最好"))
        and item not in forbidden
    ]
    locked = [
        item for item in parts
        if item not in forbidden and item not in preferences
    ]
    total_chapters = (
        int(total_chapters) if total_chapters is not None
        else outline_governance.extract_total_chapters(raw_direction))
    brief = {
        "inspiration_brief": {
            "schema": "design-expansion@1.0.0",
            "project_id": project_id,
            "title": title or project_name or "未命名项目",
            "genre": genre or project_genre or "unspecified",
            "raw_direction": raw_direction,
            "locked_facts": locked,
            "preferences": preferences,
            "forbidden": forbidden,
            "open_questions": [
                "故事持续向读者兑现的核心体验是什么？",
                "主角最不可妥协的价值观与最大恐惧是什么？",
                "第一卷结束时必须发生哪项不可逆变化？",
                "核心真相与终局方向分别是什么？",
            ],
            "autonomy_mode": mode,
            "constraints": {
                "total_chapters": total_chapters,
                "outline_detail_policy":
                    "full_chapter_map_plus_full_detailed_chapter_plans",
            },
            "reference_profiles": [],
            "source": {
                "type": source,
                "captured_at": _now(),
                "approval_status": "user_direction",
            },
            "status": "structured",
        },
    }
    policy_data = AUTONOMY[mode]
    policy = {
        "autonomy_policy": {
            "schema": "design-expansion@1.0.0",
            "project_id": project_id,
            "mode": mode,
            "delegated_domains": policy_data["delegated_domains"],
            "author_decision_domains":
                policy_data["author_decision_domains"],
            "impact_requires_author":
                policy_data["impact_requires_author"],
            "default_candidate_status": "pending_review",
            "rules": [
                "用户锁定事实不得由 AI 覆盖",
                "高于授权影响等级的候选必须进入作者决策包",
                "参考作品只允许学习方法，不得复制表达、专名或独特情节组合",
                "任何 AI 补充必须先进入 design candidate，不得直接写 NKB",
            ],
            "granted_at": _now(),
            "grant_source": source,
        },
    }
    brief_path = os.path.join(
        project_root, "sources", "design", "_intake",
        "inspiration-brief.yaml")
    policy_path = os.path.join(
        project_root, "sources", "design", "_intake",
        "autonomy-policy.yaml")
    _gov.dump_yaml(brief_path, brief)
    _gov.dump_yaml(policy_path, policy)
    outline_outputs = {}
    if total_chapters is not None:
        outline_outputs = outline_governance.prepare(
            project_root, total_chapters)
    gap_path, matrix = build_gap_matrix(project_root)
    packet_dir = os.path.join(
        project_root, "runtime", "design", "domain-packets")
    os.makedirs(packet_dir, exist_ok=True)
    domain_packets = {}
    blocking = set(
        matrix["design_gap_matrix"]["blocking_gaps"])
    for index, item in enumerate(DOMAIN_REQUIREMENTS):
        if item["domain"] not in blocking:
            continue
        packet_path = os.path.join(
            packet_dir, "%02d-%s.yaml" % (
                index + 1, item["domain"]))
        is_outline = item["domain"] == "outline"
        instructions = [
            "先服从 user locked facts 和 forbidden，再补充未定义细节",
            "明确设计理由、影响、依赖、冲突和是否需用户决定",
            "参考作品只学习方法，不复制表达、专名和独特情节组合",
            "禁止 TBD、待定、以后再说等占位内容",
        ]
        if is_outline:
            instructions.extend([
                "读取 runtime/outline/generation-plan.yaml，严格按总纲、卷纲、剧情弧、章节地图、滚动章纲顺序生成",
                "全书每章必须在章节地图中出现一次，且具有剧情进展、读者收益、状态变化和结尾承诺",
                "全书每一章都生成同等级场景级详细章纲；可以分批生成，但禁止以未来章节为由降低细化程度",
                "大纲文件先标记 candidate，设计审批通过后由平台统一晋升",
            ])
        else:
            instructions.extend([
                "只定义第一卷会使用或不提前定义就会矛盾的 minimum viable 设计",
                "每个设计实体生成独立 design_candidate 文件",
            ])
        _gov.dump_yaml(packet_path, {
            "design_domain_packet": {
                "schema": "design-domain-packet@1.0.0",
                "project_id": project_id,
                "domain": item["domain"],
                "purpose": item["purpose"],
                "required_document_types": item["types"],
                "minimum_approved_documents": item["minimum"],
                "inputs": {
                    "inspiration_brief": os.path.relpath(
                        brief_path, project_root).replace("\\", "/"),
                    "autonomy_policy": os.path.relpath(
                        policy_path, project_root).replace("\\", "/"),
                    "reference_guidance":
                        "runtime/learning/reference-guidance.yaml",
                },
                "instructions": instructions,
                "quality_checks": [
                    "能产生具体场景",
                    "能推动人物主动选择",
                    "对读者承诺有可验证贡献",
                    "与已批准设计不存在冲突",
                    "具备限制、代价或反作用，避免万能设定",
                ],
                "output_contract": (
                    "core/contracts/outline.schema.yaml"
                    if is_outline else
                    "core/contracts/design-expansion.schema.yaml#design_candidate"),
                "output_directory": (
                    "sources/outline/" if is_outline
                    else "sources/design/_candidates/"),
            },
        })
        domain_packets[item["domain"]] = os.path.relpath(
            packet_path, project_root).replace("\\", "/")
    plan = {
        "generation_plan": {
            "schema": "design-generation-plan@1.0.0",
            "project_id": project_id,
            "created_at": _now(),
            "execution_mode": "single_agent_sequential",
            "inputs": {
                "inspiration_brief": os.path.relpath(
                    brief_path, project_root).replace("\\", "/"),
                "autonomy_policy": os.path.relpath(
                    policy_path, project_root).replace("\\", "/"),
                "gap_matrix": os.path.relpath(
                    gap_path, project_root).replace("\\", "/"),
                "reference_guidance":
                    "runtime/learning/reference-guidance.yaml",
            },
            "steps": [
                {
                    "order": index + 1,
                    "domain": item["domain"],
                    "purpose": item["purpose"],
                    "minimum": item["minimum"],
                    "domain_packet": domain_packets.get(item["domain"]),
                    "output": (
                        "sources/outline/<level>/<ID>.yaml"
                        if item["domain"] == "outline"
                        else "sources/design/_candidates/<CAND-ID>.yaml"),
                }
                for index, item in enumerate(DOMAIN_REQUIREMENTS)
                if item["domain"] in matrix["design_gap_matrix"][
                    "blocking_gaps"]
            ],
            "candidate_contract":
                "core/contracts/design-expansion.schema.yaml",
            "quality_bar": {
                "review_lenses": REVIEW_LENSES,
                "minimum_lens_score": 75,
                "minimum_confidence": 0.65,
                "fatal_findings": 0,
                "maximum_author_decisions_per_batch": 15,
            },
            "completion_rule":
                "所有 gap ready、六视角设计审查通过、审批包 gate=proceed",
        },
    }
    plan_path = os.path.join(
        project_root, "runtime", "design", "generation-plan.yaml")
    _gov.dump_yaml(plan_path, plan)
    outputs = {
        "brief": brief_path,
        "autonomy_policy": policy_path,
        "gap_matrix": gap_path,
        "generation_plan": plan_path,
    }
    outputs.update({
        "outline_%s" % name: path
        for name, path in outline_outputs.items()
    })
    return outputs


def _scan_design_documents(project_root):
    docs = []
    for rel_root in ("sources/design", "sources/canon"):
        root = os.path.join(project_root, rel_root)
        if not os.path.isdir(root):
            continue
        for directory, dirs, files in os.walk(root):
            dirs[:] = [name for name in dirs if not name.startswith("_")]
            for filename in files:
                if not filename.lower().endswith((".yaml", ".yml")):
                    continue
                path = os.path.join(directory, filename)
                data = _load(path) or {}
                document = data.get("document")
                if isinstance(document, dict):
                    docs.append({
                        "path": path,
                        "type": document.get("type"),
                        "status": document.get("status"),
                        "id": document.get("id"),
                    })
    return docs


def _outline_count(project_root):
    root = os.path.join(project_root, "sources", "outline")
    count = 0
    if os.path.isdir(root):
        for directory, _, files in os.walk(root):
            count += sum(
                name.lower().endswith((".yaml", ".yml", ".md"))
                for name in files)
    return count


def build_gap_matrix(project_root):
    _ensure_dirs(project_root)
    project_id, _, _ = _project(project_root)
    docs = _scan_design_documents(project_root)
    domains = []
    blocking = []
    for spec in DOMAIN_REQUIREMENTS:
        if "__outline__" in spec["types"]:
            count = _outline_count(project_root)
            outline_report = outline_governance.validate_project(
                project_root, write=False, require_approved=False)
            approved = (
                spec["minimum"]
                if outline_report["outline_validation"]["gate"][
                    "decision"] == "proceed" else 0)
        else:
            matches = [
                item for item in docs if item["type"] in spec["types"]]
            count = len(matches)
            approved = sum(
                item["status"] == "approved" for item in matches)
        if approved >= spec["minimum"]:
            status = "ready"
        elif count:
            status = "partial"
        else:
            status = "missing"
        if status != "ready":
            blocking.append(spec["domain"])
        domains.append({
            "domain": spec["domain"],
            "purpose": spec["purpose"],
            "required_types": spec["types"],
            "minimum": spec["minimum"],
            "found": count,
            "approved": approved,
            "status": status,
        })
    matrix = {
        "design_gap_matrix": {
            "schema": "design-expansion@1.0.0",
            "project_id": project_id,
            "generated_at": _now(),
            "domains": domains,
            "blocking_gaps": blocking,
            "gate": "block" if blocking else "proceed",
        },
    }
    path = os.path.join(
        project_root, "analysis", "design", "DESIGN_GAP_MATRIX.yaml")
    _gov.dump_yaml(path, matrix)
    return path, matrix


def _candidate_schema():
    platform_root = _gov.find_platform_root()
    return _load(os.path.join(
        platform_root, "core", "contracts",
        "design-expansion.schema.yaml")) or {}


def _design_schema():
    platform_root = _gov.find_platform_root()
    return _load(os.path.join(
        platform_root, "core", "contracts",
        "design-source.schema.yaml")) or {}


def _validate_proposal(proposal, errors):
    if not isinstance(proposal, dict):
        errors.append("proposal must be a complete design-source mapping")
        return
    document = proposal.get("document")
    if not isinstance(document, dict):
        errors.append("proposal.document is required")
        return
    for field in (
            "id", "type", "title", "status", "version",
            "updated_at", "owner", "project_id"):
        if document.get(field) in (None, ""):
            errors.append("proposal.document missing %s" % field)
    spec = (_design_schema().get("type_required") or {}).get(
        document.get("type"))
    if not spec:
        errors.append(
            "proposal document.type has no design-source rule: %s" %
            document.get("type"))
        return
    section = spec.get("section")
    body = proposal.get(section)
    if not isinstance(body, dict):
        errors.append("proposal.%s must be a mapping" % section)
        return
    for field in spec.get("required_fields") or []:
        if body.get(field) in (None, ""):
            errors.append("proposal.%s missing %s" % (section, field))


def validate_candidate(path, project_root):
    data = _load(path) or {}
    candidate = data.get("design_candidate")
    errors = []
    schema = _candidate_schema()
    spec = schema.get("design_candidate") or {}
    if not isinstance(candidate, dict):
        return False, ["design_candidate mapping is required"], {}
    for field in spec.get("required") or []:
        if candidate.get(field) is None:
            errors.append("missing field: %s" % field)
    for field, enum_name in (
            ("authority_class", "authority_class_enum"),
            ("impact", "impact_enum"),
            ("status", "status_enum")):
        if candidate.get(field) not in (spec.get(enum_name) or []):
            errors.append("%s is invalid" % field)
    project_id, _, _ = _project(project_root)
    if candidate.get("project_id") != project_id:
        errors.append("project_id mismatch")
    target = str(candidate.get("target_path") or "").replace("\\", "/")
    if (not target.startswith(("sources/design/", "sources/canon/"))
            or ".." in target.split("/")):
        errors.append("target_path must stay within sources/design or sources/canon")
    originality = candidate.get("originality")
    if not isinstance(originality, dict):
        errors.append("originality must be a mapping")
    else:
        for field in spec.get("originality_required") or []:
            if originality.get(field) is None:
                errors.append("originality missing %s" % field)
        if originality.get("copied_expression") is True:
            errors.append("copied_expression must be false")
        if originality.get("copied_proper_nouns"):
            errors.append("copied_proper_nouns must be empty")
    policy = (_load(os.path.join(
        project_root, "sources", "design", "_intake",
        "autonomy-policy.yaml")) or {}).get("autonomy_policy") or {}
    if (candidate.get("impact") in (
            policy.get("impact_requires_author") or [])
            and candidate.get("authority_class") == "delegated_approved"):
        errors.append("impact level requires author decision")
    _validate_proposal(candidate.get("proposal"), errors)
    return not errors, errors, candidate


def validate_candidates(project_root):
    root = os.path.join(
        project_root, "sources", "design", "_candidates")
    results = []
    if os.path.isdir(root):
        for filename in sorted(os.listdir(root)):
            if not filename.lower().endswith((".yaml", ".yml")):
                continue
            path = os.path.join(root, filename)
            ok, errors, candidate = validate_candidate(path, project_root)
            results.append({
                "file": os.path.relpath(path, project_root).replace("\\", "/"),
                "id": candidate.get("id"),
                "valid": ok,
                "errors": errors,
            })
    report = {
        "candidate_validation": {
            "checked_at": _now(),
            "files": results,
            "valid": sum(item["valid"] for item in results),
            "invalid": sum(not item["valid"] for item in results),
            "gate": (
                "proceed" if results and all(
                    item["valid"] for item in results) else "block"),
        },
    }
    path = os.path.join(
        project_root, "analysis", "design",
        "CANDIDATE_VALIDATION.yaml")
    _gov.dump_yaml(path, report)
    return path, report


def prepare_review(project_root):
    project_id, _, _ = _project(project_root)
    report = {
        "design_review": {
            "schema": "design-review@1.0.0",
            "project_id": project_id,
            "reviewed_at": "",
            "reviewer": "",
            "lenses": {
                lens: {
                    "score": None,
                    "observation": "",
                    "evidence": [],
                    "issues": [],
                    "recommendations": [],
                    "confidence": None,
                }
                for lens in REVIEW_LENSES
            },
            "fatal_findings": [],
            "cross_domain_conflicts": [],
            "gate": {"decision": "block", "reasons": ["awaiting review"]},
        },
    }
    path = os.path.join(
        project_root, "analysis", "design", "DESIGN_REVIEW.yaml")
    _gov.dump_yaml(path, report)
    return path


def validate_review(path):
    data = _load(path) or {}
    report = data.get("design_review")
    errors = []
    if not isinstance(report, dict):
        return False, ["design_review mapping is required"], {}
    lenses = report.get("lenses")
    if not isinstance(lenses, dict):
        return False, ["lenses mapping is required"], report
    for lens in REVIEW_LENSES:
        item = lenses.get(lens)
        if not isinstance(item, dict):
            errors.append("missing lens: %s" % lens)
            continue
        for field in (
                "score", "observation", "evidence", "issues",
                "recommendations", "confidence"):
            if item.get(field) is None or (
                    field in ("observation", "evidence")
                    and item.get(field) in ("", [])):
                errors.append("%s missing %s" % (lens, field))
        score = item.get("score")
        confidence = item.get("confidence")
        if not isinstance(score, (int, float)) or not 0 <= score <= 100:
            errors.append("%s score must be 0..100" % lens)
        elif score < 75:
            errors.append("%s score below 75" % lens)
        if (not isinstance(confidence, (int, float))
                or not 0 <= confidence <= 1):
            errors.append("%s confidence must be 0..1" % lens)
        elif confidence < 0.65:
            errors.append("%s confidence below 0.65" % lens)
    if report.get("fatal_findings"):
        errors.append("fatal_findings must be empty")
    decision = (report.get("gate") or {}).get("decision")
    if not errors and decision != "proceed":
        errors.append("complete passing review must set gate.decision=proceed")
    if errors and decision == "proceed":
        errors.append("gate cannot proceed with review errors")
    return not errors, errors, report


def build_approval_packet(project_root):
    _ensure_dirs(project_root)
    project_id, _, _ = _project(project_root)
    policy = (_load(os.path.join(
        project_root, "sources", "design", "_intake",
        "autonomy-policy.yaml")) or {}).get("autonomy_policy") or {}
    delegated_domains = set(policy.get("delegated_domains") or [])
    author_impacts = set(policy.get("impact_requires_author") or [])
    delegated, decisions, rejected, conflicts = [], [], [], []
    root = os.path.join(
        project_root, "sources", "design", "_candidates")
    if os.path.isdir(root):
        for filename in sorted(os.listdir(root)):
            if not filename.lower().endswith((".yaml", ".yml")):
                continue
            path = os.path.join(root, filename)
            ok, errors, candidate = validate_candidate(path, project_root)
            cid = candidate.get("id") or filename
            entry = {
                "id": cid,
                "domain": candidate.get("domain"),
                "impact": candidate.get("impact"),
                "summary": candidate.get("rationale"),
                "candidate_file": os.path.relpath(
                    path, project_root).replace("\\", "/"),
            }
            if not ok:
                entry["errors"] = errors
                conflicts.append(entry)
            elif candidate.get("status") == "rejected":
                rejected.append(entry)
            elif (candidate.get("authority_class") in (
                    "user_locked", "author_approved", "delegated_approved")
                  or candidate.get("status") in ("approved", "promoted")):
                delegated.append(entry)
            elif (candidate.get("requires_user_decision") is True
                  or candidate.get("impact") in author_impacts
                  or candidate.get("domain") not in delegated_domains):
                decisions.append(entry)
            else:
                delegated.append(entry)
    if conflicts:
        gate = "block"
    elif decisions:
        gate = "awaiting_author"
    elif delegated:
        gate = "proceed"
    else:
        gate = "block"
    packet = {
        "approval_packet": {
            "schema": "design-expansion@1.0.0",
            "project_id": project_id,
            "created_at": _now(),
            "autonomy_mode": policy.get("mode"),
            "delegated_approvals": delegated,
            "author_decisions": decisions,
            "rejected_candidates": rejected,
            "unresolved_conflicts": conflicts,
            "gate": gate,
        },
    }
    path = os.path.join(
        project_root, "lifecycle", "design", "APPROVAL_PACKET.yaml")
    _gov.dump_yaml(path, packet)
    return path, packet


def apply_author_decisions(project_root, decisions_path):
    """Apply an explicit user decision file to the concentrated approval packet."""
    decisions = _load(decisions_path) or {}
    body = decisions.get("author_decisions") or {}
    if body.get("explicit_user_approval") is not True:
        raise ValueError("author decision requires explicit_user_approval=true")
    approved_ids = set(body.get("approved") or [])
    rejected_ids = set(body.get("rejected") or [])
    if approved_ids & rejected_ids:
        raise ValueError("a candidate cannot be both approved and rejected")
    packet_path = os.path.join(
        project_root, "lifecycle", "design", "APPROVAL_PACKET.yaml")
    packet_data = _load(packet_path) or {}
    packet = packet_data.get("approval_packet") or {}
    pending = packet.get("author_decisions") or []
    known = {item.get("id") for item in pending}
    unknown = (approved_ids | rejected_ids) - known
    if unknown:
        raise ValueError("unknown author decision ids: %s" % sorted(unknown))
    remaining = []
    for entry in pending:
        cid = entry.get("id")
        if cid in approved_ids:
            approved_entry = dict(entry)
            approved_entry["approval_source"] = "explicit_user_decision"
            approved_entry["decided_by"] = body.get("decided_by", "user")
            approved_entry["decided_at"] = _now()
            packet.setdefault("delegated_approvals", []).append(
                approved_entry)
            candidate_path = os.path.join(
                project_root,
                entry["candidate_file"].replace("/", os.sep))
            candidate_data = _load(candidate_path) or {}
            candidate = candidate_data.get("design_candidate") or {}
            candidate["authority_class"] = "author_approved"
            candidate["status"] = "approved"
            candidate["approval_evidence"] = os.path.relpath(
                decisions_path, project_root).replace("\\", "/")
            _gov.dump_yaml(candidate_path, candidate_data)
        elif cid in rejected_ids:
            rejected_entry = dict(entry)
            rejected_entry["rejection_source"] = "explicit_user_decision"
            packet.setdefault("rejected_candidates", []).append(
                rejected_entry)
            candidate_path = os.path.join(
                project_root,
                entry["candidate_file"].replace("/", os.sep))
            candidate_data = _load(candidate_path) or {}
            candidate = candidate_data.get("design_candidate") or {}
            candidate["status"] = "rejected"
            candidate["approval_evidence"] = os.path.relpath(
                decisions_path, project_root).replace("\\", "/")
            _gov.dump_yaml(candidate_path, candidate_data)
        else:
            remaining.append(entry)
    packet["author_decisions"] = remaining
    if packet.get("unresolved_conflicts"):
        packet["gate"] = "block"
    elif remaining:
        packet["gate"] = "awaiting_author"
    elif packet.get("delegated_approvals"):
        packet["gate"] = "proceed"
    else:
        packet["gate"] = "block"
    packet["last_author_decision"] = {
        "file": os.path.relpath(
            decisions_path, project_root).replace("\\", "/"),
        "decided_by": body.get("decided_by", "user"),
        "decided_at": _now(),
    }
    _gov.dump_yaml(packet_path, packet_data)
    evidence_path = os.path.join(
        project_root, "lifecycle", "design",
        "AUTHOR_DECISION_EVIDENCE.yaml")
    _gov.dump_yaml(evidence_path, {
        "approval_evidence": {
            "explicit_user_approval": True,
            "source": os.path.relpath(
                decisions_path, project_root).replace("\\", "/"),
            "approved": sorted(approved_ids),
            "rejected": sorted(rejected_ids),
            "recorded_at": _now(),
        },
    })
    return packet_path, evidence_path, packet_data


def _safe_target(project_root, relative):
    relative = str(relative or "").replace("\\", "/")
    if (not relative.startswith(("sources/design/", "sources/canon/"))
            or ".." in relative.split("/")):
        raise ValueError("unsafe design target: %s" % relative)
    root = os.path.abspath(project_root)
    target = os.path.abspath(os.path.join(root, relative))
    if os.path.commonpath([root, target]) != root:
        raise ValueError("design target escapes project")
    return target


def promote(project_root, approval_path=None):
    approval_path = approval_path or os.path.join(
        project_root, "lifecycle", "design", "APPROVAL_PACKET.yaml")
    packet = (_load(approval_path) or {}).get("approval_packet") or {}
    if packet.get("gate") != "proceed":
        raise ValueError("approval packet gate must be proceed")
    promoted = []
    for entry in packet.get("delegated_approvals") or []:
        candidate_path = os.path.join(
            project_root, entry["candidate_file"].replace("/", os.sep))
        ok, errors, candidate = validate_candidate(
            candidate_path, project_root)
        if not ok:
            raise ValueError("%s: %s" % (
                candidate.get("id"), "; ".join(errors)))
        target = _safe_target(project_root, candidate["target_path"])
        if os.path.exists(target):
            existing = _load(target) or {}
            existing_id = (existing.get("document") or {}).get("id")
            proposed_id = (
                (candidate.get("proposal") or {}).get("document") or {}
            ).get("id")
            if existing_id != proposed_id:
                raise ValueError(
                    "target exists with another document id: %s" %
                    candidate["target_path"])
        proposal = dict(candidate["proposal"])
        proposal["document"] = dict(proposal.get("document") or {})
        proposal["document"]["status"] = "approved"
        proposal["document"]["approved_via"] = (
            "delegated:%s" % packet.get("autonomy_mode"))
        proposal["document"]["approved_at"] = _now()
        os.makedirs(os.path.dirname(target), exist_ok=True)
        _gov.dump_yaml(target, proposal)
        data = _load(candidate_path) or {}
        data["design_candidate"]["status"] = "promoted"
        data["design_candidate"]["promoted_at"] = _now()
        _gov.dump_yaml(candidate_path, data)
        promoted.append(candidate["target_path"])
    operation = {
        "operation": {
            "id": "OP-DESIGN-%s" % datetime.datetime.now().strftime(
                "%Y%m%d%H%M%S%f"),
            "type": "design_candidate_promotion",
            "created_at": _now(),
            "approval_packet": os.path.relpath(
                approval_path, project_root).replace("\\", "/"),
            "promoted": promoted,
        },
    }
    operation_path = os.path.join(
        project_root, "operations", "design",
        "DESIGN_PROMOTION-%s.yaml" % datetime.datetime.now().strftime(
            "%Y%m%d%H%M%S%f"))
    _gov.dump_yaml(operation_path, operation)
    build_gap_matrix(project_root)
    return operation_path, promoted


def design_gate(project_root):
    gap_path, gap = build_gap_matrix(project_root)
    approval_path, approval = build_approval_packet(project_root)
    review_path = os.path.join(
        project_root, "analysis", "design", "DESIGN_REVIEW.yaml")
    review_ok, review_errors, _ = validate_review(review_path)
    reasons = []
    if gap["design_gap_matrix"]["gate"] != "proceed":
        reasons.append("design gaps remain")
    if approval["approval_packet"]["gate"] != "proceed":
        reasons.append(
            "approval gate=%s" % approval["approval_packet"]["gate"])
    if not review_ok:
        reasons.append("design review invalid: %s" % "; ".join(
            review_errors[:8]))
    if not reasons:
        try:
            outline_governance.approve_outline(
                project_root,
                approved_by="design-approval-gate",
                evidence=os.path.relpath(
                    approval_path, project_root).replace("\\", "/"))
            gap_path, gap = build_gap_matrix(project_root)
            if gap["design_gap_matrix"]["gate"] != "proceed":
                reasons.append("design gaps remain after outline approval")
        except (OSError, ValueError) as exc:
            reasons.append("outline approval failed: %s" % exc)
    decision = "pass" if not reasons else "block"
    result = {
        "design_approval": {
            "schema": "design-approval@1.0.0",
            "checked_at": _now(),
            "decision": decision,
            "reasons": reasons,
            "evidence": {
                "gap_matrix": os.path.relpath(
                    gap_path, project_root).replace("\\", "/"),
                "design_review": os.path.relpath(
                    review_path, project_root).replace("\\", "/"),
                "approval_packet": os.path.relpath(
                    approval_path, project_root).replace("\\", "/"),
            },
            "genesis_allowed": decision == "pass",
        },
    }
    path = os.path.join(
        project_root, "lifecycle", "design", "DESIGN_APPROVAL.yaml")
    _gov.dump_yaml(path, result)
    return path, result


def main():
    parser = argparse.ArgumentParser(
        prog="platform design",
        description="对话灵感 -> AI 设计候选 -> 审查/审批 -> Genesis 门禁")
    parser.add_argument(
        "action",
        choices=[
            "prepare", "gap", "candidates", "review-prepare",
            "review-check", "approval", "decide", "promote", "gate"])
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--brief", default="")
    parser.add_argument("--title")
    parser.add_argument("--genre")
    parser.add_argument("--total-chapters", type=int)
    parser.add_argument(
        "--mode", default="balanced",
        choices=["conservative", "balanced", "autonomous"])
    parser.add_argument("--report")
    parser.add_argument("--approval-file")
    parser.add_argument("--decisions")
    args = parser.parse_args()
    root = os.path.abspath(args.project_root)
    try:
        if args.action == "prepare":
            if not args.brief.strip():
                raise ValueError("prepare requires --brief")
            outputs = prepare(
                root, args.brief, args.title, args.genre, args.mode,
                total_chapters=args.total_chapters)
            for name, path in outputs.items():
                print("%s: %s" % (name, path))
        elif args.action == "gap":
            path, report = build_gap_matrix(root)
            print("%s gate=%s" % (
                path, report["design_gap_matrix"]["gate"]))
        elif args.action == "candidates":
            path, report = validate_candidates(root)
            print("%s gate=%s" % (
                path, report["candidate_validation"]["gate"]))
            if report["candidate_validation"]["gate"] == "block":
                sys.exit(1)
        elif args.action == "review-prepare":
            print(prepare_review(root))
        elif args.action == "review-check":
            path = args.report or os.path.join(
                root, "analysis", "design", "DESIGN_REVIEW.yaml")
            ok, errors, _ = validate_review(path)
            print("review: %s" % ("PASS" if ok else "BLOCK"))
            for error in errors:
                print("  - %s" % error)
            if not ok:
                sys.exit(1)
        elif args.action == "approval":
            path, report = build_approval_packet(root)
            print("%s gate=%s" % (
                path, report["approval_packet"]["gate"]))
        elif args.action == "decide":
            if not args.decisions:
                raise ValueError("decide requires --decisions")
            packet_path, evidence_path, report = apply_author_decisions(
                root, os.path.abspath(args.decisions))
            print("%s gate=%s" % (
                packet_path,
                report["approval_packet"]["gate"]))
            print("evidence: %s" % evidence_path)
        elif args.action == "promote":
            path, promoted = promote(root, args.approval_file)
            print("%s promoted=%d" % (path, len(promoted)))
        elif args.action == "gate":
            path, report = design_gate(root)
            print("%s decision=%s" % (
                path, report["design_approval"]["decision"]))
            if report["design_approval"]["decision"] != "pass":
                sys.exit(1)
    except (OSError, ValueError) as exc:
        print("ERROR: %s" % exc)
        sys.exit(2)


if __name__ == "__main__":
    main()
