# AI 编排器（Orchestrator · 配器）

> **定位**：最外层**调度器（Scheduler）**，包裹整个创作操作系统。
> **不写小说，只调度。** 模型无关：Claude / GPT / Gemini / DeepSeek 均经编排器调用，而非用多个 Prompt 串联。
> 用户评价：「唯一真正还能提升档次的层」——把规则变成被调度的系统。

---

## 1. 职责

- **读 Knowledge**：从 `NKB.md` 取事实源。
- **建 Context**：调 `AI上下文引擎.md`（Context Engine）生成运行时上下文。
- **调 Planning**：调 `AI写作规划.md`（L3）出规划卡。
- **调 Workflow**：调 `流程体系_小说创作.md`（L4）生成草稿。
- **调 Review**：调 `审查体系.md`（L5）四支柱检测。
- **调 Fix + Regression**：驱动 `审查体系.md` §7 五阶段回归闭环（修复 → 回归审查 → 复验）。
- **决策**：continue / end / human。
- **调 Plugin Registry**：各层经 Plugin 接口调用（见 §6），实现可替换、不写死。

---

## 2. 主循环（驱动审查体系 §7 的 Loop Engine）

```
read Knowledge
  → build Context (Context Engine)
  → plan (L3)
  → write (L4) ──▶ 状态: Draft
  → review (L5) ──▶ 状态: Reviewing
  → if 门禁失败 (Fatal / ES<80 / CI<95 / RI<60 / PI<60):
        fix (工程/编辑/读者三分) ──▶ 状态: Fixing
        regression (只查修复引入的新问题) ──▶ 状态: Regression
        re-review
        loop (受自动停止约束)
  → if 门禁 PASS: Approved → Published
```

> 循环由**门禁决定结束**，不由人喊停（守 `审查体系.md` §7 Review Loop Engine）。

---

## 3. 自动停止条件（Auto-Stop）

防止「AI 一直修、一直修」死循环：

- **MAX_LOOP = 5**：超过 5 轮强制停止。
- **Plateau 规则**：问题数须**单调下降**（如 35→12→6→…）；若连续 2 轮不降（如 loop3=6, loop4=6）→ **立即停止，标记人工介入**。
- **人工介入信号**：触发停止时输出「停滞报告」（各轮问题数 / 卡住的问题类型 / 建议人工决策点），交用户。

```
loop1: 35
loop2: 12
loop3: 6
loop4: 6  ← 不降
→ 停止 → 人工介入
```

---

## 4. 模型无关（Model-Agnostic）

- 编排器持有：循环 / 状态机 / 决策 / 自动停止。
- 具体「生成 / 审查 / 修复」由被调模型执行；换模型只换被调方，编排逻辑不变。
- Prompt 不再是「串联脚本」，而是「被编排器调用的能力单元」。

---

## 5. 与各层关系

```
                    ┌─────────────────────────────┐
                    │        Orchestrator          │
                    │  (读/建/调/决策/自动停止)     │
                    └─────────────────────────────┘
                       ↓ 调度
NKB → L1宪法 → L2规范 → L3规划 → L4 Workflow → L5 Review → L6反馈
                       ↑________ 反馈层回灌 ________│
```

## 6. Plugin 机制（模块可替换 · 不写死）

> **本轮新增**：编排器不应把「调用哪一层、用哪个实现」写死。任何模块都应可替换为另一种实现（如未来换专用叙事 AI / 阅读 AI），而不动编排逻辑——这是「可扩展性 10/10」的落地机制。

**Plugin 契约**：每个被调模块以 Plugin 形式注册，声明：

| 字段 | 说明 |
|------|------|
| `id` | 模块标识（planner / context / workflow / capability.* / review / feedback） |
| `input` | 输入契约 |
| `output` | 输出契约 |
| `capability` | 提供的能力声明 |
| `impl` | 当前实现（可替换：原生 Prompt / 外部模型 / 脚本） |
| `version` | 当前版本（如 `planner v2.1` / `capability.dialogue v3.4`），回归可知谁升级 |

**调度链（Plugin 化）**：
```
Orchestrator
  → Plugin(planner)    → L3 规划卡
  → Plugin(context)    → 运行时上下文（Context Engine）
  → Plugin(workflow)   → 草稿（内部再调 capability.* Plugin）
  → Plugin(review)     → 四支柱评分（含 Delta Review）
  → Plugin(feedback)   → 知识更新 / 系统更新
```
任一 `Plugin(x).impl` 可热替换（如 `review.impl = 阅读AI-v2`），编排逻辑不变。每个 Plugin 带 `version` 字段（如 `planner v2.1` / `capability.dialogue v3.4`），回 regression 时即可定位「是哪次升级引入了行为变化」——这是 Plugin 可替换后仍能**追溯回归**的关键（见 §6 示例）。

**示例（未来扩展）**：
- `capability.narrative.impl` 从「通用大模型」换「专用叙事模型」→ Workflow 组合调用不变。
- `review.impl` 从「通用审查」换「阅读 AI 专用审查」→ 门禁逻辑不变。
- `context.impl` 从「朴素拼接」换「带向量检索的 Context Engine」→ 上游下游不变。

> Plugin 让系统从「绑定实现」升级为「绑定契约」——扩展新能力只加 Plugin，不改编排器。

---

> 编排器让「宪法/规范/规划/流程/审查/反补」从静态规则变成**被统一调度的运行时系统**——即用户所称的「AI 创作操作系统」；Plugin 机制进一步使其成为**可替换实现的运行平台**。
