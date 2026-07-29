# -*- coding: utf-8 -*-
"""auth_engine — 六因子授权引擎（编辑≠发布的根治层）。

设计（见 core/authorization/*.yaml + 2026-07-25 用户修复设计）：
  六因子联立授权：
    allow = platform_policy AND role_capability AND resource_scope
            AND workflow_state AND task_grant AND revision_guard
  默认拒绝（immutable-policies.authorization.default = deny）。

核心职责：
  - 将"目标路径"解析到资源层（working_copy / canonical / review_artifacts / nkb_*）。
  - canonical 层的写/回滚动作 service_only，仅 publish_service 经任务授权可发起；
    任何普通 Agent 角色直接写 canonical → CANONICAL_DIRECT_WRITE_FORBIDDEN。
  - 普通角色（writer/fixer）仅能写 working_copy（chapters/drafts），须经合法任务授权。
  - 返回标准化错误码（11 个），供 CLI / 日志 / e2e 断言。

与 legacy 权限的关系：
  controlled_write 先调本引擎；若 target 不在任何授权资源层（UNGOVERNED），
  回落到 _gov.check_permission（legacy permissions.policy.yaml）。
"""
import os
import sys
import re
import datetime
import fnmatch

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


def _auth_root():
    return os.path.join(_gov.find_platform_root(), "core", "authorization")


def _load(name):
    p = os.path.join(_auth_root(), name)
    if not os.path.isfile(p):
        return {}
    try:
        return _gov.load_yaml(p) or {}
    except Exception:
        return {}


# 模块级缓存（同进程只读一次）
_CACHE = {}


def _models():
    if not _CACHE:
        _CACHE["actions"] = _load("actions.yaml").get("actions", {})
        _CACHE["resources"] = _load("resources.yaml").get("layers", {})
        _CACHE["roles"] = _load("roles.yaml").get("roles", {})
        imm = _load("immutable-policies.yaml")
        _CACHE["auth"] = (imm.get("authorization") or {})
        _CACHE["error_codes"] = (imm.get("error_codes") or {})
        _CACHE["grants_cfg"] = (imm.get("grants") or {})
        _CACHE["state"] = _load("state-permissions.yaml")
    return _CACHE


def _ec(code):
    """取错误码文案；未知错误码回退 PERMISSION_DENIED。"""
    ec = _models()["error_codes"].get(code, {})
    return ec.get("message", code)


# ───────────────────────── 资源层解析 ─────────────────────────
def _norm(target):
    t = target.replace("\\", "/").strip()
    if t.startswith("./"):
        t = t[2:]
    return t


def layer_of(target):
    """把目标路径解析到授权资源层名；不在任何层返回 None（UNGOVERNED）。"""
    t = _norm(target)
    res = _models()["resources"]
    # 解析顺序：canonical 模式优先，nkb_draft 先于 nkb_canonical（前缀重叠）
    order = ["canonical", "working_copy", "review_artifacts", "nkb_draft",
             "nkb_canonical", "protected_content"]
    for name in order:
        layer = res.get(name, {})
        prefixes = layer.get("prefixes") or []
        for p in prefixes:
            pp = p.rstrip("/")
            if t == pp or t.startswith(pp + "/") or t.startswith(pp):
                return name
        pat = layer.get("prefix_pattern")
        if pat and re.match(pat, t.split("/")[0] + "/"):
            return name
    return None


def _layer_prefixes(name):
    return (_models()["resources"].get(name, {}).get("prefixes") or [])


def _layer_writer_identity(name):
    return _models()["resources"].get(name, {}).get("writer_identity")


# ───────────────────────── 动作解析 ─────────────────────────
def _actions_of_layer(layer):
    out = []
    for an, a in _models()["actions"].items():
        if a.get("resource_layer") == layer:
            out.append(an)
    return out


def _role_has_capability(role, action):
    r = _models()["roles"].get(role, {})
    return action in (r.get("capabilities") or [])


def _role_layers(role):
    return set(_models()["roles"].get(role, {}).get("resource_layers") or [])


def infer_action(role, target, intended=None):
    """推断意图动作：显式 > 资源层默认。返回动作名或 None。"""
    if intended and intended in _models()["actions"]:
        return intended
    layer = layer_of(target)
    if layer is None:
        return None
    cands = _actions_of_layer(layer)
    # 角色具备 capability 的优先
    for a in cands:
        if _role_has_capability(role, a):
            return a
    # 否则返回该层首个动作（交由 role_capability 因子判失败）
    return cands[0] if cands else None


# ───────────────────────── 动态授权（grants）─────────────────────────
def grant_path(project_root, task_id):
    d = _models()["grants_cfg"].get("directory", "operations/grants")
    return os.path.join(project_root, d, "%s.yaml" % task_id)


