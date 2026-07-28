# 风格系统与去 AI 味实施纲要（v5.1 · 设计审查六轮修正 · 冻结基线）

> 适用范围：AI-Creative-Platform（`platform/AI-Creative-Platform`）
> 文档性质：**独立 SSOT**（完整复述四条原始原则、L0–L4 定义与存储表、与现有闭环的复用关系）
> 状态：v5.1（**架构方向审查已通过；六轮审查后补齐唯一剩余阻断——`protected-manifest` 生产者——正式冻结为实施基线；后续问题进 schema/测试/代码任务，不膨胀主文档**；当前未改代码、未提交、未推送）
> 配套代码（现状核验见 §0，全部绑定至 `baseline_commit`）：`scripts/learning/reference_learning.py`、`scripts/learning/feedback_learning.py`、`scripts/platform/writing_strategy.py`、`core/contracts/nkb-components.schema.yaml`、`core/contracts/project-layout.schema.yaml`
> 配套规范：`core/learning/自主学习与反馈闭环.md`
> 当前实施状态：`core/learning/风格系统实施状态.md`（本冻结文档是设计 SSOT，不是完成报告）

---

## 0. 现状核验（立项前证据 · 绑定基线提交）

核验时间：2026-07-27。**所有文件指纹、符号检查均绑定至同一基线提交**，避免"本地 HEAD 落后远端导致证据过期"（审查·HR4）。

- 远程：`git@github.com:1028176322-dot/AI-.git`（`origin`）；分支：`main`
- **`baseline_commit: 663b80de1d94b38daf250c25a2e5ffdecf017629`**（远端 `origin/main` HEAD；命令 `git ls-remote origin main` 与 `git fetch origin main` 后确认）
- 本地工作树 HEAD：`4c299f095c5ec2838cee8cd71d297e3fe666f664`（落后基线，符合"平台七批改造已并入 main、此后 main 另有推进"；本纲要仅修订设计）

**关键文件指纹（命令 `git show <baseline_commit>:<path> | sha256sum`，SHA-256）**

| 文件 | SHA-256 @ baseline |
|---|---|
| `scripts/learning/reference_learning.py` | `9a2f4d1a2ea80be03e0c649a8f9c16331a1a3b90418084e43fba2d5646aa92c2` |
| `scripts/learning/feedback_learning.py` | `9d1293c44cb315314fec97c580f72930b4bcf3190b4cf588c73ace80480f6c88` |
| `scripts/platform/writing_strategy.py` | `2e7e9a00323684fd5b0879a4cfafeb5a82ceca5f2eedbb0dd222f79e1e44c809` |
| `core/contracts/nkb-components.schema.yaml` | `b52d1386f914d2ba765aa45e94fa63ef45e6e4264f19488e64d95f67f80efc30` |
| `core/contracts/project-layout.schema.yaml` | `31897c9b043043805693d801915c05b1d15abe249e76c92522891e0d4c392143` |

**符号检查（命令 `git show <baseline_commit>:<path> | grep -nE <symbol>`，行号为基线提交内位置，仅辅助定位）**

| 核验项 | 符号（文件） | 基线内位置 | 结论 |
|---|---|---|---|
| 参考学习仅表层统计 | `_metrics` / `_derive_candidates` / `raw_text_stored`（`reference_learning.py`） | L120 / L189 / L253 | 只统计 + 不存原文（`raw_text_stored: False`），缺决策级参数 |
| 审查反补 14 类 | `CATEGORY_GUIDANCE`（`feedback_learning.py`） | L21 | F1/F3 可复用其分类与回归 |
| 手法层 9 场景 | `TECHNIQUE_COMPATIBILITY`（`writing_strategy.py`） | L22 | 与风格语言层正交 |
| NKB 无风格位 | 14 组件键（`nkb-components.schema.yaml`） | L16–L53 | `Canon/Characters/Locations/Organizations/Timeline/WorldState/Events/Foreshadow/Assets/Terminology/StoryState/ReaderState/Graph/Derived`，**无 Style 组件** |

**平台健康度（命令 `selfcheck` / `doctor --quick`）**

> ⚠️ 以下数值运行于**本地工作树**（HEAD `4c299f09`，即 baseline 的父提交侧）；审查指出"健康检查仍待基线复跑"。**立项前须在 `baseline_commit` 检出一个干净工作树再复跑确认**，本版不声称已通过基线复跑。
- `selfcheck`（本地工作树）：`Platform Selfcheck: proceed errors=0 warnings=0`
- `doctor --quick`（本地工作树）：`PlatformGov 健康分 100`；项目 `./projects/道法百年` 全部 `[PASS]`（仅 `QuickMode` 跳过内容型深度体检，预期）；`MemoryGov/ModelGov/MultiProjGov/ExpGov/BI` 均 `100`。

**本版状态**：已针对六轮审查（v1→v2→v3→v4→v5→v5.1）的全部阻断与高风险项修订；唯一剩余的「`protected-manifest` 无生产者」阻断已在审查六补齐（新增 `protected-manifest-build` 任务 + `MANIFEST_BUILDING/READY/CONFLICT` 状态）。审查结论：可正式冻结为实施基线，**分两级放行**（见 §12），当前设计完整度自评约 **96%**。

---

## 1. 设计原则（硬约束 · 完整复述）

**四条原始原则**
1. **不复制原文**：`raw_text_stored: False`、`copyright_policy: statistics_and_principles_only`；只存结构统计、节奏信号与抽象原则。
2. **风格卡不入 NKB**：NKB 14 组件是 SSOT 事实库且**无风格位**；红线 `forbidden: [NKB/**]`。风格卡独立存于 `learning/` + `runtime/learning/`；L3 角色语言层**只读引用** `NKB.Characters.speech`。
3. **复用现有闭环**：F1/F3 复用 `feedback_learning.py` 的「签名→约束→回归」；结构/叙事手法层复用 `writing_strategy.py`；全文走任务系统四支柱。
4. **治理兼容**：新增任务/目录/字段/写权限经 `system_maintenance` 立项，并在 `PROJECT_LAYOUT` 登记；**正文写必须收口到统一受控写原语（§2.4），且该原语须建立真正的权限隔离（broker / OS ACL / 子进程沙箱），不绕过任务系统与 CLI**。

**五条新增原则**
5. **候选稿模式**：风格修订只写 `revision-candidate`（章节正文候选稿，存于 `analysis/style/<chapter>/<task>/`），**绝不覆盖当前草稿**；应用须经受控 `chapter-apply-revision`。
6. **不可变保真基线（非唯一真相）**：`protected-manifest` 由 NKB 硬事实 + 章纲硬要求 + 当前草稿新增事实合成，是本次修订的不可变比较基线，**不得凌驾于 NKB**。
7. **指纹而非原文**：参考与候选均存不可逆指纹；指纹密钥不进 Git/日志/profile。
8. **指标三分法**：硬门禁 / 质量评分 / 人工反馈，不混用（§6）；质量门禁须版本化阈值（§6）。
9. **冲突确定性**：以"约束类型 + 作用域 + 显式授权"决策，按**字段与作用域**定优先级，无"简单叠加默认"或"固定全局 L2>L3"（§2.1）。

---

## 2. 总体架构

### 2.1 五层风格体系 + 冲突决策（吸收审查四·问题11-HR1/HR2/HR6/HR7）

**风格卡结构（每层同构；不复制平台治理，仅引用）**
```yaml
project_constraints:      # 列表；用户/项目明确批准后才成为硬约束（L0）
style_preferences:        # 列表；参考学习产生的风格倾向（soft）
style_targets:            # 列表；统计目标区间，非强制值
conflict_policy:
suppressed_rules:
example_rules:            # 每条带 example_origin（禁止参考原句）
governance_policy_ref:    # 引用平台治理策略文件/模块（由平台代码定义）
governance_policy_sha256: # 平台治理策略快照哈希（不复制治理规则进卡）
```
> **不把 `governance_constraints` 放进风格卡**（吸收问题11-HR6）：治理规则由平台代码定义，风格卡只持有 `project_constraints/style_preferences/style_targets` 三类可配置项，运行时通过 `governance_policy_ref + governance_policy_sha256` 引用平台治理策略。

