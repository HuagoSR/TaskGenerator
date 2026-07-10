# TaskGenerator Phase 13 计划书：Finance/Audit Scalable Production MVP

> 阶段名称：Phase 13 — Finance/Audit Scalable Production MVP
> 阶段定位：从 Phase 12 的 candidate-ready hardening 进入第一个可规模化生产版本。
> 适用范围：仅限当前财务 / 审计 / 合规类任务；暂不扩展新领域；暂不扩展 email、PDF、OCR、图片等复杂文件生态；继续使用当前 `.xlsx` / `.docx` / `.md` / `.txt` 等既有文件能力。
> 核心目标：把 Phase 12 已证明的 candidate-ready 路径，升级为一个可重复、可治理、可批量运行、可导出、可抽检、可回归测试的 production MVP。

---

## 1. 阶段背景

Phase 12 已经证明：

```text
1. candidate-ready 路径可以从 3-case 扩展到 5-case 与 10-case deterministic smoke。
2. verifier / export / quality contracts 能通过正例，也能通过 7 类 negative control 证明 gate hardness。
3. guarded executed eval mini-campaign 已经完成 3 cases × 2 models 的真实执行诊断。
4. TransitionPriorStore V0 observed-only 已开始记录 outcome。
5. workflow_context_fit 在 5-case strengthened rerun 中从 2 high / 3 low 提升到 5 high。
```

这说明项目已经不再处于“能不能出合格任务”的阶段。

但 Phase 12 仍然不是最终生产版本，因为还有几个关键边界：

```text
1. scratch-validated substrate promotions 还没有完全 canonicalized。
2. workflow / realism patches 仍主要是 phase-local artifacts。
3. 10-case success 仍是 deterministic slice，不等于长期多批次稳定生产。
4. executed eval 仍是 diagnostic evidence，不是 formal model separation proof。
5. 还没有 production batch manifest、dataset release manifest、版本化产物规范和抽检制度。
```

因此 Phase 13 的核心不再是新增大架构，而是做 production MVP 收口。

---

## 2. Phase 13 总目标

Phase 13 的总目标是：

> 在财务 / 审计类任务范围内，将已有 candidate-ready 生成路径转化为第一个可规模化生产的任务工厂 MVP。

这里的“可规模化生产”不等于全自动无监督，也不等于正式 benchmark-grade 数据集。

Phase 13 的 production MVP 定义为：

```text
系统能够在固定领域、固定文件类型、固定治理规则下，
连续批量生成 candidate-ready 任务包，
并为每个任务包提供完整的 provenance、verifier、quality、export、dashboard、promotion、eval-diagnostic 记录，
从而形成可审计、可复跑、可抽检、可导出的任务批次。
```

---

## 3. Phase 13 的北极星指标

Phase 13 不以“再新增多少模块”为目标，而以“生产批次是否稳定”为目标。

### 3.1 最低验收目标

```text
生成一个 production pilot batch：
- candidate_ready >= 30 个
- verifier_pass_rate >= 95%
- export_compatible_rate >= 95%
- reject_rate <= 5%
- 每个任务均有完整 package manifest
- 每个任务均有 quality report / verifier report / validity report
- 每个任务均可追溯到 skill / resource / workflow / motif / source evidence
```

### 3.2 理想验收目标

```text
生成两个 production pilot batches：
- 每批 30-50 个 candidate_ready 任务
- 第二批不低于第一批质量
- dashboard 能比较两个批次的质量变化
- repeated blockers 不随规模扩大而显著增加
- selected executed eval diagnostic campaign 能覆盖每批至少 3-5 个任务
```

### 3.3 暂不追求目标

Phase 13 暂不追求：

```text
1. 跨领域扩展。
2. 新文件生态，例如 PDF、OCR、扫描件、邮件线程。
3. 正式 benchmark-grade model separation conclusion。
4. UCB / bandit 影响采样行为。
5. 全自动 registry mutation。
6. production LLM Teacher 替代 deterministic TeacherRunner。
```

---

## 4. Phase 13 核心原则

### 原则 1：先 productionize，不急着 intelligent-optimize

