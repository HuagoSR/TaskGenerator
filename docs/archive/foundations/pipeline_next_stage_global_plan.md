# TaskGenerator 下一阶段宏观推进计划：从技能流水线到工作流条件化真实任务工厂

> 建议文件名：`docs/architecture/pipeline_next_stage_global_plan.md`
> 建议定位：宏观规划文档，不直接替代现有 `pipeline_architecture_v3.md` 和 `pipeline_b_completion_plan_2026-06-30.md`
> 核心目标：在继续推进具体工程实现的同时，为未来的 workflow、motif、任务真实性、模型区分度和闭环学习留下稳定接口，避免陷入局部调参和单任务反复修补。

---

## 1. 背景与问题判断

当前 TaskGenerator 项目已经具备较完整的两条流水线：

* **Pipeline A：Source-to-Skill**
  从真实材料、GDPVal prompt、网页材料、专业指南等来源中抽取语义技能、语义资源、技能追踪边和 motif hint。

* **Pipeline B：Skill-to-Task**
  从技能注册表中采样技能/子图，生成任务蓝图、参考文件、教师输入、GoldenRun、训练标注、rubric、质量报告、package，并导出为 rw-task 风格案例。

目前系统已经不再是“能否生成一个任务”的阶段，而是进入了更难的问题：

> 如何稳定批量生成真实、可验证、可训练、可评估、能区分模型能力的 real-world task？

当前最明显的风险不是 Pipeline B 某个模块完全不可用，而是：

1. 工程链路越来越长，但容易被局部 bug 和单任务 prompt 调整牵着走。
2. Pipeline A 的技能仍然偏“孤立节点”，虽然已有 typed resource / trace edge / motif hint，但还缺少更高层的真实工作流语境。
3. Pipeline B 当前主要根据技能、资源和 motif 组装任务，但未来应进一步升级为 workflow-conditioned task subgraph generation。
4. 当前质量门主要检查结构和局部可用性，还没有独立表达“任务是否像真实工作”“是否适合训练”“是否适合评估”“是否真的有模型区分度”。
5. 报告先行原则很稳，但如果没有受控晋升机制，系统会产生很多诊断报告，却难以逐步学习和固化改进。

因此，下一阶段不应只继续“修一个模块、跑一次 smoke、再调一个 prompt”，而应增加一层全局接口：

```text
Source / Skill / Resource substrate
        ↓
Workflow / Motif / Task-graph planning layer
        ↓
Task package generation
        ↓
Validity / evaluation / feedback / promotion layer
```

---

## 2. 下一阶段总目标

下一阶段的目标不是一次性实现所有高级功能，而是完成三件事：

### 2.1 保持现有链路可运行

继续保留当前 Pipeline A 和 Pipeline B 的稳定入口：

* `SkillRegistry/v3_skill_registry.json`
* `v3_registry_sampling_readiness_report.json`
* `v3_pipeline_b_seed_set_report.json`
* `pipeline_b_subgraph_report.json`
* `draft_task_blueprint.json`
* `reference_file_plan.json`
* `generated_file_manifest.json`
* `teacher_input_manifest.json`
* `golden_run.json`
* `training_annotation.json`
* `rubric.json`
* `pipeline_b_quality_report.json`
* `package_manifest.json`
* `rw_task_export_report.json`
* `pipeline_b_batch_report.json`
* `pipeline_b_batch_feedback_report.json`

现有 deterministic batch runner 和 batch feedback analyzer 仍然作为主要诊断入口。不要重新回到单任务分数驱动的开发方式。

### 2.2 为未来高级能力留下接口

新增若干 report-only / schema-first 的接口，不急于全部实现复杂逻辑：

* `WorkflowEpisode`
* `WorkflowArchetype`
* `MotifGraphGrammar`
* `TaskConstraintGraph`
* `ExecutionPlanDAG`
* `RealWorldnessReport`
* `SourceQualityReport`
* `DifficultyProfile`
* `ModelSeparationProfile`
* `PromotionRecord`

这些对象初期可以只是报告字段、空列表、轻量启发式或人工填写入口，不要求马上驱动采样器。

### 2.3 建立“全局视角优先”的工程纪律

每次新增模块或修 bug 前，都先判断它属于哪一层：

| 层级                          | 问题                                       |
| --------------------------- | ---------------------------------------- |
| Pipeline A substrate        | 是源材料、技能、资源、证据、trace、motif 的问题吗？          |
| Workflow / task graph layer | 是真实工作流、任务结构、角色槽位、执行依赖的问题吗？               |
| Package generation layer    | 是文件、prompt、GoldenRun、rubric、export 的问题吗？ |
| Validity / feedback layer   | 是真实度、难度、模型区分度、失败归因、晋升机制的问题吗？             |

这样可以避免把所有失败都误判成“prompt 需要再调一下”。

---

## 3. 下一阶段核心设计原则

### 原则 1：原子技能继续保留，但必须绑定工作流语境

原子技能仍然是必要的。它保证技能可复用、可去重、可组合。

但每个技能不应只作为孤立节点存在。Pipeline A 未来应尽量同时保留：

```text
Atomic Skill
+ Typed Resource Interface
+ Source Trace Context
+ Motif Role Hint
+ Workflow Episode Context
```

也就是说，技能既要足够小，又要知道它在真实工作中通常扮演什么角色。

---

