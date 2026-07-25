# -*- coding: utf-8 -*-
"""publish_chapter — Publish Service（编辑≠发布的落地层，非 Agent）。

这是「正式章节写权限断链」根治的最后一环：writer/fixer 只能写工作副本（chapters/drafts），
canonical 正式正文**只能**由本平台脚本（在 chapter_publish 任务 + 发布动态授权 grant 约束下）
确定性原子发布。AI 角色绝不直接写 canonical。

流程（publish）：
  1. 加载 chapter_publish 任务，校验类型 / required_role == publish_service。
  2. 确保任务进入 running（publishing 态）：ready→claim→start。
  3. 六因子授权门禁：auth_engine.authorize(publish_service, target, task_id,
     intended_action=chapter.publish) 必须 allow（含 grant 有效性）。
  4. 校验来源 Build（approved draft）存在并读取内容。
  5. revision_guard：若已发布过，比对 canonical 当前文件 hash 与 manifest 记录 hash，
     不一致即 REVISION_CONFLICT（疑似被绕过 Publish Service 直改）。
  6. 原子发布：写临时文件 → fsync → os.replace 落到 canonical（同文件系统原子替换）。
  7. 写历史副本 operations/published/<path>/r<N>.md（供回滚）。
  8. 更新 canonical_manifest（record_publish：revision+1 / hash / source / versions）。
  9. 闭环：finish_service_task（任务 completed）+ invalidate_grant（terminal 失效）+ 审计。

回滚（rollback）：canonical.rollback 服务动作，仅事故回滚；从 operations/published 历史副本
恢复并写新 revision（不删历史），同样受六因子约束。
"""
import os
import sys
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
import _gov
import task_engine as TE
import auth_engine as AE
import manifest as MF
import audit_log


SERVICE_ROLE = "publish_service"
HISTORY_DIR = "operations/published"   # 历史副本根（供回滚）


def _norm(p):
    return p.replace("\\", "/")


def _history_path(project_root, canon_rel, revision):
    canon_rel = _norm(canon_rel)
    base = os.path.join(project_root, HISTORY_DIR, canon_rel)
    return os.path.join(base, "r%d.md" % revision)


def _fsync_file(path):
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def _atomic_write(target_abs, content):
    """写临时文件 → fsync → 同文件系统 os.replace（原子替换）。"""
    d = os.path.dirname(target_abs)
    os.makedirs(d, exist_ok=True)
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".pub_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            _fsync_file(tmp)
        os.replace(tmp, target_abs)   # 同 FS 原子替换；失败时 tmp 残留可清理
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def publish(project_root, task_id, role=SERVICE_ROLE, agent=SERVICE_ROLE, model="platform"):
    """执行 chapter_publish 任务的原子发布。返回 manifest entry dict。"""
    project_root = os.path.abspath(project_root)
    # 1. 加载并校验任务
    st, data = TE.load_task(project_root, task_id)
    if st is None:
        raise FileNotFoundError("发布任务不存在: %s" % task_id)
    t = (data or {}).get("task", {})
    if t.get("type") != "chapter_publish":
        raise ValueError("任务 %s 非 chapter_publish（type=%s）" % (task_id, t.get("type")))
    req_role = (t.get("agent") or {}).get("required_role")
    if req_role and req_role != role:
        raise ValueError("任务 %s 需角色 %s，当前 %s" % (task_id, req_role, role))

    # 2. 确保任务进入 running（publishing 态）
    if st == "ready":
        TE.claim(project_root, task_id, agent, role, model)
        st = "claimed"
    if st == "claimed":
        TE.start(project_root, task_id, agent, role, model)
        st = "running"
    if st != "running":
        raise ValueError("发布任务 %s 未处于 running（当前 %s）" % (task_id, st))

    # 3. 六因子授权门禁
    target = t.get("publish_target") or _norm(t.get("inputs", {}).get("required", [None])[0] or "")
    if not target:
        raise ValueError("发布任务 %s 缺 publish_target" % task_id)
    auth = AE.authorize(role, target, task_id=task_id, project_root=project_root,
                        intended_action="chapter.publish")
    if auth["decision"] != "allow":
        raise PermissionError("AUTH DENY [%s]: %s" % (auth["code"], auth["message"]))

    # 4. 校验来源 Build（approved draft）
    src_list = (t.get("inputs") or {}).get("required") or []
    draft = src_list[0] if src_list else None
    if not draft or not os.path.isfile(os.path.join(project_root, _norm(draft))):
        raise FileNotFoundError("来源 Build 缺失: %s" % draft)
    with open(os.path.join(project_root, _norm(draft)), "r", encoding="utf-8") as f:
        content = f.read()

    # 5. revision_guard：已发布过则比对 canonical 当前 hash 与 manifest 记录
    canon_abs = os.path.join(project_root, target)
    prev_entry = MF.get_entry(project_root, target)
    if prev_entry and os.path.isfile(canon_abs):
        cur_hash = MF.hash_content(open(canon_abs, "r", encoding="utf-8").read())
        if cur_hash != prev_entry.get("hash"):
            raise PermissionError(
                "REVISION_CONFLICT: canonical %s 当前 hash(%s) 与 manifest 记录(%s) 不一致，"
                "疑似被绕过 Publish Service 直改；禁止发布" % (
                    target, cur_hash[:10], prev_entry.get("hash", "")[:10]))

    # 6. 原子发布
    _atomic_write(canon_abs, content)

    # 7. 历史副本（供回滚）
    new_rev = (prev_entry["revision"] + 1) if prev_entry else 1
    hist = _history_path(project_root, target, new_rev)
    os.makedirs(os.path.dirname(hist), exist_ok=True)
    with open(hist, "w", encoding="utf-8") as f:
        f.write(content)

    # 8. 更新 manifest
    entry = MF.record_publish(project_root, target, _norm(draft), content, prev_status="publishing")

    # 9. 闭环：任务 completed + grant 失效 + 审计
    TE.finish_service_task(project_root, task_id, model=model, author=agent)
    AE.invalidate_grant(project_root, task_id)
    audit_log.record(project_root, "publish", agent=agent, role=role, model=model,
                     task_id=task_id, result="success",
                     detail="published %s r%d (hash=%s)" % (target, entry["revision"], entry["hash"][:10]))
    return entry


