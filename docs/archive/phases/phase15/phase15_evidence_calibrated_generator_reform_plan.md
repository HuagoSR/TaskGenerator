# TaskGenerator Phase 15 计划书：Evidence-Calibrated Generator Reform & Guarded LLM Candidate Mode

> 建议文件名：`docs/architecture/phase_15_evidence_calibrated_generator_reform_and_llm_candidate_mode.md`  
> 阶段名称：**Phase 15 — Evidence-Calibrated Generator Reform & Guarded LLM Candidate Mode**  
> 阶段定位：从 Phase 14 的“外部校准与 LLM shadow 证据系统”进入“基于证据的生成器改造与受控 LLM 候选层实验”。  
> 核心目标：把 Phase 14 观察到的 GDPVal 高价值任务特征、TaskGenerator 低/中/高 gap motif 差异、LLM shadow 证据，转化为可验证的生成器改进和 LLM 候选层策略。  
> 基本原则：**不让 LLM 直接接管 ground truth，不启用玄学加权 GoodTaskScore，不把 production QA 等同于训练价值，不把单次 gap 当作正式模型区分结论。**

---

## 0. 2026-07-09 状态修正

Phase 15B 已经补齐原先缺失的 strong-model paired eval、gap-delta 与逐题 failure autopsy。当前 reform 的结论不是 promotion，而是 `hold_for_redesign`。

已经完成的是 Phase 15A 子实验：

```text
target_motif = evidence_to_deliverable
arms = baseline_deterministic vs generator_reform_only
model = gpt-4o-mini
complete_weak_model_pairs = 4 / 4
mean_reform_minus_baseline_delta = -0.2553
```

这个结果只说明：测试过的 reform-only 版本让 `gpt-4o-mini` 分数下降。它不说明 reform 是好现象或坏现象，因为缺少同一四个 case 的 strong-model paired eval 和 gap-delta 对照。

因此当前正确状态是：

```text
phase15_status = closed_for_current_reform
phase15a_status = completed
phase15b_status = completed
phase15b_decision = hold_for_redesign
promotion_decision = do_not_promote_default_chain
```

旧的 local closeout / completion audit 里出现的 `phase15_decision = success`、`completion_status = complete` 应解释为旧实现验收口径下“本地脚手架和已注册检查项完成”。Phase 15B 的 fixed-grader strong/weak evidence 是当前 reform 的最终判断依据。

当前补完计划见：

```text
docs/architecture/phase15_completion_plan_2026-07-09.md
```

Phase 15B 的最低补齐项是：

```text
1. 对同一 4 个 evidence_to_deliverable case 补 strong-model baseline/reform eval。
2. 计算 baseline_gap、reform_gap、gap_delta。
3. 对 case01 / case03 等降分 case 做逐题 failure autopsy。
4. 区分 productive difficulty increased 与 instruction/rubric/evidence/deliverable friction。
5. 再决定 promote_reform、rollback_reform 或 hold_for_redesign。
```

这些证据现在已经补齐，结论是：

```text
mean_gap_delta = 0.1000
positive_gap_delta_case_count = 2
negative_gap_delta_case_count = 2
mean_strong_score_delta = -0.0548
mean_reform_strong_score = 0.4727
```

因此当前 reform 不应并入默认生成器。下一步应重新设计 `evidence_to_deliverable` reform，而不是推广当前版本。

---

## 1. 阶段背景

Phase 14 已经完成，可以收口。它建立了一个新的证据框架：

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

Phase 14 的关键结论是：

1. GDPVal 财务/审计类高 gap 任务通常不是“更长的 prompt”，而是要求模型完成真实工作流：
   - reference files
   - evidence extraction
   - calculation / reconciliation / policy reasoning
   - structured deliverable
   - reviewer-facing output

2. TaskGenerator 自己生成的任务已经有一定模型区分能力，但不稳定：
   - `fan_in_reconciliation` 已经形成高 gap；
   - `cross_check_validation` 和 `policy_application` 形成中等 gap；
   - `evidence_to_deliverable` 几乎没有拉开模型差距。

3. 当前生成题与 GDPVal 高价值题的主要差距集中在：
   - 场景密度不足；
   - reference file 生态更薄；
   - deliverable 真实性偏弱；
   - gap 分布不稳定；
   - 重复证据不足。

