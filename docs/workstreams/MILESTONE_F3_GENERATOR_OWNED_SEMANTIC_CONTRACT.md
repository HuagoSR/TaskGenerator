# Milestone F3：生成器原生语义合同

> 状态：`active / awaiting_external_authorization`
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

## 当前停止点

尚未执行新的 DeepSeek / Tuzi 真实语义审查。下一步必须先获得本次 F3 campaign 的明确外部授权，然后：

1. 用 tracked public synthetic fixture 连续验证两次 DeepSeek 与 Tuzi `gpt-5.4-pro` JSON 合同；
2. 执行真实8+8语义复核；
3. 只有通过后才完成五题外部语义 smoke；
4. 失败则保持 diagnostic，不审计全部60题、不进入训练。

## 边界

- 旧60题只读，不自动升级为训练候选。
- 不调用 solver、grader、GDPVal、SFT 或 RL。
- 不切换服务器 current release。
- raw provider response、任务包和 secret 只保存在 ignored artifacts。
