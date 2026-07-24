# Phase 3 总设计：AI 创作平台化

> 落点：`core/phase3/设计稿_phase3总设计.md`
> 状态：待用户确认（确认后逐组件实现，沿用设计先行 + 本地提交不推送）
> 配套：Phase 1（治理层 dde16f1）/ Phase 2（#1 冲击 22cde5e / #2 质量 a6d7bd3 / #3 读者 34a6d7a / #4 内存 6ed392c / #5 资产 80a31af）

---

## 0. 目标与定位

Phase 1/2 把「单项目创作 OS」的工程能力做扎实（治理 / 影响 / 质量 / 读者 / 内存 / 资产 + 任务系统 + doctor）。
Phase 3 把它从**单项目实例**升级为**多租户、模型感知、实验驱动、数据可视的平台**：

| 维度 | Phase 2 终点 | Phase 3 目标 |
|---|---|---|
| 模型 | 引擎内硬编码/隐式模型 | 任务按类型/成本/质量**路由**到合适模型，支持降级链 |
| 实验 | 无 | Prompt/模型 **A/B 对照**，数据驱动经验晋升 |
| 数据 | 散点报告 | 质量/读者/成本/吞吐/实验**统一 BI + 图谱** |
| 项目 | 单实例（道法百年） | **跨项目**调度、NKB/经验/模板共享、统一入口 |
| 市场 | 无 | 外部市场信号纳入**规划与 NKB** |
| 模板 | init-project 基础脚手架 | 含市场钩子 + 多项目注册的**项目模板** |

**非目标（铁律）**：不新增 L1–L6 创作层规则（稳定期已定，不再加 Layer）；不改动既有契约语义（只扩展）。

---

## 1. 复用 Phase 1/2 的既有能力

| 既有能力 | 来源 | Phase 3 怎么用 |
|---|---|---|
| 任务系统生命周期 | task_engine（claim/promote/submit/review/fix） | 实验 variant 分配挂在 submit；多项目 dispatch 复用任务流 |
| 质量评分 | quality_scorer（logic/contract/readability/review） | BI 指标源；实验指标源 |
| 读者模拟 | reader_simulator（RR01–RR08/PI/Persona） | BI 指标源；实验指标源 |
| 内存治理/经验晋升 | memory_governor（SC1–SC7 + 晋升机制） | 实验结果喂经验晋升；多项目跨域查询 |
| 资产管理 | asset_manager（AT1–AT6） | 新组件报告纳入资产体检 |
| doctor 门禁 | platform_cli doctor | 每个 P3 组件接一个自检块 |
| 零依赖工具链 | _gov / _yaml_lite | 所有新引擎复用，无第三方依赖 |
| 装配基础设施 | ROLE_REGISTRY / permissions / versions / AGENTS.md | 每个组件按固化模式装配 |
| NKB + Derived | NKB.md（稳定期设计） | 图谱可视化数据源；市场事实落点 |
| 可观测性 | AI可观测性.md（指标→仪表盘） | BI 采集层 |

**扩展点**：orchestrator 增 model-router 调用；task_engine.submit 增 experiment variant 分配；doctor 增 P3 自检块。

---

## 2. 七大组件（逐个设计）

> 每个组件的「装配」均遵循固化模式：契约(`core/contracts/*.schema.yaml`) + 注册表(`registry/*.yaml`) + 引擎(`tools/*.py`) + ROLE_REGISTRY + permissions + platform_cli 子命令 + doctor 集成 + versions.yaml + AGENTS.md Rule + e2e 测试。
> 门禁统一为**报告式**：新检查接入 doctor，block→FAIL、caution→WARN；不阻断 task submit（除非该组件明确强制）。

### P3-1 模型布线器（Model Router）
- **目标**：决定每个任务/角色用哪个模型。
- **职责边界**：只做路由决策，返回 `model_id + endpoint + params`；**不调用模型**（模型调用仍由各引擎/编排器负责）。
- **输入**：`{role, task_type, capability, cost_budget, quality_tier, latency_sla}`。
- **输出**：resolved model spec（含降级链命中说明）。
- **数据模型**：
  - `registry/models.yaml`：`models: [{id, endpoint, ctx_window, cost_per_1k_in, cost_per_1k_out, quality_tier, modalities, supports:[capabilities], available}]`
  - `registry/model-router.yaml`：`rules`（按 role/task_type 匹配 primary）→ `fallback_chain` → `default`
