# 冲击分析仪（Impact Analyzer）设计稿

> 状态：设计稿（待确认后落地）
> 所属：Phase 2 第一阶段系统（推荐顺序 #1）
> 对接底座：任务系统（task_engine） / 版本控制（version_commit） / 审计（audit_log） / NKB-SSOT / 契约注册表（registry/versions.yaml） / 角色权限（ROLE_REGISTRY + permissions.policy）

---

## 1. 定位与价值

给定一次**变更提案**（改某个角色 / 某章 / 某个设定项 / 某个 NKB 对象），在"动手改"之前反向推算**爆炸半径**：这次改动会牵动哪些章节、哪些 NKB 组件、哪些伏笔、哪些任务、哪些契约。输出**影响报告 + 门禁建议**（proceed / caution / block），把"改一处崩一片"从事故变成可预期的前置检查。

与现有底座的关系：
- **版本控制**：`versions/<type>/<id>.yaml` 的 `revisions[]` 链记录每次内容改动 → 分析仪可回溯"谁依赖了被改对象"。
- **任务系统**：`task.dependencies` 已是显性依赖图；`impact_analysis` 类型已预留 → 分析仪可自动建跟进任务。
- **NKB-SSOT**：K1–K11 组件 + `Derived.md` 关系/影响/幂图是实体级依赖源。
- **审计**：每次分析写 `audit/`，可追溯"某次变更前做过冲击分析"。

---

## 2. 依赖图数据源（4 类 + 可选 1 类）

| # | 数据源 | 位置 | 提供的边 |
|---|--------|------|----------|
| G1 | NKB 关系图 | `projects/<id>/NKB/**`（K1–K11 + `Derived.md`） | 实体↔实体（relations / 组织 / 势力 / 地图），事件(K5) participants，伏笔(K6) targets |
| G2 | 任务依赖 | `projects/<id>/tasks/**` | `task.dependencies`（任务↔任务），`task.chapter_ref`（任务→章节） |
| G3 | 版本 revision 链 | `projects/<id>/versions/**` | `revisions[]` 中 `before/after` 引用的对象（内容↔内容） |
| G4 | 伏笔关联 | `NKB/Foreshadow.yaml`（K6） | 伏笔→被引用实体/章节 |
| G5（可选） | 章节→实体引用索引 | `projects/<id>/analysis/index/chapter-entities.yaml` | 章节文本中出现的 NKB 实体重名 → 章节↔实体 |

> **G5 是本次关键设计决策**（见 §9 待确认点 1）：是否构建章节引用索引。若无索引，章节级影响只能标"需人工确认"；有索引则可精确判定"改角色 X 会影响哪些已发布章节"。

---

## 3. 分析算法

```
analyze(change):
  graph = build_graph(G1..G4 [+G5])
  seeds = resolve_seeds(change)          # 把变更目标解析为图中的节点
  affected = bfs(seeds, max_hops=3)      # 收集受影响的节点 + 边 + 跳数
  for node in affected:
      node.severity = classify(node)     # direct(1跳)/indirect(2跳)/cascade(3跳+)
      node.criticality = criticality(node)  # approved 章节 / 已发布 artifact = 高
  gate = decide(affected)                # 见 §4 门禁逻辑
  report = render(change, affected, gate, recommendations)
  write_report(report)                   # analysis/impact/<REPORT-ID>.yaml + audit
  return report
```

- **resolve_seeds**：变更目标 `(target_type, target_id)`，其中 `target_type ∈ {chapter, nkb, outline, world, asset}`（对齐 version_control 的 artifact_type，并扩展 asset）。`target_id` 为 NKB 对象路径（如 `Characters/萧咤`）或章节号（如 `042`）。
- **classify**：按 BFS 跳数定 direct/indirect/cascade；跨组件（如 角色→事件→章节）自动升一级。
- **criticality**：节点位于 `approved/`、`versions/*` 已 approved 的 after、或任务为 `critical` 优先级 → 高。

### 门禁逻辑（decide）
- 任一受影响节点属于 **`approved/`（已发布章节）或已 approved 的版本** → `block`（必须 `human_gate` 人工放行）。
- 仅命中 **drafts / NKB 未发布 / 非 critical 任务** → `caution`（创建跟进任务，建议同步修）。
- 仅命中变更对象自身、无外溢 → `proceed`。

