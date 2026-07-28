import io, sys

PATH = "sources/references/风格融合手册.md"
# 显式 UTF-8 读写
with open(PATH, encoding="utf-8") as f:
    text = f.read()

repls = []

# 1) 四节节注（4 行块）
repls.append((
    "> 本节能见度来自平台 `reference-learn` pipeline（schema `reference-learning@2.0.0`，2026-07-28 重跑修复庆余年分章、纳入第 3 源烟雨楼后）。\n"
    "> 三本各生成 **12 维风格指纹**，下表为量化实测值（「庆余年 / 赘婿 / 烟雨楼」）。**版权红线**：仅存统计与原则（`raw_text_stored: false`），不抄原文。\n"
    "> 这些量化值**印证并细化**「一、已沉淀笔法」的定性判断；写章作区间参考，非机械复制。\n"
    "> **重大进展（2026-07-28）**：3 本独立来源已满足平台硬门槛 `minimum_independent_sources = 3`，三源跨源聚合的 **12 维风格规则已晋升为 ACTIVE 正式风格规则**（治理审批：author=肖俊，事件日志留存）。正式规则落地于 `memory/project/style-library/`（`style-cards.json` + 12 份 `.lifecycle.json` + `event-log.json`），原始候选见 `learning/candidates/style-rule-candidates/`。下方「本作迁移」区间已据三源重新校准。",
    "> 本节能见度来自平台 `reference-learn` pipeline（schema `reference-learning@2.0.0`）。2026-07-28 起历经：修复庆余年全角空格分章失真 → 纳入第 3 源烟雨楼（3 源晋升 ACTIVE）→ 同日晚纳入第 4–6 源（唐寅在异界 / 孤儿院 / 镇北王），**重跑为 6 源聚合**。\n"
    "> 六本各生成 **12 维风格指纹**，下表「庆余年 / 赘婿 / 烟雨楼」为**代表样本**（后三本唐寅/孤儿院/镇北王已纳入聚合但不单列，避免表格过宽；各源原始值见 `learning/candidates/*.profile.yaml`）。**版权红线**：仅存统计与原则（`raw_text_stored: false`），不抄原文。\n"
    "> 这些量化值**印证并细化**「一、已沉淀笔法」的定性判断；写章作区间参考，非机械复制。\n"
    "> **重大进展（2026-07-28）**：6 本独立来源远超平台硬门槛 `minimum_independent_sources = 3`（并达 `recommended_independent_sources = 5`）。六源等权（各 1/6，单源权重 0.167 ≪ 0.4 上限）跨源聚合的 **12 维风格规则已晋升为 ACTIVE 正式风格规则**（治理审批：author=肖俊，事件日志留存）。正式规则落地于 `memory/project/style-library/`（`style-cards.json` + 12 份 `.lifecycle.json` + `event-log.json`），原始候选见 `learning/candidates/style-rule-candidates/`。下方「本作迁移」区间已据六源重新校准。",
))

# 2) 表头
repls.append((
    "| # | 维度 | 庆余年 | 赘婿 | 烟雨楼 | 本作迁移 / 印证（三源重校） |",
    "| # | 维度 | 庆余年 | 赘婿 | 烟雨楼 | 本作迁移 / 印证（六源聚合重校） |",
))

# 3) 12 行本作迁移列
repls.append(("三源均第三人称主导（烟雨楼略特殊、对话「我」多致 1st 接近 3rd）；印证限知锚定肖凡（一·1），本作严守限知。",
              "六源均第三人称主导（3rd 跨度 8043–35095 ≫ 1st 2694–11820；烟雨楼/孤儿院对话「我」多致 1st 偏高）；印证限知锚定肖凡（一·1），本作严守限知。"))
repls.append(("三源均近距主导，印证贴近人物感知（一·1/三 Do）；宏观史笔只在章首/转场，正文近距。",
              "六源均近距主导（close 40905–109321 ≫ far 603–4700），印证贴近人物感知（一·1/三 Do）；宏观史笔只在章首/转场，正文近距。"))
