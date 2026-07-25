# NKB 信息源与入库规范

> **定位**：规定小说知识库 NKB 的事实来源、源文件格式、目录位置、提取规则、冲突裁决、入库流程、更新流程和验收标准。
> 本规范是 NKB Schema（`NKB.md`）的配套执行层——Schema 定义"存什么"，本规范定义"事实从哪里来、怎么进库、冲突信谁"。
>
> **机器可执行配套**：
> - `core/contracts/nkb-source.schema.yaml` — 源文件质量门禁（§19）
> - `core/contracts/nkb-candidate.schema.yaml` — 候选事实结构（§15）
> - `tools/validate_nkb_sources.py` — 校验器（扫描 `sources/` 与 `NKB/candidates/`）
> - 调用入口：`python cli/platform.py nkb --project-root <项目根>`

本规范解决以下问题：

- NKB 应从哪些文件提取事实；
- 各类文件必须包含哪些信息；
- 文件应该放在哪个目录；
- 哪些内容可以直接入库；
- 哪些内容只能作为候选事实；
- 多个文件冲突时以谁为准；
- 不同 AI 对话如何统一提取并更新 NKB；
- 如何证明一条 NKB 事实来自何处。

---

## 1. 总原则

### 1.1 NKB 只存事实

**NKB 可以存储：**

- 世界底层规则；
- 人物身份、关系、能力和状态；
- 已确认的时间与地点；
- 已发生事件；
- 已确认的资源变化；
- 已埋设或已回收的伏笔；
- 标准术语；
- 当前故事状态；
- 作者、人物和读者的信息可见状态。

**NKB 不存储：**

- 写作技巧；
- Prompt；
- 审查规则；
- 文风要求；
- 剧情建议；
- 未确认猜测；
- AI 推理；
- 读者评价；
- "可能""应该""也许"等推测性内容。

**允许：**

```
fact: 肖凡拥有青锋剑
```

**禁止：**

```
fact: 肖凡以后可能会把青锋剑送给李雪
```

### 1.2 所有事实必须可追溯

NKB 中的每一条事实必须能回答：

- 谁定义的？
- 来自哪个文件？
- 来自文件哪一段？
- 何时生效？
- 是否已经在正文发生？
- 由谁批准入库？

因此，每个 NKB 对象除业务字段外，必须包含来源元数据：

```yaml
source:
  source_type: character_design
  source_file: sources/design/characters/CHR-001_肖凡.yaml
  source_anchor: identity
  source_version: 3
  extracted_at: 2026-07-24
  extracted_by: session-20260724-001
  approval_status: approved
```

### 1.3 设计事实与已发生事实分开

小说中存在两类不同的"真相"。

**设计事实**——作者预先确定，但不一定已经在正文中发生或公开。

例如：

```
幕后黑手是三皇子。
```

**正文事实**——已经在正式章节中发生、表现或被确认。

例如：

```
第132章，肖凡得知三皇子参与商城案。
```

两者不得混在同一个字段中。建议状态：

```yaml
fact_status:
  designed: true
  occurred: false
  revealed_to_reader: false
  known_by_characters: []
```

### 1.4 正文不是唯一来源，但正文是事件确认来源

设定文件可以定义：

- 世界规律；
- 人物底层设定；
- 未来剧情真相；
- 预设伏笔；
- 地图和组织结构。

正式正文主要确认：

- 事件是否真正发生；
- 人物当前状态是否改变；
- 资源是否发生变化；
- 谁知道了什么；
- 伏笔是否已经埋设或回收；
- 当前时间线推进到哪里。

因此：

> 大纲中的"计划发生"不能直接当作"已经发生"。

---

## 2. 项目目录标准

项目仓库统一为：

```
小说项目/
├── project.yaml
│
├── sources/                         # NKB 的原始事实来源（受治理区）
│   ├── canon/                       # 世界底层设定
│   ├── design/                      # 人物、势力、地点、物品等设计
│   ├── outline/                     # 总纲、卷纲、章纲
│   ├── manuscripts/                 # 正式正文
│   ├── governance/                  # 作者确认、改设、裁决记录
│   ├── research/                    # 研究资料，仅作参考
│   └── inbox/                       # 尚未分类、尚未确认的输入
│
├── NKB/                             # 唯一事实源
│   ├── manifest.yaml
│   ├── Canon.yaml
│   ├── Characters.yaml
│   ├── Timeline.yaml
│   ├── WorldState.yaml
│   ├── Events.yaml
│   ├── Foreshadow.yaml
│   ├── Assets.yaml
│   ├── Terminology.yaml
│   ├── StoryState.yaml
│   ├── ReaderState.yaml
│   ├── Graph.yaml
│   ├── Derived.yaml
│   ├── conflicts/
│   ├── candidates/
│   ├── snapshots/
│   └── CHANGELOG.md
│
├── artifacts/
├── handoffs/
├── operations/
├── memory/
└── overrides/
```

