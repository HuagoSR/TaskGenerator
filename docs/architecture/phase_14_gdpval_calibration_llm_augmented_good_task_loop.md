# TaskGenerator Phase 14 计划书：GDPVal Calibration & LLM-Augmented Good Task Loop

> 阶段名称：Phase 14 — GDPVal Calibration & LLM-Augmented Good Task Loop
> 阶段定位：从“能生产 governed finance/audit tasks”进入“知道什么题值得生产、为什么值得训练、LLM 应该如何提高题目质量”的校准阶段。
> 适用范围：优先从 GDPVal 中财务、审计、金融、会计、合规、表格分析、报告交付相关任务入手；暂不扩展到其他领域和复杂新文件生态。
> 核心目标：建立一套外部 benchmark 对齐的“好题”评价体系，并在不破坏 deterministic production MVP 稳定性的前提下，引入 LLM shadow / candidate 层，用于提升真实感、GoldenRun、rubric 和任务诊断质量。

---

## 1. 阶段背景

当前 TaskGenerator 已经完成了一个重要阶段：

```text
Phase 11:
  candidate-ready production path closure

Phase 12:
  candidate-ready hardening
  negative controls
  guarded executed eval mini-campaign

Phase 13:
  finance/audit governed production MVP first closure
  production manifest
  diversity / dedup
  production QA gate
  explicit reviewer policy
  strict reviewed release
  production dashboard release_ready
```

这说明系统已经不只是“能生成任务”，而是已经能在 finance/audit 范围内生成 governed production candidate，并通过显式 QA 与 release dashboard 完成首轮 production MVP 收口。

但是，现在出现了一个更深层问题：

```text
系统知道哪些任务能通过内部 QA，
但还不充分知道哪些任务是真正“好题”。
```

也就是说，当前评审制度主要回答：

```text
这道题是否结构完整？
是否 evidence-closed？
是否 verifier pass？
是否 export compatible？
是否 production QA approved？
```

但还没有充分回答：

```text
这道题是否像 GDPVal 的真实任务？
是否能稳定拉开强弱模型？
拉开的差距是否来自真实推理能力，而不是格式噪声？
这道题是否适合作为训练数据？
这道题是否覆盖 GDPVal 中有价值的能力结构？
LLM 生成的内容是否真的提高了题目质量？
```

因此，Phase 14 的核心是建立 **Good Task Calibration Loop**。

---

## 2. Phase 14 总目标

Phase 14 的总目标是：

> 以 GDPVal 财务 / 审计相关任务为外部参照，建立“好题”画像和质量评分体系，并用该体系指导 LLM 在 TaskGenerator 中的引入方式。

Phase 14 不是为了立刻让 LLM 接管整个任务生成流程，也不是为了马上做正式 benchmark-grade model separation。

Phase 14 要完成的是：

```text
1. 本地化 GDPVal 财务 / 审计相关任务。
2. 用 rw-task 对 GDPVal subset 做多模型诊断评测。
3. 分析 GDPVal 中哪些任务能拉开模型差距，以及为什么。
4. 建立 GoodTaskProfiler，把 GDPVal 任务和 TaskGenerator 任务投影到同一个质量空间。
5. 总结“好题”的多维定义。
6. 引入 LLM Shadow Layer，比较 deterministic 和 LLM 生成的 GoldenRun / rubric / realism critique。
7. 根据 GoodTaskProfiler 的结果决定 LLM 后续应进入哪些主链路。
```

---

## 3. Phase 14 的核心判断

### 3.1 LLM 不是目标，而是候选改进手段

LLM 不应被理解为：

```text
只要用了 LLM，题目就会更真实、更好。
```

而应被理解为：

```text
LLM 可以生成更自然的语境、教师推理、rubric 草案和批判审查；
但这些输出是否更好，必须由 GoodTaskProfiler、verifier、production QA、GDPVal calibration 和 executed eval 来判断。
```

因此，Phase 14 先不做：

```text
LLM primary task generator
LLM primary GoldenRun
LLM primary rubric
LLM 自动修改 registry
LLM 自动通过 production QA
```

而先做：

```text
LLM shadow teacher
LLM shadow rubric
LLM realism critic
LLM reference narrative suggestion
LLM-vs-deterministic comparison
```

---

### 3.2 “好题”不能只等于强弱模型分数差距大

模型分数差距是重要启发式，但不是充分标准。

因为分差可能来自：

