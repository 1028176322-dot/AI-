# -*- coding: utf-8 -*-
"""
候选修订生产者（style-revise，纲要 §2.4 / §2.7，#22 Tier-1 已放行）。

设计要点
--------
- **只写 analysis/style/<chapter>/<task>/revision-candidate.md + revision-result.json**，
  绝不写 chapters/（草稿归 chapters/drafts，候选稿另存，避免覆盖，§2.4）。
- **绑定源草稿哈希**：``source_draft_sha256`` 锚定被修订草稿；若调用时传入的草稿哈希
  与上一份候选不符（草稿被改），新候选标记为 ``stale=True``（草稿变化 → 候选失效，§2.7）。
- **只读源草稿副本**：``ai_revise`` 不修改传入 ``draft_text``。
- 确定性默认修订器：依传入的已批准风格规则做可逆文本变换（如剥离元评论词/填充语），
  并产出 ``changes`` 明细（span / before / after / reason）。真实系统可替换为 LLM 修订，
  接口与「只写 analysis/」约束不变。
- 落盘经 ``authorize(style_revise)`` 授权（路径受 candidate_path_permission 约束）。
- 可选：传入 ``event_log``（Broker 密钥）则追加 WRITE 不可变事件；传入 ``state_machine``
  则推进 ``CANDIDATE_CREATED``（via=style-revise）。两者皆失败安全（缺省不阻断主流程）。
"""
import hashlib
import json
import os
import re
import time

SCHEMA_ID = "style.revision-result"
SCHEMA_VERSION = "1.0.0"

_META_COMMENTARY = re.compile(r"(事实上|可以说|值得注意的是|毋庸置疑|显而易见的是|总而言之|综上所述|坦白说|客观地说)")
_FILLER_PHRASE = re.compile(r"(在这个(时刻|时候|瞬间)|在这个(世界|地方|节点)|一种莫名的|一股莫名)")


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _apply_rule_transforms(draft_text, applied_style_rules):
    """依已批准风格规则做确定性可逆变换，返回 (new_text, changes)。"""
    text = draft_text
    changes = []
    span_seq = 0
    for rule in (applied_style_rules or []):
        kind = rule.get("kind") or rule.get("target")
        if kind in ("meta_commentary", "avoid_meta_commentary"):
            for m in _META_COMMENTARY.finditer(text):
                before = m.group(0)
                after = ""
                text = text.replace(before, after, 1)
                changes.append({
                    "span_id": "rule:%s:%d" % (rule.get("rule_id", "r"), span_seq),
                    "before": before,
                    "after": after,
                    "reason": "strip meta-commentary per %s" % rule.get("rule_id"),
                })
                span_seq += 1
        elif kind in ("filler_phrase", "avoid_filler"):
            for m in _FILLER_PHRASE.finditer(text):
                before = m.group(0)
                after = ""
                text = text.replace(before, after, 1)
                changes.append({
                    "span_id": "rule:%s:%d" % (rule.get("rule_id", "r"), span_seq),
                    "before": before,
                    "after": after,
                    "reason": "strip filler per %s" % rule.get("rule_id"),
                })
                span_seq += 1
    return text, changes


def ai_revise(chapter_id, revision_cycle_id, producer_task_id, draft_text,
              protected_manifest_sha256="", applied_style_rules=None,
              source_draft_sha256=None, previous_result=None, created_at=None):
    """产出候选修订稿 + revision-result 合规 dict。

    ``source_draft_sha256`` 为当前草稿哈希（调用方计算）。若 ``previous_result`` 存在且其
    绑定哈希与当前不符 → ``stale=True``（旧候选已失效）。绝不修改 draft_text。
    """
    draft_copy = draft_text[:]
    draft_sha = _sha256(draft_copy)

    stale = False
    if previous_result is not None:
        prev_src = previous_result.get("source_draft_sha256")
        if prev_src is not None and prev_src != draft_sha:
            stale = True

    candidate_text, changes = _apply_rule_transforms(draft_copy, applied_style_rules)
    candidate_sha = _sha256(candidate_text)

    return {
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "chapter_id": chapter_id,
        "revision_cycle_id": revision_cycle_id,
        "producer_task_id": producer_task_id,
        "task_id": producer_task_id,
        "revision_candidate_ref": "analysis/style/%s/%s/revision-candidate.md"
                                   % (chapter_id, revision_cycle_id),
        "source_draft_sha256": draft_sha,
        "candidate_sha256": candidate_sha,
        "changes": changes,
        "applied_style_rules": [r.get("rule_id") for r in (applied_style_rules or [])],
        "protected_manifest_sha256": protected_manifest_sha256,
        "stale": stale,
        "created_at": created_at if created_at is not None else time.time(),
    }


def validate_revision_result(d):
    errors = []
    required = ["chapter_id", "revision_cycle_id", "producer_task_id",
                "revision_candidate_ref", "source_draft_sha256", "candidate_sha256",
                "changes", "protected_manifest_sha256", "created_at"]
    for k in required:
        if k not in d:
            errors.append("missing field: %s" % k)
    if not isinstance(d.get("changes"), list):
        errors.append("changes must be list")
    return (len(errors) == 0, errors)


def calculate_dir(root, chapter_id, revision_cycle_id):
    return os.path.join(root, "analysis", "style", chapter_id, revision_cycle_id)


def persist(d, root, candidate_text, chapter_id, revision_cycle_id, producer_task_id):
    """落盘候选稿 + revision-result 到 analysis/style。调用方须已完成 authorize(style_revise)。"""
    out_dir = calculate_dir(root, chapter_id, revision_cycle_id)
    os.makedirs(out_dir, exist_ok=True)
    cand_path = os.path.join(out_dir, "revision-candidate.md")
    with open(cand_path, "w", encoding="utf-8") as f:
        f.write(candidate_text)
    res_path = os.path.join(out_dir, "%s.revision-result.json" % producer_task_id)
    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    return {"candidate_path": cand_path, "result_path": res_path}


def read_previous(root, chapter_id, revision_cycle_id):
    """读取该修订周期已有的任一 revision-result（用于 STALE 检测）。"""
    out_dir = calculate_dir(root, chapter_id, revision_cycle_id)
    if not os.path.isdir(out_dir):
        return None
    for fn in os.listdir(out_dir):
        if fn.endswith(".revision-result.json"):
            with open(os.path.join(out_dir, fn), "r", encoding="utf-8") as f:
                return json.load(f)
    return None


def append_write_event(event_log, d, actor_id, task_id):
    """可选：经 Broker 密钥追加 WRITE 不可变事件（仅 Broker 持密钥可成功）。"""
    if event_log is None:
        return None
    return event_log.append(
        "WRITE", actor_id or d.get("producer_task_id"), task_id or d.get("producer_task_id"),
        operation="style_revise",
        resource_refs=[d.get("revision_candidate_ref")],
        result="ok",
        details={"chapter_id": d.get("chapter_id"),
                 "revision_cycle_id": d.get("revision_cycle_id"),
                 "candidate_sha256": d.get("candidate_sha256")})