> `sources/` 是整个平台的**唯一事实输入端**。AI 不得绕过 `sources/` 在 `txt/`、`outline/` 呈现层目录或全项目范围内自由检索事实（见 §29）。

---

## 3. sources/ 与 NKB 的关系

```
sources/
    原始事实、作者设计、正文证据
        ↓ 提取
NKB/candidates/
    AI 提取出的候选事实
        ↓ 校验与裁决
NKB/*.yaml
    已批准的唯一事实
        ↓ 派生
WorldState / Assets / Graph / Derived
```

**必须禁止：**

```
源文件 → AI 直接覆盖正式 NKB
```

正确流程必须经过候选区：

```
源文件 → Candidate Fact → 验证 → 批准 → Commit NKB
```

---

## 4. NKB 信息来源分类

NKB 可以从七类文件提取信息。

| 优先级 | 来源类型 | 主要作用 | 是否可直接入库 |
|------|--------|--------|-------------|
| S0 | 作者裁决文件 | 处理冲突、改设、废止旧事实 | 是 |
| S1 | 世界正史文件 | 定义世界底层恒定事实 | 经初始化确认后可以 |
| S2 | 实体设计文件 | 定义人物、势力、地点、物品 | 经初始化确认后可以 |
| S3 | 已批准正式正文 | 确认事件、状态和信息变化 | 通过章节门禁后可以 |
| S4 | 已批准规划文件 | 提供未来设计、候选伏笔 | 只能进入 designed/pending |
| S5 | 审查与修复产物 | 纠正事实、发现同步缺口 | 需关联 Approved Build |
| S6 | 研究资料 | 提供现实参考 | 不得直接入库 |

---

## 5. S0 作者裁决文件

### 5.1 目录

```
sources/governance/
├── decisions/
├── retcons/
├── deprecations/
└── approvals/
```

### 5.2 用途

作者裁决文件是冲突时最高权威来源，用于：

- 改设；
- 废止旧设定；
- 处理两个事实冲突；
- 确认 AI 提取结果；
- 确认重大人物生死；
- 确认时间线调整；
- 确认大纲和正文谁优先。

### 5.3 文件模板

```yaml
document:
  id: DEC-20260724-001
  type: decision
  title: 王虎死亡章节调整
  status: approved
  version: 1
  updated_at: 2026-07-24
  owner: author
  project_id: novel-dsf

decision:
  id: DEC-20260724-001
  title: 王虎死亡章节调整
  status: approved
  decided_by: author
  decided_at: 2026-07-24

scope:
  entities:
    - CHR-002
    - EVT-130
  affected_components:
    - Characters
    - Timeline
    - Events
    - ReaderState

decision_content:
  old_fact: 王虎在第128章死亡
  new_fact: 王虎在第130章死亡
  effective_from: Ch130
  reason: 正文结构调整

actions:
  deprecate:
    - EVT-128
  create:
    - EVT-130
  rebuild:
    - WorldState
    - Graph

evidence:
  source_files:
    - sources/manuscripts/volume-02/CH-130.md
```

### 5.4 强制要求

每个裁决必须有：

- 唯一 ID；
- 旧事实；
- 新事实；
- 生效时间；
- 受影响对象；
- 是否需要重放事件；
- 作者批准状态。

没有 `status: approved` 的裁决不得修改正式 NKB。

---

## 6. S1 世界正史文件

### 6.1 目录

```
sources/canon/
├── world.yaml
├── chronology.yaml
├── power-system.yaml
├── geography.yaml
├── society.yaml
├── politics.yaml
├── economy.yaml
├── religion.yaml
├── technology.yaml
└── immutable-rules.yaml
```

题材不需要的文件可以省略，但 `world.yaml` 和 `immutable-rules.yaml` 必须存在。

### 6.2 必备信息

**world.yaml**

```yaml
document:
  id: CANON-WORLD-001
  type: world
  title: 大晟世界设定
  status: approved
  version: 1
  updated_at: 2026-07-24
  owner: author
  project_id: novel-dsf

world:
  id: WORLD-001
  name: 大晟
  genre: 架空历史玄幻
  era: 永熙
  calendar_system: 永熙纪年
  time_flow: "1:1"
  known_regions:
    - 盛京
    - 中土十八州
    - 北狄
  boundaries:
    - 禁区名称
```

**immutable-rules.yaml**

必须明确：

```yaml
document:
  id: CANON-RULES-001
  type: immutable_rules
  title: 不可变规则
  status: approved
  version: 1
  updated_at: 2026-07-24
  owner: author
  project_id: novel-dsf

rules:
  - id: CANON-RULE-001
    statement: 死人不能复活
    applies_from: story_start
    exceptions: []
    severity: fatal
```

