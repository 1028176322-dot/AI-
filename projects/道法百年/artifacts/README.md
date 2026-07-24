# Artifacts（章节产物包）
每章从规划到定稿的完整生命周期产物，由 `e:/个人/AI-Creative-Platform/core/workflows/流程体系_小说创作.md` §3.1 定义。

建议结构：
```
artifacts/CH_NNN/
├── CH_NNN_body.md        正文
├── CH_NNN_plan.md        规划卡（L3）
├── CH_NNN_context.json   运行时上下文（Context Engine 输出）
├── CH_NNN_review.md      审查报告（含 build 元数据）
└── CH_NNN_fixlog.md      修复日志（含 Delta Review 记录）
```
`build` 元数据（build.project_id / core_version / template_version / nkb_version / 各 plugin 版本）见 review 报告头部，支持跨项目比较与完全复现。
