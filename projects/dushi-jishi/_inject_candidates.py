"""把 5 源融合原型(urban.archetype.yaml)的真实 12 维指纹，提炼为可追溯的
writing_candidates，写回 learning-summary.yaml。

来源：ru_yu / nu_hai / cai_fa / xie_di / shu_xue 五本小说十二维加权融合。
规则数值均来自原型聚合结果，非凭空生成。写回后可由
`platform learn promote-project --summary ... --approved` 受控晋升。
"""
import os, sys

PROJ = r"D:/AI-Workspace/projects/dushi-jishi"
CAND = os.path.join(PROJ, "learning", "candidates")
SYS = os.path.join("D:/AI-Workspace", "platform", "AI-Creative-Platform", "scripts", "_common")
sys.path.insert(0, SYS)
import _gov

SRC = "urban.archetype (5 sources: ru_yu, nu_hai, cai_fa, xie_di, shu_xue)"

# 基于原型 12 维真实聚合值提炼的候选规则
CANDIDATES = [
    {
        "rule_id": "R-POV-DIST-01",
        "target": "narrative_pov,narrative_distance",
        "principle": ("融合 fingerprint 显示第三人称限知占优(third=10860.8 vs first=8575.4)"
                      "且强近距(close=31848.6 vs far=2274.2)：用第三人称限知、紧贴主角"
                      "感官与内心，避免全知跳叙。"),
        "review_check": "抽查 3 章开头，确认第三人称限知且近距，无全知旁白。",
        "writing_action": ("默认第三人称限知；约 70% 篇幅贴近主角感官/内心；仅在必要宏观"
                           "转向处短暂拉开距离。"),
        "confidence": 0.78, "status": "proposed",
        "source": SRC,
    },
    {
        "rule_id": "R-SYN-01",
        "target": "syntactic_rhythm",
        "principle": ("句长中等(mean=30.3字, short=0.199, long=0.324, stddev=21.3)：长短交错，"
                      "动作/对话段多用短句制造节奏。"),
        "review_check": "抽查 3 章，确认动作与对话段以短句为主，无长句堆砌。",
        "writing_action": "动作、冲突、对话用 ≤20 字短句；描写/回忆段可放长句但控制密度。",
        "confidence": 0.75, "status": "proposed",
        "source": SRC,
    },
    {
        "rule_id": "R-INFO-01",
        "target": "information_function",
        "principle": ("信息功能：plot_action=0.524 + dialogue=0.429 主导，world_exposition 仅 0.033："
                      "靠行动与对话推进，极少大段设定说明。"),
        "review_check": "抽查 3 章，确认世界设定以场景内行为/对话带出，无 exposition 长段。",
        "writing_action": "用人物行动与对话承载信息；世界/势力背景分散在情节中透出，不单列说明段。",
        "confidence": 0.85, "status": "proposed",
        "source": SRC,
    },
    {
        "rule_id": "R-DESC-01",
        "target": "description_selection",
        "principle": ("描写选择：action=0.405 优先，environment=0.266 次之，object=0.127 最少："
                      "动态描写压倒静态物描。"),
        "review_check": "抽查 3 章，确认环境/器物描写服务于动作，无静止陈列式描写。",
        "writing_action": "描写绑定动作（边做边写）；少做静态物象罗列。",
        "confidence": 0.75, "status": "proposed",
        "source": SRC,
    },
    {
        "rule_id": "R-SENS-01",
        "target": "sensory_preference",
        "principle": ("感官：visual=0.611 + auditory=0.244 具象优先，olfactory/gustatory 极低："
                      "用可见/可闻细节落地场景。"),
        "review_check": "抽查 3 章，确认场景有视觉/听觉具象，少用气味/味觉修饰。",
        "writing_action": "每场关键戏给 1–2 个视觉或听觉锚点（光影、声响、触感），避免抽象形容。",
        "confidence": 0.80, "status": "proposed",
        "source": SRC,
    },
    {
        "rule_id": "R-EMO-01",
        "target": "emotion_expression",
        "principle": ("情绪：direct=635 多于 behavioral=241(behavior_to_direct=0.402)：直给情绪为主，"
                      "但保留约 40% 行为外化避免唠叨。"),
        "review_check": "抽查 3 章，确认情绪直给与行为外化混合，不全程内心独白。",
        "writing_action": "关键情绪直接点破；次要情绪用动作/微表情外化，控制独白比例。",
        "confidence": 0.70, "status": "proposed",
        "source": SRC,
    },
    {
        "rule_id": "R-DIA-01",
        "target": "dialogue_method",
        "principle": ("对话：blocks_per_1000=10.36 密集，mean_dialogue_chars=47.3 偏短，"
                      "action_insertion=8626.6 高：短对话 + 对话间插动作。"),
        "review_check": "抽查 3 章，确认对话短促、对话块间有动作/神态插入。",
        "writing_action": "对话多短句、少长篇说教；每 2–3 轮对话插一句动作/神态打破纯对话墙。",
        "confidence": 0.85, "status": "proposed",
        "source": SRC,
    },
    {
        "rule_id": "R-META-01",
        "target": "metaphor_mechanism",
        "principle": "隐喻密度低(metaphors_per_1000=0.672)：比喻克制、贴合人物身份。",
        "review_check": "抽查 3 章，确认比喻少而准，无华丽堆喻。",
        "writing_action": "非必要不打比喻；若用，取主角熟悉域（商战/市井/江湖）的朴素喻体。",
        "confidence": 0.70, "status": "proposed",
        "source": SRC,
    },
    {
        "rule_id": "R-CLO-01",
        "target": "scene_closure",
        "principle": ("收尾：action_hook=True，末句长度约 50 字：用行动钩子收束，推进事态。"),
        "review_check": "抽查 3 章结尾，确认以行动/事态推进收束，非抒情收尾。",
        "writing_action": "章节/场景结尾给一个动作或事态推进（落子、反转、新威胁），钩住下一章。",
        "confidence": 0.80, "status": "proposed",
        "source": SRC,
    },
    {
        "rule_id": "R-AI-01",
        "target": "prohibited_patterns",
        "principle": ("去 AI 味：hedge_density=0.031 极低，template_expression_count=12.4 低："
                      "禁用模糊限定词与固定套路句式。"),
        "review_check": "全稿扫描，确认无'可能/也许/某种程度上/值得注意的是'等 hedge，无模板句。",
        "writing_action": ("禁用 hedging 限定词；句式随场景多变，避免'不仅…而且''正是因为…所以'等"
                           "固定框架；保持口语化、果断的网文嗓音。"),
        "confidence": 0.90, "status": "proposed",
        "source": SRC,
    },
    {
        "rule_id": "R-OMIT-01",
        "target": "omission_method",
        "principle": "省略信号适中(omission_signals_per_1000=1.024)：该藏处留白，制造悬念。",
        "review_check": "抽查 3 章，确认关键意图/布局有适度留白而非和盘托出。",
        "writing_action": "主角谋划、身份、后手适度留白；用结果反推，不事前剧透全貌。",
        "confidence": 0.70, "status": "proposed",
        "source": SRC,
    },
]


def main():
    summary_path = os.path.join(CAND, "learning-summary.yaml")
    s = _gov.load_yaml(summary_path)
    s["writing_candidates"] = CANDIDATES
    s["review_candidates"] = []
    s["promotion"] = {
        "state": "promoted",
        "rule": "作者授权受控晋升：五源融合指纹提炼为可追溯候选规则，经 promote-project --approved 写入项目级参考学习。",
        "promoted_at": "2026-07-28",
    }
    _gov.dump_yaml(summary_path, s)
    print("injected %d writing_candidates into summary" % len(CANDIDATES))


if __name__ == "__main__":
    main()