**每条规则自带 `scope`（取消独立 `scoped_constraints` 字段，避免第二套字段体系）**
```yaml
- rule_id: ...
  scope:
    content_type: narration | dialogue | both
    scene_types: [...]        # 空 = 全场景
    character_ids: [...]      # 空 = 不适用
    span_selector: <optional> # 指定正文 span
  value: ...
```

**L0–L4 定义与存储表（独立 SSOT）**

| 层 | 名称 | 作用 | 存储位置 | 生成来源 |
|---|---|---|---|---|
| L0 | 项目总风格 | 时代感、叙述温度、语言边界 | `memory/project/style-library/project-style.card.yaml` | 用户/项目批准（`project_constraints`） |
| L1 | 题材风格 | 历史/玄幻/悬疑/都市等基础语域 | `memory/project/style-library/genre/<genre>.card.yaml` | 内置原型 + 项目覆盖 |
| L2 | 场景风格 | 战斗/对话/探索/日常/感情/说明 | `memory/project/style-library/scene/<scene>.card.yaml` | 参考提取（style_preferences/targets） |
| L3 | 角色语言 | 每角色词汇/句式/语气/沉默方式 | `NKB.Characters.speech`（只读引用）+ `memory/project/style-library/character/<id>.card.yaml` | NKB 事实 + 角色卡覆盖 |
| L4 | 作者个人风格 | 据作者修改稿持续学习 | `memory/project/style-library/author.card.yaml` | 作者反馈晋升（审核后） |

**实际调用组合式（运行时）**
```
runtime/learning/style-guidance.yaml =
  L0 项目硬边界 + L1 题材默认值 + L2 场景规则 + L3 角色语言 + L4 作者偏好
  + 当前 writing_strategy 手法层输出 + 本次待修 AI 问题（F1 diagnosis）
```

**冲突决策（约束类型 + 作用域 + 显式授权；按字段与作用域定优先级，非全局固定）**
```
不可被风格覆盖（硬）：
  (a) NKB 硬事实
  (b) 平台治理约束（governance_constraints：POV 不越界、禁改人名）
  (c) 当前明确批准的任务内容要求（章纲 / 审查指令）

可被风格配置但受层级约束（软/目标）：
  (d) 项目风格约束（L0 project_constraints）
  (e) 场景/角色/作者/题材偏好（L2/L3/L4/L1 的 style_preferences/style_targets）

按字段与作用域决定优先级（不再设全局 L2>L3，吸收问题11-HR7）：
  - 角色对白字段：L3 > L2（角色说话方式比场景句式更具体，如战斗场景"全用短句"不得抹掉角色一贯口吻）
  - 旁白与整体节奏字段：L2 生效，L3 不参（角色语言卡 scope.content_type=dialogue，不作用于旁白）
  - 题材默认（L1）仅作最低优先级兜底
  - 每条规则仅在其 scope（content_type/scene_types/character_ids）内生效
```

**显式覆盖必须记录**（解决"场景局部覆盖项目规则"合法性）：
```yaml
override_rule_id: <被覆盖规则 id>
override_scope: { scene_types: [...], character_ids: [...] }
authorized_by: <reviewer_id/role>
reason: <文本>
expires_after_task: true        # 任务结束自动失效
```

**冲突示例的确定性答案**
- 项目要求古雅 vs 作者偏好口语 → 古雅为 L0 `project_constraints`（硬边界）；口语仅在 `style_preferences` 作软倾向，且不得覆盖古雅（除非有 `expires_after_task` 的显式 override 记录）。
- 场景卡短句 vs 角色卡长句 → **取决于字段**：角色对白字段中，**L3 角色卡优先于 L2 场景卡**；旁白节奏字段由 **L2 场景卡优先，L4 作者偏好作为低优先级倾向**；**L3 角色语言卡不参与旁白**（作者风格通常影响旁白，但角色对白方式不溢出至旁白）。
- 角色语言卡能否影响旁白 → 不能；L3 规则的 `scope.content_type` 限定为 `dialogue`。
- "禁止解释情绪" vs 某场景需直接交代 → 该场景 `scope` 局部覆盖，记入 `suppressed_rules` 与原因，必要时登记 `override`。

### 2.2 参考治理（吸收审查·问题5 / 问题7 / 问题10 / 问题11-HR5）

- **指纹（确定性方案）**：
  1. 正文做 **HMAC-SHA256 shingles**（k-shingle → HMAC，使用 `key_id` 标识的密钥；**非普通加盐哈希**）。
  2. shingles 经 **MinHash** 得 source signature；保存 `source_contribution_vector`（每来源独立贡献权重），供撤回重算。
  3. 摘要存 `source_digest`（SHA-256 全本）+ MinHash signature + 许可类型。
- **密钥存储（吸收问题11-HR5：不放项目 `secrets/`）**：密钥**不落项目目录**（即便 `.gitignore` 也可能误提交/备份/被同项目进程读取）。改为：
  - 环境变量注入 / 操作系统钥匙圈 / 独立 Secrets Manager；
  - 项目只存 `key_id`（不存密钥文件）。
  - **密钥轮换且原文已删除时**：无法重新取回原文，只能**废弃旧指纹**，不得承诺重算；新建指纹须重新导入原文（或放弃该来源贡献）。
- **来源数量与权重**（恢复，供 §2.3 引用；单一来源不得主导，否则退化为模仿单部作品）：
  - `minimum_independent_sources: 3`（低于此不形成通用原型）
  - `recommended_independent_sources: 5`
  - `max_single_source_weight: 0.4`
- **撤回/删除级联失效**：source 失效 → 删除其 `source_contribution_vector` 并重算 archetype，相关 profile 标记 `revoked`。
- **指纹比对**：候选正文生成同构 HMAC/MinHash 指纹，与参考指纹比较相似度；**绝不把原始 n-gram 写入 profile**。
- **正反例规则**：禁止参考原句；只存抽象规则或系统生成短例句；每条 `example` 带 `example_origin` ∈ `system-generated | user-owned | public-domain | licensed`。

### 2.3 提取方法定义（吸收审查·问题6 / 问题11）

**每条风格规则字段（候选）**
```yaml
rule_id:
scope:                     # 见 §2.1
rule_class: style_preference | style_target | candidate_project_constraint   # 绝不含 hard
value:
confidence:
confidence_source:        # 见下，禁用模型自报
evidence_count:
eligible_scenes:
source_count:
max_single_source_weight:
source_contribution_vector:
extractor_version:
model_id:
prompt_hash:
schema_version:
review_status: extracted | review_pending | approved | rejected
```

**置信度来源（问题11：不直接采用模型自报）**——`confidence` 须由以下**可计算**信号合成：
- 跨章节重复出现程度；跨来源一致程度；同一提取器重复运行一致性；可计算统计支持（置信区间/分布检验）；人工审核结果。
- 来源数量与权重（见 §2.2「来源数量与权重」）：`minimum_independent_sources: 3`、`recommended_independent_sources: 5`、`max_single_source_weight: 0.4`；单一来源权重不得主导，`source_count` 应达建议值方形成通用原型。

**提取器契约**：`style_extract` **只允许生成** `style_preferences` / `style_targets` / `candidate_project_constraints`；硬约束由平台代码定义，绝不来自参考学习（见 §2.10）。

### 2.4 三功能 + 候选稿模式 + 受控写原语（吸收审查四·问题11-B2/问题11-HR6）

**两类"候选"命名统一（避免混淆）**
- `revision-candidate`：章节正文候选稿（来自 style-revise），存于 `analysis/style/<chapter>/<task>/revision-candidate.md`。
- `style-rule-candidate`：从小说提取出的待审批风格规则（来自 style_extract）。

