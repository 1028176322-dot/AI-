# 质量评分（Quality Score）设计稿

> 状态：设计稿（待确认后落地）
> 所属：Phase 2 第一阶段系统（推荐顺序 #2）
> 对接底座：任务系统（task_engine） / 审计（audit_log） / 契约注册表（registry/versions.yaml） / 角色权限（ROLE_REGISTRY + permissions.policy） / 工程校验（tools/logic_check.py）

---

## 1. 定位与价值

给定一份**已产出的内容制品**（一章正文 / 一个 NKB 对象 / 一份资产），在"进入评审 / 发布"之前算出一个**可复现、可比较的质量分**，并给出**门禁建议**（proceed / caution / block）。把"质量靠人肉读后感觉"升级为"平台可计算的硬性关卡"。

与现有底座的关系：
- **logic_check（tools/logic_check.py）**：已有 C1–C22 机械校验（硬伤/警告），是"零错误密度"的可计算来源 → 质量分的工程支柱。
- **契约注册表**：章节/资产各有 schema 契约（write/revision/asset），可校验结构合法性 → 质量分的结构支柱。
- **任务系统**：`task_engine` 的 `submit → reviewing → passed/completed` 是天然关卡位；质量分可作为 `submit` 的强制门（类比 Impact Analyzer 在 `claim/start` 前置预检）。
- **审计**：每次评分写 `audit/`，可追溯"某制品某次评分几何、为何被拦"。

与小说项目侧「审查体系」（docs/审查体系.md 四支柱）的关系：**四支柱审查是项目侧人工/LLM 深度评审**（专业编辑 ES / AI 工程 CI / 读者审查 Reader Index / 发布门禁）；本 Quality Score 是**平台侧的机器可计算关卡**，能消费四支柱产出的结构化审查报告（若存在），否则以"平台可计算指标"给出保底分并标注 `review_consumed: false`。二者是"保底门禁 + 深度评审"的互补，而非重复造轮子。

---

## 2. 信号源（评分器插件，registry 注册）

质量分 = 多个 **scorer 插件** 的加权融合。平台内置 4 个 scorer，均为零依赖、可复现：

| # | scorer | 信号来源 | 输出 | 默认权重 |
|---|--------|----------|------|----------|
| QS1 | `logic_scorer` | 运行 `tools/logic_check.py`（C1–C22） | 0–100（按错误密度降分）+ `fatal` 标记（C1–C6/C8/C11/C18–C20 硬伤=结构性致命） | 0.40 |
| QS2 | `contract_scorer` | 校验制品符合其 schema 契约（chapter/asset/nkb） | 0/100（结构合法即满分）+ `fatal` 标记（缺必填/非法枚举） | 0.20 |
| QS3 | `readability_scorer` | 机械可读性指标：句长方差、AI 腔锁词密度（WR-F10 锁词表）、信息密度代理（实词比） | 0–100 | 0.20 |
| QS4 | `review_scorer`（可选） | 消费项目四支柱审查报告（约定落点 `analysis/review/<ID>.yaml`，schema 另行定义） | 映射 ES/CI/Reader Index/PI → 0–100 | 0.20 |

**权重归一**：仅当 QS4 的审查报告存在时计入 0.20；否则 QS1–QS3 权重归一化为 1.0（logic 0.5 / contract 0.25 / readability 0.25），报告标 `review_consumed: false`（partial 评分，提示"仅工程保底，未含深度评审"）。

> 权重可按类型模板（`templates/<genre>/quality-profile.yaml`）覆盖，和审查体系 profiles 同机制；缺省用 xuanhuan 默认。

---

## 3. 评分算法

```
score(target):
  signals = []
  for s in registered_scorers:
      r = s.run(project_root, target)        # 每 scorer 独立、幂等
      signals.append(r)                        # {name, score, fatal, detail}
  fatal = any(r.fatal for r in signals)        # 任一结构性致命
  composite = weighted_mean(signals)           # 按 §2 权重归一
  gate = decide(composite, fatal)              # 见 §4
  report = render(target, signals, composite, gate)
  write_report(report)                         # analysis/quality/QUAL-*.yaml + audit
  return report
```

- **weighted_mean**：`Σ(score_i × w_i) / Σw_i`，仅对实际运行的 scorer 计权（QS4 缺失则归一其余）。
- **fatal**：任一 scorer 报 `fatal: true`（结构性致命，如 logic C 硬伤、契约缺必填）→ 直接 block，不看分数。
- **幂等**：同输入同输出；报告可重跑覆盖（`QUAL-<type>-<id>-NN` 递增，不覆盖历史）。

