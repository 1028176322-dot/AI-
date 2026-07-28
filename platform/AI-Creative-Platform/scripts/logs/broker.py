# -*- coding: utf-8 -*-
"""
受控写 Broker（纲要 §2.4 / §2.8 / §2.10，实施任务 #19）。

隔离模型（#16 选定，#18 基础设施之上）
-------------------------------------
- 独立受控写 Broker 进程持有**唯一**签名密钥；普通任务进程（TaskRunner，对 chapters/ 仅读）
  无法直接写，只能通过 localhost 受限 IPC 向 Broker 发起「授权 + 写」请求。
- Broker 在密钥侧统一：``authorize()`` 签发多资源单次 capability，Writer 校验
  capability(签名/nonce/single_use) + 资源 CAS 哈希 + 路径白名单 + 拒符号链接/穿越，
  原子写，消费 capability，记不可变事件。

密钥托管：``BrokerKeyVault`` 只存在于 Broker 进程；普通任务进程（BrokerClient）拿不到密钥，
因此既无法伪造 capability，也无法直接产生合法事件——即便拿到日志文件也无法补写。

OS 层（Windows NTFS ACL 双身份）由 ``apply_ntfs_acl`` 辅助落实（默认 dry-run，安全，
避免测试环境误改 ACL）；真实《道法百年》项目落地时由运维以管理员执行。
"""
import json
import datetime
import hashlib
import hmac
import os
import socket
import subprocess
import sys
import threading
import time
import uuid

# 同目录模块（scripts/logs 已在 sys.path）
from authorize import Authorizer, TaskContext, RealFS, safe_resolve  # noqa: E402
from capability import (issue, verify, verify_resources, consume,  # noqa: E402
                        CapabilityStore, load_required_roles)
from event_log import EventLog, KeyProvider, SigningKeyUnavailable  # noqa: E402

WRITE_OPS = {"apply", "rollback", "publish", "candidate_create", "chapter_write"}

STRICT_DEPENDENCY_ROLES = {
    "apply": {
        "protected_manifest", "style_guidance",
        "fidelity_report", "quality_report",
    },
    "rollback": {"final_regression"},
    "publish": {
        "protected_manifest", "style_guidance",
        "final_regression", "nkb_sync_proof", "outline",
        "chapter_review_report",
    },
}

# 受控根：仅这些目录下的 target 角色可被 Broker 写入
DEFAULT_ALLOW_ROOTS = {
    "chapters/drafts": ("chapters", "drafts"),
    "chapters/approved": ("chapters", "approved"),
    "analysis/style": ("analysis", "style"),
}


class BrokerError(Exception):
    """受控写被拒（授权失败 / capability 失效 / 路径越权 / CAS 冲突等）。"""


class PathEscalation(BrokerError):
    """写入路径越过白名单 / 符号链接 / 穿越。"""


# --------------------------------------------------------------------------
# 密钥金库（仅 Broker 持有）
# --------------------------------------------------------------------------
class BrokerKeyVault:
    def __init__(self, key=None, key_id="local-broker-1"):
        if key is None:
            env = os.environ.get("STYLE_BROKER_KEY")
            if env:
                try:
                    key = bytes.fromhex(env)
                except ValueError:
                    key = env.encode("utf-8")
        self.key = key if key is not None else os.urandom(32)
        self.key_id = key_id

    def key_bytes(self):
        return self.key

    def key_hex(self):
        return self.key.hex()


