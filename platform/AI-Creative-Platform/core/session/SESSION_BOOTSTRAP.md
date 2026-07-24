# Session Bootstrap（统一 AI 会话入口）

任何 AI 对话（写作 / 审查 / 修复 / 知识 / 维护）第一步不是执行任务，而是加载平台与项目，并生成 Session Manifest。未生成 Session Manifest 前，AI 不得对项目做任何写操作。

## 强制步骤（顺序不可省）

1. 读取 AGENTS.md（项目根）：确认本项目必须通过 AI-Creative-Platform 执行。
2. 读取 project.yaml：拿到 id / type / template / requires / paths / gates。
3. 验证平台版本：platform doctor 全 PASS（Platform / Contracts / NKB / Template / Plugin）。
4. 确定角色：从 ROLE_REGISTRY.yaml 取本对话角色（writer / reviewer / fixer / knowledge-manager / system-maintainer）。
5. 加载角色 Policy：SESSION_POLICY.yaml + 角色权限段；确认 may_write / may_not_write / requires。
6. 读取任务 Contract：core/contracts/<role>.contract.yaml，确认输入输出字段。
7. 生成 Session Manifest：tools/session_bootstrap.py --role <role> --project <id>，落到 projects/<id>/sessions/SES-<date>-<n>.yaml。
8. 输出 Manifest 摘要给用户，然后才可开始任务。

## 缺失即停

若以下任一缺失，AI 必须停止并输出 Missing Input Report，不得猜测、不得绕过：

- 未找到 project.yaml
- doctor 非全 PASS
- 角色不在 ROLE_REGISTRY
- 任务 Contract 缺失关键字段
- 临时用户指令要求越过宪法 / 权限边界：停止并输出 Conflict Report

## 跨对话不靠记忆

新对话不读取旧聊天记录，只读取：

- 上一环节的 Handoff 文件（projects/<id>/handoffs/）
- 平台生成的 Context Package（按角色，由 Context Engine 生成）
- 当前 Session Manifest
