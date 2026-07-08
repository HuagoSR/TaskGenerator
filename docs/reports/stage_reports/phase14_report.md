# Phase 14 完成报告：GDPVal Calibration & LLM-Augmented Good Task Loop

## 1. 阶段目标

Phase 14 的目标不是继续盲目造更多题，而是建立一套外部校准体系，回答三个问题：

1. **GDPVal 财务/审计题为什么像“好题”？**
2. **TaskGenerator 自己造出的题和 GDPVal 高价值题相比差在哪里？**
3. **LLM 应该进入哪个环节，还是暂时只保留为 shadow / candidate？**

因此 Phase 14 的定位是：

```text
从“能生产 governed task”
转向
“知道什么题值得生产、为什么值得训练、如何用外部证据校准”
```

所有 GDPVal 数据都保持：

```text
eval_calibration_only = true
not_for_training_generation = true
diagnostic_only = true
```

也就是说：GDPVal 只用于校准、对照、分析，不进入训练题生成池。

---

## 2. 阶段最终状态

Phase 14 已完成，可以收口。

最终 postmortem 结论：

```text
phase14_decision = success
phase15_recommendation = phase15_candidate_mode_or_generator_reform_review
```

核心验收结果：

| 项目 | 结果 |
|---|---:|
| GDPVal subset 任务数 | 10 |
| GDPVal clean paired comparisons | 8 |
| TaskGenerator generated clean paired comparisons | 4 |
| 总 clean paired comparisons | 12 |
| LLM shadow metrics | 20 / 20 completed |
| Dashboard blockers | 0 |
| Weighted GoodTaskScore | 未启用 |
| LLM Candidate Mode | 进入 Phase 15 审阅，不自动启用 |

重要边界：

```text
ideal_2_llm_positive_impact = partial
```

这表示：LLM shadow 的证据已经齐了，但还不能直接说“LLM 一定带来正收益”。下一步需要人工审查 shadow metrics，再决定是否进入 guarded Candidate Mode。

---

## 3. Phase 14 做了什么

Phase 14 实际完成了以下工作链路：

```text
GDPVal mirror
 -> finance/audit subset
 -> rw-task 单题递进评测
 -> clean baseline
 -> task anatomy
 -> gap autopsy
 -> hypothesis ledger
 -> runnable slice
 -> GoodTaskProfiler-Observational
 -> generated-vs-GDPVal comparison
 -> LLM shadow execution
 -> dashboard
 -> postmortem / Phase 15 handoff
```

其中最关键的变化是：一开始 5 题批量跑很不干净，后来改成 **一题一题跑、一题一题诊断**。

这避免了几个严重误判：

- 模型没有 deliverable，却被当成 0 分。
- grader JSON / schema 失败，被误认为模型能力低。
- `.tar.gz` 或辅助脚本被错误送入 grader。
- sandbox timeout 被误当成模型不会做题。
- raw batch 结果直接进入 gap analysis。

最后只把 clean paired comparison 纳入模型差异分析。

---

## 4. GDPVal Clean Baseline 结果

Phase 14 最终使用 10 道 GDPVal finance/audit calibration tasks。

其中：

```text
usable_task_count = 8
needs_model_rerun_count = 2
blocked_task_count = 0
```

Gap 分布：

```text
high = 6
medium = 2
unusable = 2
```

### 4.1 GDPVal 逐题结果

以下分数为百分制近似值。

