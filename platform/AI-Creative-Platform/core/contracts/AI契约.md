# AI 创作统一契约（Unified Contract · 跨切面接口）

> **定位**：每层都有输入/输出，但此前**无统一契约**——Plugin 互换时接口对不齐，易「换实现却悄悄改了输出结构」。**统一 Contract 定义各层边界契约**，使插件真正可互换、可验证。
>
> **不属于新 Layer**：它是**跨切面接口规范**，被 Plugin 机制（`AI编排器.md` §6）引用，不进入 L1–L6 主栈。

---

## 1. 四契约（各层边界）

| 契约 | 提供方 | 输入 | 输出 |
|------|--------|------|------|
| **Planning Contract** | L3 规划者 | NKB 事实 ＋ 章目标 | 规划卡（目标 / Story Beat / 冲突 / 情绪曲线 / 预算） |
| **Context Contract** | Context Engine | NKB ＋ 规划卡 ＋ 读者态 | Final Context（带预算占用 / 优先级 / 压缩痕迹 / 冲突裁决） |
| **Capability Contract** | 能力层（各 Engine） | 编排计划 ＋ Final Context | 各引擎片段（台词 / 描写 / 战斗结果 / 情绪标注） |
| **Review Contract** | L5 Review | 正文 ＋ Final Context | 四支柱评分 ＋ Fatal A/B ＋ 门禁判定 |

> 各契约的 `id / input / output / capability / impl / version` 字段即 Plugin 注册表落地（见 `AI编排器.md` §6）。

---

## 2. 契约不变量（Invariants）

- **输入缺失 → 报错不静默**：上游未给齐契约输入，下游拒绝执行并报告缺项。
- **输出结构固定**：即便 `impl` 换了模型 / 脚本，输出结构须与契约一致——这是 Plugin 可替换的前提。
- **版本写入契约头**：每个契约实例带 `version`（`AI编排器.md` §6 Plugin Version），回 regression 可定位「哪次契约升级引入变化」。
- **不变量校验**：换 impl 后，Execution Runtime（检查点）先跑一章对照旧 Build，输出结构一致才放行（见 `AI执行运行时.md`）。

---

## 3. 与 Plugin 机制关系

```
Plugin 注册（id/input/output/capability/impl/version）
   │
   ▼ 契约即边界
换 impl（如 review.impl = 阅读AI-v2）
   → 输入/输出结构不变 → 编排逻辑不变 → 真正可互换
```

> 统一契约是「可扩展性 10/10」的**接口保证**：没有它，Plugin 机制只是「换实现」的口号；有了它，换实现是**契约约束下的安全替换**。这也让能力编排器（`AI能力层.md` §4）能稳定调度任意引擎 impl。
