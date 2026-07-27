# -*- coding: utf-8 -*-
"""Turn a conversational chapter request into a governed project task graph.

The dispatcher is deterministic: it interprets chapter counts/ranges, records
its assumptions, creates Task YAML files, and builds a Task Packet for every
created task. It never writes prose and never executes an Agent.
"""
import argparse
import datetime
import hashlib
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
import index_builder
import session_bootstrap
import task_engine
import task_templates


_NUM = r"[0-9零〇一二两三四五六七八九十百千]+"
_RANGE_RE = re.compile(
    r"第?\s*(%s)\s*章?\s*(?:到|至|[-—~～])\s*第?\s*(%s)\s*章" % (_NUM, _NUM))
_SINGLE_RE = re.compile(r"第\s*(%s)\s*章" % _NUM)
_COUNT_RE = re.compile(
    r"(?:写|创作|生成|续写|审查|审核|复审|检查)\s*(%s)\s*章" % _NUM)


def chinese_number(value):
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    digits = {
        "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3,
        "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
    }
    units = {"十": 10, "百": 100, "千": 1000}
    total = 0
    current = 0
    for char in text:
        if char in digits:
            current = digits[char]
        elif char in units:
            unit = units[char]
            total += (current or 1) * unit
            current = 0
        else:
            raise ValueError("unsupported Chinese number: %s" % value)
    return total + current


def _existing_numbers(project_root):
    return sorted({
        int(item["number"]) for item in index_builder.scan_chapters(project_root)
        if item.get("number") is not None
    })


def parse_request(request, project_root):
    text = str(request or "").strip()
    if not text:
        raise ValueError("request is empty")
    wants_review = any(word in text for word in (
        "审查", "审核", "复审", "检查", "review"))
    wants_write = any(word in text for word in (
        "写", "创作", "生成", "续写", "write"))
    if not wants_write and not wants_review:
        raise ValueError("request has no chapter writing/review intent")

    existing = _existing_numbers(project_root)
    latest = max(existing) if existing else 0
    assumptions = []
    match = _RANGE_RE.search(text)
    if match:
        start = chinese_number(match.group(1))
        end = chinese_number(match.group(2))
        if end < start:
            start, end = end, start
            assumptions.append("输入范围为倒序，已按升序执行")
        selection = "explicit_range"
    else:
        singles = [chinese_number(value) for value in _SINGLE_RE.findall(text)]
        if singles:
            start = end = singles[0]
            selection = "explicit_chapter"
        elif any(word in text for word in ("全部", "所有", "全稿")) and wants_review:
            if not existing:
                raise ValueError("project has no chapters to review")
            start, end = min(existing), max(existing)
            selection = "all_existing"
        else:
            count_match = _COUNT_RE.search(text)
            if not count_match:
                count = 1
                assumptions.append("未识别到数量，按 1 章处理")
            else:
                count = chinese_number(count_match.group(1))
            if count <= 0 or count > 1000:
                raise ValueError("chapter count must be 1..1000")
            if wants_write:
                start = latest + 1
                end = start + count - 1
                assumptions.append(
                    "“写 N 章”从项目现有最大章号的下一章开始")
                selection = "count_from_next"
            else:
                if not existing:
                    raise ValueError("project has no chapters to review")
                selected = existing[-count:]
                start, end = min(selected), max(selected)
                assumptions.append("“审查 N 章”按现有最新 N 章处理")
                selection = "latest_existing_count"
    if start <= 0:
        raise ValueError("chapter numbers must be positive")

    action = "write_pipeline" if wants_write else "review_only"
    if wants_write:
        assumptions.append(
            "写作任务自动串接审查；审查通过后只生成独立发布任务，不直接发布")
    return {
        "schema": "conversation-request-plan@1.0.0",
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
    has_intent = any(word in text for word in (
        "写", "创作", "生成", "续写", "审查", "审核", "复审", "检查",
        "write", "review"))
    # Keep the established one-chapter intake path compatible. The dispatcher
    # owns scopes that need deterministic expansion: counts, ranges, and all.
    # A request such as "写第99章" is already one governed task and therefore
    # does not need a batch Goal wrapper.
    has_scope = bool(
        _RANGE_RE.search(text) or _COUNT_RE.search(text)
        or any(word in text for word in ("全部", "所有", "全稿")))
    return has_intent and has_scope


def _chapter_ref(project_root, number):
    strict = os.path.isfile(os.path.join(project_root, "PROJECT_LAYOUT.yaml"))
    if strict:
        return "chapters/drafts/CH-%03d.md" % number
    latest = index_builder.detect_latest_version(project_root, number)
    if latest.get("path"):
        return os.path.relpath(
            latest["path"], project_root).replace("\\", "/")
    return "CH-%03d" % number


def _task(task_id, project_id, task_type, chapter_ref, dependencies,
          request_id, request):
    template = task_templates.load(task_type)
    values = {
        "conversation_request": request,
        "conversation_request_id": request_id,
        "chapter_number": int(re.search(r"\d+", chapter_ref).group(0)),
    }
    if task_type == "chapter_review":
        values["chapter_draft"] = chapter_ref
    return {
        "id": task_id,
        "type": task_type,
        "project": project_id,
        "title": "%s %s" % (
            "规划" if task_type == "plan_write" else "审查", chapter_ref),
        "version": 1,
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
                "所有产物由受控路径写入",
                "写作后必须审查，审查通过后才可建立发布任务",
            ],
        },
        "execution_policy": template.get("execution_policy") or {},
        "conversation_request_id": request_id,
    }


