# Phase 14 Baseline - 2026-07-07

## What Was Frozen

- GDPVal use: `eval_calibration_only`
- Generated task use: `generated_training_candidate`
- LLM mode: `shadow_or_candidate_diagnostics_only`

## Mirror

- mirrored task count: `220`
- mirrored reference file count: `261`
- mirror manifest: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase14\gdpval_local_mirror\dataset_manifest.json`

## Initial Calibration Subset

- selected task count: `10`
- selected task ids: `83d10b06-26d1-4636-a32c-23f92c57f30b, 7b08cd4d-df60-41ae-9102-8aaa49306ba2, 7d7fc9a7-21a7-4b83-906f-416dea5ad04f, ee09d943-5a11-430a-b7a2-971b4e9b01b5, 87da214f-fd92-4c58-9854-f4d0d10adce0, 5f6c57dd-feb6-4e70-b152-4969d92d1608, b39a5aa7-cd1b-47ad-b249-90afd22f8f21, c657103b-b348-4496-a848-b2b7165d28b2, 58ac1cc5-5754-4580-8c9c-8c67e1a9d619, 4de6a529-4f61-41a1-b2dc-64951ba03457`
- subset manifest: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase14\gdpval_subset\gdpval_finance_audit_subset_manifest.json`

## Comparison Baseline

- `finance_audit_mvp_v0_1_pilot8_diversity_final_reviewed_strict` with `8` tasks from `phase13_pilot8_diversity_final_smoke`

## Notes

- Phase 14 baseline fixes the evaluation/training boundary before GDPVal anatomy, profiler, or LLM shadow work starts.
- GDPVal artifacts remain isolated under artifacts/phase14 and must not flow into TaskGenerator training generation.
- Generated release tasks remain the comparison baseline for later generated-vs-GDPVal analysis.
