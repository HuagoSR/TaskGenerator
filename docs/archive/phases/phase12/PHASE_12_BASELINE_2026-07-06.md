# Phase 12 Baseline - 2026-07-06

## Anchor

Phase 12 starts from the final Phase 11 deterministic regression baseline.

- baseline batch report: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\pipeline_b\scratch\phase11_batch_regression_3case_policy_fix_v2\pipeline_b_batch_report.json`
- baseline batch feedback report: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\pipeline_b\scratch\phase11_batch_regression_3case_policy_fix_v2_feedback\pipeline_b_batch_feedback_report.json`
- baseline dashboard report: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\pipeline_b\scratch\phase11_batch_regression_3case_policy_fix_v2_dashboard\global_pipeline_dashboard_report.json`

## Confirmed baseline counts

- case_count = 3
- candidate_ready_count = 3
- verifier_pass_count = 3

## Guardrails

- `.env` must remain local-only and must not enter staged files.
- Phase 12 should compare against this anchor instead of reinterpreting old `revise_only` snapshots as current state.
- Future Phase 12 diffs should explain whether changes come from substrate repair, workflow-context repair, verifier/rubric repair, or export/eval hardening.
