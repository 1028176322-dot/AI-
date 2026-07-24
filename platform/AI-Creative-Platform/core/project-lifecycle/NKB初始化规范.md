# NKB 初始化规范（P4 Knowledge Preparation & NKB Genesis）

schema_version: 1.0.0
stage: P4
owner_role: knowledge-engineer
parent: 项目生命周期总规范.md

---

## 1. 目标

把 P3 完成的**设计事实源** + P2 规划资料，初始化为 NKB 的第一版权威快照。
本阶段产出称为 **NKB Genesis（知识库创世构建）**，快照号 `NKB-GENESIS-001`。

## 2. 三类输入

| 类别 | 目录 | 用途 |
|---|---|---|
| 项目权威设计资料 | sources/canon/ sources/design/ sources/governance/ | 初始化正典/人物/术语/初始 Graph/Assets/WorldState |
| 规划资料 | sources/outline/ | 初始化 StoryState / 设计态 Foreshadow / 未来候选事件 / 第一卷路径 |
| 研究资料 | sources/research/ | 仅作设计参考，不得直接成为 NKB 事实 |

研究资料进入小说世界前，须经“研究 → 设计决策 → canon 源 → NKB”转化链（见 `NKB信息源与入库规范.md` §11）。

## 3. Genesis 流程（≠“创建空 YAML”）

```
设计文件准备完成
    ↓
Source Validation（validate_sources.py 全 PASS）
    ↓
实体 ID 分配（文件内已带 ID）
    ↓
静态事实提取（canon / 人物 / 世界 / 术语）
    ↓
初始状态定义（WorldState / Assets 初始值）
    ↓
初始信息状态定义（ReaderState / 人物 knowledge_state）
    ↓
初始关系图生成（Graph）
    ↓
术语标准化（Terminology）
    ↓
冲突检测（跨源 fatal 冲突 → 交作者裁决）
    ↓
生成 NKB-GENESIS-001 快照
```

## 4. Genesis 快照

`build_nkb_genesis.py` 生成/更新 `NKB/manifest.yaml`：

```yaml
nkb:
  project_id: novel-dsf
  schema_version: 1.2.0
  snapshot_id: NKB-GENESIS-001
  status: migration          # migration（待验收）| active
  authoritative: pending      # pending（Genesis 后）| true（P5 通过）
  last_event: null
  last_approved_chapter: null
  story_time: story_start
  generated_at: 2026-07-24
```

- Genesis 后 `authoritative: pending`，**不得**被写作对话当作 SSOT 使用，直到 P5 通过。
- `NKB/` 下 11 组件 yaml 的 `records` 由本步填充初始事实（非全空）。

## 5. 契约

见 `core/contracts/nkb-genesis.schema.yaml`：定义 Genesis 产物的必备字段、组件完整性、引用完整性、零 broken_references。

## 6. 门禁

`build_nkb_genesis.py` 内部执行：
- 来源全部 `validate_sources.py` PASS；
- 所有实体有唯一 ID；
- 所有初始事实有 `source`（指向 sources/ 文件）；
- `broken_references == 0`；
- `unresolved_fatal_conflicts == 0`。

任一失败 → Genesis 中止，输出缺失项，不写 `NKB-GENESIS-001`。

## 7. 状态转移

Genesis 成功 → `lifecycle_status` 转 `preparing_knowledge` → 进入 P5。