4. LLM shadow 已经完成 20/20 metrics，但只能说明“可进入人工审阅和 Phase 15 决策”，不能说明 LLM 一定正向提高任务质量。

5. GoodTaskProfiler 当前应保持 observational，不应启用加权总分。原因是样本仍少，模型组合不完全一致，部分 gap 可能混入工具/格式噪声，LLM shadow 是否正向尚未审阅。

因此，Phase 15 的核心不是“继续多跑一些模型”或“直接让 LLM 接管生成”，而是：

> **把 Phase 14 的观察结果变成可验证的生成器改造与 LLM 候选层实验。**

---

## 2. Phase 15 总目标

Phase 15 的总目标是：

> 在保持现有 production QA / verifier / evidence closure / release governance 稳定性的前提下，用 GDPVal 校准证据和 LLM shadow 审阅结果，系统性提升 TaskGenerator 任务的训练价值、真实工作流感和模型区分能力。

更具体地说，Phase 15 要回答四个问题：

```text
1. 当前生成器哪些 motif 真正有训练价值，哪些 motif 只是 production-ready？
2. GDPVal 高 gap 任务中的哪些 productive complexity 可以安全迁移到 TaskGenerator？
3. LLM 在 realism、reference narrative、rubric、GoldenRun 中哪个位置有可验证正收益？
4. 经过 generator reform / LLM candidate 后，生成任务的 gap、runnability、QA、format-noise 是否真正改善？
```

---

## 3. Phase 15 的核心判断

### 3.1 Phase 15 不是“LLM 接管阶段”

LLM 当前只能进入：

```text
shadow review
candidate proposal
critic / reviewer
narrative suggestion
rubric suggestion
GoldenRun suggestion
```

不能进入：

```text
primary ground truth
unverified scoring truth
silent registry mutation
silent production approval
automatic sampler weight update
```

也就是说：

```text
LLM 输出 = 候选证据 / 候选草案 / 候选批评
deterministic verifier + production QA + evidence closure = 可信性兜底
```

---

### 3.2 Phase 15 不是“GoodTaskScore 打分阶段”

GoodTaskProfiler 继续保持 observational。

允许：

```text
dimension profile
gap autopsy
productive/frictional complexity labels
format-noise risk labels
runnability labels
hypothesis evidence
```

暂缓：

```text
weighted GoodTaskScore
single scalar ranking
automatic retain/discard based on score
```

Phase 15 的判断方式应当是：

```text
pre-registered hypothesis
 -> small controlled experiment
 -> clean paired eval
 -> dashboard comparison
 -> promotion / rollback decision
```

而不是：

```text
某个综合分变高
 -> 自动认定好题
```

---

### 3.3 Phase 15 的主线是“可验证改造”

Phase 14 建立了观察框架。Phase 15 要做的是 intervention：

```text
Baseline task family
 -> Generator Reform
 -> Generator Reform + LLM Candidate
 -> Clean paired eval
 -> Gap / QA / runnability / realism comparison
 -> Decision
```

核心是从“观察”转向“受控实验”。

---

## 4. Phase 15 北极星指标

### 4.1 必达目标

Phase 15 至少应完成：

```text
1. 审阅 20 个 LLM shadow outputs，并给出可执行 adoption recommendation。
2. 完成 generated task gap autopsy，解释 4 个已评测 generated tasks 的 gap 来源。
3. 选定至少 1 个 low-gap motif 做 generator reform，建议优先选择 evidence_to_deliverable。
4. 对同一 motif 生成 baseline / reform / reform+LLM 三组任务。
5. 对 4-8 个改造后任务做 clean paired eval。
6. 输出 A/B/C 对比报告，判断改造是否提升 model gap、workflow realism、training value，同时不增加 unacceptable friction。
```

### 4.2 理想目标

更理想的 Phase 15 成功状态：

```text
1. evidence_to_deliverable 从 low gap 提升到至少 medium gap。
2. 改造后任务保持 candidate_ready / verifier pass / production QA approved。
3. LLM reference narrative 或 realism critic 至少有一个候选层被证明有稳定正收益。
4. 不启用 LLM primary truth。
5. GoodTaskProfiler 仍保持 observational，但能支持明确的 generator reform recommendation。
6. 产出一个 TaskGenerator finance/audit improved release v0.2 candidate。
```

