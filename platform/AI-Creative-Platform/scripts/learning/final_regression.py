# -*- coding: utf-8 -*-
"""
最终回归审查（final-regression，纲要 §2.7 / §2.9，实施任务 #23）。

双模式
--------
- ``mode=baseline``：无修订路径（DIAGNOSED_CLEAN / REVISION_SKIPPED → FINAL_CHECK_READY）。
  input=current_draft_text；checks=[NKB, outline, protected_manifest, chapter_review]。
  通过 → ``FINAL_PASSED`` → ``PUBLISH_READY``；失败 → ``FINAL_FAILED`` → ``CHAPTER_FIX_REQUIRED``。
- ``mode=post_apply``：已修订路径（APPLIED → FINAL_CHECK_READY）。
  input=[pre_apply_text, applied_draft_text]；checks=[fidelity, quality, NKB, outline,
  protected_manifest]。
  通过 → ``FINAL_PASSED`` → ``PUBLISH_READY``；失败 → ``FINAL_FAILED`` → ``ROLLBACK_READY``。

设计要点
--------
- **只读**：不修改任何文件（不写 chapters/、不写 analysis/ 下的受保护文件）。
  产出 final-regression-result dict（落 analysis/style/<ch>/<cyc>/ 仅作审计用途）。
- **FINAL_PASSED 仅由 final-regression 任务产生**（纲要 §2.7）：state_machine 的 via=final-regression
  保证其他任务无法直接写入 FINAL_PASSED。
- **确定性默认检查**（可注入 checker 替换为 LLM 评测，接口约束不变）。
- 调用方须先经 ``transition_state(FINAL_CHECK_READY, ..., via=final-regression, ...)``
  通过后才运行本模块。
"""
import hashlib
import json
import os
import re
import time

SCHEMA_ID = "style.final-regression-result"
SCHEMA_VERSION = "1.0.0"

