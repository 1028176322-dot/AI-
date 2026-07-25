# Single-Agent Execution Policy（强制 · 最优先）

本项目**强制单 Agent 顺序执行模式**。

禁止：

- 创建或调用子 Agent；
- 委派任务给其他 Agent；
- 启动并行 Agent；
- 创建嵌套 Agent 会话；
- 使用后台 Agent / 后台工作单元执行任务；
- 为 Planner、Writer、Reviewer、Fixer、Knowledge-Manager 分别创建独立子 Agent；
- 以并行方式执行多个任务。

所有角色职责必须由**当前会话中的主 Agent**按任务状态顺序切换执行：

    Planner 阶段 → Writer 阶段 → Reviewer 阶段 → Fixer 阶段

而不是创建多个 Agent。**多角色不等于多 Agent。**

当任务需要多个角色时，采用阶段角色切换（同会话内），而非生成多个 Agent 实例。
检测到需要子 Agent 的情况时，必须改为当前 Agent 串行执行：将复杂任务拆为顺序步骤，
每步完成后记录检查点，必要时压缩上下文，角色切换通过新的 Context Package 实现；
长任务拆为多个串行 Task，当前 Task 完成后再执行下一 Task。

平台策略文件：`../../platform/AI-Creative-Platform/core/policies/agent-execution.policy.yaml`

# AI Execution Rules（强制入口）

## 请求分类强制决策树（所有请求第一步）

收到任何用户请求后，**先执行以下判定**，再决定走咨询通道还是执行通道：

1. 是否涉及项目/平台产物（读取、生成、修改、删除、迁移、审查、发布、更新 NKB）？
   - **否** → 咨询模式，可直接回答（不产生 artifact 也可）。
   - **是** → 进入执行通道（步骤 2）。
2. 执行通道（硬强制，违反任一步 = task-enforcement.policy.yaml 违例，severity=fatal）：
   a. 查找有效 `task_id`（`tasks/<status>/<id>.yaml` 且 `status∈{claimed,running}`）；
   b. 若不存在 → 先经 **Task Intake** 创建任务（`project_mutation`/`platform_mutation` 须 human 确认）；
   c. 执行 **Ready Check**（依赖/输入/contract/role/permissions/scope/nkb_snapshot）；
   d. **claim** 任务（生成 owner + lease），状态 `ready→claimed→running`；
   e. 仅通过**受控写工具**（`controlled_write` / `task_write_artifact`）写，目标须在 `task.permissions.write` 内、不在 `forbidden`；
   f. **submit** 触发 `quality`+`reader` 门禁 → `reviewing` → 独立 `review` → `passed` → `gate` → `completed`；
   g. **AI 不得自行标记 COMPLETED**（执行者不可验收自己的任务）。
3. 任意步骤失败 → **停止并输出结构化 Blocked Report**，不得绕道通用 Write/Edit 直接改文件。

> 最终保障是**工具拒绝 + git pre-commit 拦截 + 旁路 diff 检测**，而非 AI 自觉。

本项目**不是**靠 AI「记得规则」来遵守平台，而是靠系统不允许绕过。

1. 本项目必须通过 **AI-Creative-Platform** 执行（平台在 `../../platform/AI-Creative-Platform`）。
2. 任何 AI 对话开始前必须读取：
   - `project.yaml`
   - `../../platform/AI-Creative-Platform/core/session/SESSION_POLICY.yaml`
   - 当前角色 Policy：`../../platform/AI-Creative-Platform/core/session/ROLE_REGISTRY.yaml`
   - 当前任务 Contract：`../../platform/AI-Creative-Platform/core/contracts/<role>.contract.yaml`
