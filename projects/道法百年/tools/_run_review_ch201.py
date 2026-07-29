# -*- coding: utf-8 -*-
"""CH-201 chapter_review: claim/start -> run_review (prep) -> fill panel+report -> validate -> submit."""
import sys, os

SCRIPTS = "E:/AI-Workspace/platform/AI-Creative-Platform/scripts"
for d in [SCRIPTS, SCRIPTS + "/tasks", SCRIPTS + "/platform", SCRIPTS + "/_common"]:
    if d not in sys.path:
        sys.path.insert(0, d)

PROJECT = "E:/AI-Workspace/projects/道法百年"
TASK = "REQ-20260729121113455905-4D8E6B-PLAN-CH201-CHAPTER-WRITE-CHAPTER-REVIEW"
AGENT = "橘子"
ROLE = "reviewer"
ARTIFACT = "chapters/drafts/CH-201.md"
CHAPTER_TEXT = open(os.path.join(PROJECT, ARTIFACT), encoding="utf-8").read()

import task_engine as TE
import review_orchestrator as RO
import reader_panel as RP
import _gov

# ---- 1) claim + start ----
print("claim:", TE.claim(PROJECT, TASK, AGENT, ROLE))
print("start:", TE.start(PROJECT, TASK, AGENT, ROLE))

# ---- 2) run_review: 生成证据包 + 空 reader panel + 空 review report ----
brief = RO.run_review(PROJECT, TASK)
print("brief:", brief)

PANEL_PATH = os.path.join(PROJECT, "runtime", "reader-panels", "PANEL-%s" % TASK, "report.yaml")
REPORT_PATH = os.path.join(PROJECT, "runtime", "reviews", "REVIEW-%s" % TASK, "report.yaml")