```text
真实证据推理能力差距
多文件综合能力差距
政策应用能力差距
不确定性处理能力差距
格式遵循差距
工具链失败
评分偏差
题面歧义
```

Phase 14 要区分：

```text
useful model gap
vs
format noise gap
vs
tool failure gap
vs
rubric bias gap
```

所以“好题”应该是多维定义：

```text
好题 =
  GDPVal-like
  + evidence-closed
  + workflow-realistic
  + training-useful
  + evaluation-stable
  + model-separating
  - format-noise-dominated
  - tool-failure-dominated
```

---

### 3.3 GDPVal 是校准参照，不是训练材料

GDPVal 的作用是：

```text
calibration reference
external benchmark anchor
task anatomy reference
model gap reference
```

GDPVal 不应用于：

```text
直接改写成训练题
把 reference files 变形后作为训练数据
把 GDPVal answer / rubric 泄漏进生成器
用 GDPVal 任务内容直接指导同题生成
```

Phase 14 必须明确：

```text
GDPVal local mirror = eval_calibration_only
TaskGenerator production tasks = training_pool_candidate
```

二者目录、manifest、用途必须隔离。

---

## 4. Phase 14 北极星指标

### 4.1 GDPVal Calibration 指标

最低目标：

```text
- 本地化 GDPVal finance/audit-related subset
- 完成至少 10 个 GDPVal subset task 的 rw-task dry-run / executed-run pipeline
- 完成至少 2 个模型的诊断执行
- 生成 GDPVal task anatomy report
- 生成 GDPVal model gap profile
```

理想目标：

```text
- 完成 30 个 GDPVal finance / spreadsheet / report-like task 的诊断评测
- 覆盖 strong / medium / weak 三类模型
- 能识别高区分、高稳定、格式驱动、工具链敏感四类任务
- 形成 GDPVal high-value task cluster
```

---

### 4.2 GoodTaskProfiler 指标

最低目标：

```text
- 对 GDPVal subset 生成 good_task_profile.json
- 对 TaskGenerator release tasks 生成 good_task_profile.json
- 能比较 GDPVal subset 与 generated tasks 的质量分布
```

理想目标：

```text
- 输出 GDPValSimilarity
- 输出 ModelSeparationQuality
- 输出 EvidenceClosure
- 输出 WorkflowRealism
- 输出 TrainingValue
- 输出 EvaluationStability
- 输出 FormatNoiseRisk
- 输出 ToolFailureRisk
```

---

### 4.3 LLM Shadow 指标

最低目标：

```text
- 对至少 5 个 TaskGenerator production-ready tasks 运行 LLM GoldenRun Shadow
- 对至少 5 个任务运行 LLM Rubric Shadow
- 对至少 5 个任务运行 LLM Realism Critic
- 输出 deterministic-vs-LLM comparison reports
```

理想目标：

```text
- LLM Shadow 能发现 deterministic GoldenRun 的遗漏
- LLM Rubric 能提出非格式化的能力评价项
- LLM Realism Critic 的判断与 GoodTaskProfiler / 人工直觉一致
- LLM unsupported claim rate 可测
- LLM evidence citation validity 可测
```

---

## 5. Phase 14 总体结构

Phase 14 分为 10 个子阶段：

```text
14.0 Phase 14 Baseline & Scope Freeze
14.1 GDPVal Local Mirror
14.2 GDPVal Finance/Audit Subset Selection
14.3 GDPVal rw-task Diagnostic Baseline
14.4 GDPVal Task Anatomy Extraction
14.5 GoodTaskProfiler V1
14.6 Generated-vs-GDPVal Comparison
14.7 LLM Shadow Layer V1
14.8 LLM Impact Evaluation
14.9 GoodTask Dashboard
14.10 Phase 14 Postmortem & Phase 15 Decision
```

---

# 14.0 Phase 14 Baseline & Scope Freeze

## 目标

固定 Phase 14 的边界，防止阶段目标漂移。

## 范围内

```text
- GDPVal finance / audit / accounting / financial management / compliance-like subset
- 当前 TaskGenerator finance/audit production release tasks
- 当前 rw-task 评测框架
- 当前 deterministic production pipeline
- LLM shadow / candidate diagnostics
```

## 范围外

```text
- 直接把 GDPVal 改写成训练数据
- 全量 220 GDPVal 一次性跑完
- 正式 benchmark-grade model separation claim
- LLM primary task generator
- UCB / bandit sampler
- 跨领域扩展
- PDF / OCR / email 等新文件生态
```

