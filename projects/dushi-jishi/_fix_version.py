# -*- coding: utf-8 -*-
"""把 sources/design 下（非 _ 开头目录）所有 yaml 的 document.version
   由 semver 字符串(如 1.0.0 / 1.1.0) 改为整数(主版本号)。仅改 version 行，保留其余。"""
import os, re

ROOT = r"D:\AI-Workspace\projects\dushi-jishi\sources\design"
pat = re.compile(r'^(\s*version:\s*)[0-9]+\.[0-9]+(?:\.[0-9]+)?\s*$', re.M)

changed = 0
for dp, dirs, fs in os.walk(ROOT):
    dirs[:] = [d for d in dirs if not d.startswith("_")]
    for f in fs:
        if not f.endswith((".yaml", ".yml")):
            continue
        path = os.path.join(dp, f)
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        new = pat.sub(r'\g<1>1', text)
        if new != text:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(new)
            changed += 1
            print("fixed version: %s" % os.path.relpath(path, ROOT))
print("total fixed: %d" % changed)
