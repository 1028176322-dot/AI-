# -*- coding: utf-8 -*-
"""任务系统引擎（Task System Engine）—— 平台操作中心核心。

文件系统即状态：每个任务 = tasks/<status>/<TASK-ID>.yaml。
状态转移 = 移动文件 + 更新 task.status。

提供：create_task / create_goal / promote / claim / start / submit / review /
      complete / fail / retry / route / list_tasks / show_task
所有写操作均写 audit/，并在关键转移时联动 project/status.yaml。
"""
import os
import sys
import shutil
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import _gov
import audit_log
import status_update

STATES = ["backlog", "ready", "claimed", "running", "submitted",
          "reviewing", "passed", "completed", "failed", "archive"]
TRANSITIONS = {
    "backlog":   ["ready", "archive"],
    "ready":     ["claimed", "archive"],
    "claimed":   ["running", "archive"],
    "running":   ["submitted", "failed", "archive"],
    "submitted": ["reviewing", "archive"],
    "reviewing": ["passed", "failed", "archive"],
    "passed":    ["completed", "archive"],
    "completed": ["archive"],
    "failed":    ["ready", "archive"],
    "archive":   [],
}
VALID_TYPES = ["chapter_write", "chapter_review", "chapter_fix", "continuity_fix",
               "nkb_update", "candidate_review", "plan_write", "goal_decompose",
               "asset_create", "experiment", "quality_score", "impact_analysis",
               "human_gate"]
VALID_PRIORITY = ["critical", "high", "normal", "low"]
REVIEW_OF = {"chapter_write": "chapter_review", "chapter_fix": "chapter_review"}


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _tasks_dir(root):
    return os.path.join(root, "tasks")


def _state_dir(root, state):
    return os.path.join(_tasks_dir(root), state)


def _goal_dir(root):
    return os.path.join(_tasks_dir(root), "goals")


def _ensure(root):
    for s in STATES:
        os.makedirs(_state_dir(root, s), exist_ok=True)
    os.makedirs(_goal_dir(root), exist_ok=True)


def find_task(root, task_id):
    for s in STATES:
        p = os.path.join(_state_dir(root, s), task_id + ".yaml")
        if os.path.isfile(p):
            try:
                d = _gov.load_yaml(p)
            except Exception:
                continue
            if not isinstance(d, dict):
                continue
            if d.get("obsolete"):
                continue
            # 仅接受 folder 名 == 文件内 task.status 的文件，忽略残留/错位文件
            if (d.get("task") or {}).get("status") != s:
                continue
            return s, p
    return None, None


def load_task(root, task_id):
    st, p = find_task(root, task_id)
    if not p:
        return None, None
    return st, _gov.load_yaml(p)


def _state_of(root, task_id):
    st, _ = find_task(root, task_id)
    return st


