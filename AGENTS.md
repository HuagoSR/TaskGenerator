# TaskGenerator Project Notes For Future Agents

## Project Goal

This repository is part of a research project to automatically produce GDPVal-style real-world tasks for RL training.

The goal is not to handcraft one good task. The goal is a batch, automatic task factory that can repeatedly produce high-quality real-world tasks with:

- realistic source context
- reusable semantic skills
- concrete reference files
- teacher-mode solutions
- executable rubrics
- quality filtering
- evidence that different models separate meaningfully on the tasks

The current working directory is:

- `E:\THU\2026Spring\SRT\TaskGenerator`

The broader project also uses:

- `E:\THU\2026Spring\SRT\rw-task` for evaluation
- `E:\THU\2026Spring\SRT\GDPVal` for GDPVal reference material

## Current Macro Architecture

The project should be treated as two connected but separable pipelines.

### Pipeline A: Source-To-Skill

Input:

- natural-language materials
- real cases
- textbooks
- professional guides
- public datasets
- GDPVal samples
- online articles or benchmark tasks

Output:

- structured semantic skills
- evidence-backed skill registry entries

This pipeline should be LLM-heavy. Its hard problem is semantic abstraction from messy real-world text.

Expected objects:

- `RawSource`
- `NormalizedSource`
- `SourceBlock`
- `ExtractedSkillCandidate`
- `SkillEvidence`
- `SkillRegistryEntry`

### Pipeline B: Skill-To-Task

Input:

- skill registry entries
- domain constraints
- difficulty target
- deliverable type

Output:

- `TaskBlueprint`
- reference files
- candidate prompt
- `GoldenRun`
- `TrainingAnnotation`
- rubric
- training export
- rw-task-compatible export

This pipeline should be hybrid. LLMs are useful for scenario construction and teacher solving. Deterministic code is needed for validation, provenance, packaging, and quality gates.

## Important Current Documents

Read these first:

- `docs/architecture/pipeline_next_stage_global_plan.md`: newest macro plan and the current source of truth for next-stage priorities
- `docs/architecture/global_interface_contracts.md`: next-stage report-only/schema-first interface contracts derived from the global plan
- `docs/architecture/pipeline_architecture_v3.md`: current macro roadmap and future plan
- `docs/architecture/schema_design_v2.md`: V2 schema details, finance prototype history, and evaluation lessons
- `docs/architecture/pipeline_b_completion_plan_2026-06-30.md`: concrete execution plan for completing Pipeline B

Priority rule:

- Treat `pipeline_next_stage_global_plan.md` as the current strategic guide.
- Treat `pipeline_architecture_v3.md`, `schema_design_v2.md`, and `pipeline_b_completion_plan_2026-06-30.md` as still-useful architecture and implementation history, but do not let their older "next slice" language override the newer global plan.
- If a detail in the global plan conflicts with implemented code, correct the detail conservatively while preserving the plan's macro direction: workflow-conditioned task generation, report-only diagnostics first, and controlled promotion later.

Older stage reports are useful history, especially for why the project moved away from operator-heavy skill extraction, but they are not the current plan unless restated in `docs/architecture/pipeline_architecture_v3.md`.

## Repository Layout And Storage Rules

Keep the repository organized by separating active code, authoritative docs, durable reports, and generated artifacts.

Root directory:

- Keep only project coordination files and stable top-level directories here.
- Active implementation code now lives under `src/task_generator/`.
- Do not add new root-level implementation modules. New reusable modules should be package modules under `src/task_generator/`.
- Do not add new stage reports, screenshots, experiment dumps, notebooks, one-off prompts, or generated outputs to the root directory.

Documentation:

- `docs/architecture/` stores authoritative architecture and schema documents, currently:
  - `docs/architecture/pipeline_architecture_v3.md`
  - `docs/architecture/schema_design_v2.md`
- `docs/handoffs/` stores dated handoff documents, such as Pipeline A and Pipeline A-to-B handoffs.
- `docs/reports/stage_reports/` stores historical stage reports in Markdown or PDF form.
- `docs/reports/assets/` stores images used by reports. Stage report image links should be relative to the report, for example `../assets/image.png`.
- `docs/examples/` stores small static example JSON files that are useful for explanation but are not active generated outputs.

Artifacts and generated outputs:

- `artifacts/pipeline_b/` stores Pipeline B prototype outputs and other retained Pipeline B run artifacts.
- `artifacts/archive/` stores historical logs or generated evidence that should be preserved but should not live beside active code.
- `SkillRegistry/` remains the active registry/report directory for Pipeline A and Pipeline B runners. Do not move registry JSON reports unless the runner defaults and documentation are migrated in the same change.
- `Test/v2_outputs/`, `Test/v3_gdpval_prompt_sources/`, and `Test/v3_web_source_collections/` are generated-output locations and should stay ignored unless a specific small artifact is intentionally promoted.

Code and runner placement:

- Keep reusable implementation modules under `src/task_generator/`, using imports like `from task_generator.v3_source_schema import ...`.
- Keep command-line runners under `Test/` for now. Runners should prepend the repository `src/` directory to `sys.path` before importing `task_generator`.
- Keep legacy operator-heavy code under `src/task_generator/Skill/`; do not mix new Pipeline A/B modules into `src/task_generator/Skill/` unless the work is explicitly about that legacy path.
- Keep reference-file generator code under `src/task_generator/FileGenerator/` and prompt assembly utilities under `src/task_generator/Prompt/`.
- Preserve obsolete or research-evidence code under `artifacts/archive/` instead of leaving it beside active package code.

Cleanliness rules:

- New generated outputs should go under `artifacts/` or an ignored `Test/...` generated-output directory, not root.
- New persistent design docs should go under `docs/architecture/`, `docs/handoffs/`, or `docs/reports/` as appropriate.
- Temporary logs should not be committed from active code directories. If a log has research value, move it to `artifacts/archive/`.
- Repo `.env` is secret-bearing and must never be committed. Always keep `.env` out of staged files and commits.
- Do not print API keys, bearer tokens, or full secret values from `.env` into logs, reports, smoke outputs, examples, or documentation. Only mention variable names when necessary.
- At the end of each completed phase, it is fine to create a focused commit for that phase, but confirm `.env` is excluded before staging.
- Update `AGENTS.md` and the relevant architecture docs whenever a path becomes an expected project convention.

## Current Code State

Useful existing assets:

- `src/task_generator/v2_schema.py`: current V2 structured objects
- `v2_semantic_skills_finance.json`: finance seed skills
- `v2_semantic_skills_migrated.json`: migrated historical skills
- `src/task_generator/v2_task_compiler.py`: finance-specific skill-to-task compiler prototype
- `src/task_generator/FileGenerator/v2_blueprint_generator.py`: finance-specific reference file generator
- `src/task_generator/v2_golden_run.py`: deterministic finance GoldenRun prototype
- `src/task_generator/v2_quality_gate.py`: structural acceptance gate
- `src/task_generator/v2_task_quality.py`: static quality scorer
- `src/task_generator/rw_task_adapter.py`: rw-task export adapter
- `Test/run_v2_batch_funnel.py`: batch funnel runner
- `Test/run_v2_finance_optimization_playbook.py`: finance optimization report runner

These are useful prototypes, but many are finance-specific. Future work should generalize the pipeline rather than keep polishing a single finance task.

## Lessons From The Finance Prototype

Do preserve these lessons:

- GDPVal-style tasks often require creating a new deliverable file, not filling an output template.
- `GoldenRun` needs intermediate states, not only final answers.
- Exact numeric grading should be grounded in candidate-visible evidence, unless a target is explicitly teacher-only.
- Provider/model instability is real, so expensive rw-task evaluation should happen late in the funnel.
- Static scoring is useful for filtering but cannot replace dynamic model-separation evidence.

Do not overfit to the current music-tour finance task. It was a probe, not the final product.

## Current Priority

The current priority is the next-stage global plan: move from a mostly skill-pipeline view to a workflow-conditioned, closed-loop real-world task factory.

Current status snapshot as of `2026-07-06`:

- Phase 0-10 global interface, verifier, promotion, dashboard, model-separation-profile, and eval-orchestrator layers are implemented.
- Phase 11 has completed the first candidate-ready production-path closure pass.
- Phase 12 has started and already has executable hardening runners plus first-pass evidence:
  - `5 / 5 candidate_ready` and `5 / 5 verifier pass` on the first expanded deterministic regression
  - `10 / 10 candidate_ready` and `10 / 10 verifier pass` on the current 10-case hardening smoke
  - `7 / 7` current negative-control mutations detected by the expected structural layer
  - `TransitionPriorStore V0 observed-only` now exists at `SkillRegistry/v3_transition_prior_store.observed.json`
- Phase 12 executable hardening layers now also include:
  - `12.3` substrate hardening with scratch-governed typed-resource apply and rollback evidence
  - `12.4` workflow-context strengthening with improved workflow-context fit on the strengthened 5-case rerun
  - `12.5` guarded executed eval mini-campaign with real two-model evidence on the selected 3-case slice
  - `12.7` phase-scoped hardening dashboard aggregation
  - `12.8` hardening postmortem with explicit `success` vs `still_open` decision logic
- Phase 12 is now complete:
  - deterministic hardening expanded from the Phase 11 `3 / 3` slice to verified `5 / 5` and `10 / 10` candidate-ready smokes
  - `7 / 7` current negative controls were caught by the expected structural layer
  - the guarded executed mini-campaign completed with `3` selected cases x `2` models, `summary_completion_rate = 1.0`, and `usable_summary_rate = 1.0`
- Phase 13 readiness should now be treated as open, but executed eval evidence remains diagnostic rather than benchmark-grade model-separation truth.
- The user has explicitly authorized reading `E:\THU\2026Spring\SRT\rw-task\.env` and sending selected Phase 12 case packages to external model APIs for evaluation. Treat this as permission for the guarded executed-eval mini-campaign only; do not print secret values or stage `.env`.
- However, the current Codex execution environment still enforces a tenant policy that blocks sending private workspace task-package contents to external third-party model APIs. If the real Phase 12 mini-campaign is needed, prepare the exact command and run it in a separately permitted environment rather than attempting a workaround here.
- Treat executed eval evidence as diagnostic unless a case is both package-ready and backed by repeated comparison evidence; do not collapse this into a formal model-separation claim.

