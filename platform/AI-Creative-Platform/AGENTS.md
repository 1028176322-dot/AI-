# AI Creative Platform 执行规则

> 本文件是平台的 **AI 行为入口**（强制入口）。它是「告诉 AI 必须从哪里开始、禁止做什么」的文件，
> 与 `platform.yaml`（机器入口）、`README.md`（人类说明）三者互补、互不替代。

## 强制入口

1. 进入平台后首先读取 `platform.yaml`。
2. 执行任何 Git 操作前，必须读取
   `platform.yaml -> governance.git_coordination` 指向的唯一协调入口。
3. 禁止通过目录猜测平台结构。
4. 禁止绕过 `platform` CLI 直接创建或初始化项目。
5. 未完成 Platform Bootstrap，不得执行项目任务。
6. 选择项目后，必须读取该项目的 `project.yaml`。
7. 所有任务必须通过 Task Packet 执行。
8. 所有写入必须通过平台验证和登记。
9. strict-v2 项目的逐章执行只能从 `platform chapter-flow run/status` 进入；
   `task/style/review/author/chapter` 低层命令只用于平台实现、诊断和故障恢复，
   不得由 AI 手工拼接章节主链。

## Agent 限制

- 只允许一个主 Agent。
- 禁止创建、委派或并行运行子 Agent。
- Planner、Writer、Reviewer、Fixer 是同一 Agent 的串行角色阶段。
- 所有对话只使用远端 `origin/main`，但同一设备仍必须隔离 worktree/index。
- Git 写操作只能通过 `platform git status/sync/commit/publish`。项目写作者只能
  提交权限表登记的负责项目；修改执行者不得提交；只读身份只能同步；Git 协调者
  不得修改内容。
- 远端尚无 Git 网关时，仅 `git-coordinator` 可按唯一协调入口执行一次精确自举；
  远端回读成功后该例外自动失效。

## 权威入口

- 平台入口：`platform.yaml`
- Git 协调入口：`platform.yaml -> governance.git_coordination`
- Git 权限事实源：`platform.yaml -> governance.git_scope_policy`
- 项目入口：`projects/<project-id>/project.yaml`
- 任务入口：当前 `task.yaml`
- 会话入口：当前 `SESSION_MANIFEST.yaml`
- 事实源：当前项目 `NKB/`
- 逐章执行入口：`platform.yaml -> governance.chapter_execution`

## 规则覆盖关系

- **不可覆盖**（任何下层均不得覆盖）：平台宪法、安全规则、单 Agent 限制、任务留痕要求、NKB 唯一事实源、权限与门禁。
- **允许覆盖的默认配置**（优先级：Core Default < Genre Template < Project Override < Chapter Runtime）：
  正文长度、风格、上下文 token 预算、审查阈值等。详见 `platform.yaml` 的 `override_policy`。