repls.append(("烟雨楼显著更短（句均 26 / 段均 24）拉低三源均值 → 写章句均控 30–50 字、段均 25–75 字，据场景择（论理长句 / 动作短段）。",
              "六源句均 19–48（mean 34）、方差大（std 11–43）→ 写章句均控 20–48 字、据场景择（论理长句 / 动作短段）。**段均离散极大**（庆余年/赘婿/烟雨楼 24–73 字，唐寅/孤儿院/镇北王因长段落达 1200–1660 字，疑未分段或长描写块），故段均以句长为准、勿依赖段均硬值。"))
repls.append(("三源行动+对白 ≳92%（烟雨楼对白略超行动），印证 show don't tell、信息 withholding（一·1/6）；世界设定 <5%。",
              "六源行动+对白 80–92%（镇北王/烟雨楼对白偏高），印证 show don't tell、信息 withholding（一·1/6）；世界设定 <5%、情绪 <3.5%。"))
repls.append(("环境+动作主导 → 印证「白描+感官器物」（一·3）；写场景多落环境/动作，少静止人物长描。",
              "六源环境+动作主导（environment 0.23–0.34 / action 0.33–0.52），镇北王动作占比最高 → 印证「白描+感官器物」（一·3）；写场景多落环境/动作，少静止人物长描。"))
repls.append(("视觉+听觉占 ~78% → 印证感官器物（一·3）；多用「见/闻」感官，嗅觉/味觉点缀。",
              "六源视觉+听觉 78–88%（后三本听觉偏高 0.31–0.33）→ 印证感官器物（一·3）；多用「见/闻」感官，嗅觉/味觉点缀。"))
repls.append(("三源行为化情绪均多于直述（烟雨楼 0.65 最高）→ 印证「借细节传递、不直抒」（一·6）；写情绪落动作/小物，禁直接抒情。",
              "六源行为化情绪均多于直述（behavior:direct 0.25–1.60，孤儿院 1.60 最高）→ 印证「借细节传递、不直抒」（一·6）；写情绪落动作/小物，禁直接抒情。"))
repls.append(("烟雨楼对白密度近翻倍（15/千字）抬升三源均值 → 千字对白参考扩至 6–15 单元，依场景（论辩/日常多对白，动作戏少）。",
              "六源千字对白 6.7–15.0 单元（mean 10.5）→ 写章据场景择：论辩/日常多对白，动作戏少；每句对白带神态/动作标签（一·5）。"))
repls.append(("三源 0.54–0.90/千字，写章控 0.5–0.9 喻/千字，取日常/训练意象，避滥。",
              "六源 0.50–0.90 喻/千字（mean 0.66）→ 写章控 0.5–0.9 喻/千字，取日常/训练意象，避滥。"))
repls.append(("烟雨楼留白偏少、跨度大；写章每千字 0.2–5 处留白，**宁多勿少**（取法庆余年/赘婿范式）。",
              "六源 0.24–4.84 省略信号/千字（mean 2.6，跨度大）→ 写章每千字 0.2–5 处留白，**宁多勿少**（取法庆余年/赘婿范式，烟雨楼偏少不取）。"))
repls.append(("章末短句收束，钩子靠叙事承诺非机械断章 → 印证章末钩子（一·6）；三源钩子率 0.54–0.85，本作章末须回扣承诺。",
              "章末短句收束（末句 1–21 字，多数 ≤6 字），钩子靠叙事承诺非机械断章 → 印证章末钩子（一·6）；本作章末须回扣承诺（六源 5 书末句≤6字，孤儿院 21 字带选择钩子为例外）。"))
repls.append(("模板/模糊密度三源均低 → 印证「零废话」红线（二/三 Don't）；句首重复为原始计数（与章数成正比，烟雨楼 1981 章故最高），写章仍须主动换句首。",
              "六源模板表达 0–71、模糊密度 0.005–0.064 均低 → 印证「零废话」红线（二/三 Don't）；句首重复为原始计数（与章数成正比，烟雨楼 1981 章故最高），写章仍须主动换句首。"))

# 4) 第112段
repls.append((
    "> **三源跨源聚合＝正式 ACTIVE 风格规则**：12 维目标分布已由三源等权（各 1/3，单源权重 0.333 < 0.4 上限）跨源聚合，经治理审批晋升 ACTIVE，落 `memory/project/style-library/style-cards.json`。写章时该 12 维为**正式可调用的风格目标**（soft 规则，非硬约束），与「一、已沉淀笔法」定性规则互补；红线仍以「二、本作硬约束」为准。",
    "> **六源跨源聚合＝正式 ACTIVE 风格规则**：12 维目标分布已由六源等权（各 1/6，单源权重 0.167 ≪ 0.4 上限）跨源聚合，经治理审批晋升 ACTIVE，落 `memory/project/style-library/style-cards.json`。写章时该 12 维为**正式可调用的风格目标**（soft 规则，非硬约束），与「一、已沉淀笔法」定性规则互补；红线仍以「二、本作硬约束」为准。",
))

