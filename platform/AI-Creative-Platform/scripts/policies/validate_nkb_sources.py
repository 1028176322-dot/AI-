# -*- coding: utf-8 -*-
"""
validate_nkb_sources.py — NKB 源文件 / 候选事实质量门禁校验

对应规范：
  core/knowledge/NKB信息源与入库规范.md
  core/contracts/nkb-source.schema.yaml      （sources/ 门禁）
  core/contracts/nkb-candidate.schema.yaml   （NKB/candidates/ 结构）

职责：
  1. 扫描项目 sources/ 下所有 *.yaml，按 nkb-source.schema.yaml 校验：
     - document 段 common_required 必备字段
     - document.status 合法枚举
     - document.version 为整数
     - document.project_id 与项目一致（可选 --project）
     - 业务 type 对应必填字段（type_required）
     - 事实类 type 必须 status=approved（否则 WARN）
     - 禁止推测词（forbidden_patterns，非 non_fact 且非 approved 时 FAIL）
     - document.id 跨文件唯一（重复 FAIL）
  2. 扫描 NKB/candidates/ 下所有 *.yaml，按 nkb-candidate.schema.yaml 校验：
     - 顶层 required 必备字段
     - source / classification 子段必备字段
     - operation / target_component / fact_type / status 枚举合法

入口（经 platform_cli 委托）：
  python tools/platform_cli.py nkb --project-root <项目根>
独立运行：
  python tools/validate_nkb_sources.py --project-root <项目根> [--project novel-dsf]

退出码：存在 FAIL → 1；否则 0（WARN 不致命）。
"""
import os
import sys
import argparse

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
import _gov  # noqa: E402

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"


def _get(d, dotted):
    cur = d
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _scan_yaml(root):
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.endswith(".yaml") or f.endswith(".yml"):
                out.append(os.path.join(dirpath, f))
    return out


def check_source_file(path, schema, project_id, issues):
    try:
        data = _gov.load_yaml(path)
    except Exception as e:
        issues.append((FAIL, path, "YAML 解析失败：%s" % e))
        return
    if not isinstance(data, dict):
        issues.append((FAIL, path, "根节点不是映射"))
        return

    doc = data.get("document")
    if not isinstance(doc, dict):
        issues.append((FAIL, path, "缺少 document 元数据段（§19.1）"))
        return

    # common_required
    for f in schema.get("common_required", []) or []:
        if doc.get(f) is None:
            issues.append((FAIL, path, "document 缺字段 %s" % f))

    # status 枚举
    st = doc.get("status")
    if st not in (schema.get("allowed_status") or []):
        issues.append((FAIL, path, "document.status=%r 非法（允许：%s）" % (st, schema.get("allowed_status"))))

    # version 整数
    if not isinstance(doc.get("version"), int):
        issues.append((FAIL, path, "document.version=%r 非整数" % doc.get("version")))

    # project_id 一致性
    if project_id and doc.get("project_id") != project_id:
        issues.append((WARN, path, "document.project_id=%r 与项目 %r 不一致" % (doc.get("project_id"), project_id)))

    # type_required 业务必填
    t = doc.get("type")
    treq = (schema.get("type_required") or {}).get(t)
    if treq:
        for fpath in treq:
            if _get(data, fpath) is None:
                issues.append((FAIL, path, "业务必填 %s 缺失（type=%s）" % (fpath, t)))

    # 事实类必须 approved
    if t in (schema.get("fact_types") or []) and st != "approved":
        issues.append((WARN, path, "事实类(type=%s) status=%s 非 approved，不作为事实源" % (t, st)))

    # 禁止推测词（non_fact 与 approved 豁免）
    if t not in (schema.get("non_fact_types") or []) and st != "approved":
        try:
            text = open(path, "r", encoding="utf-8").read()
        except Exception:
            text = ""
        for pat in schema.get("forbidden_patterns", []) or []:
            if pat in text:
                issues.append((FAIL, path, "含推测词 %r 但未标记计划态（§19.2）" % pat))
                break


