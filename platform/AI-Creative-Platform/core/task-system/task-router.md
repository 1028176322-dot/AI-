# 任务路由与调度（Task Router & Scheduler）

> 配套：task_engine.py 的 `route()`、agent-assignment.md

## 1. 角色

Scheduler 是任务系统的「调度内核」，职责：

```
ready 任务池 + Agent 能力登记 + 优先级 + 依赖  =>  分配（claim 建议）
```

它**不直接执行**任务，只做匹配与建议；真正 claim 由 Agent 发起（保证权责清晰、可审计）。

## 2. Agent 能力登记（Agent Registry）

Agent 上线时登记能力（见 agent-assignment.md）：

```yaml
agent_session:
  agent: writer-agent-01
  status: available
  capabilities: [chapter_write, dialogue_expand, scene_expand]
  role: writer
```

Scheduler 维护内存视图：

```
agents:
  writer:    can_do: [chapter_write, dialogue_expand, scene_expand]
  reviewer:  can_do: [chapter_review, consistency_check]
  knowledge: can_do: [nkb_update]
  fixer:     can_do: [chapter_fix, continuity_fix]
```

## 3. 匹配算法

对 `ready/` 中每个任务，按：

1. **能力匹配**：`task.type` ∈ `agent.capabilities`（任务 type 与能力标签一致）。
2. **依赖满足**：任务已 `ready`（promote 已确保）。
3. **优先级**：`critical > high > normal > low`。
4. **公平性/负载**：同能力多个 Agent 时，优先分配给 `claimed` 数最少者。
5. **约束**：任务 `permissions.forbidden` 涉及的资源，Agent 角色无权则跳过。

输出：`route` 命令返回可接取任务列表（含 task_id / type / priority / goal）。

## 4. Claim 的防冲突语义

- Scheduler 给出候选后，Agent 显式 `claim` → 任务移 `claimed/`，写 `owner`。
- 已 `claimed` 的任务从 `ready` 池移除，其他 Agent 不可见。
- Lease 过期 → Scheduler `release` 回 `ready`，可重新分配。

## 5. 示例

```bash
# writer-agent-01 查询可接取任务
platform task route --project-root <root> --role writer

# 输出：
#   TASK-CH132-WRITE  chapter_write  high  GOAL-VOL003
#   TASK-CH133-WRITE  chapter_write  normal GOAL-VOL003

# Agent 接取
platform task claim --project-root <root> --task TASK-CH132-WRITE --agent writer-agent-01
```

## 6. 与编排器（orchestrator）的关系

编排器不再「拿到用户需求直接调 writer」。改为：

```
用户/Planner → 建 Task → ready 池
编排器循环：route(空闲 Agent) → claim → 执行 → submit → review → complete → 下一 Task
```

无 Task 时编排器空闲；有 Task 时严格按队列推进。这是平台「可调度」而非「被聊天驱动」的根本。