# --------------------------------------------------------------------------
# 受控写核心（密钥侧唯一写入口）
# --------------------------------------------------------------------------
class ControlledWriter:
    def __init__(self, root, key_vault=None, event_log=None, capability_store=None,
                 policy_path=None, allow_roots=None,
                 strict_dependencies=True):
        self.root = os.path.realpath(root)
        self.vault = key_vault or BrokerKeyVault()
        self.key = self.vault.key_bytes()
        self.event_log = event_log or EventLog(
            os.path.join(self.root, "runtime", "learning", "task-events.log"),
            KeyProvider(key=self.key))
        self.cap_store = capability_store or CapabilityStore(
            os.path.join(self.root, "runtime", "learning", "consumed-capabilities.log"))
        self.authorizer = Authorizer(policy_path=policy_path,
                                     capability_key=self.key, issuer=sys.modules[__name__])
        self.strict_dependencies = strict_dependencies
        self._commit_lock = threading.Lock()
        self.allow_roots = {}
        spec = allow_roots or DEFAULT_ALLOW_ROOTS
        for name, parts in spec.items():
            path = os.path.realpath(os.path.join(self.root, *parts))
            self.allow_roots[name] = path

    # -- 路径安全 ---------------------------------------------------------
    def _resolve_target(self, path):
        try:
            rp = safe_resolve(path)  # 拒符号链接 / 拒逃逸
        except PermissionError as e:
            raise PathEscalation(str(e))
        for base in self.allow_roots.values():
            if rp == base or rp.startswith(base + os.sep):
                return rp
        raise PathEscalation("path not within any allowed root: %s" % path)

    def _whitelist_target(self):
        return [self.allow_roots["chapters/drafts"], self.allow_roots["chapters/approved"]]

    # -- 唯一写入口 -------------------------------------------------------
    def request_write(self, operation, ctx, resources, content, actor_id=None,
                      session_id=None, task_id=None):
        """普通任务进程调用：经 authorize 签发 capability 后原子提交。"""
        actor_id = actor_id or ctx.actor_id
        task_id = task_id or ctx.task_id
        session_id = session_id or ctx.session_id
        res = self.authorizer.authorize(operation, ctx, resources=resources,
                                        env={"root": self.root, "fs": RealFS()})
        if not res.allowed:
            self.event_log.append("WRITE_DENIED", actor_id, task_id,
                                  operation=operation,
                                  result="denied:%s" % ",".join(f["check"] for f in res.failed))
            raise BrokerError("authorization denied: %s" % res.failed)
        return self._commit(res.capability, content, actor_id, session_id, task_id)

    def _commit(self, cap, content, actor_id, session_id, task_id):
        # Serialize verification, CAS and replacement to close the concurrent
        # check/use window.
        with self._commit_lock:
            return self._commit_once(
                cap, content, actor_id, session_id, task_id)

    def _commit_once(self, cap, content, actor_id, session_id, task_id):
        """凭 capability 提交一次写（capability 已由 Broker 签发）。"""
        # ① 令牌完整性
        ok, why = verify(cap, self.key, store=self.cap_store)
        if not ok:
            raise BrokerError("capability verify failed: %s" % why)
        if (
                cap.get("task_id") != task_id
                or cap.get("session_id") != session_id
                or cap.get("actor_id") != actor_id):
            raise BrokerError("capability identity binding mismatch")
        if self.strict_dependencies:
            roles = {
                item.get("role") for item in cap.get("resources") or []}
            missing_roles = sorted(
                STRICT_DEPENDENCY_ROLES.get(cap.get("operation"), set())
                - roles)
            if missing_roles:
                raise BrokerError(
                    "strict dependency resources missing: %s" %
                    ", ".join(missing_roles))
        # ② 资源 CAS（expected_sha256 齐验）
        ok2, why2 = verify_resources(cap, fs=RealFS())
        if not ok2:
            raise BrokerError("resource CAS failed: %s" % why2)
        # ③ 解析 + 白名单校验 target
        targets = [r for r in cap.get("resources", []) if r.get("role") == "target"]
        if not targets:
            raise BrokerError("capability has no target resource")
        rp = self._resolve_target(targets[0].get("canonical_path"))
        wl = self._whitelist_target()
        if not any(rp == b or rp.startswith(b + os.sep) for b in wl):
            raise PathEscalation("target not in writable whitelist: %s" % rp)
        # ④ CAS 预检（非 absent 的 target 须与当前哈希一致）
        expected = targets[0].get("expected_sha256")
        if expected not in (None, "absent"):
            cur = RealFS().sha256(rp)
            if cur is None:
                raise BrokerError("target missing before write: %s" % rp)
            if cur != expected:
                raise BrokerError("CAS conflict: current %s != expected %s" % (cur, expected))
        # ⑤ 原子写
        parent = os.path.dirname(rp)
        os.makedirs(parent, exist_ok=True)
        tmp = os.path.join(parent, ".tmp-%s" % uuid.uuid4().hex)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, rp)
        # ⑥ 消费 capability（single_use 防重放）
        consume(cap, self.cap_store)
        # ⑦ 不可变事件
        ev = self.event_log.append("WRITE", actor_id, task_id,
                                   operation=cap["operation"],
                                   capability_id=cap["capability_id"], result="ok")
        return {"event_id": ev["event_id"],
                "capability_id": cap["capability_id"],
                "target": rp}


