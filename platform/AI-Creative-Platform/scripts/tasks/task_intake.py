# -*- coding: utf-8 -*-
"""Task Intake：请求分类器（对话旁路封锁第一道）。

判断用户请求属于哪一类，并给出 action：
  consultation            : 无项目/平台变更，直接回答
  analysis_without_change : 分析/审查但仅出报告不落盘正文
  project_mutation        : 产生项目内容变更，须建 task（按类型路由角色）
  platform_mutation       : 产生平台/工具/政策变更，须建 task（system-maintainer，human 确认）

输出 JSON：{request_id, request, classification, task_required, project, action}
"""
import os
import sys
import argparse
import json
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
# [Phase2] 把 scripts 各分组目录加入 sys.path，保持跨组裸名 import 可用
_SCRIPTS = os.path.dirname(HERE)
if os.path.isdir(_SCRIPTS):
    for _d in os.listdir(_SCRIPTS):
        _p = os.path.join(_SCRIPTS, _d)
        if os.path.isdir(_p) and _p not in sys.path:
            sys.path.insert(0, _p) if False else None  # 兼容占位

MUTATION_VERBS = ["写", "改", "修", "生成", "创建", "新建", "更新", "删除", "重",
                  "补", "调整", "重构", "润色", "扩写", "续写", "填", "回滚"]
PLATFORM_KW = ["平台", "钩子", "脚本", "工具", "政策", "policy", "pre-commit",
               "task_system", "受控写", "session", "bootstrap", "task-enforcement"]
PROJECT_KW = ["章节", "章", "NKB", "人物", "设定", "大纲", "世界观", "冲突",
              "情节", "角色", "审查", "评分卡", "正文"]
CONSULT_KW = ["什么是", "是什么", "为什么", "如何", "怎么", "解释", "讲讲", "区别",
              "能否", "可以吗", "？", "?"]


# UTF-8 canonical vocabulary. These definitions intentionally override legacy
# mojibake constants above so Chinese requests cannot silently bypass intake.
MUTATION_VERBS = [
    "写", "改", "修改", "生成", "创建", "新建", "更新", "删除", "重写",
    "补充", "调整", "重构", "润色", "扩写", "续写", "填充", "回滚",
    "学习", "提取", "归纳", "晋升", "反补", "反哺", "回流",
]
PLATFORM_KW = [
    "平台", "钩子", "脚本", "工具", "政策", "策略", "治理", "目录规范",
    "自主学习", "policy", "pre-commit", "task_system", "受控写",
    "session", "bootstrap", "task-enforcement",
]
PROJECT_KW = [
    "章节", "NKB", "人物", "设定", "大纲", "世界观", "冲突", "情节",
    "角色", "审查", "评分卡", "正文", "参考小说", "参考原著", "读者反馈",
    "新项目", "新小说", "开新书", "章节数",
]
CONSULT_KW = [
    "什么是", "为什么", "如何", "怎么", "解释", "讲讲", "区别",
    "能否", "可以吗", "？", "?",
]


def classify(req):
    has_mut = any(v in req for v in MUTATION_VERBS)
    has_plat = any(k in req for k in PLATFORM_KW)
    has_proj = any(k in req for k in PROJECT_KW)
    has_consult = any(k in req for k in CONSULT_KW)

    # 纯咨询：无变更动词且无项目/平台关键词
    if not has_mut and not has_plat and not has_proj:
        return "consultation", False, "直接回答（无项目/平台变更）"
    if has_plat:
        return "platform_mutation", True, "创建 platform_mutation 任务（system-maintainer，需 human 确认）"
    if has_mut:
        return "project_mutation", True, "创建 project_mutation 任务（按类型路由角色）"
    if has_proj and has_consult:
        return "consultation", False, "直接回答（项目概念咨询）"
    if has_proj:
        return "analysis_without_change", True, "创建 analysis 任务（仅出报告，不落盘正文）"
    if has_consult:
        return "consultation", False, "直接回答（咨询类）"
    return "consultation", False, "默认咨询（无明确变更意图）"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--request", required=True)
    ap.add_argument("--project", default="novel-dsf")
    args = ap.parse_args()

    cls, required, action = classify(args.request)
    rid = "REQ-%s-%03d" % (datetime.datetime.now().strftime("%Y%m%d"), 1)
    out = {
        "request_id": rid,
        "request": args.request,
        "classification": cls,
        "task_required": required,
        "project": args.project,
        "action": action,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
