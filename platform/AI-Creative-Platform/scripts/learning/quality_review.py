# -*- coding: utf-8 -*-
"""
风格质量门禁（style-quality-review，按 quality-policy 版本化阈值判定，纲要 §6，#22 Tier-1）。

设计要点
--------
- **阈值 SSOT**：``quality-policy`` 实例（如 core/learning/quality-policies/default.v1.yaml）
  是判定唯一依据；review 不得自定阈值或方向。报告 ``quality_policy_version`` 必须匹配。
- **指标方向由 comparator 决定**：rhythm_distance / redundancy 越低越好（lt）；pov_consistency /
  scene_style_match 越高越好（gte）。不同指标方向不同（审查四·高风险E）。
- **样本不足处理**：``minimum_sample_size`` + ``missing_data_policy``（fail / warn / skip），
  避免短场景产生不可信评分。
- **治理硬门禁**：``hard_gate=true`` 的指标失败 → 必须 ``human_override_allowed=false``，
  即**拒绝人工豁免**（POV 越界 / 事实变化等）。
- **确定性指标计算**（原型可复现）：rhythm_distance / pov_consistency / redundancy /
  scene_style_match。真实系统可替换为 LLM 评测，接口与 comparator 语义不变。
- 落盘经 authorize(quality_review) 授权（路径受 candidate_path_permission 约束）。
"""
import json
import os
import re
import time

SCHEMA_ID = "style.quality-report"
SCHEMA_VERSION = "1.0.0"

_SENT = re.compile(r"(?<=[。！？；\.!?;])")

# 各场景风格命中线索（确定性代理：含线索句占比越高，scene_style_match 越高）
SCENE_CUES = {
    "battle": list("劈斩轰爆冲退挡杀刀枪火弹阵血防攻守"),
    "dialogue": list("说道问答笑叹"),
    "exploration": list("望寻发现走路洞林山河石径"),
    "daily": list("吃喝坐站做买卖院桌锅碗"),
    "emotion": list("心泪痛喜怒怕惊爱恨颤息"),
    "exposition": list("原因据记史传说规则原理法"),
}

try:
    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "_common"))
    from _yaml_lite import load as _yload
except Exception:  # pragma: no cover
    try:
        from yaml import safe_load as _yload
    except Exception:
        _yload = None


def _split_sentences(text):
    return [s.strip() for s in _SENT.split(text) if s.strip()]


def compute_metrics(text, scene_type):
    """确定性指标计算。返回 {metric: value} 与每指标的 sample_size。"""
    sentences = _split_sentences(text)
    n_sent = max(len(sentences), 1)

    # rhythm_distance：句长（字）相对目标 45 的平均绝对偏差，越低越好
    lens = [len(s) for s in sentences]
    target = 45.0
    rhythm = sum(abs(l - target) for l in lens) / n_sent

    # pov_consistency：主导视角占比（第三人称 vs 第一人称），越高越好
    third = sum(1 for s in sentences if ("他" in s or "她" in s or "肖凡" in s))
    first = sum(1 for s in sentences if s.startswith("我") or "我觉得" in s)
    pov_total = third + first
    pov = (third / pov_total) if pov_total > 0 else (1.0 if third >= first else 0.0)

    # redundancy：重复 4-gram 占比，越低越好
    grams = []
    for s in sentences:
        for i in range(len(s) - 3):
            grams.append(s[i:i + 4])
    n_gram = max(len(grams), 1)
    uniq = len(set(grams))
    redundancy = (n_gram - uniq) / n_gram

    # scene_style_match：含场景线索句占比，越高越好
    cues = SCENE_CUES.get(scene_type, [])
    matched = 0
    for s in sentences:
        if any(c in s for c in cues):
            matched += 1
    scene_match = matched / n_sent

    return {
        "rhythm_distance": rhythm,
        "pov_consistency": pov,
        "redundancy": redundancy,
        "scene_style_match": scene_match,
    }, {
        "rhythm_distance": n_sent,
        "pov_consistency": n_sent,
        "redundancy": n_gram,
        "scene_style_match": n_sent,
    }


def _cmp(value, comparator, warning, failure):
    """返回 ('pass'|'warn'|'fail', detail)。"""
    if comparator in ("lt", "lte"):
        if value < warning:
            return "pass", None
        if value < failure:
            return "warn", "near failure"
        return "fail", "exceeds failure_threshold"
    if comparator in ("gt", "gte"):
        if value > warning:
            return "pass", None
        if value > failure:
            return "warn", "near failure"
        return "fail", "below failure_threshold"
    if comparator == "range":
        lo, hi = (failure, warning) if failure <= warning else (warning, failure)
        if lo <= value <= hi:
            return "pass", None
        return "fail", "outside range [%s,%s]" % (lo, hi)
    return "fail", "unknown comparator: %s" % comparator


