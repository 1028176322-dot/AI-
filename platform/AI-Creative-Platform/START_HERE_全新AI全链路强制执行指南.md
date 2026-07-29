# AI Creative Platform 新项目全链路强制执行指南

> **用途**：这是给“第一次进入本工作空间、没有任何上下文”的 AI 使用的唯一流程入口。
> **适用范围**：所有按 `strict-v2` 新建的小说项目；已有旧项目不强制迁移。
> **目标**：从用户的一句话灵感开始，依次完成立项、资料准备、参考小说学习、设计、NKB Genesis、全书逐章详纲、章节写作、审查、修复、反补、真人读者验证、NKB 同步、正式发布，最后让合格正文以 TXT 落地。
> **核心原则**：聊天内容是“任务请求”，不是“文件写入授权”；任何阶段没有通过门禁，都不得进入下一阶段。
> **本次修订**：2026-07-29；补齐统一成稿、稳定批量依赖、参考规则消费、可信人工门禁和 Git 协作约束。

---

## 0. 新 AI 读完本文件后必须立即遵守的执行协议

你是平台内唯一主 Agent。读完本文件后，必须按以下顺序行动：

1. 先确认 `PLATFORM_ROOT`、`WORKSPACE_ROOT`、`PROJECT_ROOT`、`PROJECT_ID`；不知道时从清单和配置读取，禁止猜目录。
2. 读取平台与项目的权威文件，执行平台体检、项目目录校验、Broker 状态检查和会话启动。
3. 把用户在聊天框输入的“立项、生成 NKB、写多少章、审查、修改、发布”等自然语言，先派发为平台任务。
4. 只执行任务系统返回的当前合法任务，先读完整 Task Packet，再认领、启动和产出。
5. 每个任务完成后，只使用任务模板声明的事件推进状态机；不得凭自己判断跳到后面的任务。
6. 任何校验、审查、回归、NKB 同步或权限门禁未通过，必须停在当前阶段，修复后复验。
7. 任何新事实先进入 Candidate Queue；只有 `knowledge-manager` 持 `approved_event` 才能更新 NKB。
8. 正式章节只能由 Publish Service 经 Broker 发布。AI、writer、reviewer 均不得直接写 `chapters/approved/`。
9. 全程仅一个主 Agent 串行切换角色；禁止子 Agent、委派、多 Agent 并行和绕过平台脚本。
10. 若平台规则、任务包与用户临时口头指令冲突，先报告冲突并进入阻塞；不得越权执行。

新 AI 第一次回复用户时，至少要报告：

```text
平台：AI Creative Platform
项目：<PROJECT_ID>
项目状态：<lifecycle/status.yaml 中的状态>
当前会话：<SESSION_ID 或 BLOCKED>
当前任务：<TASK_ID / task type / state，或 BLOCKED>
Broker：<DEPLOYED_AND_VERIFIED 或 BLOCKED>
下一项强制动作：<唯一合法下一步>
```

如果无法给出上述信息，说明启动尚未完成，禁止开始设计、写作、审查、修改或发布。

---

## 1. 固定位置、变量与权威顺序

### 1.1 默认路径

| 变量 | 默认值 | 用途 |
|---|---|---|
| `WORKSPACE_ROOT` | `D:\AI-Workspace` | 工作空间根 |
| `PLATFORM_ROOT` | `D:\AI-Workspace\platform\AI-Creative-Platform` | 平台代码、规则与 CLI |
| `PROJECTS_ROOT` | `D:\AI-Workspace\projects` | 新项目统一父目录 |
| `PROJECT_ROOT` | `D:\AI-Workspace\projects\<project-dir>` | 当前实际项目根 |
| `PLATFORM_CMD` | `D:\AI-Workspace\platform\AI-Creative-Platform\platform.bat` | Windows 平台统一入口 |

不得把平台根当成项目根，不得把项目文件散落在工作空间根、平台根或聊天附件目录。

### 1.2 权威文件优先级

发生冲突时，按以下顺序处理；低层文件不得覆盖高层硬规则：

1. `PLATFORM_ROOT/AGENTS.md`
2. `PLATFORM_ROOT/platform.yaml`
3. `PLATFORM_ROOT/core/constitution/AI写作宪法.md`
4. `PLATFORM_ROOT/core/policies/*.yaml`
5. `PROJECT_ROOT/AGENTS.md`
6. `PROJECT_ROOT/PROJECT_LAYOUT.yaml`
7. `PROJECT_ROOT/project.yaml`
8. `PROJECT_ROOT/lifecycle/status.yaml` 与各阶段审批文件
9. `PROJECT_ROOT/NKB/manifest.yaml` 及 NKB 组件
10. `PROJECT_ROOT/sources/outline/**` 中已批准的大纲
11. 当前 Task Packet、Session Manifest 与运行时 guidance
12. 当前草稿、审查报告和对话内容

关键解释：

- NKB 是项目事实唯一真相源；对话、参考小说、AI 推断、大纲草案都不能直接成为正史。
- 已批准大纲约束“这一章要发生什么”；写作策略和风格 guidance 约束“如何写”。
- 参考小说只提供抽象、非逐字的技法证据，不能覆盖世界观、人物事实、剧情决策和作者批准项。
- 审查报告可以驱动修复和形成写作防错规则，但不能自行修改 NKB 正史。

---

## 2. 平台现行规范与实现入口

新 AI 不得只读本指南而忽略实际配置。启动时必须读取：

| 文件 | 用法 |
|---|---|
| `PLATFORM_ROOT/AGENTS.md` | AI 行为红线、启动要求、禁止事项 |
| `PLATFORM_ROOT/platform.yaml` | CLI、路径、注册表、门禁、单 Agent 配置 |
| `PLATFORM_ROOT/core/project-lifecycle/项目生命周期总规范.md` | P0—P6 生命周期 |
| `PLATFORM_ROOT/core/project-lifecycle/项目状态机.md` | 项目状态与迁移条件 |
| `PLATFORM_ROOT/core/project-lifecycle/创意收集规范.md` | 灵感如何变成正式输入 |
| `PLATFORM_ROOT/core/project-lifecycle/项目立项规范.md` | 立项交付物与门禁 |
| `PLATFORM_ROOT/core/project-lifecycle/项目定义规范.md` | 受众、定位、边界 |
| `PLATFORM_ROOT/core/project-lifecycle/创作设计规范.md` | 世界、人物、冲突、结构设计 |
| `PLATFORM_ROOT/core/project-lifecycle/AI自主设计与NKB生成规范.md` | AI 补全设计与 Genesis 的边界 |
| `PLATFORM_ROOT/core/project-lifecycle/NKB初始化规范.md` | NKB Genesis 规则 |
| `PLATFORM_ROOT/core/project-lifecycle/开写准备度规范.md` | ready_for_writing 门禁 |
| `PLATFORM_ROOT/core/project-lifecycle/五级大纲生成与滚动规划规范.md` | 全书逐章详纲与发布后刷新 |
| `PLATFORM_ROOT/core/project-lifecycle/自适应写作手法与章节首尾规范.md` | 情节/环境适配、开头结尾变化 |
| `PLATFORM_ROOT/core/knowledge/NKB信息源与入库规范.md` | NKB 来源分级、候选、审批、入库 |
| `PLATFORM_ROOT/core/learning/自主学习与反馈闭环.md` | 参考学习、审查反补、真人反馈 |
| `PLATFORM_ROOT/core/learning/风格系统与去AI味实施纲要.md` | 风格学习、诊断、修订、回归 |
| `PLATFORM_ROOT/core/learning/风格系统实施状态.md` | 已实现功能与当前边界 |
| `PLATFORM_ROOT/core/review/审查体系.md` | 审查维度和合格定义 |
| `PLATFORM_ROOT/core/review/review-plan.yaml` | 审查编排与检查项 |
| `PLATFORM_ROOT/core/task-system/templates/*.task.yaml` | 每类任务的输入、输出、权限和下一任务 |

注意：发现与 strict-v2 不一致的旧文档、旧项目目录或旧脚本时，以 `PROJECT_LAYOUT.yaml`、现行任务模板和 CLI 实现为准。旧版根目录 `txt/`、手工复制定稿、跳过 Broker 等做法不得用于新项目。

---

## 3. 每次对话/每次工作开始的强制启动链

### 3.1 启动前只读检查

按顺序执行：

```powershell
Set-Location "<当前设备上的 PLATFORM_ROOT>"
.\platform.bat bootstrap
.\platform.bat doctor --quick
.\platform.bat layout validate --project-root "<PROJECT_ROOT>"
.\platform.bat broker deploy --mode Verify --project-root "<PROJECT_ROOT>"
.\platform.bat broker status --project-root "<PROJECT_ROOT>"
.\platform.bat ready --project-root "<PROJECT_ROOT>" --preflight
```

解释：

- `bootstrap` 或 `doctor --quick` 失败：先修平台，不得执行项目任务。
- `layout validate` 失败：先恢复目录合规，不得在临时目录继续工作。
- Broker 未部署或 ACL 未验证：禁止任何正式受控写和发布。
- `ready --preflight` 若返回项目未准备好：只能执行当前生命周期允许的设计、NKB、准备度任务，禁止写正文。

### 3.2 Broker 跨设备统一部署是单项目、单设备门禁

新 strict-v2 项目初始状态默认是 `BLOCKED_NOT_DEPLOYED`。Broker 部署属于本机安全边界，不随 Git、项目复制或聊天会话迁移。即使：

