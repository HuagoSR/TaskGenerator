# Phase 14 Scope

## Purpose

Phase 14 establishes the calibration boundary for GDPVal and the first comparison baseline for TaskGenerator generated tasks.

## Fixed Uses

- GDPVal mirror use: `eval_calibration_only`
- Generated release use: `generated_training_candidate`
- LLM mode: `shadow_or_candidate_diagnostics_only`

## In Scope

- GDPVal finance/audit/accounting/compliance-like calibration subset
- Current TaskGenerator finance/audit reviewed release tasks
- Current deterministic production pipeline and rw-task diagnostic path
- LLM shadow and candidate diagnostics only

## Out Of Scope

- Rewriting GDPVal into training tasks
- Running all GDPVal tasks as a single first-pass campaign
- Benchmark-grade model separation claims
- LLM primary task generation or primary rubric truth
- UCB or bandit-driven sampler changes
- Cross-domain expansion and new file ecosystems

## Baseline Comparison Assets

- `finance_audit_mvp_v0_1_pilot8_diversity_final_reviewed_strict` from `phase13_pilot8_diversity_final_smoke` with `8` tasks

## Phase 14.3 GDPVal rw-task Diagnostic Baseline

Phase 14.3 mirrors the 10 selected GDPVal calibration tasks into a separate rw-task input package. This is a diagnostic baseline only: it does not write the skill registry, does not create release rows, and does not put GDPVal tasks into the TaskGenerator training pool.

Main entry point:

```bash
python Test/run_v3_gdpval_rw_task_eval_adapter.py --mode dry-run
```

What this does:

- reads `artifacts/phase14/gdpval_subset/gdpval_finance_audit_subset_manifest.json`
- copies each selected task's prompt, reference files, metadata, source hashes, and calibration rubric into `artifacts/phase14/gdpval_eval_baseline/eval_input/`
- writes command previews for `gpt-5.4-pro` and `gpt-4o-mini`
- writes reports without calling external models

Main reports:

- `artifacts/phase14/gdpval_eval_baseline/gdpval_eval_campaign_report.json`
- `artifacts/phase14/gdpval_eval_baseline/gdpval_model_gap_profile.json`
- `artifacts/phase14/gdpval_eval_baseline/gdpval_eval_failure_report.json`

To run the real diagnostic campaign, use:

```bash
python Test/run_v3_gdpval_rw_task_eval_adapter.py --mode execute --run-eval --model gpt-5.4-pro --model gpt-4o-mini --workers 1
```

Execution loads `.env` into the subprocess environment but does not write secret values into reports. Model outputs and grading outputs stay under `artifacts/phase14/gdpval_eval_baseline/model_runs/`.

`--model` names the model being tested on the task. `--grader-model` names the model used by `bench_standalone.grade_deliverables` to score the resulting deliverable, and defaults to `gpt-5.4-pro` because the current `gpt-4o-mini` grading path can return empty JSON completions through the configured API gateway. The adapter also runs rw-task through `task_generator.v3_rw_task_stirrup_entrypoint`, which keeps the underlying `bench_standalone.stirrup_batch` behavior but lowers the agent completion-token cap to 16000 by default so `gpt-4o-mini` requests are accepted.

GDPVal deliverable files are not copied into the rw-task input package. The input `dataset_row.json` leaves `deliverable_files` empty before model execution; original GDPVal expected deliverable names are retained only as metadata under `extra.expected_deliverable_files_metadata_only`.

## Phase 14.3 Five-Case Executed Baseline

The first executed 5-case GDPVal diagnostic baseline is stored at:

- `artifacts/phase14/gdpval_eval_baseline_5case_execute/gdpval_eval_campaign_report.json`
- `artifacts/phase14/gdpval_eval_baseline_5case_execute/gdpval_model_gap_profile.json`
- `artifacts/phase14/gdpval_eval_baseline_5case_execute/gdpval_eval_failure_report.json`