### 4.3 暂不追求目标

Phase 15 暂不追求：

```text
1. 大规模 30/50/100 任务生产。
2. 正式 benchmark-grade model separation claim。
3. 跨领域扩展。
4. PDF / OCR / email / scanned evidence 生态扩展。
5. UCB / bandit / probabilistic sampler。
6. LLM primary GoldenRun / primary rubric / primary reference files。
7. 加权 GoodTaskScore 自动决策。
```

---

## 5. Phase 15 总体结构

Phase 15 分为 10 个子阶段：

```text
15.0 Phase 15 Baseline & Decision Boundary
15.1 LLM Shadow Review & Adoption Gate
15.2 Generated Task Gap Autopsy
15.3 GDPVal Productive Complexity Pattern Library
15.4 Generator Reform Design
15.5 Guarded LLM Candidate Layer V1
15.6 Controlled A/B/C Task Experiment
15.7 Clean Paired Eval & GoodTask Comparison
15.8 Production QA / Release Impact Review
15.9 Promotion / Rollback Decision
15.10 Phase 15 Postmortem & Phase 16 Decision
```

---

# 15.0 Phase 15 Baseline & Decision Boundary

## 目标

冻结 Phase 14 结果，明确 Phase 15 的实验边界。

## 输入

```text
phase14_report.md
good_task_dashboard_report.json
generated_vs_gdpval_comparison_report.json
llm_shadow_metrics/
TaskGenerator phase13 reviewed release tasks
GDPVal calibration profiles
```

## 工作内容

1. 固定 Phase 14 baseline：
   - GDPVal clean paired comparisons = 8；
   - TaskGenerator generated clean paired comparisons = 4；
   - LLM shadow metrics = 20/20 completed；
   - Weighted GoodTaskScore disabled。

2. 明确 Phase 15 不改变：
   - GDPVal 仍为 `eval_calibration_only`；
   - LLM 不进入 primary truth；
   - GoodTaskScore 不启用；
   - production QA 仍独立于 model gap。

3. 建立 Phase 15 run 目录：

```text
artifacts/phase15/
  baseline/
  llm_shadow_review/
  gap_autopsy/
  pattern_library/
  generator_reform/
  llm_candidate/
  ab_experiments/
  eval_results/
  dashboard/
  postmortem/
```

## 输出

```text
docs/handoffs/PHASE_15_BASELINE_<date>.md
artifacts/phase15/baseline/phase15_baseline_manifest.json
```

## 验收标准

```text
- Phase 14 baseline 可追踪。
- Phase 15 实验范围清楚。
- 所有 GDPVal 数据继续标注 eval_calibration_only。
- LLM Candidate Mode 不会被默认启用。
```

---

# 15.1 LLM Shadow Review & Adoption Gate

## 目标

审阅 Phase 14 的 20 个 LLM shadow outputs，判断哪些 LLM 角色有正收益，哪些应暂缓。

## LLM shadow 类型

```text
1. GoldenRun shadow
2. Rubric shadow
3. Realism critic
4. Reference narrative suggestion
```

## 审阅维度

每个 LLM output 至少标注：

```text
helpful
neutral
harmful
unsupported_claim
evidence_mismatch
policy_mismatch
format_noise_added
better_realism
better_training_signal
better_rubric_dimension
hallucinated_business_context
candidate_visible_leakage
```

## 角色级评估

### 1. GoldenRun shadow

判断：

```text
- 是否补充 deterministic GoldenRun 遗漏的合理步骤？
- 是否引用了不存在的证据？
- 是否弱化/强化了不应改变的结论？
- 是否更好地表达 unresolved issue？
- 是否能通过 deterministic verifier？
```

### 2. Rubric shadow

判断：

```text
- 是否提出更真实的能力评价项？
- 是否减少格式噪声？
- 是否错误要求隐藏信息？
- 是否过度奖励写作风格？
- 是否能映射到 candidate-visible evidence？
```

### 3. Realism critic

判断：