**受控写原语（真正不可绕过，吸收问题11-B2 "底层脚本仍可绕过"）**
- 普通任务进程对 `chapters/drafts/` 与 `chapters/approved/` **仅有读权限**；所有正文写入**收口到唯一原语 `controlled_chapter_writer`**。
- `controlled_chapter_writer` 以**独立身份/权限**运行（三选一隔离方案：**独立 Broker 服务** / **子进程沙箱** / **OS ACL**），仅当 capability + CAS + 状态 + 路径校验全部通过才写入并记录事件。
> 若 Broker 与章节脚本同属一个系统账户、拥有相同文件权限，则仅为"治理约束"而非"不可绕过"——实现**必须**选取上述三种隔离方案之一建立真实权限边界。
- 调用链：`chapter script → request capability → controlled_chapter_writer(broker) → authorize() + 校验 → atomic compare-and-swap write → append event log`。
- 能力令牌（短期）：结构以 §2.8 **多资源 capability 契约为唯一 SSOT**（绑定 task/session/chapter + 多资源 `expected_sha256` + nonce + single_use + signature）；`apply/rollback/publish` 均使用 **CAS**（读当前草稿 sha == 期望哈希才写入临时再 rename）。
- **扫描测试仅兜底**：禁止脚本直接 `open(..., "w")`/`Path.write_text`/`os.open`/`shutil.copyfile` 写 `chapters/`，但真正的不可绕过依赖 broker/ACL 隔离（见上），不靠扫描测试独立保证。

**正文写权限精确表（吸收审查·问题1）**

| 任务 | 允许写入 | 经受控写原语 |
|---|---|---|
| `chapter_write` | 新建指定章节草稿（`chapters/drafts/`） | 是 |
| `chapter_fix` | 修改指定章节草稿（结构性问题） | 是 |
| `chapter-apply-revision` | **唯一**将已批准 `revision-candidate` 应用到草稿（受控，绑定 `APPLY_READY` + 哈希） | 是（CAS） |
| `chapter-rollback-revision` | **唯一**恢复 `pre_apply` 草稿版本（受控，回滚专用） | 是（CAS） |
| `chapter-publish` | **唯一**写 `chapters/approved/**` | 是（CAS） |
| `final-regression` | **只读**，禁止写草稿/正式章节 | 否 |
| `style-revise` | 写 `analysis/style/<chapter>/<task>/revision-candidate.md`（**非** `chapters/`，不须经 `controlled_chapter_writer`） | 否（analysis 为分析产物目录） |
| `protected-manifest-build` | **唯一生成** `protected-manifest` 的任务；写 `analysis/style/<chapter>/<task>/protected-manifest.yaml`（**非** `chapters/`） | 否（analysis 为分析产物目录） |
| 其他风格任务（ai-diagnose / fidelity-review / style-quality-review / style-rule-review / style-rule-promote 等） | **禁止**写草稿与正式章节 | — |

> 精确表述：`chapter-apply-revision` 唯一应用候选到草稿；`chapter-rollback-revision` 唯一直滚；`chapter-publish` 唯一写正式章节；三者**均不互相拥有**对方的写权限。`chapters/` 目录只保留 `drafts/` 与 `approved/` 两级，候选稿归入 `analysis/style/`。

**三功能**
- **F1 ai-diagnose**（"风格风险诊断"）：只读草稿 + NKB，输出 `diagnosis-report`，不改正文。
- **F2 style-revise**：只写 `revision-candidate` 到 `analysis/style/<chapter_id>/<task_id>/revision-candidate.md`，绑定原草稿 SHA-256；草稿变化 → 候选 `STALE`；不写 `chapters/drafts/`。
- **F3 fidelity-review**：以 `protected-manifest` 为不可变基线。
- 新增 **style-quality-review**、**final-regression**（只读）、**chapter-apply-revision**、**chapter-rollback-revision**。

**权限红线**：风格任务 `forbidden: [NKB/**, chapters/approved/**, platform/memory/**]`。

### 2.5 保真基线 protected-manifest（吸收审查·问题2 / 问题8）

**唯一存储位置**
```
analysis/style/<chapter_id>/<task_id>/protected-manifest.yaml   # 唯一 SSOT
```
任务运行目录**只保存引用**：
```yaml
protected_manifest_ref: analysis/style/CH-001/TASK-123/protected-manifest.yaml
protected_manifest_sha256: <sha256>
source_draft_sha256: <sha256>
```
> 不放入 `memory/project/style-library/`（非风格卡，且同章多次修订会覆盖）；`analysis/style/` 仅存快照引用。

**它是什么、不是什么**
```
protected-manifest =
    NKB 硬事实（source: canon）
  + 章纲硬要求（source: outline）
  + 当前草稿新增事实（source: draft_snapshot）
→ 本次修订的不可变比较基线
```
- 不得凌驾于 NKB；若 NKB 后续更新 → 重新生成基线（状态 `STALE` → 重新诊断）。

**内容分级**
```yaml
hard_preserve:        # 人名、地名、年代、数字、关键事实、关键伏笔(must_preserve)、道具归属与状态
functional_preserve:  # 场景钩子、必要观察、叙事功能、感官锚点（可润色表现但不得删除其承载信息）
soft_preserve:        # 可替换的感官表现方式、修辞选择
```

**生成任务：`protected-manifest-build`（审查六·补齐唯一剩余阻断——全文依赖它却无人生成）**

- **职责**：在 `结构稳定门禁` 之后、`ai-diagnose` 之前生成 `protected-manifest`，供 `fidelity-review` / `final-regression`（baseline 与 post_apply 两模式）/ `publish` 读取与哈希绑定。
- **写权限归属**：`protected-manifest-build` **唯一拥有** `analysis/style/<chapter>/<task>/protected-manifest.yaml` 写权（目录 `analysis/` 为分析产物，不经 `controlled_chapter_writer`）；`forbidden: [NKB/**, chapters/drafts/**, chapters/approved/**]`；`allow_subagents: false`。
```yaml
task_type: protected-manifest-build
allow_read:
  - NKB/**
  - outlines/**
  - chapters/drafts/<chapter_id>.md
allow_write:
  - analysis/style/<chapter_id>/<task_id>/protected-manifest.yaml
forbidden:
  - NKB/**
  - chapters/drafts/**
  - chapters/approved/**
allow_subagents: false
```
- **产物至少绑定（产出自带，供后续门禁比对）**：
```yaml
chapter_id:
task_id:
source_draft_sha256:        # 当前草稿哈希（NKB/章纲/草稿冲突判定基准之一）
nkb_revision:
nkb_snapshot_sha256:
outline_sha256:
builder_version:
model_id:
prompt_hash:
created_at:
hard_preserve:
functional_preserve:
soft_preserve:
```
- **冲突裁决（不得静默选择草稿，吸收审查六）**：
  - NKB 硬事实 与 草稿新增事实 冲突 → **以 NKB 为准**，草稿冲突项写入报告并进入 `MANIFEST_CONFLICT`；**不得静默采用草稿**。
  - 章纲 与 NKB 冲突 → 进入 `MANIFEST_CONFLICT`（章纲不得覆盖 NKB 硬事实）。
  - `chapter_fix` 后必须**重新生成** manifest（旧 manifest 随 NKB/章纲/草稿哈希变化进入 `STALE`）。
- **`ai-diagnose` / `style-revise` / `fidelity-review` / `final-regression` 必须引用同一 `protected_manifest_sha256`**（即本次 build 产出哈希），不得各取一份快照。

### 2.6 防新模板味（重构）

- **只对 `style_preferences` 计命中率**（`style-hitrate`）；分母 = 符合使用条件的机会数（非全章字数）。
- `governance_constraints` 与 `functional_preserve` **永不被命中率抑制**。
- `style-hitrate` 用**追加式事件日志**（append-only）再聚合，防多章并发覆盖。
- 硬规则（治理/硬保真）不可因"命中率过高"停执行；只有可调倾向（比喻密度、短句比例）计入命中率抑制。

### 2.7 修订失败循环上限 + final-regression 只读回滚（吸收审查·问题9 / 问题8 / 问题11-B1）