The run used the first five selected GDPVal calibration tasks, `gpt-5.4-pro` and `gpt-4o-mini` as evaluated models, and `gpt-5.4-pro` as grader. It prepared all 5 tasks, blocked 0 tasks, and attempted both model runs.

Important timeout boundary:

- `--case-timeout-seconds 7200` controls the outer per-case wrapper timeout.
- `--sandbox-timeout-seconds 3600` is the practical E2B sandbox cap observed in this campaign.
- Values above 3600 for the sandbox timeout are rejected by E2B with "Timeout cannot be greater than 1 hours".

Representative command:

```bash
python Test/run_v3_gdpval_rw_task_eval_adapter.py --mode execute --run-eval --task-limit 5 --model gpt-5.4-pro --model gpt-4o-mini --workers 1 --output-dir artifacts\phase14\gdpval_eval_baseline_5case_execute --overwrite --command-timeout-seconds 86400 --case-timeout-seconds 7200 --sandbox-timeout-seconds 3600
```

Observed result:

- `prepared_task_count = 5`
- `blocked_task_count = 0`
- `executed_model_count = 2`
- `gpt-5.4-pro`: execution completed, grading produced 2 completed task scores and 3 task-level grading failures
- `gpt-4o-mini`: execution completed, grading produced 4 completed task scores and 1 task-level grading failure
- raw batch `usable_task_count = 1` for two-model gap analysis
- failure report count is 6, including 2 model-level grading command failures and 4 task-level grading failures

The raw batch is useful toolchain evidence, but it is not a clean model-separation benchmark. Its apparent `gpt-5.4-pro = 0.0` versus `gpt-4o-mini = 0.23728813559322035` finding for `ee09d943-5a11-430a-b7a2-971b4e9b01b5` is superseded by the single-case repair workflow below, because later inspection showed that missing deliverables after sandbox timeout had been counted like usable zero-score outputs.

## Phase 14.3 Single-Case Progressive Evaluation

The current Phase 14.3 evaluation path is now single-case first. Each task should be run or repaired independently, then diagnosed before moving to the next task.

Main single-case entry point:

```bash
python Test/run_v3_gdpval_single_case_eval.py --run-id case_7b08 --task-id 7b08cd4d-df60-41ae-9102-8aaa49306ba2 --mode execute --model gpt-5.4-pro --model gpt-4o-mini --run-eval
```

For already-completed raw runs, first inspect and sanitize without rerunning the E2B agent:

```bash
python Test/run_v3_gdpval_single_case_eval.py --run-id inspect_7b08 --task-id 7b08cd4d-df60-41ae-9102-8aaa49306ba2 --mode diagnose-existing --source-run artifacts\phase14\gdpval_eval_baseline_5case_execute
```

Then run sanitized regrade only:

```bash
python Test/run_v3_gdpval_single_case_eval.py --run-id regrade_7b08 --task-id 7b08cd4d-df60-41ae-9102-8aaa49306ba2 --mode execute-regrade --source-run artifacts\phase14\gdpval_eval_baseline_5case_execute --run-eval
```

The single-case runner writes:

- `single_case_report.json`
- `deliverable_diagnostic_report.json`
- `sanitized_regrade_report.json`
- `case_gap_profile.json`
- `continue_decision.json`

Sanitized regrade keeps only candidate deliverables such as `.xlsx`, `.pptx`, `.docx`, `.pdf`, and `.csv`; it excludes helper scripts and scratch files. Archive deliverables such as `.tar.gz` are unpacked and scored only if a supported deliverable file is found inside.

First repaired result:

- `artifacts/phase14/gdpval_single_case_runs/regrade_7b08/`
- task: `7b08cd4d-df60-41ae-9102-8aaa49306ba2`
- decision: `ready_for_next_case`
- `gpt-5.4-pro`: `78 / 89`, score ratio `0.8764044943820225`
- `gpt-4o-mini`: `8 / 89`, score ratio `0.0898876404494382`
- score gap: `0.7865168539325843`

