# migrations/nkb/ — 知识库迁移

作用于 NKB 实体（seed、sources、锚点、terminology）的演进。

示例场景：
- 锚点错挂修正（如 TL-009/010/WS-003 下山/抵通州章号回填）
- 置信度字段标准变更（confidence 取值归一）
- 实体去重 / 合并

NKB 是唯一事实源，迁移前后须保证 reader_simulator / quality_scorer 门禁仍可闭环。
