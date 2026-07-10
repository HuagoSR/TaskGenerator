# TaskGenerator Phase 16 计划书：Evidence-to-Deliverable 重新设计与合约对齐

> 状态：`completed_redesign_again`（2026-07-10）
> 最终证据：4 cases × 3 arms × 2 models，`24 / 24 completed`，固定 grader `gpt-5.4-pro`。
> 最终判断：两个 redesign arm 的四案例平均 `gap_delta` 均为负，`promotion_decision = do_not_promote_default_chain`。
> 权威收口：`docs/handoffs/PHASE_16_COMPLETION_2026-07-10.md`

> 建议文件名：`docs/architecture/phase_16_evidence_to_deliverable_redesign_plan.md`
> 阶段名称：**Phase 16 — Evidence-to-Deliverable Redesign & Contract Alignment**
> 阶段定位：不是继续推广 Phase 15 的 reform，而是基于 Phase 15B 的负面/混合证据，重新设计 `evidence_to_deliverable` 这个低 gap motif。
> 核心目标：把 `evidence_to_deliverable` 从“看证据写总结”的弱结构任务，升级为“证据强度判断、缺失/冲突处理、结论映射、经理可用交付物”的清晰任务；同时确保 prompt、reference files、GoldenRun、rubric、verifier、production QA 全部对齐。

---

## 1. 阶段背景

Phase 14 建立了外部校准框架：用 GDPVal 财务/审计类任务观察什么题更像“好题”，并保留 GoodTaskProfiler 的 observational 形态，不启用加权总分。Phase 14 的关键结论是：好题不能只看强弱模型分数差距，还要区分真实能力差距、格式噪声、工具失败、评分偏差和任务歧义。

Phase 15 选择了当前生成题中最弱的 motif：`evidence_to_deliverable`。Phase 14 里这个 motif 的生成题几乎没有拉开模型差距，而 `fan_in_reconciliation`、`cross_check_validation`、`policy_application` 表现更好。

Phase 15A 首轮实验只看到弱模型 `gpt-4o-mini` 在 reform 版上变差，因此无法判断这是“好题变难”还是“任务变乱”。Phase 15B 补上了强模型和固定 grader 对照，结论更加清楚：当前 reform 确实制造了一点强弱模型差距，但强模型分数也下降，而且只有一半 case 的 gap 改善；失分中混入了交付物不匹配、rubric/GoldenRun 对齐风险、指令摩擦等问题。

因此 Phase 16 的出发点是：

```text
不要推广当前 reform。
不要继续沿着当前 reform 小修小补。
不要把“弱模型下降”直接解释成“题变好了”。
应该重新设计 evidence_to_deliverable 的任务骨架。
```

---

## 2. Phase 15B 给 Phase 16 的明确输入

Phase 15B 当前结论：

```text
phase15b_decision = hold_for_redesign
promotion_decision = do_not_promote_default_chain
default_generator_change_allowed = false
```

这意味着当前 reform 必须继续留在显式实验开关后面，不能进入默认生成器，也不能进入 release packaging 主路径。

Phase 15B 的关键数字：

```text
mean_baseline_strong_score = 0.5275
mean_baseline_weak_score = 0.2463
mean_reform_strong_score = 0.4727
mean_reform_weak_score = 0.0916
mean_strong_score_delta = -0.0548
mean_weak_score_delta = -0.1547
mean_baseline_gap = 0.2812
mean_reform_gap = 0.3812
mean_gap_delta = 0.1000
positive_gap_delta_case_count = 2
negative_gap_delta_case_count = 2
```

可以这样解释：

```text
reform 平均 gap 变大了一点，说明它有部分区分信号；
但强模型也下降了，而且 4 个 case 里只有 2 个 gap 变大；
所以这不是一个可以推广的稳定改造。
```

Phase 15B 的失败标签：

