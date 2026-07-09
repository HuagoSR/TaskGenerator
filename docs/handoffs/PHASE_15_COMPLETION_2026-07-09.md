# Phase 15A Partial Handoff - 2026-07-09

## Superseded By Phase 15B

This Phase 15A correction remains useful history, but the current closeout for the reform is now:

```text
docs/handoffs/PHASE_15B_COMPLETION_2026-07-09.md
phase15b_decision = hold_for_redesign
promotion_decision = do_not_promote_default_chain
```

Phase 15B has since completed the strong-model paired eval, fixed-grader gap-delta analysis, and case-level failure autopsy that this file listed as missing.

## Correction

This file corrects the earlier interpretation of the Phase 15 closeout.

At the time this Phase 15A handoff was written, Phase 15 was **not** complete under the original Phase 15 plan. What was complete was a controlled Phase 15A sub-experiment:

```text
phase15_status_at_phase15a = open
phase15a_status = completed
phase15a_scope = weak-model baseline vs reform-only clean eval for evidence_to_deliverable
phase15a_safe_action = do_not_promote_pending_strong_model_eval
next_plan = docs/architecture/phase15_completion_plan_2026-07-09.md
```

The local postmortem and completion audit currently report:

```text
phase15_decision = success
completion_status = complete
```

Those values should be read as implementation-level completion under the old audit scope. They should not be used to claim that the original Phase 15 research question has been answered.

## What Completed

Completed Phase 15A scope:

- target motif: `evidence_to_deliverable`
- arms: `baseline_deterministic` vs `generator_reform_only`
- evaluated model: `gpt-4o-mini`
- cases: `4`
- imported item count: `8 / 8`
- complete weak-model pair count: `4 / 4`

Normalized grader scores:

| case_id | baseline | reform | reform_minus_baseline |
| --- | ---: | ---: | ---: |
| `pipeline_b_batch_01_evidence_to_deliverable` | `0.5660` | `0.0000` | `-0.5660` |
| `pipeline_b_batch_02_evidence_to_deliverable` | `0.0000` | `0.0000` | `0.0000` |
| `pipeline_b_batch_03_evidence_to_deliverable` | `0.6346` | `0.3333` | `-0.3013` |
| `pipeline_b_batch_04_evidence_to_deliverable` | `1.0000` | `0.8462` | `-0.1538` |

Summary:

- positive delta pairs: `0`
- zero delta pairs: `1`
- negative delta pairs: `3`
- mean reform-minus-baseline delta: `-0.2553`

## Correct Interpretation

This result proves that the tested reform-only arm lowered `gpt-4o-mini` scores on this four-case slice.

It does **not** prove that the reform is good or bad. A weak-model score drop can mean either:

- productive difficulty increased and model separation improved, if a strong model remains high; or
- task contract, rubric, evidence, or deliverable friction increased, if the strong model also drops or the gap does not improve.

Because strong-model reform eval is missing, the current decision is:

> Keep the reform behind the explicit experiment flag. Do not promote it into the default generator. Do not call Phase 15 complete.

## Production Impact Evidence

The reform arm remained structurally viable but not release-ready:

- `4 / 4 candidate_ready`
- `4 / 4 verifier pass`
- `4 / 4 export compatible`
- `0 / 4 blocked`
- `0 / 4 governed production-ready`

Production review outcome:

- `decision = review_complete_keep_experiment_flag`
- `release_ready = false`
- `structural_regression_detected = false`

This supports experiment isolation, not default-chain promotion.

## Still Missing

Phase 15 still needs:

1. Strong-model paired eval on the same four cases and both arms.
2. Baseline/reform `gap_delta` analysis.
3. Case-level failure autopsy for case01 and case03, plus labels for all four cases.
4. A clear distinction between productive complexity and frictional complexity.
5. A final decision among `promote_reform`, `rollback_reform`, and `hold_for_redesign`.
6. An explicit decision on whether the LLM candidate arm remains blocked or gets a non-mutating diagnostic run.

## Current Evidence Paths

Primary reports:

- `artifacts/phase15/external_eval_import/phase15_external_eval_import_report.json`
- `artifacts/phase15/closeout/phase15_promotion_proposal.json`
- `artifacts/phase15/closeout/phase15_postmortem_report.json`
- `artifacts/phase15/completion_audit/phase15_completion_audit_report.json`
- `artifacts/phase15/production_impact/phase15_review/phase15_production_impact_review_report.json`

Current completion plan:

- `docs/architecture/phase15_completion_plan_2026-07-09.md`

## Next Step

Historical Phase 15A next step, now completed by Phase 15B:

1. Run or import strong-model paired eval for the four prepared baseline/reform cases.
2. Compute `baseline_gap`, `reform_gap`, and `gap_delta`.
3. Autopsy the score drops by rubric criterion, deliverable behavior, evidence use, and task clarity.
4. Then regenerate the promotion/postmortem decision using the stricter Phase 15B criteria.

Current result: see `docs/handoffs/PHASE_15B_COMPLETION_2026-07-09.md`.
