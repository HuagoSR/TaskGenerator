# Milestone F4.2 服务器从零生产 8 题收口报告

> 状态：`historical / completed`
> 最终结论：`f4_from_scratch_validation_passed`
> 完成日期：2026-07-15

## 结论

本轮在服务器 candidate release `f4-2-from-scratch-753a70c` 上，从公开网页、DeepSeek skill 提炼和空 scratch registry 开始，严格串行生产并逐题审查了 8 个财务审计任务。四个 motif 各 2 题，8/8 均通过 Terra 版本化整体编辑、程序独立重算、Luna candidate-blind 求解、全文件视觉检查、人工式放行、verifier 和 rw-task export。

本轮没有读取 GDPVal，没有修改 canonical registry，没有执行外部 solver/grader 评测，也没有切换服务器 `current`。因此它证明的是“小规模混合闭环能够从零稳定生产可完成、可重算的任务”，而不是训练价值、benchmark 权威性或默认链推广。

## 核心验收

| 项目 | 结果 |
| --- | ---: |
| 公开资料收集与冻结 | 1 次 |
| fresh scratch registry | 24 entries |
| 任务总数 | 8/8 |
| 每个 motif | 2/2 |
| Terra 版本化 revision | 8/8 |
| 程序 truth 重算一致 | 8/8 |
| Luna candidate-blind 结果一致 | 8/8 |
| 全 sheet / 全页视觉检查 | 8/8 |
| assistant review | 8/8 pass |
| verifier / rw-task export | 8/8 |
| QA blocked / 重大歧义 | 0 / 0 |
| canonical registry SHA 变化 | 0 |
| 外部 solver / grader eval | false / false |

最终 source freeze SHA-256 为 `9ef3a839...3cd4e`，scratch registry SHA-256 为 `0262c8e8...19ee`；canonical registry 运行前后均为 `7329e377...fc7`。最终 candidate 统一复验再次得到 8/8 truth、contract、visual QA、assistant review 和 export 全通过。

## 逐题结果

| Slot | Motif | 版本 | 可独立重算的关键结果 |
| ---: | --- | --- | --- |
| 1 | fan-in | revision_02 | 10 matched；2 bank-only；2 ledger-only；不推断未提供的账户余额 |
| 2 | cross-check | revision_02 | 11 lines；7 clear；4 hold；0 investigate；数量、价格与重复规则均生效 |
| 3 | policy | revision_01 | 14 transactions；5 exceptions；exception amount 2146.90 |
| 4 | evidence-to-deliverable | revision_01 | 10 tests；6 pass；2 failed；2 unresolved |
| 5 | fan-in | revision_01 | 10 matched；2 bank-only；2 ledger-only；双方期间活动均为 -3099.90 |
| 6 | cross-check | revision_01 | 11 lines；7 clear；4 hold；0 investigate；重复、价格和数量异常均可追溯 |
| 7 | policy | revision_01 | 14 transactions；5 exceptions；exception amount 2164.90 |
| 8 | evidence-to-deliverable | revision_01 | 10 tests；6 pass；2 failed；2 unresolved |

`evidence_to_deliverable` 两题继续标记为 `experimental_motif=true` 和 `default_promotion_allowed=false`。它们的通过不能推翻 Phase 16，也不能恢复为默认 motif。

## 运行与成本

- Campaign：`finance_f4_from_scratch_validation_02`
- 服务器 run root：`/home/huagosr/taskgenerator-data/runs/finance_f4_from_scratch_validation_02`
- 运行时间：约 2 小时 2 分钟。
- Tuzi：backup key only，Terra 10 次、Luna 10 次，共 20 次。
- Token：prompt 290,364；completion 45,796。
- 冻结价格口径成本：约 ¥0.783399，预算剩余约 ¥49.216601。
- 所有最终运行均正常退出，未观察到 OOM；服务器 nginx、Minecraft 和 `current` release 未受影响。

## 边界

原始 task package、teacher truth、模型响应、渲染图片、日志和成本明细保留在 ignored artifacts/服务器 run root，不进入 Git。本报告只记录脱敏指标和逻辑结论。