# --------------------------------------------------------------------------
# localhost 受限 IPC（密钥不出 Broker）
# --------------------------------------------------------------------------
class BrokerServer:
    def __init__(
            self, writer, host="127.0.0.1", port=0, client_token=None,
            allow_legacy_test_context=False):
        self.writer = writer
        self.host = host
        self.port = port
        self._srv = None
        self._thread = None
        self.client_token = (
            client_token
            if client_token is not None
            else os.environ.get("STYLE_BROKER_CLIENT_TOKEN"))
        self.allow_legacy_test_context = allow_legacy_test_context

    def _authenticate_endpoint(self, msg):
        if not self.client_token:
            return
        supplied = str(msg.get("client_token") or "")
        if not hmac.compare_digest(
                supplied.encode("utf-8"),
                str(self.client_token).encode("utf-8")):
            raise BrokerError("restricted IPC endpoint authentication failed")

    def _trusted_context(self, msg):
        identity = msg.get("identity") or msg.get("ctx") or {}
        if self.allow_legacy_test_context:
            return _ctx_from_dict(identity)
        return load_trusted_context(
            self.writer.root,
            task_id=identity.get("task_id"),
            session_id=identity.get("session_id"),
            actor_id=identity.get("actor_id"))

    def _handle(self, conn):
        try:
            buf = b""
            conn.settimeout(5.0)
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                buf += chunk
                if b"\n" in buf:
                    break
            msg = json.loads(buf.decode("utf-8"))
            op = msg.get("op")
            if op == "status":
                # Loopback health check contains no task data or secrets.
                # Authorization and mutation operations remain authenticated.
                conn.sendall(json.dumps({
                    "ok": True,
                    "state": "RUNNING",
                    "strict_dependencies": self.writer.strict_dependencies,
                    "trusted_context_source": "task_session_ssot",
                }).encode())
            elif op == "authz":
                self._authenticate_endpoint(msg)
                ctx = self._trusted_context(msg)
                res = self.writer.authorizer.authorize(
                    msg["operation"], ctx, resources=msg.get("resources"),
                    env={"root": self.writer.root, "fs": RealFS()})
                if res.allowed:
                    conn.sendall(json.dumps({"ok": True, "capability": res.capability}).encode())
                else:
                    conn.sendall(json.dumps({"ok": False, "failed": res.failed}).encode())
            elif op == "write":
                self._authenticate_endpoint(msg)
                cap = msg["capability"]
                if not self.allow_legacy_test_context:
                    # Re-read task/session/lease at commit time so a capability
                    # cannot outlive a revoked lease or changed task state.
                    load_trusted_context(
                        self.writer.root,
                        task_id=cap.get("task_id"),
                        session_id=cap.get("session_id"),
                        actor_id=cap.get("actor_id"))
                out = self.writer._commit(cap, msg.get("content", ""),
                                          actor_id=cap["actor_id"],
                                          session_id=cap["session_id"],
                                          task_id=cap["task_id"])
                conn.sendall(json.dumps({"ok": True, **out}).encode())
            else:
                conn.sendall(json.dumps({"ok": False, "error": "unknown op"}).encode())
        except Exception as e:  # 任何异常都回写错误，绝不静默
            try:
                conn.sendall(json.dumps({"ok": False, "error": str(e)}).encode())
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def serve_forever(self):
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind((self.host, self.port))
        self._srv.listen(8)
        self.port = self._srv.getsockname()[1]
        while True:
            try:
                conn, _ = self._srv.accept()
            except OSError:
                break
            t = threading.Thread(target=self._handle, args=(conn,), daemon=True)
            t.start()

    def start(self):
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)
        self._thread.start()
        for _ in range(200):
            if self.port:
                break
            time.sleep(0.005)
        return self.port

    def shutdown(self):
        if self._srv:
            try:
                self._srv.close()
            except Exception:
                pass