```text
productive_difficulty_increased = 2
deliverable_mismatch = 3
rubric_or_goldenrun_alignment_risk = 3
difficulty_without_separation_gain = 2
instruction_or_contract_friction = 1
```

这说明当前 reform 最大问题不是“完全没有增加难度”，而是：

```text
增加了一些有用难度，
但也混入了太多交付物、评分标准、GoldenRun、任务指令之间的不对齐。
```

---

## 3. Phase 16 总目标

Phase 16 的目标不是“再做一个更复杂的 evidence_to_deliverable”。

Phase 16 的目标是：

> **先把 evidence_to_deliverable 的任务合约讲清楚，再逐步增加有价值的复杂度。**

这里的“任务合约”指的是 6 件事必须互相一致：

```text
1. candidate prompt：候选模型看到的任务要求是什么？
2. reference files：哪些证据可见？哪些信息缺失、冲突或冗余？
3. expected deliverable：最终应该交什么？结构、文件名、内容范围是什么？
4. GoldenRun：标准解答如何一步步从证据走向结论？
5. rubric：评分标准到底奖励什么能力？
6. verifier / QA：系统如何检查答案是否被证据支撑、是否可评分、是否可发布？
```

如果这 6 层没有对齐，那么再真实的背景、再复杂的证据、再自然的语言，都可能只是噪声。

---

## 4. Phase 16 北极星指标

Phase 16 不以“生成更多任务”为目标，而以“重新设计后是否真正改善 evidence_to_deliverable”为目标。

### 4.1 必达目标

```text
1. 完成 Phase 15B 四个 case 的深度复盘，尤其是 case01 和 case03。
2. 产出 evidence_to_deliverable_contract_v2.json。
3. 产出 aligned GoldenRun / rubric / verifier 设计。
4. 生成 redesign_v2 小样本任务。
5. 完成 2-case clean paired eval。
6. 如果 2-case 结果健康，再扩到 4-case clean paired eval。
7. 输出 promote / hold / redesign_again 的明确判断。
```

### 4.2 理想目标

```text
1. redesign_v2 至少 3 / 4 case 的 strong-model 分数不低于 baseline 太多。
2. redesign_v2 至少 3 / 4 case 的 gap 不低于 baseline。
3. deliverable_mismatch 降到 0 或接近 0。
4. rubric_or_goldenrun_alignment_risk 降到 0 或接近 0。
5. evidence_to_deliverable 从 low-gap motif 提升到稳定 medium-gap motif。
6. 产出可进入 Phase 17 的 redesigned motif grammar / evidence dossier planner patch。
```

### 4.3 暂不追求目标

Phase 16 暂不追求：

```text
1. 大规模 production release。
2. 让 LLM 写 GoldenRun 或 rubric 的主真值。
3. 把当前 reform 改几行就直接推广。
4. 加权 GoodTaskScore。
5. UCB / bandit / sampler 自动学习。
6. 跨领域扩展。
7. PDF / OCR / email 等新文件生态。
8. 正式 benchmark-grade model separation claim。
```

---

## 5. Phase 16 核心原则

### 原则 1：先对齐，再加复杂度

当前 reform 的主要问题不是“不够复杂”，而是复杂度没有被交付物、rubric 和 GoldenRun 稳定接住。

所以 Phase 16 的优先级是：

```text
deliverable contract
→ GoldenRun alignment
→ rubric alignment
→ verifier alignment
→ productive complexity
→ clean eval
```

不是：

```text
更多文件
→ 更多背景
→ 更多噪声
→ 更多真实感
```

---

### 原则 2：弱模型下降不是成功标准

Phase 16 不把“弱模型分数下降”直接当成好事。

好的改造应该更接近：

```text
强模型仍然能做；
弱模型更容易暴露问题；
强弱差距变大；
失分原因来自证据推理、结论映射、缺失/冲突处理，而不是交付物不清或评分不对齐。
```

---