## 输出

```text
docs/architecture/phase_14_scope.md
docs/handoffs/PHASE_14_BASELINE_<date>.md
artifacts/phase14/baseline/phase14_baseline_manifest.json
```

## 验收标准

```text
- GDPVal 用途明确标记为 eval_calibration_only
- TaskGenerator release tasks 用途明确标记为 generated_training_candidate
- LLM 当前只进入 shadow/candidate diagnostics
```

---

# 14.1 GDPVal Local Mirror

## 目标

将 GDPVal 数据集本地化，形成只读校准镜像。

## 工作内容

1. 下载 / 同步 GDPVal open subset。
2. 为每个任务建立本地目录。
3. 保存 prompt、reference files、metadata。
4. 计算 hash，避免后续误改。
5. 明确用途为 `eval_calibration_only`。

## 建议目录

```text
artifacts/gdpval_local_mirror/
  dataset_manifest.json
  tasks/
    <gdpval_task_id>/
      prompt.txt
      reference_files/
      metadata.json
      file_manifest.json
      source_hashes.json
```

## Manifest 字段

```json
{
  "dataset_name": "openai/gdpval",
  "mirror_created_at": "...",
  "use": "eval_calibration_only",
  "task_count": 0,
  "task_ids": [],
  "hash_policy": "prompt_and_reference_files",
  "not_for_training_generation": true
}
```

## 输出

```text
src/task_generator/v3_gdpval_local_mirror.py
Test/run_v3_gdpval_local_mirror.py
artifacts/gdpval_local_mirror/dataset_manifest.json
```

## 验收标准

```text
- 本地 mirror 可复现
- 每个 task 有 prompt 和 reference files
- 不写入 production release 目录
- 不进入 TaskGenerator training pool
```

---

# 14.2 GDPVal Finance/Audit Subset Selection

## 目标

从 GDPVal 中选择与当前 TaskGenerator 范围最相关的任务子集。

## 选择维度

优先包含：

```text
- Finance and Insurance
- Financial Managers
- Accounting-like tasks
- Audit evidence tasks
- Spreadsheet-heavy tasks
- Report / memo deliverable tasks
- Policy / compliance reasoning tasks
- Cross-file reconciliation tasks
```

如果 GDPVal metadata 中没有直接 audit 标签，则用 prompt / file / deliverable 结构做启发式筛选。

## Subset 类型

```text
finance_audit_core:
  最接近当前 TaskGenerator 的任务

finance_spreadsheet:
  表格、计算、对账、预算、成本分析相关任务

finance_report_memo:
  报告、memo、管理层建议相关任务

policy_compliance_like:
  规则应用、例外处理、合规判断相关任务

hard_reference_tasks:
  文件多、证据链长、交付物复杂的任务
```

## 输出

```text
artifacts/phase14/gdpval_subset/gdpval_finance_audit_subset_manifest.json
artifacts/phase14/gdpval_subset/gdpval_subset_selection_report.json
```

## 验收标准

```text
- 至少选出 10 个初始 GDPVal calibration tasks
- 每个入选任务有 selection reason
- 每个排除任务可以只记录简要 reason
- subset 不与 generated training tasks 混放
```

---

# 14.3 GDPVal rw-task Diagnostic Baseline

## 目标

用当前 rw-task 框架跑 GDPVal subset，建立外部任务的模型表现基线。

## 执行策略

先小后大：

```text
Stage A:
  10 GDPVal subset tasks
  2 models
  1 run per model

Stage B:
  30 GDPVal subset tasks
  3 models
  1 run per model

Stage C:
  high-interest tasks
  3 models
  2 runs per model
```

## 模型分层

```text
strong_model
medium_model
weak_model
```

具体模型名按可用 API 和预算决定，但必须记录：

```text
evaluated_model_name
grader_model
provider
prompt_config
run_config
```

## 每个任务记录

```json
{
  "gdpval_task_id": "...",
  "occupation": "...",
  "industry": "...",
  "models": {
    "strong_model": {
      "completion_status": "completed",
      "score_ratio": 0.0,
      "tool_failure": false
    },
    "weak_model": {
      "completion_status": "completed",
      "score_ratio": 0.0,
      "tool_failure": false
    }
  },
  "score_gap": 0.0,
  "usable_for_gap_analysis": true,
  "diagnostic_only": true
}
```

