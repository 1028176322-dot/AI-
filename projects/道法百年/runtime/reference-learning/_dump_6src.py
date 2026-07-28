import sys
sys.path.insert(0, r"E:/AI-Workspace/platform/AI-Creative-Platform/scripts/_common")
import _gov

profiles = {
    "庆余年": "qingyuniandu", "赘婿": "zhuixu", "烟雨楼": "yanyulou",
    "唐寅在异界": "tangyin", "孤儿院": "gueryuan", "镇北王": "zhenbei",
}
D = {}
for cn, pid in profiles.items():
    p = _gov.load_yaml(f"learning/candidates/{pid}.profile.yaml")
    D[cn] = p["style_dimensions"]

def rng(keyfn, label):
    vals = {c: keyfn(d) for c, d in D.items()}
    nums = [v for v in vals.values() if isinstance(v, (int, float))]
    if not nums:
        return
    lo, hi, mean = min(nums), max(nums), sum(nums)/len(nums)
    print(f"  {label}: min={lo:.3f} max={hi:.3f} mean={mean:.3f}  | " +
          " ".join(f"{c}={vals[c]:.3f}" for c in D))

print("== information_function ==")
for c, d in D.items():
    print(f"  {c}: {d['information_function']['distribution']}")
print("== description_selection ==")
for c, d in D.items():
    print(f"  {c}: {d['description_selection']['distribution']}")
print("== sensory_preference ==")
for c, d in D.items():
    print(f"  {c}: {d['sensory_preference']['distribution']}")
print("== emotion_expression ==")
for c, d in D.items():
    ee = d["emotion_expression"]
    print(f"  {c}: direct={ee['direct_emotion_signal']} behav={ee['behavioral_emotion_signal']} ratio={ee['behavior_to_direct_ratio']:.3f}")
print("== dialogue_method ==")
for c, d in D.items():
    dm = d["dialogue_method"]
    print(f"  {c}: blk/1k={dm['dialogue_blocks_per_1000_chars']:.2f} mean_len={dm['mean_dialogue_chars']:.1f} act_ins={dm['action_insertion_signal']}")
rng(lambda d: d["dialogue_method"]["dialogue_blocks_per_1000_chars"], "dialogue_blk_per_1k")
print("== metaphor /1k ==")
rng(lambda d: d["metaphor_mechanism"]["metaphors_per_1000_chars"], "metaphor_per_1k")
print("== omission /1k ==")
rng(lambda d: d["omission_method"]["omission_signals_per_1000_chars"], "omission_per_1k")
print("== scene_closure ==")
for c, d in D.items():
    sc = d["scene_closure"]
    print(f"  {c}: last_len={sc['last_sentence_length']} q={sc.get('question_hook')} choice={sc.get('choice_hook')} action={bool(sc.get('action_hook'))} ending_hook={sc.get('ending_hook_rate')}")
print("== prohibited_patterns ==")
for c, d in D.items():
    pp = d["prohibited_patterns"]
    print(f"  {c}: template={pp['template_expression_count']} hedge={pp['hedge_density']:.3f} rep_open={pp['repeated_sentence_opening_count']}")
print("== source_contribution_vector ==")
s = _gov.load_yaml("learning/candidates/learning-summary.yaml")
print("source_count:", s.get("source_count"))
print("weights:", s.get("source_contribution_vector"))
print("max single weight:", max(s.get("source_contribution_vector", {}).values()))