### 原则 3：LLM 继续保持诊断身份

Phase 15B 已经给出判断：目前没有任何 LLM role 被批准写 primary truth、rubric、GoldenRun、evidence mapping、production approval 或 sampler weight。

Phase 16 中 LLM 可以做：

```text
realism critic
candidate prompt clarity critic
deliverable contract critic
rubric clarity critic
```

但不做：

```text
primary GoldenRun writer
primary rubric writer
ground truth generator
production approval decider
```

---

### 原则 4：保持 GoodTaskProfiler observational

Phase 16 仍不启用加权 GoodTaskScore。

允许使用：

```text
strong_score
weak_score
gap_delta
strong_score_delta
weak_score_delta
runnability
productive_complexity_labels
frictional_complexity_labels
deliverable_mismatch_count
rubric_alignment_risk_count
```

不允许使用：

```text
单个神秘总分
自动排名
自动推广
```

---

## 6. Phase 16 总体结构

Phase 16 分为 10 个子阶段：

```text
16.0 Phase 16 Baseline Freeze
16.1 Phase 15B Failure Autopsy Deepening
16.2 Evidence-to-Deliverable Contract V2
16.3 GoldenRun / Rubric / Verifier Alignment V2
16.4 Productive Complexity Pattern Selection
16.5 Redesign V2 Generator Implementation
16.6 Pre-Eval Structural Review And Negative Controls
16.7 Two-Case Clean Eval Pilot
16.8 Four-Case Clean Eval Expansion
16.9 Production Impact And Promotion Review
16.10 Phase 16 Postmortem And Phase 17 Decision
```

---

# 16.0 Phase 16 Baseline Freeze

## 目标

固定 Phase 15B 结果，避免 Phase 16 后续实验混淆基线。

## 输入

```text
docs/handoffs/PHASE_15B_COMPLETION_2026-07-09.md
artifacts/phase15/eval_results/phase15_strong_model_eval_report.json
artifacts/phase15/eval_results/phase15_gap_delta_report.json
artifacts/phase15/failure_autopsy/phase15_reform_failure_autopsy_report.json
artifacts/phase15/phase15b_closeout/phase15b_postmortem_report.json
```

## 工作内容

1. 记录 baseline arm、reform arm 的任务 ID、模型、grader、运行配置。
2. 冻结 Phase 15B gap-delta 结果。
3. 冻结 Phase 15B failure autopsy 标签。
4. 明确当前 reform 不进入默认链路。
5. 建立 Phase 16 工作目录。

## 输出

```text
docs/handoffs/PHASE_16_BASELINE_<date>.md
artifacts/phase16/baseline/phase16_baseline_manifest.json
```

## 验收标准

```text
- Phase 15B 结果可追溯。
- 当前 reform 明确仍 behind experiment flag。
- Phase 16 不会误把 Phase 15B reform 当成默认生成器。
```

---

# 16.1 Phase 15B Failure Autopsy Deepening

## 目标

不再只看总分，而是逐 case 分析为什么 reform 造成强模型下降、弱模型下降、gap 混合变化。

## 重点 case

Phase 15B 已标出优先复盘对象：

```text
pipeline_b_batch_01_evidence_to_deliverable
pipeline_b_batch_03_evidence_to_deliverable
```

## 每个 case 要比较

```text
baseline prompt vs reform prompt
baseline reference files vs reform reference files
baseline expected deliverable vs reform expected deliverable
baseline GoldenRun vs reform GoldenRun
baseline rubric vs reform rubric
baseline model output vs reform model output
strong model failure vs weak model failure
rubric item score delta
```

## 复盘标签

每个失分点标注为：