def dispatch(project_root, request, project_id, author="conversation-dispatch",
             model="unknown", write=True):
    plan = parse_request(request, project_root)
    stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")
    digest = hashlib.sha256(request.encode("utf-8")).hexdigest()[:6].upper()
    request_id = "REQ-%s-%s" % (stamp, digest)
    plan["request_id"] = request_id
    plan["project_id"] = project_id
    created = []
    previous_publish = None
    for number in plan["chapters"]:
        ref = _chapter_ref(project_root, number)
        if plan["action"] == "write_pipeline":
            task_id = "%s-PLAN-CH%03d" % (request_id, number)
            dependencies = [previous_publish] if previous_publish else []
            task_type = "plan_write"
            write_id = "%s-CHAPTER-WRITE" % task_id
            previous_publish = "%s-PUBLISH" % write_id
        else:
            task_id = "%s-REVIEW-CH%03d" % (request_id, number)
            dependencies = []
            task_type = "chapter_review"
        task = _task(
            task_id, project_id, task_type, ref, dependencies,
            request_id, request)
        created.append({
            "task_id": task_id,
            "type": task_type,
            "chapter": number,
            "chapter_ref": ref,
            "dependencies": dependencies,
            "predicted_pipeline": (
                [task_id, "%s-CHAPTER-WRITE" % task_id,
                 "%s-CHAPTER-WRITE-CHAPTER-REVIEW" % task_id,
                 "%s-CHAPTER-WRITE-PUBLISH" % task_id]
                if task_type == "plan_write" else [task_id]
            ),
            "_task": task,
        })
    plan["created_tasks"] = [
        {key: value for key, value in item.items() if key != "_task"}
        for item in created
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
            "all writing tasks enter review before publish",
        ],
        "task_ids": [item["task_id"] for item in created],
        "interpretation": {
            "action": plan["action"],
            "selection": plan["selection"],
            "chapters": plan["chapters"],
            "assumptions": plan["assumptions"],
        },
    }
    goal_path = task_engine.create_goal(
        project_root, goal, model=model, author=author)
    for item in created:
        state, _ = task_engine.create_task(
            project_root, item["_task"], model=model, author=author)
        item["state"] = state
    plan["states"] = {
        item["task_id"]: item["state"] for item in created}
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
    args = parser.parse_args()
    plan = dispatch(
        args.project_root, args.request, args.project,
        author=args.agent, model=args.model, write=not args.dry_run)
    print(_gov.dump_block(plan))


if __name__ == "__main__":
    main()