### 原则 2：Pipeline B 不应采样 skill list，而应采样 workflow-conditioned subgraph

未来的任务构造不应是：

```text
随机选几个 sample_ready skills
→ 拼成任务
```

也不应只是：

```text
A -> B -> C 链式 next-skill prediction
```

而应逐步升级为：

```text
选择 domain
→ 选择 workflow archetype
→ 选择 motif / graph grammar
→ 填充 graph roles
→ 检查 typed resource compatibility
→ 使用 transition belief 排序与探索
→ 生成 task constraint graph
→ 展开 execution plan DAG
→ 生成任务包
```

初期不需要完全实现这个流程，但数据结构和报告字段要为它预留空间。

---

### 原则 3：motif 不只是标签，而应逐步升级为 graph grammar

当前已有的五类 motif：

* `fan_in_reconciliation`
* `policy_application`
* `exception_escalation`
* `cross_check_validation`
* `evidence_to_deliverable`

下一阶段应逐步给每个 motif 增加：

* required roles
* optional roles
* required resources
* provided resources
* expected evidence pattern
* typical execution stages
* validation constraints
* common failure modes

示例：

```yaml
motif_type: policy_application
required_roles:
  - policy_source
  - rule_extraction_skill
  - case_evidence_source
  - rule_application_skill
  - uncertainty_or_exception_handler
  - final_deliverable_skill
optional_roles:
  - conflicting_policy_detector
  - missing_evidence_detector
  - cross_check_validator
required_resources:
  - PolicyRule
  - CaseEvidence
  - AppliedConclusion
execution_stages:
  - extract_policy
  - extract_facts
  - map_policy_to_facts
  - classify_result
  - write_supported_conclusion
  - validate_citations
```

---

### 原则 4：允许任务结构是图，但执行计划必须可解

真实任务可以是树、DAG、甚至带无向环的约束图。

但 GoldenRun 和候选模型解题时，需要有可执行顺序。

因此下一阶段应明确区分：

```text
TaskConstraintGraph
  描述任务对象、文件、证据、中间结果、约束之间的关系。
  可以有交叉引用、约束回环、验证关系。

ExecutionPlanDAG
  描述实际求解阶段。
  必须可拓扑排序，不能有不可执行的有向循环。
```

例如：

```text
ledger total + bank total → reconciliation difference
reconciliation difference + policy rule → exception explanation
exception explanation + evidence map → final memo
final memo → validation against ledger / bank / policy
```

这里验证关系可能形成约束环，但执行计划仍然是 DAG。

---

### 原则 5：质量反馈要做 credit assignment，不能粗暴惩罚所有 skill / edge

当一个任务失败时，不能简单把它用到的所有技能、边、motif 都降权。

应根据 reason code 分类归因：

| 失败原因                         | 应反馈给哪里                                                     |
| ---------------------------- | ---------------------------------------------------------- |
| `low_subgraph_confidence`    | typed resources / transition evidence / sampler confidence |
| `single_source_support`      | source diversity / skill evidence support                  |
| `partial_intermediate_state` | TeacherRunner / execution plan / role operationalization   |
| `rubric_format_noise`        | rubric builder / audience split                            |
| `policy_clause_traceability` | evidence locator / policy mapping / file manifest          |
| `model_separation_low`       | difficulty profile / trap design / ambiguity design        |
| `export_validation_failure`  | rw-task exporter / package assembler                       |
| `external_eval_timeout`      | eval runner robustness, not task quality itself            |

这意味着 feedback updater 未来必须是单独模块，不能隐藏在 task generation 过程中。

---

### 原则 6：不要过早实现“假的 UCB / bandit”

UCB1 或 bandit 策略是长期方向，但当前不应急着在全库 skill edge 上做 bandit。

原因：

1. 反馈样本太少。
2. 任务失败归因还不稳定。
3. skill edge 空间太大。
4. 当前很多失败来自 typed resource / source support / teacher operationalization，而不是 transition policy 本身。

更合理的顺序是：

```text
先记录 feedback contract
→ 再积累 batch-level outcomes
→ 再做 reason-code credit assignment
→ 再更新 workflow / motif / role / edge priors
→ 最后才引入 UCB / exploration bonus
```

---

## 4. 下一阶段总体架构

建议将系统从“两条流水线”扩展为“三层闭环架构”。

### 第一层：Source / Skill / Resource Substrate

负责真实材料、技能、资源接口、trace、motif hint、workflow episode。

关键对象：

* `RawSource`
* `NormalizedSource`
* `ExtractedSkillCandidate`
* `SkillRegistryEntry`
* `SemanticResource`
* `SkillTraceEdge`
* `SkillMotifHint`
* `WorkflowEpisode`

目标：

```text
从真实材料中抽取可复用能力，同时保留这些能力在真实工作流中的上下文。
```

---

### 第二层：Workflow-conditioned Task Package Generation

负责从 workflow / motif / skill-resource graph 生成任务包。

关键对象：

* `WorkflowArchetype`
* `MotifGraphGrammar`
* `PipelineBSubgraph`
* `TaskConstraintGraph`
* `ExecutionPlanDAG`
* `TaskBlueprint`
* `EvidenceDossierPlan`
* `ReferenceFilePlan`
* `GoldenRun`
* `TrainingAnnotation`
* `Rubric`

目标：

```text
不是拼 skill list，而是生成一个有真实工作流语境、结构可执行、证据可追踪的任务包。
```

