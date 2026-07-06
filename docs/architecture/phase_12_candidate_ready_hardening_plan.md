# TaskGenerator Phase 12 计划书：Candidate-Ready Hardening & Evidence Maturation

> 阶段名称：Phase 12 — Candidate-Ready Hardening & Evidence Maturation
> 阶段定位：Post-Phase-11 hardening，不再证明“能不能出第一个合格任务”，而是证明 candidate-ready 路径是否稳定、可信、可扩展、可评估。
> 核心目标：在保持 report-first、promotion-governed、diagnostic-conservative 原则的前提下，将 Phase 11 的 `3/3 candidate_ready` 从一次 deterministic slice 成功，推进为更稳健的 candidate-ready 生产路径与更可信的评估证据基础。

---

## 1. 背景与阶段判断

Phase 11 已经完成了第一轮 candidate-ready production path closure。

当前已确认的关键事实：

```text
default 3-case deterministic slice:
- 3 / 3 candidate_ready
- 3 / 3 verifier pass
- 3 / 3 exported
- 3 / 3 candidate_ready_compatible
```

这说明 TaskGenerator 已经不再只是“能生成 draft task package”的系统，而是已经具备：

```text
diagnose -> repair -> promote -> rerun -> verify -> candidate_ready
```

的闭环能力。

但是 Phase 11 的成功不能被过度解释。当前仍需保留以下边界：

```text
- Pipeline A substrate 仍然偏弱
- subgraph_confidence 仍然是 medium_with_pipeline_a_gaps
- workflow_context_fit 在部分 motif 上仍偏低
- executed eval 仍然是 diagnostic-only evidence
- formal model separation evidence 尚未成立
- candidate-ready 路径尚未经过更大 batch、negative control 和 repeated eval 压力测试
```

因此，Phase 12 的核心不是继续新增大量架构模块，而是对 Phase 11 的成果做硬化、扩样本、反向验证和证据成熟化。

---

## 2. Phase 12 总目标

Phase 12 的总目标是：

> 将 Phase 11 证明过的 candidate-ready 路径，从“3-case deterministic 成功”推进为“经过扩批次、负例测试、substrate 强化、guarded executed eval 和 dashboard diff 验证的稳定生产路径”。

换句话说，Phase 12 要回答 5 个问题：

```text
1. candidate_ready 是否能在更大 batch 中稳定出现？
2. candidate_ready gate 是否足够硬，能挡住坏任务？
3. Pipeline A substrate 的残留缺口是否能继续缩小？
4. executed eval 是否能从单次 smoke 变成重复、可解释的 diagnostic comparison evidence？
5. 当前 production path 是否能扩展到更多 motif，而不是停留在 Phase 11 的 3 个 case 上？
```

---

## 3. Phase 12 北极星指标

Phase 12 不以“新增多少模块”为成功标准，而以以下结果为成功标准。

### 3.1 必达指标

```text
candidate_ready path remains stable under expanded deterministic regression
```

建议最低门槛：

```text
5-case deterministic regression:
- candidate_ready >= 4 / 5
- verifier_pass >= 4 / 5
- reject = 0
- export validation blocking = 0
```

更理想门槛：

```text
10-case deterministic regression:
- candidate_ready >= 7 / 10
- verifier_pass >= 8 / 10
- reject <= 1
- repeated blocker categories clearly attributable
```

### 3.2 质量硬化指标

```text
negative control tests must fail safely
```

至少应证明：

```text
- evidence ID 被破坏时，verifier 能拦截
- policy-sensitive conclusion 缺 policy clause 时，verifier 能拦截
- reference file 缺列时，quality/export validation 能拦截
- hidden artifact 暴露给 candidate 时，export validator 能拦截
- deliverable-rubric coverage 断裂时，quality gate 能降级
```

### 3.3 Substrate 改善指标

```text
medium_with_pipeline_a_gaps should become less dominant
```

目标不是一轮内彻底消灭所有 Pipeline A gaps，而是让 dashboard 中的 substrate finding 更少、更具体、更可修复。

建议指标：

```text
- typed_resource_coverage 提升
- single_source_support finding 下降
- transition_evidence_absent/local-only finding 下降
- role coverage 提升
- workflow_context_fit 至少在部分 motif 上从 low 提升到 medium
```

### 3.4 Evaluation evidence 成熟指标

