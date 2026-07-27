# AI 自主设计与 NKB 生成规范

schema_version: 1.0.0  
stage: P2.5–P5  
owner_role: project-producer / design-reviewer / knowledge-manager

## 1. 用户职责

用户只需在 AI 对话中提供题材、灵感、核心设定、偏好、禁区和少量关键裁决，
不负责填写 NKB 字段或逐项设计普通地点、组织、资产与术语。

## 2. 强制链路

```
用户对话方向
  → Inspiration Brief
  → Autonomy Policy
  → Design Gap Matrix
  → 单 Agent 分域生成 Design Candidates
  → 总章节数驱动的五级 Outline Candidates
  → 六视角 Design Review
  → 集中 Approval Packet
  → Approved Design Sources
  → NKB Genesis
  → Readiness Review
  → Chapter Plan
```

任何对话内容、参考作品学习结果或 AI 推断都不得直接写入正式 NKB。

## 3. 自主模式

- `conservative`：中等及以上影响均需作者裁决。
- `balanced`（默认）：地点、普通组织、资产、术语和初始状态可委托 AI；
  故事核心、主角内核、致命 Canon、终局、核心关系、核心真相和高影响变化须作者裁决。
- `autonomous`：除故事核心、致命 Canon 和 fatal 影响外均可委托 AI。

用户授予自主模式后，低风险候选可凭授权证据批准；不得伪造用户明确确认。

## 4. 设计候选

每个候选必须包含：

- 完整 design-source 文档；
- 设计理由与所依据的用户方向/已批准事实；
- 置信度、影响等级、依赖和潜在冲突；
- `user_locked / ai_proposed / delegated_approved / author_approved / derived`
  权威级别；
- 原创隔离声明：只学习参考作品的方法，不复制表达、专名或独特情节组合。

## 5. 设计审查

同一个主 Agent 依次切换审查视角，禁止子 Agent：

1. consistency：跨设定一致性；
2. writeability：能否持续产生具体场景；
3. character_drive：人物是否主动制造情节；
4. reader_value：悬念、情绪、承诺和继续阅读动机；
5. long_form_capacity：长篇升级空间与重复风险；
6. originality：参考学习与项目原创事实隔离。

每个视角必须给出分数、观察、证据、问题、建议和置信度。任一分数低于 75、
置信度低于 0.65 或存在 fatal finding，均不得进入审批。

## 6. 作者集中决策

必须由作者决定的候选集中写入 `lifecycle/design/APPROVAL_PACKET.yaml`。
作者可以在对话中一次性批准/拒绝候选 ID；平台把这次确认保存为
`AUTHOR_DECISION_EVIDENCE.yaml`，未决定项继续阻断。

## 7. Genesis 门禁

strict 新项目必须存在：

- `DESIGN_GAP_MATRIX.gate=proceed`；
- 六视角 `DESIGN_REVIEW.gate.decision=proceed`；
- `APPROVAL_PACKET.gate=proceed`；
- `DESIGN_APPROVAL.decision=pass` 且 `genesis_allowed=true`。

否则 `build_nkb_genesis.py` 必须拒绝生成正式 NKB。

## 8. 可复用命令

```text
platform design prepare --project-root <项目> --brief "<对话方向>" --total-chapters 1000 --mode balanced
platform outline prepare --project-root <项目> --total-chapters 1000
platform outline validate --project-root <项目>
platform design gap --project-root <项目>
platform design candidates --project-root <项目>
platform design review-prepare --project-root <项目>
platform design review-check --project-root <项目>
platform design approval --project-root <项目>
platform design decide --project-root <项目> --decisions <作者决策.yaml>
platform design promote --project-root <项目>
platform design gate --project-root <项目>
platform genesis --project-root <项目>
platform ready --project-root <项目>
```
