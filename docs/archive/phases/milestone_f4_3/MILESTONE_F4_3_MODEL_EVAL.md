# Milestone F4.3：8题四模型真实执行评测收口

状态：`f4_2_eval_reopens_task_quality`

本报告记录 F4.2 新生产八题的真实 rw-task 执行证据。它只评价任务在当前文件工具环境中的可执行性，不证明训练价值、benchmark 权威性或 `evidence_to_deliverable` 的默认推广资格。

## 核心结果

| 项目 | 结果 |
| --- | ---: |
| 冻结任务 | 8题，四个 motif 各2题 |
| solver 组合 | 32/32 均已尝试 |
| 进程正常返回 | 31/32；另1项为 Sol 2400秒超时 |
| 实际存在交付文件 | 15/32 |
| 无交付文件 | 17/32 |
| 有效交付的 Luna 主评 | 15/15 |
| 有效 Opus 复评 | 6份；另有对无交付项的历史评分及无效评分尝试，不纳入有效复评 |
| OOM | 0 |
| canonical registry | SHA-256 前后均为 `7329e377...090fc7` |
| 服务器 current | 仍为 `milestone-f-data-production-6304e84` |
| Tuzi 预算 | 74次记账请求，保守预留 ¥35.45 / ¥50，实际扣费无法从运行侧可靠取得 |

最初汇总曾把“solver 进程正常结束”误计为“有效交付”，从而报告 `31` 份有效交付和大量 0 分。复核实际目录后确认，只有 `15` 个组合在 `deliverable_files/` 下产生文件。评测 runner 已改为以实际交付文件为准；历史原始 manifest、输出和评分保持只读。

## 按任务诊断

| Slot | Motif | 有效交付 | 诊断 |
| ---: | --- | ---: | --- |
| 1 | fan-in | 3/4 | Sonnet、DeepSeek Pro/Flash 均正确交付并得 1.0；Sol 无文件。 |
| 2 | cross-check | 0/4 | 系统性无交付。prompt 要求 `invoice_match_review.xlsx`，deliverable contract 却声明 `three_way_match_review.xlsx`，输出合同不一致。 |
| 3 | policy | 3/4 | 三个非 Sol 模型均交付并得 1.0；Sol 无文件。 |
| 4 | E2D experimental | 3/4 | 非 Sol 模型均有效，Luna 为 0.9/0.8/1.0；Flash 的 Opus 复评为0.7，属于评分严格度差异，并未发现任务事实错误。 |
| 5 | fan-in | 0/4 | 系统性无交付。prompt 要求直接“populate and submit”候选区同名模板，没有清楚要求复制到输出目录；四模型均未形成提交文件。 |
| 6 | cross-check | 3/4 | 三个非 Sol 模型均交付并得 1.0；Sol 无文件。 |
| 7 | policy | 3/4 | 三个非 Sol 模型均交付并得 1.0；Sol 第二次运行2400秒超时。 |
| 8 | E2D experimental | 0/4 | 系统性无交付。prompt 要求替换 `management_summary.docx`，deliverable contract 却声明 `control_testing_summary.docx`，输出合同不一致。 |

### Solver 归因

`gpt-5.6-sol` 的8题均没有生成交付文件，其中一次最终超时；多次运行达到100 turns，日志显示没有完成文件提交。因此本轮不能把 Sol 的历史 0 分解释为业务能力分数，而应归为 solver/tool execution failure。

其余三个模型在可正确触发输出的5题上共形成15份交付，Luna 平均分分别为：Sonnet `0.98`、DeepSeek Pro `0.96`、DeepSeek Flash `1.00`。这一结果说明这些5题确实可执行，但样本太小且分数高度饱和，不能据此建立稳定能力排序。

### Grader 归因

Slot 4 的 Flash 输出由 Luna 评为1.0、Opus评为0.7。双方都确认核心计数、分类、规则优先级和引用正确；分差来自 Opus 对结构和最小 follow-up 表述的更严格扣分。因此该项属于 grader strictness instability，不构成已确认的任务缺陷。

对没有交付文件的组合，grader 给出的0分只是“缺少提交文件”的结果，不能作为题目业务难度分数。今后 runner 必须在调用 grader 前阻止这类样本进入评分。

## 最终判断

结论为 `f4_2_eval_reopens_task_quality`，原因是8题中有3题出现四模型一致无交付，其中至少2题存在明确的 prompt—deliverable filename 合同冲突，另一题存在模板原地编辑与提交位置不清的问题。按原计划，这满足“至少2题存在任务/合同重大问题”的重新开启条件。

与此同时，另外5题均由三个不同模型成功完成，且四个 motif 都至少有一题形成外部可执行证据。这说明 F4 混合闭环并非整体失败；真正暴露的根因是生产验收只验证了语义、truth、文件可读和 export，却没有验证“solver 按 prompt 能把最终文件提交到 deliverable contract 指定位置”。

下一步应先把输出合同一致性提升为 production blocking gate：prompt 中的目标文件名、候选模板名、rw-task `deliverable_files` 路径必须一致，并增加一次无需外部模型的提交路径 smoke。完成后只重建并小规模复验 Slots 2/5/8，不扩题、不训练，也不切换当前 release。

## 运行治理

- candidate release：`f4-3-eval-eddd09a`，未激活。
- current release：`milestone-f-data-production-6304e84`，未改变。
- 运行无 OOM，未影响服务器既有服务。
- Tuzi 仅使用个人 backup key；DeepSeek 使用 official key。
- 未运行 GDPVal、训练或额外任务。
- 密钥、任务包、原始 provider 输出和运行日志均留在 ignored artifacts，不进入 Git。