Phase 12 不要求正式 model separation truth，但要让 executed eval 从“链路闭合”推进到“重复诊断证据”。

最低目标：

```text
3 candidate_ready cases
x 2 models
x 1 run
```

理想目标：

```text
3 candidate_ready cases
x 3 models
x 2 runs
```

输出应能回答：

```text
- strong / medium / weak model 的差异是否稳定？
- 差异来自 reasoning failure 还是 format following？
- 哪些 rubric items 最有区分性？
- 哪些 rubric items 是 format noise？
- grader 是否稳定？
- retry variance 是否可接受？
```

---

## 4. Phase 12 核心原则

### 原则 1：不再围绕“能不能出第一个合格任务”打转

Phase 11 已经证明可以出 candidate-ready task。Phase 12 不应继续把目标设为“再让一个 case 通过”，而应转向：

```text
稳定性
硬度
可解释性
扩展性
评估证据成熟度
```

---

### 原则 2：candidate_ready 不是 Goodhart 目标

不能为了提高 candidate-ready 数量而削弱检查。

禁止：

```text
- 降低 verifier 严格度
- 删除 blocker
- 把 critical finding 改成 warning
- 隐藏 Pipeline A gaps
- 为单个 case 写死 workaround
```

应优先通过：

```text
- substrate repair
- role coverage repair
- evidence contract repair
- rubric/deliverable alignment repair
- verifier calibration
```

让任务自然通过。

---

### 原则 3：guarded executed eval 仍保守解释

即使 candidate-ready case 能跑多模型，也不能立即宣称 formal model separation evidence。

Phase 12 的 executed eval 仍定位为：

```text
diagnostic comparison evidence
```

而非：

```text
benchmark-grade evidence
```

只有在多 case、多模型、多次运行、rubric item 差异稳定后，才能进入下一阶段的正式 model-separation campaign。

---

### 原则 4：两条主线并行推进，但不能互相污染

Phase 12 有两条主线：

```text
Track A: Candidate-ready executed eval hardening
Track B: Pipeline A substrate hardening
```

Track A 负责验证“当前合格任务能否被真实工具链稳定评估”。
Track B 负责降低“candidate-ready 路径只在当前 3 个 case 上成立”的风险。

二者都必须通过 dashboard 汇总，但不能让 eval score 直接回写 registry 或 sampler。

---

### 原则 5：negative controls 必须进入默认测试体系

当系统开始出现 `3/3 candidate_ready` 后，必须证明系统也能识别坏任务。

Phase 12 必须加入 fault injection / negative control，否则 candidate-ready 的可信度不足。

---

## 5. Phase 12 总体结构

Phase 12 分为 8 个子阶段：

```text
12.0 Baseline Freeze & Workspace Hygiene
12.1 Candidate-Ready Regression Expansion
12.2 Negative Control / Fault Injection
12.3 Pipeline A Substrate Hardening
12.4 Workflow-Context Strengthening
12.5 Guarded Executed Eval Mini-Campaign
12.6 TransitionPriorStore V0 Observational
12.7 Dashboard-Driven Evidence Review
12.8 Phase 12 Postmortem & Next-Stage Decision
```

---

# 12.0 Baseline Freeze & Workspace Hygiene

## 目标

在进入 hardening 前，冻结 Phase 11 成功基线，并清理当前工作区，避免后续无法判断变化来自哪里。

## 工作内容

1. 确认 `.env` 状态：

   * `.env` 可以本地修改；
   * 但绝不能进入 staging；
   * 不得写入 logs / reports / docs / examples。

2. 提交或明确搁置当前未提交修改：

   * Phase 11 代码修改；
   * handoff 文档；
   * dashboard diff；
   * promotion / rollback 相关报告；
   * regression report。

3. 固化 Phase 11 baseline artifacts：

   * `phase11_batch_regression_3case_policy_fix_v2`
   * `phase11_batch_regression_3case_policy_fix_v2_feedback`
   * `phase11_batch_regression_3case_policy_fix_v2_dashboard`
   * `phase_11_batch_regression_report.json`
   * `PHASE_11_CANDIDATE_READY_SUCCESS_2026-07-05.md`

4. 新增 Phase 12 baseline handoff：

```text
docs/handoffs/PHASE_12_BASELINE_<date>.md
```

## 输出

```text
docs/handoffs/PHASE_12_BASELINE_<date>.md
artifacts/pipeline_b/scratch/phase_12_baseline/
```