---

## 4. 产物：影响报告（Impact Report）

落盘：`projects/<id>/analysis/impact/<REPORT-ID>.yaml`
ID 规则：`IMP-<target_type>-<target_id seq>`（如 `IMP-nkb-Characters-萧咤-01`）。

字段（契约草案见 §5）：
```
meta: { analyzer, analyzed_at, project, change_ref }
change: { target_type, target_id, diff_summary, proposed_by }
affected:
  - { kind: nkb|chapter|task|foreshadow|version, id, relation, severity, criticality, evidence }
gate: { decision: proceed|caution|block, reasons: [..] }
recommendations:
  - { action: "sync_update"|"human_review"|"create_task", target, detail }
```

示例（改角色"萧咤"的阵营归属）：
```
affected:
  - { kind: nkb, id: Events/永熙政变, relation: participants, severity: direct, criticality: high }
  - { kind: foreshadow, id: FB-033, relation: targets, severity: indirect, criticality: medium }
  - { kind: chapter, id: "042", relation: references(索引), severity: indirect, criticality: high(approved) }
gate: { decision: block, reasons: ["影响已发布章节 042"] }
recommendations:
  - { action: human_review, target: "042", detail: "阵营变更需人工确认是否回改第042章" }
```

---

## 5. 契约草案 `core/contracts/impact.schema.yaml`

（实现时严格遵循 `_yaml_lite` 约束：不用 `|` 块标量；列表 dict 项 dash 同行；空列表渲染 `key: []`）

```yaml
schema_id: impact
version: 1.0.0
applies_to: ["analysis/impact/*.yaml"]
description: 变更影响分析报告契约（Impact Analyzer）
requires_document_header: false
top_level_sections:
  - name: meta
    required_fields: [analyzer, analyzed_at, project]
  - name: change
    required_fields: [target_type, target_id]
  - name: affected
    required_fields: []
  - name: gate
    required_fields: [decision]
nested_required:
  change: [target_type, target_id]
  gate: [decision]
severity_enum: [direct, indirect, cascade]
decision_enum: [proceed, caution, block]
criticality_enum: [low, medium, high]
forbidden_patterns: ["TODO", "FIXME", "占位", "待补"]
```

> 注意：`affected` 为列表，每项含 `kind/id/relation/severity/criticality/evidence`；`recommendations` 同结构。实现时按 `_gov.dump_block` 的列表 dict 规则序列化。

---

## 6. 工具设计 `tools/impact_analyzer.py`

复用：`_gov.load_yaml / dump_block / find_project`、`audit_log.record`、`version_commit.log`、`task_engine.find_task / list_tasks`。

API：
- `build_graph(project_root)` → 内存图（networkx 可选，默认用 dict+邻接表，零依赖）
- `analyze(project_root, target_type, target_id, diff_summary="", proposed_by="unknown")` → report dict；写 `analysis/impact/<ID>.yaml` + `audit_log.record(action="impact_analysis")`
- `render_index(project_root)` → 构建/刷新 G5 章节→实体索引 `analysis/index/chapter-entities.yaml`（扫描 `approved/` + `chapters/drafts/` 文本，对 NKB 实体重名匹配）
- `classify(node, hops)` / `decide(affected)` 纯函数，便于单测

CLI（经 `platform_cli` 委托，REMAINDER 捕获自有参数）：
```
platform impact --analyze --target-type nkb --target-id "Characters/萧咤" --reason "阵营变更"
platform impact --from-task <TASK-ID>        # 分析某任务目标的变更影响（claim 前预检）
platform impact --index                       # 重建章节→实体引用索引
platform impact --show <REPORT-ID>
```

---

## 7. 平台装配清单（落地时执行）