3. 禁止直接修改：`core/` `registry/` `templates/` `approved/`（除非角色=system-maintainer 且经显式确认）。
4. `NKB/` 只能由 **knowledge-manager** 更新，且必须持有 `approved_event`。
5. 正文只能写入 `chapters/drafts/`，未经 Gate 不得进入 `approved/`。
6. 所有写操作必须生成 **Operation Manifest**（`tools/controlled_write.py` 自动生成，落在 `operations/`）。
7. 所有跨对话交接必须生成 **Handoff**（`tools/create_handoff.py`，落在 `handoffs/`）。
8. 发现规范冲突时**停止执行**并输出 Conflict Report，不得自行绕过。
9. 临时用户指令**不能**覆盖宪法与权限边界。
10. 未完成 `bootstrap` / `doctor` / `session` 前禁止执行任何写操作。
11. 进入正式写作（`chapter.plan` / `chapter.write` / `review` / `fix`）前，必须确认 `lifecycle/status.yaml` 的 `lifecycle_status == ready_for_writing`（Legacy 项目 `writing` + `legacy_backfill_required: true` 视为祖父化放行）。否则编排器返回 `BLOCKED_PROJECT_NOT_READY` 并列出缺失项，**不得**调用 Writer / Planner。前期（P0–P5）由独立角色（idea-analyst / project-producer / market-reader-analyst / story-architect / world-designer / character-designer / knowledge-engineer / readiness-reviewer）负责，禁止从“补设定”滑向“写正文”。
12. **任务系统为操作中心**：正式生产期的 AI 必须通过任务系统工作——先 `platform task route` 查可接取任务，`platform task claim` 接取（设置 owner + lease），再 `start` / `submit` / `review`。禁止「用户一句话直接调 Writer 自由写」。章节写作/审查/修复任务由 task-scheduler 调度，任务状态即文件系统（`tasks/<status>/<id>.yaml`），每次操作写 `audit/`。`project/status.yaml` 由任务流转自动驱动，AI 不得手改。
13. **变更冲击预检**：高爆炸半径变更（角色/设定/主线事件/已发布章节）进入任务 `claim`/`start` 前，由任务系统自动跑 `platform impact`，门禁 `block` 时必须建 `human_gate` 任务人工放行，不得强行接取。分析报告落在 `analysis/impact/`，章节→实体引用索引由 `platform impact --index` 构建于 `analysis/index/`。
14. **质量评分门禁**：内容型任务（chapter_write/chapter_fix/continuity_fix/nkb_update/asset_create）`submit` 前，由任务系统自动跑 `platform quality`，门禁 `block` 时拒绝提交（须修复后重提，或建 `human_gate` 放行）；`caution` 放行但须在评审重点看。质量分 = 工程零错误(logic/contract) + 机械可读性 + 可选消费项目四支柱审查报告(analysis/review/)；无深度评审时为 partial 评分（仅拦截结构性致命）。评分报告落在 `analysis/quality/`。
15. **读者模拟门禁**：内容型任务（chapter_write/chapter_fix/continuity_fix/nkb_update/asset_create）`submit` 前，由任务系统自动跑 `platform reader`，门禁对齐审查体系支柱3——`block`=读者侧致命（RR04期待值缺失 / RR03情绪平 / RR06疲劳极高 / 情绪曲线全程平直），拒绝提交；`caution`=Reader Index<60 或 PI<60，放行但须重点打磨钩子/节奏；`proceed`=读者体验达标。读者模拟报告落在 `analysis/reader/`，可选被质量评分回退消费（缺 review 报告时按 reader 维度计分）。
16. **内存治理（Memory Governance）**：`platform/memory/` 四层经验库（global/genre/project/rejected）由 `platform memory` 体检——`block`=结构错配（level↔目录错配 / status↔位置错配 / schema 损坏），`caution`=软问题（晋升门槛未达 / 疑似重复 / 失效引用 / 缺 README）。内存治理是**平台级健康检查**，接入 `doctor`（block 致 doctor FAIL），**不阻断内容型 task submit**（memory 非章节内容）。新增经验须经晋升门槛（项目→类型≥2同类型 / 类型→全局≥3跨类型），不得由单次问题直接升全局。报告落在 `analysis/memory/`。
17. **资产管理（Asset Management）**：项目内容资产（章节/NKB/sources/artifacts/参考/图片）由 `platform asset` 体检——`block`=引用断裂（AT3 missing：章节/NKB 引用的图片/参考/源文件不存在），`caution`=软问题（AT2 orphan 孤儿资产 / AT4 duplicate 重复资产）。资产管理是**项目级健康检查**，接入 `doctor`（block 致 doctor FAIL），**不阻断内容型 task submit**（资产非章节内容门禁）。报告落在 `analysis/asset/`，含资产清单(inventory)/孤儿/缺失/重复/依赖图(dependency_graph)/健康分(health)。