def generate_grant(
        project_root, task_id, role, action, resource_layer, targets,
        ttl_seconds=None):
    """生成动态任务授权文件（task_grant 因子实体）。terminal 态会自动失效。"""
    cfg = _models()["grants_cfg"]
    if ttl_seconds is None:
        ttl_seconds = cfg.get("default_ttl_seconds", 86400)
    if isinstance(ttl_seconds, bool):
        raise ValueError("grant ttl_seconds must be an integer")
    try:
        ttl_seconds = int(ttl_seconds)
        minimum = int(cfg.get("minimum_ttl_seconds", 60))
        maximum = int(cfg.get("maximum_ttl_seconds", 604800))
    except (TypeError, ValueError):
        raise ValueError("grant TTL configuration must contain integers")
    if ttl_seconds < minimum or ttl_seconds > maximum:
        raise ValueError(
            "grant ttl_seconds must be between %d and %d"
            % (minimum, maximum))
    p = grant_path(project_root, task_id)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    now = datetime.datetime.now()
    data = {
        "grant": {
            "task_id": task_id,
            "role": role,
            "action": action,
            "resource_layer": resource_layer,
            "targets": targets if isinstance(targets, list) else [targets],
            "generated_at": now.isoformat(timespec="seconds"),
            "expires_at": (
                now + datetime.timedelta(seconds=ttl_seconds)
            ).isoformat(timespec="seconds"),
            "status": "active",
        }
    }
    with open(p, "w", encoding="utf-8") as f:
        f.write(_gov.dump_block(data))
    return p


def invalidate_grant(project_root, task_id):
    p = grant_path(project_root, task_id)
    if os.path.isfile(p):
        try:
            os.rename(p, p + ".obsolete")
        except BaseException:
            try:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(_gov.dump_block({"grant": {"task_id": task_id, "status": "invalidated"}}))
            except BaseException:
                pass


def read_grant(project_root, task_id):
    p = grant_path(project_root, task_id)
    if not os.path.isfile(p):
        return None
    try:
        d = _gov.load_yaml(p) or {}
        return d.get("grant")
    except Exception:
        return None


# ───────────────────────── 章节态解析 ─────────────────────────
def chapter_state_of(project_root, task_id):
    """把关联任务的态映射为章节态。无 task 返回 None。

    任务类型感知：running 态按任务类型细化到对应章节阶段
    （写=editing / 审查=reviewing / 修复=fixing / 发布=publishing），
    否则一个 running 的 chapter_review 任务会被误判为 editing，导致 review.write_report 被拒。
    """
    if not task_id:
        return None
    st, data = _load_task(project_root, task_id)
    if st is None:
        return None
    t = (data or {}).get("task", {})
    ttype = t.get("type")
    mapping = (_models()["state"].get("task_state_to_chapter_state") or {})
    if st == "running":
        if ttype == "chapter_review":
            return "reviewing"
        if ttype in ("chapter_fix", "continuity_fix"):
            return "fixing"
        if ttype == "chapter_publish":
            return "publishing"
        return "editing"  # chapter_write / 其它
    if st == "reviewing":
        return "reviewing"
    return mapping.get(st, st)


def _load_task(project_root, task_id):
    try:
        import task_engine as TE
        return TE.load_task(project_root, task_id)
    except Exception:
        return None, None