# ---- 3) 填 reader panel (12 镜) ----
# 每个镜头的 8 必需字段 + evidence_excerpt（必须是正文精确子串）
lens_fill = {
    "first_contact": dict(
        score=86, confidence=0.9,
        observation="开篇以雪夜/灯影/炭盆的感官锚点切入，第一句即给出场景与氛围，理解成本低，继续阅读意愿强。",
        evidence_location="第3行（开场）",
        evidence_excerpt="雪落得更密了，天上人间的灯却愈发亮。",
        reading_effect="读者立刻进入谍战夜局氛围，无开局拖沓。",
        expectation="期望后续在暖局中埋入暗线冲突，已被满足。",
        recommended_fix="无需改动；开场节奏已克制。",
    ),
    "new_reader": dict(
        score=80, confidence=0.85,
        observation="新读者能看懂肖凡/苏墨凝的上下级关系与'听雨'为敌对暗组织，但'以技破武''五条线'等前情需略靠上下文推断。",
        evidence_location="第3、7、47行",
        evidence_excerpt="苏墨凝指尖捻着一枚铜钱，漫不经心地拨弄着案上那盏茶的浮沫。",
        reading_effect="人物关系清晰；少量前情术语对新人略设门槛但不阻断。",
        expectation="期望关键前情有轻量回扣，文中以'第两百章'暗示，可接受。",
        recommended_fix="保持现状；后续章若切新读者视角可补一句前情锚。",
    ),
    "genre_veteran": dict(
        score=88, confidence=0.9,
        observation="权谋'借刀'套路呈现克制且有新意（留半条底、反将一军），避免爽文式直给。",
        evidence_location="第19、25、31行",
        evidence_excerpt="借刀——这两个字他熟。",
        reading_effect="老读者获得'布局者'智斗爽感，审美疲劳低。",
        expectation="期望反派不弱智、主角不降智，已满足。",
        recommended_fix="无需改动。",
    ),
    "plot_logic": dict(
        score=85, confidence=0.88,
        observation="因果链清晰：残部扎窝→米面推算规模→借内卫府之刀→留半底续线，每一步有动机与代价。",
        evidence_location="第5、11、23、31行",
        evidence_excerpt="西市暗巷第三进，那处死铺面后头，有个不挂牌的院子。",
        reading_effect="权谋推进可信，无机械降神。",
        expectation="期望'借刀'有可落手的由头，王录事的人设伏笔成立。",
        recommended_fix="无需改动。",
    ),
    "character_empathy": dict(
        score=84, confidence=0.87,
        observation="肖凡的'不站明处''留半底'动机一致（藏/接的武学哲学），苏墨凝机敏配合，角色能动性充足。",
        evidence_location="第13、23、33行",
        evidence_excerpt="肖凡指节在栏沿轻轻一叩。",
        reading_effect="读者理解主角克制背后的掌控欲与耐心。",
        expectation="期望角色不为剧情牺牲性格，已满足。",
        recommended_fix="无需改动。",
    ),
    "world_immersion": dict(
        score=83, confidence=0.85,
        observation="京兆府/内卫府/武者登记制等设定具因果（新政成刀柄），无出戏设定堆砌。",
        evidence_location="第17、21、39行",
        evidence_excerpt="内卫府那位王录事，上月来咱们这喝酒，醉后怨过西坊背街的贼案办不干净，上司压着不让他深究。",
        reading_effect="朝堂-市井权力结构可信，设定服务剧情。",
        expectation="期望规则边界清晰，已满足。",
        recommended_fix="无需改动。",
    ),
    "pacing_fatigue": dict(
        score=79, confidence=0.82,
        observation="中段肖凡内心推演（约13-25行）策略说明偏密，但已与'叩栏/拨茶沫/放铜钱'等动作交织，停读风险低。",
        evidence_location="第13-25行",
        evidence_excerpt="肖凡不答，只将杯中茶一饮而尽。",
        reading_effect="略有信息密度峰值，但被动作与对话稀释。",
        expectation="期望不出现大段独白，基本满足。",
        recommended_fix="可选：将'留半底' rationale 再拆一句动作化呈现，进一步降负荷。",
    ),
    "prose_clarity": dict(
        score=87, confidence=0.9,
        observation="句式干净，指代明确，画面感强，无解释腔与AI腔；'刀不沾血，人也不露形'收束利落。",
        evidence_location="第25行",
        evidence_excerpt="借刀杀人，刀不沾血，人也不露形。",
        reading_effect="阅读顺畅，金句增强记忆点。",
        expectation="期望语言有质感，已满足。",
        recommended_fix="无需改动。",
    ),
    "emotion_reward": dict(
        score=85, confidence=0.87,
        observation="苏墨凝'下得比下棋还刁'的笑与肖凡'茶凉喉热'的细节提供情绪余韵，爽点在智斗而非打斗。",
        evidence_location="第33、35行",
        evidence_excerpt="苏墨凝怔了怔，旋即低笑：\"大人这盘，下得比下棋还刁。\"",
        reading_effect="读者获得布局得逞的隐性爽感与余韵。",
        expectation="期望情绪有兑现而非只铺垫，已满足。",
        recommended_fix="无需改动。",
    ),
    "serial_retention": dict(
        score=89, confidence=0.9,
        observation="章末明确'暗线织网才刚起头'+活子续线，给下一章强追读钩子，且呼应卷二主线。",
        evidence_location="第61行",
        evidence_excerpt="以技破武这一程，到今夜收了尾；暗线织网这一程，才刚起头。",
        reading_effect="读者明确知晓后续局展开，连续阅读动力强。",
        expectation="期望章末有承诺，已满足。",
        recommended_fix="无需改动。",
    ),
    "commercial_value": dict(
        score=84, confidence=0.85,
        observation="权谋智斗+暗线收网提供高'获得感'，主角不露面肃清敌巢的稀缺爽点明确。",
        evidence_location="第47、51行",
        evidence_excerpt="他忽然觉得，这半年来隔着半座京城攥住的几根线，今夜又悄悄多缠了一道",
        reading_effect="付费/推荐意愿正面，属平台稳健爽章。",
        expectation="期望每章有可分享的'棋局感'，已满足。",
        recommended_fix="无需改动。",
    ),
    "safety_accessibility": dict(
        score=90, confidence=0.92,
        observation="无敏感内容、无刻板印象；冷兵器/暗器仅作氛围与隐喻，无受众障碍。",
        evidence_location="第55行",
        evidence_excerpt="肖凡摸出袖中那管短枪，在掌心转了半圈，又缓缓塞回。",
        reading_effect="普适可读性高。",
        expectation="期望无硬性越界，已满足。",
        recommended_fix="无需改动。",
    ),
}

