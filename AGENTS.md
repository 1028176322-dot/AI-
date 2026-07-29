# Workspace Git Governance Entry

本文件是 `D:\AI-Workspace` 及所有下级目录的 Git 行为强制入口。

## 开始前必须读取

1. `workspace.yaml`
2. 平台 `platform.yaml`
3. `platform.yaml -> governance.git_coordination`
4. `platform.yaml -> governance.git_scope_policy`
5. 当前项目 `AGENTS.md` 和 `project.yaml`

## 单一远端分支

- 所有对话读取并最终发布到同一个远端 `origin/main`。
- 同一设备的并发对话仍必须使用独立 worktree/index；禁止共享工作树。
- 本地分支名可以不同，远端发布目标只能是 `main`。
- 禁止创建、复用或推送长期 writer 远端分支。

## 项目范围权限

- 所有对话可以同步、读取和使用整个仓库。
- `project_writer` 只能修改、提交和发布其权限表登记的
  `projects/<project-id>/**`。
- `modifier` 可以修改授权文件，但不得提交或发布。
- `read_only` 只能同步、读取和使用。
- `git_coordinator` 只负责 Git 提交、异常治理和交付，不修改内容。
- 未登记身份按只读处理。

AI 不得自行选择或更换身份。身份由用户/受控启动器提供：

```text
ACP_GIT_ACTOR_ID=<actor-id>
```

## 唯一 Git 写入口

所有 Git 状态变更和远端操作只能通过：

```text
platform git status
platform git sync
platform git commit
platform git publish
```

禁止 AI 直接执行 `git add/commit/fetch/pull/merge/rebase/push/reset/clean/stash`
或修改引用。允许 `status/diff/show/log/rev-parse/cat-file/merge-base` 等只读诊断，
但不得用只读诊断拼装旁路发布流程。

唯一一次例外：当远端 `main` 尚未包含
`core/governance/git-scopes.json` 和 Git 网关时，只允许用户指定的
`git-coordinator` 按《Git协调者唯一入口》的“首次启用”清单完成一次精确自举提交。
远端回读确认后例外立即失效，任何后续 Git 写操作都必须走网关。

任何 BLOCK 必须停止。禁止通过改 actor-id、改本地权限表、强推、删分支重建、
reset、stash、手工编辑 `packed-refs` 或删除 `.git/index.lock` 绕过。

完整流程与返回码只以
`platform.yaml -> governance.git_coordination` 指向的文件为准。