- 自动重试 ≤ 1 次；二次失败 → `BLOCKED`，转人工。
- 每轮存 `revision-candidate` + 质量分；新候选事实保真度 ≥ 上版；不覆盖更优候选。
- 每任务设 model / Token / Credit 上限；**禁止子 Agent 并发执行**。
- **final-regression 为只读，且有两种模式（吸收问题11-B1 / 审查四·阻断1：无修订路径不得直接获 FINAL_PASSED）**：
  - `mode=baseline`（无修订路径：`DIAGNOSED_CLEAN` / `REVISION_SKIPPED` → `FINAL_CHECK_READY` 后运行）：
    - input：`current_draft`
    - checks：`[NKB, outline, protected_manifest, chapter_review]`（不依赖 pre_apply/applied 版本）
    - 通过 → `FINAL_PASSED → PUBLISH_READY`；失败 → `FINAL_FAILED → CHAPTER_FIX_REQUIRED`
  - `mode=post_apply`（已修订路径：`APPLIED` → `FINAL_CHECK_READY` 后运行）：
    - input：`[pre_apply_artifact, applied_draft]`
    - checks：`[fidelity, quality, NKB, outline, protected_manifest]`
    - 通过 → `FINAL_PASSED → PUBLISH_READY`；失败 → `FINAL_FAILED → ROLLBACK_READY`
  - **`FINAL_PASSED` 只能由 `final-regression` 任务产生**；其他任务（含 `chapter_write`/`chapter_fix`/`style-revise`）**无权直接写入**该状态。
  - `chapter-apply-revision` 原子写入草稿后状态 `APPLIED`；无修订路径无 `pre_apply`/`applied` 版本，故走 `baseline` 模式。
  - 必须保存（post_apply 模式，非仅 `pre_apply_sha256`）：
```yaml
pre_apply_artifact_ref: analysis/style/<ch>/<task>/draft-pre-apply.md
pre_apply_sha256: <sha256>
applied_draft_sha256: <sha256>
rollback_task_id: <task_id>
```
  - 回滚成功 → `ROLLED_BACK`；保留失败候选及报告；**不允许直接进入 `chapter_fix` / `chapter-publish`**。
  - 回滚冲突：若 `chapter-rollback-revision` 的 CAS 发现草稿在 apply 后又被改动（哈希不符 `applied_draft_sha256`），置 `ROLLBACK_CONFLICT → BLOCKED`，**绝不覆盖新内容**（见 §2.9）。

### 2.8 任务治理门禁（吸收审查四·问题11-B2/问题11-B4——operation-specific 策略）

**统一授权入口 + 分操作策略（取代"同组断言套用所有操作"，吸收问题11-B1；补齐 resume 与多资源 capability，审查四·阻断2）**
```python
authorize(operation, task, actor, session, resources):
    # 统一入口，但每个 operation 走各自检查策略
    common = [session_ready, subagent_policy_denied]
    policy = {
      "create":  [creator_can_assign_role, template_valid],
      "claim":   [actor_matches_executor, claimable_state],   # 获取 lease
      "run":     [lease_owner, role_match, runnable_state],
      "resume":  [lease_owner, role_match, resumable_state, outputs_consistent],  # 审查四·阻断2 补齐
      "complete":[completion_authority, lease_owner, completable_state, outputs_valid],
      "candidate_create":[lease_owner, candidate_path_permission],   # analysis/style 写
      "apply":   [lease_owner, APPLY_READY, source_hash_equal, target_hash_equal, path_permission],
      "rollback":[lease_owner, ROLLBACK_READY, applied_hash_equal, backup_hash_present],
      "publish": [lease_owner, PUBLISH_READY, dependency_binding, source_hash_equal, target_hash_equal],
    }
    for c in (common + policy[operation]):
        assert c()
    return issue_capability(...)   # 见下：多资源 + 单次使用 + 签名
```

**能力令牌（多资源、单次使用、签名，审查四·阻断2）**
```yaml
capability:
  capability_id:
  task_id:
  session_id:
  actor_id:
  operation:
  resources:
    - role: source              # 如当前草稿
      canonical_path: <realpath 规范化后>
      expected_sha256: <sha256>
    - role: target              # 如 approved 文件
      canonical_path: <realpath>
      expected_sha256_or_absent: <sha256 | absent>   # 新建可为 absent
    - role: candidate_or_backup
      canonical_path: <realpath>
      expected_sha256: <sha256>
  policy_sha256: <authorize 策略快照哈希>
  issued_at:
  expires_at:
  nonce:                        # 单次使用
  single_use: true
  signature:                    # 由受控写 Broker 私钥 / 会话密钥签署
```
- writer 必须：对路径做 `realpath`/规范化；**拒绝符号链接与路径穿越**；同时校验 source / target / candidate_or_backup 哈希；消费 capability 后立即失效（`single_use`）。
- capability 绑定**多个资源**的规范路径与期望哈希，授权后被替换任一资源即 CAS 失败，无法只靠单 `expected_sha256` 防源/目标替换。
- **统一的是 `authorize()` 入口，不是所有 operation 使用相同断言**。`create` 阶段尚无 lease、故不检查 lease；`claim` 是获取 lease、故不预先要求 lease 有效；`complete` 检查 `completion_authority` 而非仅 `executor_role`；只读任务（diagnose/review）无需 `allow_write` resource；`publish` 同时涉及源草稿与 approved 目标，需两个 resource 的 path 权限。
- `task create` 的 `creator_can_assign_role` 语义：校验的是**任务被指派的执行角色**（`task.executor_role` 合法性），创建者未必是执行者；运行/完成时才比对 `actor.role`。

**强制挂载点**
```
task create  → authorize("create", ...)      # session_ready + 指派角色合法性
task claim   → authorize("claim", ...)        # session_ready + 角色匹配 + 获取 lease
task run     → authorize("run", ...)          # lease_owner + 角色 + 可运行态 + subagent
task resume  → authorize("resume", ...)       # 补：角色 / 路径 / subagent policy
task complete→ authorize("complete", ...)     # 补：completion_authority + 可完成态 + 产出有效
apply/rollback/publish → authorize(..., resources)  # 显式多资源路径权限 + 状态/哈希
```

**绕过测试（纳入回归）**
- 未创建 session 不能创建变更型任务；session 未 ready 不能创建；create 后 session 失效不能 claim；
- claim 后角色不匹配不能 run；`allow_subagents: false` 时运行时拒绝派生子 Agent；
- **即便绕过 CLI/任务系统，普通进程对 `chapters/` 仅有读权限**，真实写须经 broker 隔离边界（§2.4）；
- `authorize()` 任一项失败均拒绝，且记录不可变事件日志（§10 `task-event.schema.yaml`）。

**执行层子 Agent 禁用门禁（审查四·阻断3：仅任务字段不足以阻止外层工具调用）**
- `allow_subagents: false` 不只靠模型自律，须在**执行层**真正撤掉能力：
  1. `task` 模板 `allow_subagents: false` → execution harness **不向模型暴露** `spawn` / `fork` / `delegate` 类工具；
  2. 工具网关（tool gateway）**再次拒绝**相关调用；
  3. 任何尝试调用 → 记录**违规事件**并置 `BLOCKED`。
- 纳入回归的禁用测试：
  - 任务运行前尝试 `spawn`；
  - 任务运行中尝试 `spawn`；
  - `resume` 后尝试 `spawn`；
  - 通过其他工具别名尝试派生；
  - 未经 `task run` 直接调用派生工具。
- 只有从工具暴露层撤掉能力，才是真正禁止（而非提示模型"不要使用"）。

### 2.9 候选稿状态机（revision-candidate，吸收审查·问题4 / 问题11-B3 / 问题11-B1）