Phase 13 不是让 sampler 更聪明，而是让生产路径更可靠。

优先顺序：

```text
production manifest
→ canonical assets
→ batch reproducibility
→ QA / verifier / export consistency
→ dataset release
→ diagnostic eval
→ observed transition evidence
```

而不是：

```text
UCB / bandit
→ sampler 自动学习
→ 自动改 registry
```

---

### 原则 2：Phase 12 局部成功必须 canonicalize

Phase 12 中很多成果仍在 scratch 或 phase-local artifact 中。

Phase 13 必须回答：

```text
哪些 typed-resource patches 可以进入 canonical registry？
哪些 workflow-context patches 可以进入 canonical workflow assets？
哪些 motif grammar strengthening 可以成为默认行为？
哪些只是局部 workaround，不能晋升？
```

---

### 原则 3：生产批次必须可复现

每个 production batch 必须有：

```text
batch_id
code commit
registry version
workflow asset version
motif grammar version
sampler policy version
promotion state
random seed / deterministic selection config
input case selection config
artifact paths
```

否则未来无法判断质量变化来自哪里。

---

### 原则 4：candidate_ready 仍要防 Goodhart

Phase 13 的目标是批量生成 candidate_ready，但不能让系统学会“通过检查”而不是真实任务质量。

因此每个 production batch 都必须包含：

```text
negative control regression
real-worldness audit
verifier pass
export validation
sampled human spot-check
executed eval diagnostic sample
```

---

### 原则 5：executed eval 仍是 diagnostic，不是正式 benchmark 宣告

Phase 13 可以扩大 executed eval，但仍应保守解释。

可说：

```text
diagnostic comparison evidence
```

不可说：

```text
formal benchmark-grade model separation evidence
```

除非后续进入专门的 benchmark validation phase。

---

## 5. Phase 13 总体结构

Phase 13 分为 9 个子阶段：

```text
13.0 Production Readiness Definition
13.1 Canonical Asset Consolidation
13.2 Production Batch Runner
13.3 Batch Diversity & Deduplication
13.4 Production QA Gate
13.5 Production Pilot Batch
13.6 Dataset Release Packaging
13.7 Diagnostic Evaluation Sampling
13.8 Production Dashboard & Batch Comparison
13.9 Phase 13 Postmortem & Release Decision
```

---

# 13.0 Production Readiness Definition

## 目标

明确什么叫“第一个可规模化生产版本”，避免后续目标漂移。

## 工作内容

新增文档：

```text
docs/architecture/production_mvp_definition.md
```

文档中定义：

```text
1. production_candidate_task
2. production_pilot_batch
3. candidate_ready_for_training_pool
4. diagnostic_eval_sample
5. rejected_production_candidate
6. deprecated_task
```

建议状态机：

```text
generated
→ structurally_valid
→ verifier_passed
→ candidate_ready
→ production_candidate
→ training_pool_candidate
→ diagnostic_eval_sampled
→ released
→ deprecated
```

## 每个状态的进入条件

### `candidate_ready`

```text
quality_gate = candidate_ready
verifier_status = pass
export_validation = candidate_ready_compatible
global_validity has no blocking finding
```

### `production_candidate`

```text
candidate_ready
+ batch manifest complete
+ provenance complete
+ no unresolved critical dashboard finding
+ no hidden artifact exposure
+ no negative-control regression failure
```

### `training_pool_candidate`

```text
production_candidate
+ rubric candidate-facing hygiene passed
+ evidence closure passed
+ no formal eval dependency
+ no manual blocker
```

### `diagnostic_eval_sampled`

```text
production_candidate
+ selected by eval sampling policy
+ executed eval completed or explicitly skipped
+ eval result stored as diagnostic evidence
```

## 输出

```text
docs/architecture/production_mvp_definition.md
SkillRegistry/production_state_contract.experimental.json
```

## 验收标准

```text
- production MVP 的定义明确
- candidate_ready 与 production_candidate 区分清楚
- diagnostic eval 与 formal model separation 区分清楚
```

---

# 13.1 Canonical Asset Consolidation

## 目标

