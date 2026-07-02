# TaskGenerator V3 Pipeline Roadmap

## Purpose

The project goal is not to craft one strong finance task.

The goal is to build a batch, automatic, GDPVal-style real-world-task factory for RL training data.

The system should repeatedly produce tasks with:

- realistic source context
- reusable semantic skills
- concrete reference files
- teacher-mode solutions
- executable rubrics
- quality filtering
- evidence of model-separation value

The finance task is now best understood as a prototype used to validate the pipeline. It should not become the center of the project.

## Documentation Map

Current authoritative documents:

- `docs/architecture/pipeline_architecture_v3.md`
  - macro architecture
  - two-pipeline plan
  - batch automation roadmap
  - near-term engineering priorities
- `docs/architecture/schema_design_v2.md`
  - V2 object definitions
  - finance prototype history
  - quality-gate lessons
  - dynamic evaluation notes
- `docs/architecture/pipeline_b_completion_plan_2026-06-30.md`
  - concrete Pipeline B completion plan
  - implementation phases from resource-aware sampling to rw-task export
  - first-slice test plan for the next code change

Historical context documents:

- stage report 1 markdown/pdf files
- stage report 2 markdown files
- stage report 3 markdown files
- stage report 4 markdown/pdf files
- stage report 5 markdown/pdf files

The historical reports are useful for understanding why the project moved away from operator-heavy skill extraction. They should not be treated as the current implementation plan unless their ideas are restated in this roadmap.

Code-facing documents and artifacts:

- `src/task_generator/v2_schema.py`: current V2 structured objects
- `v2_semantic_skills_finance.json`: finance seed skill examples
- `v2_semantic_skills_migrated.json`: migrated historical skill examples
- `src/task_generator/v2_quality_gate.py`: current structural acceptance gate
- `src/task_generator/v2_task_quality.py`: current static quality scorer

Repository layout convention:

- Keep active V2/V3 implementation modules under `src/task_generator/`.
- Keep `Test/` as the current CLI/smoke-runner directory; runners should add repository `src/` to `sys.path` before importing `task_generator`.
- Keep architecture and schema docs under `docs/architecture/`.
- Keep dated handoffs under `docs/handoffs/`.
- Keep stage reports and report images under `docs/reports/`.
- Keep retained run outputs and logs under `artifacts/`, while leaving `SkillRegistry/` as the active registry/report directory for current runners.
- Keep staged package outputs and rw-task draft exports under `artifacts/pipeline_b/scratch/` unless a package is intentionally promoted.

Document maintenance rule:

- put schema changes in `docs/architecture/schema_design_v2.md`
- put project roadmap changes in `docs/architecture/pipeline_architecture_v3.md`
- put experiment results near the relevant prototype section, but convert reusable lessons into pipeline rules

## Core Architecture

The project should be organized as two independent but connected pipelines.

### Pipeline A: Source-To-Skill

Purpose:

- collect real-world materials
- extract reusable semantic skills
- build and maintain a skill registry

Input examples:

- real cases
- textbooks
- professional guides
- public datasets
- GDPVal tasks
- online articles
- exam-style problems
- benchmark samples

Output:

- `RawSource`
- `NormalizedSource`
- `ExtractedSkill`
- `SkillEvidence`
- `SkillRegistryEntry`

This pipeline should be LLM-heavy. The hard problem is semantic abstraction from messy natural language.

### Pipeline B: Skill-To-Task

Purpose:

- sample skills from the registry
- assemble realistic tasks
- generate reference files
- run a teacher solution
- produce training annotations and rubrics
- export to training and evaluation formats

Input:

- selected `SkillRegistryEntry` objects
- domain/template constraints
- difficulty target
- deliverable type

Output:

- `TaskBlueprint`
- reference files
- candidate prompt
- `GoldenRun`
- `TrainingAnnotation`
- rubric
- exported dataset package
- rw-task-compatible case

This pipeline should be hybrid. LLMs are useful for scenario construction, business realism, and teacher solving. Deterministic code is still needed for validation, provenance, packaging, and quality gates.

Current bridge status:

- Pipeline B can now run `seed set -> sampled subgraph -> draft blueprint -> reference-file plan -> generated reference files -> teacher input -> deterministic GoldenRun -> training annotation -> rubric -> quality gate -> staged package -> rw-task-style draft export -> local export validation -> evaluation prep dry-run`.
- The export layer is still structural and conservative.
- `candidate_ready` packages can be formally exported.
- `revise_only` packages are blocked by default and only export as inspection-only drafts when explicitly allowed.
- blocked vs draft vs final export must remain visible in `dataset_row.extra` and the export report.
- Local export validation checks structure and file visibility before any model-backed rw-task evaluation is attempted.
- Evaluation prep dry-run copies only validated cases into a batch-style input directory and records future rw-task commands without executing them.
- the current bottleneck is no longer missing policy reference files; it is mostly Pipeline A signal weakness and partial teacher/readiness chains.

## Pipeline A: Source-To-Skill Design

### 1. SourceCollector

Responsibility:

- use stirrup or another sandboxed agent to search for source materials
- save retrieved content
- preserve source provenance

Minimum output fields:

- `source_id`
- `source_type`
- `domain_tags`
- `url_or_path`
- `retrieved_at`
- `title`
- `raw_text_path`
- `raw_file_paths`
- `collector_model`
- `collection_trace`

Notes:

- This layer should be allowed to use web search.
- It should not extract final skills directly.
- Its output should be auditable and replayable.

### 2. SourceNormalizer

Responsibility:

- convert messy source material into structured chunks
- separate text, table, task, example, formula, and domain-term blocks
- remove collection noise

Minimum output fields:

- `normalized_source_id`
- `source_id`
- `blocks`
- `domain_terms`
- `detected_artifacts`
- `candidate_task_patterns`