```text
A. productive_difficulty
   有价值的复杂度，例如需要判断证据强度、处理缺失、区分确认结论和未决事项。

B. deliverable_contract_problem
   模型不清楚要交什么、怎么交、交到哪里、交付物结构是什么。

C. rubric_alignment_problem
   任务改了，但评分标准仍按旧逻辑或不够清楚。

D. goldenrun_alignment_problem
   任务改了，但标准答案没有同步表达新的推理路径。

E. evidence_overload
   证据变多，但没有清楚说明哪些证据支持哪些结论。

F. instruction_friction
   题面变得啰嗦、模糊，模型难以定位核心要求。

G. format_or_grader_noise
   分数变化主要来自格式、文件名、路径、grader 解析等问题。
```

## 输出

```text
src/task_generator/v3_phase16_reform_autopsy_deepener.py
Test/run_v3_phase16_reform_autopsy_deepener.py
artifacts/phase16/autopsy/phase16_reform_deep_autopsy_report.json
artifacts/phase16/autopsy/phase16_case_level_score_delta_report.json
```

## 验收标准

```text
- 4 个 Phase 15B case 都有逐题复盘。
- case01 和 case03 有详细复盘。
- 每个分数下降点都被归类为 productive 或 frictional。
- 能明确哪些 reform 改动可保留，哪些必须删除。
```

---

# 16.2 Evidence-to-Deliverable Contract V2

## 目标

重新定义 `evidence_to_deliverable` 的任务合约，让候选模型、GoldenRun、rubric、verifier 都围绕同一套结构工作。

## Contract V2 核心思想

`evidence_to_deliverable` 不应只是：

```text
看证据，写一段总结。
```

它应该是：

```text
整理证据
→ 判断证据支持强度
→ 识别缺失 / 冲突 / 不确定事项
→ 把证据映射到结论
→ 写出给 manager / reviewer 可用的交付物
→ 保留证据引用和限制说明
```

## Contract V2 必备交付物结构

候选答案至少包含：

```text
1. Evidence inventory
   列出关键 Evidence_ID、来源、含义。

2. Support-strength table
   判断每条关键证据是 strong support、partial support、conflicting、missing、not relevant。

3. Conclusion map
   每个结论必须连接到 Evidence_ID。

4. Unresolved items
   不能确定的事项必须明确列出，不能硬编结论。

5. Manager-facing deliverable
   用自然语言写出给 manager / reviewer 的结论和建议。

6. Traceability appendix
   保留每个 material conclusion 的证据支撑。
```

## Contract V2 JSON 草案

```json
{
  "contract_id": "evidence_to_deliverable_contract_v2",
  "required_sections": [
    "evidence_inventory",
    "support_strength_table",
    "conclusion_map",
    "unresolved_items",
    "manager_facing_deliverable",
    "traceability_appendix"
  ],
  "allowed_support_strength_labels": [
    "strong_support",
    "partial_support",
    "conflicting",
    "missing",
    "not_relevant"
  ],
  "material_conclusion_rule": "Every material conclusion must cite at least one valid Evidence_ID.",
  "uncertainty_rule": "Unsupported or incomplete conclusions must be marked as unresolved, not inferred as final.",
  "deliverable_rule": "The final deliverable must be readable as a manager/reviewer-facing work product, not only a checklist."
}
```

## 输出

```text
SkillRegistry/evidence_to_deliverable_contract_v2.experimental.json
artifacts/phase16/contract/evidence_to_deliverable_contract_v2_report.json
```

## 验收标准

```text
- 合约能清楚说明候选模型要交什么。
- 合约能被 GoldenRun / rubric / verifier 共同使用。
- 合约不引入新文件类型。
- 合约不依赖 LLM primary truth。
```

---

# 16.3 GoldenRun / Rubric / Verifier Alignment V2

## 目标

让 GoldenRun、rubric、verifier 全部围绕 Contract V2 对齐，避免“任务改了但评分没跟上”。

## GoldenRun V2 应包含

```text
1. evidence_inventory_state
2. support_strength_state
3. conclusion_map_state
4. unresolved_items_state
5. manager_deliverable_state
6. traceability_validation_state
```

