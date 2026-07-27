# AI 能力层（Capability Layer · 运行时能力）

> **定位**：编排器 / Workflow 调用的**运行时能力模块**，位于 **L4 Workflow 与底层模型之间**。
>
> **本轮新增（系统最大缺口补完）**：原 Workflow 直接调「单一大模型生成一章」。现改为调**能力**——把对白 / 叙事 / 战斗 / 人物 / 情绪 / 描写封装为**可组合、可插拔的 Engine**。Workflow 不「直接写」，而是**组合能力**；任何模型都能调同一套能力（模型无关）。

---

## 1. 为什么需要能力层

| 旧模式 | 新模式（能力层） |
|--------|------------------|
| Workflow：「请生成第 N 章」→ 单一大模型 | Workflow：「写第 N 章」→ 能力编排器编排 Narrative＋Character＋Dialogue＋Battle＋Emotion＋Description 六引擎 |
| 质量取决于「单个模型强弱」 | 质量取决于「能力组合 + 每引擎可独立优化」 |
| 换模型 = 重写 Prompt | 换模型 = 换 `impl`（引擎实现），Workflow 不变 |

- **模型无关**：同一能力可由不同模型实现（通用大模型 / 专用叙事 AI / 专用对话 AI）。
- **可插拔**：升级某能力只换 `impl`，不动 Workflow 与编排器。
- **可独立评测**：每个 Engine 单独打分（对应 `checks/` 模块），短板可精准替换。

---

## 2. 能力契约（Capability Contract）

每个 Engine 以 Plugin 形式注册（与 `AI编排器.md` §6 一致），声明：

| 字段 | 说明 |
|------|------|
| `id` | 能力标识（capability.character / narrative / dialogue / battle / emotion / description） |
| `input` | 输入契约（情境 / 人物ID / Story Beat / 上下文） |
| `output` | 输出契约（片段 / 标注 / 建议） |
| `reads` | 读取的 NKB 组件（如 Character 读 K2） |
| `capability` | 提供的能力声明 |
| `impl` | 当前实现（可替换：原生 Prompt / 外部模型 / 脚本） |

---

## 3. 六引擎

### 3.1 Character Engine（人物引擎）
- **职责**：基于 `K2 人物` 生成 / 校验言行，防 OOC（对应 `checks/character` C1–C2）。
- **输入**：人物 ID ＋ 当前情境 ＋ NKB/K2（性格 / 价值观 / 不能做什么）。
- **输出**：符合人设的言行 / 决策建议；OOC 检测报告。
- **被谁调用**：Dialogue / Battle / Description 生成前先过 Character 约束。

### 3.2 Narrative Engine（叙事引擎）
- **职责**：节奏 / POV / 信息释放 / 场景切换 / 描写焦点（对应 `checks/narrative`）。
- **输入**：Story Beat（规划卡 §1.1）＋ 运行时上下文。
- **输出**：叙事结构建议 / 段落编排 / 节奏标注。

### 3.3 Dialogue Engine（对白引擎）
- **职责**：生成辨识度高、符合身份、推动剧情、无 AI 腔的台词（对应 `checks/dialogue`）。
- **输入**：说话人 ID（K2）＋ 情境 ＋ Character 约束。
- **输出**：台词 ＋ 潜台词标注；AI 腔检测。

### 3.4 Battle Engine（战斗引擎）
- **职责**：战力核算 / 战斗呈现（写结果不写过程）/ 资源因果（对应 `checks/battle` ＋ E3）。
- **输入**：双方属性（K2/K7）＋ 环境（K4）。
- **输出**：战斗结果 ＋ 爽感点 ＋ 资源 delta（经 Event 回写 NKB，见 `NKB.md` §2.2）。

### 3.5 Emotion Engine（情绪引擎）
- **职责**：情绪曲线控制 / 爽点密度 / 奖励感（对应 `checks/emotion` ＋ `reader/`）。
- **输入**：规划卡情绪曲线 ＋ 当前段落。
- **输出**：情绪标注 ＋ 章末钩子建议（B2）。