This repaired result is the preferred interpretation for the Fall Music Tour P&L case. It shows that the earlier batch failure was mainly a grading/package hygiene problem, not evidence that the weaker model outperformed the stronger model.

Model fallback probes now exist at `Test/probe_v3_model_provider.py`. As of this pass, Tuzi `gemini-3-pro-preview` and DeepSeek official `deepseek-v4-pro` both responded to small chat and JSON probes. Probe reports are stored under `artifacts/phase14/model_provider_probes/` and do not contain secret values.

## Phase 14.3 Clean Single-Case Baseline

The clean Phase 14.3 baseline is now assembled from repaired single-case reports rather than from the raw 5-case batch summary.

Main entry point:

```bash
python Test/run_v3_gdpval_clean_baseline.py --task-limit 5
```

Outputs:

- `artifacts/phase14/gdpval_clean_baseline/gdpval_clean_baseline_report.json`
- `artifacts/phase14/gdpval_clean_baseline/gdpval_clean_gap_profile.json`
- `artifacts/phase14/gdpval_clean_baseline/gdpval_clean_failure_report.json`

Current clean result:

- `task_count = 5`
- `usable_task_count = 4`
- `needs_model_rerun_count = 1`
- usable tasks: `83d10b06-26d1-4636-a32c-23f92c57f30b`, `7b08cd4d-df60-41ae-9102-8aaa49306ba2`, `7d7fc9a7-21a7-4b83-906f-416dea5ad04f`, `87da214f-fd92-4c58-9854-f4d0d10adce0`
- blocked task: `ee09d943-5a11-430a-b7a2-971b4e9b01b5`, because the `gpt-5.4-pro` side has no usable deliverable
- clean gap buckets: 3 high-gap tasks, 1 medium-gap task, 1 unusable task

This clean baseline is the preferred Phase 14.3 input for model-gap analysis and for Phase 14.4 / 14.5. Missing-deliverable zero scores must not be used as model-quality evidence.

## Phase 14.4A / 14.5 Route Correction

The current 4 usable clean paired comparisons are enough to guide the next slice, but not enough to justify a fixed scoring formula. Phase 14 therefore stays empirical and observational:

- do gap autopsy before adding a weighted score
- treat `83d10` as a useful low/medium-gap counterexample, not as a failed sample
- keep `ee09` as a runnability / friction case until the strong-model side has a usable deliverable
- separate productive complexity from frictional complexity
- expand by stratified clean paired comparisons, not by running a large batch blindly

Next expected outputs:

- `artifacts/phase14/gdpval_gap_autopsy/gdpval_gap_autopsy_report.json`
- `artifacts/phase14/gdpval_gap_autopsy/gdpval_gap_hypothesis_ledger.json`
- `artifacts/phase14/gdpval_runnable_slice_v2_manifest.json`
- `artifacts/phase14/generated_vs_gdpval_gap_probe.json`

`GoodTaskProfiler V1` should be implemented as `GoodTaskProfiler-Observational V1`: it records profiles, gaps, runtime, failure taxonomy, and hypotheses, but it must not emit a weighted `GoodTaskScore`. A scored profiler should wait until there are at least 12 clean paired comparisons and both GDPVal and generated-task samples have comparable diagnostics.

## Phase 14.4A Gap Autopsy Implemented

Main entry point:

```bash
python Test/run_v3_gdpval_gap_autopsy.py
```

Outputs:

- `artifacts/phase14/gdpval_gap_autopsy/gdpval_gap_autopsy_report.json`
- `artifacts/phase14/gdpval_gap_autopsy/gdpval_gap_hypothesis_ledger.json`
- per-case autopsies under `artifacts/phase14/gdpval_gap_autopsy/gdpval_gap_autopsy_cases/<case_slug>/gap_autopsy.json`

Current smoke result:

- `task_count = 5`
- `usable_task_count = 4`
- `gap_band_counts = {"high": 3, "medium": 1, "unusable": 1}`

The report extracts top rubric-gap items, productive complexity signals, frictional complexity signals, and H1-H6 hypothesis evidence. It remains calibration-only and does not score tasks with a weighted formula.

