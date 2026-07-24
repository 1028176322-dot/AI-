# 任务审查与验收（Task Review & Gate）

> 配套：task_engine.py 的 review/complete、task-review 任务自动创建、quality（Phase 2）

## 1. 审查任务的自动创建

写作任务 `submitted` 后，task_engine 自动生成审查任务：

```yaml
task:
  id: TASK-CH001-REVIEW
  type: chapter_review
  project: dao-fa
  priority: high
  status: ready            # 依赖满足即入 ready
  dependencies: [TASK-CH001-WRITE]
  agent:
    required_role: reviewer
  inputs:
    required: [BUILD-001, NKB-SNAPSHOT-001, PLAN-001, RS-001]
  expected_outputs: [review-report]
  acceptance:
    criteria:
      - 四支柱评分完成
      - 重大 finding 标注 severity
```

## 2. 审查动作

Reviewer claim 后执行 `review(task_id, decision, findings)`：

- `decision = pass` → `reviewing → passed → complete`（写作任务随之 `completed`）。
- `decision = fail` 且 `fix_required` → `reviewing → failed` + 自动建 `TASK-<id>-FIX`（source=finding）。

## 3. Finding 结构

```yaml
finding:
  id: ISSUE-001
  severity: high | medium | low
  category: character | logic | pacing | plot | continuity
  fix_required: true
  description: 肖凡行为违背人物设定（第3段）
```

## 4. 修复任务流

```
review fail (fix_required)
  → 建 TASK-CH001-FIX (type=chapter_fix, source=ISSUE-001)
  → ready → claimed(by fixer) → running → submit
  → 重新 review（Regression）
  → pass → 原写作任务 completed
```

修复任务**只能改 chapters/drafts**，禁止改 NKB（须走 candidate → TASK-NKB-UPDATE）。

## 5. 验收 Gate（Completion Gate）

任务 `completed` 前的最后一道关（区别于 review 的文学质量）：

- Artifact 存在且非空
- 格式符合 contract
- 字数 / Story Beat / 一致性通过
- NKB 冲突检查无阻断
- 若 `requires_human: true` → 须人类在 Gate 确认

通过才 `passed → completed`，并触发：
- `project/status.yaml` 推进
- Memory 沉淀（经验回收）
- 下游依赖任务 `promote`

## 6. 与质量评分（Phase 2 前瞻）

本规范只做 pass/fail 二元 Gate。Phase 2 的 Quality Score（plot/character/emotion/logic/pacing/reader_hook）将作为 review 的量化输入，长期形成「作者模型」。

## 7. 回滚接口

若 completed 后发现严重问题，可 `archive` 当前任务并重建 FIX 任务；关联的 `versions/` 提供 `rollback` 到上一 BUILD（见 version-control 规范）。
