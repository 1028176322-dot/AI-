# Git 单 main 项目权限唯一入口

> 给所有新 AI 的强制执行文件
>
> 机器入口：`platform.yaml -> governance.git_coordination`
>
> 权限事实源：`platform.yaml -> governance.git_scope_policy`
>
> 唯一命令入口：`platform git status/sync/commit/publish`

## 1. 先读结论

整个仓库只使用一个远端集成分支：

```text
origin/main
```

所有对话都可以拉取、读取和使用整个仓库，但只能提交被权限表授予的路径：

- 项目写作者：只能提交自己负责的 `projects/<project-id>/**`；
- 平台修改执行者：可以改平台文件，但不能自行提交或上传；
- 只读对话：只能同步、读取和使用；
- Git 协调者：负责提交修改执行者的交付、处理异常和跨范围治理，不修改内容。

任何 AI 都不得直接运行会改变 Git 状态或远端的原生命令。所有同步、暂存、提交和
上传必须经过 `platform git ...`。网关会从远端权威 `main` 读取权限表，并对每个
待发布 commit 的全部路径重新检查，不能通过修改本地权限副本提权。

## 2. “同一个分支”的准确含义

“所有对话使用同一个分支”是指所有合法提交最终直接进入同一个远端
`origin/main`，不再创建长期 writer 分支或每任务交付分支。

本地仍必须隔离：

- 不同设备使用各自 clone/worktree；
- 同一设备的并发对话使用独立 worktree 和 index；
- 本地分支名可以由 worktree 管理器自动分配；
- 本地分支名不是发布目标，网关始终发布到远端 `main`。

多个 worktree 不能同时检出同一个本地分支，这是 Git 的约束。禁止为了“看起来都
叫 main”而让多个 AI 共享工作树/index；那会重新造成 `index.lock`、脏文件覆盖和
错误提交。

## 3. 强制入口

AI 进入 Workspace 后依次读取：

1. Workspace 根 `AGENTS.md`；
2. `workspace.yaml`；
3. 平台 `platform.yaml`；
4. 本文件；
5. `core/governance/git-scopes.json`；
6. 当前项目 `AGENTS.md` 和 `project.yaml`。

随后设置由用户/启动器分配的身份：

```powershell
$env:ACP_GIT_ACTOR_ID = "<actor-id>"
```

AI 不得自行改成其他 actor-id。身份不明确时按 `read-only` 处理。

## 4. 权限事实源

权限文件：

```text
platform/AI-Creative-Platform/core/governance/git-scopes.json
```

每个 actor 包含：

- `role`
- `project_id`
- `project_path`
- `read_paths`
- `write_paths`
- `can_sync`
- `can_commit`
- `can_publish`
- `require_task_id`

默认身份是只读。未登记 actor 可以同步和读取，但不能提交或上传。

权限变更只有进入远端 `main` 后才生效。Git 网关发布时读取远端 `main` 中的权限，
不会相信工作区里尚未提交的修改，因此写作者不能通过修改本地权限文件扩大权限。

## 5. 角色矩阵

| 角色 | 读取全仓库 | 修改内容 | 网关同步 | 网关提交 | 网关发布 main |
|---|---:|---:|---:|---:|---:|
| `project_writer` | 是 | 仅负责项目 | 是 | 仅负责项目 | 仅负责项目 |
| `modifier` | 是 | 授权范围 | 是 | 否 | 否 |
| `read_only` | 是 | 否 | 是 | 否 | 否 |
| `git_coordinator` | 是 | 否 | 是 | 按交付清单 | 是 |

Git 协调者拥有 Git 权限，不拥有内容创作权限。发现文件问题时必须退回修改执行者，
不能顺手修改。

当前已登记的项目写作者：

| actor-id | project-id | 唯一写范围 |
|---|---|---|
| `writer-a` | `dushi-jishi` | `projects/dushi-jishi/**` |
| `writer-novel-dsf` | `novel-dsf` | `projects/道法百年/**` |

## 6. 唯一命令

### 6.1 查看状态

```powershell
.\platform\AI-Creative-Platform\platform.bat git status `
  --repo "<WORKTREE>"