This step makes later LLM extraction more stable.

### 3. SkillExtractor

Responsibility:

- extract semantic skills from normalized material
- avoid embedding exact task-generation operators
- attach evidence spans

A skill should describe:

- capability
- business meaning
- required input semantics
- expected output semantics
- hidden difficulty
- common failure modes
- common deliverables
- assembly hints
- evidence source spans

It should not describe:

- exact file names
- exact row counts
- exact generated values
- fixed rubric text
- one-off spreadsheet layouts

Current V3 refinement:

- skills should also avoid being whole GDPVal tasks in disguise
- one source prompt may yield several atomic skill candidates
- `Prepare Form 1040`, `Create a P&L Report`, and `Build an Audit Workbook` are task-level signals, not ideal registry entries
- preferred registry entries are smaller reusable actions such as input mapping, missing-evidence detection, cross-source reconciliation, period allocation, compliance-rule selection, and final-output validation
- broad task-level candidates should be revised into atomic abstractions before registry insertion

### 4. SkillRegistry

Responsibility:

- deduplicate skills
- cluster similar capabilities
- assign difficulty tags
- track domain coverage
- track quality and usage statistics

Minimum fields:

- `skill_id`
- `canonical_name`
- `domain_tags`
- `capability_tags`
- `input_contract`
- `output_contract`
- `hidden_difficulty`
- `failure_modes`
- `evidence_refs`
- `usage_count`
- `accepted_task_count`
- `rejected_task_count`
- `model_separation_stats`

The registry is the bridge between source mining and task generation.

### 5. Composable Skill Graph

Responsibility:

- make registry skills usable by Pipeline B as composable subgraphs rather than isolated nodes
- represent soft successor likelihoods without hardcoding large static successor lists inside each skill
- preserve the old port intuition while avoiding brittle string-equality port matching

Current implementation direction:

- keep `input_contract` and `output_contract`, while adding typed semantic resources with attributes
- model task construction through a skill-resource bipartite graph:
  - a skill requires semantic resources
  - a skill provides semantic resources
  - downstream compatibility is judged through resource type, attributes, domain context, and readiness signals
- store transition evidence outside `SkillRegistryEntry`, currently as report-only graph artifacts
- initialize transition priors from local source traces:
  - if a source naturally yields `A -> B -> C`, then `A -> B` and `B -> C` receive positive prior evidence
  - avoid all-pairs LLM successor generation across the full registry
- let later Pipeline B quality feedback update edge weights:
  - successful tasks increase related transition or motif weights
  - failed tasks decrease them or mark them for review
- use bandit-style exploration only after filtering by readiness and semantic compatibility

Long-term graph objective:

- the current transition graph is a bootstrap report, not the final learnable graph
- the final system should maintain a persistent transition-prior store outside `SkillRegistryEntry`
- that store should accumulate local trace evidence, deterministic resource-compatibility evidence, motif co-occurrence, and later Pipeline B task outcomes
- future priors should track fields such as `observed_count`, `success_count`, `failure_count`, `prior_score`, `posterior_score`, `exploration_bonus`, source batch IDs, and task feedback IDs
- the eventual sampler should predict the next useful skill or subgraph conditioned on the current partial skill graph, not only the last skill
- task structures may be chains, trees, DAG-like plans, or constraint graphs; the sampler should choose executable motifs or subgraphs rather than arbitrary flat skill lists
- UCB1 or another bandit-style policy belongs after feedback exists; before then, reports should remain honest static heuristics

Important distinction:

- a generated task need not be a single chain of skills
- realistic tasks can be trees, DAG-like structures, or constraint graphs with undirected cycles
- the executable solving plan should still be representable as staged dependencies without impossible directed cycles

Initial task graph motifs to prioritize:

- `fan_in_reconciliation`: multiple sources or calculations converge into one reconciliation conclusion
- `policy_application`: policy or rule evidence is extracted, then applied to concrete data
- `exception_escalation`: detect an exception, classify severity, and propose or document response
- `cross_check_validation`: independent evidence paths validate the same conclusion
- `evidence_to_deliverable`: extracted facts and judgments are synthesized into a report, memo, workbook, or checklist

Current graph-layer artifacts:

- `SemanticResource` records `resource_type`, `subtype`, `attributes`, `domain`, and `evidence_refs`
- `SemanticContract` keeps the legacy string fields and adds `required_resources`, `optional_resources`, and `provided_resources`
- `SkillTraceEdge` records local source/package relations such as local order, validation, fan-in, fan-out, and cross-check signals
- `SkillMotifHint` records motif evidence such as reconciliation, policy application, exception escalation, cross-check validation, and evidence-to-deliverable synthesis
- `src/task_generator/v3_skill_graph_diagnostics.py` checks whether extraction outputs are graph-ready by reporting typed resource coverage, trace-edge coverage, motif coverage, and invalid references
- `src/task_generator/v3_skill_transition_graph.py` builds report-only edge priors from local traces, resource compatibility, readiness signals, and motif co-occurrence
- `Test/run_v3_skill_graph_diagnostics.py` writes `graph_extraction_diagnostics.json` for any extraction directory
- `Test/run_v3_skill_transition_graph.py` writes `SkillRegistry/v3_skill_transition_graph_report.json` and `SkillRegistry/v3_composition_readiness_report.json`
- GDPVal and web-source batch runners accept `--build-transition-graph` to generate graph summaries after extraction and review
- web-source runners now also accept `--skip-registry-update` and `--calibration-only`; calibration-only runs extraction, review, graph diagnostics, and transition reports without writing accepted candidates into the persistent registry

Current verified graph-layer smoke results:

- GDPVal accountants offline graph smoke produced 7 transition edges and 1 motif hint, with 2 usable, 3 caution, and 2 blocked edges
- web-source reuse batch with `--build-transition-graph` produced 9 transition edges and 3 motif hints, with 2 usable and 7 blocked edges
- both checks were non-destructive; persistent registry entry_count remained 66 in reuse mode
- first DeepSeek graph smoke before prompt tightening produced typed resources and motif hints but no trace edges; diagnostics flagged `multi_candidate_without_trace_edges`
- after prompt tightening, DeepSeek graph smoke produced 3 candidates, 11 typed resources, 2 trace edges, 1 motif hint, no diagnostics warnings, and a transition graph with 1 usable and 1 caution edge
- existing web-source batch outputs still warn about missing graph extraction fields because they were generated before the graph prompt existed; this is a calibration signal, not a registry mutation
- `Test/run_v3_graph_calibration_report.py` aggregates diagnostics across extraction directories; current aggregate over 2 public DeepSeek smoke runs, 1 GDPVal prompt-only graph calibration run, 3 older web-source batches, and 3 new web-source graph calibration outputs reports 51 candidates, 80 typed resources, 21 trace edges, 9 motif hints, with warnings concentrated in old graph-less outputs
- after explicit user approval, GDPVal `Accountants and Auditors` prompt-only graph calibration with DeepSeek official succeeded:
  - 10 candidates
  - 20 typed resources
  - 5 trace edges
  - 1 motif hint
  - no graph diagnostics warnings
  - reviewer accepted 8 and revised 2
  - transition graph produced 5 edges: 2 caution and 3 blocked
- new web-source graph calibration with `--calibration-only --max-candidates 8` succeeded across all 3 default topics without registry mutation:
  - `audit_evidence_reconciliation`: 5 candidates, 10 typed resources, 3 trace edges, 2 motif hints, no diagnostics warnings
  - `internal_control_testing`: 8 candidates, 16 typed resources, 7 trace edges, 2 motif hints, no diagnostics warnings
  - `compliance_documentation_review`: 5 candidates, 14 typed resources, 4 trace edges, 2 motif hints, no diagnostics warnings
  - every run reported `registry_update_skipped=true`, `registry_entry_delta_this_run=0`, and registry entry_count 66
- transition graph reports now distinguish `edge_scope=registry_mapped` from `edge_scope=candidate_local`; candidate-local edges are expected in calibration-only outputs because accepted candidates have not been persisted into the registry
- the transition graph now treats source-local `resource_compatible` trace evidence as a weak unverified compatibility signal, so an accepted source-supported edge can become `caution` even if deterministic resource matching is incomplete
- the extractor prompt now asks motif hints to cover the relevant local workflow candidate subset, after one web-source calibration run showed full trace coverage but narrower motif coverage
- the next decision point is whether selected accepted calibration candidates should be allowed to enter `SkillRegistry/v3_skill_registry.json`, or remain experiment-only until a persistent transition-prior store is designed
- `Test/run_v3_pipeline_b_seed_set.py` now writes `SkillRegistry/v3_pipeline_b_seed_set_report.json`, a conservative first Pipeline B sampling slice from registry and readiness reports:
  - selected count: 20
  - selected readiness: 20 `sample_ready`
  - selected motif counts: 12 `policy_application`, 8 `evidence_to_deliverable`, 7 `cross_check_validation`, 5 `fan_in_reconciliation`
- `Test/run_v3_calibration_registry_admission.py` now writes `SkillRegistry/v3_calibration_registry_admission_report.json`, a report-only review of graph calibration accepted candidates:
  - 15 accepted candidates reviewed
  - 14 `recommend_admit`
  - 1 `merge_existing`
  - no registry update is performed
- Pipeline A to B handoff is documented in `docs/handoffs/PIPELINE_A_TO_B_HANDOFF_2026-06-30.md`

Remaining closed-loop gaps:

- no persistent `SkillTransitionPriorStore` exists yet; transition edges are still per-run or aggregate reports
- no true probabilistic sampler exists yet; the current Pipeline B sampler is deterministic and report-first, while readiness, motif, role, and edge scores remain static ranking signals
- no UCB1 or bandit update exists yet; there is no reliable reward history until Pipeline B generates and grades tasks
- no Pipeline B feedback updater exists yet; task-generation failures do not yet change skill, edge, or motif weights
- these gaps should be treated as the macro reason for Pipeline B work, not as optional polish

## Pipeline B: Skill-To-Task Design

### 1. SkillSampler

Responsibility:

- select skill combinations from the registry
- control domain, difficulty, novelty, and composability

Sampling should avoid random-only composition. It should prefer combinations with clear dependency structure.

Examples:

- normalize local-currency revenue before aggregation
- resolve missing reference values before final totals
- reconcile source-control totals before producing a client report

Near-term sampler target:

- maintain the current resource-aware, report-first subgraph sampler
- record selected skills, resource nodes, compatibility edges, motif assumptions, and missing Pipeline A signals
- do not claim learned probability or UCB behavior in this first sampler
- preserve enough identifiers for a future prior updater to connect task outcomes back to skills, edges, and motifs

Long-term sampler target:

- sample executable motifs or subgraphs from a persistent transition-prior store
- support conditioned skill-chain or skill-graph prediction, where the next choice depends on the whole partial graph
- balance exploration and exploitation with a bandit policy after enough task feedback exists
- use Pipeline B quality and model-separation evidence to update future sampling weights

### 2. TaskBlueprintAssembler

Responsibility:

- turn selected semantic skills or a sampled `PipelineBSubgraph` into a concrete task plan
- define role, scenario, evidence package, traps, deliverable, and GoldenRun plan

This is a good place for LLM assistance because business realism matters.

The assembler must output structured JSON, not only a prompt.