- 同一项目已在设备 A 部署；
- 设备 B 已为另一个项目部署 Broker；
- 项目目录中存在旧的 `broker-deployment.json`；

当前“设备 × 项目”组合仍必须运行统一部署入口并取得本机验证证据，才能解除阻塞。

#### 3.2.1 唯一允许的部署入口

所有 AI、所有 Windows 设备只能调用：

```powershell
Set-Location "<当前设备上的 PLATFORM_ROOT>"

# 1. 只读预检：不需要管理员权限
.\platform.bat broker deploy --mode Plan --project-root "<PROJECT_ROOT>"

# 2. 自动部署：只允许在用户批准后执行；非管理员时只触发一次 Windows UAC
.\platform.bat broker deploy --mode Apply --project-root "<PROJECT_ROOT>" --auto-elevate

# 3. 独立复验：Apply 返回成功后仍必须执行
.\platform.bat broker deploy --mode Verify --project-root "<PROJECT_ROOT>"

# 4. 运行状态复读
.\platform.bat broker status --project-root "<PROJECT_ROOT>"
```

禁止 AI 自己组合或直接使用以下方式部署：

- `New-LocalUser`、`sc.exe create`、`reg.exe`、`icacls.exe`；
- 直接执行 `broker acl-apply` 后就声称 Broker 已部署；
- 自写 PowerShell、批处理、Python、安装器或 Windows 服务包装器；
- 复制另一台设备的密钥、注册表项、服务账号密码或部署报告；
- 使用固定 `AIStyleChapterWriter` 服务覆盖另一个项目；
- 以管理员常驻进程、普通用户进程或临时 `broker serve` 代替正式服务；
- 因部署失败而关闭 strict-v2、放宽 ACL 或恢复直接写。

`broker acl-plan/acl-apply/acl-verify` 是统一部署脚本内部使用的低层诊断能力，不是新项目完整部署入口。

#### 3.2.2 权威脚本和固定实现

CLI 只能调用仓库内这一个部署脚本：

```text
scripts/logs/deploy_broker_windows.ps1
```

相关固定实现：

```text
scripts/logs/broker_cli.py                 # platform broker deploy 的 CLI 适配
scripts/logs/broker_windows_service.py     # 原生 Windows Service 宿主
scripts/logs/broker.py                     # 授权、capability、CAS、原子写
scripts/learning/controlled_chapter_client.py # TaskRunner 唯一客户端
```

AI 不得复制、改名或在项目中生成脚本副本。确需变更部署逻辑时，只能修改上述平台实现、测试和本指南，再统一升级所有设备。

CLI 仅为本次受控子进程使用 `ExecutionPolicy Bypass` 运行仓库内固定脚本，不修改设备级 PowerShell 执行策略；AI 禁止自行执行 `Set-ExecutionPolicy`。

若 Codex、CI Agent 或企业设备管理器在启动 CLI **之前**就完成了外部提权，
官方启动器必须仅在该部署子进程中设置
`ACP_BROKER_INITIATING_IDENTITY=<提权前的实际任务调用身份>`。CLI 只负责把该身份
透传给同一权威部署脚本，用于给受保护的客户端注册表授予只读权限；它不是密钥，
不得写入项目配置。普通 AI 不得自行填写、猜测或扩大该身份，也不得借此给用户组、
Everyone 或无关账号授权。未使用外部提权时不设置此变量，由 `--auto-elevate`
自动保留当前调用身份。

#### 3.2.3 Apply 自动完成的工作

统一脚本会确定性完成：

1. 校验 Windows、项目根、`PROJECT_LAYOUT.yaml`、Python 和必要平台文件。
2. 依据当前设备上的规范化项目根生成 8 位 `deployment_id`。
3. 若发现旧固定服务部署或从其他工作树复制来的部署报告，只在 Windows Service `ImagePath` 的 `--project-root` 与当前项目根精确一致时自动迁移；属于协调者、其他项目、其他 worktree 或无法确认归属的遗留项一律不删除、不停止，只在部署报告中记为 `skipped_foreign_service` / `skipped_foreign_project_report` 后继续。只有当前项目派生出的动态服务名 `AIStyleCW_<deployment_id>` 已被其他项目占用时才硬性拒绝，防止服务名碰撞和越权覆盖。
4. 派生本项目独立身份与服务名：
   - `ACP_TR_<deployment_id>`：TaskRunner，只读章节目录；
   - `ACP_CW_<deployment_id>`：ChapterWriter，只供 Broker 使用；
   - `AIStyleCW_<deployment_id>`：本项目 Windows 服务。
5. 派生并占用本项目 loopback 端口；冲突时在受控范围内自动选择下一端口。
6. 在当前设备使用加密安全随机数生成 Broker 签名密钥、IPC token 和两个本地账号密码；不得要求 AI 编造秘密。
7. 创建/更新本项目两个低权限本地身份并授予最小权限。
8. 安装以 ChapterWriter 身份运行、开机自动启动、失败自动重启的 Windows 服务。
9. 将 Broker key 仅注入 Windows 服务环境。
10. 将客户端 token 写入 ACL 保护的：
   `HKLM\SOFTWARE\AI-Creative-Platform\Brokers\<deployment_id>`。
11. 对 `chapters/drafts/`、`chapters/approved/` 应用并复读 NTFS ACL。
12. 以真实 TaskRunner 身份执行“创建文件必须失败”和“删除文件必须失败”探测。
13. 启动服务，验证 loopback Broker、ACL、身份、注册表客户端配置和项目绑定。
14. 原子写入部署报告；任一环节失败即返回非零并保持 strict-v2 fail-closed。

签名密钥、IPC token、账号密码不得写入项目、Git、Task Packet、聊天、日志或部署报告。

#### 3.2.4 跨设备前提和边界

每台设备必须满足：

- Windows 10/11 或 Windows Server；
- 项目位于本机 NTFS 卷，不支持把受控章节目录放在 FAT/exFAT、网络共享、NAS 或不提供 Windows ACL 的文件系统；
- 当前平台仓库包含统一脚本并处于同一受支持版本；
- Python 可由 `platform.bat` 启动；
- 用户可以批准一次管理员/UAC 操作；
- Windows 本地账户、服务控制管理器、注册表和 loopback 未被组织策略禁止。

跨设备自动化的含义是“同一命令在每台合规设备上独立生成本机身份、密钥和证据”，不是把设备 A 的安全状态复制到设备 B。非 Windows 设备当前必须返回 `REJECTED`；在平台正式实现并批准新的隔离后端前，AI 不得自行改用 Docker、systemd、chmod、sudo 或云服务。

#### 3.2.5 部署证据与通过标准

必须读取并核验：

```text
PROJECT_ROOT/runtime/learning/broker-deployment.json
PROJECT_ROOT/runtime/learning/broker-verification.json
PROJECT_ROOT/runtime/learning/broker-status.json
```

失败的 Verify 只更新 `broker-verification.json`，不得覆盖上一次有效部署报告；这样既保留回滚/迁移证据，也不会把失败伪装成已部署。

只有同时满足以下条件才是 `DEPLOYED_VERIFIED`：

- 报告的 `project_root` 是当前项目；
- `deployment_id`、服务名、端口和两个账号均存在；
- Windows 服务状态是 `Running`；
- Broker status probe 可达且绑定当前项目；
- 客户端注册表项存在、token 非空且只有受准身份可读；
- drafts/approved ACL 复读通过；
- TaskRunner 真实身份直写、直删均被拒绝；
- 报告没有保存任何秘密。

旧报告、另一设备报告、仅 `broker status` 成功、仅服务存在或仅 ACL 成功，都不足以解除门禁。

#### 3.2.6 验证失败与统一回滚

验证失败时，先保存错误并保持项目阻塞；不得切换部署方式。需要撤销本项目部署时，只能执行：

```powershell
.\platform.bat broker deploy `
  --mode Rollback `
  --project-root "<PROJECT_ROOT>" `
  --auto-elevate
```

确认本项目派生身份不再使用、并且用户明确要求删除身份时，才可追加：

```powershell
--remove-identities
```

回滚只允许删除部署报告中记录的当前项目服务、ACL 授权、注册表客户端配置和可选派生身份；不得删除其他项目服务、账号或目录。回滚后状态必须是 `ROLLED_BACK/BLOCKED_NOT_DEPLOYED`，禁止继续写作或发布。

### 3.3 会话启动

用户的对话请求先派发任务（见第 5 节），再启动会话，使 Session 能绑定到真实任务：

```powershell
.\platform.bat session bootstrap --project "<PROJECT_ID>" --intent "<任务意图>" --target "<目标章节或产物>" --role "<当前角色>" --workspace "D:\AI-Workspace"
.\platform.bat session verify --project "<PROJECT_ID>" --workspace "D:\AI-Workspace"
```

必须读取：

```text
PROJECT_ROOT/runtime/sessions/<SESSION_ID>/SESSION_MANIFEST.yaml
PROJECT_ROOT/runtime/sessions/<SESSION_ID>/SESSION_BRIEF.md
```

只有 `READY=true`，且以下门禁都为真，才能执行：

- `bootstrap_validated`
- `task_inputs_ready`
- `context_version_valid`
- `policy_version_valid`

会话或输入过期时重新 bootstrap；不得沿用旧 Session、旧 NKB hash、旧大纲 hash 或旧 guidance。

### 3.4 暂停、移交或完成时必须关闭会话

每次工作结束不能只在聊天中说明“下次继续”，必须把阶段、产物、问题和唯一下一步写入会话关闭记录：

```powershell
.\platform.bat session close `
  --project "<PROJECT_ID>" `
  --session "<SESSION_ID>" `
  --workspace "D:\AI-Workspace" `
  --stage "<当前已完成阶段>" `
  --next "<唯一合法下一步>" `
  --artifacts "<本次产物路径1>" "<本次产物路径2>" `
  --issues "<未解决问题或 none>"
```

