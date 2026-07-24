# 任务状态机（Task State Machine）

> 配套：task.schema.yaml 的 `status` 枚举、task_engine.py 的转移函数

## 1. 状态全集（folder 名 == status 值）

```
backlog → ready → claimed → running → submitted → reviewing → passed → completed
                                                                  ↑
                                                          （retry 回 ready）
failed → (retry) → ready
任意状态 → archive  （关闭/废弃，终态）
```

| 状态 | 含义 | 进入条件 |
|---|---|---|
| `backlog` | 已建，未排期 | 创建时默认（若依赖未满足则停留） |
| `ready` | 输入完整、依赖满足、可执行 | promote（依赖全 completed）或 retry 回灌 |
| `claimed` | 已被 Agent 接取 | claim（设置 owner + lease） |
| `running` | 执行中 | start |
| `submitted` | 已交产物 + 自检 | submit |
| `reviewing` | 审查中 / 等审查任务 | 自动建 review 任务并入 ready，reviewer claim 后即 reviewing |
| `passed` | 审查通过 | review pass |
| `completed` | 验收关闭 | complete（passed → completed） |
| `failed` | 失败 | fail（记录 reason + retry 策略） |
| `archive` | 归档 | 显式归档（关闭/废弃） |

## 2. 合法转移表

```
backlog    → ready
ready      → claimed, archive
claimed    → running, archive
running    → submitted, failed, archive
submitted  → reviewing, archive
reviewing  → passed, failed, archive
passed     → completed, archive
completed  → archive
failed     → ready (retry), archive
archive    → （终态，不可转出）
```

非法转移（如 `backlog → running` 跳过 claim）由 task_engine 拒绝并报错。

## 3. 依赖与 promote

- 任务有 `dependencies: [TASK-A, TASK-B]`。
- `promote` 仅当**所有**依赖任务的当前状态为 `completed` 时才允许 `backlog → ready`。
- 未满足依赖时，任务停留在 `backlog`，scheduler 不会分配。
- 循环依赖检测：promote 时若依赖图中存在环，拒绝并报警。

## 4. Claim / Lease

- `claim(task_id, agent, lease_min=60)`：要求当前状态 `ready`，写入 `owner`、`claimed_at`、`lease_expire`。
- Lease 过期（超过 `lease_expire` 且仍 `claimed`）→ scheduler 可强制 `release` 回 `ready`，避免死锁。
- 同一任务已有 `owner` 时，其他 Agent 的 claim 被拒（防双写）。

## 5. 失败与重试

- `fail(task_id, reason, strategy="reload_context", max_retry=3)`：状态→`failed`，记录 `failure`。
- `retry`：`failed → ready`，清空 owner，递增 `retry_count`；超过 `max_retry` 则禁止自动 retry，转人工。
- running 态超时（无 heartbeat）也可由 scheduler 判 `failed`。

## 6. 与 project/status.yaml 的联动

task_engine 在以下转移时调用 status_update 钩子：
- `claimed`（chapter_write）→ `current.chapter.workflow_current_step=write`
- `reviewing` → `=review`
- `failed` → `current.blocked=true`
- `completed` → 推进 `current.chapter.current`
