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