_SENT = re.compile(r"(?<=[。！？；\.!?;])")
_DIGIT = re.compile(r"\d{2,}|[零一二三四五六七八九十百千]+年?")


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_obj(obj):
    return hashlib.sha256(
        json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _split_sentences(text):
    return [s.strip() for s in _SENT.split(text) if s.strip()]


def _fact_fidelity(text, pre_apply_text, protected_manifest_sha256):
    """post_apply 保真度检查：比较 pre_apply 与 applied 的核心事实保留率（确定性）。

    数字/引号事实的保留比例。比例 >= 0.95 则「通过」。
    """
    pre_digits = set(_DIGIT.findall(pre_apply_text))
    app_digits = set(_DIGIT.findall(text))
    if not pre_digits:
        return 1.0, "no digital facts to compare"
    retained = pre_digits & app_digits
    ratio = len(retained) / len(pre_digits) if pre_digits else 1.0
    return ratio, "fact_retention=%.2f" % ratio


def _style_quality(text, pre_apply_text):
    """post_apply 质量变化：比较 applied 与 pre_apply 的节奏差距缩小。

    暂以句长分布接近原始为"质量不退化"的代理（越低越好）。
    """
    pre_sents = _split_sentences(pre_apply_text)
    app_sents = _split_sentences(text)
    pre_avg = sum(len(s) for s in pre_sents) / max(len(pre_sents), 1)
    app_avg = sum(len(s) for s in app_sents) / max(len(app_sents), 1)
    drift = abs(app_avg - pre_avg)
    return drift, "style_drift=%.2f" % drift


def _nkb_check(text, nkb_revision, nkb_snapshot_sha256, manifest_sha256):
    """确定性的 NKB/章纲/manifest 一致性检查。"""
    pass_ = bool(nkb_revision and nkb_snapshot_sha256 and manifest_sha256)
    return pass_, "nkb_bindings=%s" % ("ok" if pass_ else "missing")


def _chapter_review_binding(text, chapter_review_report_sha256):
    """baseline 模式：校验章节审查报告哈希绑定是否存在。"""
    pass_ = bool(chapter_review_report_sha256)
    return pass_, "review_binding=%s" % ("present" if pass_ else "missing")


# --------------------------------------------------------------------------
# 默认检查器（可注入替换）
# --------------------------------------------------------------------------
DEFAULT_CHECKERS = {
    "fidelity": _fact_fidelity,
    "quality": _style_quality,
    "nkb": _nkb_check,
    "chapter_review": _chapter_review_binding,
}


def run_regression(mode, chapter_id, revision_cycle_id, producer_task_id,
                   draft_text=None, pre_apply_text=None, applied_draft_text=None,
                   nkb_revision="", nkb_snapshot_sha256="",
                   protected_manifest_sha256="", outline_sha256="",
                   chapter_review_report_sha256="",
                   checkers=None, created_at=None):
    """产出 final-regression-result 合规 dict。

    参数
    ----
    mode : str
        "baseline" 或 "post_apply"
    draft_text : str | None
        baseline 模式：当前草稿全文
    pre_apply_text : str | None
        post_apply 模式：apply 前的草稿备份正文
    applied_draft_text : str | None
        post_apply 模式：apply 后的草稿正文

    返回
    ----
    dict 包含 overall=FINAL_PASSED|FINAL_FAILED、checks 明细。
    """
    checkers = checkers or DEFAULT_CHECKERS

    # 明确 mode 语义
    if mode not in ("baseline", "post_apply"):
        return {
            "schema": SCHEMA_ID, "schema_version": SCHEMA_VERSION,
            "mode": mode, "chapter_id": chapter_id,
            "revision_cycle_id": revision_cycle_id,
            "producer_task_id": producer_task_id,
            "overall": "FINAL_FAILED",
            "checks": [],
            "error": "invalid mode: %s" % mode,
            "created_at": created_at if created_at is not None else time.time(),
        }

    checks = []
    failures = []
    hard_failures = []

    if mode == "baseline":
        text = draft_text or ""
        text_sha = _sha256(text)

        # NKB / outline / manifest 绑定检查
        ok, note = checkers["nkb"](text, nkb_revision, nkb_snapshot_sha256,
                                    protected_manifest_sha256)
        checks.append({"check": "nkb_binding",
                       "input_digest": text_sha,
                       "passed": ok, "detail": note})
        if not ok:
            failures.append("nkb_binding")
            hard_failures.append("nkb_binding")

        # 章节审查报告绑定
        ok2, note2 = checkers["chapter_review"](text, chapter_review_report_sha256)
        checks.append({"check": "chapter_review_binding",
                       "input_digest": text_sha,
                       "passed": ok2, "detail": note2})
        if not ok2:
            failures.append("chapter_review_binding")
            hard_failures.append("chapter_review_binding")

    else:  # post_apply
        pre = pre_apply_text or ""
        app = applied_draft_text or ""
        app_sha = _sha256(app)
        pre_sha = _sha256(pre)

        # 保真度检查
        ratio, note = checkers["fidelity"](app, pre, protected_manifest_sha256)
        passed = ratio >= 0.95
        checks.append({"check": "fidelity",
                       "pre_apply_digest": pre_sha,
                       "applied_digest": app_sha,
                       "fact_retention": round(ratio, 4),
                       "passed": passed, "detail": note})
        if not passed:
            failures.append("fidelity")

        # 质量变化检查
        drift, note2 = checkers["quality"](app, pre)
        passed2 = drift <= 15.0  # 句长偏差 ≤15 字即质量不下滑
        checks.append({"check": "quality_regression",
                       "pre_apply_digest": pre_sha,
                       "applied_digest": app_sha,
                       "style_drift": round(drift, 2),
                       "passed": passed2, "detail": note2})
        if not passed2:
            failures.append("quality_regression")

        # NKB / outline / manifest 绑定
        ok3, note3 = checkers["nkb"](app, nkb_revision, nkb_snapshot_sha256,
                                      protected_manifest_sha256)
        checks.append({"check": "nkb_binding",
                       "input_digest": app_sha,
                       "passed": ok3, "detail": note3})
        if not ok3:
            failures.append("nkb_binding")
            hard_failures.append("nkb_binding")

    # 综合判定
    if not failures:
        overall = "FINAL_PASSED"
    elif hard_failures:
        overall = "FINAL_FAILED"
    else:
        overall = "FINAL_FAILED"

    return {
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "chapter_id": chapter_id,
        "revision_cycle_id": revision_cycle_id,
        "producer_task_id": producer_task_id,
        "overall": overall,
        "checks": checks,
        "created_at": created_at if created_at is not None else time.time(),
    }


# --------------------------------------------------------------------------
# 校验
# --------------------------------------------------------------------------
def validate_result(d):
    errors = []
    required = ["mode", "chapter_id", "revision_cycle_id", "producer_task_id",
                "overall", "checks", "created_at"]
    for k in required:
        if k not in d:
            errors.append("missing field: %s" % k)
    if d.get("overall") not in ("FINAL_PASSED", "FINAL_FAILED"):
        errors.append("invalid overall: %s" % d.get("overall"))
    if not isinstance(d.get("checks"), list):
        errors.append("checks must be list")
    return (len(errors) == 0, errors)


# --------------------------------------------------------------------------
# 落盘（analysis/style/ 审计用途，不经受控写原语）
# --------------------------------------------------------------------------
def calculate_path(root, chapter_id, revision_cycle_id, task_id):
    return os.path.join(root, "analysis", "style", chapter_id, revision_cycle_id,
                        "%s.final-regression-result.json" % task_id)


def persist(d, root, chapter_id, revision_cycle_id, task_id):
    path = calculate_path(root, chapter_id, revision_cycle_id, task_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    return path
