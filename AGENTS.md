# TaskGenerator Project Instructions

## 1. Project Goal

TaskGenerator builds a governed factory for GDPVal-style real-world training tasks. The primary objective is an automatic task-production and training-data system. Benchmark generation is a useful secondary capability, not the main claim.

The system should repeatedly produce tasks with realistic source context, reusable semantic skills, workflow-conditioned structure, candidate-visible reference files, teacher-mode solutions, training annotations, executable rubrics, quality filtering, rw-task export, and evidence-backed promotion decisions.

## 2. Read First

Read documents in this order:

1. `项目概要.md` — the only project-level source of truth for current status, phase conclusions, bottlenecks, and the A–F roadmap.
2. `docs/README.md` — documentation lifecycle and index.
3. `docs/architecture/system_architecture.md` — current technical architecture.
4. `docs/architecture/global_interface_contracts.md` — interface contracts.
5. `docs/architecture/production_mvp_definition.md` — current production contract.

Use `docs/archive/` only when historical reasoning or exact phase evidence is needed. Archived plans and handoffs must not override the root overview.

## 3. Current State

Phase 16 is complete:

```text
records = 24 / 24 completed
grader = gpt-5.4-pro
phase16_decision = redesign_again
promotion_decision = do_not_promote_default_chain
default_generator_change_allowed = false
```

Contract V2 and productive-complexity behavior remain experimental. Do not continue local `evidence_to_deliverable` tuning or promote them into the default generator without a new explicitly approved research slice.

The current roadmap is:

- A. Phase 16 evidence closure — complete.
- B. Documentation and project-state governance — complete.
- C. Local end-to-end automation — complete.
- D. Server reproduction — complete; active release is `milestone-d-094c6cb`.
- E. Warehouse-inventory vertical slice — complete; offline, public-source DeepSeek, contamination, and server evidence passed.
- F. Training-data readiness — finance production and the governed 30-task model-difference evaluation are complete; research interpretation is next.

Milestone E kept GDPVal outside generation. The active server release is `milestone-f-data-production-6304e84`. The finance campaign completed 60/60 candidate-ready tasks with 20 per allowed motif, verifier/export pass for all tasks, zero QA-blocked cases, and no external task evaluation. It does not authorize task-package upload, reward training, SFT, or RL.

## 4. Architecture Boundaries

Treat the project as four connected layers:

```text
Source / Skill / Resource Substrate
        ->
Workflow / Motif / Task-graph Planning
        ->
Task Package Generation
        ->
Validity / Evaluation / Feedback / Promotion
```

Pipeline A is Source-to-Skill. It extracts semantic skills, typed resources, trace context, motif hints, and workflow proposals from source material. It is LLM-heavy, but review, registry mutation, and promotion must remain explicit.

Pipeline B is Skill-to-Task. It assembles task subgraphs into blueprints, reference files, GoldenRun, TrainingAnnotation, rubric, packages, and rw-task exports. Scenario construction may use LLMs; validation, provenance, packaging, and quality gates should stay deterministic where possible.

Do not collapse the following boundaries:

- GDPVal is `eval_calibration_only`; never use GDPVal tasks or hidden rubrics as training-generation material.
- Candidate-visible truth and teacher-only supervision must remain separate.
- Static quality scores are filters, not substitutes for executed model evidence.
- Single-task or one-off eval evidence is diagnostic unless the governed comparison contract says otherwise.
- Registry, readiness, transition-prior, sampler-weight, and promotion changes require explicit review/apply paths.
- Do not claim UCB or bandit behavior before comparable quality feedback exists.

## 5. Repository Layout

- Reusable implementation: `src/task_generator/`.
- CLI and smoke runners: `Test/`; runners prepend repository `src/` to `sys.path`.
- Active architecture docs: `docs/architecture/`.
- Static explanatory examples: `docs/examples/`.
- Historical plans, handoffs, and reports: `docs/archive/`.
- Generated outputs and run reports: `artifacts/` or an ignored generated-output directory.
- Active registry and governed stores: `SkillRegistry/`.
- Legacy operator-heavy code: `src/task_generator/Skill/`.
- Reference-file generators: `src/task_generator/FileGenerator/`.
- Prompt utilities: `src/task_generator/Prompt/`.