---

### 第三层：Validity / Feedback / Promotion Loop

负责判断任务是否真实、是否可训练、是否可评估、是否有模型区分度，以及哪些改进可以被晋升为持久状态。

关键对象：

* `RealWorldnessReport`
* `SourceQualityReport`
* `DifficultyProfile`
* `ModelSeparationProfile`
* `FailureCorpus`
* `FeedbackAttributionReport`
* `PromotionRecord`
* `RollbackRecord`

目标：

```text
把 batch 反馈转化为可审计、可回滚、可逐步学习的系统改进，而不是一次性 smoke 结果。
```

---

## 5. 新增接口草案

本节只定义未来接口，不要求下一阶段全部实现复杂逻辑。

---

### 5.1 WorkflowEpisode

`WorkflowEpisode` 是 Pipeline A 从源材料中识别出的真实工作流片段。

它不是完整任务，也不是单个 skill，而是保留“真实工作中这些动作为什么连在一起”的上下文。

```json
{
  "workflow_episode_id": "wfep_0001",
  "source_id": "source_...",
  "domain": "audit",
  "business_context": "internal control testing",
  "actor_role": "audit associate",
  "trigger_event": "testing found missing supporting evidence",
  "input_artifacts": [
    "control matrix",
    "testing workpaper",
    "policy memo"
  ],
  "steps": [
    {
      "step_id": "step_001",
      "skill_candidate_id": "skill_...",
      "workflow_role": "context_setup",
      "observed_order": 1
    },
    {
      "step_id": "step_002",
      "skill_candidate_id": "skill_...",
      "workflow_role": "evidence_extraction",
      "observed_order": 2
    },
    {
      "step_id": "step_003",
      "skill_candidate_id": "skill_...",
      "workflow_role": "judgment",
      "observed_order": 3
    },
    {
      "step_id": "step_004",
      "skill_candidate_id": "skill_...",
      "workflow_role": "deliverable_synthesis",
      "observed_order": 4
    }
  ],
  "motif_hints": [
    "exception_escalation",
    "evidence_to_deliverable"
  ],
  "deliverable_type": "memo",
  "observed_constraints": [
    "cite evidence",
    "separate confirmed exceptions from unresolved items"
  ],
  "confidence": "medium",
  "review_status": "proposed"
}
```

初期实现方式：

* 不写入持久注册表。
* 可以由现有 extraction output 派生。
* 先生成 `workflow_episode_proposals.json`。
* 只做报告，不参与正式采样。

---

### 5.2 WorkflowArchetype

`WorkflowArchetype` 是跨多个 source episode 归纳出的真实工作类型。

示例：

* `vendor_payment_approval_review`
* `monthly_close_variance_investigation`
* `internal_control_exception_documentation`
* `policy_update_impact_review`
* `budget_reforecast_reconciliation`
* `customer_refund_escalation_review`

草案结构：

```json
{
  "workflow_archetype_id": "wfa_0001",
  "name": "internal_control_exception_documentation",
  "domain": "audit",
  "typical_actor_roles": [
    "audit associate",
    "audit manager"
  ],
  "trigger_events": [
    "control test exception found",
    "missing supporting evidence identified"
  ],
  "common_input_artifacts": [
    "control matrix",
    "sample testing workpaper",
    "policy reference",
    "exception log"
  ],
  "common_motifs": [
    "exception_escalation",
    "policy_application",
    "evidence_to_deliverable"
  ],
  "common_deliverables": [
    "audit memo",
    "exception summary",
    "manager-ready finding"
  ],
  "typical_constraints": [
    "cite evidence IDs",
    "cite policy clause IDs",
    "separate confirmed exceptions from unresolved issues"
  ],
  "source_episode_ids": [],
  "status": "experimental"
}
```

初期实现方式：

* 可以先手写 3–5 个 archetype。
* 不要求自动聚类。
* 作为 Pipeline B 采样时的可选 context，不强制改变现有 sampler。

---

### 5.3 MotifGraphGrammar

`MotifGraphGrammar` 把 motif 从标签升级为可展开的任务结构模板。

草案结构：

```json
{
  "motif_type": "fan_in_reconciliation",
  "required_roles": [
    "source_a_extractor",
    "source_b_extractor",
    "normalizer",
    "difference_calculator",
    "exception_explainer",
    "deliverable_synthesizer"
  ],
  "optional_roles": [
    "policy_checker",
    "cross_check_validator",
    "missing_evidence_detector"
  ],
  "required_resource_types": [
    "SourceDocument",
    "FinancialMetric",
    "MonetaryAmount",
    "ReconciliationDifference",
    "SupportedConclusion"
  ],
  "expected_graph_shape": "fan_in",
  "execution_stage_template": [
    "extract_source_facts",
    "normalize_values",
    "compare_or_reconcile",
    "explain_difference",
    "write_deliverable",
    "validate_traceability"
  ],
  "validation_constraints": [
    "all material conclusions must cite evidence",
    "differences must be explainable or marked unresolved"
  ]
}
```

初期实现方式：

* 先为 2 个 motif 写 grammar：`policy_application` 和 `fan_in_reconciliation`。
* Pipeline B sampler 可以只读取 grammar 并写入报告，不一定马上完全按 grammar 采样。
* 后续再让 sampler 用 role slot 填充技能。

