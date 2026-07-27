# -*- coding: utf-8 -*-
"""
protected-manifest 唯一生产者（protected-manifest-build，纲要 §2.5，#22 Tier-1 已放行）。

设计要点
--------
- **唯一生产者**：本任务类型（manifest_build）是 analysis/style/<ch>/<task>/protected-manifest.yaml
  的唯一写者；其他任务（style-revise / ai-diagnose 等）只读其哈希。写权限由 authorize(manifest_build)
  的 candidate_path_permission 约束，且写路径只落 analysis/，绝不写 chapters/。
- **保真基线**：从草稿抽取 hard / functional / soft preserve（span_id + text 三级），供
  fidelity-review / final-regression / publish 比对。抽取自「草稿本身」（作品事实），不存
  参考原句（治理规则与 style_extract 同约束，见 §2.3）。
- **冲突裁决（不得静默选草稿，吸收审查六）**：NKB 硬事实 与 草稿新增事实冲突 → 以 NKB 为准，
  冲突项写入报告并置 MANIFEST_CONFLICT；章纲与 NKB 冲突同置 MANIFEST_CONFLICT。
- 可选：传入 event_log（Broker 密钥）则追加 MANIFEST_BUILD 不可变事件。
- 确定性默认抽取器（可注入 preserve_extractor / conflict_detector）。
"""
import hashlib
import json
import os
import re
import time

SCHEMA_ID = "style.protected-manifest"
SCHEMA_VERSION = "1.0.0"

_QUOTE = re.compile(r"[「\"'“”‘’]([^」\"'“”‘’]{1,40})[」\"'“”‘’]")
_DIGIT = re.compile(r"\d{2,}|[零一二三四五六七八九十百千]+年?")
_SENT = re.compile(r"(?<=[。！？；\.!?;])")
_HOOK = re.compile(r"(忽然|就在这时|与此同时|伏笔|猛地|蓦地)")
_SOFT = re.compile(r"(颜色|气味|触感|声音|光影|温度|寒意|暖意)")

try:
    import sys as _sys
    _sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "_common"))
    from _yaml_lite import dump as _ydump
except Exception:  # pragma: no cover
    _ydump = None