18. **模型布线器（Model Router）**：任务/角色→模型的路由与降级链由 `platform model` 决策（`resolve`/`validate`）。布线器只做路由决策、返回 model spec，**不调用模型**；模型调用仍由各引擎/编排器负责。`doctor` 接入模型自检（ModelGov）——`block`=无可用模型或配置损坏，`caution`=规则引用不可用模型。属平台级健康检查，**不阻断 task submit**。报告落在 `analysis/model-router/`。

19. **多项目管理（Multi-Project）**：跨项目注册 / 隔离等级解析（Global→Genre→Project→Chapter）/ 统一 dispatch 由 `platform projects` 负责（`list`/`register`/`query`/`dispatch`/`validate`）。只做注册与调度解析，**不做创作**；dispatch 协同 `platform model` 给出项目级模型。`doctor` 接入多项目自检（MultiProjGov）——`block`=注册表损坏/项目路径缺失/重复 id，`caution`=项目无 NKB/非活跃。属平台级健康检查，**不阻断 task submit**。报告落在 `analysis/multi-project/`。

20. **实验系统（Experiment）**：Prompt/模型 A/B 对照由 `platform exp` 负责（`define`/`run`/`sample`/`report`/`validate`）。定义实验、按 split 确定性分配 variant、回收 quality/reader/ci/cost 指标、判定胜者；**不自己跑创作**（挂在 task submit / model-router 上，variant 模型经 `platform model` 解析）。`doctor` 接入实验自检（ExpGov）——`block`=实验定义损坏（无 variant/model/split 非法/min_samples 非法/无 metrics），`caution`=样本不足结论未定。属平台级健康检查，**不阻断 task submit**。样本落在 `analysis/experiment/`，结果可喂经验晋升。

21. **BI 分析（Business Intelligence）**：质量/读者/实验既有数据的统一聚合由 `platform bi` 负责（`rollup`/`dashboard`/`validate`）。从 `analysis/quality/**` + `analysis/reader/**` + `analysis/experiment/**` 回收 records，按维度（project/model/capability/component/experiment）聚合指标均值、按日产出 time-series；仪表盘定义写在 `registry/bi.yaml`（`metrics`/`dimensions`/`filters`）。**不做实时采集**，空数据→0 占位不报错。`doctor` 接入 BI 自检（BiGov）——`block`=仪表盘定义损坏（缺 id/metrics/dimensions 或枚举非法），`caution`=未配置 bi.yaml（可选）。属平台级健康检查，**不阻断 task submit**。报告落在 `analysis/bi/`。

22. **图谱可视化（Knowledge Graph Viz）**：NKB 组件（Characters/Events/Graph/WorldState/Canon）转 graph JSON + HTML/SVG 由 `platform graph` 负责（`build`/`render`/`validate`）。只读 NKB、**不修改**；空 NKB→空图（0 节点/边）不报错。`doctor` 在项目循环内接入图谱自检（GraphGov）——`caution`=悬空边（引用不存在节点）/孤立节点，`proceed`=空图或健康；属项目级健康检查，**不阻断 task submit**。graph JSON 落在 `analysis/graph/GRAPH-NN.json`，HTML 落在 `GRAPH-NN.html`。

