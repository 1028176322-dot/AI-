# -*- coding: utf-8 -*-
"""
F1 风格风险诊断（ai-diagnose，只读不改正文，纲要 §2.7 / §2.11，#21 Tier-1 已放行）。

设计要点
--------
- **严格只读**：``ai_diagnose`` 绝不修改传入的 ``draft_text`` / ``nkb_snapshot``，
  只在内部使用副本/派生量做统计，输出一份符合 ``diagnosis.schema.yaml`` 的诊断报告。
- 检测器是**确定性**的（可复现、可测），用于原型：重复开头句、元评论词、填充语、
  高频连接词等 "AI 腔 / 模板味" 信号；真实系统可替换为 LLM 诊断，但接口与只读约束不变。
- 输出经 ``validate_diagnosis`` 校验字段完整性与枚举合法性。
- 报告落盘到 ``analysis/style/<chapter>/<task>/diagnosis.json``（须经 authorize(diagnose) 授权，
  路径由 calculate_path 派生，绝不写 ``chapters/``）。
"""
import hashlib
import json
import os
import re
import time

SCHEMA_ID = "style.diagnosis"
SCHEMA_VERSION = "1.0.0"

VALID_ACTIONS = ("revise", "skip", "human_review")

# 确定性 AI 腔 / 模板味检测信号（原型用）。
_META_COMMENTARY = re.compile(r"(事实上|可以说|值得注意的是|毋庸置疑|显而易见的是|总而言之|综上所述|坦白说|客观地说)")
_FILLER_PHRASE = re.compile(r"(在这个(时刻|时候|瞬间)|在这个(世界|地方|节点)|一种莫名的|一股莫名)")
_HEDGE_OVERUSE = re.compile(r"(可能|也许|似乎|大概|某种程度上|在某种意义上|在一定程度上)")
_CONNECTOR_SPAM = re.compile(r"(而且|并且|同时|此外|然而|于是|因此|所以)(?:[，,])?(?:而且|并且|同时|此外|然而|于是|因此|所以)")

_SENT_SPLIT = re.compile(r"(?<=[。！？！？；\.!?;])")


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _split_sentences(text):
    parts = _SENT_SPLIT.split(text)
    return [p.strip() for p in parts if p.strip()]


def _detect_issues(draft_text):
    """确定性检测，返回 issue_list（元素 {category,span_id,description,severity}）。"""
    issues = []
    sentences = _split_sentences(draft_text)
    total = max(len(sentences), 1)

    # ① 重复开头句（模板化征兆）
    openers = {}
    for s in sentences:
        op = s[:2]
        openers[op] = openers.get(op, 0) + 1
    for op, cnt in openers.items():
        if cnt >= 3 and cnt / total >= 0.15:
            issues.append({
                "category": "repetitive_opener",
                "span_id": "opener:%s" % op,
                "description": "连续 %d 句以「%s」开头（占比 %.0f%%），疑似模板化" % (cnt, op, 100 * cnt / total),
                "severity": "medium",
            })

    # ② 元评论词（"事实上/值得注意的是" 等）
    for m in _META_COMMENTARY.finditer(draft_text):
        issues.append({
            "category": "meta_commentary",
            "span_id": "span:%d" % m.start(),
            "description": "检出元评论词：%s" % m.group(0),
            "severity": "low",
        })

    # ③ 填充语
    for m in _FILLER_PHRASE.finditer(draft_text):
        issues.append({
            "category": "filler_phrase",
            "span_id": "span:%d" % m.start(),
            "description": "检出填充语：%s" % m.group(0),
            "severity": "low",
        })

    # ④ 模糊限定词过载
    hedge = len(_HEDGE_OVERUSE.findall(draft_text))
    if hedge >= 5:
        issues.append({
            "category": "hedge_overuse",
            "span_id": "doc:hedge",
            "description": "模糊限定词出现 %d 次，确定性不足" % hedge,
            "severity": "low",
        })

    # ⑤ 连接词堆叠
    for m in _CONNECTOR_SPAM.finditer(draft_text):
        issues.append({
            "category": "connector_spam",
            "span_id": "span:%d" % m.start(),
            "description": "连接词堆叠：%s" % m.group(0),
            "severity": "medium",
        })
    return issues


def ai_diagnose(chapter_id, revision_cycle_id, task_id, draft_text, nkb_snapshot=None,
                protected_manifest_sha256="", policy=None, diagnosed_at=None):
    """只读诊断：绝不修改 draft_text / nkb_snapshot。

    返回符合 diagnosis.schema.yaml 的 dict。
    """
    # 防御性副本，确保只读（即便调用方后续修改原串也不影响已采样哈希）。
    draft_copy = draft_text[:]
    nkb_copy = None if nkb_snapshot is None else (nkb_snapshot.copy() if isinstance(nkb_snapshot, dict) else nkb_snapshot)

    issues = _detect_issues(draft_copy)
    has_issues = len(issues) > 0
    only_warnings = has_issues and all(i["severity"] == "low" for i in issues)
    severe = any(i["severity"] in ("high",) for i in issues)

    if not has_issues:
        recommended = "skip"
    elif severe:
        recommended = "human_review"
    elif only_warnings:
        recommended = "skip"
    else:
        recommended = "revise"

    # 若 NKB 快照存在，可附加事实一致性提示（原型仅占位，不改正文）。
    nkb_ref = _sha256(json.dumps(nkb_copy, ensure_ascii=False, sort_keys=True)) if nkb_copy is not None else ""

    return {
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "chapter_id": chapter_id,
        "revision_cycle_id": revision_cycle_id,
        "producer_task_id": task_id,
        "task_id": task_id,
        "diagnosed_at": diagnosed_at if diagnosed_at is not None else time.time(),
        "has_issues": has_issues,
        "issue_list": issues,
        "only_warnings": only_warnings,
        "recommended_action": recommended,
        "source_draft_sha256": _sha256(draft_copy),
        "protected_manifest_sha256": protected_manifest_sha256,
        "nkb_snapshot_sha256": nkb_ref,
    }


def validate_diagnosis(d):
    """校验 diagnosis.schema.yaml 必填字段与枚举。返回 (ok, errors)。"""
    errors = []
    required = ["chapter_id", "revision_cycle_id", "producer_task_id", "task_id",
                "diagnosed_at", "has_issues", "issue_list", "only_warnings",
                "recommended_action", "source_draft_sha256", "protected_manifest_sha256"]
    for k in required:
        if k not in d:
            errors.append("missing field: %s" % k)
    if d.get("recommended_action") not in VALID_ACTIONS:
        errors.append("invalid recommended_action: %s" % d.get("recommended_action"))
    if not isinstance(d.get("issue_list"), list):
        errors.append("issue_list must be list")
    for it in d.get("issue_list", []):
        for k in ("category", "span_id", "description", "severity"):
            if k not in it:
                errors.append("issue missing %s" % k)
    return (len(errors) == 0, errors)


def calculate_path(root, chapter_id, task_id):
    """analysis/style/<chapter>/<task>/diagnosis.json（非 chapters/，由 authorize 校验）。"""
    return os.path.join(root, "analysis", "style", chapter_id, task_id, "diagnosis.json")


def persist(d, root, chapter_id, task_id):
    """落盘诊断报告到 analysis/style。调用方须已完成 authorize(diagnose)。"""
    path = calculate_path(root, chapter_id, task_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    return path


def read(root, chapter_id, task_id):
    path = calculate_path(root, chapter_id, task_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