**power-system.yaml**

必须包括：

- 力量来源；
- 境界；
- 等级顺序；
- 突破条件；
- 能力边界；
- 克制关系；
- 资源消耗；
- 是否存在例外；
- 例外的触发条件。

### 6.3 对应 NKB

主要提取到：

- K1 Canon
- K3 Timeline 的历法基准
- K8 Terminology
- Graph 的地理与组织基础

---

## 7. S2 实体设计文件

### 7.1 目录

```
sources/design/
├── characters/
├── factions/
├── locations/
├── items/
├── skills/
├── creatures/
├── organizations/
└── relationships/
```

每个实体单独一个文件，不建议把几十个人物写在一个大 Markdown 中。

> 注：§7.2–§7.6 的片段示例为节选；完整文件必须按 §19.1 在顶层附加 `document:` 元数据段。

### 7.2 人物文件规范

位置：

```
sources/design/characters/CHR-001_肖凡.yaml
```

模板：

```yaml
document:
  id: CHR-001
  type: character
  title: 肖凡人物设定
  status: approved
  version: 5
  updated_at: Ch132
  owner: author
  project_id: novel-dsf

character:
  id: CHR-001
  canonical_name: 肖凡
  aliases:
    - 小凡
  status: active

identity:
  birth_date: 永熙三年
  current_age:
    value: 9
    as_of: Ch001
  gender: 男
  species: 人类
  nationality: 大晟
  occupation:
    - 清虚观道童
  faction_ids:
    - FAC-001

personality:
  stable_traits:
    - 谨慎
    - 重因果
  values:
    - 活下去
    - 不轻易欠人情
  fears:
    - 身份暴露
  desires:
    - 查清身世
  forbidden_behaviors:
    - 主动暴露穿越者身份
    - 无条件效忠官府

speech:
  register: 克制
  common_patterns: []
  prohibited_patterns: []
  aliases_for_others: {}

abilities:
  skill_ids:
    - SKL-001
  known_limits:
    - 尚不能连续施展高级道术

knowledge_state:
  knows:
    - FACT-001
  does_not_know:
    - FACT-019

relationships:
  - target_id: CHR-002
    type: friend
    status: active
    since: Ch015

secrets:
  - id: SECRET-CHR-001-01
    content: 穿越者身份
    known_by:
      - CHR-001
    revealed_to_reader: true

metadata:
  version: 5
  updated: Ch132
  source_status: designed
```

### 7.3 人物文件最低标准

任何主要人物必须具备：

- 唯一 ID；
- 标准姓名与别名；
- 身份；
- 稳定性格；
- 价值观；
- 当前目标；
- 能力及限制；
- OOC 禁区；
- 关系；
- 信息知情状态；
- 当前生存状态；
- 版本和来源。

仅有：

```
肖凡：谨慎，聪明。
```

不满足入库标准。

### 7.4 势力文件规范

```yaml
document:
  id: FAC-001
  type: faction
  title: 清虚观设定
  status: approved
  version: 2
  updated_at: Ch132
  owner: author
  project_id: novel-dsf

faction:
  id: FAC-001
  canonical_name: 清虚观
  type: 宗门
  status: active
  headquarters: LOC-012
  leader: CHR-011
  goals:
    - 保存道统
  resources:
    - AST-040
  allies: []
  enemies:
    - FAC-009
  hierarchy: {}
  membership_rules: {}
```

### 7.5 地点文件规范

```yaml
document:
  id: LOC-001
  type: location
  title: 盛京设定
  status: approved
  version: 3
  updated_at: Ch132
  owner: author
  project_id: novel-dsf

location:
  id: LOC-001
  canonical_name: 盛京
  type: capital
  parent_location: REGION-001
  coordinates: null
  controlling_faction: FAC-010
  accessibility: open
  travel_times:
    LOC-002: 3日
  permanent_features:
    - 皇城
    - 东市
```

### 7.6 物品与资源文件规范

设计文件只定义物品是什么，不负责记录人物当前拥有多少。

```yaml
document:
  id: ITEM-001
  type: item
  title: 青锋剑设定
  status: approved
  version: 1
  updated_at: Ch132
  owner: author
  project_id: novel-dsf

item:
  id: ITEM-001
  canonical_name: 青锋剑
  type: weapon
  rarity: common
  abilities:
    - 锋利
  limitations:
    - 无法承载高阶灵力
```

人物当前是否拥有该物品，应由事件写入 K5，再派生至 K7 Assets。

---

## 8. S3 正式正文文件

### 8.1 目录