Current implementation:

- `src/task_generator/v3_pipeline_b_prototype.py` still supports the legacy seed-report path.
- `Test/run_v3_pipeline_b_prototype.py --subgraph-report <pipeline_b_subgraph_report.json>` now consumes a sampled subgraph directly.
- The prototype report preserves `subgraph_id`, `subgraph_confidence`, and `subgraph_missing_signals`.
- The output is still a draft `TaskBlueprint`; reference files, GoldenRun, rubrics, and exports remain future steps.

### 3. ReferenceFileGenerator

Responsibility:

- create concrete files required by the blueprint
- preserve provenance from generated values to GoldenRun targets

Recommended strategy:

- code-led generation for numeric facts and tables
- LLM assistance for realistic wording, notes, emails, memos, and contextual documents
- no unverified LLM-generated numeric backbone unless another validator can check it

Current implementation:

- `src/task_generator/v3_reference_file_planner.py` implements a planning layer before file generation.
- `Test/run_v3_reference_file_planner.py` consumes a draft `TaskBlueprint`, optionally plus `pipeline_b_subgraph_report.json`.
- The planner emits `reference_file_plan.json` with stable file IDs, table IDs, text-section IDs, column IDs, evidence IDs, provenance hooks, and carried-forward subgraph diagnostics.
- `src/task_generator/v3_reference_file_generator.py` now consumes that plan and generates deterministic table-first files where supported.
- `Test/run_v3_reference_file_generator.py` currently generates `source_evidence.xlsx`, writes `generated_file_manifest.json`, `evidence_index.json`, and `generation_trace.json`, and explicitly marks `.docx` references as deferred template work.
- `src/task_generator/v3_teacher_input_builder.py` now consumes the blueprint, subgraph report, plan, generated-file manifest, and Pipeline A feedback.
- `Test/run_v3_teacher_input_builder.py` emits `teacher_input_manifest.json` and `teacher_input_validation_report.json`, separating candidate-visible artifacts from teacher-visible supervision and marking current readiness as `partial_ready`.
- `src/task_generator/v3_teacher_runner.py` now consumes the teacher input artifacts and deterministically emits `golden_run.json`.
- `Test/run_v3_teacher_runner.py` emits `golden_run.json` and `teacher_runner_report.json`; current smoke stays `partial_ready` and makes missing policy references explicit instead of hiding them.
- `src/task_generator/v3_training_annotation_builder.py` now consumes `golden_run.json`, `teacher_runner_report.json`, and `teacher_input_manifest.json`.
- `Test/run_v3_training_annotation_builder.py` emits `training_annotation.json` and `training_annotation_report.json`, including a richer V3 supervision artifact plus an embedded V2-compatible annotation projection.
- `src/task_generator/v3_rubric_builder.py` now consumes the training annotation and teacher outputs and emits a JSON-only `rubric.json`.
- `Test/run_v3_rubric_builder.py` emits `rubric.json` and `rubric_report.json`, preserving `partial_ready`, unresolved gaps, and warning codes instead of flattening them away.
- `src/task_generator/v3_pipeline_b_quality_gate.py` now consumes generated-file, teacher-input, teacher-runner, training-annotation, and rubric reports.
- `Test/run_v3_pipeline_b_quality_gate.py` emits `pipeline_b_quality_report.json`; the current smoke decision is `revise`, not `candidate_ready`, because deferred policy references, policy-lookup warnings, low subgraph confidence, single-source support, and the partial-ready chain remain visible.
- `src/task_generator/v3_pipeline_b_package_assembler.py` now stages gated artifacts into a package directory.
- `Test/run_v3_pipeline_b_package_assembler.py` emits `package_manifest.json` and `dataset_row_draft.json`; the current smoke package is `revise_only`, copies the generated workbook, and preserves the deferred policy document blocker.

### 4. TeacherRunner / GoldenRun

Responsibility:

- solve the task in teacher mode
- produce canonical deliverables or canonical answer objects
- emit intermediate states
- emit grading anchors
- emit rubric candidates

There should be two GoldenRun modes:

- deterministic oracle mode for templates where code can solve the task
- LLM teacher mode for open-ended tasks

Current implementation:

- `src/task_generator/v3_teacher_runner.py` implements the first deterministic TeacherRunner scaffold.
- It turns teacher intentions, required intermediate states, evidence contracts, and validation warnings into teacher-visible intermediate states, skill-linked golden steps, and final checks.
- The current runner is intentionally honest about partial readiness: even after the deterministic `policy_reference.docx` path is generated, low-confidence sampled subgraphs and support-evidence limits still keep steps `partial` instead of inventing full teacher truth.
- `src/task_generator/v3_training_annotation_builder.py` now turns those teacher artifacts into supervision items, failure modes, hidden traps, unresolved gaps, and a V2-compatible `TrainingAnnotation` projection.
- `src/task_generator/v3_rubric_builder.py` now turns supervision items, failure modes, rubric projections, and unresolved gaps into structured fact, reasoning, robustness, and compliance sections.
- The current rubric is a structured-ready contract, not an executable grader.
- `src/task_generator/v3_pipeline_b_quality_gate.py` now turns the current deterministic artifact reports into a package-level decision before any export or LLM teacher/prose step.

LLM teacher mode should use more information than the candidate:

- revealed traps
- expected intermediate states
- source provenance
- hidden constraints
- teacher-only checklist

But exact grading targets should still be traceable to candidate-visible evidence unless they are explicitly marked as teacher-only supervision.

Current LLM timing policy:

- Quality Gate V1 does not call LLMs or external APIs.
- LLM teacher mode should be scheduled after package readiness is explicit, or under a later explicit partial-teacher exploration mode.
- LLM output is a teacher proposal or prose/reference-document draft; it is not grading truth by itself.
- Grading truth must be validated against candidate-visible evidence or explicitly labeled teacher-only.