每个 state 都必须有：

```text
input evidence
expected intermediate output
allowed uncertainty
failure modes
```

## Rubric V2 应包含

```text
fact_checks:
  Evidence_ID 是否正确使用。

reasoning_checks:
  证据强度判断是否合理。

uncertainty_checks:
  是否正确区分 confirmed 和 unresolved。

deliverable_checks:
  最终交付物是否能给 manager / reviewer 使用。

traceability_checks:
  结论是否能回溯到证据。
```

Rubric 不应只奖励：

```text
标题齐全
格式漂亮
复述题面
```

Rubric 应主要奖励：

```text
证据判断
结论映射
缺失/冲突处理
专业交付物
```

## Verifier V2 应检查

```text
1. 每个 material conclusion 是否有 Evidence_ID。
2. Evidence_ID 是否真实存在。
3. unresolved item 是否没有被强行写成 confirmed conclusion。
4. support-strength label 是否来自允许集合。
5. manager-facing deliverable 是否覆盖 conclusion map。
6. traceability appendix 是否和正文一致。
```

## 输出

```text
src/task_generator/v3_evidence_to_deliverable_alignment_v2.py
Test/run_v3_evidence_to_deliverable_alignment_v2.py
artifacts/phase16/alignment/goldenrun_alignment_v2_report.json
artifacts/phase16/alignment/rubric_alignment_v2_report.json
artifacts/phase16/alignment/verifier_alignment_v2_report.json
```

## 验收标准

```text
- GoldenRun / rubric / verifier 能引用同一个 Contract V2。
- 不再出现任务复杂度增加但 rubric/GoldenRun 未同步的问题。
- Phase 15B 中的 rubric_or_goldenrun_alignment_risk 在结构审查中应明显下降。
```

---

# 16.4 Productive Complexity Pattern Selection

## 目标

从 Phase 14 的 GDPVal 观察和 Phase 15B 的失败复盘中，挑选适合 `evidence_to_deliverable` 的“有价值复杂度”。

## 可保留的 productive complexity

```text
1. evidence sufficiency judgment
   判断证据是否足够支撑结论。

2. confirmed vs unresolved separation
   区分已确认事项和未决事项。

3. conflict detection
   识别不同来源之间的冲突。

4. missing evidence escalation
   缺证据时提出后续需要什么。

5. conclusion support mapping
   每个结论必须映射到证据。

6. manager-facing recommendation
   把证据判断转化为可用建议。
```

## 暂缓或删除的 frictional complexity

```text
1. 额外背景但不影响判断。
2. 模糊交付物要求。
3. 没有评分路径的自然语言叙事。
4. 和 Evidence_ID 无关的干扰段落。
5. 需要模型猜测的隐含格式。
```

## 输出

```text
artifacts/phase16/patterns/evidence_to_deliverable_productive_patterns.json
artifacts/phase16/patterns/frictional_complexity_removal_report.json
```

## 验收标准

```text
- 每个保留的复杂度都能映射到 rubric 或 verifier。
- 每个新增任务元素都能解释它要测试什么能力。
- 不再为了“看起来真实”而增加不可评分噪声。
```

---

# 16.5 Redesign V2 Generator Implementation

## 目标

实现 `evidence_to_deliverable` 的 redesign_v2，但必须分层、可开关、可对比。

## 实验组

Phase 16 不直接做复杂 A/B/C/D 大实验。先做三组：

```text
A. baseline_deterministic
   原始稳定版本。

B. contract_v2_only
   只改交付物合约、GoldenRun、rubric、verifier，不增加太多新证据复杂度。

C. contract_v2_plus_productive_complexity
   在 B 的基础上加入有限的证据强度、缺失/冲突、unresolved item 处理。
```

LLM 暂时不作为 mutation arm。LLM 只做诊断：

```text
LLM realism critic
LLM contract clarity critic
```

## 输出

