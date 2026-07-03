# Global Interface Contracts

## Status

This document turns `pipeline_next_stage_global_plan.md` into implementation-facing interface contracts.

These contracts are intentionally schema-first and report-only. They should help future work add global diagnostics without changing existing Pipeline A registry state, Pipeline B sampling behavior, package readiness, rw-task export semantics, or sampler weights.

## Priority Rules

- Preserve the current Pipeline A and Pipeline B runners.
- Prefer additive reports and optional fields before changing core behavior.
- Keep all persistent registry, readiness, transition-prior, and sampler-weight updates behind explicit review or apply commands.
- Treat single rw-task draft smoke scores as diagnostic observations, not final model-separation evidence.
- Prefer small Pipeline B batches and repeated reason-code analysis over single-task prompt tuning.

## Layer Map

### Source / Skill / Resource Substrate

Owns source provenance, extracted semantic skills, typed resources, local traces, motif hints, and future workflow episode proposals.

Existing objects:

- `RawSource`
- `NormalizedSource`
- `SourceBlock`
- `ExtractedSkillCandidate`
- `SkillEvidence`
- `SemanticResource`
- `SkillTraceEdge`
- `SkillMotifHint`
- `SkillRegistryEntry`

New contracts:

- `WorkflowEpisode`
- `SourceQualityReport`

### Workflow / Motif / Task Graph Planning

Owns the bridge from isolated skills to workflow-conditioned task structure.

Existing objects:

- `PipelineBSubgraph`
- readiness and transition reports
- composition readiness reports

New contracts:

- `WorkflowArchetype`
- `MotifGraphGrammar`
- `TaskConstraintGraph`
- `ExecutionPlanDAG`

### Task Package Generation

Owns concrete task artifacts and candidate/teacher contracts.

Existing objects:

- `TaskBlueprint`
- `ReferenceFilePlan`
- `generated_file_manifest.json`
- `evidence_index.json`
- `teacher_input_manifest.json`
- `GoldenRun`
- `TrainingAnnotation`
- `Rubric`
- `pipeline_b_quality_report.json`
- `package_manifest.json`
- `rw_task_export_report.json`

New contract:

- `EvidenceDossierPlan`

### Validity / Feedback / Promotion

Owns global task validity, failure attribution, model-separation readiness, and controlled durable updates.

Existing objects:

- `pipeline_b_batch_report.json`
- `pipeline_b_batch_feedback_report.json`
- `pipeline_a_substrate_audit_report.json`
- `typed_resource_patch_proposal_report.json`
- `pipeline_b_eval_summary_report.json`
- `pipeline_b_eval_feedback_report.json`

New contracts:

- `GlobalTaskValidityReport`
- `RealWorldnessReport`
- `DifficultyProfile`
- `ModelSeparationProfile`
- `TaskVerifierReport`
- `FeedbackAttributionReport`
- `PromotionRecord`
- `RollbackRecord`

## Contract Drafts

### WorkflowEpisode

Purpose: preserve source-grounded workflow context around extracted skills.

Initial output files:

- `workflow_episode_proposals.json`
- `workflow_episode_proposal_report.json`

Minimum fields:

```json
{
  "workflow_episode_id": "wfep_...",
  "source_id": "source_...",
  "domain": "audit",
  "business_context": "internal control testing",
  "actor_role": "audit associate",
  "trigger_event": "control exception found",
  "input_artifacts": [],
  "steps": [],
  "motif_hints": [],
  "deliverable_type": "memo",
  "observed_constraints": [],
  "evidence_refs": [],
  "confidence": "low|medium|high",
  "review_status": "proposed"
}
```

Rules:

- Do not write episodes into `SkillRegistry/v3_skill_registry.json`.
- Derive V1 proposals from existing extraction artifacts, trace edges, motif hints, source metadata, and evidence spans.
- Preserve low-confidence and missing-source signals in the report.

### WorkflowArchetype

Purpose: describe recurring real-world workflow types without hard-coding task templates.

Initial output file:

- `SkillRegistry/v3_workflow_archetype_registry.experimental.json`

Minimum fields:

```json
{
  "workflow_archetype_id": "wfa_...",
  "name": "internal_control_exception_documentation",
  "domain": "audit",
  "typical_actor_roles": [],
  "trigger_events": [],
  "common_input_artifacts": [],
  "common_motifs": [],
  "common_deliverables": [],
  "typical_constraints": [],
  "source_episode_ids": [],
  "status": "experimental"
}
```

Rules:

- Start with 3 to 5 hand-written or semi-automatic archetypes.
- Do not make the sampler require archetypes in V1.
- Archetypes provide context, not fixed file/prompt/rubric templates.

### MotifGraphGrammar

Purpose: promote motifs from labels into role/resource/stage contracts.

Initial output file:

- `SkillRegistry/v3_motif_graph_grammar.experimental.json`

Start with:

- `policy_application`
- `fan_in_reconciliation`

Minimum fields:

```json
{
  "motif_grammar_id": "mgg_...",
  "motif_type": "policy_application",
  "required_roles": [],
  "optional_roles": [],
  "required_resource_types": [],
  "provided_resource_types": [],
  "expected_graph_shape": "chain|fan_in|fan_out|dag|constraint_graph",
  "execution_stage_template": [],
  "validation_constraints": [],
  "common_failure_modes": []
}
```

Rules:

- V1 sampler integration should report role coverage only.
- Missing grammar or missing roles should not block existing task generation.
- Batch feedback should aggregate missing roles and fallback reasons.

### TaskConstraintGraph

Purpose: describe task-internal relationships among files, evidence, policy clauses, skills, intermediate artifacts, deliverable sections, and validation constraints.

Initial output file:

- `task_constraint_graph_report.json`

Minimum fields:

```json
{
  "task_constraint_graph_id": "tcg_...",
  "nodes": [],
  "edges": [],
  "graph_shape": "chain|tree|dag|constraint_graph",
  "unsupported_required_nodes": [],
  "diagnostics": []
}
```

Rules:

- V1 can be derived from `reference_file_plan.json`, `evidence_index.json`, `teacher_input_manifest.json`, and `golden_run.json`.
- Constraint graphs may contain validation cycles, but execution plans must remain acyclic.
- Do not change rw-task export based on this report in V1.

### ExecutionPlanDAG

Purpose: make the candidate or GoldenRun solve order explicit and checkable.

Initial output file:

- `execution_plan_dag_report.json`

Minimum fields:

```json
{
  "execution_plan_id": "exec_...",
  "stages": [],
  "dag_valid": true,
  "topological_order": [],
  "missing_inputs": [],
  "validation_notes": []
}
```

Rules:

- V1 can be derived from TeacherRunner intermediate states and golden steps.
- A failed DAG check is diagnostic-only at first.
- Later quality gates may consume this report after it stabilizes.

### GlobalTaskValidityReport

Purpose: collect global task diagnostics without replacing the existing Pipeline B quality gate.

Initial output files:

- `global_task_validity_report.json`
- `real_worldness_report.json`
- `difficulty_profile_report.json`

Minimum fields:

```json
{
  "case_id": "case_...",
  "diagnostic_only": true,
  "real_worldness": {},
  "difficulty_profile": {},
  "task_constraint_graph": {},
  "execution_plan_dag": {},
  "findings": [],
  "recommended_next_layer": "pipeline_a|workflow_graph|package_generation|validity_feedback"
}
```

Rules:

- Do not change `candidate_ready`, `revise`, or `reject` decisions in V1.
- Do not call LLMs or external APIs in V1.
- The report should distinguish structure-complete-but-unrealistic cases from truly broken packages.

### EvidenceDossierPlan

Purpose: describe reference files as an evidence ecosystem, not just generated files.

Initial integration:

- Add optional dossier metadata to `reference_file_plan.json`.

Minimum fields:

```json
{
  "dossier_id": "dos_...",
  "business_context": "internal control exception review",
  "candidate_visible_files": [],
  "teacher_only_files": [],
  "file_roles": [],
  "cross_file_constraints": [],
  "distractor_items": [],
  "expected_evidence_paths": []
}
```

Rules:

- Do not rewrite `ReferenceFileGenerator` just to add this contract.
- Start with the current workbook plus policy document path.
- Represent noise, missing fields, version relations, and conflicts as metadata before generating complex file types.

### TaskVerifierReport

Purpose: reduce prompt/GoldenRun/rubric self-confirmation.

Initial output file:

- `task_verifier_report.json`

Minimum fields:

```json
{
  "verification_status": "diagnostic_only|blocking|revise|pass",
  "blocking_findings": [],
  "revise_findings": [],
  "warning_findings": [],
  "unsupported_conclusions": [],
  "rubric_visibility_issues": []
}
```

Rules:

- Deterministic by default.
- Do not modify GoldenRun or rubric.
- Do not gate quality in V1.

### PromotionRecord

Purpose: make durable state changes explicit, auditable, and reversible.

Initial output files:

- `promotion_proposals.json`
- `promotion_report.json`
- `rollback_record.json`

Minimum fields:

```json
{
  "promotion_id": "prom_...",
  "target_type": "typed_resource_patch|workflow_archetype|motif_grammar|source_quality_rule|transition_prior|registry_admission|readiness_status|sampler_rule",
  "source_report": "path/to/report.json",
  "target_path": "SkillRegistry/v3_skill_registry.json",
  "review_status": "proposed|approved|rejected|applied|rolled_back",
  "diff_summary": [],
  "rollback_record_id": null
}
```

Rules:

- Default command behavior should create proposals only.
- Any apply action must require an explicit flag.
- Task generation must never mutate registry or sampler state as a hidden side effect.
- Every apply must write enough information to support rollback.

## Initial Implementation Order

1. Keep this document and `pipeline_next_stage_global_plan.md` in sync.
2. Add Global Validity Report V1 as diagnostic-only output.
3. Add WorkflowEpisode Proposal V1 from existing Pipeline A artifacts.
4. Add experimental MotifGraphGrammar for `policy_application` and `fan_in_reconciliation`.
5. Add sampler role-coverage reporting while preserving old sampler behavior.
6. Add EvidenceDossierPlan metadata to the reference-file plan.
7. Add deterministic TaskVerifier diagnostics.
8. Add promotion/rollback proposal plumbing.

## Anti-Patterns

- Do not hide Pipeline A resource gaps inside Pipeline B fallbacks.
- Do not turn workflow archetypes into fixed task templates.
- Do not update `SkillRegistry/*.json` from task generation.
- Do not implement fake UCB or bandit behavior before comparable batch feedback exists.
- Do not treat draft rw-task smoke scores as final model-separation evidence.
