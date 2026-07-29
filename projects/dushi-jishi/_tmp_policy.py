# -*- coding: utf-8 -*-
import io
path = r"d:\AI-Workspace\projects\dushi-jishi\sources\outline\_intake\planning-policy.yaml"
s = io.open(path, "r", encoding="utf-8").read()
assert "  total_chapters: 1000\n" in s, "main total_chapters line not found"
s = s.replace("  total_chapters: 1000\n", "  total_chapters: 1035\n")
io.open(path, "w", encoding="utf-8", newline="\n").write(s)
# verify
t = io.open(path, "r", encoding="utf-8").read()
print("total_chapters now:", "  total_chapters: 1035" in t)
print("floor retained:", "  total_chapters_floor: 1000" in t)