### 5. RubricBuilder

Responsibility:

- convert GoldenRun outputs into executable or semi-executable grading criteria
- separate result checks from reasoning checks
- record tolerance and evidence source

Rubrics should not be only prose. They should include machine-readable anchors.

### 6. QualityGate

Responsibility:

- read deterministic Pipeline B reports
- decide whether the current package should be `reject`, `revise`, or `candidate_ready`
- preserve high-signal reason codes for later batch filtering and feedback updates
- prevent downstream export or expensive model calls from hiding partial readiness

Current implementation:

- `src/task_generator/v3_pipeline_b_quality_gate.py` implements the first deterministic quality gate.
- `Test/run_v3_pipeline_b_quality_gate.py` writes `pipeline_b_quality_report.json`.
- The current smoke package is expected to be `revise`, now driven by `low_subgraph_confidence`, `single_source_support`, `partial_intermediate_state`, `pipeline_a_signal_gaps`, and `partial_ready_chain`.

### 7. PackageAssembler

Responsibility:

- collect the gated artifacts into a stable package directory
- copy generated candidate-visible reference files
- preserve deferred or missing reference files as package blockers
- emit a draft dataset row for export inspection without claiming final rw-task readiness

Current implementation:

- `src/task_generator/v3_pipeline_b_package_assembler.py` implements the first staging layer.
- `Test/run_v3_pipeline_b_package_assembler.py` writes `package_manifest.json` and `dataset_row_draft.json`.
- The current smoke package is `revise_only`, because the quality gate still returns `revise`; the deterministic policy document now exists, and the remaining blockers come from Pipeline A signal weakness rather than a missing reference file.

### 8. ExportAdapter

Responsibility:

- export the same core sample to multiple downstream formats

Targets:

- training package
- rw-task package
- inspection package
- debugging package

## Quality Funnel

Batch generation requires a funnel. Full model evaluation cannot run on every sample.

Recommended funnel:

1. schema validation
2. source provenance validation
3. reference-file sanity check
4. GoldenRun completion check
5. grading-anchor consistency check
6. static quality score
7. cheap baseline model smoke test
8. selective strong-model evaluation
9. retain / revise / discard decision

Each rejected sample should produce a reason code. Rejection reasons are training data for improving the generator.

## Batch Automation Loop

The intended loop is:

1. collect source materials
2. extract and register skills
3. sample skill combinations
4. assemble task blueprints
5. generate reference files
6. run GoldenRun
7. build rubric and exports
8. run quality funnel
9. evaluate selected samples with real models
10. update skill and template statistics

The unit of progress should be a batch, not a single hand-tuned sample.

Suggested initial batch size:

- 10 source materials
- 30 extracted skills
- 10 generated task blueprints
- 5 structurally accepted tasks
- 2 expensive model-evaluated tasks

## What The Finance Prototype Contributes

The finance prototype has already produced useful engineering lessons:

- GDPVal-style tasks should often require a new deliverable, not template filling
- GoldenRun needs intermediate states, not only final answers
- exact numeric grading must be grounded in visible evidence or clearly marked teacher-only
- provider instability means full model evaluation belongs late in the funnel
- static scoring is useful but cannot replace dynamic model-separation evidence

These lessons should become pipeline rules.

They should not lead to endless manual polishing of the same finance task.

## Current Engineering Gaps

### Missing in Pipeline A

- typed semantic resource ports beyond the current natural-language `input_contract` and `output_contract`
- source-trace extraction that records local skill order, parallel branches, fan-in, fan-out, and validation relationships
- transition prior storage outside individual skill nodes
- compatibility scoring that combines semantic resources, domain context, readiness, and local transition evidence
- motif discovery and motif readiness reports for common GDPVal-style task structures
- feedback hooks from future Pipeline B quality results back into transition and motif weights

### Missing in Pipeline B

- persistent/probabilistic skill sampler beyond the current deterministic subgraph sampler
- full generic blueprint assembler beyond the current report-first subgraph-to-blueprint prototype
- broader reference-file generation beyond the current table-first deterministic slice
- actual teacher-mode execution beyond the current pre-TeacherRunner contract
- rubric builder that consumes teacher outputs
- provenance checks from rubric anchors back to source files
- batch orchestration CLI
- persistent batch reports

### Existing Assets To Reuse

- `src/task_generator/v2_schema.py`
- `src/task_generator/v2_task_compiler.py`
- `src/task_generator/FileGenerator/v2_blueprint_generator.py`
- `src/task_generator/v2_golden_run.py`
- `src/task_generator/v2_quality_gate.py`
- `src/task_generator/v2_task_quality.py`
- `src/task_generator/rw_task_adapter.py`
- `Test/run_v2_batch_funnel.py`
- `Test/run_v2_finance_optimization_playbook.py`

These are useful, but they currently represent a finance-specific path. They should be generalized after Pipeline A is introduced.

## Near-Term Plan

### Phase 1: Documentation And Contracts

Goal:

- make the architecture explicit before adding more code

Deliverables:

- this roadmap
- schema additions for source-to-skill objects
- a documented batch directory layout
- a documented sample lifecycle

### Phase 2: Minimal Source-To-Skill Prototype

Goal:

- prove that source collection and skill extraction can feed the registry

Deliverables:

- `src/task_generator/v3_source_schema.py`
- `SourceCollector` runner
- `SourceNormalizer` runner
- `SkillExtractor` runner
- a small extracted skill registry from 5-10 finance/audit sources

Current implementation status:

- `src/task_generator/v3_source_schema.py` defines the first source-to-skill schema layer:
  - `RawSource`
  - `NormalizedSource`
  - `SourceBlock`
  - `SourceSpan`
  - `SkillEvidence`
  - `ExtractedSkillCandidate`
  - `SkillRegistryEntry`
  - `SkillExtractionPromptPackage`
- `src/task_generator/v3_source_collector.py` implements the first SourceCollector contract layer:
  - `SourceCollectionRequest`
  - `CollectedSourceRecord`
  - `SourceCollectionReport`
  - source collection prompt builder
  - manifest validator
  - RawSource writer
- `src/task_generator/v3_source_search_tools.py` provides a Serper-backed Stirrup-compatible search/fetch provider:
  - default search backend is now `serper`
  - `SERPER_API_KEY` is read from the `rw-task` env file
  - Brave remains an optional compatibility backend, but is not required for the default path
- `Test/run_v3_stirrup_source_collector.py` provides a Stirrup/E2B-backed collection CLI:
  - defaults to `E:\THU\2026Spring\SRT\rw-task\.env`
  - requires explicit `--allow-web-collection` for real web access
  - supports `--dry-run-prompt` for local prompt/request inspection
  - supports `--search-backend serper|brave`
  - uses the `rw-task` Stirrup/E2B environment rather than a separate key path
- `Test/run_v3_collected_sources_to_skill_package.py` connects collected `RawSource` records to the existing normalization and skill prompt package flow
- `Test/run_v3_web_source_pipeline_a.py` runs Pipeline A on an existing collected web-source directory:
  - consumes collected `RawSource` records and does not call Serper/E2B again
  - writes source quality diagnostics before LLM extraction
  - normalizes the collection into a `SkillExtractionPromptPackage`
  - calls external LLM extraction only with explicit `--allow-external-upload`
  - runs deterministic review and updates the persistent registry from accepted candidates only
  - supports `--skip-registry-update` for report-only calibration runs
  - supports `--calibration-only`, equivalent to skipping registry update and building transition graph reports
  - emits `web_source_pipeline_a_report.json`
- `Test/run_v3_web_source_pipeline_a_batch.py` runs Pipeline A across multiple web-source topics or existing collection directories:
  - calls SourceCollector for new topics
  - reuses existing collection and extraction outputs with `--reuse-existing`
  - writes an aggregate source-quality and registry-growth report
  - keeps collection, extraction, review, and registry update as separate per-topic artifacts
  - forwards `--skip-registry-update` and `--calibration-only` so graph calibration can run without persistent registry growth
- `Test/run_v3_local_source_to_skill.py` provides a local no-network prototype:
  - reads `.txt` and `.md` files
  - creates `RawSource` records
  - splits text into normalized blocks
  - emits a skill-extraction prompt package for a later LLM step
- `src/task_generator/v3_skill_extractor.py` provides a deterministic mock extractor:
  - consumes `SkillExtractionPromptPackage`
  - emits `ExtractedSkillCandidate` objects
  - is intended for pipeline testing, not final research-quality extraction
- `src/task_generator/v3_skill_extractor.py` also provides an LLM-backed extractor interface:
  - `BaseSkillExtractor`
  - `LLMSkillExtractor`
  - `FallbackSkillExtractor`
  - Tuzi/OpenAI-compatible provider config from `.env`
  - DeepSeek official fallback config from `deepseek-key.txt`
- `Test/run_v3_mock_skill_extractor.py` runs the mock extractor from the command line
- `Test/run_v3_llm_skill_extractor.py` runs provider selection and fallback:
  - `auto`: Tuzi/OpenAI-compatible provider, then DeepSeek official, then mock
  - `tuzi`: only the `.env` provider unless mock fallback is explicitly allowed
  - `deepseek`: only DeepSeek official unless mock fallback is explicitly allowed
  - `mock`: deterministic offline extractor
  - external providers require `--allow-external-upload`
- `Test/build_v3_public_smoke_package.py` creates a hand-written public synthetic source package for safe external API smoke tests
- `Test/v3_public_smoke_package` stores the public synthetic source package; generated extraction/registry outputs are ignored
- `Test/build_v3_gdpval_prompt_sources.py` builds GDPVal prompt-only source packages:
  - reads task prompt, task id, sector, and occupation only
  - excludes rubric, reference files, deliverable files, answer traces, and file contents
  - prefers direct local Arrow cache loading to avoid unnecessary HuggingFace network calls
- `Test/run_v3_gdpval_pipeline_a_batch.py` runs a GDPVal prompt-only Pipeline A batch:
  - builds prompt-only packages
  - calls an external LLM extractor without mock fallback
  - runs deterministic review
  - updates the persistent registry
  - emits an aggregate batch report
- `src/task_generator/v3_skill_reviewer.py` provides a deterministic first-pass candidate reviewer:
  - scores reusability, diversity, semantic clarity, evidence grounding, and assembly usefulness
  - penalizes operator leakage and single-instance overfit
  - now also scores atomicity and penalizes task-level overbreadth, form-specific candidates, and jurisdiction-bound candidates
  - emits `suggested_abstraction` for candidates that should be revised into smaller reusable capabilities
- `Test/run_v3_skill_candidate_reviewer.py` emits reviewed candidates, accepted candidates, and review reports
- `src/task_generator/v3_skill_registry.py` provides a deterministic registry builder and persistent registry updater:
  - converts candidates into `SkillRegistryEntry` records
  - performs deterministic exact-name, near-name, and semantic-fingerprint deduplication
  - updates the persistent JSON registry at `SkillRegistry/v3_skill_registry.json`
  - emits coverage and possible-duplicate reports
- `Test/run_v3_skill_registry_builder.py` builds `skill_registry.json` from extracted candidates
- `Test/run_v3_skill_registry_update.py` updates the persistent registry from one or more candidate files
- smoke-test output exists under `Test/v2_outputs/v3_source_to_skill_demo`