- **接口契约**：`core/contracts/model-router.schema.yaml`（request / response 两段）。
- **装配**：ROLE_REGISTRY + permissions 增 `model-router`（只读 models.yaml/router.yaml，写 `analysis/model-router/**`）；platform_cli 接 `model` 子命令（`resolve` / `validate`）；orchestrator 调 `model_router.resolve()`；AGENTS.md Rule 18。
- **集成**：capability layer 引擎请求模型时过 router；doctor 接模型自检（models.yaml 非法/无可用模型→FAIL）。
- **验证**：`tests/test_model_router.py`（rule match / fallback / budget exceeded→cheapest / unknown role→default / 不可用模型跳过）；doctor 集成。

### P3-2 多项目管理（Multi-Project）
- **目标**：跨项目注册、调度、复用。
- **职责边界**：不做创作，只做**项目注册表 + 跨项目查询 + 统一 dispatch**。
- **输入**：扩展 `workspace.yaml` 的 `projects` 段，加 metadata（type/genre/status/created/overrides）。
- **输出**：project registry；cross-project query（按隔离等级 Global→Genre→Project→Chapter 解析事实源）；`dispatch(task, project_id)`。
- **数据模型**：
  - `registry/projects.yaml`（或扩展 workspace.yaml）：`projects: [{id, path, type, genre, status, overrides}]`
  - `core/multi-project/query.py`：隔离等级解析器（复用 Phase 2 定义的四级隔离）。
- **接口契约**：`core/contracts/project-registry.schema.yaml`。
- **装配**：ROLE_REGISTRY + permissions 增 `multi-project`；platform_cli 接 `projects` 子命令（`list` / `register` / `query` / `dispatch`）；AGENTS.md Rule 19。
- **集成**：复用 project.yaml + NKB + memory/experience；与 model-router 协同 dispatch（指定 project 用其 overrides + router 解析）。
- **验证**：`tests/test_multi_project.py`（register/list/query 隔离等级/dispatch 到指定 project）；doctor 集成。

### P3-3 实验系统（Experiment）
- **目标**：Prompt/模型 A/B 对照，数据驱动经验晋升。
- **职责边界**：定义实验、分配 variant、回收指标、判定胜者；**不自己跑创作**（挂在 task submit / model-router 上）。
- **输入**：experiment def `{name, variants:[{model, prompt, temp}], split:{by:chapter|project|random, ratio}, metrics:[quality,reader,ci,cost], min_samples, significance}`。
- **输出**：experiment report（per-variant 指标 + winner + confidence）。
- **数据模型**：`registry/experiments.yaml`；`analysis/experiment/EXP-NN.yaml`。
- **接口契约**：`core/contracts/experiment.schema.yaml`。
- **装配**：task_engine.submit 增 `_experiment_assign`（按 split 给 variant → 经 model-router 解析 model）；quality/reader 报告带 `experiment_id` 标签；ROLE_REGISTRY + permissions 增 `experiment-runner`；platform_cli 接 `exp` 子命令（`define` / `run` / `report`）；AGENTS.md Rule 20。
- **集成**：依赖 P3-1（variant 模型经 router）；指标源=quality/reader；结果喂 memory 晋升。
- **验证**：`tests/test_experiment.py`（assign split / metric aggregate / winner / significance / 样本不足不判定）；doctor 集成。