```
sources/manuscripts/
├── volume-01/
│   ├── CH-001.md
│   ├── CH-002.md
│   └── ...
├── volume-02/
└── manifest.yaml
```

只有通过发布门禁的正式章节才放入该目录。

草稿应放：

```
artifacts/builds/<build-id>/draft.md
```

不得把草稿与正式正文混在一起。

### 8.2 正文章节头信息

每章必须带机器可解析的 Front Matter：

```yaml
---
chapter:
  id: CH-132
  number: 132
  title: 商城夜变
  volume: VOL-02
  status: approved
  build_id: BUILD-132-05
  plan_id: PLAN-132-02
  context_id: CTX-132-04
  nkb_snapshot_before: NKB-244
  approved_at: 2026-07-24
timeline:
  start: 永熙十二年三月初六夜
  end: 永熙十二年三月初七凌晨
locations:
  - LOC-023
pov:
  - CHR-001
participants:
  - CHR-001
  - CHR-002
---
```

### 8.3 正文可提取的信息

正式正文可以提取：

- 新发生事件；
- 人物出场；
- 人物生死变化；
- 地点变化；
- 关系变化；
- 能力变化；
- 资源增减；
- 伏笔埋设、推进、回收；
- 信息公开和知情变化；
- 新术语；
- 时间线推进；
- 当前故事阶段变化。

### 8.4 正文不能自动确认的内容

以下内容不能因为正文一句描写就自动成为事实：

- 比喻；
- 角色谎言；
- 角色误判；
- 梦境；
- 幻觉；
- 假设；
- 内心猜测；
- 不可靠叙述；
- 未验证传闻；
- 反派吹嘘；
- 作者故意误导。

例如：

```
"听说皇帝已经死了。"
```

只能提取为：

```yaml
claim:
  speaker: CHR-021
  content: 皇帝已经死亡
  truth_status: unverified
```

不得直接将皇帝状态改为死亡。

---

## 9. S4 规划文件

### 9.1 目录

```
sources/outline/
├── premise.yaml
├── series-outline.yaml
├── volumes/
│   ├── VOL-01.yaml
│   └── VOL-02.yaml
├── chapters/
│   ├── PLAN-001.yaml
│   └── PLAN-002.yaml
└── foreshadow-plan.yaml
```

### 9.2 总纲必须包含

```yaml
series:
  premise: 核心故事前提
  protagonist: CHR-001
  central_conflict: 核心冲突
  ending_direction: 结局方向
  major_truths:
    - FACT-001
  major_arcs:
    - ARC-001
```

### 9.3 卷纲必须包含

- 卷目标；
- 起始状态；
- 结束状态；
- 主要人物；
- 主要地点；
- 核心冲突；
- 关键事件计划；
- 伏笔计划；
- 人物成长变化；
- 不可提前泄露的信息。

### 9.4 章纲必须包含

现有规划体系要求章节规划卡至少包括：

- 章节目标；
- 起承转合；
- Story Beat；
- 核心冲突；
- 情绪曲线；
- 字数预算；
- 出场人物；
- 场景；
- 预计事件；
- 伏笔动作；
- 预期状态变化。

示例：

```yaml
document:
  id: PLAN-132-02
  type: plan
  title: 第132章规划
  status: approved_for_writing
  version: 2
  updated_at: 2026-07-24
  owner: writer
  project_id: novel-dsf

plan:
  id: PLAN-132-02
  chapter_id: CH-132
  status: approved_for_writing

objective:
  plot: 商城遭袭
  character: 肖凡首次独立指挥防守
  foreshadow:
    - FB-007

participants:
  - CHR-001
  - CHR-020

locations:
  - LOC-023

expected_events:
  - candidate_id: EVT-CAND-132-01
    description: 黑虎帮袭击商城
    status: planned

expected_deltas:
  assets:
    - owner: CHR-001
      item: AST-001
      delta: -200
  relationships: []

reveal_plan:
  reader_learns:
    - FACT-080
  character_learns:
    CHR-001:
      - FACT-080
```

### 9.5 规划信息的入库限制

规划文件中的信息只能进入：

- 设计态；
- 候选事件；
- 待埋伏笔；
- 未来状态。

不能直接写为：

- 已发生事件；
- 当前世界状态；
- 当前人物资源；
- 读者已经知道。

只有正式章节 Approved 后，计划才转化为发生事实。

---

## 10. S5 审查与修复文件

### 10.1 目录

```
artifacts/builds/<build-id>/
├── review/
│   ├── static-review.yaml
│   ├── dynamic-review.yaml
│   ├── conflict-report.yaml
│   └── final-gate.yaml
├── fixes/
│   ├── fix-log.yaml
│   └── regression-report.yaml
└── manifest.yaml
```

### 10.2 可提取内容

