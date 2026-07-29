"""重建 dushi-jishi 的 urban 风格加权原型 (5 源) + learning-summary。

仅依赖平台内部模块，复用 reference_learning._build_archetype 的聚合逻辑。
源 id 固定：ru_yu, nu_hai, cai_fa, xie_di, shu_xue（各 0.2）。
"""
import os, sys

ROOT = r"D:/AI-Workspace"
PROJ = r"D:/AI-Workspace/projects/dushi-jishi"
CAND = os.path.join(PROJ, "learning", "candidates")
OUT_DIR = CAND

sys.path.insert(0, os.path.join(ROOT, "platform", "AI-Creative-Platform", "scripts", "_common"))
sys.path.insert(0, os.path.join(ROOT, "platform", "AI-Creative-Platform", "scripts", "learning"))
import _gov
import style_extract
import reference_learning as RL

SOURCE_IDS = ["ru_yu", "nu_hai", "cai_fa", "xie_di", "shu_xue"]
GENRE = "urban"


def main():
    # 读取 5 份 profile
    profiles = []
    for sid in SOURCE_IDS:
        p = _gov.load_yaml(os.path.join(CAND, "%s.profile.yaml" % sid))
        if not p:
            raise SystemExit("MISSING profile for %s" % sid)
        profiles.append(p)

    # 复用平台聚合逻辑构造 archetype
    archetype = RL._build_archetype(profiles, GENRE)
    archetype_dir = os.path.join(OUT_DIR, "style-archetypes")
    os.makedirs(archetype_dir, exist_ok=True)
    archetype_path = os.path.join(archetype_dir, "%s.archetype.yaml" % GENRE)
    _gov.dump_yaml(archetype_path, archetype)

    # 写 learning-summary.yaml（5 源各 0.2；候选规则先留空，等 promote 门禁处理）
    weights = {sid: round(1.0 / len(SOURCE_IDS), 4) for sid in SOURCE_IDS}
    summary = {
        "schema": "reference-learning-summary@2.0.0",
        "genre": GENRE,
        "generated_at": RL._now(),
        "source_profiles": ["%s.profile.yaml" % s for s in SOURCE_IDS],
        "source_count": len(SOURCE_IDS),
        "archetype": "style-archetypes/%s.archetype.yaml" % GENRE,
        "source_contribution_vector": weights,
        "style_rule_candidate_ids": [],
        "style_rule_candidates_require_review": True,
        "writing_candidates": [],
        "review_candidates": [],
        "promotion": {
            "state": "candidate",
            "rule": "参考书数量不等于项目验证数；先进入项目试验，再按 memory 晋升门槛升级。",
        },
    }
    out = os.path.join(OUT_DIR, "learning-summary.yaml")
    _gov.dump_yaml(out, summary)

    print("archetype sources=%d weights=%s" % (archetype["source_count"], archetype["source_contribution_vector"]))
    print("summary ->", out)


if __name__ == "__main__":
    main()
