# 读者模拟（Reader Simulation）设计稿

> **定位**：Phase 2 #3。平台侧「读者体验」自动化模拟器，是审查体系.md 支柱3（读者审查）的**可调度、可单测、无需模型**工程化落地。与 #2 质量评分同架构：独立报告 + 可选被质量评分消费 + 自带 gate 接入 task submit。

## 1. 定位与边界

- **做什么**：给定章节（或章节批），用**启发式规则引擎**模拟「读者读这一章的体验」，产出 `analysis/reader/*.yaml` 报告。
- **不做什么**：不做完整四支柱审查（那是 review 装配的职责）；不替代 LLM 主观评判——但预留 `model` 钩子，运行期若给定且可达可增强评分。
- **对齐**：信号维度严格对齐 `core/review/审查体系.md` §4 支柱3（RR01–RR08 + Immersion + Emotion Curve + PI + 5 角色 Persona），避免与审查体系重复定义。

## 2. 信号注册表（readers.yaml）

- `simulator`: `heuristic`（默认），可选 `llm`（预留）。
- `weights`（Persona 5 角色对 9 维的加权表，用于 Persona-Weighted RI，仅作 NH/商业研判参考，不参与主 Reader Index）。
- `thresholds`:
  - `rr04_min = 20`（低于视为「期待值缺失」→ Fatal B）
  - `emotion_flat_max = 8`（RR03 情绪密度低于此值视为「平」→ Fatal B）
  - `fatigue_extreme = 80`（RR06 原始疲劳高于此值 → Fatal B）
  - `curve_flat_var = 4`（情绪曲线分段方差低于此值视为「全程平直」→ Fatal B）
  - `reader_index_floor = 60`（RI<60 → caution）
  - `pi_floor = 60`（PI<60 → caution）

## 3. 评分算法（启发式）

输入：章节正文文本（去标题行）。预处理：按空行/换行切段落，再切句。

| 信号 | 计算（启发式代理） | 出戏/失效判定 |
|---|---|---|
| RR01 第一印象 | 前 200 字 hook 标记密度（对话/动作/悬念词/问句）→ 60 + hits×12，封顶 100 | — |
| RR02 阅读流畅 | 句长方差 + 平均句长代理；长句(>60字)占比扣分（复用 readability 思路） | — |
| RR03 情绪体验 | 全文情绪标记密度（对话/感叹/喜怒悲惊恐恨爱痛…）/千字 → 封顶 100 | 密度<`emotion_flat_max` → **平** |
| RR04 期待值 | 末 300 字钩子标记（却/竟/突然/没想到/悬念/谜/然而/就在这时…）→ 40 + hits×20 | score<`rr04_min` → **缺失** |
| RR05 奖励感 | 兑现标记（终于/成功/揭晓/获得/突破/胜/赢/雪耻…）密度 | — |
| RR06 疲劳度(raw) | 长段(>400字)占比 + 信息堆密度(低对话比) + 相邻 n-gram 重复 | raw>`fatigue_extreme` → **极高** |
| RR07 爽点兑现 | 打脸/反杀/碾压/逆转/扬眉/臣服/震撼…密度 | — |
| RR08 信息获取 | 新设定引入（乃是/所谓/据闻/规矩/境界/功法/朝堂/年号…）密度（不过高，避免与 RR06 冲突） | — |
| Immersion | 出戏词表（现代词/AI解释词/作者旁白跳戏）→ 100 − 命中×惩罚，下限 0 | — |
| Emotion Curve | 按位置分 6 段，逐段算情绪密度 → 形状列表 | 段间方差<`curve_flat_var` → **平直** |
| PI 付费意愿 | 由 RR04+RR05+RR07 高、RR06 低加权合成 0–100 | <`pi_floor` → 钩子弱 |
| Persona | 5 角色（老/新/爽文/剧情党/设定党）按 weights 对 9 维加权 → Persona-Weighted RI | 仅参考 |

**Reader Index** = `mean(RR01, RR02, RR03, RR04, RR05, 100−RR06, RR07, RR08, Immersion)`（0–100，对齐审查体系 §4.2）。

**Fatal B（读者侧致命）**：RR04 缺失 OR RR03 平 OR RR06 极高 OR 情绪曲线平直 → 任一中 → `fatal: true`。

## 4. Reader Report（落盘 analysis/reader/）