**完整状态枚举与合法转换（所有转换经 `transition_state(expected_state, next_state)`，CAS + 追加式事件日志防并发覆盖）**
```
STRUCTURE_STABLE                          # 结构稳定门禁通过后进入
  → MANIFEST_BUILDING (protected-manifest-build)
       ├─ MANIFEST_READY   → DIAGNOSED    # 唯一生成 protected-manifest 的出口
       └─ MANIFEST_CONFLICT → HUMAN_REVIEW
                                → BLOCKED

DIAGNOSED
  ├─ 有明确可修问题 → CANDIDATE_CREATED (style-revise)
  ├─ 仅警告         → DIAGNOSED_WARNING
  └─ 无问题         → DIAGNOSED_CLEAN

DIAGNOSED_CLEAN
  → FINAL_CHECK_READY → final-regression(mode=baseline)
       ├─ FINAL_PASSED → PUBLISH_READY
       └─ FINAL_FAILED → CHAPTER_FIX_REQUIRED

DIAGNOSED_WARNING
  → HUMAN_REVIEW
       ├─ REVISION_REQUESTED → CANDIDATE_CREATED
       └─ REVISION_SKIPPED   → FINAL_CHECK_READY → final-regression(mode=baseline)
                                                    ├─ FINAL_PASSED → PUBLISH_READY
                                                    └─ FINAL_FAILED → CHAPTER_FIX_REQUIRED

CANDIDATE_CREATED
  → FIDELITY_PASSED (fidelity-review)
  → FIDELITY_FAILED → RETRY_READY → CANDIDATE_CREATED (重新生成候选)
                    → BLOCKED

FIDELITY_PASSED
  → QUALITY_PASSED (style-quality-review)
  → QUALITY_FAILED → HUMAN_REVIEW
                       ├─ QUALITY_WAIVED → APPLY_READY
                       └─ BLOCKED

QUALITY_PASSED → APPLY_READY                     # 正常通过质量审查后进入 apply

APPLY_READY
  → APPLIED (chapter-apply-revision，CAS 写草稿)

APPLIED
  → FINAL_CHECK_READY → final-regression(mode=post_apply)
       ├─ FINAL_PASSED → PUBLISH_READY
       └─ FINAL_FAILED → ROLLBACK_READY

ROLLBACK_READY
  → ROLLED_BACK (chapter-rollback-revision)
  → ROLLBACK_CONFLICT → BLOCKED        # CAS 发现草稿在 apply 后又被改动，绝不覆盖新内容

CHAPTER_FIX_REQUIRED → chapter_fix → 结构稳定门禁 → 重新生成 manifest（protected-manifest-build）→ ai-diagnose（重新诊断）

PUBLISH_READY → PUBLISHED (chapter-publish，CAS 写 approved)

STALE（可从 MANIFEST_READY / CANDIDATE_CREATED / FIDELITY_PASSED / QUALITY_PASSED /
       APPLY_READY / APPLIED / FINAL_CHECK_READY / FINAL_PASSED / PUBLISH_READY 进入；
       当草稿哈希变化或 NKB / 章纲 / protected-manifest 任一更新）→ 以下游入口重走：
       - 处于 manifest 之后状态 → 先经 `protected-manifest-build` 重新生成 manifest（`MANIFEST_READY`）
       - 再进入 `ai-diagnose` 重新诊断
```

> `FINAL_PASSED` **仅由 `final-regression` 任务写入**；其他任务无权直接产生该状态（见 §2.7）。

**`chapter-apply-revision` 必须同时验证**
- 候选状态 == `APPLY_READY`；Fidelity 报告通过；Quality 通过或 `QUALITY_WAIVED`（人工批准）；
- 当前草稿哈希 == 候选绑定哈希；候选自身哈希未变；任务租约有效；执行角色正确。

**`chapter-publish` 必须验证 FINAL_PASSED 报告绑定（吸收问题11-B4，依赖变化即 STALE 重诊）**
```yaml
draft_sha256: <sha256>
nkb_revision: <NKB 版本号>
nkb_snapshot_sha256: <sha256>     # 发布前 NKB 快照
outline_sha256: <sha256>          # 章纲快照
protected_manifest_sha256: <sha256>
style_guidance_sha256: <sha256>
final_regression_config_version: <版本>
final_regression_mode: baseline | post_apply   # 证明使用了正确的 final-regression 模式（§2.7）
chapter_review_report_sha256: <sha256>          # baseline 模式所依据的章节审查报告（publish 须校验一致）
model_id: <模型>
prompt_hash: <hash>
```
- 任一依赖（NKB / 章纲 / protected-manifest / style-guidance / final-regression 配置）变化 → `FINAL_PASSED` / `PUBLISH_READY → STALE → 重新诊断`，**不允许发布过期绑定**。

### 2.10 风格规则候选审批与晋升链（吸收审查·问题6 / 问题5 / 问题11-B5 / 问题11-HR8）

**生命周期（style-rule-candidate，吸收审查四·高风险B：被拒绝为终态，不得晋升）**
```
EXTRACTED → REVIEW_PENDING
REVIEW_PENDING
  ├─ APPROVED  → PROMOTION_ELIGIBLE → PROMOTED → ACTIVE
  └─ REJECTED  → 终态（不再流转）
ACTIVE
  ├─ SUSPENDED
  └─ REVOKED
```
- `style_extract` 仅产 `style_preferences/targets/candidate_project_constraints`；`candidate_project_constraints` 须人工批准才晋升，绝不自动成 `governance_constraints`。

**审批凭证（消除自引用哈希，真实性来自不可变任务事件日志）**
```yaml
approval:
  candidate_id:            # style-rule-candidate id
  candidate_sha256:
  source_set_hash:
  reviewer_id:
  reviewer_role:
  review_task_id:          # 审批任务 id（事件日志可查）
  session_id:
  decision: approved | rejected
  approved_rule_ids: [...]
  rejected_rule_ids: [...]
  reason:
  approved_at:
integrity:
  canonicalization_version:
  payload_sha256:          # 仅对 approval 节点做 SHA-256（不含 integrity 自身）
  event_log_ref:           # 指向平台不可变任务事件日志（task-event.schema.yaml，见 §10）
  event_log_entry_hash:     # 该审批事件在日志中的哈希
```
- 真实性不依赖自报的 `reviewer_role` 字符串，而来自**任务事件、身份与不可变日志**（`event_log_ref` + `event_log_entry_hash`）。
- **审批不可变性依赖 §10 `task-event.schema.yaml` 的不可变事件日志**（单调序号 + previous_event_hash 哈希链 + 认证 actor_id + HMAC/签名或外部不可变存储）；普通本地 JSONL 可被整份重写，不能证明审批真实性。
- **密钥托管（审查四·高风险A）**：HMAC/签名密钥**不向普通任务进程开放**；事件只能经**可信日志 Broker** 写入；定期把最新链头哈希签名并**锚定到项目外**（外部不可变存储 / 独立密钥签名）；审批验证同时检查链头签名；密钥轮换须保留 `key_id` 与有效时间段。否则整份日志被重写时攻击者可重算整条链，`task-events.log` 无法真正承担审批真实性。
- `style-rule-promote --approved` 必须读取审批凭证、校验 `payload_sha256` 与事件日志一致、确认 `review_task_id` 具审批权，否则拒绝晋升。
- 来源撤回 → 相关规则 `REVOKED`；依赖该来源权重超阈的已晋升规则降级 `SUSPENDED`。

### 2.11 无问题跳过路径（吸收审查·问题9）

`ai-diagnose` 后按结果分流（与 §2.9 一致）：
```
ai-diagnose
  ├─ 无问题   → DIAGNOSED_CLEAN → FINAL_CHECK_READY → final-regression(mode=baseline)
  │              ├─ FINAL_PASSED → chapter-publish
  │              └─ FINAL_FAILED → CHAPTER_FIX_REQUIRED → chapter_fix（重走）
  ├─ 仅警告   → DIAGNOSED_WARNING → HUMAN_REVIEW
  │              ├─ REVISION_REQUESTED → CANDIDATE_CREATED → …（见 §2.9）
  │              └─ REVISION_SKIPPED   → FINAL_CHECK_READY → final-regression(mode=baseline)（同上）
  └─ 有问题   → CANDIDATE_CREATED → …（见 §2.9）
```
> 无明确可修问题时不强制进入 `style-revise`，降低不必要重写与额度消耗。

---

## 3. 章节主链重排（吸收审查·问题2 / 问题8 / 问题9 / 问题11-B1）