def _sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_obj(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _split_sentences(text):
    return [s.strip() for s in _SENT.split(text) if s.strip()]


def default_preserve_extractor(draft_text, known_entities=None):
    """从草稿本身抽取三级保真 span（确定性）。返回 (hard, functional, soft) 列表。"""
    hard, functional, soft = [], [], []
    seq = [0]

    def sid(prefix):
        seq[0] += 1
        return "%s:%d" % (prefix, seq[0])

    # hard：引号内的关键称谓/术语 + 数字事实 + 已知实体
    for m in _QUOTE.finditer(draft_text):
        hard.append({"span_id": sid("hard"), "text": m.group(0)})
    for m in _DIGIT.finditer(draft_text):
        hard.append({"span_id": sid("hard"), "text": m.group(0)})
    for ent in (known_entities or []):
        if ent and ent in draft_text:
            hard.append({"span_id": sid("hard"), "text": ent})

    # functional：场景钩子句 + 首/尾句
    sents = _split_sentences(draft_text)
    if sents:
        functional.append({"span_id": sid("fn"), "text": sents[0]})
        functional.append({"span_id": sid("fn"), "text": sents[-1]})
    for s in sents:
        if _HOOK.search(s):
            functional.append({"span_id": sid("fn"), "text": s})

    # soft：感官锚点句（可替换表现方式）
    for s in sents:
        if _SOFT.search(s):
            soft.append({"span_id": sid("soft"), "text": s})
    return hard, functional, soft


def default_conflict_detector(draft_text, nkb_hard_facts=None, outline_text=None):
    """返回冲突列表（确定性）。

    NKB 硬事实 与 草稿冲突：fact 提供 {text, expected} 且草稿在 text 附近出现不同数字 → 冲突。
    章纲 与 NKB 冲突：由调用方注入 outline 比对（原型默认不做深入语义比对，仅记录裁决规则）。
    """
    conflicts = []
    for f in (nkb_hard_facts or []):
        text = f.get("text")
        if not text or text not in draft_text:
            continue
        expected = f.get("expected")
        if expected is None:
            continue
        # 在 text 附近查找数字，若与 expected 不一致 → 冲突
        idx = draft_text.index(text)
        window = draft_text[idx:idx + 60]
        nums = _DIGIT.findall(window)
        if nums and expected not in nums:
            conflicts.append({
                "type": "nkb_vs_draft",
                "fact": text,
                "expected": expected,
                "found": nums,
                "resolution": "nkb_wins",
            })
    return conflicts


class ManifestBuildError(Exception):
    pass


def build_manifest(chapter_id, revision_cycle_id, producer_task_id, draft_text,
                   nkb_snapshot=None, outline_text="", builder_version="1.0.0",
                   model_id="", prompt_hash="", nkb_hard_facts=None,
                   preserve_extractor=None, conflict_detector=None, created_at=None):
    """产出 protected-manifest 合规 dict 或冲突报告。

    返回 dict：
      {status: "MANIFEST_READY"|"MANIFEST_CONFLICT", manifest: {...}|None,
       conflicts: [...]}
    """
    pe = preserve_extractor or default_preserve_extractor
    cd = conflict_detector or default_conflict_detector

    known = [f.get("text") for f in (nkb_hard_facts or []) if f.get("text")]
    hard, functional, soft = pe(draft_text, known_entities=known)

    conflicts = cd(draft_text, nkb_hard_facts=nkb_hard_facts, outline_text=outline_text)
    status = "MANIFEST_CONFLICT" if conflicts else "MANIFEST_READY"

    nkb_rev = (nkb_snapshot or {}).get("revision", "") if isinstance(nkb_snapshot, dict) else ""
    manifest = {
        "schema": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "chapter_id": chapter_id,
        "revision_cycle_id": revision_cycle_id,
        "producer_task_id": producer_task_id,
        "source_draft_sha256": _sha256(draft_text),
        "nkb_revision": nkb_rev,
        "nkb_snapshot_sha256": _sha256_obj(nkb_snapshot) if nkb_snapshot is not None else "",
        "outline_sha256": _sha256(outline_text),
        "builder_version": builder_version,
        "model_id": model_id,
        "prompt_hash": prompt_hash,
        "created_at": created_at if created_at is not None else time.time(),
        "hard_preserve": {"items": hard},
        "functional_preserve": {"items": functional},
        "soft_preserve": {"items": soft},
        "conflict_policy": {
            "nkb_wins": True,
            "outline_conflict": "MANIFEST_CONFLICT",
            "note": "NKB 硬事实优先；章纲与 NKB 冲突进入 MANIFEST_CONFLICT",
        },
    }
    return {"status": status, "manifest": manifest, "conflicts": conflicts}


def manifest_sha256(manifest):
    # 仅对保真内容（排除构建时刻等易变元数据）取哈希，使相同输入重建得到稳定基线哈希。
    stable = {k: v for k, v in manifest.items() if k != "created_at"}
    return _sha256_obj(stable)


def validate_manifest(d):
    errors = []
    required = ["chapter_id", "revision_cycle_id", "producer_task_id",
                "source_draft_sha256", "nkb_revision", "nkb_snapshot_sha256",
                "outline_sha256", "builder_version", "hard_preserve",
                "functional_preserve", "soft_preserve", "conflict_policy"]
    for k in required:
        if k not in d:
            errors.append("missing field: %s" % k)
    return (len(errors) == 0, errors)


def calculate_path(root, chapter_id, revision_cycle_id):
    return os.path.join(root, "analysis", "style", chapter_id, revision_cycle_id,
                        "protected-manifest.yaml")


def persist(result, root, chapter_id, revision_cycle_id):
    """落盘 manifest（或冲突报告）。调用方须已完成 authorize(manifest_build)。"""
    out_dir = os.path.join(root, "analysis", "style", chapter_id, revision_cycle_id)
    os.makedirs(out_dir, exist_ok=True)
    if result["status"] == "MANIFEST_READY" and result.get("manifest"):
        path = calculate_path(root, chapter_id, revision_cycle_id)
        content = _ydump(result["manifest"]) if _ydump else json.dumps(result["manifest"], ensure_ascii=False, indent=2)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"path": path, "status": "MANIFEST_READY"}
    # 冲突：写冲突报告（仍落 analysis/style，供人工/调度处理）
    path = os.path.join(out_dir, "manifest-conflict.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return {"path": path, "status": "MANIFEST_CONFLICT"}


def append_build_event(event_log, manifest, actor_id, task_id):
    if event_log is None:
        return None
    msha = manifest_sha256(manifest)
    return event_log.append(
        "MANIFEST_BUILD", actor_id or manifest.get("producer_task_id"),
        task_id or manifest.get("producer_task_id"),
        operation="manifest_build",
        resource_refs=[manifest.get("revision_candidate_ref") if "revision_candidate_ref" in manifest else None,
                       "analysis/style/%s/%s/protected-manifest.yaml"
                       % (manifest.get("chapter_id"), manifest.get("revision_cycle_id"))],
        result="ok",
        details={"manifest_sha256": msha})
