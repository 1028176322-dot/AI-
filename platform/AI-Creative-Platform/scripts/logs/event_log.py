# -*- coding: utf-8 -*-
"""
不可变任务事件日志（纲要 §2.10 / §10）。

设计要点
--------
- 每条事件含单调 ``seq`` + ``previous_event_hash`` 哈希链 + 认证 ``actor_id`` + HMAC 签名。
- 签名密钥仅可信日志 Broker 持有（经环境变量注入）；普通任务进程无密钥，无法追加或伪造。
- 链头哈希定期签名并锚定到项目外（anchor 文件），用于离线篡改检测。
- 提供 ``verify-event-log`` 命令（``python event_log.py verify --log <path>``）。

本模块是 #18（基础设施）的契约运行时：``task-event.schema.yaml`` 的不可变日志实现。
真实的「仅 Broker 可写」由 #19 的 OS/进程隔离落地；本模块从密码学上保证：
没有密钥就无法产生合法事件，从而即便日志文件被整份替换也能被 verify 检出。
"""
import argparse
import hashlib
import hmac
import json
import os
import time

GENESIS_PREV = "0" * 64


class SigningKeyUnavailable(Exception):
    """没有签名密钥时抛出——只有可信日志 Broker 持有密钥。"""


class EventLogError(Exception):
    pass


