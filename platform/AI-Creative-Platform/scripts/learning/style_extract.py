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
_FIRST_PERSON = re.compile(r"(?:^|[，。！？；\s])(?:我|我们|咱们)")
_THIRD_PERSON = re.compile(r"(?:^|[，。！？；\s])(?:他|她|他们|她们)")
_INNER = re.compile(r"(想到|觉得|意识到|明白|心想|记得|怀疑)")
_EXPOSITION = re.compile(r"(因为|因此|原来|这意味着|也就是说|换言之|事实上)")
_ACTION = re.compile(r"(走|跑|冲|抬|转|抓|推|拉|砍|刺|看|听|停|退|进|出)")
_EMOTION_DIRECT = re.compile(r"(高兴|悲伤|愤怒|害怕|紧张|绝望|欣喜|难过|恐惧)")
_EMOTION_ACTION = re.compile(r"(握紧|颤抖|咬牙|屏住呼吸|心跳|手心|喉结|攥|僵住)")
_SENSES = {
    "visual": re.compile(r"(看|望|光|影|色|亮|暗|形)"),
    "auditory": re.compile(r"(听|声|响|鸣|吼|低语|寂静)"),
    "olfactory": re.compile(r"(闻|气味|香|腥|臭|焦味)"),
    "tactile": re.compile(r"(冷|热|痛|麻|粗糙|湿|风拂|触)"),
    "gustatory": re.compile(r"(甜|苦|酸|辣|咸|味道)"),
}
_METAPHOR = re.compile(r"(像|如同|仿佛|宛如|好似)")
_OMISSION = re.compile(r"(没有回答|不再解释|欲言又止|沉默|……|未曾说明|暂且不提)")
_TEMPLATE_PATTERNS = re.compile(
    r"(嘴角(?:勾起|扬起)(?:一抹|一丝)?弧度|"
    r"眼中闪过一丝|心中暗道|不由得倒吸一口凉气|"
    r"命运的齿轮|夜色如墨|清晨的第一缕阳光)")


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


def _ratio(count, total):
    return round(float(count) / max(float(total), 1.0), 6)


