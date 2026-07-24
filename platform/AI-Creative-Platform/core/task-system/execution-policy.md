# 执行策略（Execution Policy）

> 配套：task_engine.py 的 submit、execution-policy 钩子、cwrite 受控写

## 1. 执行前：上下文构建（Context Builder）

Agent claim 任务后，**不允许**直接写。必须先构建 Runtime Context：

```
Task
  + constraints / permissions
  + 项目宪法（constitution）
  + NKB 快照（NKB-SNAPSHOT-<id>）
  + 章节规划（PLAN-<id>）
  + ReaderState（RS-<id>）
  + Forbidden（禁止修改 NKB / 核心设定）
        ↓
Runtime Context
        ↓
AI 生成 Artifact
```

上下文由 `context-engine` 生成，task_engine 在 `start` 时校验「必要输入是否在 `task.inputs.required` 中齐备」，缺则 `fail(reason=context_missing)`。

## 2. 执行中：受控写

- 所有产物落盘走 `cwrite`（受控写）：按 `agent.role` 的 `allow_write/deny_write` 拦截。
- Writer **禁止**直接改 NKB：发现需固化事实 → 产 `candidate fact` → 由 `TASK-NKB-UPDATE` 交给 knowledge agent。

## 3. 提交（Submit）

AI 不能自宣「完成」，必须 `submit`：

```yaml
task_submission:
  task_id: TASK-CH001-WRITE
  artifact: BUILD-001
  checks:
    constitution: pass
    context: pass
    format: pass
    self_review: pass
  outputs:
    draft: chapters/drafts/CH001.md
    report: artifacts/self-check-CH001.yaml
```

submit 动作：
1. 校验 `checks` 全 pass（否则 `failed`）。
2. 校验 `expected_outputs` 文件存在且非空。
3. 状态 `running → submitted`。
4. 触发：自动建 `TASK-<id>-REVIEW`（dependency=本任务）入 `ready/`。

## 4. 自检（Self-Check）

Writer 提交前须跑四支柱自检（review.four-pillars），输出 `self-check.yaml`：
- 人物一致性
- 逻辑自洽
- 节奏/爽点
- 规划符合度

任一 FAIL → 不允许 submit，须先本地修复或转 `TASK-<id>-FIX`。

## 5. 失败处理

| 失败类型 | 动作 |
|---|---|
| context_missing | fail + retry(reload_context)，max_retry=3 |
| 输出质量低 | review 判 failed → 建 FIX 任务 |
| 文件错误/格式错 | submit 拦截，返回错误，Agent 重做 |
| 超时（无 heartbeat） | Scheduler 判 failed → release |

## 6. 产物即 Artifact

任务「完成」的判据是**产物存在且过 Gate**，不是「AI 说了写完」。这把模糊的「AI 回答」变成可追溯、可回滚、可比较的工程产物。