把 Phase 12 的 scratch / phase-local 成功资产，审查后晋升为 canonical assets。

## 需要处理的资产类型

```text
1. typed-resource promotions
2. workflow-context patches
3. motif grammar strengthening
4. verifier calibration fixes
5. quality gate scope fixes
6. evidence dossier defaults
```

## 工作内容

### 13.1.1 Typed Resource Canonical Review

对 Phase 12 scratch-validated Tier A patches 做 canonical review：

```text
scratch validated
→ source_promotion_key confirmed
→ canonical review
→ canonical apply
→ rollback record
→ regression comparison
```

每轮最多 apply 3-5 个 patch。

### 13.1.2 Workflow Asset Canonicalization

将 Phase 12 workflow-context strengthening 中有效的 patch 分类：

```text
A. 应进入 workflow archetype registry
B. 应进入 motif grammar
C. 应进入 evidence dossier planner defaults
D. 只是局部 case hint，不晋升
```

### 13.1.3 Motif Grammar Consolidation

重点收口当前财务 / 审计类 motif：

```text
evidence_to_deliverable
cross_check_validation
fan_in_reconciliation
policy_application
exception_escalation
```

每个 motif 至少应有：

```text
required_roles
optional_roles
required_resource_types
expected_artifact_ecology
validation_constraints
common_failure_modes
candidate_deliverable_conventions
```

## 输出

```text
SkillRegistry/canonical_asset_consolidation_report.json
SkillRegistry/typed_resource_canonical_review_report.json
SkillRegistry/workflow_asset_promotion_report.json
SkillRegistry/motif_grammar_consolidation_report.json
```

## 验收标准

```text
- 至少 1 轮 canonical typed-resource promotion 完成
- 每次 apply 都有 rollback record
- workflow-context strengthening 不再只停留在 phase-local artifacts
- canonicalization 后 5-case / 10-case regression 不回退
```

---

# 13.2 Production Batch Runner

## 目标

把现有 batch runner 升级为 production pilot batch runner。

当前 batch runner 证明了 deterministic production path。
Phase 13 需要的是一个更像生产系统的入口。

## 新增能力

### 13.2.1 Batch Manifest

每次生产批次必须生成：

```json
{
  "production_batch_id": "fin_audit_prod_pilot_0001",
  "created_at": "...",
  "code_commit": "...",
  "registry_version": "...",
  "workflow_asset_version": "...",
  "motif_grammar_version": "...",
  "sampler_policy_version": "...",
  "selection_policy": "...",
  "max_cases": 50,
  "domain_scope": "finance_audit",
  "file_type_scope": ["xlsx", "docx", "md", "txt"],
  "promotion_state": "...",
  "outputs": []
}
```

### 13.2.2 Production Run Modes

建议支持三种模式：

```text
--dry-run
  只规划，不生成任务包。

--candidate-run
  生成 candidate_ready 任务包，但不进入 release。

--production-run
  生成 production_candidate，并写 production manifest。
```

### 13.2.3 Resume / Retry

生产批次需要支持：

```text
resume
retry failed case
skip known blocker
mark deprecated
```

### 13.2.4 Artifact Isolation

每个 production batch 应写到：

```text
artifacts/production_batches/<batch_id>/
```

而不是继续混在 scratch 目录中。

## 输出

```text
src/task_generator/v3_production_batch_runner.py
Test/run_v3_production_batch_runner.py
artifacts/production_batches/<batch_id>/production_batch_manifest.json
```

## 验收标准

```text
- 可以生成 30+ case production pilot batch
- 每个 case 有独立 artifact directory
- batch manifest 可追溯 registry / workflow / motif / sampler 版本
- 支持 resume / retry
- 不依赖人工手动整理 scratch 路径
```

---

# 13.3 Batch Diversity & Deduplication

## 目标

防止“规模化生产”只是重复生成同质任务。

Phase 12 文档中已经提示：5-case slice 中存在 repeated motif 和 repeated subgraph ID。Phase 13 必须处理这个问题。

## 工作内容

### 13.3.1 Diversity Report

每个 batch 统计：