What is intentionally not done yet:

- SourceCollector does not extract skills, generate tasks, write rubrics, or update the registry
- no large-scale web crawling
- source quality diagnostics are lightweight checks, not a source-quality truth model
- direct DeepSeek smoke testing has passed on the public synthetic package
- GDPVal prompt-only extraction has passed on 5 `Accountants and Auditors` prompts:
  - provider: DeepSeek official `deepseek-v4-flash`
  - candidates produced: 5
  - reviewer accepted: 5
  - registry entries produced: 5
- that first GDPVal run is now considered a successful plumbing test but a weak skill-quality target because it produced mostly task-level skills rather than atomic skills
- after adding the atomic extraction prompt and stricter reviewer, the same GDPVal prompt-only package produced:
  - 12 DeepSeek candidates with `--max-candidates 30`
  - 10 accepted atomic or near-atomic candidates
  - 2 revise candidates:
    - `Build Structured Profit and Loss Report from Multiple Sources`
    - `Map Tax Documents to IRS Form Fields`
  - 10 registry entries in the per-run atomic batch registry
- external testing on private workspace source packages should remain blocked unless the source package is explicitly approved for upload
- no semantic embedding or LLM-based registry deduplication
- accepted/rejected skill review loop exists and feeds a persistent unified registry
- current Pipeline A completion estimate:
  - node-level Pipeline A MVP: about 85%
  - scalable registry governance: about 65-70%
  - composable skill-graph layer: about 45%
  - overall Pipeline A as a substrate for Pipeline B: about 70%
- current persistent registry status:
  - path: `SkillRegistry/v3_skill_registry.json`
  - sources: accepted candidates from GDPVal prompt-only batches and Serper web-source finance/audit/compliance batches
  - entry_count: 66
  - repeated update with the same batch outputs is idempotent for entry count and source candidate IDs
  - revised candidates do not enter the persistent registry
- current GDPVal Pipeline A batch result:
  - batch runner path: `Test/run_v3_gdpval_pipeline_a_batch.py`
  - aggregate report path: `SkillRegistry/v3_pipeline_a_batch_report.json`
  - successful new batches: `Financial Managers`, `Financial and Investment Analysts`, `Compliance Officers`
  - after reviewer calibration and `--reuse-existing` rerun:
    - `Financial Managers`: 14 candidates, 11 accepted, 3 revise
    - `Financial and Investment Analysts`: 15 candidates, 11 accepted, 4 revise
    - `Compliance Officers`: 8 candidates, 6 accepted, 2 revise
  - final registry coverage includes `finance=40`, `compliance=7`, `government=7`, `accounting=5`, `audit=4`
  - `max_candidates=30` can trigger DeepSeek JSON truncation on some batches; the batch runner default is now `max_candidates=15`, `max_tokens=12000`
- current batch diagnostics:
  - aggregate report records reason-code counts, batch warnings, suspicious accepted candidates, provider/model/parameter metadata, and reuse mode
  - `source_collection_leakage` now flags open-web retrieval candidates as reviewer revise rather than registry-ready skills
  - the latest report has 1 suspicious accepted candidate: `Write Exception Statements for Regulatory Non-Compliance Findings`
  - the registry update report now lists 6 unmatched existing entries that remain in the persistent registry but are not touched by the stricter accepted-candidate rerun
- current registry audit status:
  - `src/task_generator/v3_skill_registry_audit.py` implements a non-destructive deterministic audit helper
  - `Test/run_v3_skill_registry_audit.py` writes `SkillRegistry/v3_skill_registry_audit_report.json`
  - the audit reads `SkillRegistry/v3_skill_registry.json` and the latest update report, but does not change the registry
  - default audit scope is the 6 `unmatched_existing_entries`; `--include-all` audits the full registry
  - current audit result is 6 audited entries and 6 `quarantine_recommended` governance hints
  - audit reasons include `source_collection_leakage`, `broad_deliverable_or_task_level`, `visual_or_presentation_deliverable`, `weak_atomic_action`, and `stale_due_to_reviewer_calibration`
  - audit decisions are not quality truth and do not mark entries inactive; they are pre-sampling warnings for future Pipeline B
- current SourceCollector smoke status:
  - Serper API direct test returned `status=200` and organic search results
  - `Test/run_v3_stirrup_source_collector.py --search-backend serper` succeeded on `audit_smoke_serper_02`
  - result: 3 requested sources, 3 collected sources, 3 accepted RawSources, `search_backend=serper`
  - connector produced `normalized_package/skill_extraction_prompt_package.json`
  - first failed Serper run exposed a Windows console encoding issue and an overly loose collection prompt; both were tightened before the successful run
- current web-source Pipeline A smoke status:
  - runner path: `Test/run_v3_web_source_pipeline_a.py`
  - input collection: `Test/v3_web_source_collections/audit_smoke_serper_02`
  - source quality status: `pass`
  - DeepSeek official `deepseek-v4-flash` produced 5 candidates
  - deterministic reviewer accepted 5, revised 0, rejected 0
  - persistent registry update added 5 new entries and raised entry_count from 44 to 49
  - rerunning with `--reuse-existing` produced 0 new entries and 5 merged candidates, keeping entry_count at 49
