# 读者审查（支柱三 · Reader Review）— 子目录索引

> **v4.2 起，读者审查拆为子文件**，避免单一文件膨胀（遵循元规则 #10：单一支柱检查项过多时拆子目录，不内塞）。
> 主文档 `审查体系.md` §4 只保留 Reader 一级定义；具体检查项全在此目录。

## 子文件
| 文件 | 内容 | 含检查项 |
|------|------|----------|
| `first.md` | 第一阅读体验 | RR01 第一印象 / RR02 阅读流畅 / RR06 疲劳度 |
| `emotion.md` | 情绪与曲线 | RR03 情绪体验 ＋ Emotion Curve 情绪曲线 |
| `reward.md` | 奖励与钩子 | RR04 期待值 / RR05 奖励感 / RR07 爽点兑现 / RR08 信息获取 |
| `immersion.md` | 沉浸感 | Immersion Score 沉浸感（出戏检测） |
| `persona.md` | 读者角色模拟 | 5 角色 ＋ 按类型加权 Persona Index |
| `payment.md` | 付费意愿 | PI（Payment Intent） |

## Reader Index（读者指数）公式
`Reader Index = mean(RR01, RR02, RR03, RR04, RR05, 100−RR06_疲劳度原始, RR07, RR08, Immersion)`
- 各子维度 0–100；疲劳度取反向（100−原始）。
- **门禁阈值：RI ≥ 60**（即便 ES 满分，RI<60 仍禁发布——质量 ≠ 好看）。

## Persona-Weighted Reader Index（类型加权读者指数，可选增强）
- 见 `persona.md`：按小说类型对 5 角色评分加权，使 RI 更贴近目标读者群。
- 客观 9 维 RI 用于门禁；Persona-Weighted 版作 NH / 商业研判参考。

## 与门禁关系
输出 **Reader Index ＋ Immersion ＋ PI ＋ 角色模拟**，供支柱四发布门禁综合：
`ES≥80 AND CI≥95% AND RI≥60 AND PI≥60 AND Fatal A/B 双零`。
