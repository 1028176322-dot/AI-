# AI Execution Rules（强制入口）

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