## 输出

```text
src/task_generator/v3_gdpval_rw_task_eval_adapter.py
Test/run_v3_gdpval_rw_task_eval_adapter.py
artifacts/phase14/gdpval_eval_baseline/
  gdpval_eval_campaign_report.json
  gdpval_model_gap_profile.json
  gdpval_eval_failure_report.json
```

## 验收标准

```text
- 至少 10 个 GDPVal subset tasks 能进入 rw-task eval path
- 至少 2 个模型完成执行或明确记录失败原因
- 输出 score gap 与 failure mode
- 所有结果标记为 calibration / diagnostic，不进入训练数据
```

---

# 14.4 GDPVal Task Anatomy Extraction

## 目标

分析 GDPVal 任务到底长什么样，形成“GDPVal 任务画像”。

## Task Anatomy Schema

建议字段：

```json
{
  "task_id": "...",
  "industry": "...",
  "occupation": "...",
  "role": "...",
  "task_trigger": "...",
  "reference_file_count": 0,
  "file_types": [],
  "deliverable_type": "...",
  "deliverable_format": "...",
  "requires_calculation": false,
  "requires_cross_file_reasoning": false,
  "requires_policy_application": false,
  "requires_exception_handling": false,
  "requires_uncertainty_handling": false,
  "requires_visual_or_document_formatting": false,
  "evidence_density": "low|medium|high",
  "ambiguity_level": "low|medium|high",
  "workflow_realism_features": [],
  "likely_skill_motifs": [],
  "rubric_focus_guess": []
}
```

## 提取方式

第一版可以 hybrid：

```text
deterministic:
  文件数量、文件类型、prompt 长度、deliverable keyword、reference file metadata

LLM-assisted:
  role、trigger、workflow realism、implicit constraints、task motif、ambiguity
```

注意：LLM extraction 只分析 GDPVal anatomy，不生成训练题。

## 输出

```text
src/task_generator/v3_gdpval_task_anatomy.py
Test/run_v3_gdpval_task_anatomy.py
artifacts/phase14/gdpval_anatomy/
  gdpval_task_anatomy.jsonl
  gdpval_anatomy_summary_report.json
```

## 验收标准

```text
- 每个 GDPVal subset task 有 anatomy profile
- 能统计 file type / deliverable / motif / reasoning requirement 分布
- 能和 TaskGenerator task anatomy 对齐比较
```

---

# 14.5 GoodTaskProfiler V1

## 目标

建立统一的“好题”评价器，使 GDPVal 任务和 TaskGenerator 任务能进入同一个质量坐标系。

## 质量维度

GoodTaskProfiler V1 至少包含 8 个维度：

```text
1. GDPValSimilarity
2. ModelSeparationQuality
3. EvidenceClosure
4. WorkflowRealism
5. TrainingValue
6. EvaluationStability
7. FormatNoiseRisk
8. ToolFailureRisk
```

## 维度定义

### 1. GDPValSimilarity

衡量生成题是否接近 GDPVal 的高价值任务结构。

看：

```text
occupation / role similarity
deliverable similarity
reference file ecology similarity
workflow motif similarity
evidence reasoning similarity
task complexity similarity
```

### 2. ModelSeparationQuality

不是简单强弱模型分数差，而是有用差距：

```text
useful_gap =
  reasoning_gap
+ evidence_gap
+ cross_file_gap
+ policy_application_gap
+ uncertainty_handling_gap
- format_noise_gap
- tool_failure_gap
```

### 3. EvidenceClosure

看：

```text
material conclusion evidence support
policy-sensitive conclusion clause support
numeric claim recalculability
unresolved item correctness
rubric hidden-info leakage
```

### 4. WorkflowRealism

看：

```text
actor role realism
trigger event realism
artifact ecology realism
business consequence
deliverable realism
non-template feel
```

### 5. TrainingValue

看：

```text
intermediate states
GoldenRun step quality
TrainingAnnotation richness
failure modes
hidden traps
repairable feedback
```

### 6. EvaluationStability

看：

```text
rw-task completion
grader stability
retry variance
rubric item consistency
export stability
```

### 7. FormatNoiseRisk

看：

```text
score depends mainly on headings
file naming
section ordering
styling
presentation rather than reasoning
```

### 8. ToolFailureRisk

看：

```text
model failed due to file parsing
token limits
tool runtime
unsupported output format
not actual reasoning weakness
```

## 初始分数公式

