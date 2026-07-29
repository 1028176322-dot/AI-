# Single-Agent Execution Policy

（单 Agent 串行执行；禁止子 Agent、委派与并行 Agent。以下规则覆盖会话/任务/编排器/工具四层。）

1. 对话中的“写 N 章 / 审查第 A-B 章”等请求必须先执行 `platform task dispatch --request ...`，生成 Goal、Task 和 Task Packet 后才能工作。
2. 所有写入必须关联当前 Session 中处于 claimed/running 的 Task。
3. 禁止直接修改 `chapters/approved/`；正式发布只能走 Publish Service。
4. 参考小说原文只放 `sources/references/inbox/`，学习产物不得复制原文。
5. 写作必须读取 `runtime/learning/writing-guidance.yaml`（若存在）。
6. 审查必须完成 Reader Panel，并把 findings 反补进项目写作指导。
7. 文件必须按 `PROJECT_LAYOUT.yaml` 的 storage 映射存放，禁止在根目录随意落文件。
8. 单 Agent 串行执行；禁止子 Agent、委派和并行 Agent。
9. 新项目必须先执行 `platform design prepare`；AI 设计候选通过六视角审查和审批后，
   才允许执行 NKB Genesis，聊天内容不得直接写入 NKB。
10. 用户只提供总章节数时，先执行 `platform outline prepare`；全书章节地图必须完整覆盖，
    每一章都必须具有完整场景级详细章纲并通过可写性和防注水门禁后，才允许写正文。
11. 正文开写前必须执行 `platform craft build`；提交时必须附写作手法执行证据，
    开头、场景手法和结尾与章纲不匹配或近章模板化时不得通过审查。
12. 任何 Git 操作必须先读取平台 `platform.yaml -> governance.git_coordination`；
    本 worktree 的 actor-id 必须由用户指定，只能通过
    `platform git status/sync/commit/publish` 提交
    `projects/dushi-jishi/**`；其他项目和平台内容只有读取、同步和使用权限。
13. 逐章执行必须使用 `platform chapter-flow run/status`；正常流程禁止手工拼接
    task/style/review/author/chapter 的低层命令。PAUSED 时只完成 NEXT_ACTION 后续跑。
