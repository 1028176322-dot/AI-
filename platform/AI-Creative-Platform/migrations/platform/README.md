# migrations/platform/ — 平台级迁移

作用于平台根（`core/`、`registry/`、`platform.yaml`、`cli/`、`scripts/`）的结构演进。

示例场景：
- 契约字段新增（core/contracts 升级，旧数据兼容补默认值）
- registry 索引重建
- platform.yaml 路径/版本字段变更

登记格式见 `migrations/README.md` 约定。每个迁移落地后追加到 `_applied.yaml`。
