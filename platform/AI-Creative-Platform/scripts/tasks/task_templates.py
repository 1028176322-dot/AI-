# -*- coding: utf-8 -*-
"""Task template registry.

Template file names are presentation details (some use hyphens, one uses an
underscore); the declared ``task_template.type`` is the authoritative key.
All task-system components use this module so template resolution cannot drift.
"""
import os

import _gov


HERE = os.path.dirname(os.path.abspath(__file__))
PLATFORM_ROOT = os.path.dirname(os.path.dirname(HERE))
TEMPLATES_DIR = os.path.join(PLATFORM_ROOT, "core", "task-system", "templates")


def registry():
    """Return ``{task_type: {template, path, stem}}`` for every valid template."""
    result = {}
    if not os.path.isdir(TEMPLATES_DIR):
        return result
    for filename in sorted(os.listdir(TEMPLATES_DIR)):
        if not filename.endswith(".task.yaml"):
            continue
        path = os.path.join(TEMPLATES_DIR, filename)
        data = _gov.load_yaml(path) or {}
        template = data.get("task_template") or data.get("template") or {}
        task_type = template.get("type")
        if not task_type:
            continue
        if task_type in result:
            raise RuntimeError("重复 task template type: %s" % task_type)
        result[task_type] = {
            "template": template,
            "path": path,
            "stem": filename[:-len(".task.yaml")],
        }
    return result


def resolve_type(name):
    """Resolve a declared type, filename stem, or hyphen/underscore alias."""
    entries = registry()
    if name in entries:
        return name
    normalized = str(name or "").replace("-", "_")
    for task_type, entry in entries.items():
        stem = entry["stem"].replace("-", "_")
        if normalized in (task_type.replace("-", "_"), stem):
            return task_type
    return None


def load(name):
    task_type = resolve_type(name)
    if not task_type:
        return {}
    return registry()[task_type]["template"]


def source_path(name):
    task_type = resolve_type(name)
    if not task_type:
        return None
    return registry()[task_type]["path"]


def next_types(name, event):
    template = load(name)
    raw = (template.get("next_tasks") or {}).get(event) or []
    if isinstance(raw, str):
        raw = [raw]
    result = []
    for target in raw:
        resolved = resolve_type(target)
        if resolved:
            result.append(resolved)
    return result
