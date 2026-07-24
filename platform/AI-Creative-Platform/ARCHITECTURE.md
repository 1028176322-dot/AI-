# AI 创作体系总览（AI Creative Operating System）

> **定位**：AI 创作操作系统的**导航入口**。各层细节在对应文档，本文件只讲「分几层、谁管什么、怎么咬合、何时退出」。
> 体系演进：早期偏 **Result Driven（写完再查）** → 补全 **L1–L2（过程导向）** → 再补 **NKB 小说知识库（唯一事实源）+ L3 规划者 + Context Engine（运行时上下文）+ 编排器（调度）**，形成**可扩展、可维护、可自动化执行**的工程架构；本轮再补 **Context Engine 四能力（过滤/优先级/压缩/冲突解决）+ 能力层（6 Engine）+ Delta Review + NKB 版本/事件驱动 + Plugin + Artifact + L6 拆两层**，从「操作系统」升级为「运行平台」；**本轮再补运行时增强（稳定期重点·不增 Layer）**：能力编排器（控制逻辑移出 Workflow）/ Context Budget / NKB 派生数据 / 静态·动态评测分轨 / Plugin 版本 / Build 产物（可复现）/ 可观测性 / 统一契约 / 执行运行时——架构进入稳定期，重点转向运行时可执行性、可复现性与可演进性。

---

## 架构总图

```
                    ┌──────────────────────────────┐
                    │      Orchestrator 编排器       │  ← 最外层调度（不写，只调度）
                    │  读Knowledge·建Context·调各层  │     模型无关：Claude/GPT/Gemini/DeepSeek
                    │  决策 continue/end/human·自动停止│
                    └──────────────────────────────┘
                              │ 调度
   ┌─────────── 基础事实源（不参与流程编号）───────────┐
   │       NKB 小说知识库（唯一事实源 SSOT）            │
   │ K1正史 K2人物 K3时间线 K4世界态 K5事件 K6伏笔       │
   │ K7资源 K8术语 D1故事态 D2读者态 ＋ 知识图谱         │
   └───────────────────────────────────────────────────┘
                              │ 被读取
   L1 宪法 → L2 规范 → L3 规划者 → [Context Engine] → L4 Workflow → 能力层 → L5 Review → L6 反馈
        （规划卡＋Story Beat）（运行时上下文）  （组合 6 Engine 写正文）  （四支柱＋Delta）  （知识更新→系统更新）
                              ↑________ 反馈层回灌 ________│
```

---

## 组件清单

| 组件 | 名称 | 角色 | 文档 |
|------|------|------|------|
| 基础 | NKB 小说知识库 | 唯一事实源世界数据库（SSOT）＋ 派生数据 Derived（§2.3） | `NKB.md` |
| L1 | 宪法 | 什么**绝对不能违反** | `AI写作宪法.md` |
| L2 | 规范 | 怎样思考 / 生成 / 自检（8 层 + 决策树） | `AI写作规范.md` |
| L3 | 规划者 | 生成前先出**章节规划卡**（含 Story Beat） | `AI写作规划.md` |
| 支撑 | Context Engine | 组装**运行时上下文**（过滤/优先级/压缩/冲突解决＋ Token Budget；Workflow 统一读取） | `AI上下文引擎.md` |
| L4 | Workflow（执行） | 按规划卡 + 运行时上下文写正文（双对话四阶段）＋ Build 产物包（§3.1·可复现） | `流程体系_小说创作.md`（红线 `写作规则.md`） |
| 运行时 | 能力层（Capability） | 6 Engine（Character/Narrative/Dialogue/Battle/Emotion/Description），经**能力编排器**调度（Workflow 只发指令），不依赖单一模型 | `AI能力层.md` |
| L5 | Review（审查） | 四支柱检测 + 五阶段回归闭环 ＋ Delta Review ＋ 静态/动态评测分轨（§7.10） | `审查体系.md` ＋ `checks/` ＋ `profiles/` ＋ `tools/` |
| L6 | 反馈（经验反补） | Feedback → Knowledge Update（落 NKB 事件驱态）/ System Update（落规则·流程·脚本·Prompt） | `审查体系.md` §7.6 ／ `流程体系_小说创作.md` §2＋§6 |
| 外壳 | Orchestrator（配器） | 调度全部、自动停止 ＋ Plugin（模块可替换·带版本） | `AI编排器.md` |

> 注：原「五层」中的 流程/审查/反补 现对应 **L4 / L5 / L6**；新增 NKB（底座）+ L3 规划者 + Context Engine（支撑）+ 能力层（运行时）+ 编排器（外壳）。本轮新增 **能力编排器（在能力层内，控制逻辑移出 Workflow）** 与 **跨切面三平面（可观测性 / 统一契约 / 执行运行时，非 Layer）**。

---

## 跨切面运行时平面（非 Layer · 稳定期重点）

> 用户判定架构已进入**稳定期**：不再加 Layer，转而补齐**运行时（Runtime）能力**。以下三项为**跨切面平面**，依附于编排器与各层，**不进入 L1–L6 主栈**：

| 平面 | 角色 | 文档 |
|------|------|------|
| 可观测性 Observability | 指标→仪表盘，数据驱动优化（Loop次数/致命率/RI趋势/CI/修复率/Context大小/压缩比） | `AI可观测性.md` |
| 统一契约 Contract | 各层输入/输出边界契约，使 Plugin 真正可互换 | `AI契约.md` |
| 执行运行时 Execution Runtime | 检查点/缓存/恢复/重试/回滚，失败局部化 | `AI执行运行时.md` |