---

### 5.4 TaskConstraintGraph

`TaskConstraintGraph` 描述一个具体任务包内部的结构关系。

节点类型：

* `reference_file`
* `evidence_item`
* `policy_clause`
* `semantic_resource`
* `skill_step`
* `intermediate_artifact`
* `deliverable_section`
* `validation_constraint`
* `trap_or_distractor`

边类型：

* `provides`
* `requires`
* `supports`
* `contradicts`
* `validates`
* `derived_from`
* `must_cite`
* `uncertain_due_to_missing_evidence`

初期实现方式：

* 可以由现有 `reference_file_plan.json`、`evidence_index.json`、`teacher_input_manifest.json` 和 `golden_run.json` 派生。
* 先生成 `task_constraint_graph_report.json`。
* 不要求影响导出。

---

### 5.5 ExecutionPlanDAG

`ExecutionPlanDAG` 描述 GoldenRun / candidate 解题的可执行阶段。

草案结构：

```json
{
  "execution_plan_id": "exec_0001",
  "stages": [
    {
      "stage_id": "stage_1",
      "name": "evidence_inventory",
      "requires": [],
      "provides": ["EvidenceInventory"]
    },
    {
      "stage_id": "stage_2",
      "name": "policy_clause_mapping",
      "requires": ["EvidenceInventory", "PolicyRule"],
      "provides": ["PolicyClauseEvidenceMap"]
    },
    {
      "stage_id": "stage_3",
      "name": "evidence_to_conclusion_map",
      "requires": ["EvidenceInventory", "PolicyClauseEvidenceMap"],
      "provides": ["SupportedConclusion"]
    },
    {
      "stage_id": "stage_4",
      "name": "final_deliverable",
      "requires": ["SupportedConclusion"],
      "provides": ["ManagerReadyDeliverable"]
    }
  ],
  "dag_valid": true,
  "validation_notes": []
}
```

初期实现方式：

* 可以由 TeacherRunner intermediate states 派生。
* 用于检查 GoldenRun 是否有可执行顺序。
* 后续可用于判断 task graph 是否复杂但可解。

---

### 5.6 RealWorldnessReport

`RealWorldnessReport` 判断任务是否像真实工作，而不只是结构完整。

维度：

```json
{
  "real_worldness_score": 0.0,
  "dimensions": {
    "business_context_plausibility": 0.0,
    "artifact_ecology_realism": 0.0,
    "evidence_noise_and_conflict": 0.0,
    "decision_consequence": 0.0,
    "deliverable_realism": 0.0,
    "anti_template_score": 0.0
  },
  "findings": [],
  "recommendation": "revise"
}
```

初期实现方式：

* 先做 deterministic heuristic。
* 不调用 LLM。
* 只输出报告，不阻断现有 Pipeline B。
* 等指标稳定后再纳入 quality gate。

---

### 5.7 SourceQualityReport

`SourceQualityReport` 判断源材料是否适合产生真实任务。

维度：

```json
{
  "source_id": "source_...",
  "authenticity_score": 0.0,
  "domain_authority": 0.0,
  "workflow_signal_strength": 0.0,
  "skill_density": 0.0,
  "evidence_granularity": 0.0,
  "license_or_use_risk": "unknown",
  "sensitivity_level": "low",
  "recommended_use": "skill_extraction_only"
}
```

初期实现方式：

* 可以先对 source metadata 和 normalized blocks 做静态检查。
* 对 GDPVal prompt、网页材料、专业指南分别设置不同默认策略。
* 不影响当前 SourceCollector，只作为附加报告。

---

### 5.8 DifficultyProfile

`DifficultyProfile` 不应只是一个难度标签，而应是多轴难度。

```json
{
  "difficulty_profile": {
    "evidence_retrieval": 1,
    "cross_file_reasoning": 1,
    "numerical_reasoning": 1,
    "policy_application": 1,
    "ambiguity_management": 1,
    "deliverable_complexity": 1,
    "robustness_to_noise": 1
  },
  "target_use": "training_candidate"
}
```

初期实现方式：

* 从 task blueprint、reference file plan、rubric criteria、trap count 中估计。
* 先用于 batch 统计，不用于强制采样。

---

### 5.9 ModelSeparationProfile

`ModelSeparationProfile` 记录任务是否真的能区分模型能力。

```json
{
  "task_id": "task_...",
  "evaluation_status": "not_enough_data",
  "models": [],
  "score_summary": {
    "weak_model_mean": null,
    "medium_model_mean": null,
    "strong_model_mean": null,
    "score_gap": null,
    "retry_variance": null
  },
  "discriminative_rubric_items": [],
  "format_noise_rubric_items": [],
  "common_failure_modes": [],
  "recommendation": "collect_more_evidence"
}
```

初期实现方式：

* 只定义接口。
* 不急于真实跑多模型比较。
* 只有 `candidate_ready` 或高质量 `diagnostic_eval` 包才进入这个层级。

---

### 5.10 PromotionRecord

`PromotionRecord` 负责把报告先行升级为受控晋升。

适用对象：

* typed resource patch
* skill admission
* workflow archetype
* motif grammar
* transition prior
* sampler weight
* quality gate rule
* source quality rule

草案结构：