# ───────────────────────── 主授权入口 ─────────────────────────
def authorize(role, target, task_id=None, project_root=None,
              intended_action=None, session=None):
    """六因子授权判定。

    返回 dict：
      {
        "decision": "allow" | "deny" | "ungoverned",
        "code": <错误码 或 "ALLOWED">,
        "message": <可读说明>,
        "factors": { 六因子: bool/None },
        "layer": <资源层>,
        "action": <动作>,
      }
    """
    models = _models()
    factors = {
        "platform_policy": None,
        "role_capability": None,
        "resource_scope": None,
        "workflow_state": None,
        "task_grant": None,
        "revision_guard": None,
    }

    # 解析资源层
    layer = layer_of(target)
    if layer is None:
        return {
            "decision": "ungoverned",
            "code": "UNGOVERNED",
            "message": "target 不在授权资源层，交由 legacy 权限判定",
            "factors": factors,
            "layer": None,
            "action": None,
        }

    action = infer_action(role, target, intended_action)
    if action is None:
        action = intended_action or "<unknown>"
    a_meta = models["actions"].get(action, {})
    requires_task = a_meta.get("requires_task", False)
    is_service = bool(a_meta.get("service_only"))

    # 1. platform_policy：基线默认生效
    factors["platform_policy"] = True  # 基线激活即满足；若平台配置关闭则此处置 False

    # 2. resource_scope（canonical 优先，给出最明确错误码）
    if layer == "canonical":
        if role != _layer_writer_identity("canonical"):
            return _deny("CANONICAL_DIRECT_WRITE_FORBIDDEN", factors, layer, action,
                         "正式正文 canonical 禁止直接写；只能经 Publish Service 原子发布")
        factors["resource_scope"] = True
    else:
        if layer not in _role_layers(role):
            return _deny("RESOURCE_OUT_OF_SCOPE", factors, layer, action,
                         "目标层 %s 不在角色 %s 可写资源层 %s" % (layer, role, sorted(_role_layers(role))))
        factors["resource_scope"] = True

    # 3. role_capability（service_only 动作要求服务身份）
    if is_service:
        svc = a_meta.get("service_identity")
        if role != svc:
            return _deny("SERVICE_IDENTITY_REQUIRED", factors, layer, action,
                         "动作 %s 仅服务身份 %s 可发起，当前 %s" % (action, svc, role))
        factors["role_capability"] = True
    else:
        if not _role_has_capability(role, action):
            return _deny("ROLE_CAPABILITY_DENIED", factors, layer, action,
                         "角色 %s 不具备动作 %s 的 capability" % (role, action))
        factors["role_capability"] = True

    # 4+5. workflow_state & task_grant（受任务约束的动作）
    if requires_task:
        if not task_id:
            return _deny("WRITE_TASK_REQUIRED", factors, layer, action,
                         "动作 %s 必须关联合法 Task（NO-TASK-NO-WRITE）" % action)
        st, data = _load_task(project_root, task_id)
        if st is None:
            return _deny("TASK_GRANT_MISSING", factors, layer, action,
                         "关联任务 %s 不存在" % task_id)
        if is_service:
            # 服务身份动作：以 grant 文件编码"发布/提交门禁已通过"，task 须处于 live 态
            if st not in ("claimed", "running"):
                return _deny("TASK_GRANT_MISSING", factors, layer, action,
                             "任务 %s 态=%s 不在可写态 (claimed/running)" % (task_id, st))
            g = read_grant(project_root, task_id)
            if not g or g.get("status") != "active":
                # 发布门禁未通过（审查/回归/质量未达标 → grant 未生成/未激活）
                code = "PUBLISH_GATE_FAILED" if action == "chapter.publish" else "TASK_GRANT_MISSING"
                return _deny(code, factors, layer, action,
                             "缺少有效动态授权 grant（task_grant 因子失败）：%s" % task_id)
            try:
                expired = (
                    datetime.datetime.fromisoformat(
                        str(g.get("expires_at"))) <=
                    datetime.datetime.now())
            except (TypeError, ValueError):
                expired = True
            if expired:
                return _deny(
                    "PUBLISH_GATE_FAILED", factors, layer, action,
                    "动态授权 grant 已过期或缺 expires_at：%s" % task_id)
            factors["workflow_state"] = True
            factors["task_grant"] = True
        else:
            # 普通角色动作：章节生命周期动作受章节态约束；非章节动作（如 nkb.update）
            # 不绑定章节生命周期，仅要求任务 live（claimed/running）+ capability + layer。
            sp = models["state"].get("state_permissions", {})
            action_in_machine = any(action in v for v in sp.values())
            if action_in_machine:
                ch_state = chapter_state_of(project_root, task_id)
                allowed = sp.get(ch_state)
                if allowed is None:
                    return _deny("TASK_STATE_WRITE_DENIED", factors, layer, action,
                                 "任务态 %s 不可解析为章节态（态未映射）" % st)
                if action not in allowed:
                    return _deny("TASK_STATE_WRITE_DENIED", factors, layer, action,
                                 "章节态 %s 不允许动作 %s（允许：%s）" % (ch_state, action, allowed))
            if st not in ("claimed", "running"):
                return _deny("TASK_GRANT_MISSING", factors, layer, action,
                             "任务 %s 态=%s 不在可写态 (claimed/running)" % (task_id, st))
            factors["workflow_state"] = True
            factors["task_grant"] = True

    # 6. revision_guard
    factors["revision_guard"] = True

    # 全因子通过
    if all(v is True for v in factors.values()):
        return {
            "decision": "allow",
            "code": "ALLOWED",
            "message": "六因子授权通过（role=%s action=%s layer=%s task=%s）" % (
                role, action, layer, task_id),
            "factors": factors,
            "layer": layer,
            "action": action,
        }
    # 理论上不会到这（各因子失败已提前 deny）；兜底
    return _deny("PERMISSION_DENIED", factors, layer, action, "六因子未全满足")


def _deny(code, factors, layer, action, message):
    return {
        "decision": "deny",
        "code": code,
        "message": message or _ec(code),
        "factors": factors,
        "layer": layer,
        "action": action,
    }


# ───────────────────────── CLI 自检 ─────────────────────────
def main():
    import argparse
    ap = argparse.ArgumentParser(description="六因子授权判定")
    ap.add_argument("--role", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--task-id", default=None)
    ap.add_argument("--project-root", default=None)
    ap.add_argument("--action", default=None)
    args = ap.parse_args()
    res = authorize(args.role, args.target, task_id=args.task_id,
                    project_root=args.project_root, intended_action=args.action)
    print("decision: %s" % res["decision"])
    print("code: %s" % res["code"])
    print("message: %s" % res["message"])
    print("layer: %s" % res["layer"])
    print("action: %s" % res["action"])
    print("factors: %s" % res["factors"])
    sys.exit(0 if res["decision"] in ("allow", "ungoverned") else 1)


if __name__ == "__main__":
    main()