第一版可以先用可调启发式：

```text
GoodTaskScore =
  0.18 * GDPValSimilarity
+ 0.18 * ModelSeparationQuality
+ 0.16 * EvidenceClosure
+ 0.14 * WorkflowRealism
+ 0.14 * TrainingValue
+ 0.10 * EvaluationStability
- 0.05 * FormatNoiseRisk
- 0.05 * ToolFailureRisk
```

权重不要视为真理，应通过 GDPVal baseline 和人工 review 后调整。

## 输出

```text
src/task_generator/v3_good_task_profiler.py
Test/run_v3_good_task_profiler.py
artifacts/phase14/good_task_profiler/
  good_task_profile.json
  good_task_score_report.json
  good_task_dimension_breakdown.json
```

## 验收标准

```text
- GDPVal subset 可生成 profile
- TaskGenerator production tasks 可生成 profile
- 同一 dashboard 能比较两类任务
- score gap 不再只是 strong_score - weak_score
```

---

# 14.6 Generated-vs-GDPVal Comparison

## 目标

把 TaskGenerator 生成的 finance/audit production tasks 与 GDPVal finance/audit subset 放到同一个坐标系里比较。

## 比较对象

```text
GDPVal calibration tasks:
  gdpval_finance_audit_subset

TaskGenerator tasks:
  phase13_pilot8_diversity_final_smoke release tasks
  后续 30-case / 50-case production pilot tasks
```

## 比较问题

```text
1. 生成题是否比 GDPVal 更模板化？
2. 生成题是否证据闭合更强但真实感更弱？
3. 生成题是否比 GDPVal 更容易？
4. 生成题是否模型区分性不足？
5. 生成题是否 format-noise 风险更低或更高？
6. 生成题是否覆盖了 GDPVal 高价值能力 cluster？
7. 生成题是否更适合作为训练题，而不是 eval 题？
```

## 输出

```text
artifacts/phase14/generated_vs_gdpval/
  generated_vs_gdpval_similarity_report.json
  generated_vs_gdpval_gap_report.json
  generated_vs_gdpval_quality_matrix.json
  generated_task_improvement_recommendations.json
```

## 验收标准

```text
- 能明确指出 generated tasks 和 GDPVal tasks 的主要差距
- 能把差距归类到 generator、LLM、rubric、workflow、evidence、evaluation 中的某一层
- 能产生下一步改进建议
```

---

# 14.7 LLM Shadow Layer V1

## 目标

在不破坏 deterministic production MVP 的前提下，引入 LLM 作为 shadow 层，观察它是否能提升 GoldenRun、rubric 和真实感诊断。

## 14.7.1 LLM GoldenRun Shadow

### 输入

```text
candidate prompt
candidate-visible reference files
evidence_index
policy_index
deliverable requirements
deterministic GoldenRun
rubric
```

### 输出

```text
llm_golden_run_shadow.json
llm_golden_run_comparison_report.json
```

### 比较维度

```text
LLM 是否找到相同 evidence？
LLM 是否发现 deterministic GoldenRun 遗漏？
LLM 是否编造 evidence？
LLM 是否输出 unsupported claim？
LLM 是否更自然地表达不确定性？
LLM 是否提供更好的 intermediate reasoning？
```

### 关键约束

```text
LLM shadow 不进入 release
LLM shadow 不覆盖 deterministic GoldenRun
LLM shadow 不修改 reference files
```

---

## 14.7.2 LLM Rubric Shadow

### 输入

```text
task prompt
reference file summary
GoldenRun
TrainingAnnotation
deterministic rubric
candidate-visible requirements
```

### 输出

```text
llm_rubric_shadow.json
llm_rubric_comparison_report.json
```

### 比较维度

```text
LLM rubric 是否更能评估真实能力？
是否减少格式噪声？
是否发现 deterministic rubric 漏评项？
是否错误要求隐藏信息？
是否过度奖励写作风格？
```

---

## 14.7.3 LLM Realism Critic

### 输入

```text
task prompt
reference file manifest
evidence dossier
deliverable requirements
workflow archetype
motif grammar
production QA report
```

### 输出

```text
llm_realism_critique_report.json
```

### 评价维度

```text
业务触发是否自然
文件生态是否真实
证据冲突是否合理
交付物是否像真实工作产物
任务是否过度模板化
候选者信息是否足够
是否存在不合理简化
```

---

## 14.7.4 LLM Reference Narrative Suggestion