```text
src/task_generator/v3_evidence_to_deliverable_redesign_v2.py
Test/run_v3_evidence_to_deliverable_redesign_v2.py
artifacts/phase16/redesign_v2/baseline/
artifacts/phase16/redesign_v2/contract_v2_only/
artifacts/phase16/redesign_v2/contract_v2_plus_productive_complexity/
artifacts/phase16/redesign_v2/phase16_redesign_v2_manifest.json
```

## 验收标准

```text
- 三组任务都能生成。
- contract_v2_only 先通过结构审查。
- contract_v2_plus_productive_complexity 不得引入新的 deliverable mismatch。
- LLM 不修改 primary artifacts。
```

---

# 16.6 Pre-Eval Structural Review And Negative Controls

## 目标

在花钱跑模型之前，先确认 redesign_v2 没有重复 Phase 15B 的对齐问题。

## 必跑检查

```text
candidate_ready check
verifier pass
export compatible
production QA review
contract validator
GoldenRun alignment check
rubric alignment check
deliverable contract check
negative controls
```

## Negative controls

至少包含：

```text
1. 删除 Evidence_ID。
2. 使用不存在的 Evidence_ID。
3. 把 unresolved item 写成 confirmed conclusion。
4. support-strength label 使用非法值。
5. 删除 manager-facing deliverable。
6. 让 conclusion map 和 traceability appendix 不一致。
```

## 输出

```text
artifacts/phase16/pre_eval/phase16_structural_review_report.json
artifacts/phase16/pre_eval/phase16_negative_control_report.json
```

## 验收标准

```text
- 不通过 structural review 的任务不进入 clean eval。
- negative controls 至少 5 / 6 被正确拦截。
- deliverable_mismatch 和 rubric_alignment_risk 在结构层被提前发现。
```

---

# 16.7 Two-Case Clean Eval Pilot

## 目标

先用 2 个 case 验证 redesign_v2 是否值得扩到 4 个 case。

## 模型设置

```text
strong_model = gemini-3-pro-preview 或 gpt-5.4-pro
weak_model = gpt-4o-mini
grader = gpt-5.4-pro
```

## 对比组

```text
A. baseline_deterministic
B. contract_v2_only
C. contract_v2_plus_productive_complexity
```

## 通过条件

contract_v2_only 至少应满足：

```text
strong_score_delta >= -0.05
no new deliverable_mismatch
no new rubric_alignment_risk
```

contract_v2_plus_productive_complexity 至少应满足：

```text
mean_gap_delta >= 0
strong_score_delta >= -0.10
weak_score_delta <= strong_score_delta 或 gap 不下降
frictional_complexity 不上升
```

## 输出

```text
artifacts/phase16/eval_pilot_2case/phase16_two_case_eval_report.json
artifacts/phase16/eval_pilot_2case/phase16_two_case_gap_delta_report.json
artifacts/phase16/eval_pilot_2case/phase16_two_case_failure_autopsy_report.json
```

## 验收标准

```text
- 至少 2 个 case 有 clean paired eval。
- 能判断是否扩到 4-case。
- 如果 strong 模型明显下降且 gap 无改善，则停止 redesign_v2_plus_productive_complexity。
```

---

# 16.8 Four-Case Clean Eval Expansion

## 目标

如果 2-case pilot 健康，再扩到 4 个 case，和 Phase 15B 的实验规模对齐。

## 对比指标

```text
mean_strong_score_delta
mean_weak_score_delta
mean_gap_delta
positive_gap_delta_case_count
negative_gap_delta_case_count
deliverable_mismatch_count
rubric_alignment_risk_count
difficulty_without_separation_gain_count
instruction_or_contract_friction_count
```

## 推荐推广门槛

只有满足以下条件，才允许进入 promotion review：