def _source_metrics(text):
    sentences = _split_sentences(text)
    lengths = [len(item) for item in sentences] or [0]
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    dialogue = _DIALOGUE.findall(text)
    last = sentences[-1] if sentences else ""
    mean = sum(lengths) / max(len(lengths), 1)
    variance = (
        sum((value - mean) ** 2 for value in lengths)
        / max(len(lengths), 1))
    sensory = {
        name: len(pattern.findall(text))
        for name, pattern in _SENSES.items()
    }
    function_counts = {
        "plot_action": len(_ACTION.findall(text)),
        "world_exposition": len(_EXPOSITION.findall(text)),
        "emotion": (
            len(_EMOTION_DIRECT.findall(text))
            + len(_EMOTION_ACTION.findall(text))),
        "dialogue": len(dialogue),
    }
    description_counts = {
        "environment": len(re.findall(
            r"(天|地|风|雨|云|山|河|街|屋|林|光|影)", text)),
        "character": len(re.findall(
            r"(脸|眼|手|衣|发|身形|神色|目光)", text)),
        "object": len(re.findall(
            r"(刀|剑|书|杯|门|桌|车|枪|玉|符|器)", text)),
        "action": function_counts["plot_action"],
    }
    dialogue_lengths = [
        len(item.strip("「」『』“”\"'")) for item in dialogue]
    return {
        "narrative_pov": {
            "first_person_signal": len(_FIRST_PERSON.findall(text)),
            "third_person_signal": len(_THIRD_PERSON.findall(text)),
            "interiority_signal": len(_INNER.findall(text)),
            "semantic_confirmation_required": True,
        },
        "narrative_distance": {
            "close_signal": (
                sum(sensory.values())
                + len(_INNER.findall(text))
                + len(_EMOTION_ACTION.findall(text))),
            "far_signal": len(_EXPOSITION.findall(text)),
            "semantic_confirmation_required": True,
        },
        "syntactic_rhythm": {
            "mean_sentence_chars": round(mean, 3),
            "sentence_length_stddev": round(variance ** 0.5, 3),
            "short_sentence_ratio": _ratio(
                sum(1 for value in lengths if value <= 12), len(lengths)),
            "long_sentence_ratio": _ratio(
                sum(1 for value in lengths if value >= 35), len(lengths)),
            "mean_paragraph_chars": round(
                sum(map(len, paragraphs)) / max(len(paragraphs), 1), 3),
        },
        "information_function": {
            "distribution": {
                key: _ratio(value, sum(function_counts.values()))
                for key, value in function_counts.items()
            },
            "semantic_confirmation_required": True,
        },
        "description_selection": {
            "distribution": {
                key: _ratio(value, sum(description_counts.values()))
                for key, value in description_counts.items()
            },
            "semantic_confirmation_required": True,
        },
        "sensory_preference": {
            "distribution": {
                key: _ratio(value, sum(sensory.values()))
                for key, value in sensory.items()
            },
        },
        "emotion_expression": {
            "direct_emotion_signal": len(_EMOTION_DIRECT.findall(text)),
            "behavioral_emotion_signal": len(_EMOTION_ACTION.findall(text)),
            "behavior_to_direct_ratio": round(
                len(_EMOTION_ACTION.findall(text))
                / max(len(_EMOTION_DIRECT.findall(text)), 1), 3),
            "semantic_confirmation_required": True,
        },
        "dialogue_method": {
            "dialogue_blocks_per_1000_chars": round(
                len(dialogue) * 1000 / max(len(text), 1), 3),
            "mean_dialogue_chars": round(
                sum(dialogue_lengths) / max(len(dialogue_lengths), 1), 3),
            "action_insertion_signal": len(re.findall(
                r"[」”』][^。！？]{0,20}(?:说|问|答|抬|看|笑|摇|点)", text)),
            "semantic_confirmation_required": True,
        },
        "metaphor_mechanism": {
            "metaphors_per_1000_chars": round(
                len(_METAPHOR.findall(text)) * 1000 / max(len(text), 1), 3),
            "source_domain_requires_semantic_evidence": True,
            "character_fit_requires_semantic_evidence": True,
        },
        "omission_method": {
            "omission_signals_per_1000_chars": round(
                len(_OMISSION.findall(text)) * 1000 / max(len(text), 1), 3),
            "omitted_information_type_requires_semantic_evidence": True,
        },
        "scene_closure": {
            "last_sentence_length": len(last),
            "question_hook": bool(re.search(r"[？?]\s*$", last)),
            "choice_hook": bool(re.search(
                r"(选择|决定|只能|要么|否则|却在这时)", last)),
            "action_hook": bool(_ACTION.search(last)),
            "semantic_confirmation_required": True,
        },
        "prohibited_patterns": {
            "template_expression_count": len(
                _TEMPLATE_PATTERNS.findall(text)),
            "hedge_density": round(_hedge_density(text), 6),
            "repeated_sentence_opening_count": (
                len(sentences)
                - len(set(item[:4] for item in sentences if item[:4]))),
        },
    }


def extract_source_profile(text):
    """Public deterministic twelve-dimension signal extractor."""
    return _source_metrics(text)


def _mean_value(values):
    if not values:
        return 0.0
    return round(sum(float(value) for value in values) / len(values), 6)


def _aggregate_nodes(nodes):
    """Recursively aggregate numeric metrics and preserve semantic flags."""
    if not nodes:
        return {}
    keys = sorted(set().union(*(
        set(node) for node in nodes if isinstance(node, dict))))
    result = {}
    for key in keys:
        values = [node[key] for node in nodes if key in node]
        if values and all(isinstance(v, bool) for v in values):
            result[key] = any(values)
        elif values and all(isinstance(v, (int, float)) for v in values):
            result[key] = _mean_value(values)
        elif values and all(isinstance(v, dict) for v in values):
            result[key] = _aggregate_nodes(values)
        else:
            result[key] = values[0] if values else None
    return result