| 任务 | 类型 | 强模型分数 | 弱模型分数 | 分差 | gap 档位 | 状态 |
|---|---|---:|---:|---:|---|---|
| `83d10` | audit risk metrics spreadsheet | 76.19 | 57.14 | 19.05 | medium | usable |
| `7b08` | Fall Music Tour P&L workbook | 87.64 | 8.99 | 78.65 | high | usable |
| `7d7f` | prepaid amortization workbook | 90.53 | 9.47 | 81.05 | high | usable |
| `ee09` | month-end package | 无强模型分数 | 23.73 | 无 | unusable | needs rerun |
| `87da` | identity theft reimbursement deck | 66.22 | 2.70 | 63.51 | high | usable |
| `5f6c` | finance/audit core task | 无 | 无 | 无 | unusable | needs rerun |
| `b39a` | spreadsheet task | 27.42 | 3.23 | 24.19 | medium | usable |
| `c657` | finance/audit workbook/deck task | 60.34 | 10.34 | 50.00 | high | usable |
| `58ac` | finance report/memo | 84.21 | 22.37 | 61.84 | high | usable |
| `4de6` | finance/audit report task | 67.80 | 0.00 | 67.80 | high | usable |

说明：

- GDPVal 里强模型通常是 `gpt-5.4-pro`。
- 如果 `gpt-5.4-pro` 因超时、上下文、deliverable 问题无法形成 clean pair，则用 `gemini-3-pro-preview` 作为 alternate strong model。
- 弱模型主要是 `gpt-4o-mini`。
- `ee09` 和 `5f6c` 不计入 gap analysis，因为缺少 clean paired evidence。

---

## 5. GDPVal 结果分析

### 5.1 高 gap GDPVal 题的共同特征

高 gap 任务通常不是简单问答，而是要求模型完成真实工作流：

```text
reference files
 -> evidence extraction
 -> calculation / reconciliation / policy reasoning
 -> structured deliverable
 -> reviewer-facing output
```

典型结构包括：

- 明确职业角色，例如 auditor、finance lead、analyst。
- 明确业务场景，例如 month-end close、audit sampling、reimbursement review。
- 有真实交付物要求，例如 `.xlsx`、`.pptx`、`.docx`、`.pdf`。
- 需要跨证据整合，而不是只从 prompt 抽答案。
- 需要遵守格式和业务语境，而不是只算一个数字。
- rubric 能检查结构、计算、证据引用、判断质量。

这说明 GDPVal 高价值题的难点不是“prompt 很长”，而是它要求模型形成完整工作产物。

### 5.2 差距主要来自哪里

当前 gap autopsy 显示，模型差距更常来自：

- 数字准确性
- 表格结构完整性
- evidence reconciliation
- policy / compliance application
- deliverable formatting
- professional judgment
- exception handling

不是所有差距都可信。Phase 14 特别区分了两类复杂度：

| 类型 | 含义 |
|---|---|
| productive complexity | 真实任务复杂度，会拉开模型能力 |
| frictional complexity | 工具、格式、打包、评分噪声，不应当直接算作模型能力 |

例如：

- `.xlsx` 表格任务如果要求公式、分类、汇总、核对，通常是 productive complexity。
- `.tar.gz` 打包、sandbox timeout、grader parse failure，更多是 frictional complexity。

这个区分非常重要，否则会把工具失败误判成“好题”。

---

## 6. TaskGenerator 自己生成题的对比结果

Phase 14 也对 4 道 TaskGenerator release tasks 做了 rw-task clean paired eval。

对比模型：

```text
strong_model = gemini-3-pro-preview
weak_model = gpt-4o-mini
grader = gpt-5.4-pro
```

结果如下，分数为百分制近似值：

| gap 档位 | 题目 / motif | gemini-3-pro-preview | gpt-4o-mini | 分差 |
|---|---|---:|---:|---:|
| low | `pipeline_b_batch_01_evidence_to_deliverable` | 45.28 | 43.40 | 1.89 |
| medium | `pipeline_b_batch_02_cross_check_validation` | 66.15 | 27.69 | 38.46 |
| high | `pipeline_b_batch_03_fan_in_reconciliation` | 83.64 | 14.55 | 69.09 |
| medium | `pipeline_b_batch_04_policy_application` | 57.14 | 15.87 | 41.27 |

分布：

```text
high = 1
medium = 2
low = 1
```

### 6.1 对生成题的解释

这 4 道生成题说明：TaskGenerator 已经不是只能生成“形式上可运行”的题了。

其中：