class BrokerClient:
    """TaskRunner 侧：无密钥，仅能通过 Broker 授权后写。"""

    def __init__(
            self, host="127.0.0.1", port=0, client_token=None,
            legacy_test_context=False):
        self.host = host
        self.port = port
        self.client_token = (
            client_token
            if client_token is not None
            else os.environ.get("STYLE_BROKER_CLIENT_TOKEN"))
        self.legacy_test_context = bool(legacy_test_context)

    def _send(self, msg):
        if self.client_token:
            msg = dict(msg)
            msg["client_token"] = self.client_token
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5.0)
        s.connect((self.host, self.port))
        s.sendall((json.dumps(msg) + "\n").encode("utf-8"))
        buf = b""
        while b"\n" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        s.close()
        return json.loads(buf.decode("utf-8"))

    def authz(self, operation, ctx, resources):
        identity = (
            _ctx_to_dict(ctx)
            if self.legacy_test_context else _ctx_to_identity(ctx))
        return self._send({"op": "authz", "operation": operation,
                          "identity": identity,
                          "resources": resources})

    def write(self, capability, content):
        return self._send({"op": "write", "capability": capability, "content": content})


# --------------------------------------------------------------------------
# TaskContext 序列化（IPC 传输）
# --------------------------------------------------------------------------
_CTX_FIELDS = ["task_id", "actor_id", "actor_role", "executor_id", "executor_role",
               "creator_can_assign_role", "template_valid", "state", "session_id",
               "session_ready", "subagent_policy", "lease_owner", "lease_expires_at",
               "completion_authority", "outputs_valid", "outputs_consistent",
               "dependency_binding"]


def _ctx_to_dict(ctx):
    return {k: getattr(ctx, k) for k in _CTX_FIELDS}


def _ctx_from_dict(d):
    return TaskContext(**{k: d[k] for k in _CTX_FIELDS if k in d})


def _ctx_to_identity(ctx):
    return {
        "task_id": getattr(ctx, "task_id", ""),
        "session_id": getattr(ctx, "session_id", ""),
        "actor_id": getattr(ctx, "actor_id", ""),
    }


def _parse_lease(value):
    if value in (None, "", 0):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.datetime.fromisoformat(str(value)).timestamp()
    except ValueError:
        raise BrokerError("invalid task lease timestamp")


def _dependency_binding(root, task):
    """Reconstruct write dependency truth from task inputs and evidence files."""
    values = ((task.get("inputs") or {}).get("values") or {})
    operation = {
        "chapter-apply-revision": "apply",
        "chapter-rollback-revision": "rollback",
        "chapter_publish": "publish",
        "chapter_write": "chapter_write",
        "chapter_fix": "chapter_write",
    }.get(task.get("type"))
    if not operation:
        return False
    required = {
        "apply": (
            "protected_manifest", "style_guidance",
            "fidelity_report", "quality_report"),
        "rollback": ("regression_result", "pre_apply_backup"),
        "publish": (
            "regression_result", "protected_manifest", "style_guidance",
            "nkb_sync_proof", "draft_sha256", "nkb_revision",
            "nkb_snapshot_sha256", "outline_sha256",
            "protected_manifest_sha256", "style_guidance_sha256",
            "chapter_review_report_sha256"),
        "chapter_write": (),
    }[operation]
    if any(values.get(name) in (None, "", False) for name in required):
        return False
    if operation == "publish":
        regression_value = values.get("regression_result")
        regression_path = (
            regression_value if os.path.isabs(str(regression_value))
            else os.path.join(root, str(regression_value)))
        if not os.path.isfile(regression_path):
            return False
        try:
            if regression_path.lower().endswith(".json"):
                with open(regression_path, "r", encoding="utf-8") as stream:
                    regression = json.load(stream)
            else:
                import _gov
                regression = _gov.load_yaml(regression_path) or {}
        except Exception:
            return False
        if regression.get("result") != "FINAL_PASSED":
            return False
        for name in (
                "draft_sha256", "nkb_revision", "nkb_snapshot_sha256",
                "outline_sha256", "protected_manifest_sha256",
                "style_guidance_sha256",
                "chapter_review_report_sha256"):
            if str(regression.get(name)) != str(values.get(name)):
                return False
    return True


