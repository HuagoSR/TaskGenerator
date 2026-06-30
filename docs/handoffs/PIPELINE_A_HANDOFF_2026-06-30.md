# Pipeline A Handoff - 2026-06-30

This file is a handoff note for continuing TaskGenerator Pipeline A in a fresh conversation.

Workspace:

- `E:\THU\2026Spring\SRT\TaskGenerator`

Broader project paths:

- `E:\THU\2026Spring\SRT\rw-task`: evaluation framework and shared `.env`
- `E:\THU\2026Spring\SRT\GDPVal`: GDPVal reference material

Use conda Python, not bare Python:

- `D:\miniconda3\envs\real-world-task\python.exe`
- `D:\miniconda3\envs\gdpval\python.exe`

## 1. Project Goal

The research goal is to build a batch, automatic GDPVal-style real-world-task factory for RL training.

The project is not trying to handcraft one good finance/audit task. The intended architecture is:

- collect realistic source context
- extract reusable semantic skills
- maintain an evidence-backed skill registry
- compose skills into new real-world tasks
- generate reference files
- run teacher-mode GoldenRun
- build executable or semi-executable rubrics
- evaluate generated tasks with `rw-task`
- keep tasks that create useful model separation

The current work is still Pipeline A. Do not start Pipeline B task generation yet unless explicitly requested.

## 2. Macro Architecture

The project has two separable but connected pipelines.

### Pipeline A: Source-To-Skill

Input:

- natural language materials
- GDPVal prompt-only task descriptions
- public web materials
- professional guides, cases, or textbooks

Output:

- atomic semantic skill candidates
- deterministic reviewer decisions
- persistent skill registry entries
- typed semantic resource ports
- local skill trace edges
- motif hints
- report-only transition graph and composition readiness

Current Pipeline A should stay report-first and non-destructive. Governance layers can warn, audit, or recommend exclusion, but should not delete registry entries or mutate `SkillRegistryEntry` status fields.

### Pipeline B: Skill-To-Task

Input:

- skill registry
- composition graph / transition priors
- domain and difficulty constraints
- deliverable constraints

Output:

- `TaskBlueprint`
- reference files
- candidate prompt
- `GoldenRun`
- `TrainingAnnotation`
- rubric
- training/evaluation exports

Pipeline B generic implementation is still mostly future work.

## 3. Current Pipeline A Completion Estimate

Approximate current status:

- Node-level Pipeline A MVP: 80-85%
- Scalable registry governance: 60-65%
- Composable skill-graph layer: 40% approximately
- Pipeline A as a substrate for Pipeline B: 65% approximately
- Generic Pipeline B: still low, about 15-20%

The important shift is that Pipeline A is no longer just an atomic skill registry. It now has the first version of a composable graph interface.

## 4. Core Implemented Modules

### Source schema

File:

- `v3_source_schema.py`

Important objects:

- `RawSource`
- `NormalizedSource`
- `SourceBlock`
- `SkillEvidence`
- `SemanticResource`
- `SemanticContract`
- `ExtractedSkillCandidate`
- `SkillTraceEdge`
- `SkillMotifHint`
- `SkillRegistryEntry`

Recent graph additions:

- `SemanticResource`
  - `resource_type`
  - `subtype`
  - `attributes`
  - `domain`
  - `evidence_refs`
- `SemanticContract`
  - still keeps legacy strings:
    - `requires_semantics`
    - `optional_semantics`
    - `provides_semantics`
  - now also has typed ports:
    - `required_resources`
    - `optional_resources`
    - `provided_resources`
- `SkillTraceEdge`
  - local relation between two extracted candidates
  - relation types include local order, fan-in/fan-out, validation, cross-check, motif co-occurrence
- `SkillMotifHint`
  - records task-graph motif evidence
  - current motif types:
    - `fan_in_reconciliation`
    - `policy_application`
    - `exception_escalation`
    - `cross_check_validation`
    - `evidence_to_deliverable`

Backward compatibility:

- Old candidate JSON without typed resources, trace edges, or motif hints should still load.
- Missing graph fields default to empty lists.

### Source collection

Files:

- `v3_source_collector.py`
- `v3_source_search_tools.py`
- `Test/run_v3_stirrup_source_collector.py`
- `Test/run_v3_collected_sources_to_skill_package.py`

Current status:

- SourceCollector MVP exists.
- Default search backend is Serper using `SERPER_API_KEY` from `E:\THU\2026Spring\SRT\rw-task\.env`.
- Brave remains compatible but is not recommended because the current Brave key was invalid.
- Collector writes source materials only. It must not extract skills, generate tasks, write rubrics, or update the registry.

Known smoke output:

- `Test\v3_web_source_collections\audit_smoke_serper_02`
- It collected 3 accepted RawSources and normalized them into a prompt package.

Useful commands:

```powershell
D:\miniconda3\envs\real-world-task\python.exe Test\run_v3_stirrup_source_collector.py --dry-run-prompt --output-dir Test\v3_web_source_collections\dry_run_prompt
```

```powershell
D:\miniconda3\envs\real-world-task\python.exe Test\run_v3_stirrup_source_collector.py --search-backend serper --topic "audit evidence reconciliation and internal control testing" --limit 3 --allow-web-collection --output-dir Test\v3_web_source_collections\audit_smoke_serper_02
```

```powershell
D:\miniconda3\envs\real-world-task\python.exe Test\run_v3_collected_sources_to_skill_package.py --collection-dir Test\v3_web_source_collections\audit_smoke_serper_02
```

If network/API permissions fail, stop and ask the user. Do not use mock collection to pretend real web collection succeeded.

### Skill extraction

Files:

- `v3_skill_extractor.py`
- `Test/run_v3_llm_skill_extractor.py`
- `Test/run_v3_mock_skill_extractor.py`

Providers:

- Tuzi/OpenAI-compatible from `.env`
- DeepSeek official from `deepseek-key.txt`
- mock fallback for offline schema tests only

External LLM upload boundary:

- External extraction requires `--allow-external-upload`.
- For GDPVal prompt-only packages, explicit user approval was requested and granted before running DeepSeek graph calibration.
- Do not upload private/local source packages unless the user explicitly approves.

Current extractor output files:

- `extracted_skill_candidates.json`
- `skill_extraction_report.json`
- `provider_attempts.json`
- `skill_trace_edges.json`
- `skill_motif_hints.json`
- `graph_extraction_diagnostics.json`

Important prompt update:

- LLM output top-level object is now:

```json
{
  "candidates": [],
  "trace_edges": [],
  "motif_hints": []
}
```

- Prompt was tightened after an early smoke run produced typed resources and motif hints but no trace edges.
- The tightened prompt now strongly asks for local trace edges when multiple candidates come from the same source/block and have order, dependency, validation, cross-check, or motif relationships.

### Reviewer

Files:

- `v3_skill_reviewer.py`
- `Test/run_v3_skill_candidate_reviewer.py`
- `Test/run_v3_skill_reviewer_calibration.py`

Reviewer is deterministic, not LLM-based.

It scores/penalizes:

- reusability
- diversity
- semantic clarity
- evidence grounding
- assembly usefulness
- atomicity
- operator leakage
- single-instance overfit
- task-level overbreadth
- broad documentation deliverables
- broad control assessment
- weak action granularity
- source collection leakage

Important behavior:

- `revise` candidates do not enter the persistent registry.
- `suggested_abstraction` is used to tell how to decompose broad candidates.
- Reviewer is a governance filter, not ground truth.

### Persistent registry

Files:

- `v3_skill_registry.py`
- `Test/run_v3_skill_registry_update.py`
- `SkillRegistry/v3_skill_registry.json`

Current persistent registry:

- path: `SkillRegistry/v3_skill_registry.json`
- current entry_count: 66
- sources: GDPVal prompt-only batches and Serper web-source batches
- update is deterministic and idempotent
- duplicate logic currently uses exact name, near-name, and semantic fingerprint matching

Important boundary:

- Recent graph calibration results were not written into the persistent registry.
- The registry was intentionally not changed during graph calibration.

### Registry audit and sampling readiness

Files:

- `v3_skill_registry_audit.py`
- `Test/run_v3_skill_registry_audit.py`
- `v3_registry_sampling_readiness.py`
- `Test/run_v3_registry_sampling_readiness.py`

Reports:

- `SkillRegistry/v3_skill_registry_audit_report.json`
- `SkillRegistry/v3_registry_sampling_readiness_report.json`

Current readiness result from previous run:

- registry entries: 66
- `sample_ready`: 30
- `sample_with_caution`: 7
- `exclude_until_revised`: 29

Readiness remains report-only. It does not add a `status`, `inactive`, or `quarantine` field to registry entries.