## 验收标准

```text
- 当前工作区状态清楚
- .env 未 staged
- Phase 11 成功基线可复现
- Phase 12 的后续 diff 有比较对象
```

---

# 12.1 Candidate-Ready Regression Expansion

## 目标

验证 Phase 11 的 `3/3 candidate_ready` 是否能扩展到更大 deterministic slice。

## 工作内容

1. 从默认 3-case 扩展到 5-case：

```text
max_cases = 5
```

2. 若 5-case 稳定，再扩展到 10-case：

```text
max_cases = 10
```

3. 每次运行都生成：

   * batch report
   * batch feedback report
   * global validity reports
   * task verifier reports
   * global dashboard
   * before/after dashboard diff

4. 聚合以下指标：

   * candidate_ready_count
   * revise_count
   * reject_count
   * verifier_pass_count
   * export_validation_status
   * subgraph_confidence distribution
   * workflow_context_fit distribution
   * motif role coverage
   * substrate finding distribution

## 输出

```text
artifacts/pipeline_b/scratch/phase12_regression_5case/
artifacts/pipeline_b/scratch/phase12_regression_5case_feedback/
artifacts/pipeline_b/scratch/phase12_regression_5case_dashboard/

artifacts/pipeline_b/scratch/phase12_regression_10case/
artifacts/pipeline_b/scratch/phase12_regression_10case_feedback/
artifacts/pipeline_b/scratch/phase12_regression_10case_dashboard/

phase12_candidate_ready_regression_report.json
```

## 验收标准

最低：

```text
5-case:
- candidate_ready >= 4
- verifier_pass >= 4
- reject = 0
```

理想：

```text
10-case:
- candidate_ready >= 7
- verifier_pass >= 8
- reject <= 1
```

## 失败解释要求

如果扩展后 candidate-ready 下降，必须归因到：

```text
- Pipeline A substrate
- workflow graph / role coverage
- package generation
- teacher operationalization
- rubric / verifier calibration
- export compatibility
```

不得只写“batch failed”。

---

# 12.2 Negative Control / Fault Injection

## 目标

验证 candidate-ready gate 的硬度。证明系统不仅能放行好任务，也能挡住坏任务。

## Fault Injection 类型

建议至少实现以下 7 类：

| Fault ID                   | 注入方式                                           | 预期结果                                   |
| -------------------------- | ---------------------------------------------- | -------------------------------------- |
| `missing_evidence_id`      | 删除 GoldenRun 或 deliverable 中的 Evidence_ID      | verifier revise/block                  |
| `invalid_evidence_id`      | 使用不存在的 Evidence_ID                             | verifier block                         |
| `missing_policy_clause`    | policy-sensitive conclusion 缺 clause ID        | verifier revise/block                  |
| `broken_reference_column`  | 删除 reference workbook 必需列                      | quality/export validation revise/block |
| `hidden_artifact_exposure` | 将 teacher-only artifact 暴露给 candidate          | export validator invalid               |
| `deliverable_rubric_gap`   | 删除 deliverable requirement 对应 rubric criterion | quality gate revise                    |
| `cyclic_execution_plan`    | 人工制造 execution DAG cycle                       | global validity block                  |

## 工作内容

1. 选择 Phase 11 的 1 个 candidate-ready case 作为 fault injection target。
2. 对每类 fault 生成 mutated artifact copy。
3. 运行：

   * global validity
   * task verifier
   * quality gate
   * export validator
   * dashboard
4. 记录每个 fault 是否被正确捕获。

## 输出

```text
artifacts/pipeline_b/scratch/phase12_fault_injection/
phase12_negative_control_report.json
```

报告字段建议：

```json
{
  "fault_id": "...",
  "mutation_applied": true,
  "expected_detection_layer": "task_verifier",
  "actual_detection_layer": "task_verifier",
  "expected_status": "blocked",
  "actual_status": "blocked",
  "passed_negative_control": true
}
```

## 验收标准

```text
- 至少 5 / 7 fault types 被正确捕获
- 所有 evidence / policy / hidden artifact 类 fault 必须被捕获
- 未被捕获的 fault 必须生成 verifier / quality gate 改进建议
```

---

# 12.3 Pipeline A Substrate Hardening

## 目标

减少 `medium_with_pipeline_a_gaps`，让 candidate-ready 路径不依赖弱 substrate fallback。

