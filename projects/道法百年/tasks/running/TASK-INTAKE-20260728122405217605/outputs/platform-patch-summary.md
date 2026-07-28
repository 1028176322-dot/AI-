# 风格系统与去 AI 味全链路实施补丁摘要

- 任务：`TASK-INTAKE-20260728122405217605`
- 实施日期：2026-07-28
- 执行模式：单主 Agent、串行、无委派、无子 Agent
- 保护边界：未修改任何项目正式 NKB 或已批准章节

## 已完成

1. strict-v2 任务主链已从 `chapter_review` 接入 protected manifest、诊断、修订、保真、质量、受控应用、最终回归、NKB 同步和发布。
2. 新增统一事件编排器，确定性消费模板声明的全部风格事件；校验任务状态、角色、租约、会话、输出契约、Schema、哈希和幂等键。
3. Task Packet 与 Context Engine 已覆盖所有风格输入，写作、诊断、修订和审查共享同一份哈希绑定的 L0–L4 指导。
4. 参考学习支持十二维语义证据、独立来源权重、HMAC 指纹、候选审批晋升、原文泄漏防护和参考源撤回重算。
5. 诊断、修订、保真、质量和最终回归已升级为“确定性检查 + AI 结构化语义证据”双层契约。
6. 章节写作、修复、应用、回滚和发布在 strict-v2 下统一调用 Broker；没有直写回退。
7. Broker 已实现可信 Task/Session SSOT、单次 capability、CAS、跨项目/重放/伪造/子 Agent拒绝、IPC 鉴权和原子提交。
8. 作者反馈至少三次独立证据后只生成候选；AI Reader Panel 与真人观察分账，真人数据支持校准、里程碑门禁和回补。
9. CLI、平台命令清单、Schema 注册表、自检、Doctor 和 20 个强制 E2E 已接线。
10. 旧项目不自动迁移；新项目脚手架显式启用 strict-v2 并在 Broker 未部署时 fail closed。

## OS 隔离部署结果

用户明确批准后，已在专用 strict-v2 验证项目完成：

- 创建 `SVC_TaskRunner` 与 `SVC_ChapterWriter`；
- 授予 Writer“以服务身份登录”和 Python 运行时只读执行权限；
- 安装并启动 `AIStyleChapterWriter`；
- Writer 对 drafts/approved 获得 Modify，TaskRunner 被显式 Deny Modify；
- ACL 复读验证通过，重复部署保持单一 ACE；
- TaskRunner 真实身份创建文件与删除文件均失败；
- Broker IPC 可达、使用 Task/Session SSOT、strict dependencies 已启用；
- 密钥未写入项目，部署提供完整 Rollback 模式。

平台能力状态现为 `PRODUCTION_READY`。每个未来 strict-v2 新项目仍必须完成自己的 `DEPLOYED_VERIFIED`，否则按设计 fail-closed。