## Phase 14.4B Stratified Runnable Slice

Main entry point:

```bash
python Test/run_v3_gdpval_runnable_slice.py
```

Outputs:

- `artifacts/phase14/gdpval_runnable_slice_v2_manifest.json`
- `artifacts/phase14/gdpval_next_eval_queue.json`
- `artifacts/phase14/taskgenerator_comparison_eval_plan.json`

Current smoke result:

- current GDPVal clean seed cases: `4`
- GDPVal holdout cases: `1`
- next GDPVal eval queue: `4`
- TaskGenerator comparison candidates: `4`
- target total clean paired comparisons: `12`

The next GDPVal queue currently prioritizes `58ac`, `b39a`, `4de6`, and `c657`. `ee09` remains a `runnability_friction_holdout` and is not counted as clean gap evidence. The TaskGenerator comparison plan selects one Phase 13 reviewed strict release task from each motif: `evidence_to_deliverable`, `cross_check_validation`, `fan_in_reconciliation`, and `policy_application`.

## Phase 14.5 GoodTaskProfiler-Observational V1

Main entry point:

```bash
python Test/run_v3_good_task_profiler_observational.py
```

Outputs:

- `artifacts/phase14/good_task_profiler_observational/good_task_profiler_observational_report.json`
- `artifacts/phase14/good_task_profiler_observational/good_task_observational_profiles.jsonl`
- `artifacts/phase14/good_task_profiler_observational/good_task_observational_distribution_report.json`

Current smoke result:

- `profile_count = 13`
- `gdpval_profile_count = 9`
- `taskgenerator_profile_count = 4`
- `evaluated_profile_count = 4`
- `pending_eval_profile_count = 9`
- `weighted_good_task_score_emitted = false`

The profiler records evidence dimensions only: model gap, runnability, grading status, productive/frictional complexity, evidence closure, workflow realism, training value, evaluation stability, format-noise risk, tool-failure risk, and hypothesis evidence. It does not emit `GoodTaskScore` or any weighted total score.

## Phase 14.6 Generated-vs-GDPVal Comparison V1

Main entry point:

```bash
python Test/run_v3_generated_vs_gdpval_comparison.py
```

Outputs:

- `artifacts/phase14/generated_vs_gdpval/generated_vs_gdpval_similarity_report.json`
- `artifacts/phase14/generated_vs_gdpval/generated_vs_gdpval_gap_report.json`
- `artifacts/phase14/generated_vs_gdpval/generated_vs_gdpval_quality_matrix.json`
- `artifacts/phase14/generated_vs_gdpval/generated_task_improvement_recommendations.json`

Current smoke result:

- `gdpval_profile_count = 9`
- `generated_profile_count = 4`
- `gdpval_clean_eval_count = 4`
- `generated_clean_eval_count = 4`
- `comparison_readiness = clean_pair_comparison_available`
- `blocked_reason = null`
- GDPVal gap bands: `3 high`, `1 medium`
- TaskGenerator generated gap bands: `1 high`, `2 medium`, `1 low`

This comparison now has the first clean paired generated-task evidence. It is still diagnostic-only and not benchmark-grade: the generated slice uses `gemini-3-pro-preview` as the alternate strong model and `gpt-4o-mini` as the weak model, while the GDPVal clean slice used the earlier repaired `gpt-5.4-pro` / `gpt-4o-mini` baseline. Do not emit a weighted GoodTaskScore from this evidence.

## Phase 14.6B Generated Task Comparison Eval Prep

Main entry point:

```bash
python Test/run_v3_generated_task_comparison_eval.py --mode dry-run --overwrite
```

Outputs:

- `artifacts/phase14/generated_task_comparison_eval/generated_task_comparison_eval_report.json`
- `artifacts/phase14/generated_task_comparison_eval/generated_task_comparison_failure_report.json`
- `artifacts/phase14/generated_task_comparison_eval/generated_task_comparison_command_preview.json`
- per-model eval input directories under `artifacts/phase14/generated_task_comparison_eval/eval_inputs/`