```text
1. mean_gap_delta > 0
2. positive_gap_delta_case_count >= 3 / 4
3. mean_strong_score_delta >= -0.05
4. deliverable_mismatch_count = 0
5. rubric_or_goldenrun_alignment_risk_count = 0 或明显低于 Phase 15B
6. production QA 不回退
7. no LLM primary truth
```

如果满足部分条件但不够稳定，则判为：

```text
hold_for_more_evidence
```

如果强模型明显下降或摩擦问题仍多，则判为：

```text
redesign_again
```

## 输出

```text
artifacts/phase16/eval_4case/phase16_four_case_eval_report.json
artifacts/phase16/eval_4case/phase16_four_case_gap_delta_report.json
artifacts/phase16/eval_4case/phase16_four_case_goodtask_comparison_report.json
```

## 验收标准

```text
- 4 个 case 完成 clean paired eval。
- 能给出 promote / hold / redesign_again 的明确建议。
- 不再只根据弱模型下降做判断。
```

---

# 16.9 Production Impact And Promotion Review

## 目标

如果 redesign_v2 有正向证据，也不能直接进默认链路，必须走 production impact 和显式 promotion。

## Production impact 检查

```text
candidate_ready_rate
verifier_pass_rate
export_compatible_rate
production_qa_approved_rate
release_ready_status
negative_control pass
contract_v2 validator pass
diversity / dedup
runtime / grading success
```

## Promotion 类型

可能的 promotion：

```text
evidence_to_deliverable_contract_v2_promotion
goldenrun_alignment_v2_promotion
rubric_alignment_v2_promotion
verifier_alignment_v2_promotion
evidence_dossier_productive_complexity_promotion
motif_grammar_v2_promotion
```

## 输出

```text
artifacts/phase16/production_impact/phase16_production_impact_report.json
artifacts/phase16/promotion/phase16_promotion_proposal.json
artifacts/phase16/promotion/phase16_promotion_decision_report.json
```

## 验收标准

```text
- 没有 silent default-chain mutation。
- 所有改造都能 rollback。
- 如果 redesign_v2 不够好，必须明确保留在实验路径。
```

---

# 16.10 Phase 16 Postmortem And Phase 17 Decision

## 目标

总结 Phase 16 是否完成 `evidence_to_deliverable` 的有效重新设计，并决定 Phase 17 方向。

## Phase 16 成功条件

最低成功条件：

```text
1. Phase 15B failure autopsy 深化完成。
2. evidence_to_deliverable_contract_v2 完成。
3. GoldenRun / rubric / verifier alignment v2 完成。
4. redesign_v2 至少完成 2-case clean paired eval。
5. 能判断 redesign_v2 是否值得扩到 4-case。
6. LLM 仍保持诊断，不写 primary truth。
```

理想成功条件：

```text
1. 4-case clean paired eval 完成。
2. mean_gap_delta > 0。
3. strong_score 不显著下降。
4. deliverable_mismatch 明显下降。
5. rubric/GoldenRun alignment risk 明显下降。
6. evidence_to_deliverable 从 low-gap 改善到稳定 medium-gap。
7. 至少一个 contract / alignment / motif grammar patch 进入 promotion review。
```

## 可能的 Phase 17 路线

### 路线 A：推广 redesigned evidence_to_deliverable

适用条件：

```text
redesign_v2 gap 改善稳定；
strong 模型可解性保留；
production QA 稳定；
摩擦问题下降。
```

下一阶段：

```text
扩大到 8-case / 12-case；
形成 improved release candidate；
开始纳入 production batch。
```

### 路线 B：继续 redesign

适用条件：

```text
gap 有部分信号，但仍然混入明显摩擦；
强模型下降仍然过多；
对齐问题未完全解决。
```

下一阶段：

```text
继续修改 contract / rubric / GoldenRun，而不是扩大评测。
```

### 路线 C：转向 evaluator / rubric reform

适用条件：