| 文件 | 改动 |
|------|------|
| `core/contracts/impact.schema.yaml` | 新增（§5 草案） |
| `tools/impact_analyzer.py` | 新增 |
| `registry/versions.yaml` | `core:` 下加 `impact_analyzer: 1.0.0`；`contract: 1.2.0 → 1.3.0` |
| `core/session/ROLE_REGISTRY.yaml` | 新增角色 `impact-analyzer`（capabilities: [impact_analysis]，may_write: `analysis/impact/**` + `analysis/index/**`，may_not_write: core/registry/NKB/chapters/approved/tasks） |
| `core/policies/permissions.policy.yaml` | 新增 `impact-analyzer` allow_write/deny_write（对齐 ROLE_REGISTRY） |
| `cli/platform.py` | `build_parser` 加 `impact`（REMAINDER）；`_delegate_gov` 加 `"impact":"impact_analyzer"` |
| `projects/道法百年/AGENTS.md` | 新增规则：高爆炸半径变更（角色/设定/主线事件）前须 `platform impact --analyze`，gate=block 必须 human_gate 放行 |

---

## 8. 与任务系统 / 版本控制 / 审计的衔接

- **任务系统**：`impact_analysis` 已是合法 task.type。分析仪可（可选，见 §9 待确认点 2）在 `claim`/`start` 前自动跑 `analyze`，若 gate=block 则拒绝 claim 并提示 human_gate。分析报告中的 `recommendations[action=create_task]` 可调用 `task_engine.create_task` 建跟进任务（依赖被改任务）。
- **版本控制**：`analyze` 会读 `version_commit.log` 拿到被改对象的 revision 链；报告中 `version` 类 affected 节点直接引用 `REV-*` id 作为 evidence。
- **审计**：每次 `analyze` 写 `audit_log.record(action="impact_analysis", files=[报告相对路径], result=success/fail, detail="gate=block")`，可追溯。

---

## 9. 范围与边界（已知限制 + 待确认点）

**待确认点（请你拍板）：**
1. **章节影响判定（G5）**：
   - 方案 A（推荐）：构建章节→实体引用索引 `analysis/index/chapter-entities.yaml`（扫描 NKB 实体重名 vs 章节文本），可精确判定"改 X 影响哪些章节"。索引用 `platform impact --index` 构建/刷新。
   - 方案 B：仅用 NKB 内部图 + 任务依赖，章节级影响标 `需人工确认`，不自动判定。
2. **是否接入任务系统 claim/start 作为强制预检门**（gate=block 自动阻断 claim，需 human_gate）。还是仅作"按需手动跑"的工具，不强制。
3. **报告落盘区** `analysis/impact/` 与索引区 `analysis/index/` 作为新增受治理区，是否 OK（当前项目目录无 `analysis/`，需建）。
4. **角色名** `impact-analyzer` 是否沿用此命名。

**已知限制：**
- 第一版 G5 索引为"重名匹配"，可能产生误报（同名著称）。后续可升级为 NKB 对象 ID 显式标注（章节元数据引用实体 ID）以消除误报——属 Phase 2 后续增强，不在本系统设计内。
- 跨项目影响（同一 NKB 被多项目引用）不在本期范围；本系统仅分析单项目内依赖。

---

## 10. 验收 DoD

- [ ] `core/contracts/impact.schema.yaml` 通过契约校验（无 `|` 块标量，字段齐全）。
- [ ] `platform impact --analyze --target-type nkb --target-id "Characters/X"` 在测试项目上产出 `analysis/impact/IMP-*.yaml`，结构符合契约。
- [ ] gate 逻辑正确：注入"影响已发布章节"的用例 → `block`；仅自影响 → `proceed`。
- [ ] `platform impact --index` 在测试项目生成 `analysis/index/chapter-entities.yaml`；后续 `--analyze` 能命中章节级影响。
- [ ] 每次分析写 `audit/`，`doctor` 无回归。
- [ ] 装配项（registry/versions 升 1.3.0、ROLE_REGISTRY、permissions、platform_cli 委托、AGENTS 规则）全部落地。
- [ ] 端到端测试脚本清理，不纳入 git。

---

## 11. 落地步骤顺序（确认后执行）

1. 写 `core/contracts/impact.schema.yaml`
2. 写 `tools/impact_analyzer.py`（build_graph / analyze / render_index / classify / decide + CLI）
3. 装配：registry/versions(1.3.0) / ROLE_REGISTRY / permissions / platform_cli 委托 / AGENTS 规则
4. 端到端验证（测试项目，覆盖 proceed/caution/block 三态 + 索引命中）
5. `doctor` 全 PASS → 本地提交（不 push，沿用本轮"进二阶段不推送"）
