# 项目实例：道士也玩火力覆盖（novel-dsf）

本目录是 **AI 创作运行平台** 的一个**项目实例**，不是平台本身。
全局 Core / 类型模板 / 注册表 / 跨项目经验 全部在上层平台 `../../platform/AI-Creative-Platform/`，
本项目**只持有私有事实与运行结果**。

## 本项目私有内容
- `NKB/`            世界事实库（Canon/Characters/.../Derived，空 Schema 待填充）
- `大纲_1000章总体规划.md` 等   大纲（outline）
- `txt/` 与各卷目录/   章节正文（chapters）
- `artifacts/`      每章产物包（正文+规划+上下文+审查+修复日志）
- `overrides/`      项目特例覆盖（不篡改全局宪法）
- `metrics/`        运行指标
- `memory/project/` 项目私有经验
- `project.yaml`    项目清单（编排器启动读取它）

## 运行环境组装
```
编排器加载 = Core + Genre Template(xuanhuan) + 本 project.yaml + 允许的 Memory + overrides
```
详见平台总览：`../../platform/AI-Creative-Platform/README.md`

## 复用原则
- **复用**：方法 / 能力 / 结构 / 经验（来自平台）。
- **隔离**：人物 / 世界 / 剧情 / 状态（仅本项目，绝不带入其他项目）。
