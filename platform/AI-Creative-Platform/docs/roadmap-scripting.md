# 脚本化架构路线图（Script-First Platform Redesign）

> 目标：把平台从「AI 全读全判」重构为「脚本负责确定性工作，AI 负责创造性与语义判断」。
> 本文档映射用户 22 节提案到平台现状，给出分阶段落地计划、目录决策与关键设计。

---

## 0. 核心原则

- **脚本负责确定性工作**：规则固定、结构明确、可计算/可校验的工作全部脚本化。
- **AI 负责语义与创造**：情节因果、人物动机、情绪成立、文风自然、文本创作与修复。
- **收益**：降低 Token 消耗 / 重复读取 / 提示词长度 / AI 漏步骤概率 / 会话执行差异 / 文件扫描范围。
- **分工铁律**：脚本筛选问题、准备证据、缩小范围 → AI 理解正文、判断问题、解释原因、提出修复 → 脚本验证结果、登记问题、推动流转。**脚本不替 AI 下质量结论，AI 不被脚本剥夺对正文的完整阅读与推理预算。**

---

## 1. 平台现状（已建能力，避免重复）

统一 CLI `platform_cli.py` 已存在 30+ 子命令，且 `task_engine.py` 已实现完整任务状态机。下表为提案各模块与现状的对应：

| 提案模块 | 现状 | 状态 |
|---|---|---|
| 统一 CLI `platform <domain> <action>` | `platform_cli.py`：bootstrap/doctor/check/list/init-project/session/perm/contract/gate/handoff/cwrite/nkb/init/charter/psrc/genesis/ready/status/task/ver/impact/quality/reader/memory/asset/model/projects/exp/bi/graph/market/compliance | ✅ 已建 |
| 任务状态机 | `task_engine.py`：create/claim/start/submit/review/complete/fail/retry/route/list/show/promote/ready_check + 7 模板带 `execution_policy` | ✅ 已建 |
| 单 Agent 策略（四层封锁） | `core/policies/agent-execution.policy.yaml` + AGENTS.md 强制段 + ROLE_REGISTRY tool_access 白名单 + agent_compliance_gate（doctor AgentGov 块） | ✅ 已建（Phase 5） |
| Level-1 脚本预检 → AI 语义审查 | `gate/contract/perm/ready` + `quality_scorer`（逻辑/契约/可读性）+ `reader_simulator` | ⚠️ 部分 |
| 审计 / 版本 / 报告 | `compliance_scan` + `operations/` manifest + `platform ver` + `bi/dashboard` + `doctor` | ⚠️ 部分 |
| Task Packet / Context Package | 仅 `session_bootstrap` 生成会话清单 | ❌ 缺口（最高价值） |
| Context Builder（预算过滤） | 无 | ❌ 缺口（最高价值） |
| Policy Compiler | 仅 AGENTS.md/契约原文，未编译 | ❌ 缺口 |
| NKB 查询/投影 | `platform nkb` 仅门禁校验，无 get/state/events/project | ❌ 缺口 |
| 文件/实体/章节索引 | doctor 临时扫，不持久化 | ❌ 缺口（地基） |
| 章节/卷滚动摘要 | 无 | ❌ 缺口 |
| Delta Review | 无 | ❌ 缺口 |
| 结构化 Review 报告 | 无（reader/quality 输出未标准化为 finding+evidence） | ❌ 缺口 |

**结论**：提案约 40% 已落地（CLI/任务机/单 Agent/分层审查/审计版本），缺口集中在**输入最小化工具链**（Packet/Context/Policy/NKB 查询/索引）与**审查管线增强**（预检事实/Delta/结构化报告/摘要）。

---

## 2. 目录结构决策

**不新建 `cli/` 与 `scripts/` 树**，扩展现有结构，复用已验证的状态机、pre-commit、doctor 接线：

```
AI-Creative-Platform/
├── tools/                      # 引擎（扩展，不新建 scripts/）
│   ├── platform_cli.py         # 统一 CLI（加 next/packet/context/policy/query/validate/index 子命令）
│   ├── task_engine.py          # 任务状态机（加 next_task）
│   ├── index_builder.py        # 【新】索引构建
│   ├── task_packet.py          # 【新】Task Packet
│   ├── context_builder.py      # 【新】Context Package + 预算
│   ├── policy_compiler.py      # 【新】Policy 编译
│   ├── nkb_query.py            # 【新】NKB 查询 + 投影
│   ├── validators.py           # 【新】Level-1 预检管线
│   ├── summary_builder.py      # 【新·Phase B】章节/卷滚动摘要
│   └── delta_review.py         # 【新·Phase B】Delta Review
├── core/
│   ├── policies/               # agent-execution.policy.yaml（已有）
│   ├── gates/                  # agent_compliance_gate.py（已有）+ ScriptGov（Phase A 接入）
│   └── contracts/              # 任务契约（已有，policy compile 的输入）
├── registry/                   # ROLE_REGISTRY.yaml（已有）
├── schemas/                    # 契约 schema（已有）
├── prompts/                    # 【新·Phase B】shared/roles/task-types 规则模板
├── templates/                  # 题材模板（已有 xuanhuan）
├── runtime/                    # 【新】派生产物（不入库或按需）
│   ├── indexes/                # files/entities/chapters/...json
│   ├── task-packets/           # TASK/{task.yaml,input-index.yaml,context.md,...}
│   ├── context/                # CTX-<task>-<n>.md
│   └── policies/               # <role>-<task>.compiled.yaml
└── docs/roadmap-scripting.md   # 本文档
```

