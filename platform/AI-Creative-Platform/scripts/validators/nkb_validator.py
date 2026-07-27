# -*- coding: utf-8 -*-
"""Validate canonical NKB components, records, provenance, and references."""
import argparse
import os
import re
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_ROOT = os.path.dirname(HERE)
for child in os.listdir(SCRIPTS_ROOT):
    path = os.path.join(SCRIPTS_ROOT, child)
    if os.path.isdir(path) and path not in sys.path:
        sys.path.insert(0, path)

import _gov


def _severity(strict, legacy):
    return "fail" if strict else legacy


def _record_ids(components):
    result = set()
    for records in components.values():
        for record in records:
            if isinstance(record, dict) and record.get("id"):
                result.add(str(record["id"]))
    return result


def validate_project(project_root):
    platform_root = _gov.find_platform_root()
    schema_path = os.path.join(
        platform_root, "core", "contracts", "nkb-components.schema.yaml")
    registry_path = os.path.join(
        platform_root, "schemas", "nkb", "nkb-manifest.yaml")
    schema = _gov.load_yaml(schema_path) or {}
    registry = _gov.load_yaml(registry_path) or {}
    strict = os.path.isfile(os.path.join(project_root, "PROJECT_LAYOUT.yaml"))
    legacy = schema.get("legacy") or {}
    nkb_dir = os.path.join(project_root, "NKB")
    findings = []
    components = {}
    project = _gov.load_yaml(
        os.path.join(project_root, "project.yaml")) or {}
    project_id = (
        (project.get("project") or {}).get("id") or project.get("id"))

    expected = [
        item.get("name") for item in (registry.get("components") or [])
        if isinstance(item, dict) and item.get("name")
    ]
    if not os.path.isdir(nkb_dir):
        return {
            "schema": "nkb-validation@1.0.0",
            "strict": strict,
            "findings": [{"severity": "fail", "code": "NKB_DIR_MISSING",
                          "detail": "NKB directory is missing"}],
            "gate": {"decision": "block"},
        }

    manifest_path = os.path.join(nkb_dir, "manifest.yaml")
    manifest = _gov.load_yaml(manifest_path) if os.path.isfile(
        manifest_path) else {}
    if not manifest:
        findings.append({
            "severity": _severity(strict, "warn"),
            "code": "MANIFEST_MISSING",
            "detail": "NKB/manifest.yaml is missing or empty",
        })
    else:
        nkb_meta = manifest.get("nkb")
        if not isinstance(nkb_meta, dict):
            findings.append({
                "severity": _severity(strict, "warn"),
                "code": "MANIFEST_NKB_INVALID",
                "detail": "manifest.nkb must be a mapping",
            })
            nkb_meta = {}
        if str(nkb_meta.get("schema_version")) != str(
                registry.get("schema_version")):
            findings.append({
                "severity": _severity(strict, "warn"),
                "code": "MANIFEST_SCHEMA_VERSION_DRIFT",
                "detail": "%s != %s" % (
                    nkb_meta.get("schema_version"),
                    registry.get("schema_version")),
            })
        if project_id and nkb_meta.get("project_id") != project_id:
            findings.append({
                "severity": _severity(strict, "warn"),
                "code": "MANIFEST_PROJECT_ID_MISMATCH",
                "detail": "%s != %s" % (
                    nkb_meta.get("project_id"), project_id),
            })
        component_manifest = manifest.get("components")
        if not isinstance(component_manifest, dict):
            findings.append({
                "severity": _severity(strict, "warn"),
                "code": "MANIFEST_COMPONENTS_INVALID",
                "detail": "manifest.components must be a mapping",
            })
            component_manifest = {}
        for name in expected:
            entry = component_manifest.get(name)
            if not isinstance(entry, dict):
                findings.append({
                    "severity": _severity(strict, "warn"),
                    "code": "MANIFEST_COMPONENT_MISSING",
                    "component": name,
                    "detail": "manifest.components.%s is missing" % name,
                })
            elif entry.get("file") != "%s.yaml" % name:
                findings.append({
                    "severity": _severity(strict, "warn"),
                    "code": "MANIFEST_COMPONENT_FILE_DRIFT",
                    "component": name,
                    "detail": "%s != %s.yaml" % (
                        entry.get("file"), name),
                })

    for name in expected:
        path = os.path.join(nkb_dir, "%s.yaml" % name)
        if not os.path.isfile(path):
            findings.append({
                "severity": _severity(
                    strict, legacy.get("missing_component_severity", "warn")),
                "code": "COMPONENT_MISSING",
                "component": name,
                "detail": "%s.yaml is missing" % name,
            })
            components[name] = []
            continue
        try:
            data = _gov.load_yaml(path) or {}
        except Exception as exc:
            findings.append({
                "severity": "fail", "code": "YAML_INVALID",
                "component": name, "detail": str(exc)})
            components[name] = []
            continue
        if str(data.get("schema_version")) != str(registry.get("schema_version")):
            findings.append({
                "severity": _severity(strict, "warn"),
                "code": "SCHEMA_VERSION_DRIFT", "component": name,
                "detail": "%s != %s" % (
                    data.get("schema_version"), registry.get("schema_version")),
            })
        if project_id and data.get("project_id") != project_id:
            findings.append({
                "severity": _severity(strict, "warn"),
                "code": "COMPONENT_PROJECT_ID_MISMATCH",
                "component": name,
                "detail": "%s != %s" % (
                    data.get("project_id"), project_id),
            })
        records = data.get("records")
        if not isinstance(records, list):
            findings.append({
                "severity": "fail", "code": "RECORDS_NOT_LIST",
                "component": name, "detail": "records must be a list"})
            records = []
        components[name] = records

    all_ids = _record_ids(components)
    seen = {}
    common = schema.get("common") or {}
    specs = schema.get("components") or {}
    pending_refs = []
    for component, records in components.items():
        spec = specs.get(component) or {}
        for index, record in enumerate(records):
            where = "%s.records[%d]" % (component, index)
            if not isinstance(record, dict):
                findings.append({
                    "severity": "fail", "code": "RECORD_NOT_MAPPING",
                    "component": component, "detail": where})
                continue
            rid = record.get("id")
            if rid:
                if str(rid) in seen:
                    findings.append({
                        "severity": "fail", "code": "DUPLICATE_ID",
                        "component": component,
                        "detail": "%s also appears at %s" % (rid, seen[str(rid)]),
                    })
                seen[str(rid)] = where
                pattern = common.get("id_pattern")
                if pattern and not re.match(pattern, str(rid)):
                    findings.append({
                        "severity": _severity(strict, "warn"),
                        "code": "ID_FORMAT_INVALID",
                        "component": component,
                        "record_id": rid,
                        "detail": "%s does not match %s" % (
                            rid, pattern),
                    })
            required = list(common.get("required") or []) + list(
                spec.get("required") or [])
            for field in required:
                if record.get(field) in (None, ""):
                    findings.append({
                        "severity": _severity(
                            strict, legacy.get("missing_field_severity", "warn")),
                        "code": "FIELD_MISSING", "component": component,
                        "record_id": rid, "detail": "%s.%s" % (where, field),
                    })
            required_any = spec.get("required_any") or []
            if required_any and not any(
                    record.get(field) not in (None, "") for field in required_any):
                findings.append({
                    "severity": _severity(strict, "warn"),
                    "code": "FIELD_GROUP_MISSING", "component": component,
                    "record_id": rid, "detail": "%s requires one of %s" % (
                        where, required_any),
                })
            source = record.get("source")
            if isinstance(source, dict):
                for field in common.get("source_required") or []:
                    if source.get(field) in (None, ""):
                        findings.append({
                            "severity": _severity(strict, "warn"),
                            "code": "SOURCE_FIELD_MISSING",
                            "component": component, "record_id": rid,
                            "detail": "%s.source.%s" % (where, field),
                        })
                allowed_approval = common.get(
                    "approval_status_enum") or []
                approval = source.get("approval_status")
                if approval not in allowed_approval:
                    findings.append({
                        "severity": _severity(strict, "warn"),
                        "code": "SOURCE_APPROVAL_INVALID",
                        "component": component,
                        "record_id": rid,
                        "detail": "%s.source.approval_status=%r" % (
                            where, approval),
                    })
                source_file = source.get("source_file")
                if (source_file and not str(source_file).startswith(
                        ("http://", "https://"))):
                    source_path = (
                        str(source_file) if os.path.isabs(str(source_file))
                        else os.path.join(project_root, str(source_file)))
                    if not os.path.exists(source_path):
                        findings.append({
                            "severity": _severity(strict, "warn"),
                            "code": "SOURCE_FILE_MISSING",
                            "component": component,
                            "record_id": rid,
                            "detail": "%s -> %s" % (
                                where, source_file),
                        })
            elif source not in (None, ""):
                findings.append({
                    "severity": _severity(strict, "warn"),
                    "code": "SOURCE_INVALID",
                    "component": component,
                    "record_id": rid,
                    "detail": "%s.source must be a mapping" % where,
                })
            for enum_key, allowed in spec.items():
                if not enum_key.endswith("_enum"):
                    continue
                field = enum_key[:-5]
                value = record.get(field)
                if value not in (None, "") and value not in allowed:
                    findings.append({
                        "severity": _severity(strict, "warn"),
                        "code": "ENUM_INVALID",
                        "component": component,
                        "record_id": rid,
                        "detail": "%s.%s=%r not in %s" % (
                            where, field, value, allowed),
                    })
            for field in spec.get("references") or []:
                value = record.get(field)
                if value not in (None, ""):
                    pending_refs.append((component, rid, field, str(value)))
            for field in spec.get("references_many") or []:
                values = record.get(field) or []
                if not isinstance(values, list):
                    findings.append({
                        "severity": "fail", "code": "REFERENCE_LIST_INVALID",
                        "component": component, "record_id": rid,
                        "detail": "%s.%s must be a list" % (where, field),
                    })
                    continue
                for value in values:
                    if isinstance(value, str):
                        pending_refs.append((component, rid, field, value))

    for component, rid, field, target in pending_refs:
        if target not in all_ids:
            findings.append({
                "severity": _severity(
                    strict, legacy.get("broken_reference_severity", "warn")),
                "code": "BROKEN_REFERENCE", "component": component,
                "record_id": rid,
                "detail": "%s.%s -> %s" % (rid, field, target),
            })
    errors = sum(item["severity"] == "fail" for item in findings)
    warnings = sum(item["severity"] == "warn" for item in findings)
    return {
        "schema": "nkb-validation@1.0.0",
        "strict": strict,
        "schema_version": registry.get("schema_version"),
        "components_expected": expected,
        "records": sum(len(items) for items in components.values()),
        "findings": findings,
        "summary": {"errors": errors, "warnings": warnings},
        "gate": {"decision": "block" if errors else "proceed"},
    }


def main():
    parser = argparse.ArgumentParser(prog="nkb-validator")
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()
    report = validate_project(os.path.abspath(args.project_root))
    for item in report["findings"]:
        print("[%s] %s %s" % (
            item["severity"].upper(), item["code"], item["detail"]))
    print("NKB VALIDATION: %s errors=%d warnings=%d records=%d" % (
        report["gate"]["decision"],
        report["summary"]["errors"], report["summary"]["warnings"],
        report["records"]))
    sys.exit(1 if report["gate"]["decision"] == "block" else 0)


if __name__ == "__main__":
    main()