审查文件不能创建故事事实，但可以：

- 指出 NKB 与正文冲突；
- 指出缺失事件；
- 指出人物状态未同步；
- 指出时间线错误；
- 指出同一术语多名称；
- 生成 Knowledge Update Proposal。

示例：

```yaml
document:
  id: KUP-132-01
  type: knowledge_update_proposal
  title: 王虎死亡状态同步
  status: pending
  version: 1
  updated_at: 2026-07-24
  owner: reviewer
  project_id: novel-dsf

knowledge_update_proposal:
  id: KUP-132-01
  source_review: REV-132-03
  reason: 正文确认王虎死亡，但Characters仍为active
  proposed_actions:
    - create_event: EVT-130
    - update_character_projection: CHR-002
  status: pending
```

只有章节通过 Gate 后，Knowledge Manager 才能批准写入。

---

## 11. S6 研究资料

### 11.1 目录

```
sources/research/
├── history/
├── technology/
├── geography/
├── culture/
└── references.yaml
```

研究资料只提供现实参考，不是小说世界事实。

例如历史资料中写：

```
明代京城为南京或北京。
```

不能自动覆盖小说设定中的：

```
盛京是大晟首都。
```

研究资料进入小说世界前，必须经过作者设计文件转化：

```
research → design decision → canon source → NKB
```

---

## 12. Inbox 临时输入区

### 12.1 目录

```
sources/inbox/
```

用于存放：

- 用户临时想法；
- AI 头脑风暴；
- 未整理角色设定；
- 聊天记录导出；
- 图片说明；
- 外部资料；
- 未确认改设。

### 12.2 规则

Inbox 中的任何内容：

- 不得直接进入正式 NKB；
- 不得被 Context Engine 当作事实；
- 不得作为 Review 一致性基准；
- 必须先归类到 canon、design、outline 或 governance；
- 必须取得明确状态。

文件状态示例：

```yaml
document:
  id: INBOX-20260724-001
  type: inbox
  title: 临时想法-XXX
  status: draft
  version: 1
  updated_at: 2026-07-24
  owner: author
  project_id: novel-dsf

source_status: draft
authority: unconfirmed
eligible_for_nkb: false
```

---

## 13. 来源权威等级

冲突裁决按以下优先级执行：

```
S0 作者已批准裁决
    ↓
NKB 当前正式事实
    ↓
S3 已批准正式正文
    ↓
S1 已批准世界正史
    ↓
S2 已批准实体设计
    ↓
S4 已批准规划
    ↓
S5 审查建议
    ↓
S6 研究资料
    ↓
Inbox / AI 推测
```

但需要注意：

### 13.1 设计与正文冲突

如果正文已经 Approved，而正文与旧设计文件冲突：

不得由 AI 自动判断正文覆盖设定。

应生成：

```
Conflict Report
```

交由作者决定：

- 正文写错，修正文；
- 设计已修改，更新设计；
- 属于角色误判，不构成冲突；
- 正式执行改设。

### 13.2 NKB 与新正文冲突

在正文尚未 Approved 时：

```
NKB 优先，草稿必须修正。
```

如果草稿是有意引入新事实：

```
草稿事实 → Candidate Event → Review → Approved → 写入 NKB
```

---

## 14. NKB 各组件的来源映射

| NKB 组件 | 主要来源 | 次要来源 | 禁止直接来源 |
|--------|--------|--------|------------|
| K1 Canon | sources/canon/、作者裁决 | 正式正文中的新世界规则 | 草稿、研究资料 |
| K2 Characters | sources/design/characters/ | 正式事件、作者裁决 | AI 推测 |
| K3 Timeline | 正式正文、事件 | 卷纲、章纲 | 未批准草稿 |
| K4 WorldState | K5 Events 投影 | 作者裁决后重放 | 人工直接编辑 |
| K5 Events | 已批准正文 | 作者裁决 | 规划中的预计事件 |
| K6 Foreshadow | 伏笔规划、正式正文 | 审查确认 | AI 临时猜测 |
| K7 Assets | K5 Events 投影 | 初始化资产设计 | 人工直接编辑当前值 |
| K8 Terminology | Canon、Design | 正式正文中新词 | AI 任意同义改写 |
| D1 StoryState | 已批准正文、卷状态 | 规划 | 草稿 |
| D2 ReaderState | 正文信息释放、章纲 Reveal Plan | 作者裁决 | 全知视角推测 |
| Graph | K2/K5/K7 派生 | 地理和势力设计 | 人工重复维护 |
| Derived | 已有 NKB 自动计算 | 无 | 人工直接写入 |

---

## 15. 候选事实统一结构

AI 从任何源文件提取信息时，必须先生成 Candidate Fact：