```
chapter_write
  → chapter_review（剧情/设定/人物/逻辑 四支柱）
  → chapter_fix                  # 修草稿（结构性）
  → 结构稳定门禁
  → protected-manifest-build     # 唯一生成 protected-manifest 的任务（MANIFEST_READY；冲突则 MANIFEST_CONFLICT）
  → ai-diagnose（风格风险诊断，只读）
       ├─ 无问题 → DIAGNOSED_CLEAN → FINAL_CHECK_READY
       │            → final-regression(mode=baseline)
       │                 ├─ 通过 → PUBLISH_READY → chapter-publish
       │                 └─ 失败 → CHAPTER_FIX_REQUIRED → chapter_fix（重走：结构稳定门禁 → protected-manifest-build → ai-diagnose）
       ├─ 仅警告 → DIAGNOSED_WARNING → HUMAN_REVIEW → (请求修订 | 跳过)
       │            REVISION_SKIPPED → FINAL_CHECK_READY → final-regression(mode=baseline)（同上）
       └─ 有问题 →
  → style-revise（revision-candidate，写 analysis/style/<ch>/<task>/，绑定原稿哈希）
  → fidelity-review
  → style-quality-review
       ├─ 通过 → APPLY_READY            # QUALITY_PASSED → APPLY_READY
       └─ 失败 → HUMAN_REVIEW → QUALITY_WAIVED / BLOCKED
  → chapter-apply-revision（受控 CAS 写草稿，须 APPLY_READY + 哈希一致）
  → FINAL_CHECK_READY → final-regression(mode=post_apply，只读比对 pre_apply / applied)
       ├─ 通过  → PUBLISH_READY → chapter-publish（唯一写 approved；验证 §2.9 绑定）
       └─ 失败  → ROLLBACK_READY → chapter-rollback-revision
                                       → ROLLED_BACK（禁入 publish）
                                       → ROLLBACK_CONFLICT → BLOCKED
```

---

## 4. 数据存储与目录（须登记 PROJECT_LAYOUT）

```
sources/references/inbox/                          # 已存在：TXT/MD，默认不进 Git
learning/candidates/style-profiles/                # 每源 style-profile
learning/candidates/style-archetypes/              # 通用原型（含 source_contribution_vector）
analysis/style/<chapter_id>/<task_id>/             # protected-manifest / diagnosis / revision-result / revision-candidate 唯一 SSOT（候选稿归此）
chapters/drafts/<chapter_id>.md                    # 草稿（受控写）
chapters/approved/<chapter_id>.md                  # 正式章节（受控写，仅 chapter-publish）
runtime/learning/style-guidance.yaml                # 运行时组合（含 governance_policy_ref）
runtime/learning/style-hitrate.log                 # 追加式事件日志
memory/project/style-library/                       # L0–L4 风格卡库（不含 protected-manifest、不含 governance_constraints）
```
> `chapters/` 仅保留 `drafts/` 与 `approved/`，候选稿归入 `analysis/style/`（分析产物，不经 `controlled_chapter_writer`）。

**密钥（吸收问题11-HR5）**：不建项目 `secrets/`；经环境变量 / OS 钥匙圈 / Secrets Manager 注入，项目只存 `key_id`。
**受控写**：`scripts/style/controlled_chapter_writer.py` 为唯一正文写原语（§2.4，须 broker/ACL 隔离）。
**不可变事件日志**：`runtime/logs/task-events.log` + `task-event.schema.yaml`（§10）；**经可信日志 Broker 写入，HMAC/签名密钥不向普通任务进程开放，链头定期签名锚定项目外**（§2.10）。

---

## 5. 提取层升级（12 维写作决策参数）

在现有 6 指标之上，新增**写作决策级**提取（每条按 §2.3 rule schema 产出，注明提取方法=规则+模型；`confidence` 取 §2.3 可计算来源）：

| 维度 | 提取内容（参数化） |
|---|---|
| 叙事视角 | POV 类型、限知范围、是否进入人物内心 |
| 叙事距离 | 镜头离人物远近（战斗近 / 历史介绍远） |
| 句法节奏 | 长短句比、停顿、段落长度分布 |
| 信息密度功能 | 每段推进「剧情/设定/情绪」功能标注比例 |
| 描写选择 | 写什么 / 省略什么的分布 |
| 感官偏好 | 视/听/嗅/触/味组合权重（每场景主导感官） |
| 情绪表达 | 直说 vs 动作表现比例 |
| 对话方式 | 台词长度、潜台词、动作插入比、人物辨识度 |
| 比喻机制 | 密度、来源域、角色适配 |
| 留白方式 | 暂不解释的信息类型 |
| 场景收束 | 动作/信息/选择钩子占比 |
| 禁用模式 | 模板化表达自动识别（"嘴角勾起弧度"等） |

---

## 6. 指标设计（三分法 + 版本化门禁）

| 类别 | 指标 | 门槛 |
|---|---|---|
| **硬门禁** | 关键事实保留率 | 硬事实 **100%**（一般细节分级） |
| | 关键伏笔保留率 | `must_preserve` **100%** |
| | 新增无依据事实 | **0** |
| | 正式章节直写 | 禁止（只能经 apply / rollback / publish 受控写） |
| | 候选状态/哈希绑定 | apply/publish 须验证状态机与哈希（§2.9） |
| **质量评分** | 节奏/视角/冗余/场景风格匹配 | 改用「与目标风格分布的距离」；模板表达次数结合上下文功能 |
| | 角色语言区分度 | 仅**警告项** |
| **人工反馈** | 盲选偏好 | 盲选 A/B |
| | 接受度 | **span 级接受与原因** |
| | 修改幅度 | 用户手工二次修改幅度 |

- F1 改名：**风格风险诊断**。
- **质量门禁版本化阈值（吸收问题11-HR9 / 审查四·高风险E：不同指标方向不同）**：
```yaml
quality_policy_version: <版本号>
thresholds:
  - scene_type: battle | dialogue | exploration | daily | emotion | exposition
    metric: rhythm_distance | pov_consistency | redundancy | scene_style_match
    comparator: lt | lte | gt | gte | range   # 方向：rhythm_distance 越低越好；pov_consistency 越高越好；redundancy 越低越好
    unit: <单位>
    warning_threshold: <值>
    failure_threshold: <值>
    aggregation: <mean | max | percentile>
    minimum_sample_size: <N>     # 样本不足时按 missing_data_policy 处理，避免短场景产生不可信评分
    missing_data_policy: <fail | warn | skip>
    calibration_dataset_ref: <黄金测试集引用>
    hard_gate: true | false        # 治理硬门禁必须 true
    human_override_allowed: true | false   # 硬门禁必须 false
```
  - 治理硬门禁（`hard_gate: true`，如 POV 越界、事实变化）**必须 `human_override_allowed: false`**。
  - `style-quality-review` 须按 `quality_policy_version` 中对应 `scene_type + metric + comparator` 判定 `QUALITY_PASSED / QUALITY_FAILED`，不得自定阈值或方向。

---

## 7. L4 作者学习重构（吸收审查·"L4 过于粗糙"）

记录：接受/拒绝的具体 span；修改前后差异；原因；用户手工终稿；同类偏好出现次数；适用场景；是否允许晋升。
- 至少**多次独立证据**（≥3 次同类 span 级反馈）后生成 L4 候选；仍需审核晋升，**不自动写入** `author.card.yaml`。
- L4 晋升同样产生审批凭证（§2.10 同构），可 `SUSPENDED`/`REVOKED`。

---

## 8. 分阶段实施路线（重排）

> **实施顺序调整（审查四·高风险F）**：先复跑健康度、定威胁模型与隔离方案、再建全部 schema、再写基础设施（事件日志 / authorize / capability / 受控 writer）、状态机、提取与只读诊断、候选修订与质量门禁，**最后**才接入 apply / rollback / publish。

