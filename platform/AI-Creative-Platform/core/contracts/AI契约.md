# AI 创作统一契约（Unified Contract · 跨切面接口）

> **定位**：每层都有输入/输出，但此前**无统一契约**——Plugin 互换时接口对不齐，易「换实现却悄悄改了输出结构」。**统一 Contract 定义各层边界契约**，使插件真正可互换、可验证。
>
> **不属于新 Layer**：它是**跨切面接口规范**，被 Plugin 机制（`AI编排器.md` §6）引用，不进入 L1–L6 主栈。

---

## 1. 四契约（各层边界）

| 契约 | 提供方 | 输入 | 输出 |
|------|--------|------|------|
| **Planning Contract** | L3 规划者 | NKB 事实 ＋ 全书章节数 ＋ 作者方向 | 全书每章详细规划卡（因果链 / 场景链 / 读者体验 / 状态变化 / 叙事策略 / 开头设计 / 结尾设计） |
| **Context Contract** | Context Engine | NKB ＋ 规划卡 ＋ 写作手法编排 ＋ 读者态 | Final Context（带预算占用 / 优先级 / 压缩痕迹 / 冲突裁决） |
| **Capability Contract** | 能力层（各 Engine） | 场景级编排计划 ＋ Final Context | 按情节、环境和人物状态组合的场景实现片段 |
| **Review Contract** | L5 Review | 正文 ＋ Final Context ＋ 规划卡 ＋ 写作手法证据 | 四支柱评分 ＋ 手法适配/首尾/反模板结论 ＋ Fatal A/B ＋ 门禁判定 |

> 各契约的 `id / input / output / capability / impl / version` 字段即 Plugin 注册表落地（见 `AI编排器.md` §6）。

---

## 2. 契约不变量（Invariants）

- **输入缺失 → 报错不静默**：上游未给齐契约输入，下游拒绝执行并报告缺项。
- **输出结构固定**：即便 `impl` 换了模型 / 脚本，输出结构须与契约一致——这是 Plugin 可替换的前提。
- **版本写入契约头**：每个契约实例带 `version`（`AI编排器.md` §6 Plugin Version），回 regression 可定位「哪次契约升级引入变化」。
- **不变量校验**：换 impl 后，Execution Runtime（检查点）先跑一章对照旧 Build，输出结构一致才放行（见 `AI执行运行时.md`）。
- **完整规划不变量**：总章节数为 N，就必须存在 N 份可写级详细章纲；分批生成只控制运行规模，不能用“后续窗口”替代未完成章纲。
- **首尾链不变量**：除首末章外，每章 `previous_plan_id` 与 `next_plan_id` 必须连接相邻规划；正文首尾必须提供可定位证据。

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