### 门禁逻辑（decide）
- 任一 scorer `fatal: true`（结构性致命，对齐审查体系 Fatal A）→ **block**（必须修复或 human_gate 放行）。
- `composite < HARD_FLOOR`（默认 60，可配）→ **block**（质量过低，不可进入评审/发布）。
- `HARD_FLOOR ≤ composite < TARGET`（默认 80，可配）→ **caution**（放行但标红，建议人工评审时重点看）。
- `composite ≥ TARGET` → **proceed**。

> 阈值对齐小说审查体系「发布门禁」精神（ES≥80 / CI≥95% / Reader Index≥60 / Fatal A/B 双零），但平台门是**可计算的近似**：logic_scorer 覆盖 CI 的零错误诉求，readability_scorer 覆盖读者流畅性，review_scorer（若有）补足 ES/Reader/PI。

---

## 4. 产物：质量报告（Quality Report）

落盘：`projects/<id>/analysis/quality/<REPORT-ID>.yaml`
ID 规则：`QUAL-<target_type>-<target_id>-NN`（如 `QUAL-chapter-042-01`）。

字段（契约草案见 §5）：
```
meta: { scorer, scored_at, project, target_ref }
target: { target_type, target_id, artifact_path }
signals:
  - { name: logic|contract|readability|review, score, fatal, weight, detail }
composite: { value: 0..100, review_consumed: true|false }
gate: { decision: proceed|caution|block, reasons: [..] }
recommendations:
  - { action: "fix"|"human_review"|create_task, target, detail }
```

示例（某章 logic 报 1 处 C21 警告、可读性偏低）：
```
signals:
  - { name: logic, score: 92, fatal: false, weight: 0.40 }
  - { name: contract, score: 100, fatal: false, weight: 0.20 }
  - { name: readability, score: 71, fatal: false, weight: 0.20 }
  - { name: review, score: 0, fatal: false, weight: 0.00 }   # 无审查报告
composite: { value: 89, review_consumed: false }
gate: { decision: caution, reasons: ["可读性 71 低于 TARGET 80（partial 评分，未含深度评审）"] }
recommendations:
  - { action: human_review, target: "042", detail: "可读性偏低，人工评审重点看句长/AI腔" }
```

---

## 5. 契约草案 `core/contracts/quality.schema.yaml`

（实现时严格遵循 `_yaml_lite` 约束：不用 `|` 块标量；列表 dict 项 dash 同行；空列表渲染 `key: []`）

```yaml
schema_id: quality
version: 1.0.0
applies_to: ["analysis/quality/*.yaml"]
description: 内容质量评分报告契约（Quality Score）
requires_document_header: false
top_level_sections:
  - name: meta
    required_fields: [scorer, scored_at, project]
  - name: target
    required_fields: [target_type, target_id]
  - name: signals
    required_fields: []
  - name: composite
    required_fields: [value]
  - name: gate
    required_fields: [decision]
nested_required:
  target: [target_type, target_id]
  composite: [value]
  gate: [decision]
decision_enum: [proceed, caution, block]
forbidden_patterns: ["TODO", "FIXME", "占位", "待补"]
```

---

## 6. 工具设计 `tools/quality_scorer.py`

复用：`_gov.load_yaml / dump_block / find_project`、`audit_log.record`、`task_engine.load_task`、`logic_check`（subprocess 或 import）。

API：
- `score(project_root, target_type, target_id, proposed_by="unknown")` → report dict；写 `analysis/quality/QUAL-*.yaml` + `audit_log.record(action="quality_score")`
- `score_task(project_root, task_id, **kw)` → 从任务解析 target（对齐 impact `analyze_task`）
- 内置 scorer 纯函数：`_score_logic / _score_contract / _score_readability / _score_review`，便于单测
- `decide(composite, fatal)` 纯函数

CLI（经 `platform_cli` 委托，REMAINDER 捕获自有参数）：
```
platform quality --score --target-type chapter --target-id 042
platform quality --from-task <TASK-ID>     # 评某任务制品（submit 前门禁）
platform quality --show <REPORT-ID>
```

scorer 注册：在 `registry/` 增 `scorers.yaml`（name → module/weight/enabled），`quality_scorer` 启动时加载；新 scorer 只需实现 `run(project_root, target) -> {score, fatal, detail}` 并登记。

---

## 7. 平台装配清单（落地时执行）