1. **基线复跑**：在 `baseline_commit` 检出干净工作树，`selfcheck` / `doctor --quick` 复跑确认无偏离（§0）。
2. **威胁模型与隔离方案选型**：进入编码前**必须选定一种**权限隔离方案（broker / OS ACL / 子进程沙箱不可继续"三选一"）。**当前 Windows 工作区建议**：独立写入 **Broker 进程** + 独立系统身份 + **Windows ACL** 限制正文目录 + 本地受限 IPC + 签名且单次使用的 capability。
3. **全部 schema**：`style-profile` / `style-archetype` / `style-card` / `protected-manifest` / `diagnosis` / `revision-result` / `style-quality-report` / `final-regression-result` / `chapter-apply-result` / `revision-candidate-state` / `style-rule-candidate` / `task-event` / `quality-policy` schema（§10）。
4. **基础设施**：事件日志 `event_log.py`（哈希链 + 链头锚定，§2.10）+ `authorize()` 分操作策略（§2.8）+ 多资源单次 capability（§2.8）。
5. **受控写原语与权限隔离**：`controlled_chapter_writer`（独立 Broker 身份 + Windows ACL + 路径规范化 + 单次消费，§2.4 / §2.8）。
6. **状态机与绕过测试**：`transition_state()` + 全转换 + `ROLLBACK_CONFLICT` + 绕过 / 扫描 / 事件日志篡改 / 子 Agent 禁用测试（§2.9 / §2.8）。
7. **参考提取与只读诊断**：`style_extract`（仅产 style_preferences/targets/candidate_project_constraints）+ 只读 `ai-diagnose` / `fidelity-review` / `style-quality-review` + 黄金测试集（§5 / §2.3）。
8. **候选修订与质量门禁**：`style-revise`（写 `analysis/style/`）+ 内容分级 + 版本化质量阈值（§2.4 / §2.5 / §2.6 / §6）。
9. **接入 apply / rollback / publish（冻结期后，满足 §12 五项才放开）**：`chapter-apply-revision` / `chapter-rollback-revision` / `chapter-publish` + `final-regression` 双模式（§2.7 / §2.9 / §3）。
10. **作者闭环与防模板味 + 晋升链激活**（§6 / §7 / §2.6 / §2.10）。

每阶段一个 `system_maintenance` 任务，配套 `tests/`（含 §2.8 绕过测试、§2.9 状态机测试、§4 扫描测试、§2.10 事件日志篡改测试）；旧项目 `legacy_proceed` 不迁移。

---

## 9. 风险与回退

- 候选稿模式 + 受控写原语防受控写绕过；`protected-manifest` 防误删事实/伏笔（分级后不阻碍正常润色）。
- 命中率上限 + 硬规则不抑制，防新模板味。
- 失败上限 + 额度上限 + `chapter-rollback-revision` 独立回滚，防共享额度耗尽与草稿滞留不合格态；`ROLLBACK_CONFLICT` 防覆盖新内容。
- 密钥严格隔离（环境变量/钥匙圈/Secrets Manager，仅存 `key_id`）；source 撤回级联失效。
- **受控写真实隔离依赖 broker / OS ACL / 子进程沙箱**；若仅同账户同权限则为治理约束，须选隔离方案。
- 每阶段独立回退（各有 regression 基线），不影响已发布章节。

---

## 10. 关键文件清单（落地时新建/修改）

**新建契约（core/contracts/）**
- `style-card.schema.yaml`（project/style 分类 + 每条 rule 自带 `scope`；**不含 governance_constraints，改 `governance_policy_ref`**）
- `style-profile.schema.yaml` / `style-archetype.schema.yaml`（含 `source_contribution_vector`）
- `protected-manifest.schema.yaml`（hard/functional/soft 分级）
- `diagnosis.schema.yaml` / `revision-result.schema.yaml` / `style-quality-report.schema.yaml`
- `final-regression-result.schema.yaml` / `chapter-apply-result.schema.yaml`
- `revision-candidate-state.schema.yaml`（§2.9 状态机）
- `style-rule-candidate.schema.yaml`（审批/晋升生命周期）
- `task-event.schema.yaml`（**不可变任务事件日志**：单调序号 + `previous_event_hash` 哈希链 + 认证 `actor_id` + HMAC/签名；**密钥仅对可信日志 Broker 开放，不向普通任务进程暴露；链头哈希定期签名并锚定到项目外；提供 `verify-event-log` 命令与篡改测试**）
- `authorization-policy.schema.yaml`（§2.8 `authorize()` 的分操作检查策略唯一 SSOT：create/claim/run/resume/complete/candidate_create/apply/rollback/publish 各自的断言列表与适用条件）
- `capability-token.schema.yaml`（§2.8 多资源能力令牌结构唯一 SSOT：capability_id/task_id/session_id/actor_id/operation/resources[]/policy_sha256/nonce/single_use/signature）
- `chapter-rollback-result.schema.yaml`（chapter-rollback-revision 产出：pre_apply_artifact_ref/pre_apply_sha256/applied_draft_sha256/rollback_task_id/result=ROLLED_BACK|ROLLBACK_CONFLICT）
- `quality-policy.schema.yaml`（§6 版本化阈值，含 `minimum_sample_size`）

**新建脚本/受控写**
- `scripts/style/controlled_chapter_writer.py`（**唯一正文写原语**；CAS + 能力令牌 + 事件日志；**以独立身份/权限运行（broker/沙箱/ACL 三选一隔离）**；扫描测试仅兜底）
- `scripts/learning/style_extract.py`（仅产 style_preferences/targets/candidate_project_constraints）
- `scripts/learning/reference_fingerprint.py`（HMAC-SHA256 shingles → MinHash；密钥经环境变量/钥匙圈）
- `scripts/style/{ai_diagnose, style_revise, fidelity_review, style_quality_review, protected_manifest_build, chapter_apply_revision, chapter_rollback_revision, final_regression}.py`
- `scripts/logs/event_log.py`（不可变事件日志写入 + `verify-event-log`）

**新建任务模板**
- `core/task-system/templates/{protected-manifest-build, ai-diagnose, style-revise, fidelity-review, style-quality-review, chapter-apply-revision, chapter-rollback-revision, final-regression, style-rule-review, style-rule-promote}.task.yaml`