```text
motif distribution
workflow archetype distribution
subgraph ID distribution
skill usage distribution
source support distribution
deliverable type distribution
difficulty profile distribution
evidence dossier pattern distribution
```

### 13.3.2 Dedup Rules

需要阻止：

```text
same subgraph ID repeated too often
same skill combination repeated too often
same reference file pattern repeated too often
same deliverable wording repeated too often
same motif dominating batch
```

### 13.3.3 Diversity Targets

初始目标可以保守：

```text
single motif share <= 40%
single subgraph ID count <= 2
single primary skill count <= 20% of batch
at least 3 motif types per 30-case batch
at least 2 deliverable styles per 30-case batch
```

## 输出

```text
production_batch_diversity_report.json
production_batch_dedup_report.json
```

## 验收标准

```text
- production batch 不再只是同一 motif / subgraph 的重复
- dashboard 能显示 diversity warning
- diversity rule 不明显降低 candidate_ready rate
```

---

# 13.4 Production QA Gate

## 目标

在现有 quality gate / verifier / export validator / global validity 之外，增加 production-level acceptance gate。

## Production QA Gate 输入

```text
pipeline_b_quality_report.json
task_verifier_report.json
rw_task_export_validation_report.json
global_task_validity_report.json
real_worldness_report.json
difficulty_profile_report.json
production_batch_diversity_report.json
negative_control_report.json
promotion_state_report.json
```

## Production QA Gate 判定

```text
production_ready
production_revise
production_reject
manual_review_required
```

## production_ready 条件

```text
candidate_ready
+ verifier pass
+ export compatible
+ no global validity blocking
+ real_worldness >= threshold
+ production manifest complete
+ no diversity hard violation
+ no unresolved critical promotion warning
```

## manual_review_required 条件

例如：

```text
real_worldness borderline
workflow_context_fit low
high-value but unusual task graph
new motif combination
first use of newly promoted asset
diagnostic eval score anomaly
```

## 输出

```text
src/task_generator/v3_production_qa_gate.py
Test/run_v3_production_qa_gate.py
production_qa_report.json
```

## 验收标准

```text
- candidate_ready 不会自动等于 production_ready
- production gate 能区分 production_revise 与 manual_review_required
- production gate 不降低已有 candidate-ready checks
```

---

# 13.5 Production Pilot Batch

## 目标

正式生成第一个 finance/audit production pilot batch。

## 建议批次设计

### Pilot Batch A

```text
batch_size = 30
domain = finance_audit
file_types = existing only
mode = production-run
eval = diagnostic sample only
```

### Pilot Batch B

如果 Pilot A 稳定：

```text
batch_size = 50
domain = finance_audit
file_types = existing only
mode = production-run
eval = diagnostic sample only
```

## 每个任务必须包含

```text
task_blueprint.json
reference_file_plan.json
generated_file_manifest.json
evidence_index.json
teacher_input_manifest.json
golden_run.json
training_annotation.json
rubric.json
pipeline_b_quality_report.json
task_verifier_report.json
global_validity reports
package_manifest.json
dataset_row.json
production_qa_report.json
```

## 批次级报告

```text
production_batch_manifest.json
production_batch_summary_report.json
production_batch_diversity_report.json
production_batch_quality_distribution_report.json
production_batch_failure_report.json
```

## 验收标准

最低：

```text
30-case pilot:
- production_ready >= 20
- production_revise <= 8
- production_reject <= 2
- verifier_pass_rate >= 95%
- export_compatible_rate >= 95%
```

理想：

```text
30-case pilot:
- production_ready >= 25
- production_revise <= 5
- production_reject = 0
```

---

# 13.6 Dataset Release Packaging

## 目标

把 production_ready tasks 打包成一个可交付的数据集版本。

## Release 目录结构

```text
artifacts/releases/finance_audit_mvp_v0_1/
  release_manifest.json
  dataset_rows/
  tasks/
    task_0001/
      dataset_row.json
      reference_files/
      deliverable_files/
      artifacts/
  reports/
    release_quality_report.json
    release_diversity_report.json
    release_verifier_report.json
    release_eval_diagnostic_report.json
  docs/
    README.md
    DATA_CARD.md
    KNOWN_LIMITATIONS.md
```

