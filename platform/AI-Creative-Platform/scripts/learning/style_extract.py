# -*- coding: utf-8 -*-
"""
参考风格规则提取（style_extract，纲要 §2.3 / §2.10，#21 Tier-1 已放行）。

本模块是**治理强制层**：在把参考小说转化为 ``style-rule-candidate`` 之前，强制校验
纲要设定的不可违背约束——参考学习**只产** soft 规则，绝不自动成为治理硬规则：

1. ``rule_type`` ∈ {style_preference, style_target, candidate_project_constraint}；
   任何 hard_constraint / governance_constraint **拒绝**（硬约束只能由平台代码定义）。
2. ``source_count`` >= ``minimum_independent_sources`` (3)；单一来源不得主导。
3. 任一来源权重 <= ``max_single_source_weight`` (0.4，固定)。
4. ``confidence`` 必须由**可计算来源**合成（跨章节重复 / 跨来源一致 / 提取器重跑一致 /
   统计检验 / 人工审核），**禁用模型自报**。
5. ``example_rules`` 必须带 ``example_origin`` ∈ {system-generated, user-owned,
   public-domain, licensed}；且**禁止**直接复制参考原句。
6. **绝不把原始 n-gram 写入候选**（指纹比对在别处，本产物只存抽象 value）。

真实系统的 LLM 提取被抽象为可注入的 ``extract_fn``；本模块提供一份**确定性参考实现**
（从来源正文计算可计算风格信号并合成候选），保证测试与早期联调不依赖外部模型。
"""
import hashlib
import json
import os
import re
import time

SCHEMA_ID = "style.rule-candidate"
SCHEMA_VERSION = "1.0.0"

GOVERNANCE = {
    "minimum_independent_sources": 3,
    "recommended_independent_sources": 5,
    "max_single_source_weight": 0.4,
}

ALLOWED_RULE_TYPES = {"style_preference", "style_target", "candidate_project_constraint"}
HARD_RULE_TYPES = {"hard_constraint", "hard_constraints", "governance_constraint",
                   "governance_constraints", "hard_rule"}
VALID_EXAMPLE_ORIGINS = {"system-generated", "user-owned", "public-domain", "licensed"}

_SENT_SPLIT = re.compile(r"(?<=[。！？；\.!?;])")
_DIALOGUE = re.compile(r"[「\"'“”『』][^」\"'“”』]*[」\"'“”』]")
_HEDGE = re.compile(r"(可能|也许|似乎|大概|某种程度上|在某种意义上|在一定程度上)")


class StyleExtractError(Exception):
    """治理约束被违反时抛出（提取被拒，不产出候选）。"""


def _split_sentences(text):
    parts = _SENT_SPLIT.split(text)
    return [p.strip() for p in parts if p.strip()]


def _sent_len_stats(text):
    sents = _split_sentences(text)
    if not sents:
        return 0.0, 0
    lens = [len(s) for s in sents]
    return sum(lens) / len(lens), len(sents)


def _dialogue_ratio(text):
    chars = max(len(text), 1)
    return len(_DIALOGUE.findall(text)) / (chars / 100.0 + 1)


def _hedge_density(text):
    words = max(len(_split_sentences(text)), 1)
    return len(_HEDGE.findall(text)) / words