def load_trusted_context(root, task_id, session_id, actor_id):
    """Build TaskContext only from task/session/project SSOT.

    Client-provided roles, states, leases and authority flags are ignored.
    """
    if not task_id or not session_id or not actor_id:
        raise BrokerError("task_id, session_id and actor_id are required")
    import task_engine
    import session_bootstrap
    import task_packet
    import _gov

    state, data = task_engine.load_task(root, task_id)
    if state is None:
        raise BrokerError("task not found")
    task = (data or {}).get("task") or {}
    session = session_bootstrap.load_session(root) or {}
    session_body = session.get("session") or {}
    if session_body.get("id") != session_id:
        raise BrokerError("session does not match current project SSOT")
    owner = task.get("owner")
    if not owner or owner != actor_id:
        raise BrokerError("actor is not the task lease owner")
    lease = _parse_lease(task.get("lease_expire"))
    if lease and lease <= time.time():
        raise BrokerError("task lease expired")
    runtime = session.get("agent_runtime") or {}
    if (
            runtime.get("agent_mode", "single") != "single"
            or runtime.get("subagents_enabled") is not False
            or runtime.get("delegation_enabled") is not False
            or int(runtime.get("max_active_agents", 1)) != 1):
        raise BrokerError("session violates single-agent policy")
    expected_role = (
        (task.get("agent") or {}).get("required_role") or "")
    required_inputs = ((task.get("inputs") or {}).get("required") or [])
    outputs_consistent = True
    for name in required_inputs:
        _, resolved = task_packet._resolve_input(root, name, task)
        if not resolved:
            outputs_consistent = False
            break
    project = _gov.load_yaml(os.path.join(root, "project.yaml")) or {}
    completion = (
        ((project.get("task_system") or {}).get(
            "completion_authority") or ["orchestrator"])[0])
    trusted_state = task.get("style_state") or str(state).upper()
    return TaskContext(
        task_id=task_id,
        actor_id=actor_id,
        actor_role=expected_role,
        executor_id=owner,
        executor_role=expected_role,
        creator_can_assign_role=True,
        template_valid=True,
        state=trusted_state,
        session_id=session_id,
        session_ready=all(
            value is True
            for value in (session_body.get("loaded") or {}).values()),
        subagent_policy="denied",
        lease_owner=owner,
        lease_expires_at=lease,
        completion_authority=completion,
        outputs_valid=True,
        outputs_consistent=outputs_consistent,
        dependency_binding=_dependency_binding(root, task),
    )


# --------------------------------------------------------------------------
# Windows NTFS ACL 双身份（默认 dry-run，安全；运维以管理员实际执行）
# --------------------------------------------------------------------------
def build_acl_commands(drafts, approved, taskrunner_account, writer_account):
    """构造 icacls 命令：Writer 授写、TaskRunner 拒写（双重不可绕过）。"""
    cmds = []
    for path, allow, deny in ((drafts, writer_account, taskrunner_account),
                              (approved, writer_account, taskrunner_account)):
        cmds.append('icacls "%s" /grant:r "%s":(OI)(CI)M' % (path, allow))
        cmds.append('icacls "%s" /remove:d "%s"' % (path, deny))
        cmds.append('icacls "%s" /deny "%s":(OI)(CI)M' % (path, deny))
    return cmds


def build_acl_rollback_commands(
        drafts, approved, taskrunner_account, writer_account):
    commands = []
    for path in (drafts, approved):
        commands.append(
            'icacls "%s" /remove:d "%s"' %
            (path, taskrunner_account))
        commands.append(
            'icacls "%s" /remove:g "%s"' %
            (path, writer_account))
    return commands


