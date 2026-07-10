# TaskGenerator Phase 14 计划书：GDPVal Calibration & LLM-Augmented Good Task Loop

> 2026-07-08 路线修正：Phase 14 当前阶段先做 empirical calibration，而不是直接建立带权重的 GoodTaskScore。4 个 clean GDPVal paired comparisons 已经有初步校准价值，但样本仍不足以支撑固定评分公式。后续优先产出 task profile、gap autopsy、runtime/friction taxonomy、stratified runnable slice，并把启发式降级为可验证假设。

> 阶段名称：Phase 14 — GDPVal Calibration & LLM-Augmented Good Task Loop
> 阶段定位：从“能生产 governed finance/audit tasks”进入“知道什么题值得生产、为什么值得训练、LLM 应该如何提高题目质量”的校准阶段。
> 适用范围：优先从 GDPVal 中财务、审计、金融、会计、合规、表格分析、报告交付相关任务入手；暂不扩展到其他领域和复杂新文件生态。
> 核心目标：建立一套外部 benchmark 对齐的“好题”证据体系，并在不破坏 deterministic production MVP 稳定性的前提下，引入 LLM shadow / candidate 层，用于提升真实感、GoldenRun、rubric 和任务诊断质量。当前阶段先做 profile、autopsy 和 hypothesis ledger；任何总分权重都必须等到 clean paired comparison 样本足够后再讨论。

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

> 以 GDPVal 财务 / 审计相关任务为外部参照，建立“好题”画像、失败剖析和质量证据体系，并用该体系指导 LLM 在 TaskGenerator 中的引入方式。

Phase 14 不是为了立刻让 LLM 接管整个任务生成流程，也不是为了马上做正式 benchmark-grade model separation。

Phase 14 要完成的是：

```text
1. 本地化 GDPVal 财务 / 审计相关任务。
2. 用 rw-task 对 GDPVal subset 做多模型诊断评测。
3. 分析 GDPVal 中哪些任务能拉开模型差距，以及为什么。
4. 建立 GoodTaskProfiler-Observational，把 GDPVal 任务和 TaskGenerator 任务投影到同一个证据空间。
5. 总结“好题”的多维定义。
6. 引入 LLM Shadow Layer，比较 deterministic 和 LLM 生成的 GoldenRun / rubric / realism critique。
7. 根据 GoodTaskProfiler-Observational、gap autopsy 和人工复核结果决定 LLM 后续应进入哪些主链路。
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
但这些输出是否更好，必须由 GoodTaskProfiler-Observational、gap autopsy、verifier、production QA、GDPVal calibration 和 executed eval 来判断。
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
- 完成 GDPVal subset 的 rw-task dry-run / executed-run path，并形成至少 4 个 clean paired comparisons 作为第一批剖析样本
- 完成至少 2 个模型的诊断执行
- 生成 GDPVal task anatomy report
- 生成 GDPVal model gap profile
- 生成 gap autopsy / hypothesis ledger，避免直接把小样本写成固定权重
```

理想目标：

```text
- 完成至少 12 个 clean paired comparisons，其中既包含 GDPVal，也包含 TaskGenerator generated tasks
- 覆盖 strong / medium / weak 三类模型
- 能识别高区分、高稳定、格式驱动、工具链敏感四类任务
- 形成 GDPVal high-value task cluster
```

---

### 4.2 GoodTaskProfiler-Observational 指标

最低目标：

```text
- 对 GDPVal subset 生成 observational good_task_profile.json
- 对 TaskGenerator release tasks 生成 observational good_task_profile.json
- 能比较 GDPVal subset 与 generated tasks 的证据分布、gap 分布和失败模式
- 不输出 weighted GoodTaskScore
```

理想目标：

