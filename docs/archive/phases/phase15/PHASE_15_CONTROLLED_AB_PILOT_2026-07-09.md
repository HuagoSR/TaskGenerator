# Phase 15 Controlled A/B Pilot Handoff - 2026-07-09

## Scope

This handoff records the first deterministic Phase 15 controlled experiment scaffold for the `evidence_to_deliverable` reform target.

Phase 15 remains report-first:

- GDPVal is used for calibration and anatomy patterns only.
- LLM outputs are not primary truth, not rubric truth, and not default artifact mutators.
- Generator reform is applied only behind an explicit experiment flag.
- No registry, sampler prior, promotion state, or release state is silently updated.

## Implemented Layers

### 15.5 Guarded LLM Candidate Layer

New files:

- `src/task_generator/v3_llm_candidate_layer.py`
- `Test/run_v3_llm_candidate_layer.py`

Smoke command:

```powershell
& 'D:\miniconda3\envs\taskgenerator\python.exe' Test\run_v3_llm_candidate_layer.py
```

Observed result:

- `experiment_candidate_enabled = false`
- `approved_candidate_roles = []`
- `diagnostic_only_roles = ["realism_critic"]`
- `blocked_roles = ["goldenrun", "rubric"]`
- `reference_narrative` remains `needs_more_review`

Implication:

- `generator_reform_plus_guarded_llm_candidate` is intentionally blocked for artifact mutation.
- `realism_critic` can be used only as a diagnostic sidecar if later reviewer triage needs it.

### 15.6 Controlled A/B/C Experiment Ledger

New files:

- `src/task_generator/v3_phase15_ab_experiment_runner.py`
- `Test/run_v3_phase15_ab_experiment_runner.py`

Updated production chain interfaces:

- `src/task_generator/v3_pipeline_b_prototype.py`
- `src/task_generator/v3_pipeline_b_batch_runner.py`
- `src/task_generator/v3_production_batch_runner.py`
- `Test/run_v3_production_batch_runner.py`

The default production chain is unchanged. The Phase 15 reform is applied only when `phase15_reform_spec_path` is explicitly passed.

## Pilot Evidence

Command:

```powershell
& 'D:\miniconda3\envs\taskgenerator\python.exe' Test\run_v3_phase15_ab_experiment_runner.py --experiment-id phase15_ab_pilot4 --max-cases-per-arm 4
```

Observed result:

- `baseline_deterministic`: `4 / 4 candidate_ready`
- `generator_reform_only`: `4 / 4 candidate_ready`
- `generator_reform_plus_guarded_llm_candidate`: blocked by adoption gate
- `clean_paired_eval_ready_arm_count = 2`
- only remaining reason code: `no_llm_roles_approved_for_candidate_experiment`

The reform-only arm now applies a real experiment flag, not just a proxy ledger. The generated reform blueprint includes the Phase 15 structural changes:

- `template_family = evidence_package_to_reviewer_decision_memo_phase15`
- deliverable renamed to `reviewer_decision_memo.docx`
- added candidate-visible `manager_followup.md`
- added `Severity_Indicator`, `Reviewer_Concern`, and `Support_Status` columns
- added explicit confirmed-vs-unresolved and severity-classification requirements
- added Phase 15 intermediate states for confirmed/unresolved split, severity classification, and manager-followup alignment

## Current Boundary

This pilot proves deterministic structural closure for the baseline and reform-only arms. It does not yet prove training value or model separation.

Next Phase 15 steps:

1. Run clean paired evaluation one task/model at a time over the `phase15_ab_pilot4` baseline and reform-only arms.
2. Keep the LLM candidate arm blocked unless a later review produces an approved candidate role.
3. Run production QA and dashboard comparison for the reform arm after clean eval evidence exists.
4. Write a promotion or rollback proposal based on deterministic closure plus clean paired eval evidence, not on static quality alone.
