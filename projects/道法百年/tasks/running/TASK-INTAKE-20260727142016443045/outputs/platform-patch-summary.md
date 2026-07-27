# 总章节数驱动的五级大纲治理升级

任务：`TASK-INTAKE-20260727142016443045`

## 已完成

- 用户只需提供全书章节数；平台自动生成 Planning Policy、卷/剧情弧范围、全书章节地图骨架和 AI 串行生成计划。
- 建立整书总纲、卷纲、剧情弧、章节地图、章节规划卡五级机器契约。
- 全书卷范围、剧情弧范围和章节地图必须完整覆盖所有章节，不得遗漏、重叠或重复编号。
- 未来全书保留地图级规划；当前滚动窗口默认生成 20 章场景级详细规划，避免一次性过度细化后失效。
- 章纲必须包含四类目标、真实冲突、场景、因果链、读者体验、信息释放、状态变化、约束、结尾承诺和调整边界。
- 新增防注水门禁：禁止缺进展/缺读者收益/缺状态变化/缺钩子的章节，限制连续过渡章和连续重复功能。
- 大纲设计阶段使用 `candidate`，六视角设计审查和集中审批通过后，平台统一晋升为 `approved` / `approved_for_writing`。
- strict 新项目写作任务 claim 前强制执行大纲门禁，未批准或不可写的章纲不能进入正文。
- 章节发布后自动创建 `outline_refresh` 任务，读取正文实际结果、handoff 和最新 NKB，只刷新未来地图和章纲。
- 修复“修改平台且提到新项目”被错误路由为 `project_design` 的分类优先级问题，并将误分类记录关联为本任务已解决事项。

## 核心实现

- `core/contracts/outline.schema.yaml`
- `scripts/project/outline_governance.py`
- `core/project-lifecycle/五级大纲生成与滚动规划规范.md`
- `core/task-system/templates/outline-refresh.task.yaml`
- `core/contracts/planner.contract.yaml`
- `tests/test_outline_governance.py`

## 关键命令

```text
platform design prepare --project-root <项目> --brief "<方向与全书1000章>" --total-chapters 1000
platform outline prepare --project-root <项目> --total-chapters 1000
platform outline validate --project-root <项目>
platform outline chapter-check --project-root <项目> --chapter CH-001
```

## 兼容性

- 新门禁仅对启用 strict 目录且已进入 Outline Planning Policy 的项目执行写作 claim 拦截。
- 既有项目保持原有路径兼容。
- 大纲始终是规划态，不能直接把未来计划写成 NKB 已发生事实。