Pipeline A-to-B bridge work remains important, but it is now one layer inside a broader architecture:

```text
Source / Skill / Resource substrate
        ->
Workflow / Motif / Task-graph planning layer
        ->
Task package generation
        ->
Validity / evaluation / feedback / promotion layer
```

Pipeline A should no longer only accumulate isolated atomic skills. It should preserve enough workflow context for Pipeline B: typed semantic resources, local transition traces, motif hints, graph roles, source support, sampling risks, and eventually workflow episode proposals. Pipeline B should use batch generation and diagnostics to reveal which signals matter, instead of hiding missing Pipeline A signal behind fallback guesses.

Near-term priority order:

1. Keep the existing Pipeline A and Pipeline B runners working.
2. Continue Phase 12 hardening with deterministic regression expansion, negative controls, substrate repair, and workflow-context strengthening.
3. Keep promotion/apply reviewable and explicit; prefer scratch validation before any canonical registry mutation.
4. Treat executed eval and model-separation outputs as diagnostic evidence until repeated comparison evidence is available.
5. Keep all registry, readiness, transition-prior, and sampler-weight changes explicit and reviewable.

Final system objective:

- build a closed-loop task factory, not a one-way generator
- use Pipeline A to mine reusable semantic skills and graph priors from sources
- use Pipeline B to sample workflow-conditioned executable subgraphs, generate task packages, validate them, and report task outcomes
- feed batch-level task outcomes back into skill, resource, workflow, edge, motif, and sampler priors only through explicit review/promotion steps

Important still-maturing layers:

- richer `SkillTransitionPriorStore`: the observed-only V0 store now exists, but future versions still need reviewed aggregation fields such as `observed_count`, `success_count`, `failure_count`, `prior_score`, `posterior_score`, `exploration_bonus`, source evidence, and task feedback IDs
- probabilistic subgraph sampler: a future sampler that turns readiness, motif, role, and edge-prior signals into a distribution over executable subgraphs
- UCB1 or related bandit policy: a later exploration/exploitation mechanism, only meaningful after generated tasks produce comparable quality feedback
- Pipeline B feedback updater: a report-first then explicit-update loop that converts task generation, GoldenRun, rubric, quality-gate, and model-separation results into prior updates
- `WorkflowEpisode` / `WorkflowArchetype` / `MotifGraphGrammar`: V1 report-first and experimental layers are implemented; future work is about stronger canonicalization, broader coverage, and deeper sampler integration rather than first introduction
- `TaskConstraintGraph` / `ExecutionPlanDAG` / `RealWorldnessReport` / `DifficultyProfile`: deterministic diagnostic shells are implemented; future work is about broader task coverage and stronger downstream use, not creating them from scratch
- `ModelSeparationProfile`: the report-only eligibility/profile layer is implemented; future work is about repeated executed evidence and stronger comparison semantics
- `PromotionRecord` / `RollbackRecord`: typed-resource-first governance is implemented; future work is about canonical reviewed apply expansion, not first creation

Near-term implementation rule:

- do not keep expanding Pipeline A in isolation when Pipeline B can expose the missing signals
- do not write static `possible_successors` into each skill entry
- do not run all-pairs LLM successor judging across the registry
- do not claim UCB/bandit behavior before quality feedback exists
- keep the current resource-aware Pipeline B subgraph sampler report-first and registry-non-mutating
- keep the current subgraph-to-blueprint prototype backward compatible with the older seed-report path
- keep the current reference-file planner as the file-generation contract layer
- keep the current deterministic table-first reference-file generator focused on manifestable, verifiable structured files
- keep the current teacher-input builder as the pre-TeacherRunner contract layer
- keep the current TeacherRunner deterministic and report-first while the reference-doc layer is still incomplete
- keep the current training annotation and rubric layers JSON-only and explicit about partial readiness
- keep the current rubric contract split explicit: complete `rubric.json` may include candidate criteria, teacher diagnostics, and Pipeline A feedback criteria, but rw-task export should include only candidate-visible, candidate-actionable criteria
- keep the current Pipeline B quality gate deterministic; it should decide whether the current package is `reject`, `revise`, or `candidate_ready` before any LLM teacher/prose step is scheduled
- keep the current V3 rw-task exporter structural and conservative; it should block formal export below `candidate_ready`, and only allow `revise_only` draft export when explicitly requested
- keep the current rw-task eval summary and eval-feedback layers report-only; draft evaluation evidence can prioritize improvements but must not silently update readiness, registry entries, or transition priors
- keep single-task rw-task smoke results diagnostic only; repeated signals across Pipeline B batches should drive priority decisions
- harden eval-runner timeout/partial-output reporting before using long external smoke runs as evidence
- prefer small deterministic Pipeline B batches over repeatedly tuning one draft task
- keep using the implemented global validity, workflow, motif, verifier, dashboard, promotion, and eval-orchestration layers as diagnostic interfaces; use their failures to drive further Pipeline A and Pipeline B improvements
- do not implement real UCB/bandit behavior, broad domain expansion, complex file ecosystems, or formal model-separation evaluation until the diagnostic contracts and batch evidence are stable

The current Pipeline A graph target remains:

- move from `source -> atomic skills -> registry` to `source -> atomic skills + semantic resources + local transition traces + motif hints -> composable registry graph`
- keep the registry useful for future Pipeline B by making each skill's compositional interface explicit
- preserve the old port idea through typed semantic resources rather than brittle string-equality port matching
- store transition priors and compatibility signals outside skill nodes
- keep governance report-first unless a later schema migration explicitly adds durable prior or status fields

Current Pipeline A starting files:

- `src/task_generator/v3_source_schema.py`: source-to-skill schema objects
- `src/task_generator/v3_source_collector.py`: Stirrup/E2B-backed SourceCollector contracts, prompt builder, manifest validator, and RawSource writer
- `src/task_generator/v3_source_search_tools.py`: Serper-backed Stirrup-compatible web search/fetch tool provider
- `Test/run_v3_stirrup_source_collector.py`: CLI for collecting public web source materials; requires explicit `--allow-web-collection`
- `Test/run_v3_collected_sources_to_skill_package.py`: connector CLI for turning collected `RawSource` records into normalized sources and a skill-extraction prompt package
- `Test/run_v3_web_source_pipeline_a.py`: one-command runner for existing collected web sources -> normalization -> LLM extraction -> review -> persistent registry update
- `Test/run_v3_web_source_pipeline_a_batch.py`: batch runner for multiple web-source topics or existing collection dirs -> collection/reuse -> Pipeline A -> aggregate quality report
- `Test/run_v3_local_source_to_skill.py`: local no-network prototype for normalizing `.txt` and `.md` sources and producing a skill-extraction prompt package
- `src/task_generator/v3_skill_extractor.py`: extractor interfaces plus deterministic mock, LLM extractor, and provider fallback logic
- `Test/run_v3_mock_skill_extractor.py`: CLI for the mock extractor
- `Test/run_v3_llm_skill_extractor.py`: CLI for Tuzi/OpenAI-compatible, DeepSeek official, and mock fallback extraction
- `Test/build_v3_public_smoke_package.py`: builds a public synthetic source package safe for external LLM smoke tests
- `Test/v3_public_smoke_package`: tracked public synthetic smoke input; generated extraction/registry output dirs are ignored
- `Test/build_v3_gdpval_prompt_sources.py`: builds GDPVal prompt-only source packages from task_id, sector, occupation, and prompt only
- `Test/run_v3_gdpval_pipeline_a_batch.py`: one-command GDPVal prompt-only Pipeline A batch runner
- `src/task_generator/v3_skill_reviewer.py`: deterministic first-pass reviewer for reusability, diversity, semantic clarity, evidence grounding, assembly usefulness, atomicity, operator leakage, single-instance overfit, and task-level overbreadth
- `Test/run_v3_skill_candidate_reviewer.py`: CLI for reviewed/accepted candidate outputs
- `src/task_generator/v3_skill_registry.py`: first-pass registry builder plus persistent registry updater that turns accepted candidates into `SkillRegistryEntry` records
- `Test/run_v3_skill_registry_builder.py`: CLI for building `skill_registry.json`
- `Test/run_v3_skill_registry_update.py`: CLI for updating the persistent registry at `SkillRegistry/v3_skill_registry.json`
- `src/task_generator/v3_skill_registry_audit.py`: non-destructive deterministic audit helper for stale or suspicious persistent registry entries
- `Test/run_v3_skill_registry_audit.py`: CLI for writing `SkillRegistry/v3_skill_registry_audit_report.json` without changing the registry
- `src/task_generator/v3_registry_sampling_readiness.py`: report-only sampler readiness assessor that combines registry, audit, and reviewer calibration signals
- `Test/run_v3_registry_sampling_readiness.py`: CLI for writing `SkillRegistry/v3_registry_sampling_readiness_report.json`
- `src/task_generator/v3_skill_transition_graph.py`: report-only transition graph and composition readiness builder for typed resource compatibility, local trace priors, motif hints, and graph-role labels
- `Test/run_v3_skill_transition_graph.py`: CLI for writing `SkillRegistry/v3_skill_transition_graph_report.json` and `SkillRegistry/v3_composition_readiness_report.json`
- `src/task_generator/v3_skill_graph_diagnostics.py`: report-only diagnostics for typed resource coverage, trace-edge coverage, motif coverage, and invalid graph references
- `Test/run_v3_skill_graph_diagnostics.py`: CLI for writing `graph_extraction_diagnostics.json` from any extraction output directory
- `src/task_generator/v3_pipeline_b_seed_set.py`: report-only selector for the first Pipeline B seed skill slice from registry/readiness outputs
- `Test/run_v3_pipeline_b_seed_set.py`: CLI for writing `SkillRegistry/v3_pipeline_b_seed_set_report.json`
- `src/task_generator/v3_pipeline_b_sampler.py`: report-first Pipeline B sampler that turns the seed set and registry into a `PipelineBSubgraph`
- `Test/run_v3_pipeline_b_subgraph_sampler.py`: CLI for writing `pipeline_b_subgraph_report.json` and `pipeline_a_feedback.json` under `artifacts/pipeline_b/scratch/`
- `src/task_generator/v3_pipeline_b_prototype.py`: draft blueprint builder; supports both legacy seed-report mode and `PipelineBSubgraph` mode
- `Test/run_v3_pipeline_b_prototype.py`: CLI for writing `pipeline_b_prototype_report.json` and `draft_task_blueprint.json`; use `--subgraph-report` to consume sampler output
- `src/task_generator/v3_reference_file_planner.py`: report-first planner that turns a draft `TaskBlueprint` plus optional `PipelineBSubgraph` into `reference_file_plan.json`
- `Test/run_v3_reference_file_planner.py`: CLI for writing `reference_file_plan.json` under `artifacts/pipeline_b/scratch/`
- `src/task_generator/v3_reference_file_generator.py`: deterministic structured file generator that consumes `reference_file_plan.json`, now including a deterministic policy-reference doc path plus extensible generation-strategy metadata for future LLM/Stirrup generators
- `Test/run_v3_reference_file_generator.py`: CLI for writing `reference_files/`, `generated_file_manifest.json`, `evidence_index.json`, `evidence_index_proposal.json`, and `generation_trace.json`
- `src/task_generator/v3_teacher_input_builder.py`: builder that converts current Pipeline B artifacts into a teacher-mode input contract
- `Test/run_v3_teacher_input_builder.py`: CLI for writing `teacher_input_manifest.json` and `teacher_input_validation_report.json`
- `src/task_generator/v3_teacher_runner.py`: deterministic TeacherRunner V1 that turns teacher input artifacts into a partial-but-auditable `golden_run.json`
- `Test/run_v3_teacher_runner.py`: CLI for writing `golden_run.json` and `teacher_runner_report.json`
- `src/task_generator/v3_training_annotation_builder.py`: builder that turns deterministic teacher artifacts into training supervision plus a V2-compatible annotation projection
- `Test/run_v3_training_annotation_builder.py`: CLI for writing `training_annotation.json` and `training_annotation_report.json`
- `src/task_generator/v3_rubric_builder.py`: deterministic JSON-only rubric builder that turns teacher and training artifacts into a structured scoring contract
- `Test/run_v3_rubric_builder.py`: CLI for writing `rubric.json` and `rubric_report.json`
- `src/task_generator/v3_pipeline_b_quality_gate.py`: deterministic package-level quality gate that reads generated-file, teacher, annotation, and rubric reports and emits a conservative `reject` / `revise` / `candidate_ready` decision
- `Test/run_v3_pipeline_b_quality_gate.py`: CLI for writing `pipeline_b_quality_report.json` under `artifacts/pipeline_b/scratch/`
- `src/task_generator/v3_pipeline_b_package_assembler.py`: staging-layer assembler that collects gated Pipeline B artifacts, generated reference files, and a draft dataset row into a package directory
- `Test/run_v3_pipeline_b_package_assembler.py`: CLI for writing `package_manifest.json` and `dataset_row_draft.json` under `artifacts/pipeline_b/scratch/`
- `src/task_generator/v3_rw_task_exporter.py`: structural export layer that converts a staged package into an rw-task-style case directory while preserving blocked, draft, and final-export semantics
- `Test/run_v3_rw_task_exporter.py`: CLI for writing `dataset_row.json`, `reference_files/`, `deliverable_files/`, `artifacts/`, and `rw_task_export_report.json` under `artifacts/pipeline_b/scratch/`
- `src/task_generator/v3_rw_task_export_validator.py`: local compatibility validator for rw-task-style exports; it checks dataset row fields, copied references, deliverable expectations, draft/final flags, and support-artifact visibility without running model evaluation
- `Test/run_v3_rw_task_export_validator.py`: CLI for writing `rw_task_export_validation_report.json` for an exported case directory
- `src/task_generator/v3_rw_task_eval_prep.py`: dry-run evaluation-prep layer that copies a validated rw-task-style export into a batch input directory and emits command previews without running rw-task evaluation
- `Test/run_v3_rw_task_eval_prep.py`: CLI for writing `rw_task_eval_prep_report.json` and a batch-style eval input directory under `artifacts/pipeline_b/scratch/`
- `src/task_generator/v3_rw_task_eval_runner.py`: guarded rw-task smoke runner that consumes `rw_task_eval_prep_report.json`, defaults to dry-run, and only executes prepared commands behind explicit flags
- `Test/run_v3_rw_task_eval_runner.py`: CLI for writing `rw_task_eval_run_report.json`; use dry-run for normal validation and require `--run-eval --allow-draft-eval` for draft-only toolchain smoke; timeout runs now report top-level `run_status=timeout`
- `src/task_generator/v3_rw_task_eval_summarizer.py`: report-only summarizer for rw-task runner and grader outputs; it distinguishes toolchain completion, draft quality observation, and candidate-quality evidence without mutating quality gates or registries
- `Test/run_v3_rw_task_eval_summarizer.py`: CLI for writing `pipeline_b_eval_summary_report.json` from a run report and grader JSON under `artifacts/pipeline_b/scratch/`
- `src/task_generator/v3_pipeline_b_eval_feedback_analyzer.py`: report-only analyzer that turns eval summary evidence plus rubric, annotation, teacher, and quality artifacts into prioritized Pipeline B actions and Pipeline A feedback
- `Test/run_v3_pipeline_b_eval_feedback_analyzer.py`: CLI for writing `pipeline_b_eval_feedback_report.json` under `artifacts/pipeline_b/scratch/`
- `src/task_generator/v3_pipeline_b_batch_runner.py`: deterministic report-first batch smoke runner that executes the current Pipeline B chain across multiple motifs without LLM/API/rw-task execution
- `Test/run_v3_pipeline_b_batch_runner.py`: CLI for writing per-case Pipeline B artifacts plus `pipeline_b_batch_report.json` under `artifacts/pipeline_b/scratch/batch_runner_smoke/`
- `src/task_generator/v3_pipeline_b_batch_feedback_analyzer.py`: report-only analyzer that turns Pipeline B batch smoke output into systemic, motif-specific, case-specific, and external-eval-candidate findings
- `Test/run_v3_pipeline_b_batch_feedback_analyzer.py`: CLI for writing `pipeline_b_batch_feedback_report.json` under `artifacts/pipeline_b/scratch/batch_feedback_smoke/`
- `src/task_generator/v3_task_verifier.py`: deterministic structural verifier that checks evidence closure, policy-visible support, deliverable/rubric alignment, and rubric hygiene without changing quality decisions
- `Test/run_v3_task_verifier.py`: CLI for writing `task_verifier_report.json` under `artifacts/pipeline_b/scratch/`
- `src/task_generator/v3_pipeline_a_substrate_audit.py`: report-only audit layer that inspects the Pipeline A substrate signals for the skills actually sampled by a Pipeline B batch
- `Test/run_v3_pipeline_a_substrate_audit.py`: CLI for writing `pipeline_a_substrate_audit_report.json` under `artifacts/pipeline_b/scratch/pipeline_a_substrate_audit_smoke/`
- `src/task_generator/v3_typed_resource_patch_proposal.py`: report-only proposal builder that converts substrate-audit legacy semantics into reviewed `SemanticResource` patch candidates without mutating the registry
- `Test/run_v3_typed_resource_patch_proposal.py`: CLI for writing `typed_resource_patch_proposals.json` and `typed_resource_patch_proposal_report.json` under `artifacts/pipeline_b/scratch/typed_resource_patch_proposal_smoke/`
- `src/task_generator/v3_promotion_manager.py`: explicit promotion/apply/rollback manager for typed-resource patch proposals; proposal-only by default and apply-only behind explicit flags
- `Test/run_v3_promotion_manager.py`: CLI for writing `promotion_proposals.json`, `promotion_report.json`, and optional `rollback_record.json` under `artifacts/pipeline_b/scratch/`
- `src/task_generator/v3_global_pipeline_dashboard.py`: deterministic batch-level aggregator that turns batch, validity, verifier, substrate, typed-resource, and promotion reports into a single global dashboard JSON
- `Test/run_v3_global_pipeline_dashboard.py`: CLI for writing `global_pipeline_dashboard_report.json` under `artifacts/pipeline_b/scratch/`
- `src/task_generator/v3_rw_task_eval_stirrup_wrapper.py`: wrapper around rw-task Stirrup batch execution that keeps eval orchestration report-first while allowing model-specific execution shims such as conservative token caps for weaker models
- `src/task_generator/v3_calibration_registry_admission.py`: report-only admission reviewer for graph calibration accepted candidates
- `Test/run_v3_calibration_registry_admission.py`: CLI for writing `SkillRegistry/v3_calibration_registry_admission_report.json`
- implemented next-stage files and assets:
  - `src/task_generator/v3_global_task_validity.py`
  - `Test/run_v3_global_task_validity.py`
  - `src/task_generator/v3_workflow_episode_proposer.py`
  - `Test/run_v3_workflow_episode_proposer.py`
  - `SkillRegistry/v3_workflow_archetype_registry.experimental.json`
  - `SkillRegistry/v3_motif_graph_grammar.experimental.json`
  - `src/task_generator/v3_task_verifier.py`