| 文件 | 改动 |
|------|------|
| `core/contracts/quality.schema.yaml` | 新增（§5 草案） |
| `tools/quality_scorer.py` | 新增 |
| `registry/scorers.yaml` | 新增（4 内置 scorer 注册 + 权重 + 启用） |
| `registry/versions.yaml` | `core:` 下加 `quality_scorer: 1.0.0`；`contract: 1.3.0 → 1.4.0` |
| `core/session/ROLE_REGISTRY.yaml` | 新增角色 `quality-scorer`（capabilities: [quality_score]，may_write: `analysis/quality/**`，may_not_write: core/registry/NKB/chapters/approved/tasks） |
| `core/policies/permissions.policy.yaml` | 新增 `quality-scorer` allow_write/deny_write |
| `tools/platform_cli.py` | `build_parser` 加 `quality`（REMAINDER）；`_delegate_gov` 加 `"quality":"quality_scorer"` |
| `tools/task_engine.py` | `submit` 前置质量门（gate=block 拒绝 submit，提示修复 / human_gate） |
| `projects/道法百年/AGENTS.md` | 新增规则：章类制品 `submit` 前须过质量门（block 必须修复或 human_gate） |

---

## 8. 与任务系统 / 审计 / 审查体系的衔接

- **任务系统**：`submit`（chapter_write / chapter_fix / continuity_fix）前自动跑 `score`；gate=block 则拒绝 submit 并提示修复点（或 human_gate 放行）。gate=caution 放行但附报告供评审重点看。报告中的 `recommendations[action=create_task]` 可建跟进修复任务（依赖被评任务）。
- **审计**：每次 `score` 写 `audit_log.record(action="quality_score", files=[报告相对路径], result=success/fail, detail="gate=block")`。
- **审查体系（docs/审查体系.md）**：QS4 `review_scorer` 为可选扩展——当项目产出结构化四支柱审查报告（`analysis/review/<ID>.yaml`）时消费其分，使平台门与项目深度评审对齐；本期可先交付 QS1–QS3 保底门，QS4 留接口。

---

## 9. 范围与边界（已知限制 + 待确认点）

**待确认点（请你拍板）：**
1. **评分输入融合策略**：
   - 方案 A（推荐）：融合「平台可计算指标（logic+contract+readability）＋ 可选消费项目四支柱审查报告（QS4）」。无报告时自动降级为 partial 评分。
   - 方案 B：仅平台可计算指标（QS1–QS3），不预留 QS4 消费接口（更简单，但拿不到深度评审分）。
   - 方案 C：仅消费项目四支柱审查报告（QS4 必填），无报告则无法评分（强依赖项目侧产出）。
2. **门禁接入点**：
   - 方案 A（推荐）：任务 `submit` 强制质量门（block 拦截 submit，须修复 / human_gate）；同时保留 `platform quality --score` 手动。
   - 方案 B：仅作按需手动工具，不接任务门禁（不阻断流程，只出报告）。
3. **报告落盘区** `analysis/quality/` 作为新增受治理区，是否 OK。
4. **角色名** `quality-scorer` 是否沿用此命名。

**已知限制：**
- QS3 `readability_scorer` 的"可读性"是机械代理（句长方差/AI腔锁词/实词比），非真实阅读体验；真实读者体验由审查体系 Reader Index + 读者模拟（Phase 2 #3）覆盖。
- QS4 `review_scorer` 依赖项目产出**结构化**审查报告；当前小说项目四支柱审查为 docs 形式，需另行定义 `analysis/review/` 报告 schema 才能被消费——属接口预留，不在本期强制实现。
- 跨项目质量横向比对不在本期范围（门禁只看单制品绝对分）。

---

## 10. 验收 DoD

- [ ] `core/contracts/quality.schema.yaml` 通过契约校验（无 `|` 块标量，字段齐全）。
- [ ] `platform quality --score --target-type chapter --target-id 042` 在测试项目产出 `analysis/quality/QUAL-*.yaml`，结构符合契约。
- [ ] 门禁正确：注入"logic 报 Fatal 硬伤"用例 → `block`；注入"低分"用例 → 低于 HARD_FLOOR 即 `block`、低于 TARGET 即 `caution`。
- [ ] QS4 缺失时 composite 标 `review_consumed: false` 且权重归一，无除零/误报。
- [ ] 每次评分写 `audit/`，`doctor` 无回归。
- [ ] 装配项（registry/versions 升 1.4.0、scorers.yaml、ROLE_REGISTRY、permissions、platform_cli 委托、task_engine submit 门、AGENTS 规则）全部落地。
- [ ] 端到端测试脚本清理，不纳入 git。

---

## 11. 落地步骤顺序（确认后执行）

1. 写 `core/contracts/quality.schema.yaml` + `registry/scorers.yaml`
2. 写 `tools/quality_scorer.py`（4 scorer + composite + decide + CLI）
3. 装配：registry/versions(1.4.0) / ROLE_REGISTRY / permissions / platform_cli 委托 / task_engine submit 门 / AGENTS 规则
4. 端到端验证（测试项目，覆盖 proceed/caution/block 三态 + QS4 缺失降级）
5. `doctor` 全 PASS → 本地提交（不 push，沿用本轮"进二阶段不推送"）