### 目标

仅让 LLM 改善自然语言内容，不让 LLM 决定 ground truth。

LLM 可建议：

```text
manager note
audit workpaper narrative
review comments
policy clause wording
exception explanation
```

LLM 不可决定：

```text
Evidence_ID
Policy_ID
金额
阈值
缺失状态
冲突关系
最终答案
rubric scoring truth
```

## 输出

```text
src/task_generator/v3_llm_shadow_goldenrun.py
src/task_generator/v3_llm_shadow_rubric.py
src/task_generator/v3_llm_realism_critic.py
src/task_generator/v3_llm_reference_narrative_suggestion.py

Test/run_v3_llm_shadow_goldenrun.py
Test/run_v3_llm_shadow_rubric.py
Test/run_v3_llm_realism_critic.py
Test/run_v3_llm_reference_narrative_suggestion.py
```

## 验收标准

```text
- 至少 5 个 production-ready tasks 生成 LLM shadow reports
- LLM unsupported claim rate 可计算
- LLM evidence citation validity 可计算
- LLM realism critique 可进入 GoodTaskDashboard
- LLM 输出不进入 release
```

---

# 14.8 LLM Impact Evaluation

## 目标

评估 LLM shadow 是否真的有价值，而不是只产生更多文本。

## 核心问题

```text
1. LLM GoldenRun 是否比 deterministic GoldenRun 更完整？
2. LLM GoldenRun 是否更容易出现 hallucination？
3. LLM Rubric 是否更能解释模型差距？
4. LLM Realism Critic 是否能预测 GoodTaskScore 低分项？
5. LLM Narrative Suggestion 是否提升 WorkflowRealism？
6. LLM 引入是否提高 FormatNoiseRisk？
```

## 指标

```text
llm_supported_claim_rate
llm_unsupported_claim_rate
llm_valid_evidence_ref_rate
llm_policy_ref_validity
llm_rubric_hidden_info_violation_count
llm_rubric_format_noise_delta
llm_realism_critique_alignment
llm_added_training_value_items
```

## 输出

```text
artifacts/phase14/llm_impact/
  llm_impact_evaluation_report.json
  llm_shadow_failure_taxonomy.json
  llm_adoption_recommendation_report.json
```

## 验收标准

```text
- 能明确判断 LLM 在哪些位置有帮助
- 能明确判断 LLM 在哪些位置风险高
- 能给出是否进入 LLM Candidate Mode 的建议
```

---

# 14.9 GoodTask Dashboard

## 目标

把 GDPVal baseline、generated-task profile、LLM shadow、model gap、production QA 统一到一个 dashboard 中。

## Dashboard 需要展示

```text
GDPVal subset:
  task anatomy distribution
  model gap distribution
  high-separation task clusters
  format-noise task clusters

Generated tasks:
  GoodTaskScore distribution
  GDPValSimilarity distribution
  WorkflowRealism distribution
  TrainingValue distribution
  ModelSeparationQuality distribution

LLM shadow:
  unsupported claim rate
  rubric improvement candidates
  realism critique summary
  LLM adoption recommendation

Comparison:
  generated-vs-GDPVal gaps
  recommended generator improvements
  recommended LLM insertion points
```

## 输出

```text
src/task_generator/v3_good_task_dashboard.py
Test/run_v3_good_task_dashboard.py
artifacts/phase14/good_task_dashboard/good_task_dashboard_report.json
```

## 验收标准

```text
- dashboard 能说明什么题比较好
- dashboard 能说明 generated tasks 离 GDPVal 高价值任务差在哪里
- dashboard 能说明 LLM 应该先用于哪里
- dashboard 不把 GDPVal 直接纳入训练数据
```

---

# 14.10 Phase 14 Postmortem & Phase 15 Decision

## 目标

根据 GDPVal calibration 和 LLM shadow 结果，决定下一阶段是否进入 LLM Candidate Mode 或 generator reform。

## Phase 14 成功条件

最低成功条件：

```text
1. GDPVal finance/audit subset local mirror 完成。
2. 至少 10 个 GDPVal subset tasks 完成 rw-task diagnostic baseline。
3. GDPVal anatomy extraction 完成。
4. GoodTaskProfiler V1 可同时处理 GDPVal 与 TaskGenerator tasks。
5. 至少 5 个 generated tasks 完成 LLM GoldenRun / Rubric / Realism shadow。
6. GoodTaskDashboard 能输出 generated-vs-GDPVal gap。
```

