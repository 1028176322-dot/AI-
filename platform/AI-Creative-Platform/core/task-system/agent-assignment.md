# Agent 指派与能力（Agent Assignment）

> 配套：ROLE_REGISTRY.yaml、permissions.policy.yaml、task-router.md

## 1. Agent ≠ 通用「AI」

Agent = **角色（role） + 能力（capabilities） + 权限（permissions）** 的绑定体。

```yaml
agent:
  id: writer-agent-001
  role: writer
  capabilities: [chapter_write, dialogue_expand, scene_expand]
  permissions:
    read:  [NKB/*, outline/*, tasks/*, project/status.yaml]
    write: [chapters/drafts/*, artifacts/*]
    forbidden: [NKB/*, core/*, lifecycle/*]
```

## 2. 角色与能力映射（平台预置）

| role | capabilities（任务 type 可接） | 禁止写 |
|---|---|---|
| `writer` | chapter_write, dialogue_expand, scene_expand | NKB, core, lifecycle |
| `reviewer` | chapter_review, consistency_check, quality_score | chapters, NKB, core |
| `fixer` | chapter_fix, continuity_fix | NKB（仅产 candidate）, core |
| `knowledge` | nkb_update, candidate_review | chapters, core |
| `planner` | goal_decompose, plan_write | chapters, NKB |
| `task-scheduler` | task_route, task_admin | 仅 tasks/*, project/status.yaml, audit/* |
| `status-updater` | status_write | 仅 project/status.yaml |

> 这些 role 在 `core/session/ROLE_REGISTRY.yaml` 注册；写权限在 `permissions.policy.yaml` 用 `allow_write/deny_write` 强制（task_engine 在 claim/submit 时二次校验）。

## 3. 指派规则

- 任务 `agent.required_role` 决定谁能 claim（如 `chapter_write` 需 `writer`）。
- Scheduler 仅把任务推荐给 `capabilities` 覆盖 `task.type` 且 `role == required_role` 的 Agent。
- 一个任务同一时刻只能有一个 owner（claim 互斥）。
- 任务产出的 Artifact 落盘须经 `cwrite` 受控写（按角色权限拦截）。

## 4. 多模型协作（前瞻）

`agent.model` 字段记录所用模型（GPT / Claude / Gemini / 本地）。未来 Model Router（Phase 3）按成本/速度/能力/保密选择模型，但 Agent 的**能力与权限契约不变**——模型只是 Agent 的执行后端。

## 5. 会话与生命周期

- Agent 会话有 `lease`；断开后其 `claimed` 任务由 Scheduler `release`。
- Agent 记忆分 `platform/project/session/agent/deprecated`（见 AI 记忆治理，Phase 2）。

## 6. 审计

每次 claim / submit / review 都写 `audit/`（操作人、模型、动作、文件、结果），形成企业级可追溯链。