```

返回：

- actor 和角色；
- 本地分支/HEAD；
- 远端真实 `main` SHA；
- 当前脏文件；
- 允许的写路径。

### 6.2 同步

```powershell
.\platform\AI-Creative-Platform\platform.bat git sync `
  --repo "<WORKTREE>"
```

同步规则：

- 治理上线前创建的旧 worktree 即使本地尚无 `git-scopes.json`，也先从固定
  `origin/main` 读取权威策略，再执行权限判断和 fast-forward；本地策略只显示
  `missing/invalid/differs/matches` 诊断状态，从不参与授权；
- worktree 必须干净；
- 只 Fetch 权威 `main`；
- 只允许 fast-forward；
- 本地存在未发布 commit、远端未前进时返回 `LOCAL_AHEAD`；
- 本地和远端都前进时，先复核本地所有 commit 均在 actor 项目范围；
- 本地路径与远端新增路径完全不重叠时，执行受控 rebase 并再次复核；
- 路径重叠或 rebase 冲突时恢复原 HEAD 并阻断；
- 禁止自动 stash、reset、clean 或覆盖。

所有角色都可以同步，因为所有角色都有全仓库读取权。

若托管 Python 的 `PATH` 中没有 Git，网关按以下顺序寻找：

1. `ACP_GIT_EXECUTABLE` 指定的 `git.exe`；
2. 当前 `PATH`；
3. WorkBuddy PortableGit；
4. Codex bundled Git；
5. Windows 标准 Git 安装目录。

因此不得因托管环境缺少 PATH 项而绕开网关；非标准安装只需由启动器设置
`ACP_GIT_EXECUTABLE`。

从 Git Bash 调用时，`--repo` 使用 `D:/AI-Workspace-...` 或 `/d/...` 形式；
反斜杠会被 Bash 当作转义符。这只是 shell 路径写法，不改变网关语义。

旧 worktree 自举时，它自身的旧网关代码尚未修复，第一次必须调用同一设备上
已经更新到新版 `main` 的主/协调者工作树入口，并把旧 worktree 传给 `--repo`：

```powershell
$env:ACP_GIT_ACTOR_ID = "writer-a"
& "D:\AI-Workspace\platform\AI-Creative-Platform\platform.bat" git status `
  --repo "D:\AI-Workspace-ai-worktrees\writer-a"
& "D:\AI-Workspace\platform\AI-Creative-Platform\platform.bat" git sync `
  --repo "D:\AI-Workspace-ai-worktrees\writer-a"
```

第一条应显示 `local_policy.state=missing`，第二条应返回 `FAST_FORWARDED`。完成后
旧 worktree 已包含新版网关和策略，后续才可改用它自身的 `platform.bat`。禁止从
远端手工复制单个策略文件，因为那不会升级旧网关代码，也会破坏可审计的快进过程。

### 6.3 提交

项目写作者：

```powershell
.\platform\AI-Creative-Platform\platform.bat git commit `
  --repo "<WORKTREE>" `
  --task-id "<TASK-ID>" `
  --message "<提交说明>" `
  --path "projects/<project-id>/<精确文件或目录>"
```

多个路径重复传 `--path`。网关会：

1. 从远端 `main` 读取受信权限；
2. 检查 worktree 全部脏文件；
3. 发现任何范围外脏文件立即拒绝；
4. 只暂存显式 `--path`；
5. 复查暂存区全部路径；
6. 执行 `diff --cached --check`；
7. 创建本地 commit；
8. 写设备本地审计。

修改执行者不得调用 commit。完成后向 Git 协调者交付精确文件清单；协调者使用相同
入口按交付范围提交。

项目写作者提供的 Task ID 必须在其负责项目的 `tasks/` 中唯一存在，且位于
`claimed/running/submitted/review/reviewing/passed/completed/archive` 之一。
`backlog/ready/blocked/failed` 中的任务不得用于提交或发布。

### 6.4 发布到唯一远端 main

```powershell
.\platform\AI-Creative-Platform\platform.bat git publish `
  --repo "<WORKTREE>" `
  --task-id "<TASK-ID>"
```

网关逐个检查 `remote-main..HEAD` 的所有 commit：