```text
- 输出 GDPValSimilarity 观察字段
- 输出 ModelSeparationQuality 观察字段
- 输出 EvidenceClosure 观察字段
- 输出 WorkflowRealism 观察字段
- 输出 TrainingValue 观察字段
- 输出 EvaluationStability 观察字段
- 输出 FormatNoiseRisk 观察字段
- 输出 ToolFailureRisk 观察字段
- 输出 ProductiveComplexity 与 FrictionalComplexity 区分
- 输出 GapHypotheses 与 supporting / contradicting / insufficient evidence
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
14.4A Gap Autopsy & Hypothesis Ledger
14.4B Stratified Runnable Slice
14.5 GoodTaskProfiler-Observational V1
14.6 Generated-vs-GDPVal Comparison
14.6B Generated Task Comparison Eval Prep
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
  5 GDPVal subset tasks
  single-case progressive execution and repair
  at least 4 clean paired comparisons before downstream analysis

Stage B:
  stratified runnable slice
  at least 12 clean paired comparisons across GDPVal and TaskGenerator tasks
  every case has runtime, failure taxonomy, and gap autopsy

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
- GDPVal subset tasks 能进入 rw-task eval path，并能一题一题检查 deliverable / grading / timeout 问题
- 至少 2 个模型完成执行或明确记录失败原因
- 输出 clean score gap、failure mode 与 gap autopsy
- missing-deliverable zero score 不进入模型差异分析
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

# 14.4A Gap Autopsy & Hypothesis Ledger

## 目标

对 clean paired comparisons 做逐题 autopsy，解释模型差距来自哪里，而不是只扩展 gap 表格。

当前 4 个 usable GDPVal cases 足以支持方向判断，但不足以建立评分理论。因此 14.4A 的目标是把启发式改写成可验证假设。

## 输入

```text
artifacts/phase14/gdpval_clean_baseline/gdpval_clean_baseline_report.json
artifacts/phase14/gdpval_anatomy/gdpval_task_anatomy.jsonl
single-case sanitized regrade reports
grader score reports
deliverable diagnostics
```

## 输出

```text
src/task_generator/v3_gdpval_gap_autopsy.py
Test/run_v3_gdpval_gap_autopsy.py
artifacts/phase14/gdpval_gap_autopsy/
  gdpval_gap_autopsy_report.json
  gdpval_gap_hypothesis_ledger.json
  gdpval_gap_autopsy_cases/<case_slug>/gap_autopsy.json
```

## 当前入口

```bash
python Test/run_v3_gdpval_gap_autopsy.py
```

当前 5-case clean baseline 上的 smoke 结果：

```text
task_count = 5
usable_task_count = 4
gap_band_counts = {
  medium: 1,
  high: 3,
  unusable: 1
}
```

## Autopsy 字段

```json
{
  "task_id": "...",
  "observed_gap": 0.0,
  "strong_score": 0.0,
  "weak_score": 0.0,
  "gap_band": "high|medium|low|unusable",
  "top_gap_rubric_items": [],
  "strong_failure_modes": [],
  "weak_failure_modes": [],
  "gap_hypotheses": [],
  "productive_complexity_signals": [],
  "frictional_complexity_signals": [],
  "format_noise_suspected": false,
  "tool_noise_suspected": false,
  "grader_bias_suspected": false,
  "human_review_needed": false
}
```

## 初始假设

```text
H1: cross-file evidence localization tends to increase useful gap.
H2: open-ended deliverable construction increases realism and runtime, but may reduce runnability.
H3: format-heavy rubrics can inflate weak-model surface scores.
H4: policy/application tasks may separate models differently from pure spreadsheet calculation tasks.
H5: high-gap GDPVal tasks often contain implicit business constraints.
H6: long runtime is valuable only when it reflects productive complexity, not toolchain friction.
```

每新增一个 clean paired comparison，都应更新 hypothesis ledger，而不是直接改 GoodTaskScore 权重。

## 验收标准

```text
- 4 个 current usable GDPVal tasks 都有 gap autopsy
- 83d10 被明确保留为 low/medium-gap counterexample case study
- ee09 被记录为 runnability/frictional-complexity case，而不是模型能力证据
- 每个 hypothesis 都有 supporting / contradicting / insufficient evidence 记录
```

---

# 14.4B Stratified Runnable Slice

## 目标

继续扩大样本，但不盲目按 GDPVal 顺序跑更多题。下一步目标是构建分层 calibration set，使 clean paired comparisons 达到 12 个左右。

## 样本目标

```text
短期目标：
  12 clean paired comparisons

建议构成：
  8 GDPVal calibration tasks
  4 TaskGenerator generated tasks

每个任务都需要：
  strong model score
  weak model score
  runtime / timeout evidence
  grading status
  failure taxonomy
  gap autopsy
```

## GDPVal 分层选择

```text
high-gap candidates: 4-5
medium/low-gap candidates: 3-4
grading/runnability fragile cases: 2-3
```

不要把所有 GDPVal-like tasks 都默认视为好题。低 gap task 和 fragile task 同样有价值，因为它们能帮助区分 productive complexity 和 frictional complexity。

## TaskGenerator 对照选择

从 Phase 13 reviewed release tasks 中选至少 4 个进行同样双模型评测，形成 `generated_vs_gdpval_gap_probe.json`。

```text
GDPVal clean slice:
  mean gap
  median gap
  runtime
  grading success
  format/tool noise

