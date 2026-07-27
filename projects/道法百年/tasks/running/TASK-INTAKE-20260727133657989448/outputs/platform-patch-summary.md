# 新项目 AI 自主设计与 NKB Genesis 闭环

任务：`TASK-INTAKE-20260727133657989448`

## 已完成

- 将对话中的大方向灵感结构化为灵感简报、自主权限策略、设计缺口矩阵、生成计划和分域任务包。
- 建立故事核心、世界规则、人物、组织、地点、能力与资产、冲突、弧线、伏笔与信息、读者状态、初始世界状态、术语和大纲的统一设计要求。
- 建立设计候选、六维设计审查、分级审批、用户显式裁决证据和正式设计源晋升契约。
- 低影响且被授权的设计可由 AI 自主批准；高影响与致命影响设计必须等待作者明确决定。
- 新项目 NKB Genesis 前强制校验设计审批，禁止 AI 绕过设计任务系统直接生成 NKB。
- 任务系统新增 `project_design -> design_review -> design_approval -> nkb_genesis -> readiness_review -> chapter_plan` 闭环。
- 设计或开写验收失败时按模板返回 `project_design`，不再错误进入章节修复链。
- 新项目目录新增设计 intake、候选、分析、运行时、生命周期和操作记录分区，正式设计源与 NKB 分离管理。
- 对话任务识别可将“新项目灵感/补充世界观人物大纲”等请求自动映射为平台 `project_design` 任务。
- CLI 新增统一 `design` 入口，所有步骤继续遵守单 Agent、当前会话和任务权限治理。

## 核心入口

- `scripts/project/design_expansion.py`
- `core/contracts/design-expansion.schema.yaml`
- `core/contracts/design-review.schema.yaml`
- `core/project-lifecycle/AI自主设计与NKB生成规范.md`
- `core/task-system/templates/design-review.task.yaml`
- `core/task-system/templates/design-approval.task.yaml`
- `core/task-system/templates/nkb-genesis.task.yaml`
- `core/task-system/templates/readiness-review.task.yaml`
- `tests/test_design_expansion.py`

## 安全边界

- AI 候选不能直接写入 NKB。
- 引用作品仅允许提取方法，不允许复制表达、专名或情节组合。
- 作者锁定事实不可被 AI 覆盖。
- 高影响设计没有显式用户批准证据时，设计门禁和 Genesis 均为 block。
- 旧项目保持兼容；严格门禁只对带 `PROJECT_LAYOUT.yaml` 的新项目启用。