```text
- 是否指出了 GDPVal-like 差距？
- 是否与人工直觉和 GDPVal anatomy 一致？
- 是否能识别模板化任务？
- 是否误判 evidence-closed task 为不真实？
```

### 4. Reference narrative suggestion

判断：

```text
- 是否提高场景密度？
- 是否提高文件生态真实感？
- 是否增加无依据事实？
- 是否改变 ground truth？
- 是否导致 verifier / QA 风险？
```

## Adoption Gate

每类 LLM role 给出状态：

```text
adopt_candidate
shadow_only
reject_for_now
needs_more_review
```

建议默认门槛：

```text
adopt_candidate:
  helpful_rate >= 60%
  harmful_rate <= 10%
  unsupported_claim_rate <= 5%
  evidence_mismatch_rate <= 5%
```

如果样本太少，不满足统计可信性，也可以给出：

```text
adopt_candidate_limited_experiment
```

## 输出

```text
src/task_generator/v3_llm_shadow_review.py
Test/run_v3_llm_shadow_review.py
artifacts/phase15/llm_shadow_review/llm_shadow_review_report.json
artifacts/phase15/llm_shadow_review/llm_adoption_gate_report.json
```

## 验收标准

```text
- 20 个 shadow outputs 全部被审阅或明确跳过原因。
- 至少给出每类 LLM role 的 adoption recommendation。
- 不因 dashboard 无 blocker 而自动启用 Candidate Mode。
```

---

# 15.2 Generated Task Gap Autopsy

## 目标

解释当前 4 个 TaskGenerator generated tasks 的 gap 来源，尤其是为什么 `evidence_to_deliverable` low gap、`fan_in_reconciliation` high gap。

## 输入

```text
TaskGenerator generated task outputs
rw-task strong / weak model outputs
grader reports
rubric item scores
GoodTaskProfiler observational profiles
GDPVal comparison reports
```

## 重点问题

```text
1. fan_in_reconciliation 为什么能形成强 gap？
2. evidence_to_deliverable 为什么几乎没有 gap？
3. cross_check_validation 和 policy_application 的 medium gap 来自哪些能力项？
4. gap 是否来自 productive complexity，还是 format / tool noise？
5. weak model 在 low-gap task 中到底做对了什么？
6. strong model 在 low-gap task 中是否也没有被充分挑战？
```

## Gap Autopsy 分类

每个任务输出：

```json
{
  "task_id": "...",
  "motif": "...",
  "strong_score": 0.0,
  "weak_score": 0.0,
  "gap": 0.0,
  "gap_band": "low|medium|high",
  "top_gap_sources": [
    "numeric_accuracy",
    "cross_file_reasoning",
    "policy_application",
    "deliverable_structure",
    "professional_judgment"
  ],
  "format_noise_suspected": false,
  "tool_noise_suspected": false,
  "productive_complexity_level": "low|medium|high",
  "frictional_complexity_level": "low|medium|high",
  "generator_reform_recommendation": []
}
```

## 输出

```text
src/task_generator/v3_generated_task_gap_autopsy.py
Test/run_v3_generated_task_gap_autopsy.py
artifacts/phase15/gap_autopsy/generated_task_gap_autopsy_report.json
```

## 验收标准

```text
- 4 个 generated tasks 都有 gap autopsy。
- low-gap motif 有明确改造假设。
- high-gap motif 有可复用 pattern summary。
```

---

# 15.3 GDPVal Productive Complexity Pattern Library

## 目标

从 GDPVal 高 gap 任务中提取可迁移的 productive complexity pattern，形成生成器改造素材库。

## 输入

```text
GDPVal task anatomy
GDPVal gap autopsy
GDPVal high-gap cases
TaskGenerator generated-vs-GDPVal comparison
```

## Pattern 类型

建议至少抽取：

```text
1. role_and_trigger_pattern
2. evidence_ecology_pattern
3. deliverable_contract_pattern
4. cross_file_reasoning_pattern
5. calculation_reconciliation_pattern
6. policy_or_compliance_pattern
7. professional_judgment_pattern
8. uncertainty_or_exception_pattern
9. reviewer_facing_output_pattern
```

## 示例