# 5) 第114速记
repls.append((
    "> **量化区间速记（写章参考，非硬指标，三源重校）**：句均 30–50 字、段均 25–75 字、千字对白 6–15 单元、留白 0.2–5 处（宁多勿少）、比喻 0.5–0.9/千字；行动+对白 ≳90%、世界设定 <5%。（注：烟雨楼短句短段高对白显著拉低并拓宽了区间，写章据场景择：论理长句 / 动作短段 / 日常多对白。）",
    "> **量化区间速记（写章参考，非硬指标，六源聚合重校）**：句均 20–48 字、千字对白 7–15 单元、留白 0.2–5 处（宁多勿少）、比喻 0.5–0.9/千字；行动+对白 80–92%、世界设定 <5%。（注：段均离散极大，以句长为准；六源区间已据唐寅/孤儿院/镇北王拓宽，写章据场景择：论理长句 / 动作短段 / 日常多对白。）",
))

# 6) 五节：烟雨楼行 + 注（插入 3 本新书 + 重写注）
repls.append((
    "| 《烟雨楼》 | （文件未署名） | `烟雨楼风格提取.md` | 2026-07-28（@2.0.0 三源纳入） | 短句短段高密度对白、行为化情绪、视觉听觉主导、留白偏少 | 1981 章（1980+第零章）；章长中位 2197；章末钩子率 0.8057；对白比 0.3269 |\n\n"
    "> 注：2026-07-28 用平台 `reference-learning@2.0.0` 重跑，修复庆余年全角空格缩进导致的整本 1 章失真（详见 `learning/candidates/learning-summary.yaml` 的 `data_quality_notes`），并补齐 12 维风格指纹与版权指纹。三份 profile 均 `validate_profile` PASS，`raw_text_stored: false`。**同日纳入第 3 源《烟雨楼》后，三源跨源聚合的 12 维风格规则已晋升 ACTIVE 正式风格规则**（治理审批 author=肖俊，事件日志见 `memory/project/style-library/event-log.json`）。笔法级定性提取见各书对应文件。",
    "| 《烟雨楼》 | （文件未署名） | `烟雨楼风格提取.md` | 2026-07-28（@2.0.0 三源纳入） | 短句短段高密度对白、行为化情绪、视觉听觉主导、留白偏少 | 1981 章（1980+第零章）；章长中位 2197；章末钩子率 0.8057；对白比 0.3269 |\n"
    "| 《唐寅在异界》 | （文件未署名） | `唐寅在异界风格提取.md`（待补） | 2026-07-28（@2.0.0 六源纳入） | 第三人称限知极致、近距密集、行动主导、听觉偏高、行为化情绪 | 1533 章；章长中位 3124；章末钩子率 0.7339；对白比 0.2098 |\n"
    "| 《我开的真是孤儿院，不是杀手堂》 | （文件未署名） | `孤儿院风格提取.md`（待补） | 2026-07-28（@2.0.0 六源纳入） | 极短句、超长段落、对白密集、行为化情绪最高(1.60)、选择钩子 | 1066 章；章长中位 2205；章末钩子率 0.727；对白比 0.2307 |\n"
    "| 《镇北王》 | （文件未署名） | `镇北王风格提取.md`（待补） | 2026-07-28（@2.0.0 六源纳入） | 动作描写占比最高、听觉偏高、钩子率最高(0.88)、行为化情绪 | 1775 章；章长中位 2144；章末钩子率 0.8806；对白比 0.2672 |\n\n"
    "> 注：2026-07-28 用平台 `reference-learning@2.0.0` 重跑并分两批纳入——先第 3 源《烟雨楼》（3 源晋升 ACTIVE），同日晚再纳入第 4–6 源（唐寅/孤儿院/镇北王）重跑为 6 源聚合，六源等权再晋升 ACTIVE（author=肖俊）。六份 profile 均 `validate_profile` PASS，`raw_text_stored: false`。笔法级定性提取见各书对应文件（庆余年/赘婿/烟雨楼已建，唐寅/孤儿院/镇北王待补）。",
))