## 工作内容

### 12.3.1 Typed Resource Coverage Review

1. 重新运行 substrate audit。

2. 统计：

   * still missing typed resources
   * low-confidence resource proposals
   * no-effective-diff promotions
   * applied promotions
   * rolled-back promotions

3. 对剩余 typed-resource proposals 做分级：

```text
Tier A: high confidence, ready for canonical review
Tier B: medium confidence, needs source span check
Tier C: low confidence, do not apply
Tier D: needs new source evidence
```

### 12.3.2 Canonical Promotion Batch

对 Tier A 做小批量 canonical promotion。

限制：

```text
每轮最多 apply 3-5 个 promotion
每轮必须 rerun regression
每轮必须有 rollback record
```

### 12.3.3 Support Diversity Repair

对 exact single-source skills：

1. 查找是否已有同类 source candidate；
2. 如无，则运行小范围 source collection；
3. 生成 source support proposal；
4. 不直接提高 readiness。

### 12.3.4 Transition Evidence Repair

对 transition gaps：

1. 从 WorkflowEpisode / SkillTraceEdge 中找 source-local evidence；
2. 判断是否可作为 observed transition evidence；
3. 只记录 proposal，不影响 sampler；
4. 后续交给 TransitionPriorStore V0。

## 输出

```text
phase12_substrate_audit_report.json
phase12_typed_resource_review_report.json
phase12_promotion_batch_report.json
phase12_source_support_expansion_report.json
phase12_transition_evidence_proposal_report.json
```

## 验收标准

```text
- applied high-confidence promotions >= 1
- rollback record exists
- target batch subgraph_confidence distribution improves, or gaps become more specific
- no silent registry mutation
- no quality regression after promotion
```

---

# 12.4 Workflow-Context Strengthening

## 目标

让 candidate-ready 不只是结构合格，还更像真实工作任务。

当前问题：

```text
- 部分 motif 的 workflow_context_fit 仍偏 low
- WorkflowArchetype / WorkflowEpisode 已有接口，但还没充分转化为任务真实感
```

## 工作内容

1. 对 candidate-ready cases 做 workflow realism review：

```text
- actor role 是否自然？
- trigger event 是否自然？
- input artifacts 是否像真实材料包？
- deliverable 是否像真实交付物？
- 是否存在业务后果？
- 是否只是 section-filling task？
```

2. 将 review 结果反馈到：

   * WorkflowArchetype registry
   * MotifGraphGrammar
   * EvidenceDossierPlan
   * RealWorldnessReport

3. 对低 workflow_context_fit 的 motif，补充：

   * typical trigger events
   * realistic actor roles
   * common artifact ecology
   * deliverable conventions
   * decision consequence hints

4. 重新运行 regression，观察：

   * workflow_context_fit 是否提升；
   * real_worldness_score 是否提升；
   * quality gate 是否未回退。

## 输出

```text
phase12_workflow_context_review_report.json
phase12_workflow_archetype_patch_proposals.json
phase12_motif_context_patch_report.json
phase12_real_worldness_comparison_report.json
```

## 验收标准

```text
- 至少 1 个 low workflow_context_fit case 提升到 medium
- real_worldness_score 不下降
- candidate_ready 不因 realism strengthening 回退
- 没有把 archetype 变成硬模板
```

---

# 12.5 Guarded Executed Eval Mini-Campaign

## 目标

把 executed eval 从“单 case smoke”推进到“小规模重复诊断证据”。

## 评估对象

只选择：

```text
candidate_ready
verifier pass
export validator compatible
global validity no blocking
```

的 case。

## 建议配置

### Mini-campaign V1

```text
case_count = 3
models = [strong_model, weak_model]
runs_per_model = 1
```

### Mini-campaign V2

若 V1 稳定：

```text
case_count = 3
models = [strong_model, medium_model, weak_model]
runs_per_model = 2
```

## 推荐模型分层

实际模型名可根据可用 API 调整，但必须明确区分：

```text
evaluated_model_name
grader_model
```

不要混淆“谁被评估”和“谁打分”。

## 工作内容

1. 用 Eval Orchestrator 执行 candidate-ready cases。

2. 每个模型独立工作区。

3. 生成：

   * run report
   * summary report
   * feedback report
   * model separation profile
   * dashboard intake

