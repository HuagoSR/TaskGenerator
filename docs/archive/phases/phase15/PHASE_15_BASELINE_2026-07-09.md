# Phase 15 Baseline And Decision Boundary - 2026-07-09

## Decision

- baseline_status: `ready_for_phase15_p0`
- phase14_decision: `success`
- phase15_recommendation: `phase15_candidate_mode_or_generator_reform_review`
- GDPVal use: `eval_calibration_only`
- weighted GoodTaskScore: disabled
- LLM Candidate Mode: not enabled by default

## Evidence Snapshot

- GDPVal clean usable cases: `8 / 10`
- GDPVal gap distribution: `{'medium_gap': 2, 'high_gap': 6, 'unusable': 2}`
- Generated clean pairs: `4`
- Generated gap bands: `{'low': 1, 'medium': 2, 'high': 1}`
- LLM shadow metrics: `20 / 20`
- LLM adoption recommendation: `review_shadow_metrics_before_candidate_mode`
- First reform target: `evidence_to_deliverable`

## Boundary Locks

- `gdpval_eval_calibration_only`: `locked` - GDPVal artifacts calibrate task anatomy and model-gap evidence; they must not be rewritten into training tasks.
- `llm_not_primary_truth`: `locked` - LLM outputs may be reviewed as candidate evidence, critique, or narrative suggestions only.
- `good_task_profiler_observational_only`: `locked` - Phase 14 evidence is sufficient for diagnosis but not a calibrated weighted GoodTaskScore.
- `production_qa_not_training_value`: `locked` - Production QA remains necessary for release governance but cannot prove model separation or training value.
- `no_silent_promotion_or_sampler_update`: `locked` - Generator reforms and LLM candidate roles require explicit promotion or rollback proposals after controlled evidence.

## P0 Work Items

- `15.1_llm_shadow_review`: `ready` - llm_shadow_review_report.json and llm_adoption_gate_report.json
- `15.2_generated_task_gap_autopsy`: `ready` - generated_task_gap_autopsy_report.json
- `15.3_gdpval_productive_complexity_pattern_library`: `ready` - gdpval_productive_complexity_pattern_library.json
- `15.4_generator_reform_design`: `ready_after_15.2_and_15.3` - evidence_to_deliverable_reform_spec.json
- `15.5_guarded_llm_candidate_layer`: `ready_after_15.1` - llm_candidate_layer_report.json and validation report

## Blockers

- None.

## Next Actions

- Run Phase 15.1 LLM shadow review and adoption gate over the 20 completed shadow outputs.
- Run Phase 15.2 generated task gap autopsy for the 4 clean generated task pairs.
- Build Phase 15.3 GDPVal productive complexity pattern library.
- Use evidence_to_deliverable as the first generator reform target after autopsy and pattern mapping.

## Notes

- This is a baseline freeze; it does not call external LLMs or mutate registries.
- External model calls for later Phase 15 steps should be one small experiment at a time.
- E2B/rw-task runtime limits should be treated as experiment design constraints, not as model-quality evidence.
