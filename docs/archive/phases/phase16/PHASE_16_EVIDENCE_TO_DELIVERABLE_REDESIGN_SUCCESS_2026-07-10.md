# Phase 16 Evidence-To-Deliverable Redesign Success - 2026-07-10

> Superseded: this handoff recorded the successful 2-case pilot and authorization to expand. The authoritative final closeout after the 4-case clean eval is `docs/handoffs/PHASE_16_COMPLETION_2026-07-10.md`.

## Decision

- phase16_decision: `success_expand_to_4case_clean_eval`
- promotion_decision: `hold_for_4case_expansion_before_default_promotion`
- default_generator_change_allowed: `false`
- llm_primary_truth_used: `false`
- phase17_recommendation: `route_b_4case_expansion_before_promotion`

## What Completed

- Phase 15B baseline was frozen into a Phase 16 baseline manifest.
- Four-case Phase 15B failure autopsy was deepened, with case01 and case03 kept as high-priority cases.
- `evidence_to_deliverable_contract_v2.experimental.json` was created.
- GoldenRun, rubric, and verifier alignment reports were generated from the same Contract V2.
- Three redesign V2 arms were generated: baseline, contract_v2_only, and contract_v2_plus_productive_complexity.
- Structural review and 6 / 6 negative controls passed.
- Two-case clean paired eval was executed through rw-task and imported with 12 / 12 completed records.
- Both redesign arms improved mean gap delta on the two selected cases.
- Production impact and promotion reports keep all changes out of the default chain.

## What Still Did Not Run

- Four-case clean eval expansion was not run in this pass.
- No default-generator promotion or registry mutation was performed.
- The 2-case pilot is diagnostic evidence, not benchmark-grade model-separation evidence.

## Phase 15B Failure Cause

- mean_strong_score_delta: `-0.05477817748905428`
- mean_gap_delta: `0.09996182908225085`
- failure_label_counts: `{'productive_difficulty_increased': 2, 'deliverable_mismatch': 3, 'rubric_or_goldenrun_alignment_risk': 3, 'difficulty_without_separation_gain': 2, 'instruction_or_contract_friction': 1}`
- Main cause: useful evidence-reasoning difficulty was mixed with deliverable mismatch and rubric/GoldenRun alignment friction.

## Postmortem Answers

1. Phase 15B reform failed mainly because productive difficulty was entangled with contract and scoring friction.
2. Contract V2 resolves the structural deliverable ambiguity at the artifact level.
3. Rubric / GoldenRun / verifier are now contract-aligned in deterministic design reports.
4. New complexity is productive only when it maps to support strength, unresolved handling, conflict detection, or traceability.
5. Strong-model stability is re-proven for the 2-case pilot, with positive mean strong-score deltas for both redesign arms.
6. Weak-model decline now aligns with positive gap deltas in the 2-case pilot, but needs 4-case confirmation before promotion.
7. Redesign V2 is ready for governed 4-case expansion, not default promotion.
8. LLM should still remain diagnostic only.
9. Phase 17 should run the 4-case expansion and then decide promotion, continued redesign, or evaluator/rubric reform.

## Key Outputs

- baseline_handoff: `E:\THU\2026Spring\SRT\TaskGenerator\docs\handoffs\PHASE_16_BASELINE_2026-07-10.md`
- baseline_manifest: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase16\baseline\phase16_baseline_manifest.json`
- case_delta_report: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase16\autopsy\phase16_case_level_score_delta_report.json`
- completion_audit: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase16\completion_audit\phase16_completion_audit_report.json`
- contract: `E:\THU\2026Spring\SRT\TaskGenerator\SkillRegistry\evidence_to_deliverable_contract_v2.experimental.json`
- contract_report: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase16\contract\evidence_to_deliverable_contract_v2_report.json`
- deep_autopsy: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase16\autopsy\phase16_reform_deep_autopsy_report.json`
- four_case_eval: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase16\eval_4case\phase16_four_case_eval_report.json`
- four_case_gap: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase16\eval_4case\phase16_four_case_gap_delta_report.json`
- four_case_goodtask: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase16\eval_4case\phase16_four_case_goodtask_comparison_report.json`
- friction_removal: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase16\patterns\frictional_complexity_removal_report.json`
- goldenrun_alignment: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase16\alignment\goldenrun_alignment_v2_report.json`
- negative_controls: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase16\pre_eval\phase16_negative_control_report.json`
- production_impact: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase16\production_impact\phase16_production_impact_report.json`
- productive_patterns: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase16\patterns\evidence_to_deliverable_productive_patterns.json`
- promotion_decision: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase16\promotion\phase16_promotion_decision_report.json`
- promotion_proposal: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase16\promotion\phase16_promotion_proposal.json`
- redesign_manifest: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase16\redesign_v2\phase16_redesign_v2_manifest.json`
- rubric_alignment: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase16\alignment\rubric_alignment_v2_report.json`
- structural_review: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase16\pre_eval\phase16_structural_review_report.json`
- two_case_autopsy: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase16\eval_pilot_2case\phase16_two_case_failure_autopsy_report.json`
- two_case_clean_eval_import_report: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase16\clean_eval_gate\phase16_two_case_clean_eval_import_report.json`
- two_case_clean_eval_runbook: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase16\clean_eval_gate\phase16_two_case_clean_eval_runbook.json`
- two_case_eval: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase16\eval_pilot_2case\phase16_two_case_eval_report.json`
- two_case_gap: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase16\eval_pilot_2case\phase16_two_case_gap_delta_report.json`
- verifier_alignment: `E:\THU\2026Spring\SRT\TaskGenerator\artifacts\phase16\alignment\verifier_alignment_v2_report.json`