23. **市场分析（Market Analysis）**：外部市场信号摄取→机会打分→brief 由 `platform market` 负责（`ingest`/`score`/`brief`/`sync`/`validate`）。信号来自 `sources/research/market/*.yaml`（genre + trend_score/competition/reader_demand，均 0..1；competition 越低机会越大），机会分 = Σ 权重·指标（按 `registry/market.yaml` 权重，缺省 0.4/0.3/0.3）。`sync` 可选把机会分写入 NKB `Market.yaml`（不覆盖既有）。**不替代创作决策**。`doctor` 在项目循环内接入市场自检（MarketGov）——`block`=market.yaml 权重缺项/非数值/和不为 1，`caution`=未配置 market.yaml（可选）；属项目级健康检查，**不阻断 task submit**。brief 落在 `analysis/market/`。

24. **项目模板（Project Templates）**：从 genre 模板脚手架新项目由 `platform init-project` 负责（`scaffold`/`register`）。读取 `templates/<genre>/profile.yaml`（schema_version 须与 `versions.yaml` 的 `templates.<genre>` 对齐）生成 project.yaml/空 NKB/sources/overrides/lifecycle，并在 `sources/research/market/` 落地 P3-6 市场钩子（投放区 + `TEMPLATE-<genre>.yaml.example` 填表模板），同时写 `registry/projects.yaml`（P3-2 多项目注册）+ 更新 `workspace.yaml`。**不做创作**，只做脚手架与注册；`templates/` 由 system-maintainer 维护，init 仅读模板。doctor 接入模板自检（TemplateGov）——`caution`=模板缺失/已注册项目 genre 无对应模板（init-project 将失败，但不破坏既有项目）；属平台级健康检查，**不阻断 task submit**。

## 启动时序（强制）

```
读取 AGENTS.md
  → platform session（Session Bootstrap，生成 sessions/SES-*.yaml）
  → 加载角色 Policy + 验证版本与 Contract
  → 生成 Plan
  → 写 Draft / 审查 / 修复（只能通过受控工具）
  → Operation Manifest
  → Handoff（交给下一角色对话）
```

最终保障仍是：**权限 + Contract + 受控工具 + Gate**，而不是 AI 的自觉。

25. **审查三层模型（Phase B）**：正文审查严格分三层——L1 脚本预检（`platform validate`，只输出事实 findings，不下质量结论）；L2 单 Agent 多阶段深度审查（`platform review run` 生成证据包 + 空报告模板，AI 按 immersive→structural→character→continuity→synthesis 顺序逐阶段读 `evidence/chapter.md` 并填 findings）；L3 脚本后处理（校验报告 schema、落盘、登记 Issue/修复任务）。脚本不替 AI 下质量结论，AI 不被剥夺对正文的完整阅读与推理预算（详见 `core/review/审查体系.md` 与 `core/contracts/review-report.schema.yaml`）。

26. **章节摘要落盘（Phase B）**：章节结构化摘要（plot/character_changes/new_events/new_information/open_threads）由 AI 在产出契约里填写，经 `platform summary build --chapter CHx --data-file F` 落盘 `summaries/chapters/`；卷/弧聚合与全局滚动摘要由 `platform summary aggregate/rollup` 生成。脚本只落盘与聚合，不反向从正文抽取语义。摘要与 NKB 同属事实源（入库，不 gitignore）。增量修改走 `platform delta review --from F --to T`（局部 diff + 受影响实体/规则投影，对应审查体系 §7.9 Delta Review）。

27. **项目初始化与基线自检（Phase C）**：`platform init-project` 脚手架新项目时，project.yaml 的 `gates`/`capabilities`/`plugins` 由模板 `templates/<genre>/profile.yaml` 的 `defaults:` 注入（题材唯一事实源），缺失项回落平台基线（`tools/project_template.py` 的 `_PLATFORM_BASE_DEFAULTS`）。`doctor` 新增项目级基线块 **ProjectGov**（`tools/project_health.govern`）：校验 project.yaml 必需顶层键/字段、gates 数值合法、paths 声明目录存在；`block`=缺必需键、`caution`=软问题、`proceed`=健康。所有健康块统一经 `platform_cli._run_gov` 执行器（decision→PASS/WARN/FAIL 映射 + overall_fail 聚合），契约统一为 `{gate:{decision,reasons}, composite:{health}, response:{}}`。

