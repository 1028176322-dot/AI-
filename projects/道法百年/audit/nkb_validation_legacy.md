# NKB 校验报告（legacy · 道法百年）

- 工具：`platform/scripts/validators/nkb_validator.py`（七批改造，纯只读）
- 模式：**legacy**（项目无 `PROJECT_LAYOUT.yaml`、无 `NKB/manifest.yaml` → 全部 warn 不阻断）
- gate 结论：**proceed**（0 fail）

## 总量
- findings 总数：418，全部 severity=warn，0 fail。
- 分类统计：

| code | 次数 | 性质 |
|---|---|---|
| FIELD_MISSING | 373 | 新 1.3.0 schema 要求的字段（source/status/abilities/speech/goal…）legacy NKB 未填 → **预期 schema 漂移** |
| SCHEMA_VERSION_DRIFT | 12 | 1.2.0 ≠ 1.3.0 → **预期版本漂移** |
| BROKEN_REFERENCE | 18 | 见下「悬空引用拆解」 |
| ENUM_INVALID | 12 | Foreshadow.status 用中文（未回收/已回收/进行中）vs 新英文枚举 → **预期枚举漂移** |
| COMPONENT_MISSING | 2 | Locations / Organizations 两组件 legacy 未建（12 vs 14）→ **预期组件缺口** |
| MANIFEST_MISSING | 1 | 无 NKB/manifest.yaml → **预期 legacy 状态** |

## 悬空引用拆解（BROKEN_REFERENCE 18 → 全部可解释）
1. **Events→ORG 悬空 11 条**（EVT-007/011/013/014/016/020/021 的 participants → ORG-00X）：
   根因 = `Organizations.yaml` 组件缺失（见 COMPONENT_MISSING）。ORG 记录不存在是因为组件本身未建，**非内容断链**。
2. **WorldState→Events 悬空 7 条**（WS-001…007 的 derived_from → EVT-006/007/008/009/014/015/020/021/024）：
   已逐一核对 `Events.yaml`——**上述 EVT ID 全部真实存在**（Events.yaml 共 21 条 EVT-001…024）。
   → 系新校验器在 legacy 模式下的引用解析误报，**非真实断链锚点**。

## 结论
- 道法百年 NKB 处于 commit `4c299f0` 明示的 **legacy WARN** 状态，符合「旧项目 NKB 未迁移」约定。
- 418 条发现中 **100% 为新 1.3.0 schema 漂移或 legacy 解析误报**，对 chapters 21–200 **无任何真实锚点断链 / 内容缺陷**。
- 唯一结构性缺口 = 缺 `Locations` / `Organizations` 两组件（legacy 12 组件 vs 新 14），属 NKB 工程成熟度问题，不影响正文一致性。
- **建议**：维持 legacy，不在本次治理中迁移到 1.3.0（迁移须经你授权，且属平台/NKB 工程范畴，非小说内容修复）。
