# Phase 16 Execution Reassessment - 2026-07-10

> Historical: this document records the correction from a direct-provider helper to the existing rw-task path. The authoritative final Phase 16 outcome is `docs/handoffs/PHASE_16_COMPLETION_2026-07-10.md`.

## Decision

Phase 16 should not continue through a direct provider-call evaluator. The temporary `v3_phase16_scoped_external_eval` path has been removed because it bypassed the established task-package / rw-task-compatible clean eval workflow.

Current Phase 16 status:

```text
phase16_status = minimum_success_proven_expand_to_4case_next
default_generator_change_allowed = false
llm_primary_truth_used = false
direct_provider_evaluator_allowed = false
minimum_phase16_success_proven = true
```

## What Was Removed

Removed files:

```text
src/task_generator/v3_phase16_scoped_external_eval.py
Test/run_v3_phase16_scoped_external_eval.py
artifacts/phase16/scoped_external_eval/
```

Reason:

- It called OpenAI-compatible providers directly from a Phase16 helper.
- It constructed a JSON-only candidate prompt instead of using full task packages.
- It did not route through rw-task export / eval-prep / `run_v3_rw_task_eval_runner.py`.
- It created a parallel grading path rather than reusing the Phase15 external eval readiness, runbook, result-builder, importer, and permitted-bundle pattern.

## What Can Stay

The report-first Phase16 artifacts can still be useful as design and pre-eval evidence, provided they are not treated as completed clean eval:

```text
docs/architecture/phase16_evidence_to_deliverable_redesign_plan.md
src/task_generator/v3_phase16_evidence_to_deliverable_redesign.py
src/task_generator/v3_phase16_reform_autopsy_deepener.py
src/task_generator/v3_evidence_to_deliverable_alignment_v2.py
src/task_generator/v3_evidence_to_deliverable_redesign_v2.py
src/task_generator/v3_phase16_clean_eval_gate.py
Test/run_v3_phase16_*.py, except the removed direct evaluator
Test/run_v3_evidence_to_deliverable_*.py
artifacts/phase16/*, except the removed direct evaluator outputs
```

Interpretation:

- `contract_v2`, alignment, structural review, and negative controls are pre-eval diagnostics.
- `phase16_clean_eval_gate` is an import/readiness gate only.
- `phase16_completion_audit_report.json` must remain `safe_to_mark_phase16_complete = false` until real clean paired eval results are imported.

## New Pipeline-Aligned Prep Evidence

The Phase16 clean-eval preparation path now exists and routes through the full task package / rw-task prep chain:

```text
src/task_generator/v3_phase16_production_eval_prep.py
Test/run_v3_phase16_production_eval_prep.py
src/task_generator/v3_phase16_external_eval_result_builder.py
Test/run_v3_phase16_external_eval_result_builder.py
```

Current generated evidence:

```text
artifacts/phase16/production_eval_prep/phase16_production_experiment_report.json
artifacts/phase16/production_eval_prep/phase16_clean_eval_queue_report.json
artifacts/phase16/production_eval_prep/phase16_external_eval_runbook.json
artifacts/phase16/production_eval_prep/phase16_external_eval_results_template.json
artifacts/phase16/production_eval_prep/run_phase16_clean_eval.ps1
artifacts/phase16/production_eval_prep/phase16_external_eval_results.sanitized.json
artifacts/phase16/production_eval_prep/result_builder/phase16_external_eval_result_builder_report.json
```

Current structural prep result:

```text
arms = 3 / 3 executed
production_cases_per_arm = 3
selected_clean_eval_cases = pipeline_b_batch_01_evidence_to_deliverable, pipeline_b_batch_03_evidence_to_deliverable
candidate_ready_by_arm = 3 / 3 for baseline_deterministic
candidate_ready_by_arm = 3 / 3 for contract_v2_only
candidate_ready_by_arm = 3 / 3 for contract_v2_plus_productive_complexity
clean_eval_queue_items = 12
prepared_queue_items = 12
blocked_queue_items = 0
two_case_clean_eval_structurally_ready = true
runbook_blocking_reasons = []
```

The corrected rw-task clean eval has now completed and the sanitized result builder produced `12 / 12` completed records. The Phase16 clean eval gate accepted the import:

```text
two_case_clean_eval_proven = true
record_count = 12
expected_record_count = 12
missing_records = []
malformed_records = []
```

Actual two-case signal:

```text
contract_v2_only.mean_strong_score_delta = 0.07930965144441399
contract_v2_only.mean_weak_score_delta = -0.014813911967659271
contract_v2_only.mean_gap_delta = 0.09412356341207326
contract_v2_only.positive_gap_delta_case_count = 2

contract_v2_plus_productive_complexity.mean_strong_score_delta = 0.07253860263679782
contract_v2_plus_productive_complexity.mean_weak_score_delta = -0.11422497652879783
contract_v2_plus_productive_complexity.mean_gap_delta = 0.18676357916559566
contract_v2_plus_productive_complexity.positive_gap_delta_case_count = 2
```

## Required Execution Path

Use existing conda environments:

```powershell
cd E:\THU\2026Spring\SRT\TaskGenerator
D:\miniconda3\envs\taskgenerator\python.exe ...
D:\miniconda3\envs\real-world-task\python.exe ...
```

Do not use bare `python`.

Phase16 clean eval must follow this shape:

1. Build redesign variants as full Pipeline B task packages, not JSON-only prompt packages.
2. Route each selected case/arm through reference files, GoldenRun, training annotation, rubric, quality gate, package assembler, rw-task exporter, validator, and eval-prep.
3. Use the existing rw-task eval runner path for execution.
4. Build sanitized result records from run outputs.
5. Import those records through the Phase16 clean eval gate.
6. Only then decide whether Phase16.7 is proven and whether Phase16.8 four-case expansion is allowed.

## Existing Phase15 Pattern To Reuse

Relevant existing modules:

```text
src/task_generator/v3_phase15_clean_eval_queue.py
src/task_generator/v3_phase15_external_eval_readiness.py
src/task_generator/v3_phase15_external_eval_runbook.py
src/task_generator/v3_phase15_permitted_eval_bundle.py
src/task_generator/v3_phase15_external_eval_result_builder.py
src/task_generator/v3_phase15_external_eval_importer.py
```

Relevant existing runners:

```text
Test/run_v3_phase15_clean_eval_queue.py
Test/run_v3_phase15_external_eval_readiness.py
Test/run_v3_phase15_external_eval_runbook.py
Test/run_v3_phase15_permitted_eval_bundle.py
Test/run_v3_phase15_external_eval_result_builder.py
Test/run_v3_phase15_external_eval_importer.py
Test/run_v3_rw_task_eval_runner.py
```

## Next Implementation Slice

1. Convert `contract_v2_only` and `contract_v2_plus_productive_complexity` from Phase16 package-description JSON into complete Pipeline B package outputs for two selected cases.
2. Add a Phase16 clean eval queue/readiness/runbook layer by adapting the Phase15 pattern rather than adding model calls.
3. Generate a permitted-eval bundle for the selected two-case paired run.
4. Execute only after explicit scoped authorization and only through the generated runbook.
5. Import sanitized results into `artifacts/phase16/clean_eval_gate/phase16_two_case_clean_eval_import_report.json`.

## Current Blocking Gap

Phase16 minimum success is now proven:

```text
blocking_gap = null
safe_to_mark_phase16_complete = true
next_required_scope = governed 4-case expansion before any default promotion
```
