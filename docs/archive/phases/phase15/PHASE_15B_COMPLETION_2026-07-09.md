# Phase 15B Completion Handoff - 2026-07-09

## Final Decision

Phase 15B is complete for the current `evidence_to_deliverable` reform.

```text
phase15b_decision = hold_for_redesign
promotion_decision = do_not_promote_default_chain
default_generator_change_allowed = false
```

The current reform should stay behind the explicit experiment flag. It should not be promoted into the default generator or release packaging path.

## What Phase 15B Added

Phase 15A had shown only that the reform lowered `gpt-4o-mini` scores. Phase 15B completed the missing strong-model and fixed-grader comparison:

```text
strong_model = gemini-3-pro-preview
weak_model = gpt-4o-mini
fixed_grader = gpt-5.4-pro
cases = 4 x evidence_to_deliverable
arms = baseline_deterministic vs generator_reform_only
strong_records_completed = 8 / 8
weak_outputs_regraded_with_fixed_grader = 8 / 8
```

Generated reports:

- `artifacts/phase15/eval_results/phase15_strong_model_eval_report.json`
- `artifacts/phase15/eval_results/phase15_gap_delta_report.json`
- `artifacts/phase15/failure_autopsy/phase15_reform_failure_autopsy_report.json`
- `artifacts/phase15/phase15b_closeout/phase15b_postmortem_report.json`

## Gap-Delta Evidence

Fixed-grader summary:

```text
mean_baseline_strong_score = 0.5275
mean_baseline_weak_score = 0.2463
mean_reform_strong_score = 0.4727
mean_reform_weak_score = 0.0916
mean_strong_score_delta = -0.0548
mean_weak_score_delta = -0.1547
mean_baseline_gap = 0.2812
mean_reform_gap = 0.3812
mean_gap_delta = 0.1000
positive_gap_delta_case_count = 2
negative_gap_delta_case_count = 2
```

Interpretation:

- The reform creates a partial separation signal: weak-model scores drop more than strong-model scores on average.
- The signal is not strong enough for promotion: only `2 / 4` cases improve gap delta.
- Strong-model scores are only moderate and decline in all four cases.
- The current reform therefore fails the promotion condition that strong-model solvability should remain high.

## Failure Autopsy

Autopsy status:

```text
all_cases_labeled = true
priority_cases = [
  pipeline_b_batch_01_evidence_to_deliverable,
  pipeline_b_batch_03_evidence_to_deliverable
]
```

Label counts:

```text
productive_difficulty_increased = 2
deliverable_mismatch = 3
rubric_or_goldenrun_alignment_risk = 3
difficulty_without_separation_gain = 2
instruction_or_contract_friction = 1
```

Primary finding:

> The reform creates some separation signal, but the score losses are mixed with deliverable/rubric/evidence friction and do not justify promotion.

## LLM Candidate Decision

The LLM candidate arm remains non-mutating:

```text
candidate_mode_default_enabled = false
experiment_candidate_enabled = false
approved_candidate_roles = []
diagnostic_only_roles = ["realism_critic"]
blocked_roles = ["goldenrun", "rubric"]
```

No LLM role is approved to write primary truth, rubrics, GoldenRun, evidence mappings, production approval, or sampler weights.

## Production Impact Recheck

Production impact review was rerun after Phase 15B eval:

```text
decision = review_complete_keep_experiment_flag
release_ready = false
structural_regression_detected = false
blocking_reasons = []
```

Review reasons remain:

```text
batch_diversity_warnings_require_scaleup_review
global_validity_remains_diagnostic_only
no_governed_production_ready_cases
qa_cases_still_review_required
```

This supports continued experiment isolation, not default-chain promotion.

## Completion Answer

Phase 15B answers the questions left open by Phase 15A:

```text
Did the reform improve model gap?
  mixed_partial_signal

Did it preserve strong-model solvability?
  not_enough_for_promotion

Was the weak-model decline productive or frictional?
  mixed_with_friction

Did production QA remain stable?
  yes, but only as keep_experiment_flag

Is any LLM role approved beyond shadow/diagnostic use?
  no

Should the default generator change?
  no
```

## Next Work

Do not run Phase 16 as if the current reform succeeded.

The next useful work is a redesign pass for `evidence_to_deliverable`:

1. Make the deliverable contract clearer before adding more evidence complexity.
2. Align reform rubrics and GoldenRun expectations with the new evidence ecology.
3. Keep LLM candidate roles diagnostic-only unless a later adoption gate approves a role.
4. Run a second clean eval only after the redesigned reform passes structural review.
