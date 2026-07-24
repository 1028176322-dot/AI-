# Lifecycle（项目生命周期制品区）

本目录存放 P0–P5 前期生命周期制品，是 NKB 与正式写作的**唯一合法上游**。
规范见平台：`../../platform/AI-Creative-Platform/core/project-lifecycle/`

## 目录职责

| 子目录 | 阶段 | 负责角色 | 内容 |
|---|---|---|---|
| `idea/` | P0 | idea-analyst | 创意卡 IDEA.yaml（inbox/evaluating/approved/rejected） |
| `initiation/` | P1 | project-producer | PROJECT_CHARTER.yaml + INITIATION_GATE.yaml |
| `definition/` | P2 | project-producer + market-reader-analyst | PROJECT_BRIEF / AUDIENCE / POSITIONING / CREATIVE_STRATEGY / CONTENT_BOUNDARIES |
| `readiness/` | P5 | readiness-reviewer | READINESS_REPORT.yaml + READINESS_APPROVAL.yaml |

`status.yaml` 记录项目级状态机（`lifecycle_status`），编排器 pre-flight 据此决定是否允许写作。

## 本项目的 Legacy 状态

本项目在“项目生命周期”建立前已处于写作期，因此：

- `lifecycle/status.yaml` 直接为 `lifecycle_status: writing`，并标记 `legacy_backfill_required: true`。
- 已补回最小化制品：`initiation/PROJECT_CHARTER.yaml`、`initiation/INITIATION_GATE.yaml`（均标注 `legacy_backfilled: true`，值取自已知事实，作者应核对/补全）。
- **待补回**：`definition/` 五项文件、`readiness/` 报告。补回后可将 `legacy_backfill_required` 置 false。

## 校验命令

```bash
platform charter  --project-root .      # 校验 P1/P2 制品
platform psrc     --project-root .      # 校验 P3 设计源
platform genesis  --project-root .      # 从 sources 构建 NKB-GENESIS-001
platform ready   --project-root .       # 六维开写验收
platform ready   --project-root . --preflight   # 编排器前置检查（JSON）
```
