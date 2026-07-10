# Phase 11 Baseline - 2026-07-05

## Scope

This baseline freezes the current state of the Phase 11 candidate-ready closure effort after:

- the promotion-governance/dashboard governance work was completed,
- three reviewed canonical typed-resource promotions were applied to `SkillRegistry/v3_skill_registry.json`,
- the target Pipeline B case was rerun against the updated canonical registry,
- downstream batch feedback, substrate audit, typed-resource patch proposal, and dashboard aggregation were refreshed,
- a focused contract-layer fix was applied so deliverable requirements are explicitly projected into candidate-facing rubric coverage,
- dossier heuristics and teacher/rubric readiness propagation were tightened,
- the target case naturally crossed from `revise_only` into `candidate_ready`.

This document is a snapshot for Phase 11 execution, not a replacement for the global plan in `docs/architecture/pipeline_next_stage_global_plan.md`.

This document now serves two purposes:

1. preserve the original Phase 11 baseline inputs and repair sequence,
2. record the first confirmed `candidate_ready` milestone reached by that sequence.

## Baseline Inputs

- Canonical registry:
  - `SkillRegistry/v3_skill_registry.json`
- Canonical apply evidence:
  - `artifacts/pipeline_b/scratch/promotion_manager_canonical_apply_skill_e1c4dedc31/promotion_report.json`
  - `artifacts/pipeline_b/scratch/promotion_manager_canonical_apply_skill_e1c4dedc31/rollback_record.json`
  - `artifacts/pipeline_b/scratch/phase11_promotion_apply_skill_9149d84703/promotion_report.json`
  - `artifacts/pipeline_b/scratch/phase11_promotion_apply_skill_03116f26d2/promotion_report.json`
- Batch rerun after canonical apply:
  - `artifacts/pipeline_b/scratch/phase11_batch_rerun_after_canonical_apply/pipeline_b_batch_report.json`
- Batch feedback after canonical apply:
  - `artifacts/pipeline_b/scratch/phase11_batch_feedback_after_canonical_apply/pipeline_b_batch_feedback_report.json`
- Substrate audit after canonical apply:
  - `artifacts/pipeline_b/scratch/phase11_substrate_audit_after_canonical_apply/pipeline_a_substrate_audit_report.json`
- Typed-resource patch proposal after canonical apply:
  - `artifacts/pipeline_b/scratch/phase11_typed_resource_patch_after_canonical_apply/typed_resource_patch_proposal_report.json`
- Global dashboard after canonical apply:
  - `artifacts/pipeline_b/scratch/phase11_global_dashboard_after_canonical_apply/global_pipeline_dashboard_report.json`
- Contract-fix rerun:
  - `artifacts/pipeline_b/scratch/phase11_batch_rerun_after_contract_fix/pipeline_b_batch_report.json`
- Contract-fix dashboard:
  - `artifacts/pipeline_b/scratch/phase11_global_dashboard_after_contract_fix/global_pipeline_dashboard_report.json`
- Dossier-fix rerun:
  - `artifacts/pipeline_b/scratch/phase11_batch_rerun_after_dossier_fix/pipeline_b_batch_report.json`
- Teacher-fix rerun:
  - `artifacts/pipeline_b/scratch/phase11_batch_rerun_after_teacher_fix/pipeline_b_batch_report.json`
- Rubric-fix rerun:
  - `artifacts/pipeline_b/scratch/phase11_batch_rerun_after_rubric_fix/pipeline_b_batch_report.json`
- Final nonblocking-gap-fix rerun:
  - `artifacts/pipeline_b/scratch/phase11_batch_rerun_after_nonblocking_gap_fix/pipeline_b_batch_report.json`
- Final nonblocking-gap-fix feedback:
  - `artifacts/pipeline_b/scratch/phase11_batch_feedback_after_nonblocking_gap_fix/pipeline_b_batch_feedback_report.json`
- Final nonblocking-gap-fix dashboard:
  - `artifacts/pipeline_b/scratch/phase11_global_dashboard_after_nonblocking_gap_fix/global_pipeline_dashboard_report.json`
- Executed evaluation smoke already available:
  - `artifacts/pipeline_b/scratch/eval_orchestrator_exec_campaign_smoke_v3/evaluation_orchestration_report.json`

