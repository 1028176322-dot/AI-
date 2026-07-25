# migrations/project/ — 项目级迁移

作用于 `projects/<id>/` 下的内容资产（NKB、chapters、tasks、runtime、handoffs）演进。

示例场景：
- NKB schema 升级导致既有 seed 需回填新字段
- chapters 目录结构重整（drafts/approved 拆分）
- 任务系统字段新增（task.yaml 增加 gates 字段）

注意：项目级迁移须针对每个项目分别执行，且受 `controlled_write` 与合规门约束。