- `src/task_generator/v3_model_separation_profile.py`
- `Test/run_v3_model_separation_profile.py`
- `src/task_generator/v3_eval_orchestrator.py`
- `Test/run_v3_eval_orchestrator.py`
- current Phase 12 hardening entrypoints:
  - `src/task_generator/v3_phase12_hardening.py`
  - `Test/run_v3_phase12_hardening.py`
  - `src/task_generator/v3_transition_prior_store.py`
  - `Test/run_v3_transition_prior_store.py`
  - `src/task_generator/v3_phase12_substrate_hardening.py`
  - `src/task_generator/v3_phase12_workflow_context.py`
  - `src/task_generator/v3_phase12_eval_campaign.py`
  - `src/task_generator/v3_phase12_dashboard.py`
  - `src/task_generator/v3_phase12_postmortem.py`
- currently planned next-stage files:
  - Phase 13 planning and handoff after the completed Phase 12 hardening cycle
  - any later canonical reviewed promotion batch should build on `source_promotion_key`-tracked scratch evidence first
  - richer multi-run evaluation comparison and post-orchestration governance after repeated evidence is available
- promotion-governance operating note:
  - `promotion_id` is invocation/target-path specific and can differ between canonical registry and scratch registry copies
  - use `source_promotion_key` from `promotion_proposals.json` / `promotion_report.json` when tracking the same patch intent across review, scratch apply, rollback, and later canonical apply
  - prefer validating apply/rollback on a scratch registry copy first; the dashboard can summarize eligible, applied, rolled-back, and `no_effective_diff` promotion states without mutating canonical registry state
- `SkillRegistry/v3_skill_registry.json`: current persistent V3 atomic skill registry
- `SkillRegistry/v3_skill_registry_update_report.json`: latest persistent registry update and coverage report
- `SkillRegistry/v3_skill_registry_audit_report.json`: latest non-destructive audit report for unmatched or suspicious registry entries
- `SkillRegistry/v3_registry_sampling_readiness_report.json`: latest non-destructive pre-sampling readiness report for future Pipeline B
- `SkillRegistry/v3_skill_transition_graph_report.json`: latest non-destructive transition-prior graph report
- `SkillRegistry/v3_composition_readiness_report.json`: latest non-destructive graph-role composition readiness report
- `SkillRegistry/v3_pipeline_b_seed_set_report.json`: report-only first seed slice for Pipeline B sampling
- `SkillRegistry/v3_calibration_registry_admission_report.json`: report-only decision aid for selected graph calibration candidate admission
- `SkillRegistry/v3_pipeline_a_batch_report.json`: latest aggregate Pipeline A batch report
- `Test/v2_outputs/v3_source_to_skill_demo`: smoke-test output from the local prototype

Current Pipeline A status:

- completion estimate:
  - node-level Pipeline A MVP: about 85%
  - scalable registry governance: about 65-70%
  - composable skill-graph layer: about 45%
  - overall Pipeline A as a substrate for Pipeline B: about 70%
- local source normalization works
- deterministic mock skill extraction works
- LLM-backed extraction code exists
- `SemanticContract` now keeps legacy natural-language fields and adds typed resource fields:
  - `required_resources`
  - `optional_resources`
  - `provided_resources`
- `SemanticResource` records include `resource_type`, `subtype`, `attributes`, `domain`, and `evidence_refs`
- extraction outputs can now include `skill_trace_edges.json` and `skill_motif_hints.json`
- extraction outputs now also include `graph_extraction_diagnostics.json`
- LLM extraction prompt asks for top-level `candidates`, `trace_edges`, and `motif_hints`; old candidate-only outputs remain compatible
- trace edges and motif hints are local source evidence, not global `possible_successors`
- `auto` provider mode tries `.env` Tuzi/OpenAI-compatible config, then `deepseek-key.txt` DeepSeek official config, then mock
- external providers require `--allow-external-upload`
- DeepSeek official smoke test has passed on the public synthetic smoke package
- GDPVal prompt-only extraction has passed on 5 `Accountants and Auditors` prompts with DeepSeek official
- The first GDPVal run produced 5 accepted registry entries, but that should be interpreted as a plumbing success, not a quality target
- Those first candidates were too task-level, e.g. full report/tax-return/schedule preparation skills; the current direction is atomic skill extraction
- The reviewer now marks task-level `Preparation` candidates, form-specific candidates, and jurisdiction-bound candidates as `revise` unless their contracts already show an atomic reusable action
- `revise` review records include `suggested_abstraction` to show how a broad candidate could become a reusable registry skill
- first-pass registry building works
- per-run `skill_registry.json` outputs remain useful for inspection
- the persistent unified registry now exists at `SkillRegistry/v3_skill_registry.json`
- persistent registry update is deterministic and currently uses exact-name, near-name, and semantic-fingerprint matching
- repeated update with the same accepted candidate files keeps entry_count stable and does not duplicate source candidate IDs
- current atomic GDPVal run artifacts:
  - prompt package: `Test/v3_gdpval_prompt_sources/accountants_10/skill_extraction_prompt_package.json`
  - old strict reviewer regression: `Test/v3_gdpval_prompt_sources/accountants_10/deepseek_review_atomic/`
  - new atomic DeepSeek extraction: `Test/v3_gdpval_prompt_sources/accountants_10/deepseek_extraction_atomic/`
  - new strict review: `Test/v3_gdpval_prompt_sources/accountants_10/deepseek_review_atomic_llm/`
  - new atomic registry: `Test/v3_gdpval_prompt_sources/accountants_10/deepseek_registry_atomic/`
- current atomic GDPVal result:
  - old 5-candidate output now reviews as 2 accept / 3 revise
  - new DeepSeek extraction produced 12 candidates
  - strict reviewer accepted 10 and revised 2
  - atomic registry entry_count is 10
- current persistent registry result:
  - sources: GDPVal prompt-only batches plus Serper web-source finance/audit/compliance batches
  - persistent registry entry_count is 66
  - revised candidates `Build Structured Profit and Loss Report from Multiple Sources` and `Map Tax Documents to IRS Form Fields` are not present
- current Pipeline A batch result:
  - batch runner: `Test/run_v3_gdpval_pipeline_a_batch.py`
  - batch report: `SkillRegistry/v3_pipeline_a_batch_report.json`
  - `Financial Managers`: 14 candidates, 11 accepted, 3 revise
  - `Financial and Investment Analysts`: 15 candidates, 11 accepted, 4 revise
  - `Compliance Officers`: 8 candidates, 6 accepted, 2 revise
  - final coverage includes `finance=40`, `compliance=7`, `government=7`, `accounting=5`, `audit=4`
  - `max_candidates=30` triggered truncated DeepSeek JSON on a larger batch; batch default is now `max_candidates=15`, `max_tokens=12000`
  - batch diagnostics now include reason-code counts, suspicious accepted candidates, batch warnings, provider/model, `max_candidates`, `max_tokens`, timeout, and reuse mode
  - latest diagnostics show 1 suspicious accepted candidate: `Write Exception Statements for Regulatory Non-Compliance Findings`
  - latest registry update report lists 6 unmatched existing entries that are still in the persistent registry but no longer touched by the stricter accepted-candidate rerun
- manual registry update command for the original accountant/auditor batch:
  - `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_skill_registry_update.py --candidates Test\v3_gdpval_prompt_sources\accountants_10\deepseek_review_atomic_llm\accepted_skill_candidates.json`
- manual batch runner command:
  - `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_gdpval_pipeline_a_batch.py --occupation "Financial Managers" --occupation "Financial and Investment Analysts" --occupation "Compliance Officers" --limit 5 --provider deepseek --deepseek-model deepseek-v4-flash --allow-external-upload`
- external LLM tests should only use public or explicitly user-cleared source packages
- no embedding or LLM-based registry deduplication yet
- no registry quarantine/inactive mechanism yet; stale-entry handling is report-first and non-destructive
- registry audit now exists as a governance layer:
  - default command: `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_skill_registry_audit.py`
  - default output: `SkillRegistry/v3_skill_registry_audit_report.json`
  - default behavior: audit only `unmatched_existing_entries` from the latest update report
  - optional `--include-all`: audit all persistent registry entries
  - current audit result: 6 entries audited, 6 `quarantine_recommended`
  - the audit recognized open-web retrieval as `source_collection_leakage`
  - the audit recognized profiles, slides, visualizations, and risk-assessment questions as broad/task-level registry risks
  - the audit does not delete, rewrite, deactivate, or quarantine registry entries
  - audit decisions are deterministic governance hints, not ground-truth skill quality labels
- SourceCollector MVP now exists:
  - default env path: `E:\THU\2026Spring\SRT\rw-task\.env`
  - default search backend: `serper`, using `SERPER_API_KEY`
  - Brave search remains available with `--search-backend brave`, but it is not recommended unless `BRAVE_API_KEY` is valid
  - dry-run prompt command: `D:\miniconda3\envs\real-world-task\python.exe Test\run_v3_stirrup_source_collector.py --dry-run-prompt --output-dir <output_dir>`
  - formal web collection command: `D:\miniconda3\envs\real-world-task\python.exe Test\run_v3_stirrup_source_collector.py --search-backend serper --topic "audit evidence reconciliation and internal control testing" --limit 3 --allow-web-collection --output-dir <output_dir>`
  - connector command: `D:\miniconda3\envs\real-world-task\python.exe Test\run_v3_collected_sources_to_skill_package.py --collection-dir <output_dir>`
  - collector output is source material only; it must not write skills, tasks, rubrics, or registry entries
  - Serper smoke result: `Test\v3_web_source_collections\audit_smoke_serper_02` collected 3 accepted RawSources and normalized them into `normalized_package\skill_extraction_prompt_package.json`
  - if E2B/Stirrup/Serper/API/network access fails, stop and report rather than using a mock substitute