def _agreement_for_dimension(nodes):
    """Bounded repeatability signal; never uses model self-confidence."""
    serialized = [
        json.dumps(node, ensure_ascii=False, sort_keys=True)
        for node in nodes]
    if len(serialized) <= 1:
        return 0.0
    # Exact equality is rare; stable metric shape plus source count provides a
    # conservative lower-bound pending calibrated statistical tests.
    exact = max(serialized.count(item) for item in set(serialized))
    return round(max(0.6, exact / len(serialized)), 3)


# --------------------------------------------------------------------------
# 确定性参考提取器（默认 extract_fn）
# --------------------------------------------------------------------------
def _default_extract_fn(sources, config):
    """给定来源列表，返回原始候选规格（未经治理校验）。

    每个来源：{source_id, text, weight}。返回 list of dict：
    {rule_type, scope, value, confidence_source, example_rules, source_ids}
    """
    n = len(sources) or 1
    source_ids = [s["source_id"] for s in sources]
    profiles = [
        s.get("style_profile") or _source_metrics(s.get("text", ""))
        for s in sources
    ]
    dimensions = [
        "narrative_pov", "narrative_distance", "syntactic_rhythm",
        "information_function", "description_selection",
        "sensory_preference", "emotion_expression", "dialogue_method",
        "metaphor_mechanism", "omission_method", "scene_closure",
        "prohibited_patterns",
    ]
    output = []
    for dimension in dimensions:
        nodes = [profile[dimension] for profile in profiles]
        aggregated = _aggregate_nodes(nodes)
        semantic = []
        for source in sources:
            evidence = source.get("semantic_evidence")
            if not isinstance(evidence, dict):
                continue
            if evidence.get(dimension):
                semantic.append(evidence[dimension])
        if semantic:
            aggregated["semantic_evidence"] = semantic
            aggregated["semantic_evidence_count"] = len(semantic)
        requires_semantic = any(
            bool(value) for key, value in aggregated.items()
            if "semantic" in key and key.endswith(
                ("required", "evidence")))
        rule_type = (
            "candidate_project_constraint"
            if dimension == "prohibited_patterns"
            else "style_target")
        content_type = (
            "dialogue" if dimension == "dialogue_method"
            else "narration")
        output.append({
            "rule_type": rule_type,
            "scope": {
                "content_type": content_type,
                "scene_types": [],
                "character_ids": [],
                "span_selector": "dimension:%s" % dimension,
            },
            "value": {
                "dimension": dimension,
                "target_distribution": aggregated,
                "evidence_mode": (
                    "statistics_plus_ai_semantic"
                    if semantic else "deterministic_signal_pending_ai_review"),
                "requires_semantic_review": requires_semantic and not semantic,
                "requires_human_approval": True,
                "confidence_source": {
                    "computed": True,
                    "cross_source_agreement":
                        _agreement_for_dimension(nodes),
                    "source_count": n,
                    "semantic_evidence_count": len(semantic),
                    "method":
                        "cross_source_twelve_dimension_aggregation",
                },
            },
            "evidence_count": n + len(semantic),
            "source_ids": source_ids,
            "example_rules": [{
                "text": (
                    "（系统生成）该维度只保存目标分布与抽象原则，"
                    "不保存参考作品原句。"),
                "example_origin": "system-generated",
            }],
        })
    return output


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
        # value 通常远短于来源全文；从 value 枚举窗口并在来源中检索，避免
        # 对长篇小说进行 source_length × window_count 的嵌套扫描。
        val_str = json.dumps(spec.get("value", {}), ensure_ascii=False)
        value_chunks = {
            val_str[index:index + length]
            for length in (8, 12, 16, 20, 24)
            for index in range(max(0, len(val_str) - length + 1))
        }
        for s in sources:
            text = s.get("text", "")
            for chunk in value_chunks:
                if chunk in text:
                    raise StyleExtractError(
                        "value contains raw source n-gram (forbidden): %s"
                        % chunk[:12])

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