---

## 3. 分阶段计划

### Phase A（本轮落地）—— 输入最小化工具链
优先级最高（直接降输入 Token）：
1. **索引地基** `index build` / `index find`：files/entities/chapters/terminology/events/dependencies JSON（runtime/indexes）。
2. `task next --role`：按角色找下一 ready 任务（复用 list_tasks+route+inputs_ready）。
3. `task packet TASK`：生成 Task Packet 六件套。
4. `context build --task --budget`：相关性/角色/章节/时间过滤 + 预算分配 → 最小 Context Package。
5. `policy compile --task`：编译最小规则集（must/must_not）。
6. `nkb query`：get/state/events/foreshadow/reader-known/project + 事件溯源投影。
7. `validate`：Level-1 预检管线（schema/ids/references/timeline/frontmatter/chapter_length/terminology/task_compliance/permissions/runtime_policy）。

### Phase B —— 审查管线增强
- `summary_builder`：章节结构化摘要（AI 填契约字段→脚本落盘）+ 卷/弧/滚动摘要。
- `delta_review`：`diff chapter --from --to` 输出 changed_ranges + affected_entities/rules。
- 结构化 Review 报告 schema（finding: id/category/severity/location/observation/evidence/reasoning/impact/recommended_fix）+ 单 Agent 多阶段审查计划（immersive→structural→character→continuity→synthesis）。
- `validate` 预检与 Review Contract 对接，预检事实直接喂 AI 深度审查。

### Phase C —— 维护成本降低
- 项目初始化脚本完善（`apply-template` 题材注入、`project doctor` 标准化健康块）。
- 版本/审计生成器（`snapshot/rollback/compare_versions`、`audit_report`）。
- 状态派生（`update_project_status` 从任务/NKB 派生，不手填）。
- 报告生成器（`report project-status/chapter-quality/open-foreshadow/task-progress/nkb-health`）。
- terminology 全量词表检查接入 NKB Terminology。

---

## 4. 关键设计决策

### 4.1 Context 预算算法（Phase A3）
- 预算读项目 `context.budget.yaml`，默认分配（total=12000）：
  - task 500 / chapter_plan 1800 / characters 2200 / world_state 1400 / recent_events 1500 / foreshadow 1000 / previous_summary 1800 / constraints 800 / reserve 1000。
- 超预算降级顺序：删低相关内容 → 用摘要替代原文 → 保留最高权威事实 → 保留当前章节直接相关项。
- 写作 Context ≠ 审查 Context：审查包额外含完整正文 + 脚本预检报告 + 前后章（见 §4.5）。

### 4.2 NKB 投影引擎（Phase A5）
- 事件溯源：Events → CharacterState/WorldState/AssetState/RelationshipState/ReaderState/Timeline。
- `nkb project assets CHR-001 --at EVT-035` 通过重放该角色相关事件推导持有物品。
- 仅返回任务所需；语义冲突仍交 AI/人工。

### 4.3 索引持久化（Phase A0）
- 落 `runtime/indexes/`，属派生可重生产物。建议：**提交 NKB 与 summaries（事实源），gitignore 纯派生索引**（regenerable）。
- `detect_latest_version` 通过 manifest 的 canonical_version 判定，杜绝 AI 自行猜 `CH020_final_new.md`。

### 4.4 摘要生成（Phase B）
- 章节结构化摘要（plot/character_changes/new_events/new_information/open_threads）属语义内容，**由 AI 在任务产出契约里填写，脚本落盘 `summaries/`**；脚本不反向从正文抽语义。

### 4.5 审查三层模型（Phase B 落地）
- L1 脚本预检：字数/章节号/标题/ID/Front Matter/YAML/引号标点/数值冲突/不存在实体/越权/ NKB 版本过期 → 输出**事实**不输出质量分。
- L2 AI 深度审查（单 Agent 多阶段串行）：immersive_read → structural → character → continuity → synthesis。
- L3 脚本后处理：校验报告 schema / 去重 / 登记 Issue / 建修复任务 / 绑定行号 / Delta Review / 更新质量指标。

---

## 5. Token 优化目标

| 维度 | 现状（每次任务） | 目标 |
|---|---|---|
| 输入 Token | 30,000–100,000（读全平台规范+NKB+全人物+全大纲+历史章节+任务记录） | 8,000–20,000 |
| AI 读取 | 整个项目 | 1 Task + 1 精简 Contract + 1 编译 Policy + 1 Context Package + 1–2 前章摘要 |
| AI 职责 | 找文件/组文件/记流程/维护状态/机械校验 | 仅语言理解与创造力 |

---

## 6. 约束与风险

- `_yaml_lite` 约束：不支持 `>-` 折叠标量、不支持多行流列表、Python 无法 `import` 连字符文件名（模块用下划线）。所有新增 YAML 用单行纯标量。
- 宿主 WorkBuddy 的 `Agent` 工具由宿主运行时控制，平台 YAML 无法物理移除；靠 AGENTS.md 规则 + 会话锁 + 合规门禁 + 自我约束保障（同 Phase 5 声明）。
- 所有新增能力须带 e2e 测试 + 接入 doctor（新增 ScriptGov 块），保持 Phase 4 零回归。

---

*路线图初版：2026-07-25 · 对应提案 22 节，确认整合方式=扩展现有 CLI+引擎，本轮落地 Phase A。*