def rollback(project_root, task_id, target, to_revision, role=SERVICE_ROLE,
             agent=SERVICE_ROLE, model="platform"):
    """canonical.rollback：从 operations/published 历史副本恢复到指定 revision。

    写新 revision（不删历史），受六因子约束（需 canonical.rollback 的有效 grant）。
    """
    project_root = os.path.abspath(project_root)
    target = _norm(target)
    # 授权门禁：canonical.rollback 服务动作
    auth = AE.authorize(role, target, task_id=task_id, project_root=project_root,
                        intended_action="canonical.rollback")
    if auth["decision"] != "allow":
        raise PermissionError("AUTH DENY [%s]: %s" % (auth["code"], auth["message"]))

    hist = _history_path(project_root, target, to_revision)
    if not os.path.isfile(hist):
        raise FileNotFoundError("历史副本缺失（r%d）: %s" % (to_revision, hist))
    with open(hist, "r", encoding="utf-8") as f:
        content = f.read()

    canon_abs = os.path.join(project_root, target)
    _atomic_write(canon_abs, content)
    entry = MF.rollback(project_root, target, to_revision, content, new_status="published")

    if task_id:
        try:
            TE.finish_service_task(project_root, task_id, model=model, author=agent)
            AE.invalidate_grant(project_root, task_id)
        except Exception:
            pass
    audit_log.record(project_root, "rollback", agent=agent, role=role, model=model,
                     task_id=task_id, result="success",
                     detail="rolled back %s to r%d" % (target, to_revision))
    return entry


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="publish", description="Publish Service 原子发布")
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--role", default=SERVICE_ROLE)
    ap.add_argument("--agent", default=SERVICE_ROLE)
    ap.add_argument("--model", default="platform")
    ap.add_argument("--rollback-to", type=int, default=None,
                    help="指定 revision 则执行回滚（需独立的 rollback 授权任务）")
    ap.add_argument("--target", default=None, help="回滚目标 canonical 路径")
    args = ap.parse_args()
    try:
        if args.rollback_to is not None:
            entry = rollback(args.project_root, args.task_id, args.target, args.rollback_to,
                             role=args.role, agent=args.agent, model=args.model)
            print("ROLLBACK OK: %s r%d" % (entry["path"], entry["revision"]))
        else:
            entry = publish(args.project_root, args.task_id, role=args.role,
                            agent=args.agent, model=args.model)
            print("PUBLISH OK: %s r%d (hash=%s)" % (entry["path"], entry["revision"], entry["hash"][:10]))
    except Exception as e:
        print("PUBLISH FAILED: %s" % e)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
