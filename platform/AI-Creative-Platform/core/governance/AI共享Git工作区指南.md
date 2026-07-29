# AI 共享 Git 本地隔离指南

> 本文只说明本地 worktree、index、引用探针和锁隔离。
>
> 角色权限、项目写范围、同步、提交和发布的唯一权威是
> [Git协调者唯一入口.md](Git协调者唯一入口.md)。
>
> 权限事实源是 [git-scopes.json](git-scopes.json)。

## 1. 不可违反的边界

所有对话最终只发布到远端：

```text
origin/main
```

“共同使用 main”不等于共同使用本地工作目录。多 AI 可以共享同一个 Git 对象库和
远程仓库，但同一设备上的并发对话必须各自拥有：

- 独立 worktree 目录；
- 独立 index；
- 独立本地分支；
- 稳定且唯一的 `agent-id`。

本地分支只是隔离载体，不是远端发布目标。禁止直接推送本地 writer 分支；发布只能
通过 `platform git publish` 进入远端 `main`。

## 2. 建立本地隔离 worktree

先设置稳定的 AI 标识：

```powershell
$env:AI_AGENT_ID = "writer-a"
```

然后调用仓库中的权威脚本：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File "D:\AI-Workspace\platform\AI-Creative-Platform\scripts\git\ai_git_worktree.ps1" `
  -Action Ensure `
  -RepoPath "D:\AI-Workspace" `
  -AgentId "writer-a"
```

脚本允许的用途只有：

- `Diagnose`：诊断仓库、引用和锁；
- `Ensure`：创建或确认隔离 worktree；
- `OpenBash`：在隔离 worktree 打开终端；
- `OpenGui`：在隔离 worktree 打开图形客户端。

旧的 `Pull` 和 `Push` 参数保留为可识别参数，但会 fail-closed 拒绝。它们不是合法
同步或发布入口。

## 3. 分支命名与引用探针

管理器默认使用 `-BranchMode Auto`：

1. 先创建临时引用并通过 `rev-parse` 回读验证
   `refs/heads/codex/<agent-id>`；
2. 只有斜杠引用探针失败时，才测试
   `refs/heads/codex-<agent-id>`；
3. 两者都失败就阻断；
4. Git 返回码为 0 但引用无法回读，仍判定失败；
5. 所有 Git 调用强制启用 `core.longpaths=true`。

本地分支可以是 `codex/writer-a` 或 `codex-writer-a`。无论实际使用哪个名称，远端
目标都只能是 `origin/main`。

可先运行无持久副作用的诊断：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File "D:\AI-Workspace\platform\AI-Creative-Platform\scripts\git\ai_git_worktree.ps1" `
  -Action Diagnose `
  -RepoPath "D:\AI-Workspace" `
  -AgentId "writer-a" `
  -BranchMode Auto
```

返回中的 `selected.ref_mode` 是实际选择。`BLOCKED` 时会同时报告真实 Git 错误和
仓库锁。`remote_main_authoritative.sha` 是实时远端值；
`origin_main_cached` 只是本地缓存。

## 4. 正确的同步、提交和发布

进入隔离 worktree 后，设置用户分配的治理身份：

```powershell
$env:ACP_GIT_ACTOR_ID = "writer-a"
```

只使用统一网关：

```powershell
.\platform\AI-Creative-Platform\platform.bat git status `
  --repo "D:\AI-Workspace-ai-worktrees\writer-a"

.\platform\AI-Creative-Platform\platform.bat git sync `
  --repo "D:\AI-Workspace-ai-worktrees\writer-a"

.\platform\AI-Creative-Platform\platform.bat git commit `
  --repo "D:\AI-Workspace-ai-worktrees\writer-a" `
  --task-id "<TASK-ID>" `
  --message "<提交说明>" `
  --path "projects/<project-id>/<精确路径>"

.\platform\AI-Creative-Platform\platform.bat git publish `
  --repo "D:\AI-Workspace-ai-worktrees\writer-a" `
  --task-id "<TASK-ID>"
```

网关只允许 actor 权限表登记的项目路径。不同设备使用相同入口；不需要共享对象库，
也不创建远程 writer 分支。

治理上线前已经存在的旧 worktree 可能尚无本地 `git-scopes.json`。这不是人工复制
策略或绕过网关的理由：新版网关会先从固定 `origin/main` 读取权威策略，
`status` 报告 `local_policy.state=missing`，随后 `sync` 在工作树干净时直接
fast-forward，把策略和新版平台一起带入。若本地策略无效或被修改，只显示
`invalid/differs`，不参与授权。

第一次自举不能调用旧 worktree 自己的旧脚本；必须从已经更新的主/协调者工作树
启动新版 `platform.bat`，用 `--repo` 指向旧 worktree。返回 `FAST_FORWARDED`
后，旧 worktree 才能恢复使用自身入口。标准命令见
[Git协调者唯一入口.md](Git协调者唯一入口.md) 的“同步”章节。

托管 Python 找不到 Git 时，启动器可设置：

```powershell
$env:ACP_GIT_EXECUTABLE = "<git.exe 的绝对路径>"
```

未设置时网关会自动搜索 PATH、WorkBuddy PortableGit、Codex bundled Git 和
Windows 标准安装目录。Git Bash 中 `--repo` 使用 `D:/...` 或 `/d/...` 路径。

## 5. 关于 refs/codex/turn-diffs

Codex checkpoint 引用：

```text
refs/codex/turn-diffs/**
```

本地工作分支引用：

```text
refs/heads/codex/**
```

它们是两个独立命名空间。禁止手工删除 checkpoint 引用或编辑 `packed-refs`。

## 6. 锁与异常

- `git fetch` 成功不能证明本地分支引用可写，必须以创建和回读探针为准；
- `origin/main` 可能陈旧，统一脚本会通过远端回读取得权威 SHA；
- 本地缺少 `git-scopes.json` 不再阻断旧 worktree 自举；远端权威策略缺失才阻断；
- `.git/index.lock` 可能属于另一个正在运行的 AI；
- 脚本失败时不得自动删除全局 `index.lock`；
- 只有 Git 协调者确认所有相关 Git 进程已停止并确认锁为残留后，才可单独处理锁；
- 禁止手工编辑 `packed-refs`、强推、reset、stash 或删除远端引用绕过失败。

## 7. 完成判定

开始工作前必须同时满足：

- 隔离 worktree 已建立；
- `platform git status` 显示正确 actor、角色和项目；
- `platform git sync` 成功；
- 修改范围位于 actor 的 `write_paths`；
- 提交和发布只经过 `platform git commit/publish`。

任何一步返回 BLOCK 都必须停止，并按
[Git协调者唯一入口.md](Git协调者唯一入口.md) 的返回码处理。
