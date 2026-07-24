# 任务系统规范（Task System）— 总规范

> 层级：Platform Layer — 任务系统（Task System）
> 地位：**平台操作中心（Operation Center）**
> 对应 Phase 1「必须」项：任务系统
> 配套：task-schema.yaml / goal.schema.yaml / task-state-machine.md / task-router.md / agent-assignment.md / execution-policy.md / task-review.md
> 工具：`tools/task_engine.py` + `tools/task_cli.py`（CLI：`platform task <verb>`）

## 0. 核心转变

此前平台的工作模型是：

```
用户提需求 → AI 理解 → AI 自由执行
```

这只能支撑「单 AI + 单对话 + 短周期」。要支撑**多 AI / 多项目 / 长周期 / 可追踪 / 可回滚**，必须改为：

```
目标 Goal → 任务拆解 → 任务队列 → Agent 接取(Claim) → 执行 → 产物 → 审查 → 验收 → 关闭 → 沉淀经验
```

**AI 不是被聊天驱动的，而是被任务系统调度的注册执行节点。**

任务系统是平台的「操作系统内核」：编排器、上下文引擎、NKB、审查都围绕任务流转。

## 1. 五个必须区分的概念

| 概念 | 含义 | 是否直接执行 |
|---|---|---|
| **Goal（目标）** | 长期目标（如「完成第一卷」），含 success 清单 | 否 |
| **Task（任务）** | 最小可执行单元（如「生成第一章正文」） | 是 |
| **Agent（执行者）** | 角色 + 能力 + 权限（writer / reviewer / fixer / knowledge） | — |
| **Artifact（产物）** | 任务必须产出的具体文件（CH001-draft.md），非「一段回答」 | — |
| **Gate（验收）** | 任务不能自宣完成，必须过检查（文件存在/格式/字数/规划/一致性/审查） | — |

## 2. 任务创建三种来源

1. **人工创建**：用户直接说「我要写第一章」→ 生成 `TASK-CH001-WRITE`。
2. **目标自动拆解**：用户说「完成第一卷」→ planner-agent 拆成 规划→30×写作→审查→修复→NKB同步 的任务树。
3. **系统触发**：审查发现人物行为异常 → 自动建 `TASK-CH001-FIX`（source=review-report）。

## 3. 任务目录（文件系统即状态）

```
<project>/
└── tasks/
    ├── backlog/      # 已建，依赖未满足 / 未排期
    ├── ready/        # 输入完整，可执行
    ├── claimed/      # 已被某 Agent 接取（有 owner + lease）
    ├── running/      # 执行中
    ├── submitted/    # 已提交产物 + 自检
    ├── reviewing/    # 审查中（或等待审查任务接取）
    ├── passed/       # 审查通过
    ├── completed/    # 验收关闭
    ├── failed/       # 失败（可 retry）
    └── archive/      # 已归档（关闭/废弃）
```

每个任务 = `<TASK-ID>.yaml`，位于与其 `status` 同名的文件夹。**状态转移 = 移动文件 + 更新 `task.status` 字段**。这保证状态天然版本化、可追溯、可 `git` 管理。

> 注：用户原提议文件夹为 `assigned/review`，本规范细化为 `claimed/reviewing` 等以匹配精确状态机（见 task-state-machine.md），folder 名即状态名。

## 4. Agent 如何发现并接取任务（关键）

**禁止** AI 自己扫描全部任务自由干。正确流程：

1. Agent 上线登记：`agent_session(agent=writer-01, status=available, capabilities=[chapter_write])`。
2. **Scheduler（路由）** 查询 `ready/` 池 + Agent 能力 + 优先级 + 依赖 → 匹配。
3. Agent **Claim**：生成 `task_claim(task_id, agent, lease_time=60min)` → 任务移入 `claimed/`，`owner=writer-01`。
4. 其他 Agent 见 `owner` 已设 → 拒绝，防止双写冲突。

## 5. 执行前必须构建上下文

接取后不能立刻写。执行链：

```
Task → Context Builder → Runtime Context(项目+宪法+NKB+Plan+ReaderState+Forbidden) → AI
```

上下文由 `execution-policy.md` 定义；任务文件中的 `permissions.read/write/forbidden` 与 `constraints` 直接注入执行上下文。

## 6. 产物与提交

执行产出 **Artifact + Operation Manifest**（受控写 `cwrite`）。提交时 AI 不能自宣「完成」，必须 `submit`：

```
task_submission:
  task_id: TASK-CH001-WRITE
  artifact: BUILD-001
  checks: {constitution: pass, context: pass, format: pass, self_review: pass}
```

## 7. 审查 / 修复 / 依赖 / 失败

- 写作完成 → 系统自动建 `TASK-CH001-REVIEW`（dependency=write）→ 入 `ready/`。
- 审查发现严重问题 → 建 `TASK-CH001-FIX`（source=finding）→ 入 `ready/`。
- 长篇小说必须有依赖图（plan→write→review→fix→nkb），无依赖管理必乱。
- 任务**不能直接改 NKB**：写任务产出 candidate fact → 建 `TASK-NKB-UPDATE` → knowledge agent 更新。
- 失败 → `failed`，记录 reason + retry 策略，自动 `retry`（回 `ready/`）。

## 8. 人类介入节点

`requires_human: true` 的任务（立项 / 核心设定 / 重大改设 / 主线调整 / 结局 / 发布）必须由人类在 Gate 处确认，AI 不能自动关闭。

## 9. 完整流转图

```
用户目标 → Goal创建 → Planner拆解 → Task生成 → Task队列(ready)
  → Scheduler → Agent匹配 → Claim → Context构建 → 执行
  → Artifact → Self Check → Review Task → Fix Task → Regression
  → Gate → Complete → Memory沉淀 → 下一任务
```

任务系统使平台从「几个 AI 聊天窗 + 一堆文件」升级为真正的内容生产操作系统。
