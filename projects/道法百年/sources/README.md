# sources/ — NKB 事实源受治理区

本目录是小说知识库（NKB）的**唯一事实输入端**。所有进入 NKB 的事实必须先经此区提取。
规则见平台文档：`core/knowledge/NKB信息源与入库规范.md`。

## 目录职责

| 子目录 | 来源等级 | 用途 |
|------|--------|------|
| `canon/` | S1 | 世界底层设定（`world.yaml` / `immutable-rules.yaml` 必填） |
| `design/` | S2 | 人物 / 势力 / 地点 / 物品等设计 |
| `outline/` | S4 | 总纲 / 卷纲 / 章纲（仅进入 designed/pending） |
| `manuscripts/` | S3 | 已批准正式正文（事件确认来源） |
| `governance/` | S0 | 作者裁决 / 改设 / 废止 / 批准（最高权威） |
| `research/` | S6 | 研究资料，仅参考，不得直接入库 |
| `inbox/` | — | 临时 / 未确认输入，不得直接进入 NKB |

## 质量门禁

- 每个文件必须含 `document:` 元数据段（`id` / `type` / `title` / `status` / `version` / `updated_at` / `owner` / `project_id`）。
- 事实类文件 `status` 必须为 `approved`；`inbox` / `research` / `outline` / `plan` 不受此限。
- 不得在文件中使用"可能 / 也许 / 预计"等推测词而不标记计划态。
- 校验命令：`python cli/platform.py nkb --project-root .`（零 FAIL 方可进入提取流程）。

## 当前状态

本区目前为空。散落事实现位于旧 md（`时间线与人物关系图.md` / `小说简介.md` / `大纲_1000章总体规划.md` / `参考资料/反派设定.md` 等），
待按规范 §24 初始化顺序整合进对应子目录。整合完成并通过 §25 验收前，NKB 仍为结构规范、非 `authoritative`。
