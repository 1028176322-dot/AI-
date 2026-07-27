# Skill Reference（技能/流程加载索引）

本文件是平台三核心入口之一（另两个为 `AGENTS.md` 强制规则、`MEMORY.md` 记忆索引）。
作用：**告诉 AI 在什么意图/角色下加载哪些工具与流程**，避免每次重新阅读整个平台。

> 原则：按当前任务**按需加载**，不预先把所有工具/流程塞进上下文。
> 所有工具经 `platform <cmd>` 调用（见 `platform_cli.py`）；禁止直接绕过平台层直改项目内容。

## 一、会话生命周期（始终先走）

| 时机 | 命令 | 说明 |
|---|---|---|
| 对话开始 | `platform session bootstrap --project <id> [--intent ..] [--target ..]` | 生成 SESSION_BRIEF + MANIFEST，校验四门禁；AI 首步返回 `bootstrap_result` |
| 执行前复查 | `platform session verify --project <id>` | 重验门禁，确认未过期 |
| 中途查看 | `platform session status --project <id>` | 当前会话/任务/门禁摘要 |
| 对话结束 | `platform session close --project <id> [--stage ..] [--issues ..]` | 写 `handoffs/LATEST_HANDOFF.yaml` 交接 |

## 二、意图 → 工具/流程映射

| intent / 角色 | 应加载的工具/流程 |
|---|---|
| `chapter_write`（writer） | `task_packet`（目标契约）→ `context_builder`（最小上下文）→ 写作 → `quality_scorer` + `reader_simulator`（门禁）→ `review_orchestrator` |
| `chapter_review`（reviewer） | `reader_simulator` + `quality_scorer` + `logic_check` + `delta_review`（与上一版 diff）→ 产出 Review Report |
| `chapter_fix`（fixer） | 读取 Review Report + `controlled_write`（受控改 drafts）→ 回归审查 |
| `nkb_update`（knowledge-manager） | `validate_nkb_sources`（源/候选门禁）→ `nkb_query`（检索）→ 经 approved_event 写 NKB |
| `terminology` 检查 | `terminology_check`（全量禁用同义比对，仅事实命中） |
| 报告/态势 | `report_builder`（project-status/chapter-quality/open-foreshadow/task-progress/nkb-health） |
| 维护/体检 | `platform doctor`（全部 Gov 块）+ `status_derive`（派生状态） |
| 版本/审计 | `version_commit`（snapshot/compare）+ `audit_report` |

## 三、固定规则与状态（Level 0/1，始终加载）

- `AGENTS.md`：强制行为、安全红线、执行边界（单 Agent、禁子 Agent、NKB 唯一事实源）。
- `project.yaml`：项目配置与版本绑定（id/type/template/requires/paths/gates）。
- `project/status.derived.yaml`：由 `status_derive` 派生的进度/健康/阻塞（不手填）。
- `MEMORY.md`：长期记忆索引、项目决策入口、当前主题索引。

## 四、按需知识（Level 2/3，仅任务相关时检索）

- NKB（`NKB/*.yaml`）：人物/时间线/世界/伏笔/术语——唯一事实源，按任务投影加载。
- 章节规划 / Context Package / 前两章摘要 / ReaderState / 活跃伏笔——由 `context_builder` 生成后按引用加载。
- 历史正文 / 完整人物卡 / 完整审查标准 / 旧版本差异——仅在需要证据时读取，不预先全量加入。

## 五、禁止

- 不要直接读取全部 NKB / 全部历史正文 / 全部任务记录 / 全部审查报告 / 全部 Memory。
- 不要跳过 `session bootstrap` 直接写项目（写门禁 `require_session` 会拒绝）。
- 不要创建/委派/并行子 Agent（单 Agent 串行）。