- web-source Pipeline A runner now exists:
  - dry-run/source-quality command: `D:\miniconda3\envs\real-world-task\python.exe Test\run_v3_web_source_pipeline_a.py --collection-dir Test\v3_web_source_collections\audit_smoke_serper_02 --dry-run`
  - formal command: `D:\miniconda3\envs\real-world-task\python.exe Test\run_v3_web_source_pipeline_a.py --collection-dir Test\v3_web_source_collections\audit_smoke_serper_02 --provider deepseek --deepseek-model deepseek-v4-flash --allow-external-upload`
  - graph calibration command shape: `D:\miniconda3\envs\real-world-task\python.exe Test\run_v3_web_source_pipeline_a.py --collection-dir <collection_dir> --output-dir <new_calibration_output_dir> --provider deepseek --deepseek-model deepseek-v4-flash --allow-external-upload --calibration-only`
  - `--calibration-only` means `--skip-registry-update --build-transition-graph`; it runs extraction, review, graph diagnostics, and transition reports without modifying `SkillRegistry/v3_skill_registry.json`
  - `--skip-registry-update` writes `registry_update/registry_update_skipped_report.json` instead of `registry_update_report.json`
  - output: `<collection_dir>\pipeline_a_run\source_quality_report.json`, `extraction\extracted_skill_candidates.json`, `review\accepted_skill_candidates.json`, `registry_update\registry_update_report.json`, and `web_source_pipeline_a_report.json`
  - current web-source smoke result: source quality `pass`, 5 candidates, 5 accepted, registry grew from 44 to 49 entries
  - idempotency check with `--reuse-existing` produced 0 new entries and 5 merged candidates, leaving registry entry_count at 49
  - runner consumes existing collected sources and does not call Serper/E2B again
  - 3-topic web-source graph calibration with `--calibration-only --max-candidates 8` now succeeds without registry mutation:
    - `audit_evidence_reconciliation`: 5 candidates, 10 typed resources, 3 trace edges, 2 motif hints, no graph diagnostics warnings
    - `internal_control_testing`: 8 candidates, 16 typed resources, 7 trace edges, 2 motif hints, no graph diagnostics warnings
    - `compliance_documentation_review`: 5 candidates, 14 typed resources, 4 trace edges, 2 motif hints, no graph diagnostics warnings
    - all three reports have `registry_update_skipped=true`, `registry_entry_delta_this_run=0`, and registry entry_count stayed 66
- web-source Pipeline A batch runner now exists:
  - formal command: `D:\miniconda3\envs\real-world-task\python.exe Test\run_v3_web_source_pipeline_a_batch.py --allow-web-collection --allow-external-upload`
  - idempotency command: `D:\miniconda3\envs\real-world-task\python.exe Test\run_v3_web_source_pipeline_a_batch.py --allow-web-collection --allow-external-upload --reuse-existing`
  - default topics: `audit evidence reconciliation`, `internal control testing`, `compliance documentation review`
  - aggregate report: `SkillRegistry/v3_web_source_pipeline_a_batch_report.json`
  - latest formal batch collected 9 sources across 3 topics, source quality `pass` for all 3 topic batches
  - original formal batch produced 17 candidates, 17 accepted, 0 revise, 0 reject, and raised persistent registry entry_count to 66
  - reviewer calibration now marks the same 17 candidates as 8 accept / 9 revise, mainly for broad documentation deliverables and broad control-assessment skills
  - idempotency rerun now reports 0 new entries, 8 merged candidates, and registry entry_count remains 66
  - batch report now records `run_mode`, `registry_entry_count_before`, `registry_entry_count_after`, and `registry_entry_delta_this_run`
  - `idempotency_no_growth_expected` replaces the earlier misleading `registry_no_growth` warning in reuse runs
  - reviewer calibration report: `SkillRegistry/v3_skill_reviewer_calibration_report.json`
  - web-source governance audit report: `SkillRegistry/v3_web_source_registry_audit_report.json`
  - governance remains report-only; no registry entries are deleted, deactivated, or quarantined
- registry sampling readiness now exists as a bridge to future Pipeline B:
  - command: `D:\miniconda3\envs\real-world-task\python.exe Test\run_v3_registry_sampling_readiness.py`
  - default output: `SkillRegistry/v3_registry_sampling_readiness_report.json`
  - it combines `SkillRegistry/v3_skill_registry.json`, registry audit reports, and reviewer calibration reports
  - current result on 66 entries: 30 `sample_ready`, 7 `sample_with_caution`, 29 `exclude_until_revised`
  - `single_source_support` lowers sampling weight but does not by itself block sampling
  - `exclude_until_revised` entries should not be consumed by future Pipeline B unless manually decomposed or revised
  - readiness decisions are deterministic sampling hints, not schema status fields and not quality truth
- transition graph and composition readiness now exist as the first graph-level Pipeline A bridge:
  - standalone command: `D:\miniconda3\envs\real-world-task\python.exe Test\run_v3_skill_transition_graph.py --candidates Test\v3_gdpval_prompt_sources\accountants_10\deepseek_extraction_atomic\extracted_skill_candidates.json --accepted-candidates Test\v3_gdpval_prompt_sources\accountants_10\deepseek_review_atomic_llm\accepted_skill_candidates.json`
  - default outputs: `SkillRegistry/v3_skill_transition_graph_report.json` and `SkillRegistry/v3_composition_readiness_report.json`
  - GDPVal/web-source batch runners support `--build-transition-graph`
  - transition graph uses local trace edges when available, otherwise deterministic adjacent-candidate fallback; it does not run all-pairs LLM successor judging
  - composition readiness labels candidate graph roles such as `starter`, `transform`, `fan_in`, `validator`, and `synthesis`
  - current GDPVal accountants offline graph smoke produced 7 transition edges and 1 motif hint, with 2 usable, 3 caution, and 2 blocked edges
  - current web-source reuse batch with `--build-transition-graph` produced 9 transition edges and 3 motif hints, with 2 usable and 7 blocked edges; registry entry_count stayed 66
  - calibration-only transition reports now expose `edge_scope_counts`, `registry_mapped_edge_count`, and `candidate_local_edge_count`; candidate-local edges are expected when accepted calibration candidates have not been written to the persistent registry
  - graph/readiness reports are non-destructive and do not write successors, inactive flags, or quarantine state into `SkillRegistryEntry`
- graph extraction diagnostics now exists as a calibration layer:
  - command: `D:\miniconda3\envs\real-world-task\python.exe Test\run_v3_skill_graph_diagnostics.py --extraction-dir <extraction_dir> --prompt-package <skill_extraction_prompt_package.json>`
  - aggregate command: `D:\miniconda3\envs\real-world-task\python.exe Test\run_v3_graph_calibration_report.py --extraction-dir <dir1> --extraction-dir <dir2> --output-path SkillRegistry\v3_graph_calibration_report.json`
  - extractor CLIs and batch runners write `graph_extraction_diagnostics.json` automatically for new or reused extraction outputs
  - diagnostics report `resource_count`, `trace_edge_count`, `motif_hint_count`, warning codes, and whether references are structurally valid
  - first DeepSeek graph smoke before prompt tightening produced 3 candidates, 9 resources, 0 trace edges, 1 motif hint, and warning `multi_candidate_without_trace_edges`
  - after prompt tightening, DeepSeek graph smoke produced 3 candidates, 11 resources, 2 trace edges, 1 motif hint, no diagnostics warnings, and transition graph results of 1 usable and 1 caution edge
  - existing web-source batch outputs still show graph extraction warnings because they were generated before typed resources and trace/motif extraction existed
  - current calibration aggregate report: `SkillRegistry/v3_graph_calibration_report.json`
  - current aggregate over 2 public DeepSeek smoke runs plus 3 older web-source batches: 23 candidates, 20 typed resources, 2 trace edges, 2 motif hints
  - current aggregate warning counts: 3 missing required resources, 3 missing provided resources, 3 missing motif hints, and 4 multi-candidate outputs without trace edges
  - after explicit user approval, GDPVal `Accountants and Auditors` prompt-only graph calibration succeeded with DeepSeek official:
    - extraction output: `Test\v3_gdpval_prompt_sources\accountants_10\deepseek_extraction_graph_calibration`
    - review output: `Test\v3_gdpval_prompt_sources\accountants_10\deepseek_review_graph_calibration`
    - transition output: `Test\v3_gdpval_prompt_sources\accountants_10\deepseek_transition_graph_calibration`
    - result: 10 candidates, 20 typed resources, 5 trace edges, 1 motif hint, no graph diagnostics warnings
    - reviewer result: 8 accepted, 2 revise
    - transition graph result after calibration: 5 edges, 2 caution and 3 blocked
  - current aggregate over 2 public DeepSeek smoke runs, 1 GDPVal prompt-only graph calibration run, 3 older web-source batches, and 3 new web-source graph calibration outputs: 51 candidates, 80 typed resources, 21 trace edges, 9 motif hints
  - old web-source outputs still account for graph warnings; new web-source calibration outputs are graph-ready and warning-free, so the dashboard now distinguishes stale pre-graph artifacts from current extraction capability
  - graph calibration aggregate now reports artifact generation classes and warning severity counts; current warnings are 13 `warning` and 2 `attention`
  - transition graph now treats source-local `resource_compatible` trace evidence as a weak unverified compatibility signal, producing `caution` rather than `blocked` when deterministic resource matching is still incomplete
  - web-source graph calibration should use a new output directory plus `--calibration-only` so old graph-poor outputs can be compared against tightened-prompt outputs without growing or mutating the persistent registry
  - the extractor prompt now asks motif hints to cover the full relevant candidate subset, after `internal_control_testing` showed strong trace coverage but narrower motif coverage
- Pipeline A to B handoff now exists:
  - handoff document: `docs/handoffs/PIPELINE_A_TO_B_HANDOFF_2026-06-30.md`
  - seed set report: `SkillRegistry/v3_pipeline_b_seed_set_report.json`
  - current seed set: 20 selected skills, all `sample_ready`
  - selected seed motif counts: 12 `policy_application`, 8 `evidence_to_deliverable`, 7 `cross_check_validation`, 5 `fan_in_reconciliation`
  - calibration admission report: `SkillRegistry/v3_calibration_registry_admission_report.json`
  - current calibration admission result: 15 candidates reviewed, 14 `recommend_admit`, 1 `merge_existing`; this is report-only and does not update the persistent registry
