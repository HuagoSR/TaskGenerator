# Milestone F3 外部语义校准报告

> 状态：`historical / authoritative for Milestone F3 closure`
> 结论：`f3_semantic_gate_hold_for_redesign_and_secondary_capacity`

## 实现与离线证据

- `TaskSemanticContract V2` 已实现 `design → resolved → verified`。
- 三个财务 motif 均具有 typed locator、候选可见规则、确定性 resolver 和 claim-bound rubric。
- 固定旧8题离线审计：`8/8 blocked`。
- 新生成修复任务离线结果：`8/8 verified + candidate-ready`。
- 五题新生产离线结构结果：`5/5 verified + candidate-ready`。
- 重复离线校准报告 hash 完全一致。

## Provider 准入

- DeepSeek official `deepseek-v4-pro`：公开 fixture 两轮 blind+teacher 合规。
- Tuzi `gpt-5.4-pro`：公开 fixture 两轮完整合同合规；紧凑复审合同也连续两轮合规。
- 完整复审在真实多要求任务上仍较慢，因此正式 runner 改为紧凑 finding-family adjudication。
- 没有保存 raw response、secret 或 Authorization header。

## 真实旧8题

```text
case_count = 8
blocking_recall = 8 / 8
known_finding_recall = 94.7%
successful_compact_secondary = 3
needs_human_review = 8
semantic_gate_pass = 0 / 8
```

确定性审计稳定覆盖 candidate input、decision rule 和 fact-rubric 三个已知问题家族。主审还发现 teacher/deliverable 对齐风险；主审与复审对附加问题家族边界并不总是一致，因此保持人工复核，不误放行。

## 真实 V2 修复任务

前三题结果：

| 任务 | 决策 | 说明 |
| --- | --- | --- |
| fan-in #1 | `needs_secondary_review` | 固定抽审遇到 Tuzi 额度不足，不能完成复审。 |
| fan-in #2 | `pass_with_advisories` | 语义通过，只有非阻塞建议。 |
| cross-check #1 | `needs_secondary_review` | DeepSeek仍发现规则/歧义风险，Tuzi已不可用。 |

前三题已有2题非通过，因此即使其余5题全部通过，最大也只有 `6/8`，低于预设 `7/8`。runner 立即停止，没有用离线结果或 advisory 冒充真实校准成功。

## 最终判断

- 生成器原生合同显著优于 legacy inferred contract，离线闭环有效。
- LLM审查能够发现合同之外的表达与规则歧义，但当前复审容量和跨模型裁决仍不足以支持 blocking promotion。
- 默认链、服务器 current release 和旧60题保持不变。
- 下一步应先修 cross-check V2 的规则表达，并为复审准备稳定、具备额度的独立通道，再做小规模复验。
- 不执行五题外部语义 smoke、不审计60题、不进入SFT/RL。
