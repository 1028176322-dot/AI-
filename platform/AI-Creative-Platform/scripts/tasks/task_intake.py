# -*- coding: utf-8 -*-
"""Classify AI-chat requests before any project or platform mutation."""
import argparse
import datetime
import json

MUTATION_VERBS = [
    "执行", "写", "改", "修改", "修复", "生成", "创建", "新建",
    "更新", "删除", "重写", "补充", "调整", "重构", "润色", "扩写",
    "续写", "填充", "回滚", "学习", "提取", "归纳", "晋升",
    "反补", "回流", "接入", "实现", "升级", "优化", "新增",
]
PLATFORM_KEYWORDS = [
    "平台", "钩子", "脚本", "工具", "政策", "策略", "治理",
    "目录规范", "自主学习", "policy", "pre-commit", "task_system",
    "受控写", "session", "bootstrap", "task-enforcement", "Broker",
]
PROJECT_KEYWORDS = [
    "章节", "章", "NKB", "知识库", "人物", "设定", "大纲", "世界观",
    "冲突", "情节", "角色", "审查", "评分卡", "正文", "参考小说",
    "参考原著", "读者反馈", "新项目", "新小说", "开新书", "章节数",
]
CONSULT_KEYWORDS = [
    "什么是", "为什么", "如何", "怎么", "解释", "讲讲", "区别",
    "能否", "可以吗", "是否", "？", "?",
]


def classify(request):
    text = str(request or "")
    has_mutation = any(word in text for word in MUTATION_VERBS)
    has_platform = any(word in text for word in PLATFORM_KEYWORDS)
    has_project = any(word in text for word in PROJECT_KEYWORDS)
    has_consultation = any(word in text for word in CONSULT_KEYWORDS)

    if not has_mutation and not has_platform and not has_project:
        return "consultation", False, "直接回答；无项目或平台变更"
    if has_platform and has_mutation:
        return (
            "platform_mutation", True,
            "创建 system_maintenance 任务并要求明确授权")
    if has_project and has_mutation:
        return (
            "project_mutation", True,
            "创建项目任务并按模板路由角色")
    if has_mutation:
        # A direct imperative such as “开始执行” must not silently bypass
        # governance merely because it omits the noun from the prior turn.
        return (
            "project_mutation", True,
            "创建受治理任务；由上下文确定具体类型")
    if has_project and has_consultation:
        return "consultation", False, "直接回答项目概念问题"
    if has_platform or has_project:
        return (
            "analysis_without_change", True,
            "创建只读分析任务；不得修改正式内容")
    return "consultation", False, "直接回答"


def main():
    parser = argparse.ArgumentParser(prog="task-intake")
    parser.add_argument("--request", required=True)
    parser.add_argument("--project", default="novel-dsf")
    arguments = parser.parse_args()
    classification, required, action = classify(arguments.request)
    result = {
        "request_id": "REQ-%s-%03d" % (
            datetime.datetime.now().strftime("%Y%m%d"), 1),
        "request": arguments.request,
        "classification": classification,
        "task_required": required,
        "project": arguments.project,
        "action": action,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