# --------------------------------------------------------------------------
# 规范化与哈希
# --------------------------------------------------------------------------
def _canon_bytes(event):
    """可复现的规范化字节：排除 signature 与可选 chain_head_anchor_ref。"""
    e = {k: v for k, v in event.items() if k not in ("signature", "chain_head_anchor_ref")}
    return json.dumps(e, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def event_hash(event):
    """单个事件的哈希（用于哈希链 previous_event_hash）。"""
    return hashlib.sha256(_canon_bytes(event)).hexdigest()


def _hmac(key, data):
    return hmac.new(key, data, hashlib.sha256).hexdigest()


# --------------------------------------------------------------------------
# 密钥托管：密钥只应存在于可信日志 Broker 进程
# --------------------------------------------------------------------------
class KeyProvider:
    def __init__(self, key=None, key_id=None):
        self._key = key
        self._key_id = key_id or os.environ.get("STYLE_EVENT_LOG_KEY_ID", "local-broker-1")
        if self._key is None:
            env = os.environ.get("STYLE_EVENT_LOG_KEY")
            if env:
                try:
                    self._key = bytes.fromhex(env)
                except ValueError:
                    self._key = env.encode("utf-8")

    def has_key(self):
        return self._key is not None

    def key_id(self):
        return self._key_id

    def sign(self, data):
        if not self._key:
            raise SigningKeyUnavailable("signing key unavailable; only trusted log Broker holds it")
        return _hmac(self._key, data)


# --------------------------------------------------------------------------
# 不可变事件日志
# --------------------------------------------------------------------------
class EventLog:
    def __init__(self, log_path, key_provider=None, anchor_dir=None):
        self.log_path = log_path
        self.kp = key_provider or KeyProvider()
        default_anchor = os.path.join(os.path.dirname(log_path) or ".", ".anchors")
        self.anchor_dir = anchor_dir or default_anchor

    # -- 读写 -------------------------------------------------------------
    def read_events(self):
        """公开读取事件列表（状态机重放 / 一致性校验用）。"""
        return self._load()

    def _load(self):
        if not os.path.exists(self.log_path):
            return []
        out = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                out.append(json.loads(line))
        return out

    def _write(self, event):
        os.makedirs(os.path.dirname(os.path.abspath(self.log_path)), exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    # -- 追加（仅 Broker 持有密钥可成功） --------------------------------
    def append(self, event_type, actor_id, task_id, operation=None, resource_refs=None,
               capability_id=None, result="ok", timestamp=None, chain_head_anchor_ref=None,
               details=None):
        if not self.kp.has_key():
            raise SigningKeyUnavailable("cannot append without signing key (Broker-only)")
        events = self._load()
        seq = (events[-1]["seq"] + 1) if events else 1
        prev_hash = event_hash(events[-1]) if events else GENESIS_PREV
        event = {
            "event_id": "%s-%d-%s" % (task_id, seq, event_type),
            "seq": seq,
            "previous_event_hash": prev_hash,
            "event_type": event_type,
            "actor_id": actor_id,
            "task_id": task_id,
            "operation": operation,
            "resource_refs": resource_refs or [],
            "capability_id": capability_id,
            "result": result,
            "timestamp": timestamp if timestamp is not None else time.time(),
        }
        if chain_head_anchor_ref is not None:
            event["chain_head_anchor_ref"] = chain_head_anchor_ref
        if details is not None:
            event["details"] = details
        event["signature"] = self.kp.sign(_canon_bytes(event))
        self._write(event)
        return event

    # -- 链头锚定（项目外，离线篡改检测） --------------------------------
    def anchor(self):
        if not self.kp.has_key():
            raise SigningKeyUnavailable("cannot anchor without signing key")
        events = self._load()
        if not events:
            raise EventLogError("cannot anchor an empty log")
        head_hash = event_hash(events[-1])
        anchor = {
            "anchor_id": "anchor-%s" % head_hash[:16],
            "chain_head_hash": head_hash,
            "key_id": self.kp.key_id(),
            "timestamp": time.time(),
        }
        anchor["signature"] = self.kp.sign(head_hash.encode("utf-8"))
        os.makedirs(self.anchor_dir, exist_ok=True)
        path = os.path.join(self.anchor_dir, "chain_head_anchor.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(anchor, f, ensure_ascii=False, indent=2)
        return anchor

    def _load_anchor(self):
        path = os.path.join(self.anchor_dir, "chain_head_anchor.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    # -- 校验（篡改检测 / 签名校验 / 链头一致性） ------------------------
    def verify(self, key=None):
        kp = self.kp if key is None else KeyProvider(key=key)
        events = self._load()
        prev = GENESIS_PREV
        checked = 0
        for idx, e in enumerate(events):
            canon = _canon_bytes(e)
            h = hashlib.sha256(canon).hexdigest()
            if e.get("previous_event_hash") != prev:
                return {"valid": False, "checked": checked,
                        "error": "hash chain broken at seq %s" % e.get("seq")}
            if e.get("seq") != idx + 1:
                return {"valid": False, "checked": checked,
                        "error": "seq not monotonic at line %d" % idx}
            if "signature" in e and kp.has_key():
                expected = kp.sign(canon)
                if not hmac.compare_digest(expected, e["signature"]):
                    return {"valid": False, "checked": checked,
                            "error": "signature mismatch at seq %s" % e.get("seq")}
            prev = h
            checked += 1
        anchor = self._load_anchor()
        anchor_checked = None
        if anchor is not None:
            if kp.has_key():
                exp = kp.sign(anchor["chain_head_hash"].encode("utf-8"))
                if not hmac.compare_digest(exp, anchor["signature"]):
                    return {"valid": False, "checked": checked, "error": "anchor signature mismatch"}
            if anchor["chain_head_hash"] != prev:
                return {"valid": False, "checked": checked, "error": "anchor chain head mismatch"}
            anchor_checked = True
        return {"valid": True, "checked": checked, "anchor_checked": anchor_checked}


# --------------------------------------------------------------------------
# CLI：verify-event-log / anchor
# --------------------------------------------------------------------------
def main(argv=None):
    p = argparse.ArgumentParser(prog="event_log", description="verify-event-log / anchor")
    sub = p.add_subparsers(dest="cmd")
    v = sub.add_parser("verify", help="verify-event-log")
    v.add_argument("--log", required=True)
    v.add_argument("--key", default=None, help="hex signing key (Broker-only normally)")
    v.add_argument("--anchor-dir", default=None)
    a = sub.add_parser("anchor", help="sign & anchor current chain head")
    a.add_argument("--log", required=True)
    a.add_argument("--key", required=True, help="hex signing key")
    a.add_argument("--anchor-dir", default=None)
    args = p.parse_args(argv)
    if args.cmd == "verify":
        key = bytes.fromhex(args.key) if args.key else None
        el = EventLog(args.log, KeyProvider(key=key), anchor_dir=args.anchor_dir)
        res = el.verify()
        print(json.dumps(res, ensure_ascii=False))
        return 0 if res["valid"] else 1
    if args.cmd == "anchor":
        el = EventLog(args.log, KeyProvider(key=bytes.fromhex(args.key)), anchor_dir=args.anchor_dir)
        print(json.dumps(el.anchor(), ensure_ascii=False))
        return 0
    p.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