### Transition graph and composition readiness

Files:

- `v3_skill_transition_graph.py`
- `Test/run_v3_skill_transition_graph.py`

Reports:

- `SkillRegistry/v3_skill_transition_graph_report.json`
- `SkillRegistry/v3_composition_readiness_report.json`
- Per-run graph calibration reports under extraction-specific output directories

Purpose:

- Build report-only transition priors for future Pipeline B.
- Avoid old all-pairs LLM successor judging.
- Do not write `possible_successors` into `SkillRegistryEntry`.

Current edge score sources:

- local source trace prior
- deterministic resource compatibility
- registry sampling readiness signal
- motif co-occurrence
- weak source-local `resource_compatible` trace evidence

Recent transition graph calibration:

- If an edge involves a `revise` candidate, it stays blocked.
- If deterministic resource matching fails but a local trace edge says `resource_compatible`, the edge can become `caution`, not `usable`.
- This is intentionally a soft prior, not a verified dependency.

### Graph diagnostics and calibration

Files:

- `v3_skill_graph_diagnostics.py`
- `Test/run_v3_skill_graph_diagnostics.py`
- `Test/run_v3_graph_calibration_report.py`

Reports:

- per extraction dir: `graph_extraction_diagnostics.json`
- aggregate: `SkillRegistry/v3_graph_calibration_report.json`

Diagnostics check:

- typed resource count
- typed resource coverage
- trace edge count
- trace candidate coverage
- motif hint count
- motif candidate coverage
- unknown evidence/resource/block/candidate refs
- warnings such as:
  - `missing_required_typed_resources`
  - `missing_provided_typed_resources`
  - `multi_candidate_without_trace_edges`
  - `multi_candidate_without_motif_hints`

Important distinction:

- `is_graph_ready=true` currently means structurally usable, not necessarily high quality.
- Warnings indicate calibration work, not fatal errors.

## 5. Current Key Artifacts And Results

### GDPVal prompt-only graph calibration

Input package:

- `Test\v3_gdpval_prompt_sources\accountants_10\skill_extraction_prompt_package.json`

This package contains:

- GDPVal prompt text
- task id
- sector
- occupation

It does not contain:

- rubric
- reference files
- deliverable files
- answer traces

Extraction output:

- `Test\v3_gdpval_prompt_sources\accountants_10\deepseek_extraction_graph_calibration`

Review output:

- `Test\v3_gdpval_prompt_sources\accountants_10\deepseek_review_graph_calibration`

Transition output:

- `Test\v3_gdpval_prompt_sources\accountants_10\deepseek_transition_graph_calibration`

Extraction result:

- provider: DeepSeek official
- model: `deepseek-v4-flash`
- normalized_source_count: 5
- candidates: 10
- typed resources: 20
- trace edges: 5
- motif hints: 1
- graph diagnostics warnings: none

Candidate names:

- `Compute Audit Sample Size for Statistical Testing`
- `Compute Quarter-over-Quarter Variance Analysis`
- `Select Stratified Audit Sample Based on Multiple Criteria`
- `Aggregate Financial Data by Source Category`
- `Apply Jurisdiction-Specific Tax Withholding Rates`
- `Convert Foreign Currency to Reporting Currency`
- `Compute Amortization Schedule for Prepaid Expenses`
- `Summarize Prepaid Expense and Insurance Balances`
- `Map Tax Document Fields to Filing Form Inputs`
- `Reconcile Accrual Schedules to Trial Balance`

Reviewer result:

- accepted: 8
- revise: 2
- rejected: 0

Revise candidates:

- `Apply Jurisdiction-Specific Tax Withholding Rates`
  - reasons:
    - `form_or_jurisdiction_specific`
    - `task_level_penalty_reduced_by_atomic_contract`
- `Map Tax Document Fields to Filing Form Inputs`
  - reasons:
    - `task_level_overbreadth`
    - `form_or_jurisdiction_specific`
    - `task_level_penalty_reduced_by_atomic_contract`
  - suggested abstraction:
    - `Structured Statutory Filing Input Mapping or Jurisdiction-Specific Compliance Schedule Selection`

Transition graph result after calibration:

- edges: 5
- caution: 2
- blocked: 3
- usable: 0

Interpretation:

- The tightened prompt works on real GDPVal prompt-only data.
- It produces typed resource ports and local traces without graph diagnostics warnings.
- The transition graph is still conservative.
- Some blocked edges are expected because they pass through revised candidates.
- Some caution edges show the current resource compatibility rules need more calibration.

