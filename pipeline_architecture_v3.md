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

- `pipeline_architecture_v3.md`
  - macro architecture
  - two-pipeline plan
  - batch automation roadmap
  - near-term engineering priorities
- `schema_design_v2.md`
  - V2 object definitions
  - finance prototype history
  - quality-gate lessons
  - dynamic evaluation notes

Historical context documents:

- stage report 1 markdown/pdf files
- stage report 2 markdown files
- stage report 3 markdown files
- stage report 4 markdown/pdf files
- stage report 5 markdown/pdf files

The historical reports are useful for understanding why the project moved away from operator-heavy skill extraction. They should not be treated as the current implementation plan unless their ideas are restated in this roadmap.

Code-facing documents and artifacts:

- `v2_schema.py`: current V2 structured objects
- `v2_semantic_skills_finance.json`: finance seed skill examples
- `v2_semantic_skills_migrated.json`: migrated historical skill examples
- `v2_quality_gate.py`: current structural acceptance gate
- `v2_task_quality.py`: current static quality scorer

Document maintenance rule:

- put schema changes in `schema_design_v2.md`
- put project roadmap changes in `pipeline_architecture_v3.md`
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

### 2. TaskBlueprintAssembler

Responsibility:

- turn selected semantic skills into a concrete task plan
- define role, scenario, evidence package, traps, deliverable, and GoldenRun plan

This is a good place for LLM assistance because business realism matters.

The assembler must output structured JSON, not only a prompt.

### 3. ReferenceFileGenerator

Responsibility:

- create concrete files required by the blueprint
- preserve provenance from generated values to GoldenRun targets

Recommended strategy:

- code-led generation for numeric facts and tables
- LLM assistance for realistic wording, notes, emails, memos, and contextual documents
- no unverified LLM-generated numeric backbone unless another validator can check it

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

LLM teacher mode should use more information than the candidate:

- revealed traps
- expected intermediate states
- source provenance
- hidden constraints
- teacher-only checklist

But exact grading targets should still be traceable to candidate-visible evidence unless they are explicitly marked as teacher-only supervision.

### 5. RubricBuilder

Responsibility:

- convert GoldenRun outputs into executable or semi-executable grading criteria
- separate result checks from reasoning checks
- record tolerance and evidence source

Rubrics should not be only prose. They should include machine-readable anchors.

### 6. ExportAdapter

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

- `RawSource` schema
- `NormalizedSource` schema
- `ExtractedSkill` schema with evidence spans
- source collection runner using stirrup
- source normalization runner
- skill extraction runner
- skill deduplication and registry update logic

### Missing in Pipeline B

- generic skill sampler
- generic blueprint assembler
- LLM teacher runner
- rubric builder that consumes teacher outputs
- provenance checks from rubric anchors back to source files
- batch orchestration CLI
- persistent batch reports

### Existing Assets To Reuse

- `v2_schema.py`
- `v2_task_compiler.py`
- `FileGenerator/v2_blueprint_generator.py`
- `v2_golden_run.py`
- `v2_quality_gate.py`
- `v2_task_quality.py`
- `rw_task_adapter.py`
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

- `v3_source_schema.py`
- `SourceCollector` runner
- `SourceNormalizer` runner
- `SkillExtractor` runner
- a small extracted skill registry from 5-10 finance/audit sources

Current implementation status:

- `v3_source_schema.py` defines the first source-to-skill schema layer:
  - `RawSource`
  - `NormalizedSource`
  - `SourceBlock`
  - `SourceSpan`
  - `SkillEvidence`
  - `ExtractedSkillCandidate`
  - `SkillRegistryEntry`
  - `SkillExtractionPromptPackage`
- `Test/run_v3_local_source_to_skill.py` provides a local no-network prototype:
  - reads `.txt` and `.md` files
  - creates `RawSource` records
  - splits text into normalized blocks
  - emits a skill-extraction prompt package for a later LLM step
- `v3_skill_extractor.py` provides a deterministic mock extractor:
  - consumes `SkillExtractionPromptPackage`
  - emits `ExtractedSkillCandidate` objects
  - is intended for pipeline testing, not final research-quality extraction
- `v3_skill_extractor.py` also provides an LLM-backed extractor interface:
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
- `v3_skill_reviewer.py` provides a deterministic first-pass candidate reviewer:
  - scores reusability, diversity, semantic clarity, evidence grounding, and assembly usefulness
  - penalizes operator leakage and single-instance overfit
- `Test/run_v3_skill_candidate_reviewer.py` emits reviewed candidates, accepted candidates, and review reports
- `v3_skill_registry.py` provides a first-pass deterministic registry builder:
  - converts candidates into `SkillRegistryEntry` records
  - performs simple name-based deduplication
- `Test/run_v3_skill_registry_builder.py` builds `skill_registry.json` from extracted candidates
- smoke-test output exists under `Test/v2_outputs/v3_source_to_skill_demo`

What is intentionally not done yet:

- no web search collector
- direct DeepSeek smoke testing has passed on the public synthetic package
- GDPVal prompt-only extraction has passed on 5 `Accountants and Auditors` prompts:
  - provider: DeepSeek official `deepseek-v4-flash`
  - candidates produced: 5
  - reviewer accepted: 5
  - registry entries produced: 5
- external testing on private workspace source packages should remain blocked unless the source package is explicitly approved for upload
- no semantic embedding or LLM-based registry deduplication
- accepted/rejected skill review loop exists, but the first-pass reviewer is likely too permissive

The immediate next code step is to tighten the reviewer so narrow jurisdiction- or form-specific candidates are marked as `revise` unless they are abstracted into reusable skills.

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

The next implementation step should be Pipeline A, not another finance task.

Recommended first code task:

- add `v3_source_schema.py`
- define `RawSource`, `NormalizedSource`, `SourceBlock`, `ExtractedSkillCandidate`, and `SkillRegistryEntry`
- add a small CLI that reads local source text files and emits extracted skill candidates through an LLM prompt

This will reconnect the project to the original two-pipeline design:

- natural language to semantic skill library
- semantic skill library to batch real-world tasks