## Release Manifest 字段

```json
{
  "release_id": "finance_audit_mvp_v0_1",
  "domain_scope": "finance_audit",
  "file_type_scope": ["xlsx", "docx", "md", "txt"],
  "task_count": 0,
  "production_ready_count": 0,
  "diagnostic_eval_sample_count": 0,
  "excluded_task_count": 0,
  "code_commit": "...",
  "registry_version": "...",
  "created_at": "...",
  "not_benchmark_grade": true,
  "intended_use": ["training_pool_candidate", "diagnostic_internal_eval"],
  "not_intended_use": ["formal_public_benchmark_claim"]
}
```

## DATA_CARD.md 应说明

```text
1. 数据集生成方式
2. 领域范围
3. 文件类型范围
4. 任务结构
5. 质量门
6. verifier 覆盖
7. executed eval 覆盖
8. 已知限制
9. 不应如何解释
```

## 验收标准

```text
- release 包可以独立检查
- release 中不包含密钥或本地敏感路径
- 每个任务能追溯到 artifacts
- 明确标记 not benchmark-grade unless validated later
```

---

# 13.7 Diagnostic Evaluation Sampling

## 目标

对 production batch 中的一小部分任务进行真实执行诊断，不把全部任务都跑昂贵评估。

## Sampling Policy

优先抽样：

```text
1. 每个主要 motif 至少 1 个
2. 每个 workflow archetype 至少 1 个
3. real_worldness 高 / 中 / 边界各若干
4. difficulty profile 分布覆盖
5. 首次使用 newly promoted asset 的任务
```

## 建议规模

Pilot A：

```text
production_ready tasks: 20-30
diagnostic eval sample: 5
models: 2
runs_per_model: 1
```

Pilot B：

```text
production_ready tasks: 30-50
diagnostic eval sample: 8-10
models: 3
runs_per_model: 1-2
```

## 输出

```text
diagnostic_eval_sampling_report.json
diagnostic_eval_campaign_report.json
model_separation_profile.diagnostic.json
eval_feedback_summary_report.json
```

## 解释边界

允许说：

```text
本 release 包含内部诊断性多模型执行证据。
```

不允许说：

```text
本 release 已构成正式模型排名 benchmark。
```

## 验收标准

```text
- diagnostic eval sample 覆盖主要 motif
- eval run/summary completion rate >= 90%
- 能识别 format noise vs reasoning failure
- 不把 eval score 自动回写 sampler / registry
```

---

# 13.8 Production Dashboard & Batch Comparison

## 目标

将 production batch、release、diagnostic eval、diversity、QA、promotion 全部汇总到 production dashboard。

## Dashboard 维度

```text
1. production readiness
2. candidate_ready rate
3. production_ready rate
4. verifier pass rate
5. export compatibility
6. diversity coverage
7. motif distribution
8. workflow_context_fit distribution
9. real_worldness distribution
10. difficulty profile distribution
11. promotion asset usage
12. diagnostic eval completion
13. diagnostic model score gaps
14. known limitations
```

## Batch Comparison

如果有 Pilot A 和 Pilot B，则必须比较：

```text
candidate_ready_rate delta
production_ready_rate delta
reject_rate delta
diversity delta
verifier finding delta
eval completion delta
source / skill / motif coverage delta
```

## 输出

```text
production_dashboard_report.json
production_batch_comparison_report.json
release_readiness_report.json
```

## 验收标准

```text
- dashboard 能判断 release 是否可交付
- dashboard 能显示 scale-up 是否带来质量下降
- dashboard 能明确下一批应该修什么
```

---

# 13.9 Phase 13 Postmortem & Release Decision

## 目标

决定是否发布第一个 finance/audit scalable production MVP release。

## 成功条件

Phase 13 可判定成功，如果满足：

```text
1. 至少一个 30-case production pilot batch 完成。
2. production_ready >= 20。
3. verifier_pass_rate >= 95%。
4. export_compatible_rate >= 95%。
5. diversity report 无 hard violation。
6. release package 完成。
7. diagnostic eval sample 完成。
8. release 文档明确标记 intended use 和 limitations。
9. no secret leakage。
```

