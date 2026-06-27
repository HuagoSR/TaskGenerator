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
2. Use GDPVal prompt-only packages as a safe benchmark-like input source, but do not use GDPVal rubrics/files/answer traces for extraction.
3. Treat one GDPVal prompt as potentially yielding multiple atomic skills; avoid one-prompt-one-broad-skill extraction.
4. Later connect the collector to stirrup so a model can search the web in a sandbox and save source materials.
5. Use the persistent registry update/deduplication step to scale Pipeline A across more prompt-only batches.
6. Only after Pipeline A has broader coverage and better reviewer calibration, update Pipeline B so it samples from the registry instead of hardcoded finance skills.

Current Pipeline A starting files:

- `v3_source_schema.py`: source-to-skill schema objects
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
- `SkillRegistry/v3_skill_registry.json`: current persistent V3 atomic skill registry
- `SkillRegistry/v3_skill_registry_update_report.json`: latest persistent registry update and coverage report
- `SkillRegistry/v3_pipeline_a_batch_report.json`: latest aggregate Pipeline A batch report
- `Test/v2_outputs/v3_source_to_skill_demo`: smoke-test output from the local prototype

Current Pipeline A status:

- local source normalization works
- deterministic mock skill extraction works
- LLM-backed extraction code exists
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
  - sources: `Accountants and Auditors`, `Financial Managers`, `Financial and Investment Analysts`, `Compliance Officers`
  - persistent registry entry_count is 44
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
- no web collector yet
- external LLM tests should only use public or explicitly user-cleared source packages
- no embedding or LLM-based registry deduplication yet
- no registry quarantine/inactive mechanism yet; current stale-entry handling is report-only via `unmatched_existing_entries`

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