```json
{
  "pattern_id": "gdpval_pattern_reconciliation_workbook_v1",
  "source": "GDPVal high-gap task cluster",
  "productive_complexity_type": "calculation_reconciliation",
  "description": "Task requires building a workbook that reconciles multiple source files into a reviewer-facing conclusion.",
  "translatable_to_taskgenerator": true,
  "safe_to_implement_without_new_file_types": true,
  "required_changes": [
    "add second evidence source",
    "add reconciliation difference explanation",
    "add manager-facing summary section"
  ],
  "risk": [
    "could increase runtime",
    "could increase grader complexity"
  ]
}
```

## 输出

```text
src/task_generator/v3_gdpval_productive_complexity_patterns.py
Test/run_v3_gdpval_productive_complexity_patterns.py
artifacts/phase15/pattern_library/gdpval_productive_complexity_pattern_library.json
artifacts/phase15/pattern_library/pattern_to_generator_mapping_report.json
```

## 验收标准

```text
- 至少提取 8-12 个 productive complexity patterns。
- 每个 pattern 标注是否可在当前文件类型内实现。
- 每个 pattern 标注对应的 TaskGenerator motif / generator layer。
```

---

# 15.4 Generator Reform Design

## 目标

基于 gap autopsy 和 GDPVal pattern library，设计第一轮生成器改造。

## 改造优先级

建议优先改造：

```text
evidence_to_deliverable
```

原因：

```text
- 当前 gap 最低；
- 当前 production-ready 不等于 high learning value 的代表；
- 它本来应该是 GDPVal-like 工作交付任务，但当前可能过于模板化；
- 改造后收益容易观察。
```

## Reform 方向

### 1. 场景密度增强

增加：

```text
actor role
business trigger
deadline / review context
recipient / stakeholder
decision consequence
```

### 2. Reference file 生态增强

在不引入新文件类型的前提下增加：

```text
second reference file
manager note
reviewer comment
exception log
policy excerpt
source-vs-summary mismatch
```

### 3. Deliverable 真实性增强

从“写一个结构化报告”升级为：

```text
manager-facing memo
audit finding summary
review worksheet + conclusion
exception escalation note
recommendation with limitations
```

### 4. Productive complexity 增强

加入：

```text
cross-evidence reconciliation
confirmed vs unresolved issue separation
evidence sufficiency judgment
materiality / severity classification
numeric or policy trace
```

### 5. 保持低 friction

避免：

```text
ambiguous expected output
unstable file naming
unscorable free-form deliverable
unsupported hidden information
```

## 输出

```text
src/task_generator/v3_generator_reform_planner.py
Test/run_v3_generator_reform_planner.py
artifacts/phase15/generator_reform/generator_reform_design_report.json
artifacts/phase15/generator_reform/evidence_to_deliverable_reform_spec.json
```

## 验收标准

```text
- 至少一个 low-gap motif 有明确 reform spec。
- reform spec 明确哪些是 deterministic changes，哪些可选 LLM candidate。
- reform spec 不引入新文件类型。
- reform spec 不降低 verifier / production QA 要求。
```

---

# 15.5 Guarded LLM Candidate Layer V1

## 目标

在 shadow review 通过的 role 上，建立受控 LLM candidate 层。

## 建议启用顺序

默认最稳顺序：

```text
1. Realism Critic Gate
2. Reference Narrative Candidate
3. Rubric Candidate
4. GoldenRun Candidate
```

### 1. Realism Critic Gate

作用：

```text
对任务真实感提出 critique，不直接改任务。
```

输出：

```text
llm_realism_critic_candidate_report.json
```

进入主链条件：

```text
- 只作为 QA / dashboard diagnostic input；
- 不阻断 release，除非 reviewer policy 显式使用；
- 不修改 artifacts。
```

### 2. Reference Narrative Candidate

作用：

```text
建议更真实的 manager note / review comment / audit narrative。
```

限制：

```text
- 不能修改 Evidence_ID；
- 不能修改金额、阈值、缺失状态；
- 不能修改 policy truth；
- 不能产生 unsupported claim。
```

进入主链条件：

```text
- deterministic materializer 接受 candidate；
- verifier / evidence closure 通过；
- no hidden leakage；
- production QA 不回退。
```

