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
- `usable_task_count = 1` for two-model gap analysis
- failure report count is 6, including 2 model-level grading command failures and 4 task-level grading failures

The one task with two completed scores was `ee09d943-5a11-430a-b7a2-971b4e9b01b5`: `gpt-5.4-pro` scored `0.0`, `gpt-4o-mini` scored `0.23728813559322035`, and the diagnostic score gap was `0.23728813559322035`.

This is a useful toolchain baseline, but it is not yet a clean model-separation benchmark. The main exposed issues are grading robustness and task runnability, not just model capability. The `gpt-5.4-pro = 0.0` vs `gpt-4o-mini = 0.23728813559322035` result should not be treated as a model-quality finding because later inspection showed that some zero scores came from missing deliverables after sandbox timeout.

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
