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

1. Add `v3_source_schema.py` for source-to-skill objects.
2. Add a local source-to-skill prototype that reads text files and emits `ExtractedSkillCandidate` records.
3. Later connect the collector to stirrup so a model can search the web in a sandbox and save source materials.
4. Build a skill registry update/deduplication step.
5. Only after that, update Pipeline B so it samples from the registry instead of hardcoded finance skills.

Current Pipeline A starting files:

- `v3_source_schema.py`: source-to-skill schema objects
- `Test/run_v3_local_source_to_skill.py`: local no-network prototype for normalizing `.txt` and `.md` sources and producing a skill-extraction prompt package
- `Test/v2_outputs/v3_source_to_skill_demo`: smoke-test output from the local prototype

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
