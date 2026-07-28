# -*- coding: utf-8 -*-
"""Translate chapter instructions from an AI chat into governed task graphs.

The dispatcher only interprets scope and creates task records. It never writes
prose, performs review, or bypasses task/session/Task Packet gates.
"""
import argparse
import datetime
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_ROOT = os.path.dirname(HERE)
for _child in os.listdir(SCRIPTS_ROOT):
    _path = os.path.join(SCRIPTS_ROOT, _child)
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

import _gov
import index_builder
import session_bootstrap
import task_engine
import task_templates


_NUM = r"[0-9零〇一二两三四五六七八九十百千]+"
_RANGE_RE = re.compile(
    r"第?\s*(%s)\s*章?\s*(?:到|至|[-—~～])\s*第?\s*(%s)\s*章?"
    % (_NUM, _NUM))
_SINGLE_RE = re.compile(r"第\s*(%s)\s*章" % _NUM)
_COUNT_RE = re.compile(
    r"(?:写|创作|生成|续写|审查|审核|复审|检查)\s*(%s)\s*章"
    % _NUM)

_WRITE_WORDS = ("写", "创作", "生成", "续写", "write")
_REVIEW_WORDS = ("审查", "审核", "复审", "检查", "review")


def chinese_number(value):
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    digits = {
        "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2,
        "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
        "八": 8, "九": 9,
    }
    units = {"十": 10, "百": 100, "千": 1000}
    total = 0
    current = 0
    for character in text:
        if character in digits:
            current = digits[character]
        elif character in units:
            total += (current or 1) * units[character]
            current = 0
        else:
            raise ValueError("unsupported Chinese number: %s" % value)
    return total + current


def _existing_numbers(project_root):
    return sorted({
        int(item["number"])
        for item in index_builder.scan_chapters(project_root)
        if item.get("number") is not None
    })


def _has_any(text, words):
    return any(word in text for word in words)


def parse_request(request, project_root):
    text = str(request or "").strip()
    if not text:
        raise ValueError("request is empty")
    wants_write = _has_any(text, _WRITE_WORDS)
    wants_review = _has_any(text, _REVIEW_WORDS)
    if not wants_write and not wants_review:
        raise ValueError("request has no chapter writing/review intent")

    existing = _existing_numbers(project_root)
    latest = max(existing) if existing else 0
    assumptions = []
    range_match = _RANGE_RE.search(text)
    single_matches = [
        chinese_number(value) for value in _SINGLE_RE.findall(text)]

    if range_match:
        start = chinese_number(range_match.group(1))
        end = chinese_number(range_match.group(2))
        if end < start:
            start, end = end, start
            assumptions.append("输入范围为倒序，已按升序执行")
        selection = "explicit_range"
    elif single_matches:
        start = end = single_matches[0]
        selection = "explicit_chapter"
    elif _has_any(text, ("全部", "所有", "全书")) and wants_review:
        if not existing:
            raise ValueError("project has no chapters to review")
        start, end = min(existing), max(existing)
        selection = "all_existing"
    else:
        count_match = _COUNT_RE.search(text)
        if count_match:
            count = chinese_number(count_match.group(1))
        else:
            count = 1
            assumptions.append("未识别到章节数量，按 1 章处理")
        if not 1 <= count <= 1000:
            raise ValueError("chapter count must be 1..1000")
        if wants_write:
            start = latest + 1
            end = start + count - 1
            selection = "count_from_next"
            assumptions.append(
                "“写 N 章”从现有最大章节号的下一章开始")
        else:
            if not existing:
                raise ValueError("project has no chapters to review")
            selected = existing[-count:]
            start, end = min(selected), max(selected)
            selection = "latest_existing_count"
            assumptions.append("“审查 N 章”按现有最新 N 章处理")

    if start <= 0:
        raise ValueError("chapter numbers must be positive")
    action = "write_pipeline" if wants_write else "review_only"
    if wants_write:
        assumptions.append(
            "写作自动进入章节审查和 strict-v2 风格闭环；发布必须等待"
            "最终回归、NKB 更新与 NKB 同步证明")
    if wants_write and wants_review:
        assumptions.append(
            "请求中的审查由写作后的平台审查链执行，不另建旁路审查")
    return {
        "schema": "conversation-request-plan@2.0.0",
        "request": text,
        "action": action,
        "selection": selection,
        "chapters": list(range(start, end + 1)),
        "latest_existing_chapter": latest,
        "review_explicitly_requested": wants_review,
        "assumptions": assumptions,
    }


def looks_like_chapter_request(request):
    text = str(request or "")
    # A single explicit chapter already maps to one governed intake task.
    # This dispatcher owns only scopes that require deterministic expansion.
    has_expansion_scope = bool(
        _RANGE_RE.search(text)
        or _COUNT_RE.search(text)
        or _has_any(text, ("全部", "所有", "全书")))
    return (
        _has_any(text, _WRITE_WORDS + _REVIEW_WORDS)
        and has_expansion_scope)


def _chapter_ref(project_root, number):
    strict = os.path.isfile(
        os.path.join(project_root, "PROJECT_LAYOUT.yaml"))
    if strict:
        return "chapters/drafts/CH-%03d.md" % number
    latest = index_builder.detect_latest_version(project_root, number)
    if latest.get("path"):
        return os.path.relpath(
            latest["path"], project_root).replace("\\", "/")
    return "CH-%03d" % number