```yaml
candidate:
  id: CAND-20260724-001
  target_component: Characters
  operation: update
  target_id: CHR-001
  field: relationships

  value:
    target_id: CHR-002
    type: friend
    status: ended
    ended_at: Ch130

  source:
    type: approved_manuscript
    file: sources/manuscripts/volume-02/CH-130.md
    anchor:
      paragraph_id: P-084
      excerpt_hash: sha256:xxxx
    build_id: BUILD-130-04

  classification:
    fact_type: occurred
    confidence: 1.0
    requires_author_decision: false
    contains_inference: false

  effects:
    create_event: EVT-130-03
    rebuild:
      - Characters
      - WorldState
      - Graph

  status: pending_validation
```

---

## 16. 提取规则

### 16.1 原子化

一条 Candidate 只表达一个事实变化。

**错误：**

```
fact: 王虎死亡，肖凡悲痛，并决定离开清虚观
```

**正确：**

```
王虎死亡
肖凡得知王虎死亡
肖凡情绪变为悲痛
肖凡作出离开清虚观的决定
```

每一条分别判断真伪、来源和生效时间。

### 16.2 明确事实类型

每条事实必须标记为：

```yaml
fact_type:
  - designed
  - occurred
  - revealed
  - believed
  - claimed
  - deprecated
```

含义：

- `designed`：作者设计，但尚未发生；
- `occurred`：已经客观发生；
- `revealed`：已向读者或人物公开；
- `believed`：某人物相信，不保证真实；
- `claimed`：某人物声称；
- `deprecated`：旧事实已废止。

### 16.3 明确时间有效区间

人物和世界事实不能只有当前值，还需要有效时间。

```yaml
validity:
  from: Ch015
  to: Ch129
```

例如人物关系：

```yaml
relationship:
  target: CHR-002
  type: friend
  valid_from: Ch015
  valid_to: Ch130
```

这样才能重建任意章节时点。

### 16.4 区分客观真相与信息状态

例如：

```yaml
objective_truth:
  FACT-089: 三皇子是幕后黑手

reader_state:
  knows: false

character_state:
  CHR-001:
    knows: false
  CHR-020:
    knows: true
```

不能因为 NKB 知道真相，就让所有人物或读者都知道。

### 16.5 不从缺失信息推导否定事实

正文没有提到某物，不代表人物没有该物。

**错误提取：**

```
本章未写青锋剑 → 肖凡不再拥有青锋剑
```

资源减少必须有明确事件证据：

- 丢失；
- 被夺；
- 消耗；
- 赠送；
- 损毁；
- 出售。

---

## 17. 入库流程

1. **Source Discovery** — 识别新增或修改的源文件
2. **Source Validation** — 验证文件类型、状态、版本和必备字段
3. **Fact Extraction** — 提取原子 Candidate Facts
4. **Classification** — 标记 designed / occurred / revealed / claimed
5. **Deduplication** — 与当前 NKB 比较，删除重复候选
6. **Conflict Detection** — 识别与 NKB、其他来源的冲突
7. **Approval** — 自动批准低风险事实，重大事实要求人工确认
8. **Commit Events** — 状态变化优先写入 K5 Events
9. **Projection** — 重建 K2/K4/K7/D1/D2/Graph/Derived
10. **Validation** — Schema、一致性、引用完整性检查
11. **Snapshot** — 生成新 NKB Snapshot
12. **Changelog** — 写入变更日志

---

## 18. 自动批准与人工批准边界

### 18.1 可自动批准

满足以下全部条件时可以自动批准：

- 来源是 Approved Build；
- 事实在正文中明确发生；
- 不涉及世界底层规则；
- 不涉及主要人物复活、死亡或身份颠覆；
- 不与当前 NKB 冲突；
- 能精确定位来源；
- Schema 校验通过。

例如：

```
肖凡花费十两银子购买药材。
```

可以生成资产扣减事件。

### 18.2 必须人工批准

以下事实必须人工确认：

- 世界规则新增或修改；
- 人物死亡、复活；
- 主角身份改变；
- 核心关系逆转；
- 时间线整体调整；
- 重大改设；
- 大纲与正文冲突；
- 两个 Approved 来源互相冲突；
- 删除已有事实；
- 追溯修改已经发布章节的事实；
- NKB Schema 变化。

---

## 19. 源文件质量门禁

任何源文件进入提取流程前必须通过以下门禁。

### 19.1 通用必备字段

```yaml
document:
  id: 唯一ID
  type: 文件类型
  title: 标题
  status: draft|approved|deprecated
  version: 整数
  updated_at: 日期
  owner: author|writer|reviewer
  project_id: 项目ID
```

### 19.2 禁止情况

以下文件不得作为正式事实来源：