**本轮运行时增强清单（在既有层内深化，不新增层）**：
- **能力层** 增 **能力编排器**（§4）：Workflow 只发「写第 N 章」，由编排器决定何时调 Dialogue/Emotion/Description。
- **Context Engine** 增 **Token Budget**（§2.5）：总 32000 + 各块配额，压缩据此计算。
- **NKB** 增 **派生数据 Derived**（§2.3）：关系图/影响图/幂图由 K2/K5 自动派生。
- **Review** 增 **静态/动态评测分轨**（§7.10）：静态先行（近乎零 LLM），动态后行（需读者模拟）。
- **Orchestrator** 增 **Plugin 版本**（§6）：各模块带 version，回归可知谁升级。
- **Workflow** 的 Artifact 升级为 **Build 产物**（§3.1）：含 Build 标识（NKB版本/Context哈希/审查版本/引擎版本），任何章节可完全复现。

---

## 各层退出条件（统一 Exit Criteria）

| 从 → 到 | 退出条件 |
|---------|----------|
| L2 规范 → L3 规划 | 8 层 + 决策树（六问）全过 |
| L3 规划 → L4 Workflow | 规划卡五字段齐全且与NKB / 宪法 / 规范无冲突 |
| L4 Workflow → L5 Review | 草稿完成 ＋ 自评六问全 YES |
| L5 Review → L6 反馈 / Approved | 门禁 PASS（Fatal A/B 零 ＋ ES≥80 ＋ CI≥95% ＋ RI≥60 ＋ PI≥60） |
| L5 → 循环（修复） | 门禁失败 → Fix → Regression → 复验（受 MAX_LOOP=5 / Plateau 约束） |
| L6 反馈 → 结束 | Root Cause 定位 ＋ 沉淀完成（回灌各层） |

---

## 咬合关系（Interlock）

- **Process Driven（L2 规范 + L3 规划）**：问题在写前被预防，不产生。
- **Result Driven（L5 审查）**：写后兜底检测，漏网出不了门。
- **Knowledge（底座）**：写作与审查共读同一事实源，一致性有基准。
- **Orchestrator（外壳）**：把上述静态规则变成被统一调度的**运行时系统**——即 AI 创作操作系统。

---

## 与其他文档关系

- `审查参考.txt`：L5 审查标尺的原始 10 模块框架。
- `NKB.md`：地基（唯一事实源），本轮新增 **Version 版本化** ＋ **事件驱动态**（K4/K7 由 K5 派生可重放）。
- `AI上下文引擎.md`：原 Context Builder 升级为引擎，新增 **过滤 / 优先级 / 压缩 / 冲突解决** 四能力 ＋ **Token Budget（§2.5）**。
- `AI能力层.md`：本轮新增运行时能力层（6 Engine），经 **能力编排器** 决定调用顺序（§4，Workflow 只发指令）。
- `AI编排器.md`：本轮新增 **Plugin 机制**（模块可替换·带版本）。
- `审查体系.md`：本轮新增 **§7.9 Delta Review**（增量审查）＋ **§7.10 静态/动态评测分轨**。
- `流程体系_小说创作.md`：本轮新增 **§3.1 Build 产物包**（可复现·含 Build 标识）。
- `AI可观测性.md`：本轮新增跨切面 **可观测性** 平面（Workflow→指标→仪表盘）。
- `AI契约.md`：本轮新增跨切面 **统一契约** 平面（各层边界契约·Plugin 可互换）。
- `AI执行运行时.md`：本轮新增跨切面 **执行运行时** 平面（检查点/缓存/恢复/重试/回滚）。
- `checks/`：L5 检查项库（13 模块 + 读者子目录 + 量化指标）。
- `profiles/`：L5 模块权重（按类型切换）。
- `tools/`：L5 脚本落地（ID/WBU/CI/NH/重复4类/AI腔/SFS 计算，待建）。

---

## 演进标记

- **v4.3（流程闭环）**：L5 引入五阶段回归闭环 + 状态机 + 三层元闭环。
- **五层补全**：新增 L1 宪法 + L2 规范（过程 + 结果双驱动）。
- **操作系统化（上版）**：新增 NKB 小说知识库（唯一事实源，11 组件＋三准则）＋ L3 规划者 ＋ Context Builder（标准背景）＋ 编排器（调度 / 自动停止）；原 L3/L4/L5 流程/审查/反补 顺延为 L4/L5/L6。
- **运行平台化（本轮）**：① Context Engine 四能力（过滤/优先级/压缩/冲突解决）替代朴素拼接；② 新增能力层（Character/Narrative/Dialogue/Battle/Emotion/Description 六 Engine，由 Workflow 组合调用，不依赖单一模型）；③ Review 增 Delta Review（局部修改快审，按需全量）；④ NKB 加 Version ＋ 事件驱动态（World State 由 Event 派生，可回放）；⑤ 编排器加 Plugin（模块可替换）；⑥ Workflow 增 Artifact（正文＋规划＋上下文＋审查＋修复日志）；⑦ L6 反馈拆为 Feedback→Knowledge Update→System Update。
- **稳定期运行时深化（本轮·不增 Layer）**：① 能力层增 **能力编排器**（控制逻辑移出 Workflow）；② Context Engine 增 **Token Budget**；③ NKB 增 **派生数据 Derived**；④ Review 增 **静态/动态评测分轨**；⑤ Orchestrator Plugin 增 **版本**；⑥ Workflow Artifact 升级为 **Build 产物（可复现）**；⑦ 新增跨切面三平面 **可观测性 / 统一契约 / 执行运行时**（非 Layer）。系统从「能运行」升级为「可度量、可复现、可容错、可演进」。
