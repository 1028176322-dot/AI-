# 检查项库（L3）

所有具体检查点放在本目录，**按支柱/模块分文件**。主文档 `审查体系.md` 不再罗列检查项——新增只改此处，不动主文档。

## 检查项格式（每行一条）

```
| 编号 | 检查点 | 严重度 | 自动化 | 评分方式 | 闭环方式 |
```

- **编号**：模块前缀＋两位序号（ST/LG/CH/WO/CS/BT/EM/WR/CP/BS/RR/AI）
- **严重度**：
  - `A` = Fatal A 结构性致命，立即打回，不评分
  - `B` = Fatal B 质量性致命，可评分，最终禁发布
  - `S` = 严重，重扣分
  - `N` = 一般，轻扣分
  - `T` = 建议，软提示
- **自动化**：`机检` / `AI深读` / `手动`
- **评分方式**：该点扣分幅度与判定（如「-15/项」「命中即 0 分」）
- **闭环方式**：`直接修`（审查对话落盘）/ `写作对话`（交生成端）/ `登锁词`（加锁词表）/ `加闸门`（补预防闸门）

## 四大支柱 ↔ 检查项归属

| 支柱 | 性质 | 检查项文件 | 输出 |
|------|------|-----------|------|
| ① 专业编辑审查（质量） | 作品写好没 | `story` `logic` `character` `world` `consistency` `battle` `emotion` `writing` `chapter` `business` `narrative`(⑪) `dialogue`(⑫) `conflict`(⑬) | ES 编辑综合分（Profile 13 模块加权） |
| ② AI 工程审查（错误） | 有没有 AI 错 | `ai`（重复4类/失忆/遗忘/节奏）＋ `consistency`＋ `metrics`（CI/ID/WBU） | CI 一致性指数 / AI 错误密度 |
| ③ 读者审查（体验） | 好不好看 | `reader/`（first/emotion/reward/immersion/persona/payment ＋ README 索引） | Reader Index / Immersion / PI / Persona |
| ④ 发布门禁（放行） | 能否发布 | 跨支柱综合 ＋ Fatal A/B | 门禁结论 |

> 三支柱独立评分、互不替代。`reader/` 自 v4.2 起拆为子目录（元规则 #10：支柱不内塞），主文档 `审查体系.md` §4 只留一级定义。

## 新增检查项流程（遵守元规则）
1. 判层级：属哪个支柱（L2）？哪条 Meta Rule？是已有规则实例还是新类？
2. 仅 L3：在对应 `checks/<模块>.md` 加一行，补齐【编号/检查点/严重度/自动化/评分/闭环】四要素。
3. 若需机检：在 L4 `tools/` 补脚本，项内标「机检」。
4. 不重改主文档与模块定义；跨支柱的新维度先判归属哪个支柱。

## 文件清单
- 支柱一（13 模块）：`story.md` `logic.md` `character.md` `world.md` `consistency.md` `battle.md` `emotion.md` `writing.md`（内分 8.1 语言规范性 + 8.2 阅读流畅性 Sentence Fluency，含 ZRF 黄金标准）`chapter.md` `business.md` **`narrative.md`(⑪)** **`dialogue.md`(⑫)** **`conflict.md`(⑬)**
- 支柱二：`ai.md` `metrics.md`（consistency.md 双属支柱一/二）
- 支柱三（拆子目录 `reader/`）：`README.md`（索引＋RI公式）`first.md`(RR01/02/06) `emotion.md`(RR03+情绪曲线) `reward.md`(RR04/05/07/08) `immersion.md`(沉浸感) `persona.md`(5角色+类型加权) `payment.md`(PI)