TaskGenerator generated slice:
  mean gap
  median gap
  runtime
  grading success
  format/tool noise
```

该 probe 的目的不是宣布 benchmark-grade 结论，而是判断当前 production_ready 是否也具有 learning value。

## 验收标准

```text
- 有 runnable slice v2 manifest
- slice 选择理由按 strata 记录
- 至少提出下一批 4-6 个 GDPVal task 的运行顺序
- 至少提出 4 个 TaskGenerator release task 的对照评测计划
```

## 当前入口

```bash
python Test/run_v3_gdpval_runnable_slice.py
```

## 当前输出

```text
src/task_generator/v3_gdpval_runnable_slice.py
Test/run_v3_gdpval_runnable_slice.py
artifacts/phase14/gdpval_runnable_slice_v2_manifest.json
artifacts/phase14/gdpval_next_eval_queue.json
artifacts/phase14/taskgenerator_comparison_eval_plan.json
```

当前 smoke 结果：

```text
current_gdpval_clean_seed_count = 4
gdpval_holdout_count = 1
next_gdpval_eval_count = 4
taskgenerator_comparison_count = 4
target_total_clean_pairs = 12
```

下一批 GDPVal 队列当前为 `58ac`, `b39a`, `4de6`, `c657`。`ee09` 保留为 `runnability_friction_holdout`，不计入 clean gap 目标。

---

# 14.5 GoodTaskProfiler-Observational V1

## 目标

建立统一的“好题观察器”，使 GDPVal 任务和 TaskGenerator 任务能进入同一个证据坐标系。V1 只做 profile 和证据记录，不输出综合总分，不声明固定权重。

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

第一版先记录可比较的观察字段：

```text
GoodTaskProfiler-Observational V1 does not emit a weighted GoodTaskScore.

Record only:
  observed_gap
  strong_score / weak_score
  runnability_status
  grading_status
  runtime / timeout_margin
  reference_file_count / reference_file_total_size
  deliverable_type / deliverable_count
  reasoning_requirements
  productive_complexity_signals
  frictional_complexity_signals
  rubric_item_gap_summary
  format_noise_risk
  tool_noise_risk
  gap_hypotheses
  human_or_llm_autopsy_notes

Do not introduce a weighted score until:
  total clean paired comparisons >= 12
  both GDPVal and TaskGenerator generated tasks are represented
  every compared task has runtime, failure taxonomy, and gap autopsy

Do not treat any weights as stable until:
  GDPVal usable clean paired comparisons >= 12
  TaskGenerator evaluated clean paired comparisons >= 12
```

任何总分权重都应推迟到 GoodTaskProfiler-Scored 阶段再讨论。

## 输出

```text
src/task_generator/v3_good_task_profiler_observational.py
Test/run_v3_good_task_profiler_observational.py
artifacts/phase14/good_task_profiler_observational/
  good_task_profiler_observational_report.json
  good_task_observational_profiles.jsonl
  good_task_observational_distribution_report.json
```

## 当前入口

```bash
python Test/run_v3_good_task_profiler_observational.py
```

当前 smoke 结果：

```text
profile_count = 13
gdpval_profile_count = 9
taskgenerator_profile_count = 4
evaluated_profile_count = 4
pending_eval_profile_count = 9
weighted_good_task_score_emitted = false
```

## 验收标准

```text
- GDPVal subset 可生成 observational profile
- TaskGenerator production tasks 可生成 observational profile
- 同一 dashboard 能比较两类任务的证据结构、gap 分布和失败模式
- score gap 不再只是 strong_score - weak_score，而必须带有 deliverable、grader、runtime 和噪声解释
- V1 不生成 weighted GoodTaskScore
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
src/task_generator/v3_generated_vs_gdpval_comparison.py
Test/run_v3_generated_vs_gdpval_comparison.py
artifacts/phase14/generated_vs_gdpval/
  generated_vs_gdpval_similarity_report.json
  generated_vs_gdpval_gap_report.json
  generated_vs_gdpval_quality_matrix.json
  generated_task_improvement_recommendations.json