```json
{
  "promotion_id": "promo_0001",
  "target_type": "typed_resource_patch",
  "target_ids": [],
  "source_report_ids": [],
  "review_status": "proposed",
  "reviewer": null,
  "decision": "pending",
  "applied_at": null,
  "rollback_available": true,
  "rollback_record_id": null,
  "notes": []
}
```

初期实现方式：

* 先生成 proposal。
* 不自动 apply。
* 后续手动审核后再单独实现 apply CLI。

---

## 6. 分阶段实施计划

---

## Phase 0：全局文档与接口冻结

### 目标

先把大局写清楚，避免工程推进时再次陷入局部思维。

### 工作内容

1. 新增本文档：

   * `docs/architecture/pipeline_next_stage_global_plan.md`

2. 新增接口说明文档：

   * `docs/architecture/global_interface_contracts.md`

3. 在现有 roadmap 中补一段：

   * 当前阶段从 “Pipeline B completion” 进入 “workflow-conditioned task factory interface”。
   * 明确：不推翻现有 Pipeline B，只在其上增加全局报告接口。

4. 建立术语表：

   * skill
   * resource
   * trace edge
   * motif
   * workflow episode
   * workflow archetype
   * task constraint graph
   * execution plan DAG
   * real-worldness
   * model separation
   * promotion

### 输出

```text
docs/architecture/pipeline_next_stage_global_plan.md
docs/architecture/global_interface_contracts.md
```

### 验收标准

* 文档能解释为什么不继续只打磨单个任务。
* 文档能解释 workflow / motif / skill-resource graph 三者关系。
* 文档明确哪些是近期实现，哪些只是未来接口。
* 文档明确不直接修改持久注册表。

---

## Phase 1：新增全局报告壳层，不改变现有流水线行为

### 目标

先让现有 Pipeline B batch run 额外产出全局诊断报告，但不改变采样、生成、质量门和导出逻辑。

### 新增报告

```text
global_task_validity_report.json
real_worldness_report.json
difficulty_profile_report.json
task_constraint_graph_report.json
execution_plan_dag_report.json
```

### 工作内容

1. 从现有 artifacts 读取：

   * `draft_task_blueprint.json`
   * `reference_file_plan.json`
   * `generated_file_manifest.json`
   * `evidence_index.json`
   * `teacher_input_manifest.json`
   * `golden_run.json`
   * `rubric.json`
   * `pipeline_b_quality_report.json`

2. 生成轻量级报告：

   * 任务是否有明确业务角色？
   * 是否有真实触发事件？
   * 是否有多文件证据生态？
   * 是否有证据冲突或缺失？
   * 是否有可执行阶段？
   * 是否存在 task graph 结构？
   * 是否只是模板化 section 填空？

3. 所有判断都先作为 `diagnostic_only`，不进入 quality gate。

### 输出目录建议

```text
artifacts/pipeline_b/scratch/<case_id>/global_validity/
```

### 验收标准

* 不改变现有 Pipeline B 结果。
* 不影响 `candidate_ready` / `revise` / `reject` 判定。
* 每个 batch case 都能生成全局诊断报告。
* 报告能指出“结构完整但真实感不足”的任务。

---

## Phase 2：WorkflowEpisode Proposal V1

### 目标

让 Pipeline A 不只抽取 skill / resource / trace / motif hint，还能保留真实工作流片段。

### 工作内容

1. 新增 `WorkflowEpisode` schema。

2. 从已有 extraction output 中派生 workflow episode proposal。

3. 初期不要求 LLM prompt 大改，可先用现有字段启发式组合：

   * 同一 source 下的 skill candidates
   * trace edges
   * motif hints
   * source title / domain tags
   * deliverable hints
   * evidence spans

4. 输出 proposal，不进入 SkillRegistry。

### 新增模块建议

```text
src/task_generator/v3_workflow_episode_proposer.py
Test/run_v3_workflow_episode_proposer.py
```

### 输出

```text
workflow_episode_proposals.json
workflow_episode_proposal_report.json
```

### 验收标准

* 每个 source batch 至少能尝试生成 workflow episode proposal。
* episode 中能保留 actor role、trigger event、input artifacts、step roles、motif hints。
* proposal 中保留 source evidence。
* 不写入 `SkillRegistry/v3_skill_registry.json`。

---

## Phase 3：WorkflowArchetype Registry 草案

### 目标

建立 3–5 个手工或半自动的 workflow archetype，让 Pipeline B 未来不再直接从孤立 skill 开始生成任务。

### 初始 archetype 建议

```text
internal_control_exception_documentation
policy_clause_application_review
multi_source_reconciliation_memo
missing_evidence_escalation_review
evidence_based_manager_briefing
```

### 工作内容

1. 新增实验性文件：

```text
SkillRegistry/v3_workflow_archetype_registry.experimental.json
```

2. 每个 archetype 记录：

   * domain
   * actor roles
   * trigger events
   * common input artifacts
   * common motifs
   * common deliverables
   * common constraints
   * associated workflow episode IDs

3. 先不让 sampler 强依赖 archetype。

4. Pipeline B 只把 archetype 信息写入 blueprint / report。

### 验收标准

* 至少 3 个 archetype。
* 每个 archetype 至少关联 1 个 motif。
* 每个 archetype 至少定义 1 种 realistic deliverable。
* 不影响当前 batch runner。

---

## Phase 4：MotifGraphGrammar V1

### 目标

把 motif 从“标签”升级成“可展开的图结构模板”。

### 优先支持的 motif

