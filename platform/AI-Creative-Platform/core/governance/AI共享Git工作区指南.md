# AI 共享 Git 仓库隔离规则

## 不可违反的边界

多个 AI 可以共享同一个 Git 仓库对象库和远程仓库，但不得并发使用同一个工作树、
同一个 index 或同一个分支。`main` 只允许协调者更新。

每个 AI 必须具有：

- 独立目录：`<仓库名>-ai-worktrees/<agent-id>/`
- 独立分支：优先 `codex/<agent-id>`；仅当引用能力探针证实斜杠引用不可写时，
  自动降级为 `codex-<agent-id>`
- 独立 index：由 Git worktree 自动维护
- 独立 Pull/Push：只操作 `codex/<agent-id>`

## 建立隔离工作树

设置稳定且唯一的 AI 标识：

```powershell
$env:AI_AGENT_ID = "writer-a"
```

右键仓库内任意文件夹，选择：

```text
AI Git Bash Here (Isolated)
```

也可以直接调用：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File "$env:USERPROFILE\.workbuddy\tools\ai_git_worktree.ps1" `
  -Action Ensure `
  -RepoPath "D:\AI-Workspace" `
  -AgentId "writer-a"
```

新设备尚未安装 WorkBuddy 工具副本时，先直接运行仓库权威脚本：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File "D:\AI-Workspace\platform\AI-Creative-Platform\scripts\git\ai_git_worktree.ps1" `
  -Action Diagnose `
  -RepoPath "D:\AI-Workspace" `
  -AgentId "writer-a"
```

仓库脚本是 SSOT，`$env:USERPROFILE\.workbuddy\tools\ai_git_worktree.ps1`
只是部署副本；更新后必须校验两者 SHA-256 一致。

管理器默认使用 `-BranchMode Auto`：

1. 先用临时引用实际创建、`rev-parse` 回读并 CAS 删除，验证
   `refs/heads/codex/<agent-id>`；
2. 只有斜杠引用探针失败时才测试 `refs/heads/codex-<agent-id>`；
3. 两者都失败则阻塞，绝不把 Git 的返回码当作唯一成功证据；
4. 所有 Git 调用固定启用 `core.longpaths=true`，避免任务链长文件名导致 worktree
   检出到一半失败。
5. `origin/main` 仅是本地缓存，不能作为远端真相源；Ensure/Pull 必须通过
   `git ls-remote origin refs/heads/<branch>` 取得精确 SHA，确认该 commit 对象
   已存在或完成显式 fetch 后，按 SHA 创建分支或 `merge --ff-only`。

可先执行无持久副作用的诊断：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File "$env:USERPROFILE\.workbuddy\tools\ai_git_worktree.ps1" `
  -Action Diagnose `
  -RepoPath "D:\AI-Workspace" `
  -AgentId "writer-a" `
  -BranchMode Auto
```

返回结果中的 `selected.ref_mode` 为实际选择；`BLOCKED` 时会同时报告斜杠和平面
引用的真实 Git 错误与当前仓库锁。`remote_main_authoritative.sha` 是远端实时值；
`origin_main_cached` 只是本地缓存，`origin_main_cache_matches=false` 时管理器仍会
使用实时 SHA，不得人工 reset 到缓存值。

### 关于 `refs/codex/turn-diffs`

Codex checkpoint 使用的是：

```text
refs/codex/turn-diffs/**
```

AI 工作分支使用的是：

```text
refs/heads/codex/**
```

这是两个独立引用命名空间，packed-refs 中存在前者不会阻止后者。禁止手工删除
checkpoint 引用或直接编辑 `packed-refs`。

### 权限与锁的判断

- `git fetch` 成功不能证明 `refs/heads/**` 可写；必须以引用创建和回读探针为准。
- packed-refs 中的 `refs/remotes/origin/main` 可能陈旧或不可重写；不得手工删除
  该行。管理器的 Ensure/Pull/Push 不依赖 remote-tracking ref，并在 Push 后用
  `ls-remote` 回读远端 SHA 验证。
- AI 沙箱可能把 `.git` 设为只读。在这种环境中，脚本会明确报告
  `Permission denied` 或 `unable to create directory`。应从受信终端、右键入口
  或获准的 Git 操作运行管理器，不能靠改分支名绕过权限边界。
- `index.lock` 可能属于另一 AI 正在运行的 Git。失败回滚只删除本次创建的 worktree
  和分支，并使用旧 SHA 做 CAS；管理器只报告全局锁，绝不自动删除。
- 只有确认所有 Git 进程已结束、锁确属崩溃残留时，才可由协调者单独清理锁。

## 独立拉取与上传

```powershell
# 只快进该 AI 的远程分支；远程分支不存在时以 origin/main 初始化
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File "$env:USERPROFILE\.workbuddy\tools\ai_git_worktree.ps1" `
  -Action Pull -RepoPath "D:\AI-Workspace" -AgentId "writer-a"

# 只推送管理器分配的分支，永不直接推送 main
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File "$env:USERPROFILE\.workbuddy\tools\ai_git_worktree.ps1" `
  -Action Push -RepoPath "D:\AI-Workspace" -AgentId "writer-a"
```

Pull 在工作树有未提交修改时拒绝执行；Push 在当前分支不是分配分支时拒绝执行。
创建、Pull、Push 经过仓库级互斥锁串行化，但不同 AI 的编辑、测试和提交可并行。

## 合并到 main

AI 只能上传管理器返回的 `branch`（通常为 `codex/<agent-id>`，兼容环境可能为
`codex-<agent-id>`）。协调者通过审查、测试和合并门禁后，
统一合并到 `main`。禁止 AI 使用 `push --force`、直接推送 `main`、共享主工作树，
或通过删除 `.git/index.lock` 绕过仍在运行的 Git 操作。