### P3-4 BI 分析（Business Intelligence）
- **目标**：质量/读者/成本/吞吐/实验 的统一分析仪表盘。
- **职责边界**：聚合既有数据，产出 rollup + dashboard JSON；**不做实时采集**（复用 observability）。
- **输入**：audit_log + `analysis/quality/**` + `analysis/reader/**` + `analysis/experiment/**` + observability metrics。
- **输出**：per-project / per-model / per-capability / time-series rollups；dashboard JSON。
- **数据模型**：`registry/bi.yaml`（dashboards 定义：metrics, dimensions, filters）；`analysis/bi/DASH-NN.yaml`。
- **接口契约**：`core/contracts/bi.schema.yaml`。
- **装配**：ROLE_REGISTRY + permissions 增 `bi-analyst`；platform_cli 接 `bi` 子命令（`rollup` / `dashboard`）；AGENTS.md Rule 21。
- **集成**：依赖 P3-1/P3-3 + observability/quality/reader（既有）。
- **验证**：`tests/test_bi.py`（aggregate by dimension / time-series / empty→0 issues）；doctor 集成。

### P3-5 图谱可视化（Knowledge Graph Viz）
- **目标**：可视化 NKB 派生图谱（关系/影响/势力）。
- **职责边界**：把 NKB Derived 转图数据 + 渲染 HTML/SVG；**不修改 NKB**。
- **输入**：`NKB/Derived.md`（关系/影响/幂图）。
- **输出**：graph JSON（nodes/edges）+ HTML 渲染。
- **数据模型**：`analysis/graph/GRAPH-NN.json`；`core/graph-viz/render.py`。
- **接口契约**：`core/contracts/graph.schema.yaml`。
- **装配**：ROLE_REGISTRY + permissions 增 `graph-viz`（只读 NKB，写 `analysis/graph/**`）；platform_cli 接 `graph` 子命令（`build` / `render`）；AGENTS.md Rule 22。
- **集成**：依赖既有 NKB Derived（稳定期已设计）。
- **验证**：`tests/test_graph_viz.py`（build nodes/edges / render html / empty→0）；doctor 集成。

### P3-6 市场分析（Market Analysis）
- **目标**：把外部市场信号纳入规划与 NKB。
- **职责边界**：市场数据摄取（人工上传 `sources/research/market` 或未来 API）+ 机会打分；**不替代创作决策**。
- **输入**：`sources/research/market/*.yaml`（genre trends / competitor / reader pref）。
- **输出**：market brief；genre opportunity score；写入 NKB K4/K7（市场事实）。
- **数据模型**：`registry/market.yaml`；`core/market-analysis/score.py`。
- **接口契约**：`core/contracts/market.schema.yaml`。
- **装配**：ROLE_REGISTRY + permissions 增 `market-analyst`；platform_cli 接 `market` 子命令（`ingest` / `score` / `brief`）；AGENTS.md Rule 23。
- **集成**：依赖 `sources/`（既有受治理区）+ NKB；喂 AI写作规划。
- **验证**：`tests/test_market.py`（ingest / score / brief / empty→0）；doctor 集成。

### P3-7 项目模板（Project Templates）
- **目标**：从模板脚手架新项目（含市场钩子 + 多项目注册）。
- **职责边界**：扩展既有 init-project，加 market-analysis 钩子 + multi-project 注册。
- **输入**：template（genre）+ project name。
- **输出**：新项目实例（project.yaml + NKB + sources + overrides + 注册到 projects.yaml）。
- **数据模型**：复用 `templates/` + init-project。
- **接口契约**：扩展 project_genesis 契约（加 market hook 段）。
- **装配**：platform_cli `init-project` 扩；ROLE_REGISTRY 已有 init；AGENTS.md Rule 24。
- **集成**：依赖 P3-2（注册）+ `sources/` + NKB genesis。
- **验证**：`tests/test_project_template.py`（scaffold + register + 幂等）；doctor 集成。

---

## 3. 组件顺序（依赖驱动）

```
P3-1 模型布线器  ─┐
                  ├─→ P3-2 多项目管理 ─┬─→ P3-3 实验系统 ─┬─→ P3-4 BI 分析
                  │                    │                 │
                  │                    │   P3-5 图谱可视化（依赖既有 NKB Derived，可并行 P3-4）
                  │                    │   P3-6 市场分析（依赖 sources/NKB，可并行 P3-5）
                  │                    └─→ P3-7 项目模板（依赖 P3-2 + init-project）
```