- `fan_in_reconciliation` 已经能形成强 gap。
- `cross_check_validation` 和 `policy_application` 有中等 gap。
- `evidence_to_deliverable` 分差很小，不能很好区分模型。

这意味着当前生成器已经有一定训练价值信号，但不稳定。

### 6.2 与 GDPVal 的主要差距

和 GDPVal 高 gap 题相比，当前生成题的主要短板是：

1. **场景密度不足**  
   GDPVal 的业务背景、角色、时间点、交付对象更自然。

2. **reference file 生态更薄**  
   GDPVal 往往通过文件内容制造真实工作负担；生成题的 reference files 更规则、更模板化。

3. **deliverable 真实性仍偏弱**  
   GDPVal 的交付物更像真实工作产物，生成题有时更像“为了测能力而构造的表格”。

4. **gap 分布不稳定**  
   4 道生成题里有 1 道 low gap，说明当前 production QA 不能保证模型区分度。

5. **还缺少足够重复证据**  
   4 道题可以做诊断，但不能做 benchmark-grade 结论。

---

## 7. GoodTaskProfiler-Observational 结论

Phase 14 实现的是：

```text
GoodTaskProfiler-Observational V1
```

它记录证据，但不输出加权总分。

原因是目前还不能可靠决定：

```text
哪些指标应该占多少权重？
```

当前 profiler 记录的维度包括：

- model gap
- runnability
- grading status
- productive complexity
- frictional complexity
- evidence closure
- workflow realism
- training value
- evaluation stability
- format-noise risk
- tool-failure risk
- hypothesis evidence

最终 dashboard 明确：

```text
weighted_good_task_score_emitted = false
```

这是正确的。现在如果硬做 GoodTaskScore，会显得很“科学”，但其实权重还没有足够证据支撑。

---

## 8. LLM Shadow 结果

Phase 14 对 5 个 TaskGenerator production-ready tasks 做了 4 类 LLM shadow：

| Shadow 类型 | 数量 | 状态 |
|---|---:|---|
| GoldenRun shadow | 5 / 5 | ready |
| Rubric shadow | 5 / 5 | ready |
| Realism critic | 5 / 5 | ready |
| Reference narrative suggestion | 5 / 5 | ready |

总计：

```text
total_prepared_task_shadows = 20
total_completed_metric_count = 20
total_awaiting_llm_output = 0
impact_readiness = ready_for_impact_analysis
```

### 8.1 LLM Shadow 的结论

当前结论不是：

```text
LLM 已经证明能提高任务质量
```

而是：

```text
LLM shadow 证据已经完整，可以进入人工审阅和 Phase 15 决策
```

Postmortem 对这一项的状态是：

```text
ideal_2_llm_positive_impact = partial
```

原因是：

- shadow output 已经有了；
- metrics 已经可计算；
- 但还需要判断这些差异到底是正向改进、无意义改写，还是引入幻觉/不稳定性。

### 8.2 LLM Candidate Mode 的边界

Dashboard 现在没有 blocker，但 Candidate Mode 不能自动启用。

正确路线是：

```text
review_shadow_metrics_before_candidate_mode
```

也就是说 Phase 15 应先看：

- LLM GoldenRun 是否补上 deterministic GoldenRun 的遗漏？
- LLM rubric 是否提出了更合理的能力维度？
- LLM realism critic 是否和 GDPVal anatomy / human intuition 一致？
- LLM reference narrative 是否提高真实感，还是制造无依据背景？
- unsupported claim rate 是否可控？
- evidence citation validity 是否可接受？

---

## 9. Dashboard 与 Postmortem 结论

GoodTask Dashboard 最终状态：

```text
overall_status = ready_for_phase14_postmortem
phase14_readiness = partial_diagnostic_dashboard_ready
primary_blockers = []
weighted_good_task_score_emitted = false
```

Postmortem 最终状态：

```text
phase14_decision = success
phase15_recommendation = phase15_candidate_mode_or_generator_reform_review
```

成功条件状态：

