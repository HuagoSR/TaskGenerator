# Phase 15 Completion Plan - 2026-07-09

## Status Correction

Phase 15 should remain open.

The current run completed a useful controlled sub-experiment, but it did not complete the original Phase 15 research question. The precise status is:

```text
phase15_status = open
phase15a_status = completed
phase15a_scope = weak-model baseline vs reform-only clean eval for evidence_to_deliverable
phase15b_status = planned
current_safe_action = do_not_promote_pending_strong_model_eval
```

The previous local closeout artifacts report `phase15_decision = success` and `completion_status = complete`. Those values should be read as the old implementation-level audit result: the implemented local Phase 15 scaffolding reached its then-registered closeout path. They must not be read as proof that the full Phase 15 plan has answered whether the reform improves training value or model separation.

## What Phase 15A Proved

Phase 15A completed the `gpt-4o-mini` side of a baseline/reform-only paired eval for four `evidence_to_deliverable` cases.

| case | baseline `gpt-4o-mini` | reform `gpt-4o-mini` | reform minus baseline |
| --- | ---: | ---: | ---: |
| `pipeline_b_batch_01_evidence_to_deliverable` | `0.5660` | `0.0000` | `-0.5660` |
| `pipeline_b_batch_02_evidence_to_deliverable` | `0.0000` | `0.0000` | `0.0000` |
| `pipeline_b_batch_03_evidence_to_deliverable` | `0.6346` | `0.3333` | `-0.3013` |
| `pipeline_b_batch_04_evidence_to_deliverable` | `1.0000` | `0.8462` | `-0.1538` |

Summary:

```text
positive_delta_pair_count = 0
zero_delta_pair_count = 1
negative_delta_pair_count = 3
mean_reform_minus_baseline_delta = -0.2553
```

This proves only that the tested reform-only arm is harder or less score-friendly for `gpt-4o-mini`.

It does not prove:

```text
the reform improves model separation
the reform lowers task quality
the reform increases productive complexity
the reform introduces only frictional complexity
the reform should be promoted
the reform should be permanently abandoned
```

The safe conclusion is narrower:

> Do not promote this reform into the default generator until strong-model paired eval, gap-delta analysis, and case-level failure autopsy are complete.

## Missing Evidence

The full Phase 15 plan still needs these missing pieces before closeout:

1. Strong-model paired eval for the same four cases and both arms.
2. Baseline/reform gap comparison:

```text
baseline_gap = strong_baseline - weak_baseline
reform_gap = strong_reform - weak_reform
gap_delta = reform_gap - baseline_gap
```

3. Case-level autopsy of the score drops, especially case01 and case03.
4. Classification of score drops into productive difficulty versus task/rubric/evidence friction.
5. A guarded LLM candidate decision. The current LLM candidate layer keeps artifact-mutating candidate mode disabled because no role is approved for candidate experiment.
6. A final promotion decision that distinguishes `promote_reform`, `rollback_reform`, and `hold_for_redesign`.

## Phase 15B Work Packages

### 15B-1 Strong-Model Paired Eval

Run the same four `evidence_to_deliverable` cases for a strong model on both arms:

```text
baseline_deterministic / strong_model
generator_reform_only / strong_model
```

Prefer the Phase 14 strong model if still available, such as `gemini-3-pro-preview`, or another recorded strong model with the same grader and run configuration. Record exact `evaluated_model_name`, `provider`, `grader_model`, and timeout settings.

Expected output:

```text
artifacts/phase15/eval_results/phase15_strong_model_eval_report.json
artifacts/phase15/eval_results/phase15_gap_delta_report.json
```

Acceptance:

```text
4 / 4 baseline strong records completed
4 / 4 reform strong records completed
numeric scores imported
gap_delta computed for all four cases
```

### 15B-2 Gap-Delta Interpretation

For each case, classify the reform into one of three outcome patterns:

```text
productive_separation_gain:
  strong score stays high or improves
  weak score drops
  reform_gap > baseline_gap

quality_or_contract_regression:
  strong and weak both drop
  or strong drops enough that the gap does not improve meaningfully

difficulty_without_separation_gain:
  both models drop similarly
  reform_gap is flat or lower
```

The reform can only be considered useful if the strong model remains capable and the gap increases for reasons that survive qualitative review.

### 15B-3 Case-Level Failure Autopsy

Inspect model outputs, grader records, rubrics, and generated task artifacts for all four cases, with priority on:

```text
case01 delta = -0.5660
case03 delta = -0.3013
```

Each case should receive one or more reason labels:

```text
productive_difficulty_increased
instruction_clarity_decreased
deliverable_mismatch
rubric_mismatch
evidence_overload
ground_truth_or_goldenrun_mismatch
format_or_tool_noise
grader_misread
```

Expected output:

```text
artifacts/phase15/failure_autopsy/phase15_reform_failure_autopsy_report.json
```

Acceptance:

```text
all 4 cases labeled
case01 and case03 have criterion-level loss explanations
autopsy distinguishes productive complexity from frictional complexity
```

### 15B-4 LLM Candidate Arm Decision

Do not treat the absence of the LLM candidate arm as a completed A/B/C experiment. Current evidence says:

```text
candidate_mode_default_enabled = false
experiment_candidate_enabled = false
approved_candidate_roles = []
diagnostic_only_roles = ["realism_critic"]
blocked_roles = ["goldenrun", "rubric"]
```

Phase 15B should either:

1. Keep LLM candidate out of artifact mutation and explicitly mark A/B/C as reduced to A/B for this phase, or
2. Approve a strictly diagnostic sidecar role and run a non-mutating `reform + diagnostic realism critic` comparison.

No LLM role may write primary truth, rubrics, GoldenRun, evidence mappings, production approval, or sampler weights.

### 15B-5 Production Impact Recheck

After strong-model evidence and autopsy are available, rerun the production impact review as a diagnostic release-safety check, not as a substitute for training-value evidence.

Acceptance:

```text
candidate_ready remains 4 / 4
verifier pass remains 4 / 4
no hidden artifact exposure
no unsupported-claim increase
production review explains whether single-motif concentration is acceptable for experiment-only evidence
```

### 15B-6 Final Phase 15 Postmortem

The final postmortem should use one of these decisions:

```text
promote_reform:
  strong model remains high
  weak model drops
  gap_delta positive
  autopsy shows productive difficulty
  QA and verifier remain stable

rollback_reform:
  strong model also drops
  or gap_delta is flat/negative
  or autopsy shows task/rubric/evidence friction

hold_for_redesign:
  direction has plausible signal
  but implementation, rubric, LLM role, or evidence ecology needs redesign before another clean eval
```

The postmortem should not enter Phase 16 until it answers:

```text
Did the reform improve model gap?
Did it preserve strong-model solvability?
Was the weak-model decline productive or frictional?
Did production QA remain stable?
Is any LLM role approved beyond shadow/diagnostic use?
Should the default generator change, stay unchanged, or receive a redesigned experiment?
```

## Recommended Immediate Next Step

Do not start Phase 16 yet.

Start Phase 15B by running or importing strong-model paired eval for the already prepared four-case baseline/reform queue, then build the gap-delta report and failure autopsy. Until that is done, keep the reform behind the explicit experiment flag and keep the default generator unchanged.