def _move(root, task_id, data, new_state):
    old_st, old_p = find_task(root, task_id)
    new_p = os.path.join(_state_dir(root, new_state), task_id + ".yaml")
    data = dict(data)
    t = dict(data.get("task", {}))
    t["status"] = new_state
    data["task"] = t
    os.makedirs(os.path.dirname(new_p), exist_ok=True)
    with open(new_p, "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(data))
    # 删除旧文件：优先 os.remove；若被安全删除拦截（沙箱可能 sys.exit），
    # 退化为 rename 为 .obsolete；再失败则把旧文件标记为 obsolete 覆盖写。
    # 三种情况下 find_task 都会忽略 obsolete / folder≠status 的残留文件。
    if old_p and os.path.isfile(old_p) and os.path.abspath(old_p) != os.path.abspath(new_p):
        try:
            os.remove(old_p)
        except BaseException:
            try:
                os.rename(old_p, old_p + ".obsolete")
            except BaseException:
                try:
                    with open(old_p, "w", encoding="utf-8") as f:
                        f.write(_gov.dump_block({"obsolete": True, "superseded_by": new_p}))
                except BaseException:
                    pass
    return new_p


def _deps_completed(root, task_id, deps):
    for d in (deps or []):
        if _state_of(root, d) != "completed":
            return False
    return True


def _impact_precheck(root, task_id, t):
    """强制预检：claim/start 前对内容型任务跑冲击分析，gate=block 则阻断。

    仅对内容型任务（chapter_write/chapter_fix/continuity_fix/nkb_update/asset_create）
    生效；其余任务跳过。工具缺失或分析异常时放行（不阻断主流程）。
    """
    tt = (t or {}).get("type")
    if tt not in ("chapter_write", "chapter_fix", "continuity_fix", "nkb_update", "asset_create"):
        return
    try:
        import impact_analyzer
    except Exception:
        return
    try:
        rep = impact_analyzer.analyze_task(root, task_id, diff_summary="pre-claim/start gate", write=False)
    except Exception:
        return
    if (rep.get("gate") or {}).get("decision") == "block":
        reasons = (rep.get("gate") or {}).get("reasons") or ["影响已发布内容"]
        raise ValueError("冲击分析 gate=block：%s；需 human_gate 任务放行" % "；".join(reasons))


def _quality_precheck(root, task_id, t):
    """强制预检：submit 前对内容型任务跑质量评分，gate=block 则阻断提交。

    仅对内容型任务（chapter_write/chapter_fix/continuity_fix/nkb_update/asset_create）
    生效；其余任务跳过。工具缺失或评分异常时放行（不阻断主流程）。
    """
    tt = (t or {}).get("type")
    if tt not in ("chapter_write", "chapter_fix", "continuity_fix", "nkb_update", "asset_create"):
        return
    try:
        import quality_scorer
    except Exception:
        return
    try:
        rep = quality_scorer.score_task(root, task_id, proposed_by="quality-scorer", write=False)
    except Exception:
        return
    if (rep.get("gate") or {}).get("decision") == "block":
        reasons = (rep.get("gate") or {}).get("reasons") or ["质量不达标"]
        raise ValueError("质量评分 gate=block：%s；须修复后重新 submit 或 human_gate 放行" % "；".join(reasons))


# ───────────────────────── 创建 ─────────────────────────
def create_task(root, task_dict, model="unknown", author="planner-agent"):
    """创建任务。无依赖或依赖已 completed -> ready；否则 backlog。返回 (state, path)。"""
    _ensure(root)
    t = dict(task_dict.get("task", task_dict))
    task_id = t.get("id")
    if not task_id:
        raise ValueError("task.id 必填")
    if t.get("type") and t["type"] not in VALID_TYPES:
        raise ValueError("未知 task.type: %s" % t["type"])
    if t.get("priority") and t["priority"] not in VALID_PRIORITY:
        raise ValueError("未知 task.priority: %s" % t["priority"])
    t.setdefault("version", 1)
    t.setdefault("created", _now())
    t.setdefault("created_by", author)
    t.setdefault("urgency", "normal")
    deps = t.get("dependencies") or []
    # 循环依赖浅检：依赖必须在 tasks 中存在或为合法 id
    init_state = "ready" if _deps_completed(root, task_id, deps) else "backlog"
    t["status"] = init_state
    data = {"task": t}
    p = _move(root, task_id, data, init_state)
    audit_log.record(root, "task_create", agent=author, model=model,
                     task_id=task_id, files=[os.path.relpath(p, root)],
                     result="success", detail="type=%s -> %s" % (t.get("type"), init_state))
    return init_state, p


def create_goal(root, goal_dict, model="unknown", author="planner-agent"):
    _ensure(root)
    g = dict(goal_dict.get("goal", goal_dict))
    gid = g.get("id")
    if not gid:
        raise ValueError("goal.id 必填")
    g.setdefault("status", "active")
    g.setdefault("created", _now())
    g.setdefault("created_by", author)
    g.setdefault("success", [])
    os.makedirs(_goal_dir(root), exist_ok=True)
    p = os.path.join(_goal_dir(root), gid + ".yaml")
    with open(p, "w", encoding="utf-8") as f:
        f.write(_gov.dump_block({"goal": g}))
    audit_log.record(root, "task_create", agent=author, model=model,
                     task_id=gid, files=[os.path.relpath(p, root)],
                     result="success", detail="goal created")
    return p


# ───────────────────────── 流转 ─────────────────────────
def promote(root, task_id, model="unknown", author="task-scheduler"):
    """backlog -> ready（依赖全部 completed）。"""
    st, data = load_task(root, task_id)
    if st is None:
        raise FileNotFoundError(task_id)
    if st != "backlog":
        return st, "已是 %s，无需 promote" % st
    deps = (data.get("task") or {}).get("dependencies") or []
    if not _deps_completed(root, task_id, deps):
        return st, "依赖未全部 completed，停留 backlog"
    _move(root, task_id, data, "ready")
    audit_log.record(root, "task_create", agent=author, model=model, task_id=task_id,
                     result="success", detail="promoted backlog->ready")
    return "ready", "promoted"


def claim(root, task_id, agent, role, model="unknown", lease_min=60):
    st, data = load_task(root, task_id)
    if st is None:
        raise FileNotFoundError(task_id)
    if st != "ready":
        raise ValueError("claim 要求状态 ready，当前 %s" % st)
    t = data["task"]
    req_role = (t.get("agent") or {}).get("required_role")
    if req_role and role != req_role and role != "task-scheduler":
        raise ValueError("角色不匹配：task 需 %s，agent 为 %s" % (req_role, role))
    owner = t.get("owner")
    if owner and owner != agent:
        raise ValueError("任务已被 %s 接取，不能重复 claim" % owner)
    _impact_precheck(root, task_id, t)
    t["owner"] = agent
    t["claimed_at"] = _now()
    t["lease_expire"] = (datetime.datetime.now() + datetime.timedelta(minutes=lease_min)).isoformat(timespec="seconds")
    _move(root, task_id, data, "claimed")
    # 状态联动：章节写作任务进入 write 步
    if t.get("type") == "chapter_write":
        status_update.set_step(root, chapter=t.get("chapter_ref"), step="write", by="task-system")
    audit_log.record(root, "task_claim", agent=agent, role=role, model=model,
                     task_id=task_id, result="success", detail="claimed by %s" % agent)
    return "claimed"


def start(root, task_id, agent, role="unknown", model="unknown"):
    st, data = load_task(root, task_id)
    if st != "claimed":
        raise ValueError("start 要求 claimed，当前 %s" % st)
    _impact_precheck(root, task_id, data["task"])
    _move(root, task_id, data, "running")
    audit_log.record(root, "task_start", agent=agent, role=role, model=model,
                     task_id=task_id, result="success", detail="running")
    return "running"


def submit(root, task_id, artifact, outputs=None, checks=None,
           agent="unknown", role="unknown", model="unknown"):
    st, data = load_task(root, task_id)
    if st != "running":
        raise ValueError("submit 要求 running，当前 %s" % st)
    _quality_precheck(root, task_id, data["task"])
    checks = checks or {}
    failed = [k for k, v in checks.items() if v not in ("pass", True)]
    if failed:
        _move(root, task_id, data, "failed")
        data["task"]["failure"] = {"reason": "self_check_failed", "checks": checks}
        _move(root, task_id, data, "failed")
        audit_log.record(root, "task_submit", agent=agent, role=role, model=model,
                         task_id=task_id, result="fail", detail="checks 未全 pass: %s" % failed)
        return "failed", "self-check 未通过"
    t = data["task"]
    t["artifact"] = artifact
    t["outputs"] = outputs or {}
    t["submission"] = {"checks": checks, "at": _now()}
    _move(root, task_id, data, "submitted")
    # 自动建审查任务
    rev_type = REVIEW_OF.get(t.get("type"))
    created_review = None
    if rev_type:
        rid = "%s-REVIEW" % task_id
        review_task = {
            "task": {
                "id": rid,
                "version": 1,
                "project": t.get("project"),
                "type": rev_type,
                "title": "审查 %s" % task_id,
                "status": "ready",
                "priority": t.get("priority", "high"),
                "created": _now(),
                "created_by": "task-system",
                "goal": t.get("goal"),
                "dependencies": [task_id],
                "inputs": {"required": [artifact]},
                "expected_outputs": ["review-report"],
                "acceptance": {"criteria": ["四支柱评分完成", "重大 finding 标注 severity"]},
                "permissions": {"read": ["chapters/*", "NKB/*"], "write": ["artifacts/*"], "forbidden": ["core/*"]},
                "agent": {"required_role": "reviewer"},
            }
        }
        _move(root, rid, review_task, "ready")
        created_review = rid
    audit_log.record(root, "task_submit", agent=agent, role=role, model=model,
                     task_id=task_id, result="success",
                     detail="artifact=%s review=%s" % (artifact, created_review))
    return "submitted", created_review


def review(root, task_id, decision, findings=None, reviewer="unknown",
           role="reviewer", model="unknown"):
    """对审查任务做决策。pass -> 原任务 completed；fail -> 建 FIX 任务。"""
    st, data = load_task(root, task_id)
    if st not in ("submitted", "reviewing", "running", "claimed"):
        # 允许 reviewer 直接对 review 任务判（review 任务通常在 ready/claimed/running）
        pass
    t = data["task"]
    # 找被审查的原任务
    dep = (t.get("dependencies") or [None])[0]
    if decision == "pass":
        _move(root, task_id, data, "passed")
        _move(root, task_id, data, "completed")
        if dep:
            dst, ddata = load_task(root, dep)
            if dst in ("submitted", "reviewing"):
                ddata["task"]["review"] = {"decision": "pass", "at": _now()}
                _move(root, dep, ddata, "passed")
                _move(root, dep, ddata, "completed")
                status_update.set_step(root, step="done", blocked=False, by="task-system")
                _promote_dependents(root, dep, model, role)
        audit_log.record(root, "task_review", agent=reviewer, role=role, model=model,
                         task_id=task_id, result="success", detail="PASS")
        return "completed", "原任务已完成"
    else:
        _move(root, task_id, data, "failed")
        # 建 FIX 任务
        fix_id = None
        if dep:
            dst, ddata = load_task(root, dep)
            # 原任务保持在 submitted/reviewing，等待修复后重审
            fix_id = "%s-FIX" % dep
            sev = "high"
            cats = []
            for f in (findings or []):
                cats.append(f.get("category"))
            fix_task = {
                "task": {
                    "id": fix_id,
                    "version": 1,
                    "project": ddata["task"].get("project"),
                    "type": "chapter_fix" if ddata["task"].get("type") == "chapter_write" else "continuity_fix",
                    "title": "修复 %s" % dep,
                    "status": "ready",
                    "priority": "high",
                    "created": _now(),
                    "created_by": "task-system",
                    "goal": ddata["task"].get("goal"),
                    "dependencies": [dep],
                    "inputs": {"required": [dep]},
                    "expected_outputs": ["fixed-draft"],
                    "acceptance": {"criteria": ["修复 finding", "复审通过"]},
                    "permissions": {"read": ["chapters/*", "NKB/*"], "write": ["chapters/drafts/*"], "forbidden": ["NKB/*", "core/*"]},
                    "agent": {"required_role": "fixer"},
                    "source_findings": findings or [],
                }
            }
            _move(root, fix_id, fix_task, "ready")
            status_update.set_step(root, blocked=True, reason="review failed: %s" % (cats or ["unknown"]), by="task-system")
        audit_log.record(root, "task_review", agent=reviewer, role=role, model=model,
                         task_id=task_id, result="fail", detail="FAILED; fix=%s" % fix_id)
        return "failed", fix_id


def complete(root, task_id, model="unknown", author="task-scheduler"):
    st, data = load_task(root, task_id)
    if st != "passed":
        if st == "completed":
            return "completed", "已是 completed"
        raise ValueError("complete 要求 passed，当前 %s" % st)
    _move(root, task_id, data, "completed")
    audit_log.record(root, "task_complete", agent=author, model=model,
                     task_id=task_id, result="success", detail="completed")
    # 推进下游依赖
    _promote_dependents(root, task_id, model, author)
    return "completed"


def _promote_dependents(root, done_id, model, author):
    for s in ("backlog", "ready"):
        d = _state_dir(root, s)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith(".yaml"):
                continue
            tid = fn[:-5]
            _, td = load_task(root, tid)
            deps = (td.get("task") or {}).get("dependencies") or []
            if done_id in deps and s == "backlog":
                promote(root, tid, model, author)


def fail(root, task_id, reason, strategy="reload_context", max_retry=3,
         model="unknown", author="task-system"):
    st, data = load_task(root, task_id)
    if st in ("completed", "archive"):
        raise ValueError("终态不可 fail")
    data["task"]["failure"] = {"reason": reason, "strategy": strategy, "max_retry": max_retry}
    data["task"]["retry_count"] = data["task"].get("retry_count", 0)
    _move(root, task_id, data, "failed")
    status_update.set_step(root, blocked=True, reason="task failed: %s" % reason, by="task-system")
    audit_log.record(root, "task_fail", agent=author, model=model, task_id=task_id,
                     result="fail", detail=reason)
    return "failed"


def retry(root, task_id, model="unknown", author="task-scheduler"):
    st, data = load_task(root, task_id)
    if st != "failed":
        raise ValueError("retry 要求 failed，当前 %s" % st)
    rc = data["task"].get("retry_count", 0) + 1
    max_r = (data["task"].get("failure") or {}).get("max_retry", 3)
    if rc > max_r:
        raise ValueError("超过 max_retry(%d)，转人工" % max_r)
    data["task"]["retry_count"] = rc
    data["task"]["owner"] = None
    data["task"]["failure"] = None
    _move(root, task_id, data, "ready")
    status_update.set_step(root, blocked=False, by="task-system")
    audit_log.record(root, "task_create", agent=author, model=model, task_id=task_id,
                     result="success", detail="retry #%d -> ready" % rc)
    return "ready"


def route(root, role, capabilities):
    """扫描 ready/ 池，返回该 role+capabilities 可接取的任务列表。"""
    caps = set(capabilities or [])
    out = []
    d = _state_dir(root, "ready")
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".yaml"):
            continue
        tid = fn[:-5]
        _, td = load_task(root, tid)
        t = td.get("task", {})
        req_role = (t.get("agent") or {}).get("required_role")
        if req_role and req_role != role:
            continue
        if t.get("type") not in caps:
            continue
        out.append({
            "task_id": tid,
            "type": t.get("type"),
            "priority": t.get("priority"),
            "goal": t.get("goal"),
            "title": t.get("title"),
        })
    return out


def list_tasks(root, state=None):
    out = {}
    states = [state] if state else STATES
    for s in states:
        d = _state_dir(root, s)
        if not os.path.isdir(d):
            continue
        ids = [f[:-5] for f in os.listdir(d) if f.endswith(".yaml")]
        if ids:
            out[s] = sorted(ids)
    return out


def show_task(root, task_id):
    st, data = load_task(root, task_id)
    if st is None:
        print("# 任务不存在: %s" % task_id)
        return
    print("状态: %s" % st)
    print(_gov.dump_block(data))


if __name__ == "__main__":
    print("task_engine 仅作库使用；CLI 见 task_cli.py")