- 必须是线性历史；
- 每个 commit 的每个文件都必须在 actor 写范围内；
- 即使某越权文件后来被恢复，历史中出现过也会拒绝；
- worktree 必须干净；
- 本地 HEAD 必须以当前远端 `main` 为祖先；
- Push 必须是普通 fast-forward；
- Push 后必须用 `ls-remote` 回读并确认 SHA。

## 7. 不同电脑、不同项目

不同电脑不共享本地对象库，没有关系。每台电脑都执行相同流程：

```text
platform git status
        ↓
platform git sync
        ↓
修改自己项目
        ↓
platform git commit
        ↓
platform git publish
```

例如：

- 电脑 A：`writer-a`，仅写 `projects/dushi-jishi/**`；
- 电脑 B：`writer-novel-dsf`，仅写 `projects/道法百年/**`；
- 两者都从 `origin/main` 同步；
- 两者都把合法 commit 直接发布到 `origin/main`；
- 任何人都能读取对方项目，但不能通过网关提交对方路径。

新项目或新 writer 必须先由平台修改执行者更新 `git-scopes.json`，再由 Git 协调者
提交并发布该权限变更。权限未进入远端 `main` 前，新 writer 保持只读。

## 8. 多设备并发

远端 `main` 是最终 compare-and-swap 门禁。

若两个项目同时发布：

1. 第一台设备成功 fast-forward `main`；
2. 第二台设备的 Push 被拒绝为 `REMOTE_CAS_REJECTED`；
3. 第二台设备不得强推；
4. 再次执行 `platform git sync`；
5. 网关复核本地每个 commit 的项目范围，并比较双方路径；
6. 路径不重叠时受控 rebase 到最新 `main`，复核通过后可再次发布；
7. 路径重叠或 rebase 冲突时恢复原 HEAD，交给 Git 协调者人工处理。

受控 rebase 不会在脏工作树、越权 commit、路径重叠或冲突时继续。禁止直接运行
原生 `git rebase`。

## 9. 新增项目/身份

修改 `git-scopes.json` 时至少登记：

```json
"writer-example": {
  "role": "project_writer",
  "project_id": "example-project",
  "project_path": "projects/example-project",
  "read_paths": ["**"],
  "write_paths": ["projects/example-project/**"],
  "can_sync": true,
  "can_commit": true,
  "can_publish": true,
  "require_task_id": true
}
```

强制条件：

- 一个 writer 默认只绑定一个项目；
- 写路径必须位于该项目根；
- 不得授权 `projects/**`；
- 不得授权另一个项目；
- 不得让项目 writer 修改平台、Workspace 根或权限表；
- 平台修改执行者默认无 commit/publish 权限；
- 只有用户可以决定角色和项目归属。

## 10. 审计

Git 网关把审计写到设备本地：

```text
%LOCALAPPDATA%/AI-Creative-Platform/git-audit/<repo-id>.jsonl
```

审计包含：

- actor/project/task；
- action 与 decision；
- 发布前后 SHA；
- commit 列表；
- 文件路径；
- 时间和仓库位置。

秘密、密码和 Git 凭据不得进入审计。

## 11. 禁止操作

除网关内部调用外，所有 AI 禁止直接执行：

- `git add`
- `git commit`
- `git fetch`
- `git pull`
- `git merge`
- `git rebase`
- `git push`
- `git reset`
- `git clean`
- `git stash`
- `git update-ref`
- 修改/删除分支和标签

始终禁止：

- force push / force-with-lease；
- 删除远端分支绕过 non-fast-forward；
- 多个 AI 共享同一 worktree/index；
- 手工编辑 `packed-refs`；
- 未确认锁所有者就删除 `.git/index.lock`；
- 修改本地权限文件后声称权限已生效；
- 绕过网关用原生 Git 上传。

允许的原生 Git 只读命令仅限诊断，例如 `status`、`diff`、`show`、`log`、
`rev-parse`、`cat-file` 和 `merge-base`；但优先使用 `platform git status`。

## 12. 常见返回码

