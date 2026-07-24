# Git 分支约束与 pre-commit（防止 AI 越权）

文件系统权限（受控工具）之外，再用 Git 加一道锁：即使 AI 直接改了文件，也无法提交越权内容。

## 分支模型

```
main              # 稳定成品（仅 Gate 合并）
develop           # 集成分支
ai/writer/*       # 写作对话产出 Draft
ai/reviewer/*     # 审查对话产出 Review
ai/fixer/*        # 修复对话产出修复
```

## 提交规则（pre-commit 自动拦截）

| 分支 | 允许提交 | 禁止提交 |
|---|---|---|
| `ai/writer/*` | chapters/drafts、artifacts/plans、artifacts/reviews(否) | NKB/ approved/ core/ registry/ templates/ |
| `ai/reviewer/*` | artifacts/reviews、handoffs | chapters/ 正文修改 |
| `ai/fixer/*` | chapters/drafts、artifacts/fix-logs | NKB/ approved/ core/ registry/ templates/ |
| 任意分支含 NKB/ 变更 | 必须同时暂存 operations/ 的 Operation Manifest | — |

额外约束（建议）：
- NKB 更新单独提交；Core 修改必须单独 PR；Approved 只能由 Gate 合并。
- 没有 Operation Manifest 的写操作提交 → 拒绝。
- 没有 Build ID 的 Draft 提交 → 拒绝（由 CI 进一步校验）。

## 安装

```bash
cd AI-Workspace
git config core.hooksPath platform/AI-Creative-Platform/tools/git_hooks
```

钩子脚本：`platform/AI-Creative-Platform/tools/git_hooks/pre-commit`（纯 bash，无依赖）。
