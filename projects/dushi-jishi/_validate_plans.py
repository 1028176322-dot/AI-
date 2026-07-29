# -*- coding: utf-8 -*-
"""轻量校验已生成章纲：技术兼容 + anti_template（连续3章同首尾/场景）。"""
import os, re, sys
sys.path.insert(0, r"D:/AI-Workspace/platform/AI-Creative-Platform/scripts/_common")
sys.path.insert(0, r"D:/AI-Workspace/platform/AI-Creative-Platform/scripts/project")
sys.path.insert(0, r"D:/AI-Workspace/platform/AI-Creative-Platform/scripts/platform")
import _gov
import writing_strategy as ws

ROOT = r"D:/AI-Workspace/projects/dushi-jishi"
COMPAT = ws.TECHNIQUE_COMPATIBILITY
OPENING_FIT = ws.OPENING_FIT
ALL_T = set(ws.ALL_TECHNIQUES)
ENDING_MODES = {"danger","revelation","decision","consequence","payoff",
    "emotional_afterglow","relationship_shift","cognitive_reversal",
    "new_goal","world_state_change","quiet_anomaly","action_commitment"}

plans = {}
for f in os.listdir(os.path.join(ROOT, "sources/outline/chapters")):
    m = re.match(r"PLAN-CH-(\d+)\.yaml", f)
    if not m: continue
    n = int(m.group(1))
    d = _gov.load_yaml(os.path.join(ROOT, "sources/outline/chapters", f))
    plans[n] = d

bad_key = 0; bad_tech = 0; bad_open = 0; bad_close = 0; bad_supp = 0
issues = []
for n in range(1, 1036):
    if n not in plans:
        issues.append("MISSING %d" % n); continue
    p = plans[n]
    ns = p.get("narrative_strategy", {})
    od = p.get("opening_design", {})
    ed = p.get("ending_design", {})
    sc = (p.get("scenes") or [{}])[0]
    st = sc.get("type")
    dom = ns.get("dominant_technique")
    supp = ns.get("supporting_techniques") or []
    entry = od.get("entry_mode")
    closure = ed.get("closure_mode")
    if st is None or dom is None or entry is None or closure is None:
        bad_key += 1; issues.append("KEY %d st=%s dom=%s entry=%s close=%s" % (n, st, dom, entry, closure)); continue
    if dom not in COMPAT.get(st, set()):
        bad_tech += 1; issues.append("TECH %d %s/%s" % (n, st, dom))
    if entry not in OPENING_FIT.get(st, set()):
        bad_open += 1; issues.append("OPEN %d %s/%s" % (n, st, entry))
    if closure not in ENDING_MODES:
        bad_close += 1; issues.append("CLOSE %d %s" % (n, closure))
    if not set(supp).issubset(ALL_T) or dom in supp:
        bad_supp += 1; issues.append("SUPP %d" % n)

# anti_template: 连续3章同 (entry, closure, scene) 或同 dominant
seq = [(
    plans[n]["opening_design"].get("entry_mode"),
    plans[n]["ending_design"].get("closure_mode"),
    (plans[n].get("scenes") or [{}])[0].get("type"),
    plans[n]["narrative_strategy"].get("dominant_technique"),
) for n in range(1, 1036) if n in plans]

trip_same_openclose = 0
trip_same_dom = 0
viol = []
for i in range(2, len(seq)):
    a, b, c = seq[i-2], seq[i-1], seq[i]
    if (a[0], a[1], a[2]) == (b[0], b[1], b[2]) == (c[0], c[1], c[2]):
        trip_same_openclose += 1; viol.append("3CONSEC-OC %d-%d" % (i-1, i+1))
    if a[3] == b[3] == c[3]:
        trip_same_dom += 1; viol.append("3CONSEC-DOM %d-%d" % (i-1, i+1))

print("checked plans:", len(plans))
print("bad_key=%d bad_tech=%d bad_open=%d bad_close=%d bad_supp=%d" % (bad_key, bad_tech, bad_open, bad_close, bad_supp))
print("3-consec same(open/close/scene)=%d  3-consec same dominant=%d" % (trip_same_openclose, trip_same_dom))
if issues[:20]: print("ISSUES(sample):", issues[:20])
if viol[:20]: print("VIOL(sample):", viol[:20])
print("RESULT:", "PASS" if (bad_key+bad_tech+bad_open+bad_close+bad_supp+trip_same_openclose+trip_same_dom)==0 else "FAIL")
