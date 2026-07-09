# Phase 15 External Eval Authorization Request - 2026-07-09

## Current State

Phase 15 deterministic work is ready for clean paired evaluation:

- `phase15_ab_pilot4` produced `4 / 4 candidate_ready` baseline cases.
- `phase15_ab_pilot4` produced `4 / 4 candidate_ready` reform-only cases behind the explicit Phase 15 experiment flag.
- `phase15_clean_eval_queue` prepared `16 / 16` one-case, one-model eval queue items:
  - 2 arms: `baseline_deterministic`, `generator_reform_only`
  - 4 paired cases
  - 2 models: `gpt-4o-mini`, `gemini-3-pro-preview`

The first attempted local run failed because the sandbox could not connect to the external model/API:

- attempted item: `baseline_deterministic__pipeline_b_batch_01_evidence_to_deliverable__gpt_4o_mini`
- run report: `artifacts/phase15/clean_eval_runs/baseline_case01_gpt4omini/rw_task_eval_run_report.json`
- failure evidence: `All connection attempts failed`

Two external-execution escalation attempts were rejected by policy review because the visible chat did not contain explicit approval for this exact Phase 15 task-package export.

After the user provided explicit visible approval for the exact single item, a third escalation attempt was still rejected because the current tenant policy denies exporting a private workspace task package to an untrusted third-party model/API even with explicit user approval.

## Minimal Explicit Authorization Needed

To continue Phase 15 clean paired eval, the user should explicitly approve the following in a normal chat message:

```text
我明确授权你本次将 Phase 15 的单个 task package
`baseline_deterministic / pipeline_b_batch_01_evidence_to_deliverable / gpt-4o-mini`
连同必要 API key 发送到外部模型/API/中转站执行 clean eval。
请一次只执行这一条，不要批量运行。
```

This authorization is intentionally narrow:

- one arm: `baseline_deterministic`
- one case: `pipeline_b_batch_01_evidence_to_deliverable`
- one model: `gpt-4o-mini`
- one eval input directory:
  `artifacts/phase15/clean_eval_queue/eval_inputs/baseline_deterministic/pipeline_b_batch_01_evidence_to_deliverable/gpt-4o-mini`
- one runner output directory:
  `artifacts/phase15/clean_eval_runs/baseline_case01_gpt4omini_authorized`

After that single item succeeds or fails, the next paired item should be run separately:

- `generator_reform_only / pipeline_b_batch_01_evidence_to_deliverable / gpt-4o-mini`

## Exact Command For First Authorized Item

```powershell
& 'D:\miniconda3\envs\taskgenerator\python.exe' Test\run_v3_rw_task_eval_runner.py `
  --prep-report 'artifacts\phase15\clean_eval_queue\eval_inputs\baseline_deterministic\pipeline_b_batch_01_evidence_to_deliverable\gpt-4o-mini\rw_task_eval_prep_report.json' `
  --output-dir 'artifacts\phase15\clean_eval_runs\baseline_case01_gpt4omini_authorized' `
  --run-eval `
  --command-timeout-seconds 600
```

## Data Sent Externally

The wrapper will send the candidate task prompt and reference package contents needed for the model to solve the task. For this first item, the generated package includes:

- candidate prompt from `dataset_row.json`
- `source_evidence.xlsx`
- `manager_request.md`
- deliverable expectation: `evidence_review_memo.docx`

It may use API credentials loaded by the existing rw-task / Stirrup / model-provider environment. Do not print or commit secret values.

## Success Evidence

A successful first item should produce:

- `artifacts/phase15/clean_eval_runs/baseline_case01_gpt4omini_authorized/rw_task_eval_run_report.json`
- model output directory:
  `artifacts/phase15/clean_eval_queue/eval_inputs/baseline_deterministic/pipeline_b_batch_01_evidence_to_deliverable/gpt-4o-mini_results`