### 3. Rubric Candidate

作用：

```text
提出更好的能力评价项。
```

限制：

```text
- 不能要求隐藏信息；
- 必须映射 candidate-visible evidence 或 deliverable requirement；
- 必须分离 format criteria 与 reasoning criteria。
```

### 4. GoldenRun Candidate

暂缓或小范围实验。

限制：

```text
- 必须逐条 material claim evidence-supported；
- 不能成为 primary truth；
- 只能和 deterministic GoldenRun 做 diff；
- 只有 verifier pass 后才可作为 teacher proposal。
```

## 输出

```text
src/task_generator/v3_llm_candidate_layer.py
Test/run_v3_llm_candidate_layer.py
artifacts/phase15/llm_candidate/llm_candidate_layer_report.json
artifacts/phase15/llm_candidate/llm_candidate_validation_report.json
```

## 验收标准

```text
- 至少 1 个 LLM role 进入 guarded candidate experiment。
- LLM candidate 不直接成为 truth。
- 所有 LLM candidate 都有 validation report。
- 任何 harmful output 都能被记录并阻断。
```

---

# 15.6 Controlled A/B/C Task Experiment

## 目标

用受控实验验证 generator reform 和 LLM candidate 是否真的提升任务质量。

## 实验组

建议三组：

```text
A. Baseline deterministic
B. Generator reform only
C. Generator reform + LLM candidate layer
```

## 实验对象

优先选择：

```text
evidence_to_deliverable
```

可选第二对象：

```text
policy_application
```

## 每组任务数

最低：

```text
每组 4 个任务
总计 12 个任务
```

理想：

```text
每组 8 个任务
总计 24 个任务
```

## 固定条件

三组应尽量固定：

```text
same domain scope
same file type scope
same production QA gates
same evaluator model pair
same grader model
same run configuration
same release policy
```

## 输出

```text
src/task_generator/v3_phase15_ab_experiment_runner.py
Test/run_v3_phase15_ab_experiment_runner.py
artifacts/phase15/ab_experiments/
  baseline/
  generator_reform/
  generator_reform_llm_candidate/
  phase15_ab_experiment_manifest.json
```

## 验收标准

```text
- 三组都能生成 candidate_ready tasks。
- 至少 4 个任务进入 clean paired eval。
- LLM candidate 组不出现 QA / verifier 系统性退化。
- 实验记录足以比较 model gap、runnability、realism、format noise。
```

---

# 15.7 Clean Paired Eval & GoodTask Comparison

## 目标

对 Phase 15 A/B/C 实验任务进行 clean paired eval，并用 GoodTaskProfiler-Observational 进行比较。

## 模型配置

建议继续使用：

```text
strong_model = gemini-3-pro-preview 或 gpt-5.4-pro
weak_model = gpt-4o-mini
grader = gpt-5.4-pro
```

具体模型可以根据可用性调整，但必须记录：

```text
evaluated_model_name
grader_model
provider
run_config
task_group
experiment_arm
```

## 比较指标

```text
model_gap
strong_score
weak_score
runnability
grading_success
runtime
productive_complexity
frictional_complexity
format_noise_risk
tool_failure_risk
workflow_realism
training_value
verifier findings
production QA status
```

## 成功信号

对于 low-gap motif reform，最低目标：

```text
evidence_to_deliverable:
  baseline gap ≈ low
  reform gap >= medium OR productive complexity clearly improves without QA regression
```

理想目标：

```text
reform+LLM candidate:
  higher workflow realism
  higher or equal model gap
  no increase in unsupported claims
  no increase in grading failures
  no hidden leakage
```

## 输出

```text
artifacts/phase15/eval_results/phase15_clean_paired_eval_report.json
artifacts/phase15/eval_results/phase15_good_task_comparison_report.json
artifacts/phase15/eval_results/phase15_format_noise_report.json
artifacts/phase15/eval_results/phase15_productive_vs_frictional_complexity_report.json
```

## 验收标准

```text
- 至少 4-8 个 Phase 15 generated tasks 有 clean paired eval。
- 能判断 generator reform 是否有效。
- 能判断 LLM candidate 是否正向、无效或有害。
- 不输出 weighted GoodTaskScore。
```

---