panel = _gov.load_yaml(PANEL_PATH) or {}
# 校验 evidence_excerpt 精确命中正文
for lid, f in lens_fill.items():
    ex = f["evidence_excerpt"]
    if ex not in CHAPTER_TEXT:
        raise SystemExit("EVIDENCE_NOT_FOUND for %s: %s" % (lid, ex))
for lens in panel.get("lenses") or []:
    lid = lens.get("id")
    if lid in lens_fill:
        lens.update(lens_fill[lid])
panel["dropoff"] = {
    "risk": "low",
    "location": "中段策略推演（约第13-25行）",
    "reason": "权谋说明偏密但已与动作/对话交织，停读风险低，不构成阻断。",
}
panel["summary"] = "12 镜头整体高分（均>78），无致命镜头；开篇氛围、借刀智斗、章末钩子为强项，中段略密但已稀释。整体 proceed，建议可选微调降负荷。"
_gov.dump_yaml(PANEL_PATH, panel)
print("panel filled & dumped")

# ---- 4) 填 review report (findings + verdict) ----
report = _gov.load_yaml(REPORT_PATH) or {}
findings = [
    {
        "id": "F-1",
        "category": "continuity",
        "severity": "info",
        "location": "全文（第47、57、61行）",
        "observation": "与第200章'收网/五条线'前情一致衔接，肖凡'网成鱼跑不了'的掌控叙事连贯。",
        "evidence": "第47行'朝争的爆、新政的落、火器的验、听雨的退、洗牌的启，五条线拧到一处'；第61行'暗线织网这一程，才刚起头'。",
        "reasoning": "章纲要求承接收网基调，正文在情绪与意象上对齐，无断点。",
        "impact": "维持卷二主线连续性与读者记忆锚。",
        "recommended_fix": "无需修复；保持该呼应节奏。",
    },
    {
        "id": "F-2",
        "category": "pacing",
        "severity": "warn",
        "location": "第13-25行（肖凡内心推演段）",
        "observation": "中段策略说明密度略高，存在轻微信息负荷峰值。",
        "evidence": "第13行'米面够十来张嘴，说明残部不是三五个人的散兵'、第25行'借刀杀人，刀不沾血'等连续推演。",
        "reasoning": "虽已用'叩栏/拨茶沫/放铜钱'等动作交织，但纯策略陈述占比偏高。",
        "impact": "新读者在中段可能有轻微阅读减速，未达停读。",
        "recommended_fix": "可选：将'留半底'的 rationale 再拆为一次动作化呈现（如苏墨凝倒茶时的反问），进一步降负荷。",
    },
    {
        "id": "F-3",
        "category": "terminology",
        "severity": "info",
        "location": "第61行",
        "observation": "'以技破武'作为阶段弧标签出现，需与大纲/卷二命名保持一致，避免后续章用词漂移。",
        "evidence": "第61行'以技破武这一程，到今夜收了尾；暗线织网这一程，才刚起头'。",
        "reasoning": "阶段命名若前后不一致会削弱系列感。",
        "impact": "低；仅影响系列术语统一。",
        "recommended_fix": "在卷二术语表中登记'以技破武''暗线织网'两阶段标签，后续章沿用。",
    },
]
report["findings"] = findings
report["verdict"] = "pass_with_fixes"
report["summary"] = "CH-201《残部追踪》整体质量高：开篇氛围、借刀智斗、章末钩子为强项；仅中段策略密度略高（warn）与阶段术语登记（info）两项软建议。无硬一致性/阻断问题，verdict=pass_with_fixes。"
_gov.dump_yaml(REPORT_PATH, report)
print("report filled & dumped")

# ---- 5) validate ----
ok, errors = RO.validate_report(PROJECT, TASK)
print("validate_report:", ok, errors)
if not ok:
    raise SystemExit("VALIDATE_FAILED: %s" % errors)

# ---- 6) submit ----
res = TE.submit(
    PROJECT, TASK, ARTIFACT,
    outputs={
        "review_report": "runtime/reviews/REVIEW-%s/report.yaml" % TASK,
        "findings": "runtime/reviews/REVIEW-%s/report.yaml" % TASK,
    },
    agent=AGENT, role=ROLE,
)
print("submit:", res)