- current web-source Pipeline A batch status:
  - runner path: `Test/run_v3_web_source_pipeline_a_batch.py`
  - aggregate report path: `SkillRegistry/v3_web_source_pipeline_a_batch_report.json`
  - default topics: `audit evidence reconciliation`, `internal control testing`, `compliance documentation review`
  - formal batch collected 9 sources across 3 topics and all 3 source-quality reports passed
  - DeepSeek official `deepseek-v4-flash` produced 17 candidates
  - the first reviewer pass accepted 17, revised 0, rejected 0; this was treated as a calibration warning
  - after reviewer calibration, the same 17 candidates review as 8 accept, 9 revise, 0 reject
  - new reason codes include `broad_documentation_deliverable`, `broad_control_assessment`, and `weak_action_granularity`
  - persistent registry reached entry_count 66
  - idempotency rerun with `--reuse-existing` now reports run mode, registry count before/after, 0 entry delta, and 8 merged candidates under the calibrated reviewer
  - `idempotency_no_growth_expected` distinguishes expected no-growth reuse runs from true quality no-growth warnings
- current Pipeline A quality governance status:
  - `Test/run_v3_skill_reviewer_calibration.py` writes `SkillRegistry/v3_skill_reviewer_calibration_report.json`
  - web-source candidate-file audit writes `SkillRegistry/v3_web_source_registry_audit_report.json`
  - candidate-file audit uses deterministic registry candidate refs and avoids broad matching on non-unique raw candidate IDs
  - audit marks web-derived entries with `web_source_batch_governance_attention` but does not modify registry entries
  - `src/task_generator/v3_registry_sampling_readiness.py` and `Test/run_v3_registry_sampling_readiness.py` now turn registry, audit, and calibration signals into a pre-sampling report
  - readiness report path: `SkillRegistry/v3_registry_sampling_readiness_report.json`
  - current readiness result on 66 registry entries: 30 `sample_ready`, 7 `sample_with_caution`, 29 `exclude_until_revised`
  - readiness is report-only; it does not add registry status fields, delete entries, or quarantine entries in-place
  - `single_source_support` is treated as a sampling-weight signal rather than a blocking quality failure

The immediate Pipeline A-to-B bridge is now available at the node level: future Pipeline B should read the sampling readiness report before selecting skills. The next Pipeline A target is graph-level composability: new source materials should produce not only accepted atomic skills, but also semantic resource ports, local transition traces, and motif hints that can support tree/DAG-style task assembly.

The graph-level bridge is now strong enough for a minimal Pipeline B prototype, but not yet for broad Pipeline B task generation. Web-source graph calibration remains experiment-only until an explicit registry-entry decision is made.

### Phase 3: Batch Skill-To-Task Prototype

Goal:

- generate tasks from registry entries rather than hand-selected hardcoded skills

Deliverables:

- `SkillSampler`
- batch `TaskBlueprint` assembler
- batch generator CLI
- batch report with accepted/rejected samples

### Phase 4: LLM TeacherRunner

Goal:

- implement real teacher-mode task solving

Deliverables:

- `TeacherRunRequest`
- `TeacherRunResult`
- `LLMTeacherRunner`
- teacher output validator
- rubric candidate builder

This is the major missing piece for tasks that cannot be solved deterministically.

### Phase 5: Closed-Loop Dataset Factory

Goal:

- turn generation and evaluation into a repeatable dataset production loop

Deliverables:

- batch dashboard
- model-separation reports
- rejection-reason analytics
- skill coverage reports
- retained training-data export

## Immediate Next Step

Pipeline A has reached a handoff point, and the first Pipeline B bridge is now working through subgraph sampling, draft blueprint assembly, reference-file planning, deterministic workbook generation, deterministic policy-reference doc generation, a teacher-input contract, a deterministic TeacherRunner, a deterministic training-annotation layer, a structured rubric layer, a package-level quality gate, and a staged package assembler. The next implementation step should either wire `rw-task` export to this package format or broaden the generation contract toward more file types and future LLM/Stirrup strategies.

Recommended next code tasks:

- keep using `Test/run_v3_pipeline_b_subgraph_sampler.py` to produce `pipeline_b_subgraph_report.json`
- keep using `Test/run_v3_pipeline_b_prototype.py --subgraph-report ...` to produce the draft `TaskBlueprint`
- keep using `Test/run_v3_reference_file_planner.py` to produce `reference_file_plan.json`
- keep using `Test/run_v3_reference_file_generator.py` to produce `reference_files/`, `generated_file_manifest.json`, `evidence_index.json`, and `generation_trace.json`
- keep the reference-file manifest contract extensible so deterministic, LLM, Stirrup, and imported file generators can all report through the same artifact shape
- keep using `Test/run_v3_teacher_input_builder.py` to produce `teacher_input_manifest.json` and `teacher_input_validation_report.json`
- keep using `Test/run_v3_teacher_runner.py` to produce `golden_run.json` and `teacher_runner_report.json`
- keep using `Test/run_v3_training_annotation_builder.py` to produce `training_annotation.json` and `training_annotation_report.json`
- keep using `Test/run_v3_rubric_builder.py` to produce `rubric.json` and `rubric_report.json`
- keep using `Test/run_v3_pipeline_b_quality_gate.py` to produce `pipeline_b_quality_report.json`
- keep using `Test/run_v3_pipeline_b_package_assembler.py` to produce `package_manifest.json` and `dataset_row_draft.json`
- wire a `rw-task` export adapter to the staged package, gated by package readiness
- continue marking prose-heavy `.docx` references as deferred until a separate template/document slice is ready
- carry missing Pipeline A fields and low-confidence fallback diagnostics into teacher mode rather than hiding them
- keep graph calibration outputs experiment-only until a later explicit decision allows selected candidates to update the persistent registry
- continue improving resource compatibility and motif coverage only in response to Pipeline B assembly failures

The implementation should deliberately avoid two traps:

- do not keep expanding Pipeline A in isolation once Pipeline B can reveal what signals are actually missing
- do not implement a fake bandit sampler before task-quality feedback exists; first log the feedback contract, then learn from it

This will reconnect the project to the original two-pipeline design:

- natural language to semantic skill library
- semantic skill library to batch real-world tasks