先做两个：

1. `policy_application`
2. `fan_in_reconciliation`

原因：

* 这两类任务结构清晰。
* 当前项目已有相关文件生成和 rubric 经验。
* 二者能覆盖政策条款映射、多源证据、对账、异常解释等核心能力。

### 工作内容

1. 新增 motif grammar 文件：

```text
SkillRegistry/v3_motif_graph_grammar.experimental.json
```

2. 每个 grammar 包含：

   * required roles
   * optional roles
   * required resource types
   * expected graph shape
   * execution stage template
   * validation constraints
   * common failure modes

3. 修改 Pipeline B sampler report：

   * 写入 selected motif grammar ID。
   * 写入哪些 role 被填充。
   * 写入哪些 role 缺失。
   * 写入 fallback reason。

4. 初期不强制 sampler 完全按 grammar 生成，只做 report alignment。

### 验收标准

* `pipeline_b_subgraph_report.json` 能显示 role coverage。
* batch feedback 能统计 motif role 缺口。
* 不因为 grammar 缺失而直接阻断现有任务生成。

---

## Phase 5：Subgraph Sampler V2：从 skill sampling 到 role filling

### 目标

将 Pipeline B sampler 从“选一组 skills”逐步升级为“在 workflow / motif 条件下填充 graph roles”。

### 工作内容

1. Sampler 输入增加可选参数：

   * `--workflow-archetype`
   * `--motif-grammar`
   * `--target-difficulty-profile`

2. Sampler scoring 从简单 skill selection 扩展为：

```text
candidate_score =
  readiness_weight
  + resource_compatibility_score
  + motif_role_fit_score
  + workflow_context_fit_score
  + source_trace_prior
  + support_diversity_score
  + novelty_bonus
  - known_risk_penalty
```

3. 输出继续 report-first：

   * 不更新 transition prior。
   * 不更新 sampler weight。
   * 不调用 UCB。
   * 不自动采样 `exclude_until_revised`。

4. `sample_with_caution` 仍需显式 flag 才可探索。

### 输出字段新增

```json
{
  "workflow_archetype_id": null,
  "motif_grammar_id": null,
  "filled_roles": [],
  "missing_roles": [],
  "role_fit_scores": [],
  "workflow_context_fit": "low|medium|high",
  "task_graph_shape_assumption": "chain|tree|dag|constraint_graph",
  "sampler_policy_version": "role_filling_v1"
}
```

### 验收标准

* 旧命令仍可运行。
* 新命令可在指定 motif grammar 时输出 role coverage。
* batch report 能聚合 missing roles。
* 如果 typed resources 仍缺失，必须继续显式报告 `low_due_to_resource_fallback`，不能掩盖。

---

## Phase 6：EvidenceDossierPlan V1

### 目标

把 reference files 从“生成几个文件”升级为“生成真实证据包”。

### 设计思想

真实任务往往不是一个干净 `.xlsx` 加一个 `.docx`，而是一组有版本、有冗余、有冲突、有缺失、有干扰的材料包。

### 新增对象

```text
EvidenceDossierPlan
```

### 字段草案

```json
{
  "dossier_id": "dos_0001",
  "business_context": "internal control exception review",
  "candidate_visible_files": [],
  "teacher_only_files": [],
  "file_roles": [
    {
      "file_id": "file_001",
      "role": "primary_evidence",
      "noise_level": "low",
      "contains_conflict": false,
      "contains_missing_fields": true,
      "version_relation": null
    }
  ],
  "cross_file_constraints": [],
  "distractor_items": [],
  "expected_evidence_paths": []
}
```

### 工作内容

1. 先不重写 ReferenceFileGenerator。

2. 在 `reference_file_plan.json` 外层增加 dossier metadata。

3. 支持描述：

   * primary evidence
   * policy reference
   * manager notes
   * outdated version
   * distractor source
   * missing attachment
   * conflict source

4. 初期仍然可以只生成 2 个文件，但报告中要能表达未来文件生态。

### 验收标准

* 当前 `.xlsx` + `.docx` 任务也能被描述为一个简化 evidence dossier。
* 文件角色、噪声、冲突、缺失、版本关系有字段。
* 不要求一次性生成 email、PDF、图片等复杂文件。

---

## Phase 7：独立 Verifier V1

### 目标

降低 GoldenRun / rubric / prompt 自证循环风险。

### 问题

当前任务生成、教师解答和评分规则都来自同一条链路，容易出现：

```text
生成器要求写某 section
→ TeacherRunner 也写这个 section
→ Rubric 也按这个 section 评分
→ 分数提高，但不一定说明任务真实解决
```

### 工作内容

新增 `TaskVerifier`，独立检查：

1. GoldenRun 中的结论是否能追溯到 evidence IDs。
2. policy-sensitive conclusion 是否同时引用 policy clause 和 evidence。
3. final deliverable 是否覆盖 candidate prompt 的核心要求。
4. TaskConstraintGraph 中的 required constraints 是否被 GoldenRun 满足。
5. 是否存在 unsupported conclusion。
6. 是否存在 evidence item 未被使用但被 rubric 要求引用。
7. 是否存在 rubric criteria 对候选不可见或不可操作。

### 新增模块建议

```text
src/task_generator/v3_task_verifier.py
Test/run_v3_task_verifier.py
```

### 输出

```text
task_verifier_report.json
```