## 更强成功条件

```text
1. 50-case pilot batch 完成。
2. production_ready >= 40。
3. diagnostic eval sample >= 8。
4. batch comparison 显示质量稳定。
5. canonical asset consolidation 完成至少一轮。
```

## 输出

```text
docs/handoffs/PHASE_13_FINANCE_AUDIT_MVP_SUCCESS_<date>.md
```

或：

```text
docs/handoffs/PHASE_13_FINANCE_AUDIT_MVP_BLOCKED_<date>.md
```

## Postmortem 必须回答

```text
1. 是否达到第一个可规模化生产版本？
2. production_ready 任务数量是多少？
3. 哪些 motif 最稳定？
4. 哪些 motif 仍需要修？
5. 是否出现规模扩大后的质量下降？
6. diagnostic eval 是否发现系统性问题？
7. release 是否适合进入 training pool？
8. 下一阶段是否可以开始 prior learning / sampler intelligence？
```

---

## 6. Phase 13 工作优先级

## P0：立即做

```text
1. 定义 production MVP contract。
2. 收口 Phase 12 scratch-validated assets。
3. 做 canonical typed-resource promotion review。
4. 建 production batch manifest。
5. 改造 batch runner 为 production pilot runner。
```

## P1：紧随其后

```text
1. 实现 production QA gate。
2. 增加 diversity / dedup report。
3. 跑 30-case production pilot batch。
4. 打包 release candidate。
5. 做 5-case diagnostic eval sample。
```

## P2：条件成熟后做

```text
1. 扩到 50-case pilot batch。
2. 做 Pilot A / Pilot B batch comparison。
3. 增加 3-model diagnostic eval。
4. 扩充 TransitionPriorStore observations。
```

## P3：继续暂缓

```text
1. UCB / bandit sampler。
2. 自动 sampler weight update。
3. broad domain expansion。
4. PDF / OCR / email / scanned evidence ecology。
5. production LLM Teacher mode。
6. formal public benchmark claim。
```

---

## 7. 当前距离第一个可规模化生产版本还有多远？

如果“第一个可规模化生产版本”定义为：

```text
固定财务/审计领域
固定现有文件类型
可批量生成 production_ready candidate tasks
带完整 manifest、QA、verifier、export、dashboard、diagnostic eval sample
```

那么当前已经完成了最难的前置证明：

```text
candidate-ready path exists
candidate-ready path survives 10-case deterministic smoke
negative controls work
guarded executed eval path works
```

剩下主要是 productionization：

```text
canonical asset consolidation
production batch runner
diversity / dedup
production QA gate
release packaging
diagnostic eval sampling
batch comparison
```

所以工程距离可以理解为：

```text
不是“还要重新发明系统”，
而是“把已经证明可行的路径收束成可交付生产版本”。
```

如果按成熟度来描述：

```text
当前：candidate-ready hardening completed
下一阶段完成后：finance/audit scalable production MVP
再下一阶段：prior learning + diagnostic model-separation maturity
```

---

## 8. Phase 13 完成后的项目状态

如果 Phase 13 成功，项目将从：

```text
经过初步硬化的 candidate-ready 任务工厂 V1.5
```

升级为：

```text
财务/审计类可规模化生产任务工厂 MVP
```

届时项目将具备：

```text
1. 可批量生成 production-ready 财务/审计任务。
2. 可导出 release 包。
3. 可审计每个任务的来源、技能、资源、工作流、评分和验证记录。
4. 可进行小规模真实执行诊断。
5. 可比较不同 production batch 的质量。
6. 可为后续 sampler learning / prior update 提供 outcome 数据。
```

这将是项目真正从“研究型系统原型”进入“可交付数据生产系统”的节点。

---

## 9. 一句话总结

Phase 13 的核心不是让系统更复杂，而是把 Phase 12 已经证明可行的 candidate-ready 路径变成一个真正可交付的财务/审计任务生产 MVP：

> 能批量生产、能质量验收、能版本化发布、能抽样真实评估、能明确限制边界、能为后续闭环学习积累数据。