```

## 当前入口

```bash
python Test/run_v3_generated_vs_gdpval_comparison.py
```

当前 smoke 结果：

```text
gdpval_profile_count = 9
generated_profile_count = 4
gdpval_clean_eval_count = 4
generated_clean_eval_count = 0
comparison_readiness = structure_only_pending_generated_eval
blocked_reason = generated_tasks_have_no_clean_paired_eval_yet
```

# 14.6B Generated Task Comparison Eval Prep

## 目标

把 14.4B 选出的 4 个 TaskGenerator reviewed release tasks 接到 rw-task 诊断评测准备路径中，让 generated side 不再停留在结构对比。

这一层只负责：

```text
- 验证 release task 是否仍是 rw-task-compatible
- 为每个 task x model 生成 eval input
- 生成 command preview
- 可选执行 rw-task，但必须显式 --mode execute --run-eval
```

默认不调用模型、不读取 `.env`、不产生 clean score。

## 当前入口

```bash
python Test/run_v3_generated_task_comparison_eval.py --mode dry-run --overwrite
```

## 输出

```text
src/task_generator/v3_generated_task_comparison_eval.py
Test/run_v3_generated_task_comparison_eval.py
artifacts/phase14/generated_task_comparison_eval/
  generated_task_comparison_eval_report.json
  generated_task_comparison_failure_report.json
  generated_task_comparison_command_preview.json
  eval_inputs/
  model_runs/
  validation_reports/
```

当前 dry-run smoke 结果：

```text
selected_task_count = 4
model_count = 2
task_model_attempt_count = 8
prepared_count = 8
dry_run_ready_count = 8
blocked_count = 0
failed_count = 0
timeout_count = 0
```

当前 Codex 执行环境不能直接把私有 workspace task package 上传给外部 rw-task / E2B / model API。真实执行应在允许外部调用的本机终端中运行；执行后用汇总器读取结果：

```bash
python Test/run_v3_generated_task_eval_summary.py
```

当前 dry-run-only 汇总结果：

```text
task_count = 4
model_score_count = 8
completed_model_score_count = 0
clean_pair_count = 0
blocked_pair_count = 4
```

汇总输出：

```text
src/task_generator/v3_generated_task_eval_summary.py
Test/run_v3_generated_task_eval_summary.py
artifacts/phase14/generated_task_comparison_eval_summary/
  generated_task_eval_summary_report.json
  generated_task_gap_profile.json
```

## 解释

14.6B 说明：TaskGenerator 生成题已经可以进入与 GDPVal clean slice 相同的 rw-task 诊断通道，但还没有真实模型分数。

因此：

```text
- generated-vs-GDPVal comparison 仍然是 structure-only
- GoodTaskProfiler 仍然不输出 weighted GoodTaskScore
- 下一步应一题一题执行 generated task paired eval，并把分数回填到 observational profile
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

## 当前实现状态：14.7A Prepare Layer

当前已实现 LLM Shadow 的 prepare/shell 层：

```text
src/task_generator/v3_llm_shadow_common.py
src/task_generator/v3_llm_shadow_goldenrun.py
src/task_generator/v3_llm_shadow_rubric.py
src/task_generator/v3_llm_realism_critic.py
src/task_generator/v3_llm_reference_narrative_suggestion.py

Test/run_v3_llm_shadow_goldenrun.py
Test/run_v3_llm_shadow_rubric.py
Test/run_v3_llm_realism_critic.py
Test/run_v3_llm_reference_narrative_suggestion.py
```

当前 smoke：

```text
GoldenRun shadow: 5 / 5 production-ready tasks prepared
Rubric shadow: 5 / 5 production-ready tasks prepared
Realism critic: 5 / 5 production-ready tasks prepared
Reference narrative suggestion: 5 / 5 production-ready tasks prepared
```

输出目录：

```text
artifacts/phase14/llm_shadow/
  llm_goldenrun_shadow_batch_report.json
  llm_rubric_shadow_batch_report.json
  llm_realism_critic_batch_report.json
  llm_reference_narrative_suggestion_batch_report.json
```

重要边界：