### 验收标准

* Verifier 默认 deterministic。
* 不调用 LLM。
* 不修改 GoldenRun / rubric。
* 只输出 blocking / revise / warning findings。
* 后续可接入 quality gate，但初期只做诊断。

---

## Phase 8：Promotion / Rollback 机制 V1

### 目标

把“报告先行”升级为“可审计晋升”，避免系统只产出报告但无法学习。

### 适用对象

* typed resource patch
* workflow archetype
* motif grammar
* source quality rule
* transition prior candidate
* registry admission candidate
* readiness status change
* sampler scoring rule

### 工作内容

1. 新增 promotion proposal schema。

2. 新增 promotion report。

3. 新增手动审核状态：

   * `proposed`
   * `approved`
   * `rejected`
   * `applied`
   * `rolled_back`

4. 初期只支持 typed resource patch apply。

5. 所有 apply 必须生成 rollback record。

### 新增模块建议

```text
src/task_generator/v3_promotion_manager.py
Test/run_v3_promotion_manager.py
```

### 验收标准

* 默认只生成 proposal，不 apply。
* apply 必须显式 flag。
* 每次 apply 记录 source report、review decision、target file、diff summary。
* 可以回滚。
* 不允许 task generation 过程隐式修改 registry。

---

## Phase 9：Batch-level Global Dashboard

### 目标

把多个报告汇总成一个全局视图，让开发者不被单个 case 牵着走。

### 输入

* `pipeline_b_batch_report.json`
* `pipeline_b_batch_feedback_report.json`
* `real_worldness_report.json`
* `difficulty_profile_report.json`
* `task_verifier_report.json`
* `pipeline_a_substrate_audit_report.json`
* `typed_resource_patch_proposal_report.json`

### 输出

```text
global_pipeline_dashboard_report.json
```

### Dashboard 维度

```text
Batch health
- attempted cases
- revise / reject / candidate_ready counts
- repeated reason codes
- motif-level failure distribution

Pipeline A substrate health
- typed resource coverage
- source support diversity
- transition evidence coverage
- workflow episode coverage

Task realism health
- real-worldness score distribution
- artifact ecology richness
- business-context plausibility
- anti-template score

Task executability health
- execution DAG validity
- unsupported GoldenRun conclusions
- verifier blocking findings

Training / evaluation readiness
- training_candidate count
- diagnostic_eval count
- benchmark_grade count
- model separation evidence count
```

### 验收标准

* dashboard 能回答“下一步该修 Pipeline A、Pipeline B、文件生成、TeacherRunner、rubric 还是 eval runner？”
* dashboard 不被单个任务分数主导。
* dashboard 能识别跨案例系统性问题。

---

## 7. 建议的近期最小实施顺序

如果只选最小的一组下一步，不建议马上实现全部 9 个 Phase。

建议近期先做以下 5 个最小切片：

### Slice 1：写入全局规划文档与接口文档

输出：

```text
docs/architecture/pipeline_next_stage_global_plan.md
docs/architecture/global_interface_contracts.md
```

目的：

* 固定大方向。
* 避免后续开发变成无边界修 bug。

---

### Slice 2：Global Validity Report 壳层

输出：

```text
global_task_validity_report.json
real_worldness_report.json
difficulty_profile_report.json
```

目的：

* 不改变现有流水线。
* 让每个 batch case 多一层全局诊断。

---

### Slice 3：WorkflowEpisode Proposal V1

输出：

```text
workflow_episode_proposals.json
workflow_episode_proposal_report.json
```

目的：

* 让 Pipeline A 从“技能提取”升级为“技能 + 工作流片段提取”。
* 仍然不改注册表。

---

### Slice 4：MotifGraphGrammar V1

输出：

```text
v3_motif_graph_grammar.experimental.json
```

目的：

* 先把 `policy_application` 和 `fan_in_reconciliation` 两个 motif 结构化。
* 让后续 sampler 有 role slots 可填。

---

### Slice 5：Sampler Report Role Coverage

输出字段：

```text
filled_roles
missing_roles
role_fit_scores
workflow_context_fit
task_graph_shape_assumption
```

目的：

* 暂时不改采样策略。
* 先让 sampler 报告它是否满足 motif / workflow role。
* 为后续 role-filling sampler 做准备。

---

## 8. 暂缓事项

以下事项重要，但不建议立刻做。

### 8.1 暂缓真正的 UCB / bandit sampler

原因：

* 当前反馈样本不足。
* credit assignment 还没解决。
* 过早实现会制造“看似智能”的假闭环。

当前只需要记录未来 bandit 需要的数据：

```text
observed_count
success_count
failure_count
reason_code_distribution
motif_context
workflow_context
role_context
source_support_level
```

---

### 8.2 暂缓大规模领域扩展

可以设计领域扩展接口，但不要马上扩到法律、医疗、HR、供应链等多个领域。

原因：

* 当前 audit / finance / compliance 领域还没形成稳定 candidate_ready 工厂。
* 过早扩展会稀释诊断信号。

建议：

```text
先把 audit / finance / compliance 做到 batch 稳定
再选择 supply_chain 或 customer_support_ops 作为第二领域
```

---

### 8.3 暂缓复杂文件生态生成

EvidenceDossierPlan 可以先建接口，但不要马上实现 email thread、PDF scan、图片 OCR、隐藏列、复杂 Excel 样式等。