**修改**
- `scripts/learning/reference_learning.py`（v2 提取 + 指纹；`raw_text_stored` 保持 False）
- `core/contracts/project-layout.schema.yaml` + `scripts/project/project_layout.py`（登记目录；**不登记项目 secrets/**）
- `scripts/platform/writing_strategy.py`（门禁协同）
- 章节脚本（`chapter_write`/`chapter_fix`/`chapter-publish`）改为经 `controlled_chapter_writer`
- `core/learning/自主学习与反馈闭环.md`（补风格体系 + 候选稿模式 + 晋升链 + 不可变事件日志）
- `tests/`（每阶段回归，含绕过测试、状态机测试、扫描测试、事件日志篡改测试）

---

## 11. 设计审查记录（累计）

- **v1→v2（审查一）**：成熟度 ~75%→~86%；吸收 10 阻断 + 3 高风险。
- **v2→v3（审查二）**：~86%→~90%（待复审）；修复 6 阻断 + 12 高风险/非阻断（写权限表、protected-manifest 唯一 SSOT、session 强制挂载点、候选状态机、治理硬规则分离、审批晋升链、独立 SSOT、final-regression 回滚、跳过路径、HMAC 指纹、置信度可计算、契约补齐）。
- **v3→v4（审查三）**：~90%→~95%（自评偏高）；修复 5 阻断 + 高风险（独立回滚任务、受控写+扫描测试、状态机主分支、统一 authorize 思路、审批凭证去自引用、冲突优先级框架、scope 字段、候选命名、基线证据绑定、密钥存储）。
- **v4→v5（审查四）**：~95%→~93%–94%（下调自评）；本轮修订：
  - **4 项阻断全部修复**：
    1. `authorize()` 不能按同组断言运行 → §2.8 改为**统一入口 + 分操作策略**（create/claim/run/complete/candidate_create/apply/rollback/publish 各自检查列表；create 不查 lease、claim 获取 lease、complete 查 completion_authority、publish 双 resource）。
    2. `controlled_chapter_writer` 仍非不可绕过 → §2.4 明确**普通进程对 `chapters/` 仅读**、写须经**独立身份 broker/沙箱/ACL 三选一隔离**；扫描测试仅兜底；候选稿移出 `chapters/`，改存 `analysis/style/<ch>/<task>/revision-candidate.md`（`chapters/` 只留 drafts/approved）。
    3. 状态机仍缺关键转换 → §2.9 补 `QUALITY_PASSED→APPLY_READY`、`DIAGNOSED_WARNING→HUMAN_REVIEW→REVISION_REQUESTED/REVISION_SKIPPED`、`ROLLBACK_READY→ROLLED_BACK/ROLLBACK_CONFLICT→BLOCKED`；`STALE` 覆盖 `FINAL_PASSED`/`PUBLISH_READY`。
    4. publish 绑定不完整 → §2.9 `chapter-publish` 须校验 `FINAL_PASSED` 绑定 `draft_sha256/nkb_revision/nkb_snapshot_sha256/outline_sha256/protected_manifest_sha256/style_guidance_sha256/final_regression_config_version/model_id/prompt_hash`，任一变化即 `STALE` 重诊。
  - **高风险/非阻断修复**：审批日志不可变性无对象 → §2.10/§10 新增 `task-event.schema.yaml`（单调序号 + previous_event_hash 哈希链 + 认证 actor_id + HMAC/签名或外部不可变存储 + `verify-event-log` 命令与篡改测试）；治理规则复制进风格卡 → §2.1 风格卡仅持 `project_constraints/style_preferences/style_targets`，改 `governance_policy_ref + governance_policy_sha256` 引用；L2/L3 固定优先级 → §2.1 改按字段与作用域（角色对白 L3>L2、旁白 L2 生效 L3 不参）；质量门禁无版本化阈值 → §6 新增 `quality_policy_version` + 分 scene_type/metric 阈值；§0 健康度明确"待基线复跑"，自评成熟度下调为 93%–94%。
- **现状核验**：见 §0（绑定基线提交、完整 SHA-256、baseline 符号行号、selfcheck/doctor 数值来自本地工作树、立项前须在 baseline 复跑）。

- **v5→v5.1（审查五·小修）**：设计完整度约 95%；审查确认 v5 可正式通过"架构方向审查"，仅需小修补齐 3 阻断 + 小错，形成可实施冻结基线。本轮修复：
  - **3 项阻断**：
    1. 无修订路径绕过 final-regression → §2.7 定义 final-regression 双模式（`baseline`：input=current_draft，checks=[NKB,outline,protected_manifest,chapter_review]，失败 CHAPTER_FIX_REQUIRED；`post_apply`：input=[pre_apply,applied]，失败 ROLLBACK_READY）；§2.9/§3 插入 `FINAL_CHECK_READY`，`DIAGNOSED_CLEAN`/`REVISION_SKIPPED`→FINAL_CHECK_READY→baseline，`APPLIED`→FINAL_CHECK_READY→post_apply；明确 FINAL_PASSED 仅由 final-regression 写入。
    2. authorize 缺 resume + capability 绑定不全 → §2.8 补 `resume:[lease_owner,role_match,resumable_state,outputs_consistent]`；capability 改为多资源（source/target/candidate_or_backup）canonical_path+expected_sha256、nonce、single_use、signature；writer 须 realpath/拒符号链接与穿越/同时校验三资源哈希/消费即失效。
    3. 禁子 Agent 仅任务检查 → §2.8 新增执行层门禁：harness 不暴露 spawn/fork/delegate、工具网关再拒、违规记事件并 BLOCKED；补 5 项禁用测试（运行前/中/resume后/别名/未经 run）。
  - **小错/高风险修复**：事件日志密钥托管（§2.10/§4/§10：密钥仅 Broker 开放、链头锚定项目外）；风格规则生命周期分支歧义（§2.10：REJECTED 为终态，不得晋升）；L3 示例错对象（§2.1：L3 角色卡优先于 L2 场景卡）；source_count 交叉引用失效（§2.2 恢复 minimum_independent_sources:3 / recommended:5 / max_single_source_weight:0.4）；质量阈值缺比较方向（§6 补 comparator/unit/aggregation/missing_data_policy/calibration_dataset_ref/hard_gate）；§8 实施顺序调整（先复跑/威胁模型/选型隔离方案/建 schema/基础设施/受控写/状态机/提取/候选/最后接入 apply）。
  - **冻结**：用户要求补齐后冻结纲要，后续问题直接进入 schema / 测试 / 代码任务，不再膨胀主文档。文件未提交/推送。

- **v5.1·冻结（审查六·小修）**：设计完整度约 96%；审查确认 v5.1 可进入冻结阶段，**唯一剩余阻断为「`protected-manifest` 被多门禁依赖却无生产者任务」**。本轮修复：
  - **唯一阻断**：补齐 `protected-manifest-build` 生成任务——定义其权限（**唯一**写 `analysis/style/<ch>/<task>/protected-manifest.yaml`；`forbidden: [NKB/**, chapters/drafts/**, chapters/approved/**]`；`allow_subagents: false`）、产物绑定（chapter_id/task_id/source_draft_sha256/nkb_revision/nkb_snapshot_sha256/outline_sha256/builder_version/model_id/prompt_hash + 三级 preserve）、冲突裁决（NKB 与草稿冲突**以 NKB 为准**、章纲与 NKB 冲突进 `MANIFEST_CONFLICT`、chapter_fix 后重生成、各门禁引用同一 manifest 哈希）；§2.9 状态机新增 `STRUCTURE_STABLE → MANIFEST_BUILDING → MANIFEST_READY / MANIFEST_CONFLICT`；§3 主链在「结构稳定门禁」后插入该任务；§10 补脚本与模板。
  - **契约一致性小修**：① 删除 §2.4 旧单哈希 capability 描述，统一引用 §2.8 多资源契约（解决冲突）；② `authorize()` 参数 `resource`→`resources`，apply/rollback/publish 挂载点同步；③ 修正 §2.1 L3/L4 示例笔误（旁白由 L2 优先、L4 作低优先倾向、L3 角色语言卡不参与旁白）；④ §10 补 `authorization-policy` / `capability-token` / `chapter-rollback-result` 三个基础治理契约；⑤ §2.9 publish 绑定补 `final_regression_mode` 与 `chapter_review_report_sha256`；⑥ §6 恢复 `minimum_sample_size`；⑦ §0 状态更新为六轮审查与冻结结论。
  - **正式冻结**：本版为最终设计基线，**不再制作 v5.2 / v6 主纲要**；后续审查对象从「设计文档」切换为「schema、测试与代码实现」。文件未提交/推送。

---

## 12. 两级放行建议（v5.1 已冻结基线结论）

**v5.1 已通过"架构方向审查"并正式冻结为实施基线（审查六补齐唯一剩余阻断 `protected-manifest-build` 后）**，契约与原型验证可立即展开：
- `protected-manifest-build` 生成任务与其状态机（§2.5 / §2.9 / §3，manifest 生产者缺失的阻断已闭合）；
- 全部 schema（§10，含 `task-event` / `quality-policy` / `authorization-policy` / `capability-token` / `chapter-rollback-result`）；
- `transition_state()` 状态机原型（CAS + 追加事件日志，含 `FINAL_CHECK_READY` / `ROLLBACK_CONFLICT` / `CHAPTER_FIX_REQUIRED`）；
- 指纹系统（HMAC/MinHash + 密钥注入）；
- 黄金测试集（F1 只读诊断）+ 风格规则提取 + 人工审批原型；
- `authorize()` 分操作策略 + 多资源单次 capability + 执行层子 Agent 禁用；
- 不可变事件日志 + 链头锚定。

**真实章节写入（apply / rollback / publish）继续冻结，直到 §8 第 2 步选定隔离方案且以下完成**
1. `authorize()` operation-specific policy + `resume`（§2.8）。
2. `controlled_chapter_writer` 真实权限隔离（**须先选定 broker / ACL / 沙箱之一**，Windows 工作区建议 Broker + 独立身份 + Windows ACL + 受限 IPC，§8 第 2 步）。
3. 状态转换完整 + `ROLLBACK_CONFLICT` + `FINAL_CHECK_READY`（§2.9）。
4. `final-regression` 双模式（baseline / post_apply）+ `publish` 绑定 NKB / 章纲 / manifest（§2.7 / §2.9）。
5. 审批事件日志可验证不可变性（密钥托管 + 链头锚定 + 篡改测试，§2.10 / §10）。

完成上述五项后再进入灰度较稳；v5.1 自评设计完整度约 **96%**。**纲要自 v5.1（审查六）起正式冻结**：后续发现的问题直接进入 schema / 测试 / 代码任务，不再制作 v5.2 / v6 主纲要。

