# Pipeline A To Pipeline B Handoff - 2026-06-30

## Purpose

This handoff defines the point where Pipeline A can pause as a standalone construction effort and start feeding a minimal Pipeline B prototype.

Pipeline A should not be treated as complete or perfect. It is now good enough to act as a controlled Source-To-Skill substrate while Pipeline B begins to test whether the extracted skills, resource contracts, readiness decisions, and graph signals are useful for real task assembly.

## Current Pipeline A Status

- Node-level Pipeline A MVP: about 85%.
- Registry governance: about 65-70%.
- Graph composability: about 45%.
- Overall Pipeline A maturity as a Pipeline B substrate: about 70%.
- Persistent registry entry count: 66.
- Sampling readiness: 30 `sample_ready`, 7 `sample_with_caution`, 29 `exclude_until_revised`.

Pipeline A now supports:

- source collection and normalization
- LLM extraction
- deterministic review
- persistent registry update
- registry audit and sampling readiness
- graph extraction diagnostics
- transition graph and composition readiness reports
- calibration-only web-source graph runs that do not mutate the registry

## Stable Inputs For Pipeline B

Pipeline B should initially read only these Pipeline A artifacts:

- `SkillRegistry/v3_skill_registry.json`
- `SkillRegistry/v3_registry_sampling_readiness_report.json`
- `SkillRegistry/v3_pipeline_b_seed_set_report.json`
- `SkillRegistry/v3_graph_calibration_report.json`
- selected per-run `skill_transition_graph_report.json`
- selected per-run `composition_readiness_report.json`

Pipeline B should not directly consume every accepted candidate file. Accepted candidate files from calibration runs are experiment outputs unless admitted through a later explicit registry update.

## Pipeline B Seed Set

Seed report:

- `SkillRegistry/v3_pipeline_b_seed_set_report.json`

Current seed selection:

- selected count: 20
- selected readiness: 20 `sample_ready`
- motif coverage among selected seeds:
  - `policy_application`: 12
  - `evidence_to_deliverable`: 8
  - `cross_check_validation`: 7
  - `fan_in_reconciliation`: 5

The seed set is intentionally conservative. It is a first sampling slice for Pipeline B, not a final approval of all registry contents.

Pipeline B should prefer these seed records over sampling directly from all 66 registry entries.

## Graph Calibration Status

Aggregate graph calibration report:

- `SkillRegistry/v3_graph_calibration_report.json`

Current aggregate:

- extraction dirs: 9
- candidates: 51
- typed resources: 80
- trace edges: 21
- motif hints: 9
- warning severities: 13 `warning`, 2 `attention`

Artifact generations:

- `graph_calibration`: 4
- `graph_capable`: 2
- `pre_graph_or_legacy`: 3

The remaining missing-resource and missing-trace warnings are concentrated in old pre-graph web-source outputs. They should be read as stale baseline artifacts, not as failures of the current graph prompt.

Current attention warnings:

- GDPVal accountants graph calibration has motif coverage below trace coverage.
- `internal_control_testing` web-source calibration has motif coverage below trace coverage.

This is a prompt/diagnostics calibration target, but it does not block a minimal Pipeline B prototype.

## Calibration Candidate Admission

Admission report:

- `SkillRegistry/v3_calibration_registry_admission_report.json`

Current result over 15 accepted graph calibration candidates:

- 14 `recommend_admit`
- 1 `merge_existing`

This report is non-destructive. It does not write to `SkillRegistry/v3_skill_registry.json`.

Recommended decision:

- Do not bulk-admit all calibration candidates yet.
- Use the admission report to select a small number of candidates only if Pipeline B needs them.
- Treat `merge_existing` as additional evidence, not new skill growth.

## Interpretation Rules

Readiness:

- `sample_ready`: default eligible for Pipeline B seed sampling.
- `sample_with_caution`: exploratory only; provenance should remain visible.
- `exclude_until_revised`: do not sample until revised or decomposed.

Graph edges:

- `edge_scope=registry_mapped`: both endpoints map to persistent registry entries.
- `edge_scope=candidate_local`: at least one endpoint is experiment-only.
- candidate-local edges are useful calibration evidence, but not persistent transition priors.

Motifs:

- Motif hints are source-supported task-shape clues, not task blueprints.
- Pipeline B should use motifs as sampling constraints for small executable subgraphs.

Registry:

- Pipeline B should not mutate the registry.
- Registry admission should remain a separate Pipeline A governance action.

## Recommended Pipeline B First Slice

Build a minimal prototype that:

1. Reads `v3_pipeline_b_seed_set_report.json`.
2. Selects a small seed subset from `sample_ready` records.
3. Chooses one motif, preferably `evidence_to_deliverable`, `cross_check_validation`, or `fan_in_reconciliation`.
4. Attempts to assemble a small skill-resource subgraph.
5. Generates a draft `TaskBlueprint` without yet requiring full rw-task export.
6. Reports which Pipeline A signals were useful or missing.

This first Pipeline B slice should be feedback-oriented. Its purpose is to discover which Pipeline A resource contracts, motifs, and readiness signals actually help task assembly.

## What Pipeline A Should Still Improve Later

- Better motif coverage when trace coverage is high.
- More precise resource subtype compatibility.
- Report-first persistent transition-prior accumulation.
- Admission workflow for selected calibration candidates.
- Feedback hooks from Pipeline B task quality back into graph/motif weights.

These should be driven by Pipeline B failures rather than continued Pipeline A polishing in isolation.