新的 AI 接手时必须先读取上次 Session 的关闭信息，但仍要重新执行 bootstrap/verify；旧 Session 的结论不能替代当前文件 hash、任务状态和权限状态复验。

---

## 4. 新项目创建与目录治理

### 4.1 创建方式

禁止手工复制旧项目、随意新建目录或把附件目录当项目。只能事务式创建：

```powershell
.\platform.bat project create `
  --id "<PROJECT_ID>" `
  --title "<书名>" `
  --genre "<题材>" `
  --language "zh-CN" `
  --project-dir "<规范目录名>" `
  --workspace "D:\AI-Workspace"
```

创建后必须：

1. 在 `WORKSPACE_ROOT/workspace.yaml` 和平台项目注册表中确认项目已登记。
2. 读取 `PROJECT_ROOT/AGENTS.md`、`project.yaml`、`PROJECT_LAYOUT.yaml`。
3. 执行 `layout validate`。
4. 为当前“设备 × 项目”执行 `broker deploy Plan → Apply → Verify`。
5. 从 P0 生命周期开始，不得直接创建 NKB 或正文。

### 4.2 顶层目录用途

| 路径 | 唯一用途 |
|---|---|
| `PROJECT_ROOT/project.yaml` | 项目身份、类型、状态与路径配置 |
| `PROJECT_ROOT/PROJECT_LAYOUT.yaml` | strict-v2 目录、存储和强制链标记 |
| `PROJECT_ROOT/lifecycle/` | P0—P6 状态、报告、审批证据 |
| `PROJECT_ROOT/sources/` | 原始参考、研究、设计源、正式大纲 |
| `PROJECT_ROOT/NKB/` | canonical 项目事实 |
| `PROJECT_ROOT/chapters/drafts/` | 受控章节草稿 |
| `PROJECT_ROOT/chapters/approved/` | Publish Service 写入的正式章节 |
| `PROJECT_ROOT/learning/candidates/` | 尚未批准的学习候选 |
| `PROJECT_ROOT/memory/project/` | 当前项目已激活的学习与风格资产 |
| `PROJECT_ROOT/runtime/` | 会话、任务包、上下文、临时 guidance 与面板 |
| `PROJECT_ROOT/tasks/` | 任务状态机记录 |
| `PROJECT_ROOT/analysis/` | 审查、设计、风格、学习和回归证据 |
| `PROJECT_ROOT/operations/` | NKB、设计、发布等操作清单与授权证据 |
| `PROJECT_ROOT/audit/` | 审计记录 |
| `PROJECT_ROOT/versions/snapshots/` | 可追踪快照 |
| `PROJECT_ROOT/canonical_manifest.yaml` | 正式章节真相源索引 |

禁止：

- 在项目根散落临时脚本、诊断文件、草稿或附件。
- 在平台目录保存某个项目的正文/大纲/NKB。
- 为方便而新建非契约目录。
- 直接编辑 `chapters/approved/`、`canonical_manifest.yaml` 或绕过 Operation Manifest 修改 NKB。

确需新增一种公共能力时，应先判断：

- 项目专属内容：放项目契约目录。
- 所有项目可复用的确定性操作：实现为平台 `scripts/` + CLI 子命令 + 合约/schema + 测试，不复制到每个项目。
- 题材通用但非全局硬规则：进入经过治理的模板/题材记忆，不能污染跨项目事实。

---

## 5. 聊天请求必须先进入任务系统

### 5.1 对话框不会天然破坏任务系统，但“直接照做”会

用户可以直接说：

- “写第 1—10 章”
- “审查最近五章并修改到合格”
- “生成全书 1000 章详纲”
- “学习这些参考小说并用于写作”

这些话只能作为任务 intake。AI 必须先执行：

```powershell
.\platform.bat task --project-root "<PROJECT_ROOT>" dispatch `
  --request "<用户原始请求，不改写关键范围>" `
  --project "<PROJECT_ID>" `
  --agent "<当前AI标识>" `
  --model "<当前模型标识>"
```

平台会把范围、默认假设和任务链写入：

```text
PROJECT_ROOT/tasks/goals/
PROJECT_ROOT/tasks/<state>/
PROJECT_ROOT/runtime/task-packets/<TASK_ID>/
```

批量写作使用稳定发布屏障串行推进：第 `N+1` 章的 `plan_write`
依赖请求级固定任务 `REQ-...-PUBLISH-CHNNN`，而不是依赖风格链内部动态
生成的任务名。只有上一章 `chapter_publish` 真正 completed，下一章才会从
backlog 进入 ready。任何 AI 都不得自行删除依赖、提前 promote 或并行写后章。

对话本身不授予以下权限：

- 写正文；
- 修改 NKB；
- 标记审查通过；
- 把草稿移入 approved；
- 跳过缺失的详纲、reference learning、reader gate 或 Broker。

### 5.2 每个任务必须读取完整 Task Packet

任务执行前：

```powershell
.\platform.bat task --project-root "<PROJECT_ROOT>" next --agent "<当前AI标识>" --role "<角色>"
.\platform.bat task --project-root "<PROJECT_ROOT>" packet --task "<TASK_ID>"
```

必须逐个读取：

| 文件 | 含义 |
|---|---|
| `runtime/task-packets/<TASK_ID>/task.yaml` | 任务类型、目标、依赖、状态 |
| `runtime/task-packets/<TASK_ID>/input-index.yaml` | 必需输入及 resolved/pending |
| `runtime/task-packets/<TASK_ID>/context.md` | 本任务最小上下文 |
| `runtime/task-packets/<TASK_ID>/constraints.md` | 权限、红线和约束 |
| `runtime/task-packets/<TASK_ID>/output-contract.yaml` | 允许输出、格式与验收 |
| `runtime/task-packets/<TASK_ID>/execution-manifest.yaml` | 单 Agent、角色、模型、预算和执行元数据 |

任一 required input 为 pending：阻塞并补输入；不得自行假设。

标准状态操作：

```powershell
.\platform.bat task --project-root "<PROJECT_ROOT>" claim --task "<TASK_ID>" --agent "<当前AI标识>"
.\platform.bat task --project-root "<PROJECT_ROOT>" start --task "<TASK_ID>" --agent "<当前AI标识>"
# 只在任务允许的路径产出
.\platform.bat task --project-root "<PROJECT_ROOT>" submit --task "<TASK_ID>" --artifact "<产物路径>"
```

审查、完成与路由只按模板使用：

```powershell
.\platform.bat task --project-root "<PROJECT_ROOT>" review --task "<TASK_ID>" --decision pass --findings "[]"
.\platform.bat task --project-root "<PROJECT_ROOT>" event --task "<TASK_ID>" --event "<模板声明事件>"
.\platform.bat task --project-root "<PROJECT_ROOT>" complete --task "<TASK_ID>"
```

不能把 `complete` 当成跳过审查的按钮；缺少模板要求的输出、hash 绑定或事件时不得完成。

---

## 6. 从灵感到允许开写：P0—P6 强制链

### 6.1 生命周期总链

```text
P0 Idea
  → P1 Initiation
  → P2 Definition
  → P3 Design
  → P4 Knowledge / NKB Genesis
  → P5 Readiness
  → P6 Runtime Writing
```

对应状态：

```text
idea → evaluating → initiated → defining → designing
→ preparing_knowledge → readiness_review
→ ready_for_writing → writing → completed → archived
```

任何状态不得倒推为“默认已完成”。已有文件不等于已批准；必须存在本阶段要求的报告、审批和 task event。

### 6.2 各阶段产物与下一项强制动作

| 阶段 | 必须使用/生成的文件 | 通过条件 | 通过后唯一强制动作 |
|---|---|---|---|
| P0 创意 | `lifecycle/idea/IDEA.yaml` | 灵感、核心吸引力、边界和未知项已记录 | 发起 P1 立项评估 |
| P1 立项 | `lifecycle/initiation/PROJECT_CHARTER.yaml`、`INITIATION_GATE.yaml` | 目标、范围、风险、责任、完成定义通过 | 进入 P2 项目定义 |
| P2 定义 | `lifecycle/definition/PROJECT_BRIEF.yaml`、`AUDIENCE.yaml`、`POSITIONING.yaml`、`CREATIVE_STRATEGY.yaml`、`CONTENT_BOUNDARIES.yaml` | 受众、定位、内容边界、商业/阅读目标明确 | 进入 P3 设计 |
| P3 设计 | `sources/design/_intake/**`、`_candidates/**`、正式 `sources/design/**`、`analysis/design/**`、`lifecycle/design/**` | 六维设计审查通过，须用户裁决项已处理，设计审批通过 | 执行 P4 NKB Genesis |
| P4 知识 | `NKB/*.yaml`、`NKB/manifest.yaml`、`operations/**`、Genesis 校验报告 | 14 个 NKB 组件 canonical 校验通过，生成 `NKB-GENESIS-001` | 执行 P5 Readiness |
| P5 准备度 | `lifecycle/readiness/READINESS_REPORT.yaml`、`READINESS_APPROVAL.yaml` | 六维开写验收、第一卷可写性、全书详纲覆盖等通过 | 状态置 `ready_for_writing`，生成 chapter-plan 任务 |
| P6 运行 | Task Packet、章节计划、策略、草稿、审查、修复、反馈、NKB 同步、发布 | 每章完整状态机通过 | 发布后刷新未来详纲，再处理下一章 |

