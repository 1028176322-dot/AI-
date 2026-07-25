# 设计稿 · 内存治理（Memory Governance）

> Phase 2 #4 · 配套 reader-sim/quality-score/impact-analyzer 的第四道平台能力。
> 目标：把 `memory/` 四层经验库（global/genre/project/rejected）从「约定文档」变成「系统可校验、可体检、可防退化」的受治理资产。

## §1 定位
- **不是**章节内容门禁（与 quality/reader 不同）。内存治理是**平台级健康工具**，对 `platform/memory/` 目录做体检。
- 三重职责：① schema 合法性 ② 晋升门槛执行（防把单项目特例误升全局）③ 退化/重复检测（防污染）。
- 接入点：`platform memory` 子命令（validate/report/dedup）+ `doctor` 平台健康检查。报告式门禁，**不阻断 task submit**（memory 非章节内容）。

## §2 治理对象
`platform/AI-Creative-Platform/memory/`：
```
memory/
├── global/   跨多项目验证的通用经验（最高级）
├── genre/    仅对某种类型有效（按题材分子目录，如 xuanhuan/）
├── project/  仅当前小说使用（每个项目私有）
├── rejected/ 被否决 / 降级 / 误报率高的经验
└── 晋升机制.md
```
条目格式（见 §5 契约 + 晋升机制.md）：
```yaml
id: MEM-G-001
level: global | genre | project
problem: 现象
root_cause: 根因
action: [处置步骤]
validated_projects: N
confidence: 0.0~1.0
status: active | deprecated
# genre 级附加：genre: xuanhuan
# project 级附加：scope: current_project
```

## §3 检查项（全量治理）
1. **SC1 schema 合法**：必填字段齐全、类型正确、confidence∈[0,1]、id 格式 `MEM-(G|XH|P|R)-NNN` 与 level 一致。
2. **SC2 level↔目录一致**：global 条目必须在 `global/`、genre 在 `genre/<genre>/`、project 在 `project/`、rejected 在 `rejected/`；错配=block。
3. **SC3 status↔位置一致**：`status: deprecated` 必须在 `rejected/`；`active` 不得在 `rejected/`；错配=block。
4. **SC4 晋升门槛执行**：
   - project→genre：`validated_projects >= 2` 且同类型 ≥2 项目（genre 级要求）。
   - genre→global：`validated_projects >= 3` 且跨类型（global 级要求）。
   - 未达门槛但 level 高于应有=caution（提示但非结构违规）。
5. **SC5 重复检测**：同层内 `problem` 归一（去标点/小写/分词）相似度 ≥ 阈值（默认 0.85）判定重复=caution，列出候选合并。
6. **SC6 失效引用**：action 引用了不存在的文件/规则（轻量：仅查 `../晋升机制.md` 类相对路径存在性）=caution。
7. **SC7 孤立 README**：各级目录缺 README 提示（不强制）。

## §4 门禁决策（报告式）
- `fatal` = SC2/SC3 任一命中（结构错配）→ **block**。
- `caution` = SC4/SC5/SC6 命中（软问题）。
- `proceed` = 全清。
- 门禁**只报告**，不阻断 task submit（memory 非内容门禁）；但 `doctor` 会因 block 而 FAIL，作为平台健康红线。

## §5 memory.schema.yaml 契约
- `applies_to: ["memory/**/*.yaml"]`
- 必填：`id` `level` `problem` `root_cause` `action`(list) `validated_projects`(int) `confidence`(float 0~1) `status`
- 条件必填：`genre`(level=genre) / `scope`(level=project)
- `forbidden_patterns: ["TODO","FIXME","占位","待补"]`

## §6 引擎 memory_governor.py
- `govern(platform_root, write=True)`：遍历 `memory/` 四层 → 跑 SC1–SC7 → 产出 report dict。
- report 结构：`meta` / `target`(memory根) / `signals`(各 SC 结果+计数) / `composite`(健康分=100-扣分) / `fatal` / `gate` / `duplicates` / `recommendations`。
- 健康分 `health` = 100 − (fatal×40 + caution×5)，下限 0。
- 预留 `model` 参数：给定且可用时，SC5 重复检测改用嵌入相似度（默认启发式）。
- CLI：`platform memory validate`（仅校验）/ `report`（产出报告文件）/ `dedup`（列出重复候选）。
- 报告落点：`analysis/memory/<平台版本>/MEM-<NN>.yaml`（analysis 下新增 memory 子目录）。

## §7 装配清单
1. `core/contracts/memory.schema.yaml`（契约）
2. `registry/memory.yaml`（晋升门槛/重复阈值/门禁阈值/README 要求）
3. `tools/memory_governor.py`（引擎）
4. `core/session/ROLE_REGISTRY.yaml`：加 `memory-governor`（may_write `analysis/memory/**`，may_not_write `memory/**` 本身——只读体检）
5. `core/policies/permissions.policy.yaml`：mirror
6. `cli/platform.py`：加 `memory` 子命令
7. `cli/platform.py doctor`：接入 memory 自检（block→doctor FAIL）
8. `registry/versions.yaml`：加 `memory_governor: 1.0.0`
9. `projects/道法百年/AGENTS.md`：加 Rule 16 内存治理

## §8 与既有体系衔接
- 复用 `quality_scorer` 的 `_safe_load`/`_rel`/`_write_report` 模式（从 `tools/` import）。
- 不接 `task_engine.submit`（非内容门禁），与 quality/reader 明确区分。
- 复用 `_yaml_lite`（已修 CRLF）。

## §9 待确认 / 限制
- 晋升门槛的「项目数」目前靠 `validated_projects` 字段自报；不强制跨项目真实验证（平台暂无多项目实例），仅校验字段逻辑。
- `action` 失效引用检测为轻量路径存在性，不解析内容。
- 重复检测默认启发式归一相似度，LLM 增强为可选。

## §10 DoD（完成定义）
- [ ] contract + registry + engine 三件套落地
- [ ] `platform memory validate/report/dedup` 可用
- [ ] `doctor` 接入且当前 memory/ 为 proceed（无结构错配）
- [ ] tests/test_memory.py ≥ 6 用例（ok/block/重复/caution/落盘/契约/doctor集成）
- [ ] impact/quality/reader 回归无破坏
- [ ] 本地提交（不推送）

## §11 落地步骤
1. 写 `memory.schema.yaml` + `registry/memory.yaml`
2. 写 `memory_governor.py`，`govern()` 跑 SC1–SC7
3. 装配 role/perm/CLI/doctor/versions/AGENTS
4. 写 e2e 测试 + 跑 doctor + 回归
5. 本地提交
