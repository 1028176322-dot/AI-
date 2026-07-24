# 设计稿 · 资产管理（Asset Management）

> Phase 2 #5 · 配套 impact-analyzer / quality-score / reader-sim / memory-governance 的第五道平台能力。
> 目标：把项目内容资产（章节 / NKB / 源事实 / 产出物 / 参考资料 / 图片）从「散落文件」变成
> 「可盘点、可体检、可防引用断裂 / 重复 / 孤儿」的受治理资产。

## §1 定位
- **项目级内容资产体检**（区别于 #4 平台级 `memory/` 治理）。资产管理治「内容资产」，内存治理治「平台经验库」。
- 三重职责：① 资产盘点（inventory）② 引用完整性（防 orphan / missing）③ 退化 / 重复检测（防污染）。
- 接入点：`platform asset` 子命令（inventory / report / orphans / missing / dedup）+ `doctor` 平台健康检查。
- 门禁：**报告式**（同 #4）。`missing`=block → `doctor` FAIL 作为发布红线；但**不阻断 task submit**（资产非章节内容门禁，quality/reader 才是内容门禁）。

## §2 治理对象
项目根下（paths 可配，默认取自 `project.yaml`）：
```
章节     paths.chapters        = ./txt            （递归 .md/.txt）
NKB      paths.nkb             = ./NKB            （*.yaml，11 组件；Assets 为 K7）
大纲     paths.outline         = ./大纲_1000章总体规划.md
源事实   sources/              = ./sources        （canon/design/governance/inbox/manuscripts/outline/research/）
产出物   paths.artifacts       = ./artifacts      （忽略 README.md）
参考资料 参考资料/            顶层素材目录
图片    图片/               顶层素材目录
```
实际项目已验证：txt/ 分卷子目录、NKB/ 11 组件 yaml、sources/ 含 inbox/ 收件箱、artifacts/ 仅 README、顶层 参考资料/ 图片/ 存在。

## §3 检查项（全量治理）
- **AT1 inventory 资产清单**：按类型（章节 / NKB / 源 / 产出 / 参考 / 图片）统计文件数、总字节、最新修改时间。
- **AT2 orphan 孤儿资产**（存在但无人引用）：
  - `sources/inbox/` 下未归类文件（收件箱滞留）。
  - `artifacts/` 非 README 文件，且其文件名 / 路径未被任何章节 / NKB 文本引用字符串包含。
  - `sources/` 下文件未被任何 NKB record 的 `source` / `ref` 字段反向引用。
- **AT3 missing 缺失资产**（被引用但不存在）：
  - NKB record 的 `source` / `ref` 路径字符串指向的文件不存在。
  - 章节 / NKB 文本中引用的 `图片/*` / `参考资料/*` / `.md` 相对路径不存在。
  - （轻量：扫描引用路径字符串存在性，不解析语义。）
- **AT4 duplicate 重复资产**：同类型文件内容归一（去标点 / 小写 / 字符 bigram）相似度 ≥ 阈值（默认 0.85）判定重复 = caution。
- **AT5 dependency 依赖图**：记录引用边 `from → to`，输出 graph 数据到报告（供可视化 / 调试）。
- **AT6 health 健康分**：`health = max(0, 100 − missing×fatal_penalty − orphan×caution_penalty − duplicate×caution_penalty)`。

## §4 门禁决策（报告式，同 #4）
- `fatal` = AT3 missing 任一命中（引用断裂，影响发布）→ **block**。
- `caution` = AT2 orphan / AT4 duplicate 命中（软问题）。
- `proceed` = 全清。
- 门禁只报告，不阻断 task submit（资产非内容门禁）；但 `doctor` 会因 block 而 FAIL，作为平台健康红线。

## §5 asset.schema.yaml 契约
- `applies_to: ["analysis/asset/**/*.yaml"]`
- 必填：`meta`(scorer/scored_at/project) / `target`(project_root / asset_summary) / `signals`(AT1–AT6) /
  `composite`(health) / `fatal` / `gate` / `orphans` / `missing` / `duplicates` / `dependency_graph` / `recommendations`
- `forbidden_patterns: ["TODO","FIXME","占位","待补"]`

## §6 引擎 asset_manager.py
- `govern(project_root, write=True, proposed_by="unknown", model="unknown")`：扫描 → 跑 AT1–AT6 → 产出 report dict。
- report 结构：`meta` / `target` / `signals`(各 AT 结果+计数) / `composite`(health) / `fatal` / `gate` / `orphans` / `missing` / `duplicates` / `dependency_graph` / `recommendations`。
- 健康分 `health = max(0, 100 − 扣分)`，下限 0。
- 报告落点：`analysis/asset/AST-<NN>.yaml`（项目侧 `analysis/` 已存在）。
- CLI：`platform asset inventory`（仅清单）/ `report`（产出报告）/ `orphans` / `missing` / `dedup`。
- 复用 `_gov` / `audit_log` / `_yaml_lite`（已修 CRLF）。

## §7 装配清单
1. `core/contracts/asset.schema.yaml`（契约）
2. `registry/asset.yaml`（orphan/missing/duplicate 阈值、扣分权重、引用检测开关、inbox 视为孤儿）
3. `tools/asset_manager.py`（引擎）
4. `core/session/ROLE_REGISTRY.yaml`：加 `asset-manager`（may_write `analysis/asset/**`，只读内容目录）
5. `core/policies/permissions.policy.yaml`：mirror
6. `tools/platform_cli.py`：加 `asset` 子命令（`--project-root`，委托 asset_manager）
7. `tools/platform_cli.py doctor`：接入 asset 自检（block → FAIL）
8. `registry/versions.yaml`：加 `asset_manager: 1.0.0`
9. `projects/道法百年/AGENTS.md`：加 Rule 17 资产管理

## §8 与既有体系衔接
- 复用 `memory_governor` 的 `_safe_load` / `_rel` / `_write_report` 模式（从 `tools/` import）。
- 不接 `task_engine.submit`（非内容门禁），与 quality/reader 明确区分，与 memory-governor 一致。
- 复用 `_yaml_lite`（已修 CRLF）。

## §9 待确认 / 限制
- 引用检测为轻量路径存在性，不解析语义、不追踪 NKB 内部 record 引用链。
- 相似度默认启发式归一相似度，LLM 增强为可选（预留 `model` 参数）。
- `sources/inbox/` 全部视为孤儿候选，除非被某 NKB record 反向引用。

## §10 DoD（完成定义）
- [ ] contract + registry + engine 三件套落地
- [ ] `platform asset inventory/report/orphans/missing/dedup` 可用
- [ ] `doctor` 接入且当前项目为 proceed 或 caution（无 missing → block）
- [ ] `tests/test_asset.py` ≥ 6 用例（inventory / orphan / missing→block / duplicate / 落盘 / 契约 / doctor 集成）
- [ ] impact/quality/reader/memory 回归无破坏
- [ ] 本地提交（不推送）

## §11 落地步骤
1. 写 `asset.schema.yaml` + `registry/asset.yaml`
2. 写 `asset_manager.py`，`govern()` 跑 AT1–AT6
3. 装配 role / perm / CLI / doctor / versions / AGENTS
4. 写 e2e 测试 + 跑 doctor + 回归
5. 本地提交
