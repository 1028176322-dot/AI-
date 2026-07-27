# -*- coding: utf-8 -*-
"""
统一授权入口 + 分操作策略（纲要 §2.8 / §10）。

``authorization-policy.schema.yaml`` 是分操作检查策略的**唯一 SSOT**：
本模块只负责「检查如何实现」，而「每个 operation 跑哪些检查」完全由契约驱动。
写操作（apply/rollback/publish/candidate_create/chapter_write）授权成功时，
经 ``capability.issue`` 发放多资源、单次使用、签名的令牌。
"""
import hashlib
import json
import os
import time
from dataclasses import dataclass, field

try:
    from _yaml_lite import load as _yload
except Exception:  # pragma: no cover - fallback 仅当平台解析器不可用
    try:
        from yaml import safe_load as _yload
    except Exception:
        _yload = None

SCHEMA_DIR = os.path.normpath(os.path.join(
    os.path.dirname(__file__), "..", "..", "core", "learning", "schemas"))

WRITE_OPERATIONS = {"apply", "rollback", "publish", "candidate_create", "chapter_write"}
VALID_ROLES = {"writer", "reviewer", "architect", "operator", "author"}


# --------------------------------------------------------------------------
# 上下文（authorize 的输入）
# --------------------------------------------------------------------------
@dataclass
class TaskContext:
    task_id: str = ""
    actor_id: str = ""
    actor_role: str = ""
    executor_id: str = ""
    executor_role: str = ""
    creator_can_assign_role: bool = True
    template_valid: bool = True
    state: str = "CREATED"
    session_id: str = ""
    session_ready: bool = True
    subagent_policy: str = "denied"   # 风格任务默认 denied
    lease_owner: str = ""
    lease_expires_at: float = 0.0
    completion_authority: str = "operator"
    outputs_valid: bool = True
    outputs_consistent: bool = True
    dependency_binding: bool = True


# --------------------------------------------------------------------------
# 文件系统助手（含安全解析：拒符号链接与越界）
# --------------------------------------------------------------------------
def safe_resolve(path, base=None):
    rp = os.path.realpath(path)
    if os.path.islink(path):
        raise PermissionError("symlink not allowed: %s" % path)
    if base:
        bb = os.path.realpath(base)
        if not (rp == bb or rp.startswith(bb + os.sep)):
            raise PermissionError("path escapes base: %s" % path)
    return rp