| 条件 | 状态 |
|---|---|
| GDPVal mirror / subset / boundary | met |
| 至少 4 个 GDPVal clean pairs | met |
| gap autopsy / hypothesis ledger | met |
| GoodTaskProfiler / dashboard | met |
| 12 clean paired comparisons | met |
| LLM shadow 可用于 impact review | partial |
| Phase 15 route 清晰 | met |

---

## 10. 关键结论

### 10.1 GDPVal 确实提供了有价值的外部校准

GDPVal 高 gap 题说明，真实有价值的任务通常不是“更难的题面”，而是：

```text
更真实的工作流
更具体的角色和场景
更密集的证据
更明确的交付物
更强的 rubric 可判定性
```

### 10.2 我们自己的题已经有初步模型区分能力

4 道 TaskGenerator 生成题中：

```text
1 high
2 medium
1 low
```

这说明当前 TaskGenerator 已经能产出部分有模型区分度的任务。

但它还不稳定，尤其是 `evidence_to_deliverable` 几乎没有拉开模型差距。

### 10.3 Production QA 不等于训练价值证明

Phase 13 的 production QA 可以说明：

```text
这个任务结构完整
这个任务可以 release
这个任务 reference/rubric/export 没有明显坏掉
```

但它不能说明：

```text
这个任务一定能训练模型
这个任务一定能拉开模型差距
这个任务一定接近 GDPVal 高价值任务
```

Phase 14 最大的价值之一，就是把这两件事分开了。

### 10.4 GoodTaskScore 暂时不能启用

现在可以记录很多 profiler 维度，但不能给总分。

原因是：

- 样本仍少；
- GDPVal 和生成题使用的强模型组合不完全一致；
- LLM shadow 是否正向还没人工审阅；
- 有些 gap 可能混入工具/格式噪声；
- weighted score 会给人一种过度确定的错觉。

所以当前正确状态是：

```text
GoodTaskProfiler = observational
GoodTaskScore = disabled
```

### 10.5 Phase 15 有两个可能方向

Phase 15 不应该默认“让 LLM 接管”。

它应该在两个方向中做选择：

#### 路线 A：Guarded LLM Candidate Mode

如果 shadow review 显示某一类 LLM 输出确实有稳定正收益，可以让 LLM 进入候选层，例如：

- LLM GoldenRun candidate
- LLM rubric candidate
- LLM reference narrative candidate
- LLM realism critic gate

但必须经过 deterministic verifier 和 production QA。

#### 路线 B：Generator Reform

如果 shadow review 显示 LLM 帮助有限，或者风险太大，就应该优先改生成器本身：

- 强化 workflow archetype
- 强化 motif grammar
- 强化 evidence dossier planner
- 提升 reference file 真实感
- 控制 deliverable 多样性
- 学习 GDPVal 高 gap 任务结构

---

## 11. 推荐的 Phase 15 起点

我建议 Phase 15 第一件事不是继续跑更多模型，而是做：

```text
LLM shadow metric review + generator reform decision
```

具体来说：

1. 逐类审阅 20 个 LLM shadow 输出。
2. 判断哪个 shadow 类型最有正收益。
3. 对比高 gap GDPVal anatomy 和当前生成题 anatomy。
4. 选一个最小可控切入点。
5. 只把 LLM 放进 candidate layer，不进入 primary truth layer。
6. 再用 4-8 道生成题做一轮 clean paired eval 验证。

最稳的候选顺序可能是：

```text
realism critic
 -> reference narrative suggestion
 -> rubric candidate
 -> GoldenRun candidate
```

不建议一开始就让 LLM 直接生成完整任务或 ground truth。

---

## 12. 最终一句话总结

Phase 14 的真正成果不是“我们已经知道好题公式”，而是：

```text
我们已经建立了一套能把 GDPVal、高 gap、生成题质量、LLM shadow、工具噪声和训练价值放在同一个框架里讨论的证据系统。
```

这让 Phase 15 可以从拍脑袋优化，进入有外部校准依据的优化。