def load_policy(path):
    if _yload is None:
        raise RuntimeError("no yaml loader available")
    with open(path, "r", encoding="utf-8") as f:
        return _yload(f.read())


def review(chapter_id, revision_cycle_id, producer_task_id, task_id, scene_type,
           draft_text, policy, applied_style_rules=None, quality_policy_version=None,
           human_override=False, created_at=None):
    """按 policy 判定质量，返回符合 style-quality-report.schema 的 dict。

    ``policy`` 为 quality-policy 实例 dict（含 thresholds 列表）。
    ``human_override=True`` 仅在对应指标 ``human_override_allowed=True`` 时生效。
    """
    pol_version = policy.get("quality_policy_version")
    if quality_policy_version is not None and quality_policy_version != pol_version:
        raise ValueError("quality_policy_version mismatch: report=%s policy=%s"
                         % (quality_policy_version, pol_version))

    metrics_vals, sample_sizes = compute_metrics(draft_text, scene_type)
    thresholds = policy.get("thresholds", [])
    metric_reports = []
    failures = []
    hard_failures = []

    for row in thresholds:
        if row.get("scene_type") != scene_type:
            continue
        metric = row["metric"]
        if metric not in metrics_vals:
            continue
        value = metrics_vals[metric]
        sample_size = sample_sizes.get(metric, 0)
        warning = row["warning_threshold"]
        failure = row["failure_threshold"]
        min_sample = row["minimum_sample_size"]
        miss_policy = row["missing_data_policy"]
        hard = bool(row.get("hard_gate"))
        allowed_override = bool(row.get("human_override_allowed"))

        # 样本不足处理
        if sample_size < min_sample:
            if miss_policy == "fail":
                metric_reports.append(_mrep(metric, row, value, sample_size, False,
                                            "sample too small (fail)"))
                failures.append(metric)
                if hard:
                    hard_failures.append(metric)
                continue
            elif miss_policy == "warn":
                metric_reports.append(_mrep(metric, row, value, sample_size, True,
                                            "sample too small (warn)"))
                continue
            else:  # skip
                continue

        verdict, detail = _cmp(value, row["comparator"], warning, failure)
        if verdict == "pass":
            metric_reports.append(_mrep(metric, row, value, sample_size, True, None))
        elif verdict == "warn":
            metric_reports.append(_mrep(metric, row, value, sample_size, True, detail))
        else:  # fail
            metric_reports.append(_mrep(metric, row, value, sample_size, False, detail))
            failures.append(metric)
            if hard:
                hard_failures.append(metric)

    # 综合判定
    if failures:
        if human_override and not hard_failures:
            # 仅当全部失败指标均允许豁免时，人工豁免生效
            overall = "QUALITY_WAIVED"
        else:
            overall = "QUALITY_FAILED"
    else:
        overall = "QUALITY_PASSED"

    return {
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "chapter_id": chapter_id,
        "revision_cycle_id": revision_cycle_id,
        "producer_task_id": producer_task_id,
        "task_id": task_id,
        "scene_type": scene_type,
        "quality_policy_version": pol_version,
        "metrics": metric_reports,
        "overall": overall,
        "human_override": human_override if (human_override and not hard_failures) else False,
        "applied_style_rules": applied_style_rules or [],
        "created_at": created_at if created_at is not None else time.time(),
    }


def _mrep(name, row, value, sample_size, passed, detail):
    return {
        "name": name,
        "comparator": row["comparator"],
        "value": round(value, 4),
        "warning_threshold": row["warning_threshold"],
        "failure_threshold": row["failure_threshold"],
        "sample_size": sample_size,
        "passed": passed,
        "detail": detail,
    }


def validate_report(d):
    errors = []
    required = ["chapter_id", "revision_cycle_id", "producer_task_id", "task_id",
                "scene_type", "quality_policy_version", "metrics", "overall", "created_at"]
    for k in required:
        if k not in d:
            errors.append("missing field: %s" % k)
    if d.get("overall") not in ("QUALITY_PASSED", "QUALITY_FAILED", "QUALITY_WAIVED"):
        errors.append("invalid overall: %s" % d.get("overall"))
    return (len(errors) == 0, errors)


def calculate_path(root, chapter_id, revision_cycle_id, task_id):
    return os.path.join(root, "analysis", "style", chapter_id, revision_cycle_id,
                        "%s.quality-report.json" % task_id)


def persist(d, root, chapter_id, revision_cycle_id, task_id):
    path = calculate_path(root, chapter_id, revision_cycle_id, task_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    return path