**推荐实现顺序**：P3-1 → P3-2 → P3-3 → P3-4 → P3-5 → P3-6 → P3-7
（P3-5/P3-6 仅依赖既有 NKB/sources，可前移与 P3-3/P3-4 并行；顺序以依赖清晰为主，不强制串行。）

---

## 4. 统一架构原则（Phase 3 全周期遵守）

1. **装配模式固化**：契约 + 注册表 + 引擎 + ROLE_REGISTRY + permissions + platform_cli 子命令 + doctor 集成 + versions.yaml + AGENTS.md Rule + e2e 测试。
2. **零依赖工具链**：复用 `_gov` + `_yaml_lite`；CLI 委托 `_delegate_gov`（子命令 `--project-root` 或 `--platform-root` 按作用域区分，沿用 asset/memory 先例）。
3. **报告式门禁**：新检查接入 doctor，block→FAIL、caution→WARN；不阻断 task submit（除非该组件明确强制，如 models.yaml 无可用模型）。
4. **可观测闭环**：所有新引擎写 audit_log，供 BI 回收；指标带 `component` / `project_id` / `experiment_id` 标签。
5. **契约先行**：每个组件先写 `*.schema.yaml`（必填段 + 枚举 + forbidden_patterns），引擎与测试围绕契约。
6. **不破稳定期架构**：不新增 L1–L6 Layer；跨切面能力（如 BI）视为平面而非 Layer。

---

## 5. 验收 DoD（每个组件）

- [ ] 设计稿小节（本文件对应段）已确认
- [ ] 契约 `core/contracts/*.schema.yaml` 落盘且字段齐备
- [ ] 注册表 `registry/*.yaml` 落盘
- [ ] 引擎 `tools/*.py` 实现，复用 `_gov`/`_yaml_lite`
- [ ] 装配：ROLE_REGISTRY + permissions + platform_cli 子命令 + versions.yaml + AGENTS.md Rule 全部到位
- [ ] doctor 集成块（block/caution 逻辑正确）
- [ ] e2e 测试 `tests/test_*.py` ≥ 7 用例全 PASS
- [ ] `doctor` 全 PASS 无回归
- [ ] 全套回归（impact/quality/reader/memory/asset + 已有 P3）全 PASS
- [ ] 本地提交（不推送），commit message 注明组件与 task 号

---

## 6. 落点文件清单（预估）

```
core/phase3/设计稿_phase3总设计.md              ← 本文件
core/model-router/  + contracts/model-router.schema.yaml + registry/models.yaml + registry/model-router.yaml + tools/model_router.py + tests/test_model_router.py
core/multi-project/ + contracts/project-registry.schema.yaml + registry/projects.yaml + tools/multi_project.py + tests/test_multi_project.py
core/experiment/    + contracts/experiment.schema.yaml + registry/experiments.yaml + tools/experiment.py + tests/test_experiment.py
core/bi/            + contracts/bi.schema.yaml + registry/bi.yaml + tools/bi.py + tests/test_bi.py
core/graph-viz/     + contracts/graph.schema.yaml + tools/graph_viz.py + tests/test_graph_viz.py
core/market-analysis/ + contracts/market.schema.yaml + registry/market.yaml + tools/market.py + tests/test_market.py
core/project-templates/ + 扩展 init-project + tests/test_project_template.py
（每组件细化设计稿在本文件确认后逐组件展开，或各自补一份 `设计稿_*.md`）
```

---

## 7. 待用户确认事项

1. 七组件范围与切分是否准确（尤其 P3-5 图谱 / P3-6 市场 的边界）？
2. 实现顺序 P3-1→P3-7 是否认可（P3-5/P3-6 可前移并行）？
3. 门禁是否统一报告式（不阻断 submit）？有无组件需强制门禁（如 models.yaml 无可用模型）？
4. 是否同意落点路径与装配模式（沿用 Phase 2 固化模式）？
5. 确认后从 P3-1 模型布线器开始，先出该组件独立设计稿再实现。