Current dry-run smoke result:

- selected TaskGenerator comparison tasks: `4`
- models: `2`
- task-model attempts: `8`
- prepared: `8`
- dry-run ready: `8`
- blocked / failed / timeout: `0`

This layer validates the selected Phase 13 reviewed strict release tasks, prepares rw-task input packages, and records per-model command previews. It does not call external models in dry-run mode. Real execution must be explicit with `--mode execute --run-eval`.

The current clean generated-task comparison used single-task runs with `gemini-3-pro-preview` versus `gpt-4o-mini`, graded by `gpt-5.4-pro`. Each task was executed in its own output directory, then merged with:

```bash
python Test/run_v3_generated_task_eval_summary.py --eval-report-path <case01_report> --eval-report-path <case02_report> --eval-report-path <case03_report> --eval-report-path <case04_report> --strong-model gemini-3-pro-preview --weak-model gpt-4o-mini
```

Current executed summary result:

- generated tasks: `4`
- model records: `8`
- completed model scores: `8`
- clean generated pairs: `4`
- blocked generated pairs: `0`
- generated task gaps:
  - `pipeline_b_batch_01_evidence_to_deliverable`: `0.0189`
  - `pipeline_b_batch_02_cross_check_validation`: `0.3846`
  - `pipeline_b_batch_03_fan_in_reconciliation`: `0.6909`
  - `pipeline_b_batch_04_policy_application`: `0.4127`

Summary outputs:

- `artifacts/phase14/generated_task_comparison_eval_summary/generated_task_eval_summary_report.json`
- `artifacts/phase14/generated_task_comparison_eval_summary/generated_task_gap_profile.json`

## Phase 14.7A LLM Shadow Prepare Layer

Main entry points:

```bash
python Test/run_v3_llm_shadow_goldenrun.py
python Test/run_v3_llm_shadow_rubric.py
python Test/run_v3_llm_realism_critic.py
python Test/run_v3_llm_reference_narrative_suggestion.py
```

Implemented modules:

- `src/task_generator/v3_llm_shadow_common.py`
- `src/task_generator/v3_llm_shadow_goldenrun.py`
- `src/task_generator/v3_llm_shadow_rubric.py`
- `src/task_generator/v3_llm_realism_critic.py`
- `src/task_generator/v3_llm_reference_narrative_suggestion.py`

Outputs:

- `artifacts/phase14/llm_shadow/llm_goldenrun_shadow_batch_report.json`
- `artifacts/phase14/llm_shadow/llm_rubric_shadow_batch_report.json`
- `artifacts/phase14/llm_shadow/llm_realism_critic_batch_report.json`
- `artifacts/phase14/llm_shadow/llm_reference_narrative_suggestion_batch_report.json`
- per-task shadow prompt packages and comparison shells under `artifacts/phase14/llm_shadow/<shadow_kind>/<task_id>/`

Current prepare smoke result:

- GoldenRun shadow packages: `5 / 5` prepared and executed
- Rubric shadow packages: `5 / 5` prepared and executed
- Realism critic packages: `5 / 5` prepared and executed
- Reference narrative packages: `5 / 5` prepared and executed

The prepare layer is still separate from execution, but Phase 14 now also has executed shadow outputs. Metrics are diagnostic-only and must be reviewed before any LLM Candidate Mode promotion.

## Phase 14.8 LLM Impact Evaluation Shell

Main entry point:

```bash
python Test/run_v3_llm_impact_evaluation.py
```

Outputs:

- `artifacts/phase14/llm_impact/llm_impact_evaluation_report.json`
- `artifacts/phase14/llm_impact/llm_shadow_failure_taxonomy.json`
- `artifacts/phase14/llm_impact/llm_adoption_recommendation_report.json`

Current smoke result:

- shadow kinds: `4`
- prepared task shadows: `20`
- awaiting LLM output: `0`
- completed metrics: `20`
- impact readiness: `ready_for_impact_analysis`
- adoption recommendation: `review_shadow_metrics_before_candidate_mode`

This report explicitly separates shadow execution from adoption. The evidence is now complete enough for impact review, but it does not by itself prove that an LLM insertion point has reliable positive value.

## Phase 14.9 GoodTask Dashboard

Main entry point:

```bash
python Test/run_v3_good_task_dashboard.py
```

Outputs:

- `artifacts/phase14/good_task_dashboard/good_task_dashboard_report.json`
- `artifacts/phase14/good_task_dashboard/good_task_dashboard_summary.json`

Current smoke result:

- `overall_status = ready_for_phase14_postmortem`
- `phase14_readiness = partial_diagnostic_dashboard_ready`
- sections: `4`
- `weighted_good_task_score_emitted = false`
- primary blockers: `[]`

The dashboard is diagnostic-only. It can explain the current evidence state and next actions, but it still does not emit a weighted GoodTaskScore. LLM Candidate Mode remains a Phase 15 review decision, not an automatic Phase 14 output.

## Phase 14.10 Postmortem And Phase 15 Decision

Main entry point:

```bash
python Test/run_v3_phase14_postmortem.py
```

Outputs:

- `artifacts/phase14/postmortem/phase14_postmortem_report.json`
- `docs/handoffs/PHASE_14_GDPTASK_CALIBRATION_SUCCESS_2026-07-08.md`

Current postmortem decision:

- `phase14_decision = success`
- `phase15_recommendation = phase15_candidate_mode_or_generator_reform_review`

Minimum success criteria currently met:

- GDPVal finance/audit subset and calibration boundary exist.
- At least `4` GDPVal clean paired comparisons are usable for gap analysis.
- Gap autopsy and hypothesis ledger exist.
- GoodTaskProfiler and dashboard can represent GDPVal and TaskGenerator tasks without a weighted score.
- The 12 clean-pair target is met.
- LLM shadow outputs and impact metrics are complete enough for human review.

Current clean-pair evidence:

- GDPVal clean paired comparisons: `8`
- TaskGenerator generated clean paired comparisons: `4`
- total clean paired comparisons: `12`
- GDPVal gap bands: `6 high`, `2 medium`, `2 unusable`
- TaskGenerator generated gap bands: `1 high`, `2 medium`, `1 low`

Remaining review item:

- `ideal_2_llm_positive_impact = partial`: the LLM shadow evidence exists, but human review still needs to decide whether any insertion point is reliably positive enough for Candidate Mode.

This is now a success handoff for Phase 14 evidence collection. It is not a scored-profiler handoff and not a benchmark-grade model-separation claim.

## Phase 14.4 GDPVal Task Anatomy Extraction

GDPVal task anatomy extraction now has a deterministic V1 pass over the selected finance/audit subset.

Main entry point:

```bash
python Test/run_v3_gdpval_task_anatomy.py
```

Outputs:

- `artifacts/phase14/gdpval_anatomy/gdpval_task_anatomy.jsonl`
- `artifacts/phase14/gdpval_anatomy/gdpval_anatomy_summary_report.json`
- `artifacts/phase14/gdpval_anatomy/gdpval_task_anatomy_distribution.json`
- `artifacts/phase14/gdpval_anatomy/good_task_profiler_input.json`
- per-task profiles under `artifacts/phase14/gdpval_anatomy/task_profiles/<case_slug>/task_anatomy_profile.json`

Current anatomy result over the 10-task subset:

- deliverable types: 7 spreadsheet workbooks, 1 slide deck, 2 document/report tasks
- clean eval status: 4 usable for gap analysis, 1 needs model rerun, 5 not yet evaluated
- common motifs include `evidence_to_spreadsheet_deliverable`, `cross_check_validation`, `amortization_schedule`, `month_end_financial_reporting`, and `policy_application`

This is a deterministic profile only. LLM annotation fields are reserved as `not_requested`; they must not be treated as primary truth or as training-generation input.