```text
模型输出看起来合理，但 grader/rubric 评分不稳定；
gap 变化难以解释；
format noise 或 rubric bias 过高。
```

下一阶段：

```text
加强 rubric item decomposition；
引入 format-noise detector；
改进 grader adapter。
```

### 路线 D：转向其他 motif

适用条件：

```text
evidence_to_deliverable 经过两轮 redesign 仍不稳定；
其他 motif 如 policy_application / cross_check_validation 更有收益。
```

下一阶段：

```text
暂停 evidence_to_deliverable；
把资源转向更有希望的 motif。
```

## 输出

```text
docs/handoffs/PHASE_16_EVIDENCE_TO_DELIVERABLE_REDESIGN_SUCCESS_<date>.md
```

或：

```text
docs/handoffs/PHASE_16_EVIDENCE_TO_DELIVERABLE_REDESIGN_BLOCKED_<date>.md
```

## Postmortem 必须回答

```text
1. Phase 15B reform 失败的主要原因是什么？
2. Contract V2 是否解决了交付物不清问题？
3. Rubric / GoldenRun / verifier 是否真正对齐？
4. 新复杂度是 productive 还是 frictional？
5. 强模型是否仍能稳定完成？
6. 弱模型下降是否对应真实能力缺口？
7. redesign_v2 是否值得推广？
8. LLM 是否仍应只做诊断？
9. Phase 17 应该扩大、继续改、转 evaluator，还是换 motif？
```

---

## 7. Phase 16 工作优先级

### P0：立即做

```text
1. 固定 Phase 15B baseline。
2. 深化 case01 / case03 复盘。
3. 设计 evidence_to_deliverable_contract_v2。
4. 对齐 GoldenRun / rubric / verifier。
5. 建立 structural review 和 negative controls。
```

### P1：紧随其后

```text
1. 实现 contract_v2_only 任务生成。
2. 实现 contract_v2_plus_productive_complexity 任务生成。
3. 做 2-case clean eval pilot。
4. 根据 strong-score / gap / friction 判断是否扩到 4-case。
```

### P2：条件成熟后做

```text
1. 做 4-case clean eval。
2. 做 production impact review。
3. 形成 promotion proposal 或 redesign_again 决策。
4. 如果成功，准备 improved release candidate。
```

### P3：继续暂缓

```text
1. LLM primary GoldenRun。
2. LLM primary rubric。
3. LLM 直接生成 ground truth。
4. 默认启用 LLM candidate mutation。
5. 加权 GoodTaskScore。
6. UCB / bandit。
7. 跨领域扩展。
8. 正式 benchmark-grade model separation claim。
```

---

## 8. 关键风险与防护

### 风险 1：再次把“真实感”误当成“好题”

防护：

```text
每个真实感增强都必须映射到 evidence、rubric 或 verifier。
```

### 风险 2：弱模型下降被误判为成功

防护：

```text
必须同时看 strong_score_delta 和 gap_delta。
```

### 风险 3：GoldenRun / rubric 没有跟随任务改造

防护：

```text
Contract V2 必须先生成 GoldenRun state、rubric criterion、verifier check。
```

### 风险 4：LLM 输出引入无依据内容

防护：

```text
LLM 只做 diagnostic critic；不得修改 primary truth。
```

### 风险 5：再次扩大实验太早

防护：

```text
2-case pilot 不健康时，不扩 4-case；4-case 不健康时，不进 promotion。
```

---

## 9. 最终一句话

Phase 16 的核心不是“继续让 evidence_to_deliverable 更复杂”，而是：

> **把 evidence_to_deliverable 的交付物、证据映射、GoldenRun、rubric 和 verifier 重新对齐，让复杂度真正变成可评分、可训练、可区分模型能力的复杂度。**

如果 Phase 16 成功，`evidence_to_deliverable` 才有可能从当前的低/不稳定 gap motif，变成一个稳定的中等 gap、可训练、可发布的真实工作流任务类型。