### 3.6 Description Engine（描写引擎）
- **职责**：五感 / 场景具体 / 时空锚点（对应 `checks` D2 ＋ E2）。
- **输入**：场景 ＋ 世界态（K4）。
- **输出**：描写片段（可嵌入正文）。

---

## 4. 能力编排器（Capability Orchestrator · 控制逻辑移出 Workflow）

> **本轮关键升级**：原 Workflow 仍「知道谁先谁后」——它直接编排 6 引擎调用顺序，把大量**控制逻辑压在 Workflow 里**，Workflow 难以简化。**现把「何时调哪个引擎」的控制权移交能力编排器**：Workflow 只发一句指令「写第 N 章」，由能力编排器依据 Story Beat ＋ 上下文，自行决定每个片段该调 Dialogue / Emotion / Description / Battle / Narrative / Character。Workflow 越来越薄。

**能力编排器的职责**：
- 输入：完整章节规划卡（场景类型、环境作用、叙事策略、开头/结尾设计）＋运行时上下文＋宪法/规范约束。
- 输出：**能力编排计划（Capability Composition Plan）**——逐场景标注主导/辅助手法、引擎组合、执行顺序和选择理由。
- 决策依据：场景类型、人物选择、环境功能、信息释放和读者目标，不允许所有章节套同一 Story Beat 模板。

| 场景类型 | 适配手法与主要能力 |
|----------|--------------------|
| action | 动作因果、空间清晰、环境压力、节奏加速；Narrative＋Character＋Battle＋Emotion＋Description |
| dialogue | 潜台词、权力变化、选择压力；Narrative＋Character＋Dialogue＋Emotion |
| investigation | 线索递进、公平线索、假设修正、有限视角；Narrative＋Character＋Description |
| exploration | 感官落地、空间路径、环境阻力；Narrative＋Description＋Character |
| emotional | 自由间接引语、具身情绪、余波；Character＋Emotion＋Narrative |
| business | 资源后果、过程压缩、博弈对白；Narrative＋Character＋Dialogue |
| training | 动作因果、资源代价、进步反馈；Character＋Battle＋Emotion |
| revelation | 对比揭露、延迟命名、公平证据；Narrative＋Character＋Emotion |
| transition | 时间压缩、省略、场景对照、余韵；Narrative＋Emotion＋Description |

开头根据第一场景选择行动中切入、后果、选择、对话冲突、发现、环境异常、情绪余波、
时间跳转等进入方式；结尾根据本章实际变化选择危机、揭露、决定、代价、兑现、余韵、
关系变化、新目标等收束方式，不再强制统一悬崖钩子。

> 编排器不写正文，只产出「编排计划」；确定性实现为
> `scripts/platform/writing_strategy.py`。各引擎按计划执行，正文提交时必须提供具体执行证据。

---

## 5. 与架构关系

```
L4 Workflow ──(发指令「写第N章」)──▶ 能力编排器 ──(编排计划)──▶ 能力层（6 Engine，经 Plugin 调用）
                              │ reads
                              ▼
                            NKB（K2/K4/K7…）
                              │
                              ▼ 模型（impl 可替换）
```
- Context Engine 为各 Engine 提供**过滤后、带优先级、已压缩、无冲突**的事实，避免引擎各读各的。
- 能力层是「运行能力」的核心落地——与 Context Engine、Delta Review 并列为本轮三大运行时升级。

---

## 6. 可插拔示例

- `capability.narrative.impl` 从「通用大模型」换「专用叙事模型」→ Workflow 编排不变。
- `capability.dialogue.impl` 换「专用对话模型」→ 对白质量提升，其余不动。
- `capability.battle.impl` 换「战力脚本 + 模板」→ 战斗数值严谨，不依赖模型发挥。

> 能力层让系统从「绑一个模型写」升级为「组合一套可替换能力写」——且**由能力编排器决定组合方式**，Workflow 只发指令。这是「AI 创作运行平台」区别于「创作流程」的关键。