### 6.3 用户只提供方向时，AI 如何补全

用户只需要提供大方向灵感、关键设定和总章节数。AI 可以自主补全低风险设计，但必须走候选—审查—审批链：

```powershell
.\platform.bat design prepare --project-root "<PROJECT_ROOT>" --brief "<用户灵感>" --total-chapters <N> --mode balanced
.\platform.bat design gap --project-root "<PROJECT_ROOT>"
.\platform.bat design candidates --project-root "<PROJECT_ROOT>"
.\platform.bat outline prepare --project-root "<PROJECT_ROOT>" --total-chapters <N>
.\platform.bat design review-prepare --project-root "<PROJECT_ROOT>"
# AI 按六个审查视角填写设计审查报告
.\platform.bat design review-check --project-root "<PROJECT_ROOT>" --report "<DESIGN_REVIEW路径>"
.\platform.bat design approval --project-root "<PROJECT_ROOT>"
# 对高影响项取得用户决定，并写 decisions 文件
.\platform.bat design decide --project-root "<PROJECT_ROOT>" --decisions "<DECISIONS路径>"
.\platform.bat design promote --project-root "<PROJECT_ROOT>" --approval-file "<APPROVAL路径>"
.\platform.bat design gate --project-root "<PROJECT_ROOT>"
```

设计任务强制状态链：

```text
project_design
  --on_submit--> design_review
  --on_pass----> design_approval
  --on_fail----> project_design

design_approval
  --on_pass----> nkb_genesis
  --on_fail----> project_design
```

以下内容必须询问用户或进入 human gate，不得假定：

- 会改变作品核心卖点、主角身份/终局、题材边界的高影响决策；
- 伦理、合规、敏感内容边界；
- 参考作品授权范围；
- 明显相互冲突的用户设定；
- 会造成大规模返工且不存在安全默认值的选择。

---

## 7. 参考小说资料与自主学习链

### 7.1 原始文件和学习产物的固定路径

| 内容 | 路径 | 是否可直接用于正文 |
|---|---|---|
| 用户提供的原始小说 | `sources/references/inbox/` | 否，只能由学习任务读取 |
| 来源授权/指纹/索引 | `sources/references/manifests/` | 否，是来源治理证据 |
| 单书风格画像 | `learning/candidates/style-profiles/` | 否，候选 |
| 多书抽象原型 | `learning/candidates/style-archetypes/` | 否，候选 |
| 学习摘要/写作与审查候选 | `learning/candidates/` | 否，待审 |
| 当前项目已批准的参考学习 | `memory/project/reference-learning/` | 是，限定为项目实验规则 |
| 写作/审查运行时参考指导 | `runtime/learning/reference-guidance.yaml` | 是，任务上下文输入 |
| L0—L4 风格卡 | `memory/project/style-library/` | 是，经治理的风格层 |
| 当前章节合成风格指导 | `runtime/learning/style-guidance.yaml` 或 `runtime/learning/style-guidance/<TASK_ID>.yaml` | 是，只对绑定任务有效 |

原始小说不得进入 Git；学习产物不得保存原文、长句、可还原片段或高相似 n-gram。

### 7.2 强制学习步骤

1. 用户明确授权参考文件用于分析。
2. 把文件放入 `sources/references/inbox/`，为每个来源生成 manifest、hash、授权范围和撤回信息。
3. 派发 `reference_learn` 任务。
4. 运行确定性批处理，生成画像、原型和学习摘要。
5. AI 进行语义层提炼：只提炼结构、节奏、视角、对话、场景、悬念、信息释放、情绪、开头/结尾等方法。
6. `candidate_review` 独立审查原创隔离、可执行性、适用边界和反例。
7. 只有批准候选才能 `promote-project --approved`。
8. 生成/更新 `reference-guidance.yaml`，随后由 chapter plan、context、style guidance 和 review 使用。

确定性批处理：

```powershell
.\platform.bat learn batch `
  --input-dir "<PROJECT_ROOT>\sources\references\inbox" `
  --genre "<题材>" `
  --output-dir "<PROJECT_ROOT>\learning\candidates" `
  --license-type "<授权类型>" `
  --fingerprint-key-id "<指纹密钥标识>"
```

审核后仅在当前项目启用：

```powershell
.\platform.bat learn promote-project `
  --summary "<PROJECT_ROOT>\learning\candidates\<learning-summary>.yaml" `
  --project-root "<PROJECT_ROOT>" `
  --approved
```

来源数量门槛：

- 1—2 个有效来源：只能探索，不能形成稳定原型；
- 3—4 个有效来源：可生成带警告候选；
- 推荐至少 5 个彼此独立、授权明确的优质来源；
- 来源数量绝不能替代候选审查和项目批准。

### 7.3 参考学习如何真正进入写作和审查

每章写作前必须在 Task Packet/Context 中解析：

```text
runtime/learning/reference-guidance.yaml
runtime/learning/writing-guidance.yaml
runtime/learning/review-regression.yaml
memory/project/style-library/**
runtime/learning/style-guidance*.yaml
runtime/writing-strategies/STRATEGY-CH-NNN.yaml
```

写作者必须在 `writing_strategy_evidence` 中说明：

- 本章采用了哪些已批准参考技法；
- 为什么与本章情节、环境、人物、POV 和情绪目标相匹配；
- 如何进行了原创化改造；
- 哪些技法因不适用被主动排除。

审查者必须复核：

- 是“方法迁移”而非“措辞模仿”；
- 技法没有覆盖大纲事实和人物动机；
- 没有为了套风格破坏因果、节奏或可读性；
- 同一种开头、句式、桥段和收尾没有机械重复。

发现参考内容与 canonical NKB 冲突时，NKB 胜出；参考规则被拒绝或降级，不修改 NKB 来迁就参考作品。

已有项目若在 L0—L4 卡片体系上线前把已批准规则保存在
`memory/project/style-library/style-cards.json`，guidance 生成器会只读桥接其中
`status=ACTIVE/APPROVED` 的抽象规则到 L4。`EXTRACTED`、`review_pending`、
`REJECTED`、`REVOKED` 等状态永不进入正文。桥接不是再次晋升，也不改变原始
生命周期文件；新规则仍必须落入标准 `*.card.yaml` 治理链。

---

## 8. NKB Genesis：高质量生成、文件结构与更新边界

### 8.1 NKB 不能由一段提示词直接生成

合法来源链：

```text
用户灵感
→ inspiration-brief
→ autonomy-policy
→ design-gap-matrix
→ AI design candidates
→ 六维设计审查
→ 用户/策略审批
→ approved design sources
→ NKB Genesis staging
→ canonical validation
→ NKB-GENESIS-001
```

严禁：

- 把聊天内容原样写入 NKB；
- 从参考小说抽取人物、势力、设定或剧情写入本项目 NKB；
- 先生成正文、再倒填 NKB 合理化；
- 让 writer 直接改 NKB；
- 仅因“AI 认为合理”就把推断升为正史。

### 8.2 canonical NKB 文件

Genesis 必须生成并校验：

```text
NKB/manifest.yaml
NKB/Canon.yaml
NKB/Characters.yaml
NKB/WorldState.yaml
NKB/StoryState.yaml
NKB/Timeline.yaml
NKB/Events.yaml
NKB/Locations.yaml
NKB/Organizations.yaml
NKB/Assets.yaml
NKB/Foreshadow.yaml
NKB/ReaderState.yaml
NKB/Terminology.yaml
NKB/Graph.yaml
NKB/Derived.yaml
```

用途概览：

| 组件 | 用途 |
|---|---|
| Canon | 不可违背的项目正史和硬约束 |
| Characters | 身份、目标、能力、认知、关系、语言特征 |
| WorldState | 世界规则、时代、制度、资源与边界 |
| StoryState | 当前剧情状态、未完成问题、进行中目标 |
| Timeline / Events | 时间与事件因果、先后关系 |
| Locations / Organizations / Assets | 地点、组织、物品/能力等实体 |
| Foreshadow | 伏笔的植入、状态、兑现窗口 |
| ReaderState | 读者已知/未知、期待、谜团、承诺与兑现 |
| Terminology | 唯一标准名，防止同义漂移 |
| Graph | 实体关系与依赖 |
| Derived | 可重建的派生信息，不得反向覆盖 canonical 事实 |
| manifest | 版本、hash、快照、组件索引与状态 |

执行：

```powershell
.\platform.bat genesis --project-root "<PROJECT_ROOT>"
.\platform.bat ready --project-root "<PROJECT_ROOT>"
.\platform.bat ready --project-root "<PROJECT_ROOT>" --approve
```

任务强制链：

```text
nkb_genesis --on_submit--> readiness_review
readiness_review --on_pass--> chapter_plan
readiness_review --on_fail--> project_design
```

`--approve` 只在 READINESS_REPORT 已真实通过时使用，不能用来“强行变 ready”。

### 8.3 运行期事实回写

正文中新产生的事实先写：

```text
tasks/running/<chapter-write-task>/outputs/candidate_facts.*
```

随后：

```text
candidate_facts + approved_event
→ nkb_update
→ operation_manifest + nkb_snapshot_after
→ nkb_sync canonical validation
→ nkb_sync_proof
→ chapter_publish
```