```text
- 当前实现不调用外部模型
- 当前实现不伪造 LLM 输出
- 当前 shadow report 均为 awaiting_llm_output
- unsupported claim rate / evidence citation validity / realism alignment 等指标要等真实 LLM 输出后才能计算
- shadow 产物只在 artifacts/phase14/llm_shadow/ 下，不进入 release，不覆盖 deterministic GoldenRun / rubric / reference files
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
4. LLM Realism Critic 是否能预测 observational profile 中的低质量证据、frictional complexity 和人工 autopsy 标记？
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

## 当前实现状态

当前已实现 impact evaluation shell：

```text
src/task_generator/v3_llm_impact_evaluation.py
Test/run_v3_llm_impact_evaluation.py
```

当前入口：

```bash
python Test/run_v3_llm_impact_evaluation.py
```

当前 smoke 结果：

```text
shadow_kind_count = 4
total_prepared_task_shadows = 20
total_awaiting_llm_output = 20
total_completed_metric_count = 0
impact_readiness = awaiting_llm_shadow_outputs
adoption recommendation = do_not_enter_llm_candidate_mode_yet
```

解释：

```text
14.8 目前只能证明 shadow package 已准备好，不能证明 LLM 有正收益。
LLM Candidate Mode 仍然被阻止，直到真实 LLM shadow output 产生可计算指标。
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
  GoodTaskProfiler observational distribution
  GDPValSimilarity evidence distribution
  WorkflowRealism evidence distribution
  TrainingValue evidence distribution
  ModelSeparationQuality evidence distribution
  ProductiveComplexity / FrictionalComplexity split

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

## 当前实现状态

当前已实现 GoodTask Dashboard V1：

```text
src/task_generator/v3_good_task_dashboard.py
Test/run_v3_good_task_dashboard.py
artifacts/phase14/good_task_dashboard/
  good_task_dashboard_report.json
  good_task_dashboard_summary.json
```

当前入口：

```bash
python Test/run_v3_good_task_dashboard.py
```

当前 smoke 结果：

```text
overall_status = blocked_pending_external_eval
phase14_readiness = partial_diagnostic_dashboard_ready
weighted_good_task_score_emitted = false
can_claim_generated_vs_gdpval_model_separation = false
can_enter_llm_candidate_mode = false
gdpval_clean_eval_count = 4
generated_clean_eval_count = 4
```

当前 blocker：

```text
none
remaining_review_item = llm_candidate_mode_requires_phase15_risk_gate
```

解释：

```text
Dashboard 已能统一展示 GDPVal calibration、TaskGenerator generated tasks、LLM shadow、generated-vs-GDPVal comparison。
但它不会输出 weighted GoodTaskScore，也不会声称 generated tasks 已经具备模型区分证据。
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
2. Phase 14.3 clean baseline 完成，至少 4 个 GDPVal clean paired comparisons 可用于 gap analysis。
3. GDPVal anatomy extraction 完成。
4. Gap autopsy 与 hypothesis ledger 完成，并保留低/中 gap counterexample 与失败样本。
5. GoodTaskProfiler-Observational V1 可同时处理 GDPVal 与 TaskGenerator tasks，且不输出 weighted GoodTaskScore。
6. Stratified runnable slice 计划明确，能说明下一批为何选这些题。
```

理想成功条件：

```text
1. 至少 12 个 clean paired comparisons 完成，其中同时包含 GDPVal 与 TaskGenerator generated tasks。
2. 3-model diagnostic comparison 在高价值小切片上完成。
3. 能识别 GDPVal 高区分任务 cluster，也能解释低/中 gap counterexample。
4. 能识别 generated tasks 的主要质量短板。
5. LLM shadow 证明至少一个位置有明确正收益。
6. Phase 15 的 LLM Candidate Mode 或 generator reform 入口清晰。
```

## 输出

```text
docs/handoffs/PHASE_14_GDPTASK_CALIBRATION_SUCCESS_<date>.md
```

或：

```text
docs/handoffs/PHASE_14_GDPTASK_CALIBRATION_BLOCKED_<date>.md
```

## 当前实现状态

当前已实现 Phase 14 postmortem / Phase 15 decision 层：

```text
src/task_generator/v3_phase14_postmortem.py
Test/run_v3_phase14_postmortem.py
artifacts/phase14/postmortem/phase14_postmortem_report.json
docs/handoffs/PHASE_14_GDPTASK_CALIBRATION_SUCCESS_2026-07-08.md
```

当前入口：

```bash
python Test/run_v3_phase14_postmortem.py
```

当前决策：

```text
phase14_decision = success
phase15_recommendation = phase15_candidate_mode_or_generator_reform_review
```

当前已满足的最低条件：

```text
- GDPVal finance/audit subset local mirror / boundary exists
- 8 GDPVal clean paired comparisons usable for gap analysis
- 4 TaskGenerator generated clean paired comparisons usable for diagnostic comparison
- anatomy / gap autopsy / hypothesis ledger / GoodTaskProfiler / dashboard are present
- weighted GoodTaskScore is not emitted
```

当前未满足的理想条件：

