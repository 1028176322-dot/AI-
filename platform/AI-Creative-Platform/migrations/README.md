# migrations/ — 平台迁移骨架

本目录存放平台级、项目级、知识库（NKB）级的**受控迁移脚本**，用于在不破坏既有数据的前提下，
演进契约、索引与运行时结构。

## 三层子目录
- `platform/`   ：平台自身（core/contracts、registry、platform.yaml 等）的演进迁移
- `project/`    ：项目实例（projects/<id> 下的 NKB、chapters、tasks、runtime）的演进迁移
- `nkb/`        ：NKB 知识库实体（seed、sources、锚点）的演进迁移

## 约定
1. 每个迁移是一个**幂等**脚本（`up()` 可重复执行无副作用），并记录执行结果到 `migrations/<层>/_applied.yaml`。
2. 命名：`NNNN_slug.py`（NNNN 四位序号，slug 描述意图），如 `0001_reindex_nkb.py`。
3. 迁移**只增不改**：已发布的迁移不得原地修改，须新建后续序号迁移来纠正。
4. 迁移不推送、不自动执行于生产；由 `platform migration apply --layer <platform|project|nkb>` 显式触发，且须人工授权。
5. 任何迁移失败须可回滚（提供 `down()` 或快照），禁止留下半迁移状态。

> 阶段2（2026-07-25）已通过 `scripts/` 重排完成工具链迁移；本骨架用于后续契约/版本演进的正式迁移登记。