- grade output directory:
  `artifacts/phase15/clean_eval_queue/eval_inputs/baseline_deterministic/pipeline_b_batch_01_evidence_to_deliverable/gpt-4o-mini_grades`

The run is not enough to complete Phase 15 by itself. It only unlocks the first half of the first paired comparison. The reform counterpart must be executed separately before any model-gap claim is made.

## Current Recommendation

Do not mark Phase 15 complete yet.

Keep the generator reform behind the explicit experiment flag until:

1. at least the first baseline/reform pair completes clean eval,
2. grading output is available for both arms,
3. Phase 15 closeout is regenerated with actual eval results,
4. promotion recommendation changes from `keep_experiment_flag_only` only if evidence supports it.

If this tenant policy remains in force, complete Phase 15 clean eval in a separately permitted environment using the exact command above, then copy only sanitized result summaries and grader outputs back into this repository.

## Sanitized Result Import Path

This repository now includes a report-only importer for results produced in a separately permitted environment:

```powershell
& 'D:\miniconda3\envs\taskgenerator\python.exe' Test\run_v3_phase15_external_eval_importer.py
```

The importer writes:

- `artifacts/phase15/external_eval_import/phase15_external_eval_results_template.json`
- `artifacts/phase15/external_eval_import/phase15_external_eval_import_report.json`

The default import scope is intentionally narrow:

- case: `pipeline_b_batch_01_evidence_to_deliverable`
- model: `gpt-4o-mini`
- arms: `baseline_deterministic` and `generator_reform_only`

Fill the template in the permitted environment with sanitized item-level records only. Do not include API keys, bearer tokens, full raw prompts, or private provider logs. Once both baseline and reform records are present with numeric scores, re-run the importer and then regenerate Phase 15 closeout.

`Test/run_v3_phase15_promotion_postmortem.py` now consumes `artifacts/phase15/external_eval_import/phase15_external_eval_import_report.json` by default, so a `ready_for_closeout` import report will be reflected in the Phase 15 promotion proposal and postmortem without manual JSON editing.

If the permitted environment preserves runbook output directories, build the sanitized results file from local run reports and grade JSON:

```powershell
& 'D:\miniconda3\envs\taskgenerator\python.exe' Test\run_v3_phase15_external_eval_result_builder.py
```

This writes `artifacts/phase15/external_eval_import/phase15_external_eval_results.json`, which can then be consumed by `Test\run_v3_phase15_external_eval_importer.py`. If run reports or grade scores are missing, generated records remain non-complete and the importer will continue to block closeout.

The result builder also reads `artifacts/phase15/permitted_eval_bundle/phase15_permitted_eval_bundle_report.json` by default. If the portable bundle is executed in a permitted environment and copied back with its `grades/` directory, the builder can recover sanitized completed records from the bundled grade outputs even when `rw_task_eval_run_report.json` is absent.

After copying results or bundled grades back, refresh the full closeout chain with one local command:

```powershell
& 'D:\miniconda3\envs\taskgenerator\python.exe' Test\run_v3_phase15_closeout_refresh.py
```

This command runs the sanitized result builder, result importer, production impact review, promotion/postmortem builder, completion audit, and local status summary in sequence. It writes `artifacts/phase15/closeout_refresh/phase15_closeout_refresh_report.json` and still does not call external APIs or read secrets.

Current expected status before real returned grades are present:

- result builder: `record_count = 2`, `completed_count = 0`, `missing_count = 2`
- importer: `import_status = blocked`
- production impact review: `decision = review_complete_keep_experiment_flag`
- postmortem: `phase15_decision = still_open`
- completion audit: `completion_status = not_complete`, with `7 / 9` requirements proven
- local status: `blocked_on_external_eval`

When real returned grades are present and imported as a complete first pair, the local status should move from `blocked_on_external_eval` to `ready_for_local_followup`. A previous sandbox connection failure or tenant-policy denial should not override successfully imported clean-eval evidence; remaining blockers should then come from production QA, release readiness, or promotion review rather than external-eval availability.