- 没有状态；
- 没有版本；
- 无法判断属于哪个项目；
- 同一实体没有唯一 ID；
- 把事实和建议混写；
- 使用大量"可能、也许、预计"但不标记计划态；
- 正文没有章节 ID；
- 大纲没有 Plan ID；
- 修改后没有 Changelog；
- 文件名无法识别内容类型。

> 机器校验：`validate_nkb_sources.py` 依据 `core/contracts/nkb-source.schema.yaml` 执行上述门禁。

---

## 20. 文件命名规范

| 类别 | 命名 |
|----|----|
| 人物 | `CHR-001_肖凡.yaml` |
| 势力 | `FAC-001_清虚观.yaml` |
| 地点 | `LOC-001_盛京.yaml` |
| 物品 | `ITEM-001_青锋剑.yaml` |
| 章节 | `CH-001.md` |
| 章节规划 | `PLAN-001.yaml` |
| 事件 | `EVT-001.yaml` |
| 作者裁决 | `DEC-20260724-001.yaml` |
| 改设 | `RETCON-20260724-001.yaml` |
| 候选事实 | `CAND-20260724-001.yaml` |

**禁止依赖：**

- `人物最终版2_真的最终版.md`
- `新设定最新.md`
- `大纲修改版3.md`

---

## 21. NKB Manifest

NKB/manifest.yaml 必须记录整个知识库状态：

```yaml
nkb:
  project_id: novel-dsf
  schema_version: 1.2.0
  snapshot_id: NKB-245
  status: active
  authoritative: true
  last_event: EVT-132-05
  last_approved_chapter: CH-132
  generated_at: 2026-07-24

components:
  Canon:
    file: Canon.yaml
    version: 12
  Characters:
    file: Characters.yaml
    version: 83
  Timeline:
    file: Timeline.yaml
    version: 132
  Events:
    file: Events.yaml
    version: 245

source_roots:
  - ../sources/canon
  - ../sources/design
  - ../sources/outline
  - ../sources/manuscripts
  - ../sources/governance

integrity:
  unresolved_conflicts: 0
  pending_candidates: 3
  broken_references: 0
```

---

## 22. 不同 AI 对话的职责

### Writer AI

**可以：**

- 读取 NKB Snapshot；
- 根据规划和 Context 写草稿；
- 提交 Candidate Event；
- 标记可能需要更新的 NKB 项。

**不可以：**

- 直接修改正式 NKB；
- 把规划事件标记为已发生；
- 修改 Canon；
- 直接修改 K4/K7。

### Reviewer AI

**可以：**

- 对照 NKB 检查正文；
- 发现同步缺口；
- 生成 Conflict Report；
- 生成 Knowledge Update Proposal。

**不可以：**

- 自行决定重大改设；
- 直接提交高风险事实。

### Knowledge Manager AI

**可以：**

- 验证 Candidate；
- 写入 Event；
- 执行 Projection；
- 更新版本；
- 生成 Snapshot 和 Changelog。

**不可以：**

- 创作正文；
- 根据推测补齐缺失事实；
- 绕过作者裁决。

### System Maintainer AI

**只负责：**

- Schema；
- 提取器；
- 目录规范；
- Contract；
- 校验脚本。

**不得将某个项目的具体事实写入全局平台。**

---

## 23. 跨对话交接规范

每个写作或审查对话结束时，应输出：

```yaml
nkb_handoff:
  session_id: SES-001
  project_id: novel-dsf
  base_snapshot: NKB-244

candidate_facts:
  - CAND-132-001
  - CAND-132-002

potential_conflicts:
  - CONF-132-001

recommended_actions:
  - validate_candidates
  - rebuild_world_state

files:
  candidate_dir: NKB/candidates/BUILD-132-05/
  conflict_report: NKB/conflicts/CONF-132-001.yaml
```

新对话只接收结构化 Handoff，不依赖旧聊天内容。

---

## 24. 初始化旧项目的提取顺序

旧项目首次建立 NKB 时，必须按以下顺序执行：

1. 第一阶段：作者裁决与现行治理文件
2. 第二阶段：世界观与不可变规则
3. 第三阶段：人物、势力、地点、物品设计
4. 第四阶段：正式正文逐章提取 Events
5. 第五阶段：重建 Timeline
6. 第六阶段：由 Events 投影 WorldState 和 Assets
7. 第七阶段：提取伏笔与 ReaderState
8. 第八阶段：统一术语
9. 第九阶段：生成 Graph 和 Derived
10. 第十阶段：执行全库冲突审计
11. 第十一阶段：作者确认
12. 第十二阶段：将 NKB 标记为 authoritative

不能先从正文一次性总结全部事实，因为正文包含：

- 角色谎言；
- 误导；
- 旧设定；
- 已废止内容；
- 叙述性比喻；
- 隐含但未确认的推测。