若 `nkb_sync` 失败，必须回到 `nkb_update`；没有同步证明不得发布章节。
该链按章节原子执行，不得把多章 `candidate_facts` 延后合并、卷末一次性同步，
也不得为了节省模型调用而跳过。无新增事实也必须生成空增量证据并完成 canonical
validation，确保“本章未改变 NKB”同样可审计。

---

## 9. 全书大纲：必须覆盖每一章的详细信息

### 9.1 五级大纲固定路径

```text
sources/outline/_intake/planning-policy.yaml
sources/outline/series/series-outline.yaml
sources/outline/volumes/VOL-NNN.yaml
sources/outline/arcs/ARC-NNN.yaml
sources/outline/maps/chapter-map.yaml
sources/outline/chapters/PLAN-NNN.yaml
runtime/outline/generation-plan.yaml
analysis/outline/OUTLINE_VALIDATION.yaml
lifecycle/outline/**
operations/outline/**
```

层级含义：

1. 全书层：核心命题、终局、总升级路线、总体承诺与兑现。
2. 分卷层：卷目标、卷冲突、卷高潮、卷末状态变化。
3. 情节弧层：阶段目标、阻力、转折、失败代价、弧结算。
4. 章节地图：每章在全书/分卷/情节弧中的位置与依赖。
5. 逐章详纲：全书每一章一份 `PLAN-NNN.yaml`，不是只做近期窗口。

### 9.2 每章详纲至少要包含

- 章节 ID、卷/弧归属、时间与地点；
- POV、出场人物及其进入本章时的状态；
- 本章目标、读者预期和承接上一章的入口；
- 场景序列，每场的目标、阻力、行动、变化和退出点；
- 核心因果链、关键选择、失败代价和不可逆变化；
- 冲突类型、强度、升级方式；
- 信息释放、读者已知/未知、误导和揭示；
- 情绪曲线、关系变化、人物认知变化；
- 世界规则/能力/资源使用及 NKB 引用；
- 伏笔植入、推进、回收与禁提前泄露项；
- 本章兑现、爽点/痛点/悬念和读者回报；
- 开头功能与进入方式；
- 结尾功能、状态差和下一章牵引；
- 适配的场景/叙事技法候选及禁用套路；
- 目标字数 `word_budget`；
- 本章完成后要产生的 candidate facts 和 handoff；
- 可审查的验收标准。

### 9.3 生成与校验

```powershell
.\platform.bat outline prepare --project-root "<PROJECT_ROOT>" --total-chapters <N>
```

AI 按 `runtime/outline/generation-plan.yaml` 分批补齐内容，但即使批量生成，最终必须覆盖全书所有章节。

```powershell
.\platform.bat outline validate --project-root "<PROJECT_ROOT>"
.\platform.bat outline chapter-check --project-root "<PROJECT_ROOT>" --chapter "CH-NNN"
```

以下任一情况不得开写：

- `chapter-map.yaml` 缺章、重复、编号断裂；
- 任何一章缺 `PLAN-NNN.yaml`；
- 计划只有一句情节摘要，缺少场景、因果、人物、读者状态、首尾或字数预算；
- 出现大量可互换的占位章、填充章；
- 大纲未通过设计审查和审批；
- 当前章计划引用的 NKB/上章 handoff 已过期。

全书已有逐章详纲不代表永不调整。正式章节发布后，必须由 `outline_refresh` 根据已发生事实、handoff 和最新 NKB，只刷新尚未执行的未来章计划；不得悄悄改写全书核心批准目标。

---

## 10. 每章写作前：计划、上下文、参考学习与自适应手法

### 10.1 chapter-plan 是写作的直接入口

`chapter_plan` 任务必须读取：

```text
sources/outline/**
NKB/**
chapters/approved/**
上一章 handoff
lifecycle/status.yaml
```

并产出本次任务工作区中的：

```text
chapter_plan
handoff
```

只有 chapter-plan 提交成功，才能生成 `chapter_write`。

### 10.2 为当前章构建写作策略

```powershell
.\platform.bat craft build --project-root "<PROJECT_ROOT>" --chapter "CH-NNN"
```

输出：

```text
runtime/writing-strategies/STRATEGY-CH-NNN.yaml
```

策略必须由本章计划动态选择，而不是固定模板。至少根据以下因素适配：

- 情节任务：推进、揭示、冲突、转折、过渡、回收；
- 环境：空间约束、天气、光线、噪声、群体、危险和资源；
- 人物：POV、能力、认知权限、关系、压力和语言特征；
- 节奏：快慢、信息密度、场景长度、留白；
- 情绪：进入状态、触发事件、转折与退出状态；
- 读者状态：已知/未知、期待、疲劳、困惑风险和回报时机；
- 参考学习：适用技法、原创化方式和禁用模仿；
- 跨章变化：避免连续使用同一开头模式、结尾模式、句式和节奏。

### 10.3 构建当前章风格指导

```powershell
.\platform.bat style guidance-build `
  --project-root "<PROJECT_ROOT>" `
  --chapter "CH-NNN" `
  --cycle "<REVISION_CYCLE_ID>" `
  --task "<TASK_ID>" `
  --scene "<场景类型>" `
  --character "<角色ID>" `
  --writing-strategy "<STRATEGY-CH-NNN.yaml>"
```

组合来源：

```text
L0 项目风格：memory/project/style-library/project-style.card.yaml
L1 题材风格：memory/project/style-library/genre/<genre>.card.yaml
L2 场景风格：memory/project/style-library/scene/<scene>.card.yaml
L3 角色语言：NKB/Characters.yaml + memory/project/style-library/character/<id>.card.yaml
L4 作者风格：memory/project/style-library/author.card.yaml
审查反补：runtime/learning/writing-guidance.yaml
回归检查：runtime/learning/review-regression.yaml
参考实验规则：runtime/learning/reference-guidance.yaml（经 Context 注入）
```

Task Packet 生成时会自动从当前 `PLAN-NNN.yaml` 的全部 `scenes[].type` 和
`scenes[].participants` 派生 scene/character 作用域，再与任务显式作用域合并。
禁止把所有章节固定成 `scene=daily` 或省略出场人物；否则相应 L2 场景卡和 L3
人物声线卡不会被选中。

### 10.4 开头与结尾的硬要求

开头必须由本章功能决定，例如：动作中切入、感官异常、对话冲突、后果承接、目标受阻、空间发现、时间压力。不得每章都用天气、醒来、总结、旁白解释或同一句式开场。

结尾必须由本章状态变化决定，例如：新事实改变目标、选择产生代价、关系翻转、承诺兑现、危机升级、关键行动启动、信息权限改变。不得每章机械“留下悬念”、强行断句或统一感叹。

平台证据门禁要求：

- 开头符合 chapter plan 的 opening function；
- 结尾符合 ending function；
- 环境对行动和结果有因果作用，而非装饰；
- 技法与情节、场景、人物适配；
- 与近期章节的开头/结尾相似度不得超过阈值 `0.75`；
- 同一 opening/ending mode 不得连续出现 3 次；
- 不存在模板化套写、机械分段和无效填充。

---

### 10.5 受管自动成稿入口

平台现在提供统一 Author Executor。它只接受合法 `chapter_write` Task，读取完整
Task Packet，通过模型路由选择模型，再调用当前设备批准的模型适配器。适配器必须
以 stdin JSON / stdout JSON 返回以下五项：

```text
chapter_draft
self_check
writing_strategy_evidence
candidate_facts
handoff
```

设备管理员必须把批准的适配器 argv 以 JSON 数组配置到
`AI_CREATIVE_AUTHOR_COMMAND_JSON`。命令使用 `shell=false`，不得在注册表、
项目、任务包或指南中写 API Key、token 或 shell 拼接命令。先验证：

```text
registry/author-executors.yaml
core/contracts/chapter-author.schema.yaml
```

```powershell
.\platform.bat author validate --model "<MODEL_ID>"
```

检查将发送给模型的受管请求但不生成正文：

```powershell
.\platform.bat author prepare `
  --project-root "<PROJECT_ROOT>" `
  --task "<CHAPTER_WRITE_TASK_ID>"
```

正式执行：

```powershell
.\platform.bat author run `
  --project-root "<PROJECT_ROOT>" `
  --task "<CHAPTER_WRITE_TASK_ID>" `
  --agent "<当前AI标识>"
```

`author run` 确定性执行：

```text
Ready Check
→ claim/start（仅在需要时）
→ 生成/复读 Task Packet
→ model-router
→ 设备级批准适配器
→ 五项响应合同校验
→ 字数硬门禁
→ Broker 写 chapters/drafts
→ task submit
→ 自动创建 chapter_review
```

如果当前 AI 运行在对话框中、无法作为本机 stdio 命令被适配器调用，不得因此
绕开任务系统。改走同一 Author Executor 的交互式交换：

```powershell
.\platform.bat author begin `
  --project-root "<PROJECT_ROOT>" `
  --task "<CHAPTER_WRITE_TASK_ID>" `
  --agent "<当前AI标识>"

# begin 会认领/启动任务，并返回任务工作区内的 request_file、response_file。
# 当前 AI 必须完整读取 request_file，按 chapter-author.schema.yaml 把五项结果
# 写成一个 JSON 对象到 response_file，然后执行：

.\platform.bat author ingest `
  --project-root "<PROJECT_ROOT>" `
  --task "<CHAPTER_WRITE_TASK_ID>" `
  --response-file "<begin 返回的 response_file>" `
  --agent "<同一AI标识>"
