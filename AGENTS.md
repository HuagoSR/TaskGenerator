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

- `pipeline_architecture_v3.md`: current macro roadmap and future plan
- `schema_design_v2.md`: V2 schema details, finance prototype history, and evaluation lessons

Older stage reports are useful history, especially for why the project moved away from operator-heavy skill extraction, but they are not the current plan unless restated in `pipeline_architecture_v3.md`.

## Current Code State

Useful existing assets:

- `v2_schema.py`: current V2 structured objects
- `v2_semantic_skills_finance.json`: finance seed skills
- `v2_semantic_skills_migrated.json`: migrated historical skills
- `v2_task_compiler.py`: finance-specific skill-to-task compiler prototype
- `FileGenerator/v2_blueprint_generator.py`: finance-specific reference file generator
- `v2_golden_run.py`: deterministic finance GoldenRun prototype
- `v2_quality_gate.py`: structural acceptance gate
- `v2_task_quality.py`: static quality scorer
- `rw_task_adapter.py`: rw-task export adapter
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

The next priority is Pipeline A.

Recommended next implementation steps:

1. Keep improving Pipeline A around atomic, reusable, evidence-backed skill extraction.
2. Upgrade Pipeline A from isolated skill nodes to a composable skill graph.
3. Preserve the old port idea, but do not rely on string-equality port matching.
4. Treat ports as typed semantic resources with attributes, such as `MonetaryAmount`, `FinancialMetric`, `ControlEvidence`, `AuditFinding`, `Jurisdiction`, or `TimePeriod`.
5. Extract local skill traces from sources, so natural source order such as `A -> B -> C` can become initial transition evidence.
6. Store transition priors and compatibility signals outside skill nodes, not as static `possible_successors` embedded in every skill.
7. Use GDPVal prompt-only and web-source batches to learn common task motifs, such as reconciliation, policy application, evidence fan-in, exception escalation, and cross-check validation.
8. Keep governance report-first: transition/readiness decisions should not mutate or delete registry entries unless a later schema migration explicitly adds such fields.

New Pipeline A target:

- move from `source -> atomic skills -> registry` to `source -> atomic skills + semantic resources + local transition traces + motif hints -> composable registry graph`
- keep the registry useful for future Pipeline B by making each skill's compositional interface explicit
- avoid returning to the slow old strategy where every new skill triggers all-pairs LLM successor judging

Current Pipeline A starting files:

- `v3_source_schema.py`: source-to-skill schema objects
- `v3_source_collector.py`: Stirrup/E2B-backed SourceCollector contracts, prompt builder, manifest validator, and RawSource writer
- `v3_source_search_tools.py`: Serper-backed Stirrup-compatible web search/fetch tool provider
- `Test/run_v3_stirrup_source_collector.py`: CLI for collecting public web source materials; requires explicit `--allow-web-collection`
- `Test/run_v3_collected_sources_to_skill_package.py`: connector CLI for turning collected `RawSource` records into normalized sources and a skill-extraction prompt package
- `Test/run_v3_web_source_pipeline_a.py`: one-command runner for existing collected web sources -> normalization -> LLM extraction -> review -> persistent registry update
- `Test/run_v3_web_source_pipeline_a_batch.py`: batch runner for multiple web-source topics or existing collection dirs -> collection/reuse -> Pipeline A -> aggregate quality report
- `Test/run_v3_local_source_to_skill.py`: local no-network prototype for normalizing `.txt` and `.md` sources and producing a skill-extraction prompt package
- `v3_skill_extractor.py`: extractor interfaces plus deterministic mock, LLM extractor, and provider fallback logic
- `Test/run_v3_mock_skill_extractor.py`: CLI for the mock extractor
- `Test/run_v3_llm_skill_extractor.py`: CLI for Tuzi/OpenAI-compatible, DeepSeek official, and mock fallback extraction
- `Test/build_v3_public_smoke_package.py`: builds a public synthetic source package safe for external LLM smoke tests
- `Test/v3_public_smoke_package`: tracked public synthetic smoke input; generated extraction/registry output dirs are ignored
- `Test/build_v3_gdpval_prompt_sources.py`: builds GDPVal prompt-only source packages from task_id, sector, occupation, and prompt only
- `Test/run_v3_gdpval_pipeline_a_batch.py`: one-command GDPVal prompt-only Pipeline A batch runner
- `v3_skill_reviewer.py`: deterministic first-pass reviewer for reusability, diversity, semantic clarity, evidence grounding, assembly usefulness, atomicity, operator leakage, single-instance overfit, and task-level overbreadth
- `Test/run_v3_skill_candidate_reviewer.py`: CLI for reviewed/accepted candidate outputs
- `v3_skill_registry.py`: first-pass registry builder plus persistent registry updater that turns accepted candidates into `SkillRegistryEntry` records
- `Test/run_v3_skill_registry_builder.py`: CLI for building `skill_registry.json`
- `Test/run_v3_skill_registry_update.py`: CLI for updating the persistent registry at `SkillRegistry/v3_skill_registry.json`
- `v3_skill_registry_audit.py`: non-destructive deterministic audit helper for stale or suspicious persistent registry entries
- `Test/run_v3_skill_registry_audit.py`: CLI for writing `SkillRegistry/v3_skill_registry_audit_report.json` without changing the registry
- `v3_registry_sampling_readiness.py`: report-only sampler readiness assessor that combines registry, audit, and reviewer calibration signals
- `Test/run_v3_registry_sampling_readiness.py`: CLI for writing `SkillRegistry/v3_registry_sampling_readiness_report.json`
- `v3_skill_transition_graph.py`: report-only transition graph and composition readiness builder for typed resource compatibility, local trace priors, motif hints, and graph-role labels
- `Test/run_v3_skill_transition_graph.py`: CLI for writing `SkillRegistry/v3_skill_transition_graph_report.json` and `SkillRegistry/v3_composition_readiness_report.json`
- `v3_skill_graph_diagnostics.py`: report-only diagnostics for typed resource coverage, trace-edge coverage, motif coverage, and invalid graph references
- `Test/run_v3_skill_graph_diagnostics.py`: CLI for writing `graph_extraction_diagnostics.json` from any extraction output directory
- `v3_pipeline_b_seed_set.py`: report-only selector for the first Pipeline B seed skill slice from registry/readiness outputs
- `Test/run_v3_pipeline_b_seed_set.py`: CLI for writing `SkillRegistry/v3_pipeline_b_seed_set_report.json`
- `v3_calibration_registry_admission.py`: report-only admission reviewer for graph calibration accepted candidates
- `Test/run_v3_calibration_registry_admission.py`: CLI for writing `SkillRegistry/v3_calibration_registry_admission_report.json`
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
  - handoff document: `PIPELINE_A_TO_B_HANDOFF_2026-06-30.md`
  - seed set report: `SkillRegistry/v3_pipeline_b_seed_set_report.json`
  - current seed set: 20 selected skills, all `sample_ready`
  - selected seed motif counts: 12 `policy_application`, 8 `evidence_to_deliverable`, 7 `cross_check_validation`, 5 `fan_in_reconciliation`
  - calibration admission report: `SkillRegistry/v3_calibration_registry_admission_report.json`
  - current calibration admission result: 15 candidates reviewed, 14 `recommend_admit`, 1 `merge_existing`; this is report-only and does not update the persistent registry
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

## Environment Notes

Use conda Python, not bare Python.

Known useful interpreters:

- `D:\miniconda3\envs\gdpval\python.exe`
- `D:\miniconda3\envs\real-world-task\python.exe`

The `real-world-task` environment is used for rw-task evaluation. The `gdpval` environment has been useful for generation and pandas/openpyxl work.

The worktree may contain unrelated dirty files and generated outputs. Do not revert user or unrelated changes.

## Working Style

When continuing this project:

- Think in batches, not single examples.
- Convert single-task fixes into reusable schema fields, validator rules, or quality-gate checks.
- Keep source provenance explicit.
- Keep Pipeline A and Pipeline B modular.
- Use the finance prototype to validate architecture, not as the center of the research.