def _sha256_file(path):
    if not os.path.exists(path) or os.path.islink(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class RealFS:
    def sha256(self, path):
        return _sha256_file(path)


def _path_within(path, prefix):
    p = path.replace("\\", "/")
    pre = prefix.replace("\\", "/")
    return p == pre or p.startswith(pre + "/")


# --------------------------------------------------------------------------
# 检查断言（每个返回一个 (ok, reason) 元组）
# --------------------------------------------------------------------------
def _lease_valid(ctx):
    return ctx.lease_expires_at == 0.0 or ctx.lease_expires_at > time.time()


def chk_session_ready(ctx, res, env):
    return (ctx.session_ready is True, "session not ready")


def chk_subagent_policy_denied(ctx, res, env):
    return (ctx.subagent_policy == "denied", "subagent policy must be denied for style tasks")


def chk_creator_can_assign_role(ctx, res, env):
    if not ctx.creator_can_assign_role:
        return (False, "creator cannot assign role")
    if ctx.executor_role not in VALID_ROLES:
        return (False, "invalid executor role: %s" % ctx.executor_role)
    return (True, "")


def chk_template_valid(ctx, res, env):
    return (ctx.template_valid, "template invalid")


def chk_actor_matches_executor(ctx, res, env):
    return (ctx.actor_id == ctx.executor_id, "actor != executor")


def chk_claimable_state(ctx, res, env):
    return (ctx.state in ("CREATED", "OPEN"), "state not claimable: %s" % ctx.state)


def chk_lease_owner(ctx, res, env):
    if ctx.actor_id != ctx.lease_owner:
        return (False, "not lease owner")
    if not _lease_valid(ctx):
        return (False, "lease expired")
    return (True, "")


def chk_role_match(ctx, res, env):
    return (ctx.actor_role == ctx.executor_role, "role mismatch")


def chk_runnable_state(ctx, res, env):
    return (ctx.state == "CLAIMED", "state not runnable: %s" % ctx.state)


def chk_completion_authority(ctx, res, env):
    return (ctx.actor_role == ctx.completion_authority, "no completion authority")


def chk_completable_state(ctx, res, env):
    return (ctx.state == "RUNNING", "state not completable: %s" % ctx.state)


def chk_resumable_state(ctx, res, env):
    return (ctx.state in ("RUNNING", "PAUSED"), "state not resumable: %s" % ctx.state)


def chk_outputs_valid(ctx, res, env):
    return (ctx.outputs_valid, "outputs invalid")


def chk_outputs_consistent(ctx, res, env):
    return (ctx.outputs_consistent, "outputs inconsistent")


def _realpath(p):
    try:
        return os.path.realpath(p)
    except Exception:
        return p


def _within(rp, base):
    return rp == base or rp.startswith(base + os.sep)


def chk_reviewer_role(ctx, res, env):
    # 审批操作要求执行角色具 reviewer/author 权威（拒绝 writer/operator 自批）。
    return (ctx.actor_role in ("reviewer", "author"),
            "actor lacks reviewer authority: %s" % ctx.actor_role)


def chk_candidate_path_permission(ctx, res, env):
    # canonical_path 为 realpath（绝对）；候选稿须位于 analysis/style 且不得在 chapters/ 下。
    root = env.get("root")
    for r in (res or []):
        p = r.get("canonical_path", "")
        if root:
            rp = _realpath(p)
            analysis = _realpath(os.path.join(root, "analysis", "style"))
            chapters = _realpath(os.path.join(root, "chapters"))
            if not _within(rp, analysis):
                return (False, "candidate path not under analysis/style: %s" % p)
            if _within(rp, chapters):
                return (False, "candidate path under chapters forbidden: %s" % p)
        else:
            if not _path_within(p, "analysis/style") or _path_within(p, "chapters"):
                return (False, "candidate path not permitted: %s" % p)
    return (True, "")


def chk_APPLY_READY(ctx, res, env):
    return (ctx.state == "APPLY_READY", "state != APPLY_READY: %s" % ctx.state)


def chk_ROLLBACK_READY(ctx, res, env):
    return (ctx.state == "ROLLBACK_READY", "state != ROLLBACK_READY: %s" % ctx.state)


def chk_PUBLISH_READY(ctx, res, env):
    return (ctx.state == "PUBLISH_READY", "state != PUBLISH_READY: %s" % ctx.state)


def chk_dependency_binding(ctx, res, env):
    return (ctx.dependency_binding, "dependency binding missing")


def chk_path_permission(ctx, res, env):
    # 仅校验「实际写目标」(role=target) 是否位于 chapters/drafts 或 chapters/approved 下；
    # source / candidate_or_backup 等引用资源由各自哈希检查约束，不在此处限制路径。
    root = env.get("root")
    targets = [r for r in (res or []) if r.get("role") == "target"]
    if root:
        drafts = _realpath(os.path.join(root, "chapters", "drafts"))
        approved = _realpath(os.path.join(root, "chapters", "approved"))
        for t in targets:
            rp = _realpath(t.get("canonical_path", ""))
            if not (_within(rp, drafts) or _within(rp, approved)):
                return (False, "path not permitted: %s" % t.get("canonical_path"))
        return (True, "")
    for t in targets:
        p = t.get("canonical_path", "")
        if not (_path_within(p, "chapters/drafts") or _path_within(p, "chapters/approved")):
            return (False, "path not permitted: %s" % p)
    return (True, "")


def _hash_check(resources, role, env, allow_absent):
    fs = env.get("fs") or RealFS()
    for r in (resources or []):
        if r.get("role") != role:
            continue
        expected = r.get("expected_sha256")
        path = r.get("canonical_path")
        actual = fs.sha256(path) if path else None
        if expected in (None, "absent"):
            if allow_absent:
                return (True, "")
            return (actual is None, "resource absent but expected present")
        if actual is None:
            return (False, "%s file missing" % role)
        return (actual == expected, "%s hash mismatch" % role)
    return (False, "resource role %s not found" % role)


def chk_source_hash_equal(ctx, res, env):
    return _hash_check(res, "source", env, allow_absent=False)


def chk_target_hash_equal(ctx, res, env):
    return _hash_check(res, "target", env, allow_absent=True)


def chk_applied_hash_equal(ctx, res, env):
    return _hash_check(res, "source", env, allow_absent=False)


def chk_backup_hash_present(ctx, res, env):
    for r in (res or []):
        if r.get("role") == "source":
            return (True, "")
    return (False, "backup (source) resource missing")


CHECKS = {
    "session_ready": chk_session_ready,
    "subagent_policy_denied": chk_subagent_policy_denied,
    "creator_can_assign_role": chk_creator_can_assign_role,
    "template_valid": chk_template_valid,
    "actor_matches_executor": chk_actor_matches_executor,
    "claimable_state": chk_claimable_state,
    "lease_owner": chk_lease_owner,
    "role_match": chk_role_match,
    "runnable_state": chk_runnable_state,
    "completion_authority": chk_completion_authority,
    "completable_state": chk_completable_state,
    "outputs_valid": chk_outputs_valid,
    "resumable_state": chk_resumable_state,
    "outputs_consistent": chk_outputs_consistent,
    "candidate_path_permission": chk_candidate_path_permission,
    "APPLY_READY": chk_APPLY_READY,
    "ROLLBACK_READY": chk_ROLLBACK_READY,
    "PUBLISH_READY": chk_PUBLISH_READY,
    "dependency_binding": chk_dependency_binding,
    "path_permission": chk_path_permission,
    "reviewer_role": chk_reviewer_role,
    "source_hash_equal": chk_source_hash_equal,
    "target_hash_equal": chk_target_hash_equal,
    "applied_hash_equal": chk_applied_hash_equal,
    "backup_hash_present": chk_backup_hash_present,
}


# --------------------------------------------------------------------------
# 策略加载
# --------------------------------------------------------------------------
def load_policy(policy_path=None):
    path = policy_path or os.path.join(SCHEMA_DIR, "authorization-policy.schema.yaml")
    if _yload is None:
        raise RuntimeError("no yaml loader available")
    with open(path, "r", encoding="utf-8") as f:
        return _yload(f.read())


def policy_sha256(policy):
    return hashlib.sha256(
        json.dumps(policy.get("operation_checks", []), sort_keys=True,
                   ensure_ascii=False).encode("utf-8")).hexdigest()


class AuthResult:
    def __init__(self, allowed, operation, failed, capability=None):
        self.allowed = allowed
        self.operation = operation
        self.failed = failed
        self.capability = capability

    def to_dict(self):
        return {
            "allowed": self.allowed,
            "operation": self.operation,
            "failed_checks": self.failed,
            "capability": self.capability,
        }


# --------------------------------------------------------------------------
# 授权器（统一入口）
# --------------------------------------------------------------------------
class Authorizer:
    def __init__(self, policy_path=None, capability_key=None, issuer=None):
        self.policy = load_policy(policy_path)
        self.checks_map = self.policy.get("operation_checks", [])
        self.common_checks = self.policy.get("common_checks", ["session_ready", "subagent_policy_denied"])
        self.capability_key = capability_key  # bytes | None
        self.issuer = issuer

    def _checks_for(self, operation):
        specific = []
        for row in self.checks_map:
            if row.get("operation") == operation:
                specific = list(row.get("checks", []))
                break
        return list(self.common_checks) + specific

    def authorize(self, operation, ctx, resources=None, env=None):
        env = env or {}
        if operation not in {r["operation"] for r in self.checks_map}:
            return AuthResult(False, operation, [{"check": "<operation>", "ok": False,
                                                  "reason": "unknown operation: %s" % operation}])
        failed = []
        for name in self._checks_for(operation):
            fn = CHECKS.get(name)
            if fn is None:
                failed.append({"check": name, "ok": False, "reason": "unknown check"})
                continue
            ok, reason = fn(ctx, resources, env)
            if not ok:
                failed.append({"check": name, "ok": False, "reason": reason})
        if failed:
            return AuthResult(False, operation, failed)
        cap = None
        if operation in WRITE_OPERATIONS and self.issuer is not None and self.capability_key:
            cap = self.issuer.issue(
                task_id=ctx.task_id,
                session_id=ctx.session_id,
                actor_id=ctx.actor_id,
                operation=operation,
                resources=resources or [],
                policy_sha256=policy_sha256(self.policy),
                key=self.capability_key,
            )
        return AuthResult(True, operation, [], capability=cap)
