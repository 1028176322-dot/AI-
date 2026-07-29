# -*- coding: utf-8 -*-
import io

path = r"d:\AI-Workspace\projects\dushi-jishi\lifecycle\design\AUTHOR_DECISIONS.yaml"

approved = [
    "ability-commercial-build-001",
    "arc-protagonist-001",
    "canon-no-supernatural-001",
    "canon-realism-001",
    "char-lujingshan-001",
    "char-luzheng-001",
    "conflict-inner-001",
    "conflict-prison-survival-001",
    "conflict-protagonist-group-001",
    "foreshadow-family-001",
    "foreshadow-insider-001",
    "foreshadow-lookalike-001",
    "reader-state-001",
    "world-lingang-001",
]

content = '''author_decisions:
  schema: design-expansion@1.0.0
  explicit_user_approval: true
  decided_by: user
  decided_at: "2026-07-28T15:44:00"
  approved:
'''
for cid in approved:
    content += "    - %s\n" % cid
content += '''  rejected: []
  note: "用户于 2026-07-28T15:43 明确口令：全部批准 14 项。含 world-lingang-001（已扩为多层级跨城世界地图）。"
'''

with io.open(path, "w", encoding="utf-8", newline="\n") as f:
    f.write(content)

# verify
data = None
import sys
sys.path.insert(0, r"platform/AI-Creative-Platform/scripts/_common")
import _yaml_lite as yl
data = yl.load(open(path, encoding="utf-8").read())
body = data["author_decisions"]
print("explicit_user_approval:", body.get("explicit_user_approval"))
print("approved count:", len(body.get("approved", [])))
print("all 14:", sorted(body["approved"]) == sorted(approved))
