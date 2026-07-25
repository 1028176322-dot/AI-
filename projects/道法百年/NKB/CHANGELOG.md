# NKB CHANGELOG（库级变更史）

> 配合 NKB.md §2.1 对象级 `Version/Updated` 使用。本文件记「为何变更 / 范围」。

## v1 — 全量填充首版 seed（2026-07-25）

**范围**：11 个组件文件（Canon / Characters / Timeline / WorldState / Events / Foreshadow / Assets / Terminology / StoryState / ReaderState / Graph）全部从散落文档收敛整合为可机读事实。

**事实源（仅限可信文档，未取任何未审核章节）**：
- `小说简介.md`
- `大纲_1000章总体规划.md`
- `时间线与人物关系图.md`

**可信度标注**：每条记录带 `src`（来自哪份文档）+ `confidence: outline`（= 来自大纲/设定层，尚未经已审核章节核验）。等章节过审后，对应记录可升级为 `confidence: verified`。

**派生组件处理**：
- `WorldState.yaml` / `Assets.yaml`：按 NKB.md §2.2 标 `seeded: true` + `derived_from`（指向 Events），仅填源自可信大纲的**稳定世界态/持有物**，后续须由 Events 重放派生、不得直接手改。
- `Derived.yaml`：按 §2.3 留空，由脚本从 K2/K5 自动派生，不手填。

## ⚠️ 已知冲突：进京时序（待用户裁决）

两份可信文档在「进京 / 盘店 / 仙人醉 / 天上人间开业 / 苏墨凝相认」的章节锚点上**互相矛盾**：

| 文档 | 立场 |
|------|------|
| `时间线与人物关系图.md`（第 1-18 章锚点，标注 2026-07-20 更新） | 进京在 **Ch9-18**（抵通州镇→进京访玄尘子→盘店→收沈遇→天上人间开业） |
| `大纲_1000章总体规划.md`（第九节，裁决 2026-07-20 用户确认） | 进京在 **卷一 81-100 章**；明确要求「现有 1-20 章时间线重排：前 60 章为观内成长+下山历练，81 章起进京」 |

**处理（以大纲裁决为准）**：
- Timeline / Events / WorldState / Assets 中相关条目按时间线文档锚于 Ch9-18，但均加 `conflict_note` 标注「大纲裁决应后移至 81-100 章，待重排」。
- StoryState.SS-003 显式标注该冲突。
- **待办**：用户确认后，将 Ch9-18 的进京线重排至 81-100 章，并同步更新 Timeline/Events/WorldState/Assets 的章节锚点与 conflict_note。

## 后续维护约定
- 任何事实修正（写作 L4 / 修复 L5 落盘）须同步更新对应 NKB 组件，并 `Version +1` + 写 `Updated` 章号（§2.1）。
- 世界态/资源变更走 Events 派生（§2.2）；图谱/派生数据走脚本重算（§2.3）。
- 章节过审后，将相关记录的 `confidence` 由 `outline` 升为 `verified`。