```

`begin/ingest` 与 `run` 经过完全相同的响应合同、字数、Broker 和 Task submit
门禁。它不是“手工写正文绕过平台”，而是让当前对话 AI 成为受管语义执行端；
响应只能写入已认领任务的 workspace，不能直接写 drafts/approved。

适配器模式未配置、交互响应未 ingest、返回非 JSON、缺任一语义证据、字数不足、
Task/Session/Broker 无效时一律阻塞。禁止退回临时脚本、直接聊天写文件或把 `model-router` 的
“支持 chapter_write”误认为已经调用模型。不同 AI 产品只允许更换设备级适配器，
不得各自重写章节流程。

同一 Task Packet 重试时，执行器复用已通过响应合同的缓存，避免重复计费和正文
漂移。只有确认模型输出本身有误时才可加 `--regenerate`；输入文件变化会形成新的
请求 hash，并自动重新生成。

---

## 11. 章节草稿：从一开始就使用 TXT

### 11.1 唯一合规的 TXT 路径

用户要求最终正文是 TXT，因此新项目必须从草稿阶段就使用：

```text
chapters/drafts/CH-NNN.txt
```

最终由 Publish Service 产生：

```text
chapters/approved/CH-NNN.txt
```

平台当前没有独立的、可替代发布门禁的“MD 转 TXT 导出器”。因此禁止：

- 先写 `CH-NNN.md`，最后手工改名为 `.txt`；
- 手工复制到 `chapters/approved/`；
- 新建旧版根目录 `txt/`；
- 用文件管理器、普通脚本或 shell 直接生成正式 TXT；
- 发布后再制作一个脱离 `canonical_manifest.yaml` 的“最终版”。

如任务包错误地把目标声明为 `.md`，必须在开始写作前修正任务目标/输出合同并重新生成 Task Packet，不能在末尾补救。

### 11.2 受控写

`chapter_write` 的正文先落任务工作区，再通过受控写/Broker 写入 drafts。写作者只可写：

```text
tasks/running/<TASK_ID>/outputs/**
chapters/drafts/**
```

不得写：

```text
NKB/**
chapters/approved/**
core/**
registry/**
templates/**
```

写作任务同时必须产出：

```text
chapter_draft
self_check
writing_strategy_evidence
candidate_facts
handoff
```

优先使用第 10.5 节的 `platform author run` 一次完成受管成稿、五项输出、
Broker 落盘和 submit。若当前 AI 产品不能作为命令适配器调用，必须使用
`platform author begin → ingest`；不能把 `chapter_write.py --content-file`
伪装成自动生成命令。`chapter_write.py` 是底层受控落盘原语，不负责创作。

写完正文后生成证据模板并填写：

```powershell
.\platform.bat craft evidence-prepare `
  --project-root "<PROJECT_ROOT>" `
  --chapter "CH-NNN" `
  --draft "<PROJECT_ROOT>\chapters\drafts\CH-NNN.txt"

.\platform.bat craft evidence-check `
  --project-root "<PROJECT_ROOT>" `
  --chapter "CH-NNN" `
  --evidence "<PROJECT_ROOT>\analysis\writing-strategy\EVIDENCE-CH-NNN.yaml" `
  --draft "<PROJECT_ROOT>\chapters\drafts\CH-NNN.txt" `
  --plan "<PROJECT_ROOT>\sources\outline\chapters\PLAN-NNN.yaml"
```

证据检查不通过，`chapter_write` 不得 submit。

---

## 12. 审查必须覆盖的观察点

章节审查不是只查错字。至少覆盖以下层面：

### 12.1 事实、故事与技法

1. NKB 一致性：人物、时间、地点、能力、物品、组织、术语。
2. 连续性：承接上章、状态变化、未完成动作、handoff。
3. 因果与逻辑：原因、条件、行动、结果、代价。
4. 人物驱动：目标、认知、动机、关系、选择是否成立。
5. 冲突：是否产生真实选择、升级、代价和不可逆变化。
6. 节奏：是否有无效段落、重复说明、场景失衡或兑现过迟。
7. 叙事：POV、时序、信息权限、转场和聚焦。
8. 对话：角色可辨、潜台词、功能、信息自然度。
9. 情绪：有触发、有过程、有外显、有退出状态。
10. 世界构建：规则、限制、代价与剧情行动结合。
11. 大纲履约：本章目标、场景、转折、开头、结尾、字数预算。
12. 写作手法适配：技法是否适合情节/环境/人物，而非套模板。
13. 原创隔离：是否出现参考作品可识别表达、结构复刻或角色映射。
14. 去 AI 味：抽象总结、机械排比、重复句式、解释性旁白、伪深刻。
15. 商业/连载：承诺与兑现、章内回报、追读动力、付费边界。

对应检查文件位于：

```text
core/review/checks/*.md
core/review/checks/reader/*.md
core/contracts/review.contract.yaml
core/contracts/review-report.schema.yaml
```

### 12.2 读者的多观察点

AI 读者面板至少从以下角度建立证据，不得只给总体“好看/不好看”：

- 第一屏/开头是否快速建立关注点；
- 是否知道“谁要什么、什么在阻碍他”；
- 是否沉浸，是否因解释、跳跃、术语或视角漂移出戏；
- 是否困惑，困惑是有意悬念还是信息缺失；
- 情绪是否被触发，变化是否可信；
- 节奏是否疲劳、拖沓、过密或回报不足；
- 人物是否值得关心、行为是否可信；
- 对话是否自然并有角色差异；
- 期待是否建立、推进并兑现；
- 爽点/痛点/悬念是否有铺垫和后果；
- 结尾是否自然产生继续阅读动机；
- 推荐意愿、付费意愿和可能停读点。

AI 面板：

```powershell
.\platform.bat reader-panel prepare `
  --project-root "<PROJECT_ROOT>" `
  --task "<TASK_ID>" `
  --chapter-ref "CH-NNN" `
  --chapter-path "<PROJECT_ROOT>\chapters\drafts\CH-NNN.txt"

# AI 填写生成的面板报告后
.\platform.bat reader-panel validate --report "<reader-panel-report.yaml>"
```

输出位于：

```text
runtime/reader-panels/PANEL-<TASK_ID>/report.yaml
analysis/reader/**
```

AI 模拟读者只能作为预测证据，绝不能标成“真人反馈”。

### 12.3 真人读者验证

真人反馈在以下里程碑必须进入 `human_gate`：

- 试读/首批章节；
- 分卷结束；
- 付费边界；
- 重大修订后。

准备与摄取：

```powershell
.\platform.bat reader-panel prepare-human --project-root "<PROJECT_ROOT>" --task "<HUMAN_GATE_TASK_ID>"
.\platform.bat reader-panel ingest-human --project-root "<PROJECT_ROOT>" --task "<HUMAN_GATE_TASK_ID>" --feedback "<真人反馈文件>"
```

最低要求：

- 至少 3 名独立参与者；
- 记录读者分群；
- 记录读完率、推荐意愿、付费意愿、停读点；
- 区分原始观察、解释和决策；
- 生成 AI 预测校准；
- 不得由 AI 虚构参与者或补造数据。

真人样本不足或证据冲突时进入 human gate，不得自动宣告合格。

#### 12.3.1 human gate 与 AI Reader Panel 的边界

- 每章必须有 AI Reader Panel，但它是预测证据，不是人工放行。
- `human_gate` 只在风格警告、保真冲突、质量例外、已发布内容冲击或真人读者
  里程碑等模板分支出现，不是每章固定步骤。
- 普通质量例外必须绑定当前任务及 `gate_context_sha256`，不能用聊天中的
  “全部放行”替代。
- 真人读者里程碑不得批量授权、不得跳过真实反馈报告。

AI 可以只读检查待裁决内容：

```powershell
.\platform.bat human-gate inspect `
  --project-root "<PROJECT_ROOT>" `
  --task "<HUMAN_GATE_TASK_ID>"
```

授权必须由独立的受信人工审批界面执行。该界面临时持有设备级
`AI_CREATIVE_HUMAN_APPROVAL_SECRET`，普通 Writer/Reviewer AI 进程不得获得
这个秘密。普通质量例外可把多个明确 task id 绑定在一份短期授权中：

```powershell
.\platform.bat human-gate authorize `
  --project-root "<PROJECT_ROOT>" `
  --task "<HUMAN_GATE_TASK_ID_1>" `
  --task "<HUMAN_GATE_TASK_ID_2>" `
  --decision pass `
  --authorized-by "<真实审批人>" `
  --reason "<具体理由>" `
  --expires-minutes 60
```

不允许通配符、章节范围或无上限授权；有效期只能是 1—1440 分钟。签名授权写入
`operations/grants/human/`，并逐项绑定 task id、当前上下文 hash 和决定。文件被
修改、上下文改变、到期、决定不匹配或签名无法验证时，事件路由 fail-closed。
授权合同位于 `core/contracts/human-gate-authorization.schema.yaml`。

真人读者里程碑即使有签名授权，也必须附带 `evidence_mode=verified_human_input`
的 `human_reader_report`，满足至少 3 名参与者和至少 2 个分群；此类任务一次
只能授权一个，不能和其他 gate 合并。

---

## 13. “审查—修改—反补—完全合格”的完整章节状态机

以下是 strict-v2 的强制链。AI 必须逐任务执行，不能把多步合并成“我已经审查并修改好了”。

```text
chapter_plan
  → chapter_write
  → chapter_review
      ├─ fail → chapter_fix → chapter_review（循环）
      └─ pass → protected-manifest-build
                   ├─ conflict → human_gate
                   └─ complete → ai-diagnose
                                      ├─ clean → final-regression(baseline)
                                      ├─ warning → human_gate
                                      └─ issues → style-revise
                                                     → fidelity-review
                                                         ├─ fail → style-revise（循环）
                                                         └─ pass → style-quality-review
                                                                      ├─ fail → human_gate
                                                                      └─ pass → chapter-apply-revision
                                                                                   → final-regression(post_apply)

final-regression
  ├─ pass → nkb_update
  ├─ fail_baseline → chapter_fix → chapter_review
  └─ fail_post_apply → chapter-rollback-revision
                           ├─ conflict → human_gate
                           └─ rolled_back → 停止并建立新的修复任务

nkb_update
  → nkb_sync
      ├─ fail → nkb_update
      └─ pass → chapter_publish
                   ├─ fail → 阻塞，不得手工发布
                   └─ pass → outline_refresh
                                  ├─ fail → outline_refresh（循环）
                                  └─ pass → 本章闭环完成，可进入下一章
```

关键任务的角色与输出：

| 任务 | 角色 | 关键输出 |
|---|---|---|
| `chapter_plan` | story-architect | chapter_plan、handoff |
| `chapter_write` | writer | TXT 草稿、自检、策略证据、candidate facts、handoff |
| `chapter_review` | reviewer | review_report、findings |
| `chapter_fix` | writer | 修复后的草稿、自检、handoff |
| `protected-manifest-build` | writer | 保真基线与 hash 绑定 |
| `ai-diagnose` | writer（只读诊断） | diagnosis_report |
| `style-revise` | writer | revision_candidate，不直接覆盖草稿 |
| `fidelity-review` | reviewer | fidelity_report |
| `style-quality-review` | reviewer | quality_report |
| `chapter-apply-revision` | writer/Broker | apply_result、pre_apply_backup |
| `final-regression` | reviewer | regression_result |
| `chapter-rollback-revision` | writer/Broker | rollback_result |
| `nkb_update` | knowledge-manager | nkb_change、operation_manifest、snapshot |
| `nkb_sync` | reviewer | nkb_sync_proof、validation_report |
| `chapter_publish` | publish_service | approved TXT、canonical_manifest |
| `outline_refresh` | story-architect | 刷新后的未来章节地图/详纲、报告、handoff |

同一个主 Agent 可以按任务串行切换角色，但不能在同一任务里既写又自我伪造独立审查证据。角色切换必须体现在不同 Task、Task Packet、状态和产物中。

---

## 14. 审查问题如何反补写作，形成自主学习闭环

### 14.1 每次审查发现都必须结构化

finding 至少包含：

- `category`
- `severity`
- `observation/problem`
- `evidence/location`
- `root_cause/reasoning`
- `recommended_fix`
- 是否阻断发布

审查任务 review/event 时提交 findings，平台会把重复问题沉淀为：

```text
memory/project/review-feedback/feedback-ledger.yaml
runtime/learning/writing-guidance.yaml
runtime/learning/review-regression.yaml
analysis/learning/FEEDBACK-*.yaml
```

外部或补录审查报告使用：

```powershell
.\platform.bat feedback ingest --project-root "<PROJECT_ROOT>" --report "<review-report.yaml>"
.\platform.bat feedback validate --ledger "<PROJECT_ROOT>\memory\project\review-feedback\feedback-ledger.yaml"
```

### 14.2 反补的使用方法

下一章 `chapter_plan`、`chapter_write` 和 `style guidance` 必须读取：

- `writing-guidance.yaml`：把历史根因转成写作前防错动作；
- `review-regression.yaml`：审查时必须重测的历史问题；
- `feedback-ledger.yaml`：频次、跨章复发、严重度和晋升候选。

闭环：

```text
审查 finding
→ 修复当前章
→ feedback ledger 记录根因与频次
→ writing guidance 约束下一次写作
→ review regression 在下一次审查复测
→ 跨章复发则形成候选规则
→ 独立审核后才可晋升
```

不得：

- 把一次偶发问题立即升级成全项目硬规则；
- 自动修改平台全局规则；
- 把审查意见当 NKB 事实；
- 只修当前句子，不记录根因；
- 只生成 ledger，但后续 Task Packet 不读取。

### 14.3 作者修改与风格升级

作者实际修改稿是 L4 作者风格学习的重要证据，但不能一次修改就自动晋升。应：

1. 保留修改前/后绑定与差异证据；
2. 提炼非逐字规则候选；
3. 至少跨 3 次独立反馈验证稳定性；
4. 进入 `style-rule-review`；
5. 通过后由 `style-rule-promote` 写入项目风格库；
6. 新 guidance 生效，旧章节只有在建立修订任务时才重跑，不能静默批量改写。

---

## 15. 正式 TXT 发布与落地验收

### 15.1 发布的唯一入口

只有 `chapter_publish` 任务满足全部输入和授权后，执行：

```powershell
.\platform.bat chapter --project-root "<PROJECT_ROOT>" publish --task-id "<CHAPTER_PUBLISH_TASK_ID>"
```

Publish Service 必须验证：

- 草稿是 `chapters/drafts/CH-NNN.txt`；
- chapter review 已通过；
- final regression 已通过且绑定未过期；
- NKB revision/hash 一致；
- outline、protected manifest、style guidance、review report hash 一致；
- 有 publish authorization；
- 有有效 `nkb_sync_proof`；
- Broker 和 ACL 状态有效；
- 目标只能是 `chapters/approved/CH-NNN.txt`；
- 原子写入并更新 `canonical_manifest.yaml`。

### 15.2 发布完成定义

一章只有同时满足以下条件才叫“完全合格并落地”：

- `chapters/approved/CH-NNN.txt` 存在；
- 内容 hash 与发布记录一致；
- `canonical_manifest.yaml` 已登记该章；
- 对应 `chapter_publish` 任务是 pass/completed；
- NKB 更新和 `nkb_sync_proof` 可追踪；
- 审查、风格、读者、回归报告均存在且无阻断 finding；
- 审查问题已反补到 feedback ledger/guidance；
- `outline_refresh` 已完成；
- 当前项目目录再次通过 `layout validate`；
- 没有在非规范目录产生“另一个最终版”。

整本小说完成后，最终正文真相源是：

```text
PROJECT_ROOT/chapters/approved/CH-001.txt
PROJECT_ROOT/chapters/approved/CH-002.txt
...
PROJECT_ROOT/chapters/approved/CH-NNN.txt
PROJECT_ROOT/canonical_manifest.yaml
```

如果未来需要合并为单个全书 TXT，必须先新增/使用受治理的确定性“全书装配”平台命令：

- 输入仅允许读取 `canonical_manifest.yaml` 中已批准的 `.txt`；
- 按 canonical 章节顺序装配；
- 校验每章 hash、缺章、重复章和编码；
- 输出到契约允许的发布/构建目录；
- 生成装配 manifest 和审计记录。

在该命令正式存在前，不得把手工拼接文件称为 canonical 正文。

---

## 16. 失败关闭矩阵：遇到什么，必须做什么

| 情况 | 必须动作 | 禁止动作 |
|---|---|---|
| 找不到项目根/项目未注册 | 从 `workspace.yaml`、`platform.yaml`、registry 查找；仍无则阻塞 | 猜目录、临时建项目 |
| `layout validate` 失败 | 修复目录/标记后重验 | 在错误目录继续产出 |
| 无 Task ID/Task Packet | dispatch/intake 并生成任务包 | 直接照聊天内容执行 |
| required input pending | 补输入或回到上游任务 | AI 自己虚构输入 |
| Session READY=false | 修复 blocker，重新 bootstrap | 沿用旧会话 |
| 项目未 `ready_for_writing` | 回到当前 P0—P5 阶段 | 写正文 |
| 参考未授权/未审核 | 隔离在 inbox/candidates | 用于正文或审查规则 |
| 全书详纲缺章 | 补齐并 `outline validate` | 只写近期几章后开写 |
| 当前章 plan 缺失/过期 | `outline chapter-check`，刷新计划 | 临场自由发挥 |
| Broker/ACL 未验证 | 只走 `broker deploy Plan → Apply → Verify`；Apply 前取得用户/UAC 授权 | 手工组合服务、账号、注册表或 ACL；普通文件写入绕过 |
| writing evidence 不通过 | 修改草稿/策略证据后复验 | submit |
| chapter review fail | `chapter_fix → chapter_review` | 直接风格修订或发布 |
| 风格保真 fail | 回到 `style-revise` | 直接 apply |
| final regression fail | baseline 回 chapter_fix；post_apply 回滚 | 标记通过 |
| NKB sync fail | 回到 `nkb_update` | 发布 |
| human gate 无签名授权/上下文已变化 | 重新 inspect，由受信人工界面签发短期、精确范围授权 | AI 自制决定文件、复用旧授权、通配放行 |
| human gate 缺真人数据 | 等待至少 3 人、2 分群的真实报告 | AI 冒充真人、用普通质量授权代替样本 |
| Author Executor 未配置/响应合同失败 | 配置设备级适配器；对话 AI 改走 `author begin → ingest`；修复响应后重试 | 直接写草稿、用 `--content-file` 冒充自动成稿 |
| 批量后章仍在 backlog | 核验上一章固定 `REQ-...-PUBLISH-CHNNN` 是否 completed | 删除依赖、手工 promote、并行写后章 |
| 发布失败 | 保持草稿，修复授权/绑定/Broker 后重试 | 手工复制到 approved |
| 规则冲突 | 按权威顺序报告并阻塞高风险动作 | 选择最方便的规则 |

---

## 17. 平台脚本复用原则

全链路优先复用平台已有确定性命令：

| 环节 | 统一入口 |
|---|---|
| 项目创建 | `platform project create` |
| 平台/项目体检 | `platform bootstrap`、`doctor`、`layout validate` |
| 会话 | `platform session bootstrap/verify/close` |
| 对话转任务 | `platform task dispatch` |
| 受管自动成稿 | 命令适配器：`platform author validate/prepare/run`；对话 AI：`platform author begin/ingest` |
| 设计 | `platform design ...` |
| 大纲 | `platform outline prepare/validate/chapter-check` |
| NKB Genesis/准备度 | `platform genesis`、`ready` |
| 参考学习 | `platform learn batch/promote-project` |
| 写作策略 | `platform craft build/evidence-*` |
| 风格链 | `platform style ...` |
| AI/真人读者 | `platform reader-panel ...` |
| 人工裁决 | `platform human-gate inspect/authorize`；authorize 仅限受信人工审批界面 |
| 审查反补 | `platform feedback ingest/validate` |
| Broker/ACL | `platform broker deploy --mode Plan/Apply/Verify/Rollback`；低层 `acl-*` 仅供统一脚本内部使用 |
| 章节发布 | `platform chapter ... publish` |

复用规则：

1. 先查 `platform.yaml` 和 `platform <command> --help`，已有命令就不得另写临时脚本。
2. 新脚本必须解决可重复、确定性的公共操作；AI 语义判断不能伪装成脚本完成。
3. 公共脚本放平台 `scripts/`，由 `cli/platform.py` 暴露；不得复制进各项目。
4. 新脚本必须有输入/输出合同、schema、fail-closed 校验、幂等性、审计、回滚和测试。
5. 项目只保存参数、输入、结果和证据，不保存平台公共实现副本。
6. 任何写 canonical 的脚本都必须接入 Task、Session、Broker、授权与 Operation Manifest。
7. 不要把 `scripts/chapter_pipeline_driver.py` 当作 strict-v2 全链路唯一入口；它不能替代现行任务模板、风格链、NKB sync、真人门禁和 Broker 授权。

### 17.1 批量章节与 Git 节奏

- 所有 Git 角色、项目写范围、`main` 更新、分叉和锁处置必须先读取
  `platform.yaml -> governance.git_coordination` 指向的
  `core/governance/Git协调者唯一入口.md`；这是唯一权威，其他章节只作索引。
- 所有对话最终只发布到同一个远端 `origin/main`；禁止创建、复用或推送 writer
  远端分支、任务交付分支。
- 每个对话必须使用用户/启动器分配的 `ACP_GIT_ACTOR_ID`。项目写作者只可修改、
  提交和发布 `git-scopes.json` 中登记的 `projects/<project-id>/**`；其他项目和
  平台文件只能读取、同步和使用。
- 同一设备的并发对话必须使用独立 worktree/index 和本地分支。这里的本地分支仅是
  并发隔离载体，不是远端发布目标。
- worktree 只由 `scripts/git/ai_git_worktree.ps1` 的
  `Diagnose/Ensure/OpenBash/OpenGui` 动作管理。旧 `Pull/Push` 动作强制拒绝。
- 同步、提交、发布的唯一入口是
  `platform git status/sync/commit/publish`。禁止直接运行原生 Git 写命令。
- `platform git commit` 必须绑定真实 Task ID 并显式列出路径；网关检查工作树和
  暂存区全部路径。`platform git publish` 会逐个复核待发布 commit 的路径，并只
  以普通 fast-forward 更新 `origin/main`。
- 多设备同时发布时，先成功者更新 `main`，后一个会收到
  `REMOTE_CAS_REJECTED`。禁止强推；再次执行 `platform git sync` 后，网关只在
  本地 commit 全部合法且双方路径不重叠时受控 rebase，并在前后复核。路径重叠或
  冲突时恢复原 HEAD，交由 Git 协调者评估。
- 修改执行者可以按授权范围修改文件，但不得暂存、提交或上传；按精确文件清单交给
  Git 协调者。协调者只处理 Git 交付和异常，不顺手修改内容。
- 平台 Task、审查、NKB、发布和审计始终逐章原子闭环。
- 每个完全发布并完成 `outline_refresh` 的章节形成一个 Git 提交，便于回滚和定位。
- 每 5 个已闭环章节推送一次远端；卷末、付费边界和高风险修订立即推送。
- worktree 诊断见 `core/governance/AI共享Git工作区指南.md`；角色和路径权限仍以
  《Git协调者唯一入口》及 `git-scopes.json` 为准。
- `refs/codex/turn-diffs/**` 与 `refs/heads/codex/**` 不冲突，禁止修改
  `packed-refs` 清理前者。失败时不得自动删除 `.git/index.lock`；它可能属于另一
  个 AI，只能由协调者确认无 Git 进程后处理。
- `origin/main` 本地引用可能陈旧。网关以远端回读的精确 SHA 进行同步和发布后
  复核，禁止根据 `packed-refs` 中的旧值回退项目。
- Git 批次不能改变平台串行依赖，也不能把 5 章 NKB 更新合并成一次。

---

## 18. 每章执行检查单

AI 在开始每章前逐项回答“是”：

- [ ] 项目状态是 `ready_for_writing` 或 `writing`。
- [ ] Broker 状态和 ACL 已验证。
- [ ] 本章来自合法 Task，Session READY=true。
- [ ] Task Packet 六个文件均已读取，输入无 pending。
- [ ] 全书逐章详纲验证通过，本章 `PLAN-NNN.yaml` 通过 chapter-check。
- [ ] NKB、上一章 approved 正文和 handoff 为最新版本。
- [ ] 参考学习已获授权、审核和项目级批准。
- [ ] 已读取 reference guidance、writing guidance、review regression。
- [ ] 已生成本章 writing strategy 和 style guidance。
- [ ] guidance 已记录本章全部场景类型、出场人物和 ACTIVE 参考规则来源。
- [ ] 成稿来自 `platform author run`，或同一 AI 完成 `platform author begin → ingest`；不存在直接写 drafts。
- [ ] 草稿目标明确为 `chapters/drafts/CH-NNN.txt`。
- [ ] 开头/结尾由本章功能决定，并检查跨章重复。
- [ ] 写作策略证据和字数预算检查通过。
- [ ] chapter review 的事实/故事/技法/读者维度全部通过。
- [ ] 有问题时已完成 fix/review 循环，而不是口头宣称修复。
- [ ] 风格诊断、保真、质量、apply、final regression 均走完适用分支。
- [ ] 审查 findings 已进入反馈 ledger 并反补写作/回归 guidance。
- [ ] candidate facts 已经 NKB update + NKB sync，并有同步证明。
- [ ] 正式 TXT 由 Publish Service 写入 approved，manifest 已更新。
- [ ] 发布后 outline refresh 已完成。

有任何一项为“否”，本章不得宣告完成。

---

## 19. 全书完成检查单

- [ ] `CH-001.txt` 至 `CH-NNN.txt` 全部位于 `chapters/approved/`。
- [ ] canonical manifest 无缺章、重复章、hash 漂移。
- [ ] 所有章节 task chain 可追踪，无跳步完成。
- [ ] 所有 NKB 更新有 operation manifest 和 sync proof。
- [ ] 所有卷末、付费边界和重大修订里程碑完成人类读者门禁。
- [ ] 所有 human gate 授权均签名、未过期、绑定具体 task/context；没有通配或 AI 自批。
- [ ] 参考来源授权、指纹、撤回链完整，学习产物无原文泄漏。
- [ ] 审查反馈已沉淀并在后续章节得到回归验证。
- [ ] NKB、章纲、正文、summaries/handoffs 的最终状态一致。
- [ ] 项目目录通过 strict-v2 layout 校验。
- [ ] 没有项目外散落的草稿、最终版或临时脚本。
- [ ] 项目状态经正式任务迁移到 `completed`。

---

## 20. 可直接交给全新 AI 的首条指令

```text
请先完整读取：
D:\AI-Workspace\platform\AI-Creative-Platform\START_HERE_全新AI全链路强制执行指南.md

然后按该文件第 0、1、3、5 节完成平台识别、项目定位、体检、Broker/ACL 校验、
任务派发、Task Packet 读取和 Session Bootstrap。

在你能明确报告 PROJECT_ROOT、PROJECT_ID、lifecycle status、SESSION_ID、
TASK_ID、Task type/state、Broker 状态和唯一合法下一步之前，
禁止开始设计、生成 NKB/大纲、写作、审查、修改、反补或发布。

本次用户请求是：
<把我的自然语言要求原样放在这里>
```

---

## 21. 最终判定语句

平台内的“完成”不是 AI 说“已经完成”，而是同时存在：

```text
合法 Task
+ READY Session
+ resolved inputs
+ 受控产物
+ 独立审查证据
+ 修复与回归通过
+ 学习/反馈反补
+ NKB canonical 同步证明
+ Broker/Publish Service 授权发布
+ canonical_manifest 登记
+ 发布后大纲刷新
= 可审计、可回滚、可继续下一步的真正闭环
```

任何缺项都必须视为未完成。最方便的下一步不等于最合法的下一步；AI 始终执行状态机允许的唯一下一步。