def check_candidate_file(path, schema, issues):
    try:
        data = _gov.load_yaml(path)
    except Exception as e:
        issues.append((FAIL, path, "YAML 解析失败：%s" % e))
        return
    if not isinstance(data, dict):
        issues.append((FAIL, path, "根节点不是映射"))
        return

    cand = data.get("candidate")
    if not isinstance(cand, dict):
        issues.append((FAIL, path, "缺少 candidate 段（§15）"))
        return

    # 顶层 required
    for f in schema.get("required", []) or []:
        if cand.get(f) is None:
            issues.append((FAIL, path, "candidate 缺字段 %s" % f))

    # operation 枚举
    op = cand.get("operation")
    if op not in (schema.get("allowed_operations") or []):
        issues.append((FAIL, path, "operation=%r 非法（允许：%s）" % (op, schema.get("allowed_operations"))))

    # target_component 枚举
    tc = cand.get("target_component")
    if tc not in (schema.get("allowed_target_components") or []):
        issues.append((FAIL, path, "target_component=%r 非法（允许：%s）" % (tc, schema.get("allowed_target_components"))))

    # status 枚举
    st = cand.get("status")
    if st not in (schema.get("allowed_status") or []):
        issues.append((FAIL, path, "status=%r 非法（允许：%s）" % (st, schema.get("allowed_status"))))

    # source 段
    src = cand.get("source")
    if isinstance(src, dict):
        for f in schema.get("source_required", []) or []:
            if src.get(f) is None:
                issues.append((FAIL, path, "source 缺字段 %s" % f))
    else:
        issues.append((FAIL, path, "candidate.source 缺失或非映射"))

    # classification 段
    clf = cand.get("classification")
    if isinstance(clf, dict):
        for f in schema.get("classification_required", []) or []:
            if clf.get(f) is None:
                issues.append((FAIL, path, "classification 缺字段 %s" % f))
        ft = clf.get("fact_type")
        if ft not in (schema.get("allowed_fact_types") or []):
            issues.append((FAIL, path, "classification.fact_type=%r 非法（允许：%s）" % (ft, schema.get("allowed_fact_types"))))
    else:
        issues.append((FAIL, path, "candidate.classification 缺失或非映射"))


def main():
    ap = argparse.ArgumentParser(prog="validate_nkb_sources",
                                 description="NKB 源文件/候选事实质量门禁校验")
    ap.add_argument("--sources", help="sources 目录（默认 <project-root>/sources）")
    ap.add_argument("--schema", help="nkb-source.schema.yaml（默认平台 core/contracts）")
    ap.add_argument("--candidates", help="候选事实目录（默认 <project-root>/NKB/candidates）")
    ap.add_argument("--candidate-schema", help="nkb-candidate.schema.yaml")
    ap.add_argument("--project", help="期望 project_id（用于一致性校验）")
    ap.add_argument("--project-root", help="项目根（自动推导 sources/ 与 NKB/candidates/）")
    args = ap.parse_args()

    plat = _gov.find_platform_root()
    schema_path = args.schema or os.path.join(plat, "core", "contracts", "nkb-source.schema.yaml")
    cand_schema_path = args.candidate_schema or os.path.join(plat, "core", "contracts", "nkb-candidate.schema.yaml")

    if not os.path.isfile(schema_path):
        sys.stderr.write("ERROR: 源 schema 不存在：%s\n" % schema_path)
        sys.exit(2)
    schema = _gov.load_yaml(schema_path)
    cand_schema = None
    if os.path.isfile(cand_schema_path):
        cand_schema = _gov.load_yaml(cand_schema_path)

    issues = []

    # ── sources/ 模式 ──
    sources_dir = args.sources
    if not sources_dir and args.project_root:
        sources_dir = os.path.join(args.project_root, "sources")
    if sources_dir and os.path.isdir(sources_dir):
        files = _scan_yaml(sources_dir)
        id_seen = {}
        for p in files:
            check_source_file(p, schema, args.project, issues)
            try:
                d = _gov.load_yaml(p) or {}
                did = (d.get("document") or {}).get("id")
                if did:
                    id_seen.setdefault(did, []).append(p)
            except Exception:
                pass
        for did, ps in id_seen.items():
            if len(ps) > 1:
                issues.append((FAIL, ", ".join(ps), "document.id=%s 重复（§19.2）" % did))

    # ── candidates/ 模式 ──
    cand_dir = args.candidates
    if not cand_dir and args.project_root:
        cand_dir = os.path.join(args.project_root, "NKB", "candidates")
    if cand_dir and os.path.isdir(cand_dir):
        if cand_schema is None:
            sys.stderr.write("ERROR: 候选 schema 不存在：%s\n" % cand_schema_path)
            sys.exit(2)
        for p in _scan_yaml(cand_dir):
            check_candidate_file(p, cand_schema, issues)

    if not sources_dir and not cand_dir:
        sys.stderr.write("ERROR: 未指定 --sources / --candidates / --project-root\n")
        sys.exit(2)

    # ── 输出 ──
    fails = [i for i in issues if i[0] == FAIL]
    warns = [i for i in issues if i[0] == WARN]
    for sym, path, msg in issues:
        print("[%s] %s : %s" % (sym, path, msg))
    print("─" * 60)
    print("总计 %d 项检查，FAIL %d，WARN %d" % (len(issues), len(fails), len(warns)))
    if fails:
        print("结果：FAIL —— 源文件/候选事实未通过门禁，不得进入提取流程。")
        sys.exit(1)
    print("结果：PASS —— 门禁通过（WARN 不致命）。")
    sys.exit(0)


if __name__ == "__main__":
    main()