### Public synthetic graph smoke

Old smoke:

- `Test\v3_public_smoke_package\deepseek_graph_smoke`
- candidates: 3
- resources: 9
- trace_edges: 0
- motif_hints: 1
- warning:
  - `multi_candidate_without_trace_edges`

New smoke after prompt tightening:

- `Test\v3_public_smoke_package\deepseek_graph_smoke_v2`
- candidates: 3
- resources: 11
- trace_edges: 2
- motif_hints: 1
- warnings: none
- transition graph:
  - 1 usable
  - 1 caution

Interpretation:

- Prompt tightening successfully induced local trace edges.

### Web-source batch status

Batch report:

- `SkillRegistry\v3_web_source_pipeline_a_batch_report.json`

Current report was a `--reuse-existing --build-transition-graph` run:

- batch_count: 3
- registry before: 66
- registry after: 66
- registry delta: 0
- candidate_count: 17
- accepted_count: 8
- revise_count: 9
- rejected_count: 0
- graph edge_count: 9
- motif_count: 3
- usable_edge_count: 2
- blocked_edge_count: 7

Graph extraction summary for old web-source outputs:

- resource_count: 0
- trace_edge_count: 0
- motif_hint_count: 0
- warning counts:
  - `missing_required_typed_resources`: 3
  - `missing_provided_typed_resources`: 3
  - `multi_candidate_without_trace_edges`: 3
  - `multi_candidate_without_motif_hints`: 3

Interpretation:

- Old web-source outputs were generated before typed resources / trace edges / motif hints existed.
- They are structurally readable but graph-poor.
- The next useful step is to rerun one small web-source batch with the tightened graph prompt.

### Aggregate graph calibration report

Report:

- `SkillRegistry\v3_graph_calibration_report.json`

Current aggregate includes:

- 2 public synthetic DeepSeek smoke runs
- 1 GDPVal prompt-only graph calibration run
- 3 older web-source batch extraction dirs

Current totals:

- extraction dirs: 6
- candidate_count: 33
- resource_count: 40
- trace_edge_count: 7
- motif_hint_count: 3

Warning counts:

- `missing_provided_typed_resources`: 3
- `missing_required_typed_resources`: 3
- `multi_candidate_without_motif_hints`: 3
- `multi_candidate_without_trace_edges`: 4

Interpretation:

- New public smoke and GDPVal calibration outputs are graph-rich and warning-free.
- Old web-source batches dominate the warnings.
- This report is now the main dashboard for graph extraction calibration.

## 6. Important Commands

### Real LLM extraction on GDPVal prompt-only package

Use only after explicit approval for external upload:

```powershell
D:\miniconda3\envs\real-world-task\python.exe Test\run_v3_llm_skill_extractor.py --prompt-package Test\v3_gdpval_prompt_sources\accountants_10\skill_extraction_prompt_package.json --output-dir Test\v3_gdpval_prompt_sources\accountants_10\deepseek_extraction_graph_calibration --provider deepseek --deepseek-model deepseek-v4-flash --allow-external-upload --max-candidates 10 --max-tokens 12000 --timeout-seconds 180
```

### Review graph calibration candidates

```powershell
D:\miniconda3\envs\real-world-task\python.exe Test\run_v3_skill_candidate_reviewer.py --candidates Test\v3_gdpval_prompt_sources\accountants_10\deepseek_extraction_graph_calibration\extracted_skill_candidates.json --output-dir Test\v3_gdpval_prompt_sources\accountants_10\deepseek_review_graph_calibration
```

### Build diagnostics for one extraction dir

```powershell
D:\miniconda3\envs\real-world-task\python.exe Test\run_v3_skill_graph_diagnostics.py --extraction-dir Test\v3_gdpval_prompt_sources\accountants_10\deepseek_extraction_graph_calibration --prompt-package Test\v3_gdpval_prompt_sources\accountants_10\skill_extraction_prompt_package.json
```

### Build transition graph for calibration output