## Permitted-Environment Runbook

To reduce manual command drift, generate a sequential first-pair runbook before moving to a permitted environment:

```powershell
& 'D:\miniconda3\envs\taskgenerator\python.exe' Test\run_v3_phase15_external_eval_runbook.py
```

This writes:

- `artifacts/phase15/external_eval_runbook/phase15_external_eval_runbook.json`
- `artifacts/phase15/external_eval_runbook/run_phase15_first_pair_external_eval.ps1`

The generated script runs only the first paired comparison in order:

1. `baseline_deterministic / pipeline_b_batch_01_evidence_to_deliverable / gpt-4o-mini`
2. `generator_reform_only / pipeline_b_batch_01_evidence_to_deliverable / gpt-4o-mini`

It stops after a failed item instead of continuing into a batch.

Before moving the package to a permitted environment, run the local structural readiness check:

```powershell
& 'D:\miniconda3\envs\taskgenerator\python.exe' Test\run_v3_phase15_external_eval_readiness.py
```

Expected status:

- `readiness_status = ready_for_permitted_environment`
- `blocking_reasons = []`

This check verifies runbook/script/template consistency only; it does not call external APIs and does not make the current tenant permitted to export the task package.

## Portable Permitted-Environment Bundle

To reduce path drift when moving the first-pair eval to a separately permitted environment, build a portable bundle:

```powershell
& 'D:\miniconda3\envs\taskgenerator\python.exe' Test\run_v3_phase15_permitted_eval_bundle.py
```

Current expected status:

- `bundle_status = ready_for_permitted_environment`
- `item_count = 2`
- bundled items:
  - `baseline_deterministic / pipeline_b_batch_01_evidence_to_deliverable / gpt-4o-mini`
  - `generator_reform_only / pipeline_b_batch_01_evidence_to_deliverable / gpt-4o-mini`

The builder writes:

- `artifacts/phase15/permitted_eval_bundle/phase15_permitted_eval_bundle_report.json`
- `artifacts/phase15/permitted_eval_bundle/phase15_first_pair_gpt4omini_permitted_eval_bundle/`
- `artifacts/phase15/permitted_eval_bundle/phase15_first_pair_gpt4omini_permitted_eval_bundle.zip`

The generated bundle includes a relative-path script, copied eval input directories, a result template, README, and checksums. It intentionally excludes `.env`, API key files, provider logs, and generated model outputs. Configure secrets separately in the permitted environment.

## Completion Audit

Use the completion audit to avoid mistaking scaffolding for Phase 15 completion:

```powershell
& 'D:\miniconda3\envs\taskgenerator\python.exe' Test\run_v3_phase15_completion_audit.py
```

Current expected status before external results are imported:

- `completion_status = not_complete`
- proven items: Phase 15.0 through deterministic A/B and runbook readiness layers
- unresolved items: clean paired eval, governed production approval/release impact, and final success postmortem

The audit writes `artifacts/phase15/completion_audit/phase15_completion_audit_report.json`.

## Local Status Summary

Use the local status runner as the last local check after importing external eval results and regenerating closeout/audit reports:

```powershell
& 'D:\miniconda3\envs\taskgenerator\python.exe' Test\run_v3_phase15_local_status.py
```

Current expected status before external results are imported:

- `local_status = blocked_on_external_eval`
- `phase15_completion_status = not_complete`
- `phase15_decision = still_open`
- `external_eval_package_readiness = ready_for_permitted_environment`
- `permitted_eval_bundle_status = ready_for_permitted_environment`
- `external_eval_import_status = blocked`
- `tenant_policy_status = tenant_policy_denied`

The runner writes `artifacts/phase15/local_status/phase15_local_status_report.json`. It only reads existing local reports and writes a summary; it does not call external APIs, read `.env`, or print secret values.