# 7) 六节 132/133/134
repls.append((
    "- **✅ 晋升正式风格规则门槛已满足（2026-07-28）**：现已有 **3 本独立来源**（庆余年 / 赘婿 / 烟雨楼），达到平台硬门槛 `minimum_independent_sources = 3`。三源跨源聚合的 **12 维风格规则已全部晋升 ACTIVE 正式风格规则**（治理审批 author=肖俊，单源权重各 1/3 < 0.4 上限）。正式规则落 `memory/project/style-library/`（`style-cards.json` + 12 份 `.lifecycle.json` + `event-log.json`），原始候选见 `learning/candidates/style-rule-candidates/`。",
    "- **✅ 晋升正式风格规则门槛已超额满足（2026-07-28）**：现已有 **6 本独立来源**（庆余年 / 赘婿 / 烟雨楼 / 唐寅在异界 / 孤儿院 / 镇北王），远超平台硬门槛 `minimum_independent_sources = 3` 并达 `recommended_independent_sources = 5`。六源等权（各 1/6）跨源聚合的 **12 维风格规则已全部晋升 ACTIVE 正式风格规则**（治理审批 author=肖俊，单源权重各 0.167 ≪ 0.4 上限）。正式规则落 `memory/project/style-library/`（`style-cards.json` + 12 份 `.lifecycle.json` + `event-log.json`），原始候选见 `learning/candidates/style-rule-candidates/`。",
))
repls.append((
    "- **沿用中的项目试验级候选**：跨源聚合的 5 条写作候选（`REF-CHAPTER-RHYTHM / END-HOOK / DIALOGUE-BALANCE / EMOTION-WAVE / PARAGRAPH-CONTRAST`，现基于 3 源）保留于 `learning/candidates/learning-summary.yaml` 的 `writing_candidates`，作为写作/审校软指引（`runtime/learning/reference-guidance.yaml`），与 12 维 ACTIVE 规则互补。",
    "- **沿用中的项目试验级候选**：跨源聚合的 5 条写作候选（`REF-CHAPTER-RHYTHM / END-HOOK / DIALOGUE-BALANCE / EMOTION-WAVE / PARAGRAPH-CONTRAST`，现基于 6 源）保留于 `learning/candidates/learning-summary.yaml` 的 `writing_candidates`，作为写作/审校软指引（`runtime/learning/reference-guidance.yaml`），与 12 维 ACTIVE 规则互补。",
))
repls.append((
    "- **若想进一步加强（推荐 5 源）**：平台 `recommended_independent_sources = 5`。再投放 ≥1 本**独立**（不同作者、非同一 IP 衍生、文本不重复）小说原文至 `sources/references/inbox/`（标准化 `第X章` 分章格式最佳），重跑 `runtime/reference-learning/_extract_3src.py` + `_promote_style_rules.py` 即可刷新并再晋升。**注意**：inbox 内同名/重复副本（如庆余年 .txt 与 .utf8.txt）会被当伪独立来源，已移入 `_archive/`，投放新作请勿重复。",
    "- **若想进一步加强（可选）**：已达 6 源、超过推荐门槛。平台无更高硬门槛，若需更大语料覆盖可继续投放独立小说至 `sources/references/inbox/`（标准化 `第X章` 分章），重跑 `runtime/reference-learning/_extract_3src.py` + `_promote_style_rules.py` 刷新晋升。**注意**：inbox 内同名/重复副本会被当伪独立来源，已移入 `_archive/`，投放新作请勿重复。",
))

# 执行 + 断言唯一
fail = 0
for i, (old, new) in enumerate(repls):
    c = text.count(old)
    if c != 1:
        print(f"[FAIL] repl#{i} count={c}")
        fail += 1
        # 打印 old 前 40 字便于定位
        print("   old-head:", repr(old[:40]))
    else:
        text = text.replace(old, new, 1)

if fail:
    raise SystemExit(f"{fail} 处匹配失败，已中止写回（未改动文件）")

with open(PATH, "w", encoding="utf-8") as f:
    f.write(text)
print(f"OK: 全部 {len(repls)} 处替换成功，已写回 {PATH}")