## Applied Canonical Promotions

Applied promotions:

- `promotion_id = promotion_db5935e143fb`
- `source_promotion_key = promotion_source_9677dfcbc9d7`
- target skill:
  - `skill_e1c4dedc31`
  - `Apply Foreign Tax Withholding to Revenue`
- `promotion_id = promotion_8ed905c65711`
- `source_promotion_key = promotion_source_d44cb339b9aa`
- target skill:
  - `skill_9149d84703`
  - `Reconcile Source Totals to Report Line Items`
- `promotion_id = promotion_c9ecfe2cb4d9`
- `source_promotion_key = promotion_source_d01bc99d8287`
- target skill:
  - `skill_03116f26d2`
  - `Consolidate Period Financial Data from Multiple Sources`

Applied typed-resource additions in canonical registry include:

- required resources:
  - `MonetaryAmount` / `Gross revenue by country`
  - `PolicyRule` / `Withholding tax rates per country`
- provided resources:
  - `MonetaryAmount` / `Net revenue after withholding`
  - `MonetaryAmount` / `Withholding tax amount per country`
- reconciliation and consolidation resources for:
  - source transaction datasets
  - previous-period workbooks
  - account-mapping tables
  - reconciled line items
  - variance and supporting-schedule style outputs

Post-apply verification now shows:

- the first three reviewed sampled-skill promotions are aligned with the canonical registry,
- repeated proposal generation drops already-applied patches to `no_effective_diff` when re-proposed,
- the only remaining sampled-skill patch candidate is low-confidence and `needs_source_evidence`, not directly apply-eligible.

## Primary Phase 11 Target Case

Current target case:

- `pipeline_b_batch_01_evidence_to_deliverable`

Why this remained the Phase 11 candidate-ready target:

1. It stayed structurally alive through the repair loop instead of collapsing to `reject`.
2. It improved after a real canonical promotion, which means substrate repair was having visible downstream effect.
3. Even before final closure it already had:
   - `real_worldness_score = 1.0`
   - `execution_dag_valid = true`
   - `verifier_blocking_count = 0`
4. It already supports executed evaluation as diagnostic evidence, so later readiness changes can be inspected without first rebuilding the eval stack.

## Observed Improvement Across The Promotion Sequence

Most important delta:

- before canonical typed-resource apply:
  - `subgraph_confidence = low_due_to_resource_fallback`
- after the first canonical typed-resource apply:
  - `subgraph_confidence = medium_with_pipeline_a_gaps`

This is the clearest current proof that Phase 8 promotion governance is not just bookkeeping. A reviewed typed-resource promotion can improve Pipeline B sampling quality without changing gate truth or silently mutating other priors.

Additional observation after the second and third sampled-skill applies:

- `subgraph_confidence` stayed at `medium_with_pipeline_a_gaps`
- `quality_decision` stayed `revise`
- `package_readiness` stayed `revise_only`

Interpretation:

- typed-resource promotion was necessary and materially helpful,
- but it is no longer the only active bottleneck,
- and continuing to chase low-confidence substrate patches without new evidence is unlikely to produce the first `candidate_ready` package on its own.

## Candidate-Ready Milestone

The target case is now `candidate_ready`.

Confirmed state from the final refreshed rerun and dashboard:

- `quality_decision = candidate_ready`
- `package_readiness = candidate_ready`
- `export_decision = exported`
- `validation_status = candidate_ready_compatible`
- `teacher_input_validation_report = teacher_ready`
- `teacher_runner_report = teacher_ready`
- `training_annotation_report = annotation_ready`
- `rubric_report = rubric_ready`
- `verifier_status = pass`
- `pipeline_b_quality_report.decision.reason_codes = []`
- `pipeline_b_batch_feedback_report.findings = []`
- dashboard readiness:
  - `candidate_ready_count = 1`
  - `usable_eval_evidence_case_count = 1`
  - `orchestration_with_profile_count = 1`

This is the first confirmed Phase 11 success condition:

- a package reached `candidate_ready`,
- without lowering gate thresholds,
- without suppressing verifier findings,
- and while keeping residual Pipeline A/workflow weaknesses visible in diagnostics rather than smuggling them into hidden gate bypasses.

What changed materially in the last repair steps:

1. deliverable requirements were projected into candidate-facing rubric coverage,
2. dossier heuristics stopped inventing overly aggressive missing-attachment / manager-note / stale-version placeholders for this simple case,
3. diagnostic-only teacher states stopped being treated as incomplete execution states,
4. rubric readiness stopped inheriting non-candidate diagnostic partials,
5. teacher-input and teacher unresolved-gap handling stopped treating provisional subgraph confidence and Pipeline A caution notes as package-blocking gaps.

## Residual Root-Cause Ordering After Candidate-Ready

The refreshed dashboard and substrate audit now support the following *post-success* ordering.

### 1. Pipeline A substrate remains the top repair layer

Evidence:

- `missing_typed_resource_skill_count = 1`
- `transition_gap_skill_count = 3`
- `manual_resource_patch_candidate_count = 1`
- `new_source_evidence_candidate_count = 1`

Interpretation:

- the low-risk typed-resource patch surface has mostly been exhausted for the currently sampled skills,
- the remaining missing skill is blocked by low-confidence patch quality plus sparse source support,
- and transition evidence is still sparse/local-only.

### 2. Deliverable-to-rubric alignment has been repaired for the current target case

Evidence:

- after the contract-layer fix:
  - `verifier_status = pass`
  - `verifier_reason_coverage = {}`

Interpretation:

- the previous `deliverable_requirement_undercovered` issue was a real contract-generation miss,
- it was fixed by explicitly projecting deliverable requirements into the candidate-facing rubric wording,
- and verifier is no longer the main blocker for this case.

### 3. Workflow conditioning is still weak

Evidence:

- `workflow_context_fit = low`
- focus area:
  - `focus_workflow_graph_structure`

Interpretation:

- the case is no longer in the worst substrate confidence state,
- but the selected subgraph is still under-structured relative to the intended workflow layer.

### 4. Evaluation evidence is closed only at diagnostic strength

Evidence:

- `executed_orchestration_count = 1`
- `usable_eval_evidence_case_count = 1`
- `draft_eval_only_case_count = 1`
- `model_separation_profile.evaluation_status = not_enough_data`

Interpretation:

- the executed evaluation chain is closed,
- but the current evidence is still draft-diagnostic rather than formal comparison-grade evidence,
- so the next evaluation goal is repeated evidence collection or stronger-ready cases, not premature model-separation claims.

## Phase 11 Baseline Conclusion

As of 2026-07-05, the project has crossed the first major Phase 11 threshold:

- governance and promotion plumbing are working,
- three reviewed canonical typed-resource promotions have been applied safely,
- those promotions produced a measurable downstream sampler improvement,
- contract-layer and teacher-readiness fixes converted the surviving target case into the first true `candidate_ready` package,
- the remaining work is no longer "make one case pass" but "stabilize and widen this success without regressing substrate governance".

## Next Recommended Work Order

1. Preserve the current candidate-ready closure rules; do not reintroduce dossier over-assertion or teacher-readiness over-blocking.
2. The first multi-case regression has now completed and reached a stronger result than expected:
   - `artifacts/pipeline_b/scratch/phase11_batch_regression_3case_policy_fix_v2/`
   - `candidate_ready_count = 3`
   - `verifier_status_counts.pass = 3`
3. Treat `skill_21b64a3c34` as a new-source-evidence problem, not an immediately applyable registry patch.
4. Keep substrate/workflow issues visible:
   - `workflow_context_fit = low`
   - `subgraph_confidence = medium_with_pipeline_a_gaps`
   - remaining transition/support gaps in the sampled skills
5. Only after repeated candidate-ready or near-candidate-ready cases emerge should executed eval evidence be treated as more than draft diagnostic support.
6. The next stage should shift from Phase 11 closure to post-closure hardening:
   - repeated executed evaluation evidence on candidate-ready cases,
   - typed-resource/source-evidence strengthening for the still-weak sampled substrate,
   - role-filling confidence improvement rather than further gate relaxation.

## Guardrails

- Do not lower `quality_gate` thresholds to force a `candidate_ready` result.
- Do not silently mutate transition priors or sampler weights.
- Do not treat current executed eval evidence as formal model-separation truth.
- Keep `.env` out of staging, commits, logs, and generated reports.