4. 分析：

   * score gap
   * score variance
   * discriminative rubric items
   * format noise items
   * common failure modes
   * toolchain failure rate

## 输出

```text
artifacts/pipeline_b/scratch/phase12_eval_campaign_v1/
phase12_eval_campaign_report.json
phase12_model_separation_profile.json
phase12_eval_dashboard_report.json
```

## 解释边界

即使 V1 成功，也只能表述为：

```text
candidate-ready diagnostic comparison evidence
```

不能表述为：

```text
formal benchmark-grade model separation evidence
```

## 验收标准

```text
- all selected cases complete eval prep
- >= 80% run/grade/summary completed
- profile can distinguish evaluated_model_name and grader_model
- at least some rubric items show non-format discrimination
- dashboard can ingest all eval evidence
```

---

# 12.6 TransitionPriorStore V0 Observational

## 目标

开始积累未来概率采样器所需的结构化 evidence，但暂不影响 sampler 行为。

## 设计原则

```text
record only, no sampling influence
observed_only, no UCB
no automatic posterior update
no registry mutation
```

## 记录对象

每个 candidate-ready / revise / reject case 都可以生成 observation。

字段草案：

```json
{
  "transition_observation_id": "...",
  "case_id": "...",
  "workflow_archetype_id": "...",
  "motif_type": "...",
  "task_graph_shape": "...",
  "from_skill_id": "...",
  "to_skill_id": "...",
  "from_role": "...",
  "to_role": "...",
  "resource_bridge": "...",
  "source_trace_evidence_count": 0,
  "task_usage_count_increment": 1,
  "outcome": "candidate_ready",
  "quality_reason_codes": [],
  "verifier_status": "pass",
  "eval_evidence_status": "not_run|diagnostic_only|usable_diagnostic",
  "confidence": "low",
  "status": "observed_only"
}
```

## 输出

```text
SkillRegistry/v3_transition_prior_store.observed.json
phase12_transition_prior_observation_report.json
```

## 验收标准

```text
- candidate_ready cases generate observations
- revise/reject cases also generate negative or caution observations
- observations include motif and role context
- sampler behavior unchanged
- no UCB or bandit logic introduced
```

---

# 12.7 Dashboard-Driven Evidence Review

## 目标

把 Phase 12 的多类证据统一到 dashboard 中，避免多份报告再次散落。

## Dashboard 应吸收

```text
- expanded regression reports
- negative control report
- substrate hardening reports
- workflow-context review report
- executed eval campaign reports
- model separation profiles
- transition prior observation report
- promotion governance reports
```

## 新增 dashboard 视角

### 12.7.1 Candidate-ready stability

```text
candidate_ready_rate
verifier_pass_rate
export_compatible_rate
motif-level candidate_ready distribution
```

### 12.7.2 Gate hardness

```text
negative_control_pass_rate
faults_not_caught
detection_layer_distribution
```

### 12.7.3 Substrate maturity

```text
typed_resource_coverage_delta
support_diversity_delta
transition_gap_delta
subgraph_confidence_distribution
```

### 12.7.4 Evaluation maturity

```text
executed_case_count
model_count
runs_per_model
score_gap_distribution
format_noise_ratio
diagnostic_discrimination_items
```

### 12.7.5 Workflow realism

```text
workflow_context_fit_distribution
real_worldness_score_distribution
artifact_ecology_richness
deliverable_realism
```

## 输出

```text
phase12_global_dashboard_report.json
phase12_dashboard_diff_report.json
```

## 验收标准

```text
- dashboard can answer whether Phase 12 improved stability
- dashboard can distinguish quality hardening from score chasing
- dashboard can show whether candidate-ready path expanded beyond original 3 cases
```

---

# 12.8 Phase 12 Postmortem & Next-Stage Decision

## 目标

总结 Phase 12 是否完成 hardening，并决定是否进入 Phase 13。

## 成功条件

Phase 12 可判定成功，如果满足：

```text
1. 5-case regression 达到 >= 4 candidate_ready
2. negative controls 大部分被正确捕获
3. substrate gaps 有可测改善
4. 至少 1 轮 guarded executed eval mini-campaign 完成
5. dashboard 能统一展示 regression / negative control / substrate / eval evidence
6. 没有隐式 registry mutation
```

更强成功条件：

```text
1. 10-case regression 达到 >= 7 candidate_ready
2. 3-case x 3-model x 2-run eval campaign 完成
3. workflow_context_fit 有明确改善
4. TransitionPriorStore V0 开始积累 observed outcomes
```

