# 平台记忆索引（memory/）

本目录为平台级长期记忆，跨项目共享索引，**不替代任何项目的 `NKB/`**（项目事实源以各自 `NKB/` 为准，见 platform.yaml `cross_project_isolation: true`）。

## 子目录
- `global/`：跨项目通用事实、平台决策与约定。
- `genre/`：按题材（玄幻/悬疑/都市/...）沉淀的创作知识与模板经验。
- `rejected/`：被否决的方案与决策记录，避免重复提议。

## 隔离
- `cross_project_isolation: true`（见 platform.yaml）：各项目相互独立，平台 memory 仅作跨项目索引，不写入项目专属事实。