```powershell
D:\miniconda3\envs\real-world-task\python.exe Test\run_v3_skill_transition_graph.py --candidates Test\v3_gdpval_prompt_sources\accountants_10\deepseek_extraction_graph_calibration\extracted_skill_candidates.json --accepted-candidates Test\v3_gdpval_prompt_sources\accountants_10\deepseek_review_graph_calibration\accepted_skill_candidates.json --trace-edges Test\v3_gdpval_prompt_sources\accountants_10\deepseek_extraction_graph_calibration\skill_trace_edges.json --motif-hints Test\v3_gdpval_prompt_sources\accountants_10\deepseek_extraction_graph_calibration\skill_motif_hints.json --transition-report-path Test\v3_gdpval_prompt_sources\accountants_10\deepseek_transition_graph_calibration\skill_transition_graph_report.json --composition-report-path Test\v3_gdpval_prompt_sources\accountants_10\deepseek_transition_graph_calibration\composition_readiness_report.json
```

### Aggregate graph calibration report

```powershell
D:\miniconda3\envs\real-world-task\python.exe Test\run_v3_graph_calibration_report.py --extraction-dir Test\v3_public_smoke_package\deepseek_graph_smoke --extraction-dir Test\v3_public_smoke_package\deepseek_graph_smoke_v2 --extraction-dir Test\v3_gdpval_prompt_sources\accountants_10\deepseek_extraction_graph_calibration --extraction-dir Test\v3_web_source_collections\pipeline_a_batches\audit_evidence_reconciliation\pipeline_a_run\extraction --extraction-dir Test\v3_web_source_collections\pipeline_a_batches\internal_control_testing\pipeline_a_run\extraction --extraction-dir Test\v3_web_source_collections\pipeline_a_batches\compliance_documentation_review\pipeline_a_run\extraction --output-path SkillRegistry\v3_graph_calibration_report.json
```

### Web-source batch reuse with graph reports

```powershell
D:\miniconda3\envs\real-world-task\python.exe Test\run_v3_web_source_pipeline_a_batch.py --allow-web-collection --allow-external-upload --reuse-existing --build-transition-graph
```

### Static checks

```powershell
D:\miniconda3\envs\real-world-task\python.exe -m py_compile v3_source_schema.py v3_skill_extractor.py v3_skill_graph_diagnostics.py v3_skill_transition_graph.py Test\run_v3_skill_graph_diagnostics.py Test\run_v3_graph_calibration_report.py Test\run_v3_skill_transition_graph.py Test\run_v3_llm_skill_extractor.py Test\run_v3_mock_skill_extractor.py Test\run_v3_gdpval_pipeline_a_batch.py Test\run_v3_web_source_pipeline_a.py Test\run_v3_web_source_pipeline_a_batch.py
```

## 7. Current Working Tree Notes

The worktree contains many unrelated dirty files from older experiments. Do not revert them.

Known relevant files changed or added during the recent Pipeline A graph work include:

- `AGENTS.md`
- `docs/architecture/pipeline_architecture_v3.md`
- `docs/architecture/schema_design_v2.md`
- `v3_source_schema.py`
- `v3_skill_extractor.py`
- `v3_skill_graph_diagnostics.py`
- `v3_skill_transition_graph.py`
- `Test/run_v3_skill_graph_diagnostics.py`
- `Test/run_v3_graph_calibration_report.py`
- `Test/run_v3_skill_transition_graph.py`
- `SkillRegistry/v3_graph_calibration_report.json`

There are also generated output directories under:

- `Test\v3_public_smoke_package\deepseek_graph_smoke_v2`
- `Test\v3_public_smoke_package\mock_graph_smoke_v2`
- `Test\v3_gdpval_prompt_sources\accountants_10\deepseek_extraction_graph_calibration`
- `Test\v3_gdpval_prompt_sources\accountants_10\deepseek_review_graph_calibration`
- `Test\v3_gdpval_prompt_sources\accountants_10\deepseek_transition_graph_calibration`

No commit has been made for the most recent graph calibration work in the current handoff state.

## 8. Current Architecture Risks

### Risk 1: Typed resource vocabulary is still small

The current vocabulary works for finance/audit/compliance smoke tests but is not a complete ontology.

Next work should inspect real typed resources and add deterministic aliasing only when repeated failures appear.

### Risk 2: Transition graph is conservative

Current GDPVal calibration produced 5 edges but none `usable`; 2 are `caution` and 3 are `blocked`.

This is acceptable for now. The graph should not overclaim dependency validity. It should expose evidence and uncertainty.

### Risk 3: Motif extraction is sparse

GDPVal calibration produced 1 motif hint covering only one candidate. This may be too sparse for Pipeline B motif sampling.