## 输出

```text
docs/handoffs/PHASE_12_HARDENING_SUCCESS_<date>.md
```

或：

```text
docs/handoffs/PHASE_12_HARDENING_BLOCKED_<date>.md
```

## Postmortem 必须回答

```text
- candidate-ready path 是否扩展成功？
- 哪些 motif 最稳定？
- 哪些 motif 仍不稳定？
- gate 是否足够硬？
- substrate 主要剩余问题是什么？
- executed eval 是否稳定？
- model score gap 是否来自真实能力差异？
- 是否可以进入 Phase 13？
```

---

## 6. Phase 12 工作优先级

## P0：立即做

```text
1. 清理工作区，确保 .env 不进入 staging
2. 固化 Phase 11 baseline
3. 运行 5-case deterministic regression
4. 建立 negative control / fault injection
5. 汇总 Phase 12 dashboard
```

## P1：紧随其后

```text
1. 做 typed-resource / source support / transition gap hardening
2. 对 low workflow_context_fit case 做 workflow realism review
3. 做 3-case guarded executed eval mini-campaign
4. 建 TransitionPriorStore V0 observed-only
```

## P2：条件成熟后做

```text
1. 10-case regression
2. 3-model x 2-run eval mini-campaign
3. workflow archetype patch promotion
4. motif grammar patch promotion
```

## P3：继续暂缓

```text
1. UCB / bandit sampler
2. automatic transition prior update
3. formal benchmark-grade model separation claim
4. large domain expansion
5. complex PDF / OCR / scanned evidence ecology
6. production LLM teacher mode
```

---

## 7. 两条路线如何取舍

Codex 提出的两条路线都对：

```text
A. 对现有 3 / 3 candidate_ready case 做 guarded executed eval 扩充
B. 回到 substrate 层处理 typed-resource / transition-gap 弱点
```

Phase 12 不应二选一，而应采用“双主线、不同节奏”：

```text
Track A: Eval hardening
- 快速启动
- 小规模
- 证明 executed evidence 可重复
- 不回写 sampler/registry

Track B: Substrate hardening
- 稳定推进
- 走 promotion governance
- 每轮小批量 apply
- 用 regression 验证
```

优先顺序建议：

```text
先做 5-case regression + negative controls
然后并行：
- 对通过的 candidate_ready cases 做 guarded eval
- 对 dashboard 残留 substrate gaps 做 promotion review
```

原因：

```text
- 如果 5-case regression 不稳，说明先修 production path
- 如果 negative controls 不稳，说明先修 gate hardness
- 如果二者都稳，executed eval 扩充才更有意义
```

---

## 8. 当前阶段最大风险与防护

## 风险 1：把 candidate_ready 当作终点

防护：

```text
引入 negative controls 和 expanded regression
```

## 风险 2：把 eval score 当作模型区分结论

防护：

```text
所有 Phase 12 eval 标记为 diagnostic comparison evidence
```

## 风险 3：promotion 变成隐式 registry mutation

防护：

```text
所有 canonical apply 必须有 source_promotion_key、review、backup、rollback
```

## 风险 4：workflow realism 被结构检查掩盖

防护：

```text
workflow_context_fit + real_worldness review + artifact ecology review
```

## 风险 5：系统开始 Goodhart quality gate

防护：

```text
fault injection + verifier calibration + human spot-check
```

---

## 9. Phase 12 完成后的项目状态

如果 Phase 12 成功，项目将从：

```text
可产出 candidate_ready 的闭环任务工厂 V1
```

升级为：

```text
经过初步硬化的 candidate-ready 任务工厂 V1.5
```

届时可以更有底气地进入 Phase 13：

```text
Phase 13: Small-Scale Model Separation & Prior Learning
```

Phase 13 才适合考虑：

```text
- formal mini benchmark set
- repeated multi-model comparison
- transition prior updater
- cautious probabilistic sampler
- selected UCB-style exploration
```

---

## 10. 一句话总结

Phase 12 的核心不是继续证明系统能生成合格任务，而是证明：

> 这个 candidate-ready 路径是稳定的、能拒绝坏样本的、能被外部执行重复验证的、能通过 substrate 修复继续增强的，并且还没有把 diagnostic evidence 误当成 formal benchmark truth。