Do not add implementation modules, stage reports, experiment dumps, notebooks, screenshots, or generated outputs to the repository root.

`Test/v2_outputs/` is a hard no-touch zone unless the user explicitly reopens it.

## 6. Documentation Governance

- `项目概要.md` alone owns macro goals, current status, phase ledger, bottlenecks, and roadmap.
- Local technical documents own only their subsystem or interface.
- A temporary workstream plan must be linked from the overview while active and moved to `docs/archive/` when closed.
- Archived documents are historical and effectively read-only.
- Historical runners must write regenerated handoffs and scope documents under `artifacts/historical_phase_runs/`, not active docs.
- At phase close, update the overview with core evidence and archive detailed plans/reports.
- Avoid exhaustive module inventories in docs; code and tests are the implementation inventory.

## 7. Generated Artifacts And Secrets

- `.env` is secret-bearing and must never be staged or committed.
- `deepseek-key.txt` is a local ignored compatibility file; never print or commit it.
- Never write API keys, bearer tokens, or full secret values into prompts, task packages, logs, JSON, Markdown, examples, or commits.
- Secret values may enter a process only as authentication material for the configured endpoint.
- Raw task packages, provider outputs, grader outputs, retry logs, and execution logs remain ignored artifacts.
- Preserve user-owned dirty changes and unrelated artifacts. Do not reset or overwrite them.

External-eval permission is scoped. A prior authorization applies only to the explicitly named campaign. Obtain explicit permission for any new private-package external run.

## 8. Environment And Existing Tooling

Use the existing environments instead of creating new ones:

```text
D:\miniconda3\envs\taskgenerator\python.exe
D:\miniconda3\envs\real-world-task\python.exe
D:\miniconda3\envs\gdpval\python.exe
E:\THU\2026Spring\SRT\rw-task
```

Use `taskgenerator` for repository runners and orchestration. Use `real-world-task` for rw-task execution when the prep contract specifies it. The repository runner already handles `PYTHONPATH`, timeout, partial failure, and grader configuration; do not bypass it with direct provider calls.

Before expensive execution, run structural readiness, verifier, export validation, package fingerprinting, and dry-run/runbook checks. Keep completed results, preserve first failures, and follow the campaign retry policy rather than silently replacing evidence.

## 9. Engineering Rules

- Work in batches and preserve deterministic reproducibility.
- Convert repeated single-task fixes into schema, contract, validator, or quality-gate improvements.
- Keep source provenance and candidate-visible evidence explicit.
- Prefer report-first diagnostics before canonical mutation.
- Keep promotion and rollback reviewable.
- Prefer small bounded experiments over broad uncontrolled model or domain sweeps.
- Do not add new root-level modules.
- Use `apply_patch` for hand edits and preserve unrelated worktree changes.
- Update active docs when an expected path, interface, or operational boundary changes.

## 10. Next Workstream Boundary

Milestone C is complete. The unified local runner now provides Manifest V2, scratch-first profiles, checksum-backed reuse, resume/rerun/status actions, public offline and LLM smoke profiles, lifecycle indexing, and eval preparation with external eval disabled by default.

Milestones D and E are complete. Milestone F finance production produced 60/60 candidate-ready tasks. The governed evaluation of 30 tasks is complete with 120/120 solver processes returned, 116 valid deliveries, 116 primary grades, 63 audit grades, four `gpt-4o-mini` non-deliveries, and no OOM or provider failure. The remaining 30 tasks are not authorized for evaluation. The next work is research interpretation and training-data-readiness planning; this does not authorize RL training, default-chain promotion, or broad multi-domain expansion.