def _task(
        task_id, project_id, task_type, chapter_ref, dependencies,
        request_id, request):
    template = task_templates.load(task_type)
    number_match = re.search(r"\d+", chapter_ref)
    values = {
        "conversation_request": request,
        "conversation_request_id": request_id,
        "chapter_number": int(number_match.group()) if number_match else None,
    }
    if task_type == "chapter_review":
        values["chapter_draft"] = chapter_ref
    return {
        "id": task_id,
        "type": task_type,
        "project": project_id,
        "title": "%s %s" % (
            "规划" if task_type == "plan_write" else "审查",
            chapter_ref),
        "version": 2,
        "priority": "high",
        "chapter_ref": chapter_ref,
        "dependencies": dependencies,
        "agent": {"required_role": template.get("required_role")},
        "permissions": template.get("permissions") or {},
        "inputs": {
            "required": template.get("required_inputs") or [],
            "values": values,
        },
        "expected_outputs": template.get("allowed_outputs") or [],
        "acceptance": {
            "criteria": [
                "Task Packet 输入完整",
                "所有产物只能写入任务许可路径",
                "写作后必须审查；strict-v2 必须经过风格闭环、"
                "最终回归、NKB 更新与同步后才可发布",
            ],
        },
        "execution_policy": template.get("execution_policy") or {},
        "conversation_request_id": request_id,
    }


def _predicted_pipeline(plan_id):
    write = "%s-CHAPTER-WRITE" % plan_id
    review = "%s-CHAPTER-REVIEW" % write
    manifest = "%s-PROTECTED-MANIFEST-BUILD" % review
    diagnose = "%s-AI-DIAGNOSE" % manifest
    return {
        "common": [plan_id, write, review, manifest, diagnose],
        "clean": [
            "%s-FINAL-REGRESSION" % diagnose,
            "%s-NKB-UPDATE" % diagnose,
            "%s-NKB-SYNC" % diagnose,
            "%s-PUBLISH" % write,
        ],
        "issues": [
            "%s-STYLE-REVISE" % diagnose,
            "%s-FIDELITY-REVIEW" % diagnose,
            "%s-STYLE-QUALITY-REVIEW" % diagnose,
            "%s-CHAPTER-APPLY-REVISION" % diagnose,
            "%s-FINAL-REGRESSION" % diagnose,
            "%s-NKB-UPDATE" % diagnose,
            "%s-NKB-SYNC" % diagnose,
            "%s-PUBLISH" % write,
        ],
    }


def dispatch(
        project_root, request, project_id,
        author="conversation-dispatch", model="unknown", write=True):
    plan = parse_request(request, project_root)
    stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")
    digest = hashlib.sha256(
        request.encode("utf-8")).hexdigest()[:6].upper()
    request_id = "REQ-%s-%s" % (stamp, digest)
    plan["request_id"] = request_id
    plan["project_id"] = project_id

    created = []
    previous_publish = None
    for number in plan["chapters"]:
        chapter_ref = _chapter_ref(project_root, number)
        if plan["action"] == "write_pipeline":
            task_id = "%s-PLAN-CH%03d" % (request_id, number)
            dependencies = [previous_publish] if previous_publish else []
            task_type = "plan_write"
            predicted = _predicted_pipeline(task_id)
            previous_publish = predicted["clean"][-1]
        else:
            task_id = "%s-REVIEW-CH%03d" % (request_id, number)
            dependencies = []
            task_type = "chapter_review"
            predicted = {"common": [task_id]}
        task = _task(
            task_id, project_id, task_type, chapter_ref, dependencies,
            request_id, request)
        created.append({
            "task_id": task_id,
            "type": task_type,
            "chapter": number,
            "chapter_ref": chapter_ref,
            "dependencies": dependencies,
            "predicted_pipeline": predicted,
            "_task": task,
        })
    plan["created_tasks"] = [
        {key: value for key, value in row.items() if key != "_task"}
        for row in created
    ]
    if not write:
        return plan

    session_bootstrap.require_session(project_root)
    goal = {
        "id": "GOAL-%s" % request_id,
        "title": request[:100],
        "project": project_id,
        "source": "ai_conversation",
        "request_id": request_id,
        "success": [
            "all requested chapters have governed tasks",
            "all writing tasks enter review and strict-v2 gates before publish",
        ],
        "task_ids": [row["task_id"] for row in created],
        "interpretation": {
            "action": plan["action"],
            "selection": plan["selection"],
            "chapters": plan["chapters"],
            "assumptions": plan["assumptions"],
        },
    }
    goal_path = task_engine.create_goal(
        project_root, goal, model=model, author=author)
    for row in created:
        state, _ = task_engine.create_task(
            project_root, row["_task"], model=model, author=author)
        row["state"] = state
    plan["states"] = {
        row["task_id"]: row["state"] for row in created}
    plan["manifest_path"] = goal_path
    return plan


def main():
    parser = argparse.ArgumentParser(prog="conversation-dispatch")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--agent", default="conversation-dispatch")
    parser.add_argument("--model", default="unknown")
    parser.add_argument("--dry-run", action="store_true")
    arguments = parser.parse_args()
    result = dispatch(
        arguments.project_root, arguments.request, arguments.project,
        author=arguments.agent, model=arguments.model,
        write=not arguments.dry_run)
    print(_gov.dump_block(result))


if __name__ == "__main__":
    main()
