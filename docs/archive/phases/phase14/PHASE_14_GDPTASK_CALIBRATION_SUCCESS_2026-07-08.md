# Phase 14 GDPTask Calibration Success - 2026-07-08

## Decision

- phase14_decision: `success`
- phase15_recommendation: `phase15_candidate_mode_or_generator_reform_review`
- dashboard_status: `ready_for_phase14_postmortem`
- weighted GoodTaskScore: not emitted
- GDPVal training use: forbidden; calibration only

## Evidence Snapshot

- GDPVal clean usable cases: `8 / 10`
- GDPVal gap bands: `{'medium': 2, 'high': 6, 'unusable': 2}`
- Dashboard blockers: `[]`
- LLM impact readiness: `ready_for_impact_analysis`
- LLM adoption recommendation: `review_shadow_metrics_before_candidate_mode`

## Success Criteria

- `minimum_1_gdpval_mirror_and_subset`: `met` - GDPVal finance/audit subset and calibration boundary exist.
- `minimum_2_clean_gdpval_baseline`: `met` - At least 4 GDPVal clean paired comparisons are usable for gap analysis.
- `minimum_3_gap_autopsy`: `met` - Gap autopsy and hypothesis ledger exist with usable and counterexample cases.
- `minimum_4_observational_profiler_dashboard`: `met` - GoodTaskProfiler and dashboard can represent GDPVal and generated tasks without weighted score.
- `ideal_1_total_clean_pairs_12`: `met` - At least 12 clean paired comparisons include GDPVal and TaskGenerator generated tasks.
- `ideal_2_llm_positive_impact`: `partial` - LLM shadow provides enough evidence to decide whether any insertion point is positive.
- `ideal_3_phase15_route`: `met` - Phase 15 route is clear.

## Postmortem Answers

- `1_gdpval_high_gap_tasks`: 7b08cd4d-df60-41ae-9102-8aaa49306ba2 (spreadsheet_workbook, gap=0.787); 7d7fc9a7-21a7-4b83-906f-416dea5ad04f (spreadsheet_workbook, gap=0.811); 87da214f-fd92-4c58-9854-f4d0d10adce0 (slide_deck, gap=0.635); c657103b-b348-4496-a848-b2b7165d28b2 (spreadsheet_workbook, gap=0.500); 58ac1cc5-5754-4580-8c9c-8c67e1a9d619 (document_report, gap=0.618); 4de6a529-4f61-41a1-b2dc-64951ba03457 (document_report, gap=0.678)
- `2_gap_source_real_skill_vs_noise`: Current evidence suggests meaningful gaps often come from numeric accuracy, policy application, evidence reconciliation, and deliverable structure. Some friction remains: ee09 and slide/deck packaging show missing-deliverable/tool-noise risk.
- `3_high_value_common_structure`: High-value GDPVal cases tend to combine spreadsheet or presentation deliverables, explicit professional roles, cross-file synthesis, policy/compliance reasoning, reconciliation, and reviewer-visible deliverable constraints.
- `4_generated_vs_high_value_gap`: Generated tasks now have a 4-case clean paired diagnostic slice. The observed generated gaps are mixed: one low-gap case and three medium/high-gap cases. This is enough to compare initial distributions against GDPVal, but not enough for benchmark-grade model-separation claims or a weighted GoodTaskScore.
- `5_production_qa_sufficiency`: Production QA is sufficient for governed release readiness, but not sufficient to prove training value or model separation.
- `6_unstable_profiler_dimensions`: Generated-task model separation, format-noise risk, tool-failure risk, and LLM-impact dimensions remain observational. They are now measurable enough for Phase 15 review, but not stable enough for a weighted score.
- `7_llm_value_position`: Shadow outputs now exist for GoldenRun, rubric, realism critic, and reference narrative. impact_readiness=ready_for_impact_analysis, completed_metric_count=20. The remaining question is whether the observed deltas are beneficial enough for Candidate Mode.
- `8_llm_candidate_mode`: No. Current recommendation is review_shadow_metrics_before_candidate_mode; review the completed shadow metrics before promotion.
- `9_next_phase_direction`: Phase 15 should review the completed shadow metrics and choose a narrow route: either guarded LLM Candidate Mode for the best-supported insertion point, or generator reform if shadow benefits are weak or risky.
- `counterexamples_to_keep`: 83d10b06-26d1-4636-a32c-23f92c57f30b (spreadsheet_workbook, gap=0.190); b39a5aa7-cd1b-47ad-b249-90afd22f8f21 (spreadsheet_workbook, gap=0.242); ee09 remains a runnability/friction holdout.

## Next Actions

- Run queued GDPVal cases one at a time until clean paired comparisons approach 8.
- Execute generated comparison tasks one at a time, then rerun generated eval summary and comparison reports.
- human review of metric alignment
- candidate-mode risk gate
- Use GDPVal next eval queue to raise GDPVal clean paired comparisons from 4 toward 8.

## Notes

- GDPVal remains eval_calibration_only and must not enter training generation.
- Weighted GoodTaskScore remains disabled because Phase 14 is observational, not a calibrated scoring system.
- Phase 14 evidence collection is complete enough to enter Phase 15 route selection.
- LLM shadow metrics are complete; Candidate Mode still requires human review and a risk gate.