# 15.8 Production QA / Release Impact Review

## 目标

验证 Phase 15 改造不会破坏 Phase 13 production MVP 的稳定性。

## 检查项

```text
candidate_ready_rate
verifier_pass_rate
production_qa_approved_rate
release_ready_status
negative_control pass
diversity / dedup
duplicate_subgraph_count
duplicate_skill_signature_count
hidden artifact exposure
evidence closure
runnable paired eval success
```

## Release Impact 分类

每个 experiment arm 给出：

```text
release_safe
release_requires_review
release_blocked
diagnostic_only
```

## 输出

```text
artifacts/phase15/production_impact/phase15_production_qa_impact_report.json
artifacts/phase15/production_impact/phase15_release_impact_report.json
```

## 验收标准

```text
- 改造后的任务不能只提高 gap，却破坏 production QA。
- 如果 LLM candidate 提高真实感但增加 unsupported claims，应判为 diagnostic_only。
- 若 reform 有正收益，应进入 promotion review，而不是静默成为默认生成器。
```

---

# 15.9 Promotion / Rollback Decision

## 目标

将被验证有效的 generator reform 或 LLM candidate layer 作为可审计 promotion proposal，而不是直接写入默认链路。

## Promotion 类型

```text
generator_reform_promotion
motif_grammar_promotion
workflow_archetype_promotion
evidence_dossier_planner_promotion
llm_candidate_role_promotion
rubric_candidate_rule_promotion
```

## Promotion 要求

每个 proposal 必须包含：

```json
{
  "promotion_id": "...",
  "promotion_type": "...",
  "source_experiment_id": "...",
  "affected_modules": [],
  "evidence_summary": {
    "model_gap_delta": null,
    "workflow_realism_delta": null,
    "qa_regression": false,
    "unsupported_claim_delta": null,
    "format_noise_delta": null
  },
  "recommended_decision": "approve|reject|more_evidence",
  "rollback_available": true
}
```

## 输出

```text
artifacts/phase15/promotion/phase15_promotion_proposals.json
artifacts/phase15/promotion/phase15_promotion_decision_report.json
```

## 验收标准

```text
- 所有改造都通过 explicit proposal。
- 没有 silent default-chain mutation。
- 至少一个 reform 可以进入 approved or more_evidence 状态。
```

---

# 15.10 Phase 15 Postmortem & Phase 16 Decision

## 目标

总结 Phase 15 是否成功，以及下一阶段应进入哪条路线。

## Phase 15 成功条件

最低成功条件：

```text
1. LLM shadow review 完成。
2. generated task gap autopsy 完成。
3. GDPVal productive complexity pattern library 完成。
4. 至少一个 motif 的 generator reform spec 完成。
5. 至少一个 guarded LLM candidate role 完成实验或明确拒绝。
6. A/B/C 实验完成。
7. 至少 4 个 Phase 15 generated tasks 有 clean paired eval。
8. 能明确判断下一阶段应优先走 LLM Candidate Mode、Generator Reform，还是 Evaluator Reform。
```

理想成功条件：

```text
1. evidence_to_deliverable 从 low gap 提升到 medium gap。
2. reform+LLM candidate 组提高 workflow realism 且不增加 unsupported claims。
3. 至少一个 LLM role 被批准进入 limited candidate mode。
4. 至少一个 generator reform 被批准进入 promotion review。
5. Phase 15 improved release candidate 通过 production QA。
```

## 输出

```text
docs/handoffs/PHASE_15_EVIDENCE_CALIBRATED_REFORM_SUCCESS_<date>.md
```

或：

```text
docs/handoffs/PHASE_15_EVIDENCE_CALIBRATED_REFORM_BLOCKED_<date>.md
```

## Postmortem 必须回答

```text
1. 哪个 motif 最值得继续改？
2. 哪个 GDPVal productive pattern 最可迁移？
3. LLM 在哪个 role 中最有帮助？
4. LLM 在哪个 role 中风险最大？
5. Generator Reform 是否比 LLM Candidate 更有效？
6. 改造是否提高 model gap？
7. 改造是否提高 workflow realism？
8. 改造是否引入 frictional complexity？
9. Phase 16 应进入哪个方向？
```