---

## 25. 初始化验收标准

NKB 正式切换为 SSOT 前，必须满足：

```yaml
acceptance:
  schema_valid: true
  all_entities_have_ids: true
  all_facts_have_sources: true
  all_events_have_chapter_anchors: true
  no_direct_world_state_edits: true
  no_direct_asset_state_edits: true
  terminology_duplicates: 0
  broken_references: 0
  unresolved_fatal_conflicts: 0
  reader_state_initialized: true
  last_approved_chapter_matches_project: true
  author_approved: true
```

未达到时：

```yaml
nkb:
  status: migration
  authoritative: false
```

达到后：

```yaml
nkb:
  status: active
  authoritative: true
```

---

## 26. 每章完成后的 NKB 更新规范

每章 Approved 后必须执行：

```
读取 Approved Build
    ↓
提取 Candidate Facts
    ↓
对照 Plan 与旧 NKB
    ↓
识别实际发生和未发生内容
    ↓
创建 Events
    ↓
更新 Timeline
    ↓
投影 Characters / WorldState / Assets
    ↓
更新 Foreshadow
    ↓
更新 ReaderState
    ↓
统一 Terminology
    ↓
重建 Graph / Derived
    ↓
生成 Snapshot
    ↓
运行 Regression
```

任何一步失败：

```
章节不得进入 Published
```

或者至少标记：

```yaml
publication:
  content_approved: true
  knowledge_sync: failed
  final_status: blocked
```

---

## 27. 最终边界

**应放在平台 Core 的内容：**

- NKB Schema
- 信息源规范
- 提取规则
- 入库 Contract
- 冲突策略
- 校验脚本
- 投影逻辑
- 角色权限

**应放在类型 Template 的内容：**

- 题材专用 NKB 扩展字段
- 题材默认实体类型
- 题材特有力量体系字段
- 题材特有术语分类

**应放在项目 sources 的内容：**

- 世界设定
- 人物设定
- 大纲
- 正文
- 作者裁决
- 研究资料

**应放在项目 NKB 的内容：**

- 已经批准的项目事实
- 候选事实
- 冲突报告
- 快照
- 变更日志
- 派生数据

---

## 28. 核心规则总结

- NKB 只存事实，不存规则和推理。
- 每条事实都必须有来源、版本、生效时间和批准状态。
- 规划中的事件不是已发生事件。
- 正文中的角色台词不是客观真相。
- 草稿不得直接更新正式 NKB。
- 已批准正文通过 Event 更新动态事实。
- WorldState 和 Assets 由 Event 派生，不直接手改。
- 重大事实变化必须人工批准。
- 所有 AI 对话通过 Candidate、Handoff 和 Knowledge Manager 交接。
- 只有通过初始化验收的 NKB 才能标记为唯一事实源。

---

## 知识链全景

这份规范补齐后，平台形成清晰的知识链：

```
项目原始资料 sources
        ↓ 提取（validate_nkb_sources.py 门禁）
候选事实 candidates
        ↓ 冲突与审批（Knowledge Manager）
K5 Events / 静态定义
        ↓ 投影
NKB 正式组件
        ↓ 供数
Context Engine
        ↓ 统一供给
不同 AI 对话统一使用
```

---

## 29. 既有架构强制边界

本规范是对既有架构的强化，不得与之冲突。以下两条边界为**强制约束**，任何 AI 对话、脚本、流程均不得绕过：

### 29.1 NKB 是唯一事实源

- NKB 是写作和审查的唯一事实源；
- 章节正文只负责**呈现**事实，而不是重复**定义**事实；
- 任何 NKB 事实的增删改，必须经由 §17 入库流程，禁止会话直接 `write` 覆盖 `NKB/*.yaml`。

### 29.2 Context Engine 的事实来源受限

- Context Engine 只能从**正式 NKB、规划卡、上一章衔接、伏笔状态、时间线和读者态**构建运行时上下文；
- 不得把 `sources/inbox/`、研究资料或聊天记录临时拼进 Prompt 充当事实；
- `sources/` 下的未批准文件（`status != approved`，且非 S4 规划类）不得进入 Context。

### 29.3 sources/ 受治理区约束

- `sources/` 是 NKB 的唯一事实输入端；AI 不得绕过 `sources/` 在 `txt/`、`outline/`（呈现层）或全项目范围内自由检索事实；
- 既有 `txt/`（正式章节呈现）、`outline/`（大纲呈现）等目录不属于事实源，其事实必须以正式形态映射到 `sources/manuscripts/`、`sources/outline/` 后方可入库；
- 任何进入 `sources/` 的文件必须满足 §19 质量门禁，否则 `validate_nkb_sources.py` 判 FAIL，不得进入提取流程。
