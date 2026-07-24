# AI 创作运行平台（AI-Creative-Platform）

> 把「AI 小说创作流程」升级为**可跨项目复用的创作运行平台**。
> 核心思想：**复用方法 / 能力 / 结构 / 经验，隔离人物 / 世界 / 剧情 / 状态**。

本平台不是又一层 Layer，而是把已有系统按「**全局 Core / 类型 Template / 项目 Project**」三层彻底分离，并补齐四大工程落点，使新建小说从「复制旧项目再清理」变为「选择模板并实例化」。

---

## 〇、工作空间（Workspace）—— 跨设备入口

任何设备克隆本仓库后，从 **Workspace** 进入，而不是写死某个盘符：

```
Workspace   工作空间（workspace.yaml 声明 platform / projects 相对路径）
   ↓
Platform    平台（platform/AI-Creative-Platform：全局 Core + 模板 + 注册表 + 经验）
   ↓
Projects    项目集合（projects/：每个小说一个目录）
   ↓
Project     单项目实例（project.yaml + NKB + overrides + metrics + ...）
   ↓
Build       单章产物（正文 + 规划 + 上下文 + 审查 + 修复日志，含 build: 版本标识）
```

- `workspace.yaml` 是**唯一布局事实源**：`platform:` 与 `projects:` 均相对 workspace 根。
- 项目 `project.yaml` **只声明 `requires:`（版本约束），不写平台路径**；由 workspace 解析实际位置。换电脑 / 换盘符均不失效。
- 环境变量覆盖：`AI_PLATFORM_HOME`（平台根）、`AI_WORKSPACE_HOME`（workspace 根）。
- 平台工程化（bootstrap / doctor / CLI）见 **[第八节](#八平台工程化workspace--cli)**。

---

## 一、四个工程落点（本次重构目标）

| # | 落点 | 实现 |
|---|------|------|
| 1 | **Core / Template / Project 三层目录隔离** | `core/`（全局）＋ `templates/`（题材）＋ `projects/`（实例），物理分离 |
| 2 | **project.yaml 项目清单** | 编排器启动只读它，即知项目/模板/NKB/Plugin/门禁/产物路径 |
| 3 | **Global / Genre / Project 三级 Memory** | `memory/global` `memory/genre` `memory/rejected`（平台）＋ 各项目 `memory/project`（私有），含晋升机制 |
| 4 | **Plugin 与 Schema 全部版本化引用** | `registry/plugins.yaml` `capabilities.yaml` `versions.yaml`，项目引用 `plugin@version`，不复制实现 |

---

## 二、三层隔离与覆盖顺序

```
Global（全局可复用）
   ↓ 被覆盖
Genre Template（题材可复用）
   ↓ 被覆盖
Project Configuration（项目私有）
   ↓ 被覆盖
Chapter Runtime（章节私有）
```

- **下层可覆盖上层，不能反向污染**：Project 不能改 Global；Chapter 不能改 Project。
- **Global**：宪法 / 规范 / 流程 / 检查项 / 能力引擎 / Context Engine / 编排器 / 脚本 / 已验证跨项目经验。
- **Genre**：各类型 Profile / 规划 / 审查阈值 / 能力路由 / 术语种子 / NKB 扩展字段。
- **Project**：人物 / 世界观 / 时间线 / 伏笔 / 专名 / 大纲 / 正文 / 读者态 / 项目经验。
- **Chapter**：规划卡 / Final Context / 草稿 / 审查报告 / 修复日志 / 章节状态。

---

## 三、目录总览

```
AI-Workspace/                             # 工作空间根（克隆仓库入口）
├── workspace.yaml                        # 布局清单：platform / projects 相对路径
├── platform/
│   └── AI-Creative-Platform/             # 平台（原三层结构，见下）
│       ├── core/                         # 全局 Core（所有项目共用，不属于任何小说）
│       │   ├── constitution/             # AI写作宪法（L1）
│       │   ├── specifications/           # AI写作规范（L2）
│       │   ├── planning/                 # AI写作规划（L3 规划者）
│       │   ├── context-engine/           # AI上下文引擎
│       │   ├── capabilities/             # AI能力层（6 Engine）
│       │   ├── workflows/                # 流程体系_小说创作
│       │   ├── review/                   # 审查体系 + checks/
│       │   ├── contracts/                # AI契约（四契约）
│       │   ├── observability/            # AI可观测性
│       │   └── runtime/                  # AI执行运行时
│       ├── registry/                     # 版本化引用（不复制实现）
│       │   ├── plugins.yaml              # 各 Plugin：impl + contract + version
│       │   ├── capabilities.yaml         # 6 能力引擎目录
│       │   └── versions.yaml             # 版本锚点
│       ├── templates/                    # 类型模板（题材差异）
│       │   ├── xuanhuan/ … qingxiaoshuo/
│       │   │   ├── profile.yaml / planning.yaml / review-thresholds.yaml
│       │   │   ├── capability-routing.yaml / terminology-seed.yaml / nkb-schema-extension.yaml
│       ├── memory/                       # 可复用经验（三级 + rejected）
│       │   ├── global/  genre/  rejected/  晋升机制.md
│       ├── tools/                        # 平台工程化 CLI（bootstrap/doctor/check/init-project）
│       │   ├── platform_cli.py  _yaml_lite.py  platform.bat  platform.sh
│       ├── ARCHITECTURE.md  README.md  迁移与切换.md
└── projects/                             # 项目集合（每个小说一个目录）
    └── 道法百年/                          # 项目实例：project.yaml + NKB + overrides + ...
```

项目实例（如《道士也玩火力覆盖》）位于 `projects/道法百年/`（相对 workspace 根），含：
`project.yaml` · `NKB/`（项目私有事实源）· `outline/` · `txt/`各卷 · `artifacts/` · `overrides/` · `metrics/` · `memory/project/`

---

## 四、project.yaml 的作用

编排器启动只需读取项目 `project.yaml`，即知：
- 当前是哪一个项目（`project.id`）
- 使用哪种类型模板（`template.id`@`version`）
- 加载哪个 NKB（`paths.nkb`）
- 调哪些 Plugin（`plugins.*`@`version`）
- 使用什么门禁（`gates.*`）
- 产物写到哪里（`paths.artifacts`）

切换项目 = 切换 `project.yaml`，**不修改全局流程**。

---

## 五、新项目启动流程（实例化，非复制）

1. 选择类型模板（`templates/<genre>/`）
2. 创建 `project.yaml`（引用模板 + 锁定 Plugin 版本）
3. 从 Schema 生成**空 NKB**（`NKB/*.yaml`，`records: []`）
4. 填写 Canon / 人物 / 世界 / 时间线初始数据
5. 绑定 Plugin 版本（`plugins.*@version`）
6. 加载 Global Memory + Genre Memory
7. **不加载**其他项目的 NKB 与 Project Memory
8. 运行初始化一致性审查
9. 开始规划与写作

---

## 六、运行环境组装公式

```
加载 Core
  + 加载 Genre Template（project.yaml.template）
  + 加载当前 Project（project.yaml + NKB）
  + 加载允许的 Memory（global + genre + 本项目 project）
  + 应用 Overrides（project.overrides）
= 当前项目运行环境
```

---

## 七、复用原则（一句话）

- **可跨项目复用**：宪法、规范、流程、检查项、脚本、能力引擎、Context Engine、Plugin、题材模板、已验证经验。
- **不可跨项目直接复用**：人物事实、世界状态、事件、时间线、伏笔、资源、专名、Reader State、项目推断、具体修复。

---

## 八、平台工程化（Workspace + CLI）

平台不仅是架构设计，更具备「新电脑拉取仓库即可运行」的工程能力。

### 1. 启动顺序（任何设备一致）
```
clone 仓库
  → platform bootstrap   # 检查 Platform/Plugin/NKB/Contracts/Template → 生成 .cache/manifest.json
  → platform doctor      # 只读诊断，退出码反映健康度（FAIL=1）
  → platform run         # 编排器启动（未来；当前由对话调用）
```

### 2. 命令一览
| 命令 | 作用 |
|------|------|
| `python tools/platform_cli.py bootstrap` | 初始化环境：兼容检查全 PASS 才写缓存；任一项 FAIL 立即中止 |
| `… doctor` | 只读诊断，逐项报告 PASS / FAIL / WARN，退出码 0 / 1 |
| `… check [--project <id>]` | 单项目兼容性检查（requires vs 实际） |
| `… init-project --name <目录> --type <genre>` | 脚手架新项目（空 NKB + overrides + 自动登记进 workspace.yaml） |
| `… version` | 打印 Platform / Core / Templates / Plugins 版本目录 |
| `… list` | 列出 workspace 登记的项目 |

> Windows 可直接用 `tools/platform.bat <cmd>`，\*nix 用 `tools/platform.sh <cmd>`。

### 3. 兼容性检查（启动第一件事）
每个项目 `project.yaml` 声明 `requires:`（platform / nkb_schema / contracts / templates）。
`bootstrap` / `doctor` 启动时**先校验**，任一项 FAIL → 非零退出，绝不放行：
- **Platform** PASS：平台目录存在 + `registry/versions.yaml` 可读 + `core.platform` 满足约束
- **Contracts** PASS：contract 版本满足约束
- **NKB** PASS：NKB `schema_version` 满足约束
- **Template** PASS：类型模板 `schema_version` 满足约束
- **Plugin** PASS：`plugins` + `capabilities` 引用的 `name@version` 全部在 `registry` 注册

### 4. 零依赖
`platform_cli.py` 优先用 PyYAML；未安装时 fallback 到同目录 `_yaml_lite.py`（零依赖 YAML 子集解析器），
保证「克隆即运行」无需 `pip install`。

---

## 九、迁移与 cutover

本次从单项目文档重构为平台的迁移清单与切换步骤，见 **`迁移与切换.md`**。
全局 Core 文档已从小说仓库 `docs/` 迁出；小说仓库 `docs/` 仅保留项目私有内容（治理索引 / 红线），并加 `docs/DEPRECATED.md` 指路。