def verify_ntfs_acl(
        drafts, approved, taskrunner_account, writer_account):
    """Read ACLs back and verify identities and effective ACE intent."""
    if os.name != "nt":
        return {
            "verified": False,
            "reason": "NTFS ACL verification is Windows-only",
            "paths": {},
        }
    details = {}
    verified = True
    identities = {}
    for account in (taskrunner_account, writer_account):
        identity = subprocess.run(
            ["net", "user", account], capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False)
        identities[account] = {
            "exists": identity.returncode == 0,
            "returncode": identity.returncode,
        }
        verified = verified and identity.returncode == 0
    for path in (drafts, approved):
        proc = subprocess.run(
            ["icacls", path], capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False)
        text = (proc.stdout or "") + (proc.stderr or "")
        lines = [
            line.replace(" ", "").lower()
            for line in text.splitlines()]
        writer_lines = [
            line for line in lines
            if writer_account.lower() in line]
        runner_lines = [
            line for line in lines
            if taskrunner_account.lower() in line]
        writer_grant_write = any(
            ("(m)" in line or "(f)" in line) and "(deny)" not in line
            for line in writer_lines)
        taskrunner_deny_write = any(
            ("(m)" in line or "(f)" in line) and "(deny)" in line
            for line in runner_lines)
        path_ok = (
            proc.returncode == 0
            and writer_grant_write
            and taskrunner_deny_write)
        details[path] = {
            "returncode": proc.returncode,
            "writer_grant_write": writer_grant_write,
            "taskrunner_deny_write": taskrunner_deny_write,
            "acl": text,
            "verified": path_ok,
        }
        verified = verified and path_ok
    return {
        "verified": verified,
        "identities": identities,
        "paths": details,
    }


def apply_ntfs_acl(drafts, approved, taskrunner_account, writer_account,
                   apply=False, dry_run=True):
    """落实 NTFS ACL。默认 dry_run=True 仅返回命令、不实际变更，避免误改系统。

    真实部署：``apply_ntfs_acl(d, a, "SVC_TaskRunner", "SVC_ChapterWriter",
    apply=True, dry_run=False)`` 以管理员执行。
    """
    cmds = build_acl_commands(drafts, approved, taskrunner_account, writer_account)
    rollback = build_acl_rollback_commands(
        drafts, approved, taskrunner_account, writer_account)
    applied = False
    results = []
    verification = {
        "verified": False,
        "reason": "dry-run: ACL not changed",
    }
    if apply and not dry_run:
        if os.name != "nt":
            raise BrokerError("NTFS ACL deployment requires Windows")
        argv = []
        for path in (drafts, approved):
            argv.extend([
                (["icacls", path, "/grant:r",
                  "%s:(OI)(CI)M" % writer_account], True),
                (["icacls", path, "/remove:d",
                  taskrunner_account], False),
                (["icacls", path, "/deny",
                  "%s:(OI)(CI)M" % taskrunner_account], True),
            ])
        for command, required in argv:
            proc = subprocess.run(
                command, capture_output=True, text=True,
                encoding="utf-8", errors="replace", check=False)
            results.append({
                "command": command,
                "required": required,
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            })
        applied = all(
            item["returncode"] == 0
            for item in results if item["required"])
        verification = verify_ntfs_acl(
            drafts, approved, taskrunner_account, writer_account)
        if not applied or not verification.get("verified"):
            raise BrokerError(
                "ACL commands or read-back verification failed")
    return {
        "commands": cmds,
        "rollback_commands": rollback,
        "applied": applied,
        "verified": bool(verification.get("verified")),
        "verification": verification,
        "results": results,
    }


# --------------------------------------------------------------------------
# 便捷：以 ephemeral 密钥构造本地 Broker（测试 / 单进程演示）
# --------------------------------------------------------------------------
def local_broker(root, key=None):
    return ControlledWriter(
        root, key_vault=BrokerKeyVault(key=key),
        strict_dependencies=False)
