# -*- coding: utf-8 -*-
"""
多资源、单次使用、签名能力令牌（纲要 §2.8 / §10）。

令牌结构以 ``capability-token.schema.yaml`` 的**多资源 oneOf 为唯一 SSOT**：
每个 operation 需要的资源角色（source/target/candidate_or_backup 等）由契约 ``oneOf``
动态派生，避免在代码里硬编码而与实际契约漂移。
密钥仅受控写 Broker 持有（与事件日志同一把密钥），普通任务进程无法签发或伪造。
"""
import hashlib
import hmac
import json
import os
import time
import uuid

from authorize import SCHEMA_DIR

try:
    from _yaml_lite import load as _yload
except Exception:  # pragma: no cover
    try:
        from yaml import safe_load as _yload
    except Exception:
        _yload = None


class CapabilityError(Exception):
    pass


def _canon(token):
    t = {k: v for k, v in token.items() if k != "signature"}
    return json.dumps(t, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def load_required_roles(schema_path=None):
    """从 capability-token.schema.yaml 的 oneOf 派生 {operation: [role,...]}。"""
    path = schema_path or os.path.join(SCHEMA_DIR, "capability-token.schema.yaml")
    if _yload is None:
        raise RuntimeError("no yaml loader available")
    with open(path, "r", encoding="utf-8") as f:
        data = _yload(f.read())
    out = {}
    for entry in data.get("oneOf", []):
        op = entry.get("operation")
        roles = [r.get("role") for r in entry.get("resources", [])]
        out[op] = roles
    return out


# --------------------------------------------------------------------------
# 消费记录（single_use 防重放）
# --------------------------------------------------------------------------
class CapabilityStore:
    def __init__(self, path=None):
        self.path = path
        self._consumed = set()
        if path and os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            self._consumed.add(json.loads(line)["capability_id"])
                        except Exception:
                            pass

    def is_consumed(self, cid):
        return cid in self._consumed

    def consume(self, cid):
        self._consumed.add(cid)
        if self.path:
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"capability_id": cid, "at": time.time()}) + "\n")

    def reset(self):
        self._consumed = set()
        if self.path and os.path.exists(self.path):
            os.remove(self.path)


# --------------------------------------------------------------------------
# 签发 / 校验 / 消费
# --------------------------------------------------------------------------
def issue(task_id, session_id, actor_id, operation, resources, policy_sha256, key,
          lease_seconds=300, nonce=None, single_use=True):
    if operation not in load_required_roles():
        raise CapabilityError("unknown operation: %s" % operation)
    required = load_required_roles()[operation]
    roles = [r.get("role") for r in (resources or [])]
    for need in required:
        if need not in roles:
            raise CapabilityError("missing resource role %s for %s" % (need, operation))
    now = time.time()
    token = {
        "capability_id": str(uuid.uuid4()),
        "task_id": task_id,
        "session_id": session_id,
        "actor_id": actor_id,
        "operation": operation,
        "resources": resources,
        "policy_sha256": policy_sha256,
        "issued_at": now,
        "expires_at": now + lease_seconds,
        "nonce": nonce or os.urandom(16).hex(),
        "single_use": single_use,
    }
    token["signature"] = hmac.new(key, _canon(token), hashlib.sha256).hexdigest()
    return token


def verify(token, key, store=None, now=None):
    """校验令牌完整性：签名 / 过期 / 单次消费。不含资源哈希 CAS（由 writer 执行）。"""
    now = now or time.time()
    if token.get("expires_at", 0) < now:
        return (False, "expired")
    if token.get("single_use") and store and store.is_consumed(token["capability_id"]):
        return (False, "already consumed (single_use)")
    expected = hmac.new(key, _canon(token), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, token.get("signature", "")):
        return (False, "signature mismatch")
    return (True, "ok")


def verify_resources(token, fs=None):
    """CAS 前置：核对令牌内各资源实际哈希 == 期望哈希（expected=absent 则文件应不存在）。"""
    import _yaml_lite  # noqa  (仅用于错误提示，不影响逻辑)
    from authorize import RealFS, _path_within  # noqa
    fs = fs or RealFS()
    for r in token.get("resources", []):
        expected = r.get("expected_sha256")
        path = r.get("canonical_path")
        actual = fs.sha256(path) if path else None
        if expected in (None, "absent"):
            if actual is not None:
                return (False, "resource %s should be absent but exists" % r.get("role"))
        elif actual is None:
            return (False, "resource %s missing: %s" % (r.get("role"), path))
        elif actual != expected:
            return (False, "resource %s hash mismatch" % r.get("role"))
    return (True, "ok")


def consume(token, store):
    if store is None:
        raise CapabilityError("store required to consume")
    if token.get("single_use"):
        store.consume(token["capability_id"])