```yaml
meta:
  simulator: heuristic            # 或 llm
  simulated_at: "2026-07-24T21:00:00"
  project: <project_id>
  model: heuristic                # 实际使用的引擎
target:
  target_type: chapter
  target_id: "77"
  artifact_path: approved/第77章_烟.md
signals:
  rr01_first_impression: 88
  rr02_fluency: 85
  rr03_emotion: 70
  rr04_anticipation: 60
  rr05_reward: 65
  rr06_fatigue_raw: 20
  rr07_coolpoint: 72
  rr08_info: 68
  immersion: 90
  emotion_curve: [20, 45, 70, 55, 80, 40]
  persona:
    veteran: 78
    newcomer: 80
    pulp: 74
    plot: 76
    worldbuilding: 79
reader_index: 79.0
pi: 68
fatal: false
gate:
  decision: proceed              # proceed | caution | block
  reasons: []
```

## 5. reader.schema.yaml（契约）

`applies_to: ["analysis/reader/*.yaml"]`；必含段 `meta`(simulator/simulated_at/project) / `target`(target_type/target_id) / `signals` / `reader_index` / `pi` / `fatal` / `gate`(decision ∈ proceed|caution|block)。`forbidden_patterns: [TODO, FIXME, 占位, 待补]`。

## 6. reader_simulator.py（工具）

- 复用 `tools/_yaml_lite` 读写、`_find_chapter_file` 定位章节。
- `simulate(project_root, target_type, target_id, model="heuristic", write=True)` → 返回报告 dict；`write=True` 落盘 `analysis/reader/READ-<type>-<id>-NN.yaml`。
- `simulate_task(project_root, task_id, **kw)`：从 task 解析 target（chapter_ref / target）。
- `_decide(ri, pi, fatal_b, thr)`：fatal_b→block；ri<floor 或 pi<floor→caution；否则 proceed。
- `main()`：CLI verbs `sim` / `from-task` / `show`。
- LLM 钩子：`model != "heuristic"` 时尝试调用（本环境默认走启发式，钩子留空实现/抛 NotImplemented 由调用方决定）。

## 7. 装配清单

- `registry/readers.yaml`（新增）
- `core/contracts/reader.schema.yaml`（新增）
- `core/reader-sim/设计稿_reader-simulation.md`（本文件）
- `tools/reader_simulator.py`（新增）
- `registry/versions.yaml`：加 `reader_simulator: 1.0.0`
- `core/session/ROLE_REGISTRY.yaml`：加 `reader-sim` 角色（capability `reader_sim`，可写 `analysis/reader/**`，禁写核心区/chapters/approved/tasks）
- `core/policies/permissions.policy.yaml`：并行加 `reader-sim` 读写规则
- `tools/platform_cli.py`：加 `reader` 子命令（delegate 到 `reader_simulator`）
- `tools/task_engine.py`：`submit` 加 `_reader_precheck`（仅内容类任务 chapter_write/chapter_fix/continuity_fix/nkb_update/asset_create），gate=block 抛 `ValueError` 拒绝提交
- `projects/道法百年/AGENTS.md`：加 Rule 15 读者模拟门禁

## 8. 与质量评分(#2)衔接

扩展 `quality_scorer._score_review`：当 `analysis/review/` 缺失但 `analysis/reader/` 存在时，回退读 reader 报告的 `reader_index`/`pi`，并将 `fatal_b → fatal=True`；`es`/`ci` 在无全量审查时占位 100（无相反证据），detail 标注「reader-only 回退」。实现 #2 的「融合+可选消费」：有全量 review→用 review；仅有 reader sim→降级消费 reader 维度。

## 9. 待确认点 / 限制

- 启发式是**代理信号**，非真实读者主观；LLM 钩子留待模型可用时增强。
- Persona 加权 RI 仅作 NH/商业研判参考，不进主 Reader Index（对齐审查体系 §4.2）。
- 出戏词表为初版，后续可随项目专名治理扩充。

## 10. DoD（完成定义）

- [ ] readers.yaml + reader.schema.yaml 落地，doctor 通过
- [ ] reader_simulator.py 实现，启发式 9 维 + 情绪曲线 + PI + Persona 全算
- [ ] 落盘 `analysis/reader/` 报告，契约校验通过
- [ ] 自带 gate，接入 task submit 强制门（block 拒绝）
- [ ] 质量评分回退消费 reader 报告
- [ ] `tests/test_reader.py` 覆盖 proceed/caution/block/落盘/契约/submit门禁/质量回退，全 PASS
- [ ] 本地提交（不推送）

## 11. 落地步骤

1. 写契约 + 注册表（#100/#101）
2. 实现 reader_simulator.py（#102）
3. 装配平台（#104）
4. 质量评分回退接入（#103）
5. 测试 + doctor + 回归 + 本地提交（#105）