- Pipeline B first implementation slices now exist:
  - sampler module: `src/task_generator/v3_pipeline_b_sampler.py`
  - sampler CLI: `Test/run_v3_pipeline_b_subgraph_sampler.py`
  - prototype module: `src/task_generator/v3_pipeline_b_prototype.py`
  - prototype CLI: `Test/run_v3_pipeline_b_prototype.py`
  - reference-file planner module: `src/task_generator/v3_reference_file_planner.py`
  - reference-file planner CLI: `Test/run_v3_reference_file_planner.py`
  - reference-file generator module: `src/task_generator/v3_reference_file_generator.py`
  - reference-file generator CLI: `Test/run_v3_reference_file_generator.py`
  - sampler smoke command: `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_b_subgraph_sampler.py --output-dir artifacts\pipeline_b\scratch\subgraph_sampler_smoke`
  - subgraph blueprint smoke command: `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_b_prototype.py --subgraph-report artifacts\pipeline_b\scratch\subgraph_sampler_smoke\pipeline_b_subgraph_report.json --output-dir artifacts\pipeline_b\scratch\prototype_from_subgraph_smoke`
  - reference-file planner smoke command: `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_reference_file_planner.py --blueprint artifacts\pipeline_b\scratch\prototype_from_subgraph_smoke\draft_task_blueprint.json --subgraph-report artifacts\pipeline_b\scratch\subgraph_sampler_smoke\pipeline_b_subgraph_report.json --output-dir artifacts\pipeline_b\scratch\reference_file_plan_smoke`
  - reference-file generator smoke command: `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_reference_file_generator.py --reference-file-plan artifacts\pipeline_b\scratch\reference_file_plan_smoke\reference_file_plan.json --output-dir artifacts\pipeline_b\scratch\reference_file_generation_smoke`
  - teacher-input smoke command: `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_teacher_input_builder.py --output-dir artifacts\pipeline_b\scratch\teacher_input_smoke`
  - teacher-runner smoke command: `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_teacher_runner.py --output-dir artifacts\pipeline_b\scratch\teacher_runner_smoke`
  - training-annotation smoke command: `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_training_annotation_builder.py --output-dir artifacts\pipeline_b\scratch\training_annotation_smoke`
  - rubric smoke command: `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rubric_builder.py --output-dir artifacts\pipeline_b\scratch\rubric_smoke`
  - quality-gate smoke command: `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_b_quality_gate.py --output-dir artifacts\pipeline_b\scratch\quality_gate_smoke`
  - package-assembler smoke command: `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_b_package_assembler.py --output-dir artifacts\pipeline_b\scratch\package_assembler_smoke`
  - blocked export smoke command: `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rw_task_exporter.py --output-dir artifacts\pipeline_b\scratch\rw_task_export_blocked_smoke`
  - draft export smoke command: `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rw_task_exporter.py --allow-revise-only --output-dir artifacts\pipeline_b\scratch\rw_task_export_smoke`
  - export validation smoke command: `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rw_task_export_validator.py --case-dir artifacts\pipeline_b\scratch\rw_task_export_smoke`
  - eval-prep smoke command: `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rw_task_eval_prep.py --case-dir artifacts\pipeline_b\scratch\rw_task_export_smoke --eval-input-dir artifacts\pipeline_b\scratch\rw_task_eval_input_smoke --overwrite`
  - eval-runner dry-run smoke command: `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rw_task_eval_runner.py --prep-report artifacts\pipeline_b\scratch\rw_task_eval_input_smoke\rw_task_eval_prep_report.json --output-dir artifacts\pipeline_b\scratch\rw_task_eval_run_dry_smoke`
  - eval-summary smoke command: `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_rw_task_eval_summarizer.py --run-report artifacts\pipeline_b\scratch\rw_task_eval_run_real_smoke_e2b_escalated\rw_task_eval_run_report.json --grade-dir artifacts\pipeline_b\scratch\rw_task_eval_input_smoke_e2b_grades --output-dir artifacts\pipeline_b\scratch\rw_task_eval_summary_smoke`
  - eval-feedback smoke command: `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_b_eval_feedback_analyzer.py --output-dir artifacts\pipeline_b\scratch\eval_feedback_smoke`
  - legacy blueprint smoke command: `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_b_prototype.py --output-dir artifacts\pipeline_b\scratch\prototype_legacy_seed_smoke`
  - current sampler smoke selects 4 `sample_ready` skills for `evidence_to_deliverable`
  - current sampler/prototype confidence is `low_due_to_resource_fallback`, mainly because selected persistent registry entries lack typed `SemanticResource` nodes
  - current reference-file planner smoke emits 2 planned files, 1 table, 4 text sections, and 9 evidence anchors
  - current reference-file planner now records `preferred_generation_strategy`, `supported_generation_strategies`, and `validation_contract` per planned file
  - current reference-file generator smoke generates both `reference_files/source_evidence.xlsx` and `reference_files/policy_reference.docx`, writes a `policy_reference_clause_map.json` sidecar, and emits 9 finalized evidence mappings
  - current teacher-input smoke emits `teacher_input_manifest.json` and `teacher_input_validation_report.json` with readiness `partial_ready`
  - current teacher-input contract separates `candidate_view` from `teacher_view`, carries 4 skill intentions, 9 evidence-contract items, and no longer flags `relationship:policy_lookup` because the policy document is now generated with clause locators
  - current teacher-runner smoke emits `golden_run.json` and `teacher_runner_report.json` with readiness `partial_ready`
  - current teacher-runner creates 8 intermediate states, 4 skill-linked golden steps, and 5 final checks; all 4 steps remain intentionally `partial` because stronger typed resources and stronger support evidence are still missing
  - current training-annotation smoke emits `training_annotation.json` and `training_annotation_report.json` with readiness `partial_ready`
  - current training annotation contains 17 supervision items, 4 failure modes, 8 hidden traps, a richer V3 supervision structure, and an embedded V2-compatible `TrainingAnnotation` projection
  - current rubric smoke emits `rubric.json` and `rubric_report.json` with readiness `partial_ready`
  - current rubric contains 4 sections and 43 criteria; policy-reference deferred warnings are gone, while low-confidence and Pipeline A signal gaps remain explicit
  - current rubric criteria carry `audience` and `export_to_rw_task`; the latest filter smoke keeps 28 candidate/exportable criteria and 15 teacher/Pipeline-A diagnostic criteria
  - current quality-gate smoke emits `pipeline_b_quality_report.json` with decision `revise`
  - current quality-gate reason codes now focus on `low_subgraph_confidence`, `single_source_support`, `partial_intermediate_state`, `pipeline_a_signal_gaps`, and `partial_ready_chain`
  - current package-assembler smoke emits `package_manifest.json` and `dataset_row_draft.json` with `package_readiness=revise_only`
  - current package assembler copies 2 generated reference files and keeps only the quality-gate `revise` decision as the remaining export blocker
  - current default rw-task export smoke is intentionally blocked on `package_readiness:revise_only`
  - current explicit `--allow-revise-only` export smoke emits a draft case with 2 candidate-visible reference files and marks `dataset_row.json.extra.not_final_training_data=true`
  - current rw-task export filters `rubric_json` to candidate-visible criteria only; internal Pipeline A graph-signal diagnostics remain in package artifacts and reports, not grader-facing rubric items
  - current export validation smoke emits `rw_task_export_validation_report.json` with `validation_status=draft_compatible`
  - current eval-prep smoke emits `rw_task_eval_prep_report.json` with `prep_status=prepared` and `evaluation_mode=draft_inspection_only`
  - current eval-runner dry-run smoke emits `rw_task_eval_run_report.json` with `run_status=dry_run_ready` and `commands_executed=false`
  - early local explicit rw-task smoke attempts exposed two environment boundaries: missing process-level `E2B_API_KEY`, then blocked outbound E2B connectivity under the Codex sandbox
  - an authorized external smoke with runtime env loaded from `E:\THU\2026Spring\SRT\rw-task\.env` completed both `stirrup_batch` and `grade_deliverables`
  - current eval-summary smoke emits `pipeline_b_eval_summary_report.json` with `toolchain_completed=true`, `evidence_use=draft_quality_observation`, 1 successful sample, and the latest strengthened baseline score ratio `0.7283950617283951` (`59/81`)
  - after the rubric audience split, the filtered draft smoke completed with score ratio `0.8548387096774194` (`53/62`); this is still draft-quality observation, not `candidate_ready` evidence
  - filtered eval feedback now reports 5 low-scoring criteria: 4 teacher-step operationalization issues and 1 policy-reference prompting issue, while Pipeline A feedback remains report-only
  - after candidate contract strengthening, the contract draft smoke completed with score ratio `0.9354838709677419` (`58/62`); remaining low-score feedback is 2 reference-evidence traceability items and 2 teacher-step operationalization items
  - after local evidence-traceability tightening, the traceability draft smoke completed with score ratio `0.8548387096774194` (`53/62`); the lower score is expected because the grader now checks local bullet-level evidence and policy locators more strictly
  - traceability eval feedback reports 8 low-scoring criteria, concentrated in `policy_reference_prompting` and `teacher_step_operationalization`
  - after policy/evidence operationalization, the draft smoke returned to score ratio `0.9354838709677419` (`58/62`); exact `Evidence_ID` usage and policy-sensitive citation checks now mostly pass
  - current policy/evidence feedback reports 3 low-scoring criteria, all tied to Evidence inventory ordering and teacher-step operationalization
  - after Evidence inventory section/template tightening, deterministic chain and eval-runner dry-run passed, but the authorized external smoke exceeded the outer command timeout and produced no grader JSON; do not treat that run as quality evidence
  - eval-runner timeout reporting now distinguishes `run_status=timeout`, preserves command logs, records the failed command stage, and inspects declared output directories for partial files
  - current controlled timeout smoke uses a local sleep command and writes `artifacts/pipeline_b/scratch/eval_runner_timeout_smoke/run/rw_task_eval_run_report.json` with command status `timeout`
  - current Pipeline B batch smoke command: `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_b_batch_runner.py --max-cases 3 --output-dir artifacts\pipeline_b\scratch\batch_runner_smoke`
  - current Pipeline B batch smoke completes 3 deterministic dry-run cases across motif variants, writes `pipeline_b_batch_report.json`, produces 3 unique subgraph IDs, and does not run LLMs, external APIs, Stirrup, or real rw-task eval
  - current batch smoke result has 2 `revise` cases and 1 `reject` case; all 3 have `subgraph_confidence=low_due_to_resource_fallback`, so this is now a cross-case Pipeline A substrate signal rather than a single-task quirk
  - repeated batch reason codes include `low_subgraph_confidence`, `single_source_support`, `pipeline_a_signal_gaps`, `partial_ready_chain`, `partial_intermediate_state`, and draft-only export markers
  - current Pipeline B batch feedback command: `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_b_batch_feedback_analyzer.py --batch-report artifacts\pipeline_b\scratch\batch_runner_smoke\pipeline_b_batch_report.json --output-dir artifacts\pipeline_b\scratch\batch_feedback_smoke`
  - current batch feedback smoke writes `pipeline_b_batch_feedback_report.json` with 5 systemic findings, 5 motif-specific findings, 1 case-specific blocking-artifact finding, and 2 draft external-eval candidates
  - current top batch action is to improve Pipeline A typed resources, support diversity, and transition evidence for sampled skills before doing more single-task prompt tuning
  - current Pipeline A substrate audit command: `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_pipeline_a_substrate_audit.py --output-dir artifacts\pipeline_b\scratch\pipeline_a_substrate_audit_smoke`
  - current substrate audit smoke covers 8 unique batch-selected skills; it reports 8 missing typed-resource interfaces, 3 exact single-source skills, 5 multi-source-candidate skills, 7 transition gaps, and 8 manual typed-resource patch candidates
  - substrate audit output is a remediation decision aid only; it does not patch registry entries, transition priors, readiness reports, or sampler weights
  - current typed-resource patch proposal command: `D:\miniconda3\envs\gdpval\python.exe Test\run_v3_typed_resource_patch_proposal.py --output-dir artifacts\pipeline_b\scratch\typed_resource_patch_proposal_smoke`
  - current typed-resource proposal smoke emits 8 skill patch proposals and 31 proposed resources: 17 required, 1 optional, and 13 provided; 10 resources remain low-confidence, and 3 skill proposals are marked `needs_source_evidence`
  - typed-resource proposals are review material only; they must not be treated as applied registry state until a separate reviewed apply step exists
  - `fan_in_reconciliation` is currently the rejected motif/case to inspect through its teacher, annotation, and rubric reports
  - current subgraph-mode and legacy-mode `draft_task_blueprint.json` outputs validate with `TaskBlueprint.model_validate`