28. **版本/审计生成器（Phase C）**：内容版本控制统一经 `platform ver`（`version_commit`）：既有 `commit/log/rollback`（按 `versions/<type>/<id>.yaml` 记 revision），Phase C 新增 `snapshot`（项目级快照到 `versions/snapshots/<ts>[_label]/`，含 `manifest.yaml` + sha256，可还原）、`snapshots`（列快照）、`compare`（两 revision 文本 diff + similarity/added/removed）、`govern`。操作审计统一经 `platform audit report`（`audit_report`）：聚合 `audit/audit.log.jsonl`（总量 / 按 action / role / agent / 日），`audit_log.record` 为 append-only 不可篡改。`doctor` 接入 **VersionGov**（versions/ 存在性）+ **AuditGov**（审计日志可读性），均 `caution` 不阻断内容任务。

29. **状态派生（Phase C）**：项目状态**不得手填**——`platform status derive`（`status_derive.derive`）从任务系统（`tasks/<status>/*.yaml` 计数 + 章节前沿抽取 + failed 阻塞检测）+ NKB（`NKB/*.yaml` 组件计数 + Foreshadow 未回收统计）自动派生，落盘 `project/status.derived.yaml`（可重生产物，不覆盖手填的 `project/status.yaml`）。派生内容：任务 by_state/total/active_types、NKB component_counts/open_foreshadows、progress（current_chapter_frontier/completed_chapter_tasks/completion_ratio_vol1）、blocked（failed 任务）、drift（手填与派生漂移提示）。`doctor` 接入 **StatusGov**（`status_derive.govern`）：`block`=project.yaml 或 NKB 缺失，`caution`=存在失败任务 / 未生成派生文件 / 手填漂移，`proceed`=正常；caution 不阻断内容型 task submit（派生状态非章节内容门禁）。

30. **报告生成器（Phase C）**：`platform report <type>`（`report_builder`）把既有派生数据渲染为可读 Markdown，脚本只做确定性聚合与渲染、不替 AI 下质量结论、缺失数据源降级提示绝不崩溃。五类报告：① `project-status`（复用 status_derive 派生态势）② `chapter-quality`（聚合 `analysis/quality` + `analysis/reader`，逐章质量分/读者指数RI/PI/门禁，汇总均值与阻断数）③ `open-foreshadow`（NKB/Foreshadow.yaml 未回收伏笔清单 + 最迟回收章）④ `task-progress`（tasks 按状态计数 + 章节前沿 + 失败阻塞）⑤ `nkb-health`（NKB 组件计数 + 空组件标记）。`all` 输出全部。`doctor` 接入 **ReportGov**（`report_builder.govern`）：`caution`=NKB 缺失（部分报告降级为空），`proceed`=正常；不阻断内容型 task submit。

31. **术语全量词表检查（Phase C）**：术语一致性以 `NKB/Terminology.yaml` 为唯一事实源——`standard` 为标准词、`forbidden` 为禁用同义（部分记录为空 `[]` 表示无同义需管）。`platform validate terminology --file F`（L1 预检）与 `platform terminology scan --project-root R`（全稿件扫描 `txt/` 树全部 `.txt`）均从 Terminology.yaml 取出**全量**禁用同义词表逐行比对，仅输出事实命中（行号 / 命中禁用词 / 应改标准词），**不替 AI 判定是否误用**。Level-1 既有 `_collect_terminology` 已修正字段映射（读 `forbidden`，兼容 `deprecated`/`aliases`）。`doctor` 接入 **TermGov**（`terminology_check.govern`）：`block`=Terminology.yaml 缺失或无记录，`proceed`=正常；不阻断内容型 task submit。