理想成功条件：

```text
1. 30 个 GDPVal subset tasks 完成 baseline。
2. 3-model diagnostic comparison 完成。
3. 能识别 GDPVal 高区分任务 cluster。
4. 能识别 generated tasks 的主要质量短板。
5. LLM shadow 证明至少一个位置有明确正收益。
6. Phase 15 的 LLM Candidate Mode 入口清晰。
```

## 输出

```text
docs/handoffs/PHASE_14_GDPTASK_CALIBRATION_SUCCESS_<date>.md
```

或：

```text
docs/handoffs/PHASE_14_GDPTASK_CALIBRATION_BLOCKED_<date>.md
```

## Postmortem 必须回答

```text
1. GDPVal 财务/审计 subset 中哪些题最能拉开模型差距？
2. 分差来自真实能力还是格式/工具噪声？
3. GDPVal 高价值题有什么共同结构？
4. TaskGenerator 题和这些高价值题差在哪里？
5. 当前 production QA 是否足以说明“好题”？
6. GoodTaskScore 哪些维度最不稳定？
7. LLM 在 GoldenRun、rubric、realism、reference narrative 中哪个位置最有价值？
8. LLM 是否可以进入 Candidate Mode？
9. 下一阶段是改 generator、改 LLM layer，还是改 evaluator？
```

---

## 6. Phase 14 工作优先级

## P0：立即做

```text
1. 固定 Phase 14 scope。
2. 建 GDPVal local mirror。
3. 选择 finance/audit-related GDPVal subset。
4. 让 GDPVal subset 进入 rw-task diagnostic baseline。
5. 建 Task Anatomy Schema。
```

## P1：紧随其后

```text
1. 实现 GoodTaskProfiler V1。
2. 对 TaskGenerator release tasks 生成同样 profile。
3. 做 generated-vs-GDPVal comparison。
4. 建 LLM GoldenRun Shadow。
5. 建 LLM Rubric Shadow。
6. 建 LLM Realism Critic。
```

## P2：条件成熟后做

```text
1. 扩到 30 个 GDPVal subset tasks。
2. 做 3-model diagnostic comparison。
3. 做 LLM Reference Narrative Suggestion。
4. 形成 GoodTaskDashboard。
5. 生成 LLM adoption recommendation。
```

## P3：继续暂缓

```text
1. LLM Primary GoldenRun。
2. LLM Primary Rubric。
3. LLM 直接生成 ground truth 数据。
4. 用 GDPVal 任务改写训练题。
5. UCB / bandit。
6. formal benchmark-grade model separation claim。
7. 跨领域扩展。
```

---

## 7. Phase 14 与后续 Phase 15 的关系

Phase 14 不是最终改进生成器的阶段，而是建立优化方向的阶段。

如果 Phase 14 成功，Phase 15 可以有三种可能路线。

### 路线 A：LLM Candidate Mode

如果 LLM shadow 证明可靠：

```text
LLM GoldenRun candidate
LLM Rubric candidate
LLM reference narrative candidate
deterministic verifier
production QA gate
```

### 路线 B：Generator Reform

如果 generated-vs-GDPVal comparison 显示任务结构与 GDPVal 高价值题差距明显：

```text
改 workflow archetype
改 motif grammar
改 evidence dossier planner
改 diversity / difficulty distribution
```

### 路线 C：Evaluator Reform

如果 GDPVal baseline 显示模型分差主要受 rubric / grader / toolchain 影响：

```text
改 rubric decomposition
改 model gap profiler
改 format-noise detector
改 rw-task grading adapter
```

Phase 14 的任务是决定下一阶段走哪条路线，而不是预设答案。

---

## 8. 最终总结

Phase 14 的核心思想是：

> 不再只问“这个任务能不能通过 production QA”，而是问“这个任务为什么值得训练模型”。

因此，Phase 14 要把 TaskGenerator 从：

```text
governed production task factory
```

升级为：

```text
externally calibrated, LLM-augmented good-task factory
```

它的关键产物不是更多任务，而是一个新的判断系统：

```text
GDPVal calibration
+ model gap profiling
+ good task anatomy
+ generated-vs-GDPVal comparison
+ LLM shadow evaluation
+ GoodTaskDashboard
```

只有建立了这个判断系统，后续无论是继续 deterministic 生成，还是引入 LLM 生成，才有明确的优化方向。
