# -*- coding: utf-8 -*-
"""审计记录：append-only jsonl。

每条操作追加一行 JSON，不可修改历史。任务系统 / 版本系统 / 受控写均调用 record()。
"""
import os
import sys
import json
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
# [Phase2] 把 scripts 各分组目录加入 sys.path，保持跨组裸名 import 可用
_SCRIPTS = os.path.dirname(HERE)
if os.path.isdir(_SCRIPTS):
    for _d in os.listdir(_SCRIPTS):
        _p = os.path.join(_SCRIPTS, _d)
        if os.path.isdir(_p) and _p not in sys.path:
            sys.path.insert(0, _p)
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _audit_path(project_root):
    d = os.path.join(project_root, "audit")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "audit.log.jsonl")


def record(project_root, action, agent="unknown", role="unknown", model="unknown",
           task_id=None, files=None, result="success", detail=None):
    """追加一条审计记录，返回该记录 dict。

    op_id 自动递增（OP-000001 ...）。写入失败抛异常（审计丢失是严重事件，交由调用方告警）。
    """
    p = _audit_path(project_root)
    op_id = 1
    if os.path.isfile(p):
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                m = rec.get("op_id", "")
                if m.startswith("OP-"):
                    try:
                        n = int(m.split("-", 1)[1])
                        if n >= op_id:
                            op_id = n + 1
                    except Exception:
                        pass
    rec = {
        "op_id": "OP-%06d" % op_id,
        "ts": _now(),
        "agent": agent,
        "role": role,
        "model": model,
        "action": action,
        "task_id": task_id,
        "files": files or [],
        "result": result,
        "detail": detail,
    }
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


if __name__ == "__main__":
    # 直接调用仅用于自测
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    r = record(root, "cwrite", agent="tester", action="cwrite", result="success", detail="selftest")
    print("recorded:", r["op_id"])