| code | 含义 | 唯一下一步 |
|---|---|---|
| `ACTOR_ID_REQUIRED` | 未指定身份 | 由用户/启动器分配 actor |
| `GIT_EXECUTABLE_NOT_FOUND` | PATH 和标准位置均找不到 Git | 由启动器设置 `ACP_GIT_EXECUTABLE` |
| `GIT_EXECUTABLE_INVALID` | 显式 Git 路径不存在 | 修正 `ACP_GIT_EXECUTABLE` |
| `ACTION_NOT_AUTHORIZED` | 角色无该权限 | 停止，不得改身份绕过 |
| `TASK_NOT_FOUND_OR_ELIGIBLE` | Task 不存在或状态不可交付 | 回到任务系统处理 |
| `PATH_SCOPE_VIOLATION` | 含非负责项目路径 | 退回越权修改 |
| `DIRTY_WORKTREE` | 同步/发布时有未提交内容 | 先按合法任务处理 |
| `NON_FAST_FORWARD_BASE` | 本地不基于最新 main | 交给协调者评估 |
| `REMOTE_CAS_REJECTED` | 另一设备抢先发布 | 重新同步并治理分叉 |
| `DIVERGED_PATH_OVERLAP` | 本地与远端修改路径重叠 | 协调者人工处理 |
| `SCOPED_REBASE_CONFLICT` | 受控对齐冲突且已回滚 | 协调者人工处理 |
| `MERGE_COMMIT_REJECTED` | 待发布范围含 merge | 协调者审查历史 |
| `DETACHED_HEAD` | 当前 worktree 没有本地分支 | 用统一 worktree 管理器修复 |
| `TRUSTED_POLICY_MISSING` | 远端尚无权限表 | 先部署本功能 |

任何 BLOCK 都不得通过强推、改 actor-id、改本地权限表或直接调用 Git 绕过。

## 13. 给新 AI 的启动检查单

- [ ] 我已读取 Workspace 根 `AGENTS.md`。
- [ ] 我已读取本文件。
- [ ] 用户已明确我的 actor-id 和负责项目。
- [ ] `platform git status` 显示的角色/项目正确。
- [ ] 我使用独立 worktree/index。
- [ ] 开始修改前已执行 `platform git sync`。
- [ ] 我只修改 `write_paths` 范围。
- [ ] 提交绑定真实 Task ID。
- [ ] 我只使用 `platform git commit/publish`。
- [ ] BLOCK 时停止，不尝试原生 Git 绕过。

有一项为“否”就不得修改、提交或上传。

## 14. 强制边界

平台网关能够可靠拒绝通过它发起的越权提交，并从远端受信策略读取权限。但如果所有
AI 共用同一份可写 GitHub SSH 凭据，一个故意无视本文件的外部进程仍可直接调用
Git 绕过本地网关。

服务器级硬阻断需要同时满足：

1. 普通 AI 不持有可直接写仓库的凭据，只有受控网关/Broker 持有；或
2. 每个项目使用不同 GitHub 用户/团队/App 身份，并配置 Push Rulesets；或
3. `main` 要求 PR/状态检查，由服务器拒绝未经网关验证的更新。

在服务器保护尚未完成前，本地网关是强制 AI 入口，但不是 GitHub 凭据隔离的替代品。

## 15. 首次启用

网关的受信策略来自远端 `main`。因此本功能尚未进入远端时，调用 write action 会
返回 `TRUSTED_POLICY_MISSING`，这是预期的 fail-closed 行为。

首次上线只允许用户指定的 `git-coordinator` 执行一次自举：

1. 接收修改执行者给出的精确文件清单；
2. 排除清单外的既有脏文件和未跟踪文件；
3. 用上线前既有受信 Git 流程把本功能作为一个原子批次提交并普通
   fast-forward 到 `main`；
4. 远端回读确认 `main` 已包含：
   - `core/governance/git-scopes.json`
   - `scripts/git/git_scope_gateway.py`
   - `cli/platform.py` 中的 `platform git` 入口
   - 本文件与 Workspace/平台 `AGENTS.md`
5. 执行 `platform git validate-policy`；
6. 分别以 `writer-a`、`writer-novel-dsf`、`read-only` 执行
   `platform git status`，确认角色和路径；
7. 宣布自举完成。

第 4 步远端回读成功后，自举例外立即且永久失效。之后包括 Git 协调者在内的所有
身份都必须使用网关，不得把“部署”当成长期旁路。
