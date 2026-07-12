# Milestone F3：生成器原生语义合同

> 状态：`historical / superseded_by_external_calibration_hold`
> 项目级状态仍由根目录《项目概要》管理。

## 目标

把语义有效性从成品后的 LLM 猜测，前移为生成器拥有的 `design → resolved → verified` 合同。LLM 只负责发现语义风险，确定性合同、独立重算和分级裁决决定是否放行。

## 已完成的离线证据

- 新增通用 `TaskSemanticContract V2`、typed locator、expected-result、validator 和 rubric binding。
- 三个财务适配器已覆盖现金对账、三单匹配和费用政策。
- 费用输入已显式加入 `Attendee_Count`；现金任务不再虚构未提供的期初/期末余额；三单匹配新增候选可见状态与优先级规则。
- 三题真实离线链路得到 `3/3 verified、candidate-ready、verifier/export pass`。
- 固定8个旧问题任务的只读审计为 `8/8 blocked`。
- 新生成8个修复任务为 `8/8 verified + candidate-ready`，超过 `7/8` 门槛。
- 重复校准报告 SHA-256 完全一致，外部调用为0。
- 五题新生产的离线结构部分为 `5/5 verified + candidate-ready`。

## 最终停止点

外部授权后，公开 provider 合同验证通过。旧8题真实复核达到 `8/8` 非放行；但 V2 修复任务前三题只有1题通过，另2题需要复审，其中 Tuzi 随后返回额度不足。此时最多只能达到 `6/8`，低于 `7/8` 门槛，campaign 按规则提前停止。

最终为 `f3_semantic_gate_hold_for_redesign_and_secondary_capacity`。未执行五题外部语义 smoke、60题审计或训练。

## 边界

- 旧60题只读，不自动升级为训练候选。
- 不调用 solver、grader、GDPVal、SFT 或 RL。
- 不切换服务器 current release。
- raw provider response、任务包和 secret 只保存在 ignored artifacts。
