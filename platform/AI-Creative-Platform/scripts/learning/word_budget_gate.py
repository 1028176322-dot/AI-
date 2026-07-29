# -*- coding: utf-8 -*-
"""Word-budget hard gate for chapter drafts (CH-001 字数缺口治理).

管线原只在写作 / 审查侧校验 *质量* 维度，从不测量真实字数，导致草稿可
腰斩却全程 PASS。本模块提供可被 `craft evidence-check` 与 `chapter_write`
落章入口共用的真实字数硬校验：实测草稿可见字符数须 >= ratio * plan.word_budget。
"""
import os
import re

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def measure_chars(text):
    """Return (cjk_count, non_ws_count) for a chapter draft."""
    cjk = len(_CJK_RE.findall(text))
    non_ws = len(re.sub(r"\s", "", text))
    return cjk, non_ws


def read_word_budget(plan_path):
    """Extract word_budget int from a chapter plan (regex, robust to YAML layout)."""
    try:
        with open(plan_path, "r", encoding="utf-8") as stream:
            text = stream.read()
    except OSError:
        return None
    m = re.search(r"word_budget\s*:\s*(\d+)", text)
    if not m:
        return None
    return int(m.group(1))


def enforce_word_budget(draft_path, plan_path, ratio=0.9):
    """Hard gate: measured draft CJK char count must meet >= ratio * word_budget.

    `word_budget` counts Chinese characters EXCLUDING punctuation (CJK only),
    so the gate compares the CJK count, not the punctuation-inclusive count.

    Returns (ok, errors). Never raises on missing files — reports them so the
    caller can fail-closed (refuse to write / refuse to pass).
    """
    if not draft_path or not os.path.isfile(draft_path):
        return False, ["word-budget gate: draft file missing: %s" % draft_path]
    if not plan_path or not os.path.isfile(plan_path):
        return False, ["word-budget gate: plan file missing: %s" % plan_path]
    with open(draft_path, "r", encoding="utf-8") as stream:
        text = stream.read()
    cjk, non_ws = measure_chars(text)
    budget = read_word_budget(plan_path)
    if budget is None:
        return False, [
            "word-budget gate: word_budget not found in plan %s" % plan_path]
    threshold = int(round(budget * ratio))
    if cjk < threshold:
        return False, [
            "word-budget gate: draft CJK chars %d (incl. punct %d) < %.0f%% of "
            "budget %d (%d CJK required)"
            % (cjk, non_ws, ratio * 100, budget, threshold)
        ]
    return True, []