# --------------------------------------------------------------------------
# 确定性参考提取器（默认 extract_fn）
# --------------------------------------------------------------------------
def _default_extract_fn(sources, config):
    """给定来源列表，返回原始候选规格（未经治理校验）。

    每个来源：{source_id, text, weight}。返回 list of dict：
    {rule_type, scope, value, confidence_source, example_rules, source_ids}
    """
    n = len(sources) or 1
    avg_lens = []
    dials = []
    hedges = []
    for s in sources:
        al, _ = _sent_len_stats(s.get("text", ""))
        avg_lens.append(al)
        dials.append(_dialogue_ratio(s.get("text", "")))
        hedges.append(_hedge_density(s.get("text", "")))

    def _agree(metric_vals, thr):
        # 跨来源一致程度：超过阈值的来源比例 -> 可计算的置信来源
        over = sum(1 for v in metric_vals if v >= thr)
        return over / n

    source_ids = [s["source_id"] for s in sources]
    out = []

    # 规则 1：对话密度 -> style_preference（偏好短促对白）
    d_agree = _agree(dials, 0.05)
    if d_agree >= 0.6:
        out.append({
            "rule_type": "style_preference",
            "scope": {"content_type": "dialogue", "scene_types": ["对白"], "character_ids": [],
                       "span_selector": "dialogue_block"},
            "value": {
                "preference": "对白占比高的场景宜用短促、有信息量的台词，避免冗长解释",
                "applies_when": "scene_types contains 对白",
                "confidence_source": {
                    "computed": True,
                    "cross_source_agreement": round(d_agree, 3),
                    "min_independent_sources": n,
                    "method": "cross_source_dialogue_ratio_agreement",
                },
            },
            "example_rules": [{
                "text": "（系统生成）短促对白示例：『退。』他只吐出一个字。",
                "example_origin": "system-generated",
            }],
            "source_ids": source_ids,
        })

    # 规则 2：平均句长 -> style_target（目标句长区间）
    avg_all = sum(avg_lens) / n
    out.append({
        "rule_type": "style_target",
        "scope": {"content_type": "narrative", "scene_types": ["叙述"], "character_ids": [],
                   "span_selector": "sentence"},
        "value": {
            "target": {"metric": "avg_sentence_len_chars", "min": max(8, int(avg_all * 0.7)),
                        "max": int(avg_all * 1.4)},
            "rationale": "跨来源叙述句长聚合得到的目标区间",
            "confidence_source": {
                "computed": True,
                "cross_chapter_repetition": True,
                "min_independent_sources": n,
                "method": "cross_source_avg_sentence_len",
            },
        },
        "example_rules": [{
            "text": "（系统生成）叙述句保持在目标句长区间内，避免机械卡上限。",
            "example_origin": "system-generated",
        }],
        "source_ids": source_ids,
    })

    # 规则 3：模糊限定词密度 -> candidate_project_constraint（候选约束，须人工批准）
    h_agree = _agree(hedges, 0.02)
    if h_agree >= 0.6:
        out.append({
            "rule_type": "candidate_project_constraint",
            "scope": {"content_type": "all", "scene_types": [], "character_ids": [],
                       "span_selector": "paragraph"},
            "value": {
                "constraint": "候选：单段模糊限定词密度 > 0.02 的句子比例偏高，建议重写为确定性表述",
                "requires_human_approval": True,
                "confidence_source": {
                    "computed": True,
                    "cross_source_agreement": round(h_agree, 3),
                    "min_independent_sources": n,
                    "method": "cross_source_hedge_density",
                },
            },
            "example_rules": [{
                "text": "（系统生成）原句『他似乎可能有点犹豫』改写为『他握刀的手背暴起青筋。』",
                "example_origin": "system-generated",
            }],
            "source_ids": source_ids,
        })
    return out


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class StyleExtractor:
    def __init__(self, extract_fn=None, governance=None, extractor_version="proto-1",
                 prompt_hash="", model_id=None):
        self.extract_fn = extract_fn or _default_extract_fn
        self.gov = dict(GOVERNANCE, **(governance or {}))
        self.extractor_version = extractor_version
        self.prompt_hash = prompt_hash
        self.model_id = model_id

    # -- 治理校验 ---------------------------------------------------------
    def _enforce(self, spec, sources):
        rule_type = spec.get("rule_type")
        if rule_type in HARD_RULE_TYPES:
            raise StyleExtractError(
                "rejected: hard constraint not allowed from reference learning: %s" % rule_type)
        if rule_type not in ALLOWED_RULE_TYPES:
            raise StyleExtractError("unknown rule_type: %s" % rule_type)

        src_ids = spec.get("source_ids", [])
        source_count = len(set(src_ids))
        if source_count < self.gov["minimum_independent_sources"]:
            raise StyleExtractError(
                "source_count %d < minimum_independent_sources %d"
                % (source_count, self.gov["minimum_independent_sources"]))

        # 单源权重上限（固定 0.4）
        weights = {s["source_id"]: float(s.get("weight", 1.0 / max(len(sources), 1)))
                   for s in sources}
        for sid in src_ids:
            if weights.get(sid, 0.0) > self.gov["max_single_source_weight"]:
                raise StyleExtractError(
                    "source %s weight %.3f exceeds max_single_source_weight %.2f"
                    % (sid, weights.get(sid, 0.0), self.gov["max_single_source_weight"]))

        # confidence 必须可计算，禁模型自报
        cs = (spec.get("value", {}) or {}).get("confidence_source")
        if not isinstance(cs, dict) or not cs.get("computed"):
            raise StyleExtractError("confidence must be computed (confidence_source.computed=True), not model self-report")

        # 例句：必须标注来源，且禁止复制参考原句
        for ex in spec.get("example_rules", []) or []:
            if ex.get("example_origin") not in VALID_EXAMPLE_ORIGINS:
                raise StyleExtractError("example_rule missing/invalid example_origin: %r" % ex.get("example_origin"))
            for s in sources:
                if ex.get("text") and ex["text"] in s.get("text", ""):
                    raise StyleExtractError("example_rule uses forbidden raw reference sentence")

        # 绝不存原始 n-gram：value 序列化后不得包含任何来源连续片段（>=8 字）。
        # 用滑动窗口（而非按句切分）以捕获跨标点嵌入的原始文本。
        val_str = json.dumps(spec.get("value", {}), ensure_ascii=False)
        for s in sources:
            text = s.get("text", "")
            n = len(text)
            for i in range(n - 7):
                for L in (8, 12, 16, 20, 24):
                    if i + L > n:
                        break
                    chunk = text[i:i + L]
                    if chunk in val_str:
                        raise StyleExtractError(
                            "value contains raw source n-gram (forbidden): %s" % chunk[:12])

    def _build_candidate(self, spec, sources, revision_cycle_id, task_id,
                          session_id, chapter_id):
        self._enforce(spec, sources)
        src_ids = spec.get("source_ids", [])
        source_count = len(set(src_ids))
        weights = {s["source_id"]: float(s.get("weight", 1.0 / max(len(sources), 1)))
                   for s in sources}
        source_contribution_vector = {sid: round(weights.get(sid, 0.0), 4) for sid in src_ids}

        # confidence 由可计算信号合成（此处直接采用 confidence_source 提供的聚合）
        cs = spec["value"]["confidence_source"]
        confidence = round(min(1.0, max(0.0,
                              float(cs.get("cross_source_agreement", 0.6))
                              + 0.1 * max(0, source_count - self.gov["minimum_independent_sources"]))), 4)

        candidate_id = "SRC-%s" % _hash(json.dumps(spec, sort_keys=True, ensure_ascii=False))[:16]
        source_set_hash = _hash("|".join(sorted(set(src_ids))))
        value = dict(spec.get("value", {}))
        value["confidence_source"] = cs  # 随产物保留可计算来源（不存原始文本）

        candidate = {
            "schema": SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "candidate_id": candidate_id,
            "candidate_sha256": _hash(json.dumps(spec, sort_keys=True, ensure_ascii=False)),
            "source_set_hash": source_set_hash,
            "rule_id": "RULE-%s" % candidate_id[:8],
            "scope": spec.get("scope", {}),
            "rule_type": spec["rule_type"],
            "value": value,
            "confidence": confidence,
            "evidence_count": spec.get("evidence_count", source_count * 3),
            "eligible_scenes": spec.get("eligible_scenes", []),
            "source_count": source_count,
            "max_single_source_weight": self.gov["max_single_source_weight"],
            "minimum_independent_sources": self.gov["minimum_independent_sources"],
            "recommended_independent_sources": self.gov["recommended_independent_sources"],
            "source_contribution_vector": source_contribution_vector,
            "extractor_version": self.extractor_version,
            "model_id": self.model_id,
            "prompt_hash": self.prompt_hash,
            "review_status": "EXTRACTED",
            "created_at": time.time(),
        }
        # 可选：保留例句（已校验来源合规）
        if spec.get("example_rules"):
            candidate["example_rules"] = spec["example_rules"]
        return candidate

    def extract(self, sources, revision_cycle_id, task_id, session_id="", chapter_id="",
                scope=None):
        """从参考来源提取风格规则候选（经治理校验）。

        ``sources``: list of {source_id, text, weight?}。返回合规 style-rule-candidate 列表；
        任一违反治理即抛 StyleExtractError（不产出部分结果）。
        """
        if not sources:
            raise StyleExtractError("no sources provided")
        raw = self.extract_fn(sources, {"scope": scope})
        candidates = []
        for spec in raw:
            candidates.append(self._build_candidate(
                spec, sources, revision_cycle_id, task_id, session_id, chapter_id))
        return candidates


