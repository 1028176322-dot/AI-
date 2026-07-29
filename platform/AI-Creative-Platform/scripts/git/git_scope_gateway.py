#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Project-scoped single-main Git gateway.

The gateway deliberately trusts the policy stored in the authoritative remote
main commit, not a locally edited policy file. It serializes no cross-device
state; Git's fast-forward update is the final compare-and-swap guard.
"""

import argparse
import datetime
import fnmatch
import hashlib
import json
import os
import posixpath
import subprocess
import sys


POLICY_RELATIVE_PATH = (
    "platform/AI-Creative-Platform/core/governance/git-scopes.json")
REMOTE_NAME = "origin"
INTEGRATION_BRANCH = "main"
SCHEMA = "git-scope-gateway-result@1.0.0"
GIT_ELIGIBLE_TASK_STATES = (
    "claimed", "running", "submitted", "review", "reviewing",
    "passed", "completed", "archive")


class GatewayError(RuntimeError):
    def __init__(self, code, message, details=None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def _run_git(repo, *arguments, check=True):
    command = [
        "git", "-c", "core.longpaths=true", "-c", "core.quotepath=false",
        "-C", repo,
    ] + list(arguments)
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if check and completed.returncode:
        raise GatewayError(
            "GIT_COMMAND_FAILED",
            "Git command failed",
            {
                "arguments": list(arguments),
                "returncode": completed.returncode,
                "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(),
            },
        )
    return completed


def _repo_root(requested):
    start = os.path.abspath(requested or os.getcwd())
    result = _run_git(start, "rev-parse", "--show-toplevel")
    return os.path.normpath(result.stdout.strip())


def _normalize_path(value):
    raw = str(value).replace("\\", "/")
    raw_parts = raw.split("/")
    if (
            not raw
            or raw.startswith("/")
            or ":" in raw
            or ".." in raw_parts):
        raise GatewayError(
            "PATH_INVALID",
            "Git path must be a repository-relative path",
            {"path": str(value)},
        )
    normalized = posixpath.normpath(raw)
    if normalized in (".", "..") or normalized.startswith("../"):
        raise GatewayError(
            "PATH_INVALID",
            "Git path must not escape or resolve to the repository root",
            {"path": str(value)},
        )
    return normalized


def _remote_tip(repo, remote, branch):
    result = _run_git(
        repo, "ls-remote", "--exit-code", remote,
        "refs/heads/%s" % branch, check=False)
    if result.returncode:
        raise GatewayError(
            "REMOTE_BRANCH_UNAVAILABLE",
            "Authoritative remote branch was not found",
            {
                "remote": remote,
                "branch": branch,
                "stderr": result.stderr.strip(),
            },
        )
    line = result.stdout.strip().splitlines()
    if len(line) != 1:
        raise GatewayError(
            "REMOTE_BRANCH_AMBIGUOUS",
            "Remote branch query did not return exactly one ref",
            {"output": result.stdout.strip()},
        )
    return line[0].split()[0]


def _fetch_authoritative(repo, remote, branch, expected_sha):
    _run_git(repo, "fetch", "--no-tags", remote, "refs/heads/%s" % branch)
    exists = _run_git(
        repo, "cat-file", "-e", "%s^{commit}" % expected_sha, check=False)
    if exists.returncode:
        raise GatewayError(
            "REMOTE_OBJECT_MISSING",
            "Fetch completed but authoritative commit cannot be read",
            {"expected_sha": expected_sha},
        )


def _load_policy_from_commit(repo, commit_sha):
    result = _run_git(
        repo, "show", "%s:%s" % (commit_sha, POLICY_RELATIVE_PATH),
        check=False)
    if result.returncode:
        raise GatewayError(
            "TRUSTED_POLICY_MISSING",
            "Authoritative main does not contain the Git scope policy",
            {
                "commit": commit_sha,
                "policy_path": POLICY_RELATIVE_PATH,
            },
        )
    try:
        policy = json.loads(result.stdout)
    except ValueError as exc:
        raise GatewayError(
            "TRUSTED_POLICY_INVALID",
            "Authoritative Git scope policy is not valid JSON",
            {"error": str(exc)},
        )
    _validate_policy(policy)
    return policy


def _load_local_policy(repo):
    path = os.path.join(repo, *POLICY_RELATIVE_PATH.split("/"))
    try:
        with open(path, "r", encoding="utf-8-sig") as stream:
            policy = json.load(stream)
    except (OSError, ValueError) as exc:
        raise GatewayError(
            "LOCAL_POLICY_INVALID",
            "Local Git scope policy cannot be read",
            {"path": path, "error": str(exc)},
        )
    _validate_policy(policy)
    return policy


def _validate_policy(policy):
    if not isinstance(policy, dict):
        raise GatewayError("POLICY_INVALID", "Policy root must be an object")
    if policy.get("schema") != "git-scope-policy@1.0.0":
        raise GatewayError(
            "POLICY_SCHEMA_UNSUPPORTED",
            "Unsupported Git scope policy schema",
            {"schema": policy.get("schema")},
        )
    if policy.get("integration_branch") != "main":
        raise GatewayError(
            "POLICY_BRANCH_INVALID",
            "Single-main gateway requires integration_branch=main")
    if policy.get("remote") != REMOTE_NAME:
        raise GatewayError(
            "POLICY_REMOTE_INVALID",
            "Single-main gateway requires remote=origin")
    if policy.get("policy_path") != POLICY_RELATIVE_PATH:
        raise GatewayError(
            "POLICY_PATH_INVALID",
            "Policy path does not match the compiled trust anchor",
            {
                "expected": POLICY_RELATIVE_PATH,
                "actual": policy.get("policy_path"),
            },
        )
    actors = policy.get("actors")
    if not isinstance(actors, dict) or not actors:
        raise GatewayError(
            "POLICY_ACTORS_MISSING", "Policy must define actors")
    for actor_id, actor in actors.items():
        if not isinstance(actor, dict):
            raise GatewayError(
                "POLICY_ACTOR_INVALID",
                "Actor policy must be an object",
                {"actor_id": actor_id},
            )
        paths = actor.get("write_paths")
        if not isinstance(paths, list):
            raise GatewayError(
                "POLICY_PATHS_INVALID",
                "Actor write_paths must be a list",
                {"actor_id": actor_id},
            )
        role = actor.get("role")
        if role not in (
                "project_writer", "modifier", "read_only",
                "git_coordinator"):
            raise GatewayError(
                "POLICY_ROLE_INVALID",
                "Actor role is not recognized",
                {"actor_id": actor_id, "role": role},
            )
        for path in paths:
            _normalize_path(path)
        if role == "project_writer":
            project_id = actor.get("project_id")
            if (
                    not isinstance(project_id, str)
                    or not project_id
                    or "/" in project_id
                    or "\\" in project_id
                    or project_id in (".", "..")):
                raise GatewayError(
                    "POLICY_PROJECT_INVALID",
                    "Project writer must bind one simple project id",
                    {"actor_id": actor_id, "project_id": project_id},
                )
            project_path = actor.get("project_path")
            if (
                    not isinstance(project_path, str)
                    or not project_path
                    or project_path.startswith("/")
                    or ".." in project_path.replace("\\", "/").split("/")):
                raise GatewayError(
                    "POLICY_PROJECT_PATH_INVALID",
                    "Project writer must bind one project directory",
                    {
                        "actor_id": actor_id,
                        "project_path": project_path,
                    },
                )
            project_prefix = _normalize_path(project_path)
            if (
                    not project_prefix.startswith("projects/")
                    or project_prefix.endswith("/**")):
                raise GatewayError(
                    "POLICY_PROJECT_PATH_INVALID",
                    "Project writer must bind one project directory",
                    {
                        "actor_id": actor_id,
                        "project_path": actor.get("project_path"),
                    },
                )
            denied = [
                path for path in paths
                if not (
                    _normalize_path(path) == project_prefix
                    or _normalize_path(path).startswith(
                        project_prefix + "/"))
            ]
            if denied:
                raise GatewayError(
                    "POLICY_PROJECT_SCOPE_INVALID",
                    "Project writer paths must stay inside its project",
                    {
                        "actor_id": actor_id,
                        "project_id": project_id,
                        "project_path": project_prefix,
                        "denied_paths": denied,
                    },
                )
            if actor.get("require_task_id") is not True:
                raise GatewayError(
                    "POLICY_TASK_BINDING_REQUIRED",
                    "Project writers must require a Task ID",
                    {"actor_id": actor_id},
                )
        if role in ("modifier", "read_only"):
            if actor.get("can_commit") or actor.get("can_publish"):
                raise GatewayError(
                    "POLICY_ROLE_CAPABILITY_INVALID",
                    "Modifier/read-only actors cannot commit or publish",
                    {"actor_id": actor_id, "role": role},
                )
        if role == "read_only" and paths:
            raise GatewayError(
                "POLICY_READ_ONLY_SCOPE_INVALID",
                "Read-only actor cannot have write paths",
                {"actor_id": actor_id},
            )
    default = policy.get("default_actor")
    if not isinstance(default, dict):
        raise GatewayError(
            "POLICY_DEFAULT_ACTOR_INVALID",
            "Policy must define a default actor object")
    if (
            default.get("role") != "read_only"
            or default.get("write_paths")
            or default.get("can_commit")
            or default.get("can_publish")):
        raise GatewayError(
            "POLICY_DEFAULT_ACTOR_UNSAFE",
            "Unknown actors must default to read-only")


def _actor(policy, actor_id):
    actors = policy.get("actors") or {}
    if actor_id in actors:
        result = dict(actors[actor_id])
        result["actor_id"] = actor_id
        return result
    default = dict(policy.get("default_actor") or {})
    default["actor_id"] = actor_id
    return default


def _resolve_actor_id(requested):
    actor_id = requested or os.environ.get("ACP_GIT_ACTOR_ID")
    if not actor_id:
        raise GatewayError(
            "ACTOR_ID_REQUIRED",
            "Set ACP_GIT_ACTOR_ID or pass --actor-id")
    if not all(
            character.isalnum() or character in "._-"
            for character in actor_id):
        raise GatewayError(
            "ACTOR_ID_INVALID",
            "Actor id may contain letters, digits, dot, underscore and hyphen")
    return actor_id


def _is_allowed(path, patterns):
    normalized = _normalize_path(path)
    for pattern in patterns:
        candidate = _normalize_path(pattern)
        if candidate == "**":
            return True
        if candidate.endswith("/**"):
            prefix = candidate[:-3].rstrip("/")
            if normalized == prefix or normalized.startswith(prefix + "/"):
                return True
        if fnmatch.fnmatchcase(normalized, candidate):
            return True
    return False


def _require_action(actor, key):
    if actor.get(key) is not True:
        raise GatewayError(
            "ACTION_NOT_AUTHORIZED",
            "Actor is not authorized for this Git gateway action",
            {
                "actor_id": actor.get("actor_id"),
                "role": actor.get("role"),
                "required_permission": key,
            },
        )


def _require_task(repo, actor, task_id):
    if actor.get("require_task_id") and not task_id:
        raise GatewayError(
            "TASK_ID_REQUIRED",
            "This actor must bind Git writes to a Task ID",
            {"actor_id": actor.get("actor_id")},
        )
    if not actor.get("require_task_id"):
        return None
    if not all(
            character.isalnum() or character in "._-"
            for character in task_id):
        raise GatewayError(
            "TASK_ID_INVALID",
            "Task ID may contain letters, digits, dot, underscore and hyphen",
            {"task_id": task_id},
        )
    project_path = _normalize_path(actor.get("project_path"))
    tasks_root = os.path.join(
        repo, *project_path.split("/"), "tasks")
    candidates = []
    for state in GIT_ELIGIBLE_TASK_STATES:
        state_root = os.path.join(tasks_root, state)
        if not os.path.isdir(state_root):
            continue
        for current_root, _, filenames in os.walk(state_root):
            for suffix in (".yaml", ".yml"):
                if task_id + suffix in filenames:
                    candidates.append(os.path.join(
                        current_root, task_id + suffix))
    if len(candidates) != 1:
        raise GatewayError(
            "TASK_NOT_FOUND_OR_ELIGIBLE",
            "Task ID must resolve once in an eligible project task state",
            {
                "actor_id": actor.get("actor_id"),
                "project_id": actor.get("project_id"),
                "task_id": task_id,
                "eligible_states": list(GIT_ELIGIBLE_TASK_STATES),
                "matches": [
                    os.path.relpath(path, repo).replace("\\", "/")
                    for path in candidates
                ],
            },
        )
    return candidates[0]


def _head(repo):
    return _run_git(repo, "rev-parse", "HEAD").stdout.strip()


def _branch(repo):
    result = _run_git(
        repo, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    return result.stdout.strip() if result.returncode == 0 else "DETACHED"


def _require_attached_branch(repo):
    branch = _branch(repo)
    if branch == "DETACHED":
        raise GatewayError(
            "DETACHED_HEAD",
            "Governed Git writes require an attached local worktree branch")
    return branch


def _status_paths(repo):
    paths = set()
    commands = (
        ("diff", "--name-only", "-z"),
        ("diff", "--cached", "--name-only", "-z"),
        ("ls-files", "--others", "--exclude-standard", "-z"),
    )
    for command in commands:
        output = _run_git(repo, *command).stdout
        paths.update(
            _normalize_path(item)
            for item in output.split("\0") if item)
    return sorted(paths)


def _ensure_paths_allowed(paths, actor, context):
    patterns = actor.get("write_paths") or []
    denied = [
        path for path in paths
        if not _is_allowed(path, patterns)
    ]
    if denied:
        raise GatewayError(
            "PATH_SCOPE_VIOLATION",
            "Git operation includes paths outside the actor write scope",
            {
                "actor_id": actor.get("actor_id"),
                "project_id": actor.get("project_id"),
                "context": context,
                "denied_paths": denied,
                "write_paths": patterns,
            },
        )


def _is_ancestor(repo, older, newer):
    result = _run_git(
        repo, "merge-base", "--is-ancestor", older, newer, check=False)
    return result.returncode == 0


def _commits_between(repo, base, head):
    output = _run_git(
        repo, "rev-list", "--reverse", "%s..%s" % (base, head)).stdout
    return [line.strip() for line in output.splitlines() if line.strip()]


def _paths_between(repo, base, head):
    output = _run_git(
        repo, "diff", "--name-only", "-z",
        "%s..%s" % (base, head)).stdout
    return sorted({
        _normalize_path(path)
        for path in output.split("\0") if path
    })


def _commit_paths(repo, commit):
    output = _run_git(
        repo, "diff-tree", "--root", "--no-commit-id",
        "--name-only", "-r", "-z", commit).stdout
    return sorted(
        {_normalize_path(item) for item in output.split("\0") if item})


def _validate_commit_range(repo, base, head, actor):
    commits = _commits_between(repo, base, head)
    if not commits:
        raise GatewayError(
            "NOTHING_TO_PUBLISH",
            "Local HEAD has no commits beyond authoritative main")
    all_paths = set()
    commit_reports = []
    for commit in commits:
        parents = _run_git(
            repo, "show", "-s", "--format=%P", commit).stdout.split()
        if len(parents) > 1:
            raise GatewayError(
                "MERGE_COMMIT_REJECTED",
                "Project-scoped publication requires linear commits",
                {"commit": commit, "parents": parents},
            )
        paths = _commit_paths(repo, commit)
        _ensure_paths_allowed(paths, actor, "commit:%s" % commit)
        all_paths.update(paths)
        commit_reports.append({"commit": commit, "paths": paths})
    diff_check = _run_git(
        repo, "diff", "--check", "%s..%s" % (base, head), check=False)
    if diff_check.returncode:
        raise GatewayError(
            "DIFF_CHECK_FAILED",
            "Git whitespace/error check failed",
            {"output": (diff_check.stdout + diff_check.stderr).strip()},
        )
    return {
        "commits": commit_reports,
        "paths": sorted(all_paths),
    }


def _audit(repo, event):
    base = os.environ.get("ACP_GIT_AUDIT_DIR")
    if not base:
        local = os.environ.get("LOCALAPPDATA")
        base = os.path.join(
            local or os.path.expanduser("~"),
            "AI-Creative-Platform", "git-audit")
    os.makedirs(base, exist_ok=True)
    repo_id = hashlib.sha256(
        os.path.normcase(os.path.abspath(repo)).encode("utf-8")
    ).hexdigest()[:12]
    path = os.path.join(base, "%s.jsonl" % repo_id)
    body = dict(event)
    body["schema"] = "git-scope-audit@1.0.0"
    body["repository"] = repo
    body["generated_at"] = datetime.datetime.now(
        datetime.timezone.utc).isoformat()
    with open(path, "a", encoding="utf-8") as stream:
        stream.write(json.dumps(body, ensure_ascii=False) + "\n")
    return path


def _trusted_context(repo, actor_id):
    _load_local_policy(repo)
    remote = REMOTE_NAME
    branch = INTEGRATION_BRANCH
    remote_sha = _remote_tip(repo, remote, branch)
    _fetch_authoritative(repo, remote, branch, remote_sha)
    policy = _load_policy_from_commit(repo, remote_sha)
    return policy, _actor(policy, actor_id), remote, branch, remote_sha


def command_status(args):
    repo = _repo_root(args.repo)
    actor_id = _resolve_actor_id(args.actor_id)
    policy, actor, remote, branch, remote_sha = _trusted_context(
        repo, actor_id)
    return {
        "decision": "ALLOW_READ",
        "action": "status",
        "actor": actor,
        "repository": repo,
        "local_branch": _branch(repo),
        "local_head": _head(repo),
        "remote": remote,
        "remote_branch": branch,
        "remote_head": remote_sha,
        "dirty_paths": _status_paths(repo),
        "policy_schema": policy.get("schema"),
    }


def command_sync(args):
    repo = _repo_root(args.repo)
    _require_attached_branch(repo)
    actor_id = _resolve_actor_id(args.actor_id)
    policy, actor, remote, branch, remote_sha = _trusted_context(
        repo, actor_id)
    _require_action(actor, "can_sync")
    dirty = _status_paths(repo)
    if dirty:
        raise GatewayError(
            "DIRTY_WORKTREE",
            "Sync is refused while the worktree has uncommitted changes",
            {"dirty_paths": dirty},
        )
    local_sha = _head(repo)
    state = "ALREADY_CURRENT"
    if local_sha != remote_sha:
        if _is_ancestor(repo, local_sha, remote_sha):
            _run_git(repo, "merge", "--ff-only", remote_sha)
            state = "FAST_FORWARDED"
        elif _is_ancestor(repo, remote_sha, local_sha):
            state = "LOCAL_AHEAD"
        else:
            common_base = _run_git(
                repo, "merge-base", local_sha, remote_sha).stdout.strip()
            local_validation = _validate_commit_range(
                repo, common_base, local_sha, actor)
            remote_paths = _paths_between(repo, common_base, remote_sha)
            overlap = sorted(
                set(local_validation["paths"]).intersection(remote_paths))
            if overlap:
                raise GatewayError(
                    "DIVERGED_PATH_OVERLAP",
                    "Local scoped commits overlap paths changed on main",
                    {
                        "local_head": local_sha,
                        "remote_head": remote_sha,
                        "common_base": common_base,
                        "overlap_paths": overlap,
                    },
                )
            rebase = _run_git(
                repo, "rebase", "--onto", remote_sha, common_base,
                check=False)
            if rebase.returncode:
                _run_git(repo, "rebase", "--abort", check=False)
                restored = _head(repo)
                if restored != local_sha:
                    raise GatewayError(
                        "SCOPED_REBASE_ROLLBACK_FAILED",
                        "Scoped rebase failed and original HEAD was not restored",
                        {
                            "expected_head": local_sha,
                            "actual_head": restored,
                        },
                    )
                raise GatewayError(
                    "SCOPED_REBASE_CONFLICT",
                    "Scoped rebase conflicted and was rolled back",
                    {
                        "local_head": local_sha,
                        "remote_head": remote_sha,
                        "stdout": rebase.stdout.strip(),
                        "stderr": rebase.stderr.strip(),
                    },
                )
            rebased_head = _head(repo)
            _validate_commit_range(
                repo, remote_sha, rebased_head, actor)
            state = "SCOPED_REBASED"
    final_head = _head(repo)
    audit_path = _audit(repo, {
        "actor_id": actor_id,
        "project_id": actor.get("project_id"),
        "action": "sync",
        "decision": "ALLOW",
        "state": state,
        "before": local_sha,
        "after": final_head,
        "remote_head": remote_sha,
    })
    return {
        "decision": "ALLOW",
        "action": "sync",
        "state": state,
        "actor": actor,
        "local_head": final_head,
        "remote_head": remote_sha,
        "audit_path": audit_path,
        "policy_schema": policy.get("schema"),
    }


def command_commit(args):
    repo = _repo_root(args.repo)
    _require_attached_branch(repo)
    actor_id = _resolve_actor_id(args.actor_id)
    policy, actor, remote, branch, remote_sha = _trusted_context(
        repo, actor_id)
    _require_action(actor, "can_commit")
    _require_task(repo, actor, args.task_id)
    dirty = _status_paths(repo)
    if not dirty:
        raise GatewayError("NOTHING_TO_COMMIT", "Worktree has no changes")
    _ensure_paths_allowed(dirty, actor, "worktree")
    requested = sorted({_normalize_path(path) for path in args.path})
    if not requested:
        raise GatewayError(
            "COMMIT_PATH_REQUIRED",
            "Commit requires one or more explicit --path values")
    _ensure_paths_allowed(requested, actor, "requested_paths")
    for path in requested:
        absolute = os.path.abspath(os.path.join(repo, path))
        if os.path.commonpath([repo, absolute]) != repo:
            raise GatewayError(
                "COMMIT_PATH_ESCAPES_REPOSITORY",
                "Requested path escapes the repository",
                {"path": path},
            )
    _run_git(repo, "add", "-A", "--", *requested)
    staged_output = _run_git(
        repo, "diff", "--cached", "--name-only", "-z").stdout
    staged = sorted({
        _normalize_path(path)
        for path in staged_output.split("\0") if path
    })
    if not staged:
        raise GatewayError(
            "NOTHING_STAGED", "Requested paths produced no staged changes")
    _ensure_paths_allowed(staged, actor, "staged")
    diff_check = _run_git(repo, "diff", "--cached", "--check", check=False)
    if diff_check.returncode:
        raise GatewayError(
            "DIFF_CHECK_FAILED",
            "Staged Git whitespace/error check failed",
            {"output": (diff_check.stdout + diff_check.stderr).strip()},
        )
    _run_git(repo, "commit", "-m", args.message)
    commit_sha = _head(repo)
    audit_path = _audit(repo, {
        "actor_id": actor_id,
        "project_id": actor.get("project_id"),
        "task_id": args.task_id,
        "action": "commit",
        "decision": "ALLOW",
        "commit": commit_sha,
        "paths": staged,
        "remote_head_at_authorization": remote_sha,
    })
    return {
        "decision": "ALLOW",
        "action": "commit",
        "actor": actor,
        "commit": commit_sha,
        "paths": staged,
        "remote_head_at_authorization": remote_sha,
        "audit_path": audit_path,
        "policy_schema": policy.get("schema"),
    }


def command_publish(args):
    repo = _repo_root(args.repo)
    _require_attached_branch(repo)
    actor_id = _resolve_actor_id(args.actor_id)
    policy, actor, remote, branch, remote_sha = _trusted_context(
        repo, actor_id)
    _require_action(actor, "can_publish")
    _require_task(repo, actor, args.task_id)
    dirty = _status_paths(repo)
    if dirty:
        raise GatewayError(
            "DIRTY_WORKTREE",
            "Publish requires a clean worktree",
            {"dirty_paths": dirty},
        )
    local_sha = _head(repo)
    if not _is_ancestor(repo, remote_sha, local_sha):
        raise GatewayError(
            "NON_FAST_FORWARD_BASE",
            "Local HEAD is not based on authoritative remote main",
            {
                "local_head": local_sha,
                "remote_head": remote_sha,
                "resolution": (
                    "Do not force, reset or delete refs. Sync before editing, "
                    "or return the divergence to the Git coordinator."),
            },
        )
    validation = _validate_commit_range(
        repo, remote_sha, local_sha, actor)
    push = _run_git(
        repo, "push", remote,
        "%s:refs/heads/%s" % (local_sha, branch), check=False)
    if push.returncode:
        raise GatewayError(
            "REMOTE_CAS_REJECTED",
            "Remote main changed or rejected the scoped publication",
            {
                "local_head": local_sha,
                "authorized_remote_head": remote_sha,
                "stdout": push.stdout.strip(),
                "stderr": push.stderr.strip(),
                "resolution": (
                    "Query the new remote main. Never force push. If another "
                    "project advanced main, sync/rebase only through an "
                    "approved coordinator workflow."),
            },
        )
    remote_after = _remote_tip(repo, remote, branch)
    if remote_after != local_sha:
        raise GatewayError(
            "REMOTE_READBACK_MISMATCH",
            "Push returned success but remote read-back differs",
            {"expected": local_sha, "actual": remote_after},
        )
    audit_path = _audit(repo, {
        "actor_id": actor_id,
        "project_id": actor.get("project_id"),
        "task_id": args.task_id,
        "action": "publish",
        "decision": "ALLOW",
        "before": remote_sha,
        "after": local_sha,
        "paths": validation["paths"],
        "commits": [
            item["commit"] for item in validation["commits"]
        ],
    })
    return {
        "decision": "ALLOW",
        "action": "publish",
        "actor": actor,
        "remote": remote,
        "remote_branch": branch,
        "before": remote_sha,
        "after": local_sha,
        "paths": validation["paths"],
        "commits": validation["commits"],
        "audit_path": audit_path,
        "policy_schema": policy.get("schema"),
    }


def command_validate_policy(args):
    repo = _repo_root(args.repo)
    policy = _load_local_policy(repo)
    return {
        "decision": "PASS",
        "action": "validate-policy",
        "schema": policy.get("schema"),
        "integration_branch": policy.get("integration_branch"),
        "actors": sorted((policy.get("actors") or {}).keys()),
    }


def build_parser():
    parser = argparse.ArgumentParser(
        prog="platform git",
        description="Project-scoped single-main Git gateway")
    sub = parser.add_subparsers(dest="action", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", default=None)
    common.add_argument("--actor-id", default=None)

    sub.add_parser("status", parents=[common])
    sub.add_parser("sync", parents=[common])

    commit = sub.add_parser("commit", parents=[common])
    commit.add_argument("--task-id", default=None)
    commit.add_argument("--message", required=True)
    commit.add_argument("--path", action="append", default=[])

    publish = sub.add_parser("publish", parents=[common])
    publish.add_argument("--task-id", default=None)

    validate = sub.add_parser("validate-policy")
    validate.add_argument("--repo", default=None)
    return parser


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args()
    handlers = {
        "status": command_status,
        "sync": command_sync,
        "commit": command_commit,
        "publish": command_publish,
        "validate-policy": command_validate_policy,
    }
    try:
        result = handlers[args.action](args)
        result["schema"] = SCHEMA
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except GatewayError as exc:
        body = {
            "schema": SCHEMA,
            "decision": "BLOCK",
            "code": exc.code,
            "message": str(exc),
            "details": exc.details,
        }
        try:
            repo = _repo_root(getattr(args, "repo", None))
            audit_path = _audit(repo, {
                "actor_id": (
                    getattr(args, "actor_id", None)
                    or os.environ.get("ACP_GIT_ACTOR_ID")),
                "task_id": getattr(args, "task_id", None),
                "action": getattr(args, "action", None),
                "decision": "BLOCK",
                "code": exc.code,
                "message": str(exc),
            })
            body["audit_path"] = audit_path
        except Exception:
            pass
        print(json.dumps(body, ensure_ascii=False, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
