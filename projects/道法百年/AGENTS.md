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