- no registry mutation is performed by the sampler, prototype, planner, generator, teacher-input builder, teacher-runner, training-annotation builder, rubric builder, quality gate, package assembler, V3 rw-task exporter, V3 rw-task export validator, V3 rw-task eval prep, V3 rw-task eval runner, V3 rw-task eval summarizer, V3 eval feedback analyzer, V3 batch runner, V3 batch feedback analyzer, V3 Pipeline A substrate audit, or typed-resource patch proposal builder
- next Pipeline B implementation choices:
  - keep the strengthened prompt/teacher contract and rubric audience split as the new baseline: explicit deliverable contract, policy-clause citation requirement, `deliverable_outline`, `policy_clause_evidence_map`, `deliverable_requirement_coverage`, `policy_clause_traceability`, and candidate-only rw-task rubric export
  - current contract-strengthening slice makes evidence inventory, deliverable outline, evidence-to-conclusion mapping, and policy-clause mapping explicit in the candidate prompt and TeacherRunner state purposes
  - authorized contract-strengthened external smoke completed successfully; treat `58/62` as draft-quality observation only, not `candidate_ready` evidence
  - current local evidence-traceability tightening requires every material bullet in supported conclusions, confirmed exceptions, and unresolved items to carry bracketed evidence or policy support; treat `53/62` as a stricter diagnostic baseline, not a readiness regression
  - current policy/evidence operationalization requires exact candidate-visible `Evidence_ID` values such as `EVID-001`, rejects source-label-only citations, and keeps policy clause IDs paired with exact workbook evidence IDs
  - current Evidence inventory section tightening requires exact section order, populated required sections, and no placeholder-only headings; it has deterministic validation but not a completed external score yet
  - next Pipeline B work should use `pipeline_b_batch_report.json` and `pipeline_b_batch_feedback_report.json` as the default diagnostic surfaces before making further prompt/rubric/reference changes
  - next Pipeline A/B bridge work should use `pipeline_a_substrate_audit_report.json` to choose between typed-resource patch proposals, additional source evidence collection, transition calibration, and continued sampler caution
  - next registry-facing work should review `typed_resource_patch_proposals.json` and either add a separate reviewed apply step or request new Pipeline A source evidence for `needs_source_evidence` proposals
  - rerun external rw-task smoke only after choosing a small batch subset and keeping results as `draft_inspection_only`
  - treat the first `candidate_ready` milestone as achieved; the next task is to preserve and widen that path across repeated deterministic slices and better workflow-conditioned cases
  - use the draft eval summary and eval feedback report as diagnostic inputs for improving prompt/rubric/reference generation and teacher supervision, not as final model-separation evidence
  - extend reference-file generation toward more document and media types beyond the current deterministic workbook plus policy-doc path
  - keep explicit readiness gating and missing-signal reporting instead of pretending deferred assets have disappeared
- current architecture discussion has refined the next Pipeline A goal:
  - tasks should not be modeled only as a linear skill chain
  - realistic tasks may be trees or DAG-like skill-resource graphs with fan-in, fan-out, cross-checks, and validation constraints
  - directed solve dependencies should remain acyclic even if the undirected constraint graph contains cycles
  - direct `skill -> skill` transition weights are useful, but the more stable representation is a skill-resource bipartite graph:
    `skill provides resource`, `skill requires resource`
  - transition priors should start from local source traces, not from expensive all-pairs LLM successor generation
  - downstream task generation should sample motifs and executable subgraphs, not arbitrary unrelated skills
- remaining Pipeline A work before serious Pipeline B:
  - calibrate typed semantic resource extraction quality with real LLM outputs
  - improve local skill-trace extraction beyond adjacent order
  - accumulate transition priors across batches instead of only per-run reports
  - graph-role readiness for starters, transforms, fan-in nodes, validators, and synthesis nodes
  - motif discovery and motif-quality diagnostics for common GDPVal-style task structures
  - feedback hooks from generated task quality back to transition and motif weights
  - decide whether selected web-source graph calibration accepted candidates should enter the persistent registry, or remain experiment-only while transition priors are designed
  - start a minimal Pipeline B prototype that consumes `v3_pipeline_b_seed_set_report.json` and reports which Pipeline A signals are missing or useful

## GoldenRun Direction

Current state:

- The finance prototype has a deterministic GoldenRun.
- A general LLM-teacher GoldenRun is not yet fully implemented.

Needed direction:

- `TeacherRunRequest`
- `TeacherRunResult`
- `LLMTeacherRunner`
- teacher output validator
- rubric candidate builder

LLM teacher mode should use more information than the candidate, such as revealed traps, expected intermediate states, source provenance, and teacher-only checklists.

However, exact grading targets should still be traceable to visible source evidence unless explicitly marked as teacher-only.

## Current rw-task Smoke Runner

Pipeline B now has a guarded runner that consumes the prepared eval input and records execution metadata.

Default behavior:

- read `artifacts/pipeline_b/scratch/rw_task_eval_input_smoke/rw_task_eval_prep_report.json`
- verify `prep_status=prepared`
- write a dry-run `rw_task_eval_run_report.json`
- do not call `bench_standalone.stirrup_batch`, `grade_deliverables`, external APIs, or model providers

Explicit execution behavior:

- require both `--run-eval` and `--allow-draft-eval` for the current `draft_inspection_only` sample
- record model name, python executable, rw-task root, command list, start/end times, exit codes, output dirs, and failure reasons
- keep `not_final_training_data=true` and `evaluation_mode=draft_inspection_only` visible in all reports
- do not mutate `SkillRegistry/*.json`

The first real smoke has already answered that the V3 package can pass through the rw-task toolchain. Current executed eval evidence should still not be treated as formal model-separation evidence unless it is repeated on sufficiently closed `candidate_ready` cases.

Recommended next choices:

- follow `docs/architecture/pipeline_next_stage_global_plan.md` before any older next-slice note in this file
- add `global_task_validity_report.json`, `real_worldness_report.json`, `difficulty_profile_report.json`, `task_constraint_graph_report.json`, and `execution_plan_dag_report.json` as diagnostic-only reports without changing current Pipeline B decisions
- add `WorkflowEpisode` proposal output from existing Pipeline A extraction artifacts, without writing to `SkillRegistry/v3_skill_registry.json`
- add experimental workflow archetype and motif grammar files, starting with `policy_application` and `fan_in_reconciliation`, without making the sampler depend on them yet
- extend sampler and batch reports with role coverage fields such as `filled_roles`, `missing_roles`, `role_fit_scores`, `workflow_context_fit`, and `task_graph_shape_assumption`
- keep using `pipeline_b_batch_report.json`, `pipeline_b_batch_feedback_report.json`, `pipeline_a_substrate_audit_report.json`, and `typed_resource_patch_proposal_report.json` as diagnostic evidence, but do not treat typed-resource proposals as applied registry state

Current eval-feedback result:

- `feedback_status=analyzed`
- `eval_evidence_use=draft_quality_observation`
- 6 low-scoring criteria
- 5 prioritized Pipeline B actions
- 3 Pipeline A feedback items
- 14 candidate-ready blockers
- the highest-signal current weaknesses are:
  - prompt-to-deliverable contract clarity
  - evidence-to-conclusion traceability
  - skill-step operationalization in teacher states and prompt wording
  - policy-rule usage being too implicit

Current strengthened prompt/teacher contract result:

- the current deterministic blueprint now explicitly requires:
  - deliverable-path awareness
  - separation of supported conclusions, confirmed exceptions, and unresolved items
  - policy-sensitive conclusions to cite both evidence IDs and policy clause IDs
- the current GoldenPlan now explicitly includes:
  - `deliverable_outline`
  - `policy_clause_evidence_map`
- the current final-check set now explicitly includes:
  - `deliverable_requirement_coverage`
  - `policy_clause_traceability`
- latest deterministic smoke after this strengthening slice:
  - `teacher_runner`: 8 intermediate states, 5 final checks
  - `training_annotation`: 17 supervision items
  - `rubric`: 43 criteria
  - `package_assembler`: `package_readiness=revise_only`
  - `rw_task_eval_prep`: `prep_status=prepared`, `evaluation_mode=draft_inspection_only`

Current local evidence-traceability tightening result:

- the candidate prompt now requires every material bullet in `Supported conclusions`, `Confirmed exceptions`, and `Unresolved items` to end with local bracketed support such as `[Evidence: EV-###]` or `[Evidence: EV-###; Policy: POL-###]`
- TeacherRunner final checks and state purposes now distinguish general evidence availability from local bullet-level evidence support
- TrainingAnnotation/Rubric projection now checks local support for each material conclusion, policy-sensitive bullet, confirmed exception, and unresolved item
- deterministic traceability smoke results:
  - `teacher_input`: `partial_ready`, 2 generated candidate-visible files, 0 deferred files, 9 evidence-contract items, and no relationship warnings
  - `teacher_runner`: 8 intermediate states, 4 steps, 5 final checks
  - `training_annotation`: 17 supervision items
  - `rubric`: 43 total criteria, 28 rw-task-exportable criteria, 15 diagnostic criteria
  - `quality_gate`: `revise`, with reason codes focused on low subgraph confidence, partial intermediate states, Pipeline A signal gaps, and single-source support
  - `rw_task_export_validator`: `validation_status=draft_compatible`
  - `rw_task_eval_runner` dry-run: `run_status=dry_run_ready`
- authorized traceability external smoke completed with `gpt-5.4-pro`, `run_status=completed`, and score `53/62`; this stricter result should be read as a better diagnostic lens, not as final model-separation evidence

Current policy/evidence operationalization result:

- the candidate prompt now requires exact candidate-visible `Evidence_ID` values from the workbook, such as `EVID-001`, and explicitly says source labels such as `Manager Email` or `Ledger Snapshot` are not substitutes
- policy-sensitive bullets now require exact workbook evidence IDs plus `POL-###` clause IDs in the same local bracketed support
- TeacherRunner and TrainingAnnotation/Rubric wording now checks exact `Evidence_ID` support rather than generic evidence locations or source labels
- deterministic smoke results remain structurally stable:
  - `teacher_input`: `partial_ready`, 2 generated candidate-visible files, 0 deferred files, 9 evidence-contract items, and no relationship warnings
  - `teacher_runner`: 8 intermediate states, 4 steps, 5 final checks
  - `training_annotation`: 17 supervision items and 13 hidden traps
  - `rubric`: 43 total criteria, 28 rw-task-exportable criteria, 15 diagnostic criteria
  - `quality_gate`: `revise`
  - `rw_task_export_validator`: `validation_status=draft_compatible`
  - `rw_task_eval_runner` dry-run: `run_status=dry_run_ready`
- authorized policy/evidence external smoke completed with `gpt-5.4-pro`, `run_status=completed`, and score `58/62`
- eval feedback now reports only 3 low-scoring criteria, all tied to Evidence inventory ordering / teacher-step operationalization; policy-reference prompting is no longer the dominant low-score source

Current Evidence inventory section/template tightening result:

- the candidate prompt now requires exact top-level section order before any appendix:
  - `Evidence inventory`
  - `Deliverable outline`
  - `Evidence reviewed`
  - `Supported conclusions`
  - `Confirmed exceptions`
  - `Unresolved items`
  - `Policy clause mapping`
  - `Follow-up`
- `Evidence inventory` must be the first substantive section and must include `Evidence_ID`, `Source file`, `Observed item/value`, and `Intended use`
- required sections may not be placeholder-only; evidence inventory, evidence-to-conclusion map, and policy mapping details must appear inside their named sections rather than after `Follow-up`
- deterministic smoke results remain structurally stable:
  - `teacher_input`: `partial_ready`, 2 generated candidate-visible files, 0 deferred files, 9 evidence-contract items, and no relationship warnings
  - `teacher_runner`: 8 intermediate states, 4 steps, 5 final checks
  - `training_annotation`: 17 supervision items and 17 hidden traps
  - `rubric`: 43 total criteria, 28 rw-task-exportable criteria, 15 diagnostic criteria
  - `quality_gate`: `revise`
  - `rw_task_export_validator`: `validation_status=draft_compatible`
  - `rw_task_eval_runner` dry-run: `run_status=dry_run_ready`
- authorized inventory-section external smoke did not produce a quality score: the outer command timed out after the prepared eval started, no `rw_task_eval_run_report.json` or grader JSON was written, and the spawned Python processes were stopped
- treat this as an evaluation-runner/resume issue or inconclusive external smoke, not as evidence that task quality improved or degraded

Current rw-task compatibility fix result:

- the V3 rw-task exporter now converts internal V3 structured rubric objects into legacy rw-task-compatible `rubric_json`:
  - stringified list of rubric items
  - each item carries `score`, `criterion`, `required`, `rubric_item_id`, and `tags`
- the local export validator now accepts either:
  - structured JSON rubric payloads
  - stringified rw-task rubric-item lists
- the V3 eval runner now aligns `GRADER_MODEL` with the eval-prep model for `grade_deliverables`, instead of silently falling back to `rw-task/.env` `GRADER_MODEL`
- strengthened real draft smoke result after this fix:
  - `run_status=completed`
  - grader model: `gpt-5.4-pro`
  - `summary_status=summarized`
  - `evidence_use=draft_quality_observation`
  - total score `59 / 81`
  - average score ratio `0.7283950617283951`
  - eval feedback now reports 13 low-scoring criteria and 2 prioritized Pipeline B actions

Current LLM timing policy:

- Pipeline B Quality Gate V1 does not call LLMs or external APIs.
- LLM teacher mode should be scheduled after the quality gate has made package readiness explicit, or under an explicit partial-teacher exploration flag in a later slice.
- LLM outputs should be stored as teacher proposals or prose/reference-document drafts, not as grading truth by themselves.
- Grading truth must remain grounded in candidate-visible evidence or be explicitly labeled as teacher-only supervision.

## Environment Notes

Use conda Python, not bare Python.

Known useful interpreters:

- `D:\miniconda3\envs\gdpval\python.exe`
- `D:\miniconda3\envs\real-world-task\python.exe`

The `real-world-task` environment is used for rw-task evaluation. The `gdpval` environment has been useful for generation and pandas/openpyxl work.

rw-task smoke note:

- the current Codex environment can validate export, eval prep, and runner dry-run locally
- explicit `--run-eval --allow-draft-eval` locally showed two runtime boundaries:
- missing `E2B_API_KEY` if the process environment is not populated from `E:\THU\2026Spring\SRT\rw-task\.env`
- `All connection attempts failed` when the current sandbox blocks outbound E2B connectivity even after the runtime env is loaded
- an authorized external run completed both prepared commands and produced grader output
- treat the completed smoke as toolchain evidence and draft-quality observation, not final task-quality truth
- the current evaluation focus is to harden executed evidence closure and keep blocked or dry-run summaries out of comparison intake, not to claim a formal model-comparison verdict yet

Tuzi/OpenAI-compatible provider notes:

- Repo `.env` currently contains `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY`, and `OPENAI_API_KEY_BACKUP`.
- `src/task_generator/v3_skill_extractor.py` now accepts `OPENAI_API_KEY_BACKUP` as a fallback when `OPENAI_API_KEY` is absent.
- `Test/probe_tuzi_models.py` supports `--key-source primary`, `--key-source backup`, and `--key-source auto` for explicit smoke testing.
- Tuzi docs describe OpenAI-compatible chat at `/v1/chat/completions` and responses at `/v1/responses`; the configured repo base URL is `https://api.tu-zi.com/v1`.
- Smoke tests on 2026-07-01:
  - `D:\miniconda3\envs\gdpval\python.exe Test\probe_tuzi_models.py --env-path .env --key-source backup --model gpt-5.4 --timeout 90` returned HTTP 200, but the chat message content was empty.
  - `D:\miniconda3\envs\gdpval\python.exe Test\probe_tuzi_models.py --env-path .env --key-source backup --model gpt-5.4-pro --timeout 90` returned HTTP 200 with `pong`.
  - `D:\miniconda3\envs\gdpval\python.exe Test\probe_tuzi_models.py --env-path .env --key-source primary --model gpt-5.4-pro --timeout 90` also returned HTTP 200 with `pong`.
- Practical conclusion: use `gpt-5.4-pro` for the next Tuzi smoke tests. The primary key is currently usable; `OPENAI_API_KEY_BACKUP` is validated and can be used manually if the primary key fails or automatically when the primary key is absent.
- Current Pipeline B table-first reference-file generation, teacher-input contract building, and TeacherRunner V1 should all remain deterministic local code and do not require E2B/Stirrup or LLM calls yet. Use E2B/Stirrup and Tuzi model calls later for sandboxed agent workflows, prose-heavy reference documents, scenario variation, and future LLM teacher mode.
- Do not print API keys in logs or reports. Only record key source names such as `OPENAI_API_KEY` or `OPENAI_API_KEY_BACKUP`.

The worktree may contain unrelated dirty files and generated outputs. Do not revert user or unrelated changes.

## Working Style

When continuing this project:

- Think in batches, not single examples.
- Convert single-task fixes into reusable schema fields, validator rules, or quality-gate checks.
- Keep source provenance explicit.
- Keep Pipeline A and Pipeline B modular.
- Use the finance prototype to validate architecture, not as the center of the research.