建议顺序：

```text
xlsx + docx
→ xlsx + docx + txt/manager note
→ 多版本 policy
→ email-like md
→ folder-style evidence package
→ PDF / image / scanned artifact
```

---

### 8.4 暂缓正式模型区分度评估

当前 draft smoke 只能作为诊断，不应作为正式 model separation evidence。

只有当任务达到以下条件后再进入模型区分度评估：

* package 不再是 `revise_only`
* task verifier 无 blocking findings
* real-worldness 达到阈值
* difficulty profile 明确
* rubric audience split 稳定
* reference evidence locator 稳定
* 至少小批量任务达到 `candidate_ready`

---

## 9. 关键反模式

下一阶段需要刻意避免这些反模式。

### 反模式 1：单任务分数驱动开发

错误做法：

```text
某个 draft 得分低
→ 继续调这个 prompt
→ 得分上升
→ 误以为系统变好
```

正确做法：

```text
batch 运行
→ 看跨案例 repeated reason codes
→ 找系统性原因
→ 修接口或 substrate
→ 再 batch 验证
```

---

### 反模式 2：把 Pipeline A 问题藏在 Pipeline B fallback 里

错误做法：

```text
typed resource 缺失
→ Pipeline B 自己猜
→ 任务勉强生成
→ 报告里不显示缺口
```

正确做法：

```text
typed resource 缺失
→ Pipeline B 可以 fallback
→ 但必须显式写入 report
→ batch feedback 聚合
→ Pipeline A substrate audit / promotion 处理
```

---

### 反模式 3：把 workflow archetype 做成硬模板

Workflow archetype 不是固定题目模板。

错误做法：

```text
internal_control_exception_documentation
= 固定文件 + 固定 prompt + 固定 rubric
```

正确做法：

```text
workflow archetype
= 角色、触发事件、常见文件、常见 motif、常见约束、常见交付物
```

它应该提供真实语境，而不是把任务变成模板换皮。

---

### 反模式 4：隐式修改注册表

错误做法：

```text
任务生成失败
→ 某模块自动改 SkillRegistry
```

正确做法：

```text
任务生成失败
→ 生成 feedback report
→ 生成 promotion proposal
→ 人工或显式审核
→ apply CLI
→ 生成 rollback record
```

---

### 反模式 5：过度追求复杂图生成器

错误做法：

```text
一开始就支持任意图、任意环、任意 motif
```

正确做法：

```text
先支持 2 个 motif grammar
→ role coverage report
→ task constraint graph report
→ execution DAG validation
→ 再逐步扩展
```

---

## 10. 下一阶段完成标志

下一阶段不以“所有任务 candidate_ready”为完成标志。

更合理的完成标志是：

### 10.1 全局接口完成

* 有 `WorkflowEpisode` schema。
* 有 `WorkflowArchetype` 草案。
* 有 `MotifGraphGrammar` 草案。
* 有 `TaskConstraintGraph` 报告。
* 有 `ExecutionPlanDAG` 报告。
* 有 `RealWorldnessReport`。
* 有 `DifficultyProfile`。
* 有 `PromotionRecord` 草案。

### 10.2 现有流水线未被破坏

* 旧 Pipeline B batch runner 仍可运行。
* 旧 rw-task draft export 仍可运行。
* 旧 quality gate 仍可运行。
* 所有新增模块默认 report-only。

### 10.3 batch 诊断更清晰

以前只能看到：

```text
low_subgraph_confidence
single_source_support
partial_intermediate_state
```

下一阶段应能进一步定位为：

```text
缺少 typed resource？
缺少 workflow role？
缺少 motif grammar role？
缺少 source support？
task graph 不完整？
execution DAG 不清楚？
real-worldness 不足？
rubric 在评格式而不是评任务？
```

### 10.4 为未来闭环学习留下数据

即使暂不实现 UCB / bandit，也应开始记录：

```text
workflow_archetype_id
motif_grammar_id
filled_roles
missing_roles
skill_role_assignments
task_graph_shape
execution_stage_status
real_worldness_dimensions
difficulty_profile
verifier_findings
quality_reason_codes
promotion_candidate_ids
```

这些字段未来可以成为 transition prior、motif prior、workflow prior 和 sampler weight 的更新依据。

---

## 11. 最终路线图摘要

```text
当前状态：
Pipeline B 链路已基本跑通，但任务仍多为 revise/draft。
主要瓶颈是 Pipeline A substrate 与任务真实性/全局有效性接口不足。

下一阶段：
不急于重写现有模块。
先新增全局接口和报告层。

最小推进顺序：
1. 写全局规划文档和接口文档。
2. 增加 Global Validity Report 壳层。
3. 增加 WorkflowEpisode Proposal。
4. 增加 MotifGraphGrammar V1。
5. 让 sampler 报告 role coverage。
6. 再考虑 role-filling sampler。
7. 再考虑 verifier、promotion、model separation。

长期目标：
从“技能到任务”升级为
“真实来源 → 技能/资源/工作流 → workflow-conditioned task graph → 证据包 → GoldenRun/rubric → 质量与模型反馈 → 受控晋升”的闭环任务工厂。
```

---

## 12. 一句话原则

下一阶段最重要的原则是：

> 不要为了修一个任务而失去任务工厂的大局；每个局部修复都应该留下可复用的接口、报告字段或晋升路径。