Next prompt/reasoning calibration should ask for motif hints over small subgraphs, not only isolated candidate signals.

### Risk 4: Old web-source batches are graph-poor

Older web-source extraction outputs have no typed resources, trace edges, or motif hints.

These should be treated as old baselines, not proof that web-source Pipeline A cannot support graph extraction.

### Risk 5: Persistent registry is still node-centric

The registry stores skills, not persistent transition priors.

This is intentional for now. Transition graph remains report-only until we decide the right persistent edge-store format.

## 9. Recommended Next Steps

### Step 1: Rerun one small web-source batch with the tightened graph prompt

Goal:

- verify that public web-source materials now produce typed resources, trace edges, and motif hints like GDPVal prompt-only did

Recommended approach:

- Use one existing collection dir first.
- Do not recollect web sources unless necessary.
- Do not update persistent registry unless explicitly deciding to accept the new batch.

Candidate command shape:

```powershell
D:\miniconda3\envs\real-world-task\python.exe Test\run_v3_web_source_pipeline_a.py --collection-dir Test\v3_web_source_collections\pipeline_a_batches\audit_evidence_reconciliation --output-dir Test\v3_web_source_collections\pipeline_a_batches\audit_evidence_reconciliation\pipeline_a_run_graph_calibration --provider deepseek --deepseek-model deepseek-v4-flash --allow-external-upload --build-transition-graph
```

Important:

- This command may update the persistent registry because the runner currently calls registry update.
- If we want a pure calibration run, add or implement a `--skip-registry-update` / `--dry-run-after-extraction` style flag before running it.
- Safer next engineering step: add a calibration-only mode to `Test/run_v3_web_source_pipeline_a.py`.

### Step 2: Add calibration-only mode to web-source Pipeline A runner

This is probably the best immediate code task.

Desired behavior:

- normalize collection
- run LLM extraction
- run graph diagnostics
- optionally run reviewer
- optionally build transition graph
- do not update persistent registry

Suggested flag:

- `--skip-registry-update`

or:

- `--calibration-only`

This would let us rerun old web-source batches with the new graph prompt without polluting `SkillRegistry/v3_skill_registry.json`.

### Step 3: Improve motif prompt

Current prompt can produce typed resources and trace edges, but motif hints are sparse.

Improve prompt so that when multiple candidates from one source form a task pattern, it emits a motif hint covering the relevant subset.

Example:

- sample-size calculation + variance analysis + sample selection should probably become a motif around audit testing workflow, maybe `cross_check_validation` or `evidence_to_deliverable`
- amortization schedule + balance summary should probably become `evidence_to_deliverable`
- accrual schedules + trial balance should become `fan_in_reconciliation`

### Step 4: Calibrate transition graph compatibility

Current deterministic compatibility sometimes cannot match resources that are intuitively connected.

Do not solve this with all-pairs LLM successor judging.

Better path:

- inspect repeated caution/blocked reasons
- add resource aliases or subtype-to-type rules
- keep LLM trace evidence as weak prior only
- require `usable` edges to have either deterministic compatibility or strong repeated local evidence

### Step 5: Design persistent transition prior store

Only after several batches produce stable graph outputs.

Do not write successors into each `SkillRegistryEntry`.

Preferred direction:

- separate `SkillTransitionPriorStore`
- keyed by from-skill, to-skill, relation type, motif
- stores:
  - observed_count
  - success_count
  - failure_count
  - prior score
  - evidence traces
  - source batches
  - caution/blocked history

### Step 6: Only then start minimal Pipeline B sampler

Pipeline B should sample small graph motifs, not arbitrary skill chains.

Initial sampler should probably:

- read `SkillRegistry/v3_skill_registry.json`
- read readiness report
- read transition graph reports
- avoid `exclude_until_revised`
- prefer `sample_ready`
- sample motif-shaped subgraphs:
  - fan-in reconciliation
  - policy application
  - cross-check validation
  - evidence-to-deliverable

Do not generate full tasks until Pipeline A graph signals are stable enough.

## 10. One-Sentence Handoff Summary

Pipeline A now has source collection, LLM semantic extraction, reviewer, persistent registry, audit/readiness, typed resource ports, trace edges, motif hints, graph diagnostics, and report-only transition graph; the next best step is to add a calibration-only mode for web-source Pipeline A and rerun one small web-source batch with the tightened graph prompt without updating the persistent registry.