```text
- LLM positive-impact adoption decision is still review-required
- weighted GoodTaskScore is still disabled
- benchmark-grade model separation is still out of scope
- direct LLM Candidate Mode promotion still requires a Phase 15 risk gate
```

解释：

```text
14.10 生成的是 blocked / partial handoff，不是 success handoff。
这不是因为 deterministic reports 缺失，而是因为外部执行证据缺失。
```

## Postmortem 必须回答

```text
1. GDPVal 财务/审计 subset 中哪些题最能拉开模型差距？
2. 分差来自真实能力还是格式/工具噪声？
3. GDPVal 高价值题有什么共同结构？
4. TaskGenerator 题和这些高价值题差在哪里？
5. 当前 production QA 是否足以说明“好题”？
6. GoodTaskProfiler-Observational 中哪些证据维度最不稳定，最需要人工或 LLM autopsy？
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
4. 收口 Phase 14.3 clean baseline，不再使用 raw batch 中的 missing-deliverable zero score。
5. 建 Task Anatomy Schema。
6. 对当前 4 个 usable GDPVal cases 做 gap autopsy。
7. 建 hypothesis ledger，把每个启发式写成可被支持或推翻的假设。
```

## P1：紧随其后

```text
1. 形成 stratified runnable slice，目标是至少 12 个 clean paired comparisons。
2. 对 TaskGenerator release tasks 生成同样 observational profile。
3. 做 generated-vs-GDPVal comparison。
4. 实现 GoodTaskProfiler-Observational V1。
5. 建 LLM GoldenRun Shadow。
6. 建 LLM Rubric Shadow。
7. 建 LLM Realism Critic。
```

## P2：条件成熟后做

```text
1. 在 12 个 clean paired comparisons 之后，讨论是否扩到 30 个 GDPVal subset tasks。
2. 做 3-model diagnostic comparison。
3. 做 LLM Reference Narrative Suggestion。
4. 形成 GoodTaskDashboard。
5. 生成 LLM adoption recommendation。
6. 只有在 GDPVal 和 TaskGenerator 两侧都有足够 clean paired comparisons 后，才讨论 GoodTaskProfiler-Scored 或 weighted GoodTaskScore。
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

## 2026-07-08 Generated-Task Eval Update

The generated-task external-eval gap is now partially closed. The four selected Phase 13 TaskGenerator release tasks have clean paired diagnostic scores with `gemini-3-pro-preview` versus `gpt-4o-mini`, graded by `gpt-5.4-pro`.

Current generated clean gaps:

```text
pipeline_b_batch_01_evidence_to_deliverable: 0.0189
pipeline_b_batch_02_cross_check_validation: 0.3846
pipeline_b_batch_03_fan_in_reconciliation: 0.6909
pipeline_b_batch_04_policy_application: 0.4127
```

Historical comparison status at the first generated-task update:

```text
gdpval_clean_eval_count = 4
generated_clean_eval_count = 4
gdpval_gap_bands = 3 high / 1 medium
generated_gap_bands = 1 high / 2 medium / 1 low
comparison_readiness = clean_pair_comparison_available
```

This historical update was superseded by the later 12-clean-pair and LLM shadow completion updates below. Do not use it as the current Phase 14 decision.

## 2026-07-08 Clean-Pair Target Update

The 12-clean-pair target is now met:

```text
GDPVal clean paired comparisons = 8
TaskGenerator generated clean paired comparisons = 4
total clean paired comparisons = 12
GDPVal gap bands = 6 high / 2 medium / 2 unusable
TaskGenerator generated gap bands = 1 high / 2 medium / 1 low
```

The full LLM shadow batch has now completed:

```text
total_prepared_task_shadows = 20
total_completed_metric_count = 20
total_awaiting_llm_output = 0
impact_readiness = ready_for_impact_analysis
adoption_recommendation = review_shadow_metrics_before_candidate_mode
```

The current Phase 14 postmortem decision is:

```text
phase14_decision = success
phase15_recommendation = phase15_candidate_mode_or_generator_reform_review
handoff = docs/handoffs/PHASE_14_GDPTASK_CALIBRATION_SUCCESS_2026-07-08.md
```

Important boundary: `ideal_2_llm_positive_impact` is still `partial`, not `met`. The LLM shadow metrics are complete enough for review, but Phase 15 must still decide whether any insertion point is reliably positive enough for guarded Candidate Mode. Weighted GoodTaskScore remains disabled.

只有建立了这个判断系统，后续无论是继续 deterministic 生成，还是引入 LLM 生成，才有明确的优化方向。