def validate_candidate(c):
    """校验 style-rule-candidate.schema 关键必填字段。返回 (ok, errors)。"""
    errors = []
    required = ["candidate_id", "candidate_sha256", "source_set_hash", "rule_id", "scope",
                "rule_type", "value", "confidence", "evidence_count", "source_count",
                "max_single_source_weight", "minimum_independent_sources",
                "recommended_independent_sources", "extractor_version", "prompt_hash",
                "schema_version", "review_status"]
    for k in required:
        if k not in c:
            errors.append("missing field: %s" % k)
    if c.get("rule_type") not in ALLOWED_RULE_TYPES:
        errors.append("invalid rule_type: %s" % c.get("rule_type"))
    if c.get("review_status") != "EXTRACTED":
        errors.append("review_status must be EXTRACTED at extraction: %s" % c.get("review_status"))
    if not (isinstance(c.get("confidence"), (int, float)) and 0.0 <= c["confidence"] <= 1.0):
        errors.append("confidence must be number in [0,1]")
    if c.get("source_count", 0) < c.get("minimum_independent_sources", 3):
        errors.append("source_count < minimum_independent_sources")
    if c.get("max_single_source_weight", 0) > 0.4:
        errors.append("max_single_source_weight > 0.4")
    return (len(errors) == 0, errors)


def persist(candidates, root, chapter_id, task_id):
    """落盘候选到 analysis/style。调用方须已完成 authorize(extract)。返回目录。"""
    out_dir = os.path.join(root, "analysis", "style", chapter_id, task_id)
    os.makedirs(out_dir, exist_ok=True)
    for c in candidates:
        path = os.path.join(out_dir, "%s.json" % c["candidate_id"])
        with open(path, "w", encoding="utf-8") as f:
            json.dump(c, f, ensure_ascii=False, indent=2)
    manifest = {"schema": "style.rule-candidate-set", "count": len(candidates),
                "candidate_ids": [c["candidate_id"] for c in candidates]}
    with open(os.path.join(out_dir, "candidates.manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return out_dir