---

## 6. Phase 15 的三种可能 Phase 16 路线

### 路线 A：LLM Candidate Mode Expansion

如果 Phase 15 证明 LLM 有明确正收益：

```text
Phase 16A:
  扩大 LLM reference narrative candidate
  扩大 LLM realism critic gate
  小范围引入 rubric candidate
  GoldenRun candidate 继续谨慎
```

适用条件：

```text
LLM candidate improves realism/training value
unsupported claim rate low
QA no regression
model gap stable or improves
```

---

### 路线 B：Generator Reform Scale-Up

如果 generator reform 明显有效，而 LLM 收益有限：

```text
Phase 16B:
  系统性升级 motif grammar
  系统性升级 evidence dossier planner
  扩展 productive complexity patterns
  对更多 motifs 做 A/B eval
```

适用条件：

```text
Generator Reform improves gap / realism
LLM candidate neutral or risky
production QA stable
```

---

### 路线 C：Evaluator / GoodTaskProfiler Reform

如果实验结果混乱或评分噪声很高：

```text
Phase 16C:
  加强 gap autopsy
  加强 format-noise detector
  改进 grader/rubric decomposition
  继续 observational profiler
```

适用条件：

```text
gap changes hard to interpret
format/tool noise high
model pairs inconsistent
grader variance high
```

---

## 7. Phase 15 的优先级

## P0：立即做

```text
1. 固定 Phase 14 baseline。
2. 审阅 20 个 LLM shadow outputs。
3. 完成 generated task gap autopsy。
4. 建 GDPVal productive complexity pattern library。
5. 选择 evidence_to_deliverable 作为第一轮 reform target。
```

## P1：紧随其后

```text
1. 设计 evidence_to_deliverable reform spec。
2. 建 LLM candidate adoption gate。
3. 生成 A/B/C 三组任务。
4. 跑 4-8 道 clean paired eval。
5. 产出 Phase 15 GoodTask comparison。
```

## P2：条件成熟后做

```text
1. 对 policy_application 或 cross_check_validation 做第二轮 reform。
2. 小范围引入 rubric candidate。
3. 扩大生成任务评测数量到 12-24。
4. 生成 Phase 15 improved release candidate。
```

## P3：继续暂缓

```text
1. LLM primary GoldenRun。
2. LLM primary rubric。
3. LLM 直接生成 ground truth 数据。
4. 加权 GoodTaskScore。
5. UCB / bandit。
6. formal benchmark-grade model separation claim。
7. 跨领域扩展。
```

---

## 8. 关键风险与防护

### 风险 1：LLM 输出看起来更自然，但引入 unsupported claim

防护：

```text
evidence citation validation
unsupported claim detector
LLM candidate validation report
deterministic verifier
production QA
```

### 风险 2：gap 变大但来自 format noise

防护：

```text
format-noise report
rubric item gap decomposition
productive/frictional complexity labels
```

### 风险 3：generator reform 提高复杂度但破坏 runnability

防护：

```text
runnability profile
grading success tracking
tool failure taxonomy
negative controls
```

### 风险 4：把 GDPVal 外部校准误用成训练材料

防护：

```text
GDPVal remains eval_calibration_only
not_for_training_generation = true
no GDPVal rewrite into training tasks
```

### 风险 5：GoodTaskProfiler 被过早变成总分

防护：

```text
observational only
no weighted score
no automatic ranking
```

---

## 9. 最终总结

Phase 15 的核心不是“多跑模型”，也不是“让 LLM 接管生成”。

Phase 15 的核心是：

> **用 Phase 14 建立的外部校准证据，设计并验证第一轮真正能提升 TaskGenerator 任务训练价值的改造。**

它要把项目从：

```text
会生产 governed tasks
```

推进到：

```text
会根据 GDPVal 校准和模型差异证据改进任务质量
```

也就是从“生产系统”走向“可学习的任务质量改进系统”。

Phase 15 成功后，TaskGenerator 将不再只是一个可靠的财务/审计任务工厂，而会开始具备真正的研究价值：

```text
能解释什么任务值得训练，
能对比 GDPVal 高价值任务，
能审慎使用 LLM，
能通过受控实验证明 generator reform 是否有效。
```
