# TaskGenerator Project Instructions

## Project Goal

TaskGenerator is a governed factory for GDPval-style professional tasks. Its research goal is to automatically construct realistic, multi-file occupational scenarios with candidate-visible evidence, teacher-only truth, executable delivery contracts and behavior-backed evaluation. Training-data production is a future outcome, not an assumption.

## Read First

1. `项目概要.md` — only project-level source of truth.
2. `docs/README.md` — documentation lifecycle and index.
3. `docs/architecture/system_architecture.md` — current and target architecture.
4. `docs/architecture/global_interface_contracts.md` — stable and proposed contracts.
5. `docs/architecture/production_mvp_definition.md` — production semantics.
6. `docs/architecture/pipeline_reconstruction_problem_statement.md` — R10 research problem.
7. `docs/architecture/pipeline_reconstruction_optimization_plan.md` — active R10 plan.
8. `docs/operations/pipeline_reconstruction_runbook.md` — operational stop point and preconditions.

Use `docs/archive/` only for historical evidence; it never overrides the overview.

## Current State

R9 proved the production and evaluation infrastructure; R7's fully fresh reproduction froze at 5/10 because the task-design provider was unstable. Both are historical evidence. Do not resume R7, merge cohorts or interpret it as a partial evaluation.

R10 Scenario-First is the active research boundary. R10.0–R10.7 established public Work Seeds, professional rules, narrative Scenario Bibles, agent-native professional Skills, derived evidence bundles, four statically admitted tasks and a four-task behavioral pilot. R10.8 corrected one teacher anchor, diagnosed low separation, and tested two GDPval-calibrated compiler revisions. Its final official ChatGPT Codex/DeepSeek campaign left the income task as `near_tie` and the price task as `judge_ambiguous`, so R10.8 closed as `evaluator_revision_required` without six/ten-task expansion. R10.9 is now the active experiment: reuse two public Seeds/Rules but create new work worlds before any task exists, derive one baseline and one profession-constrained adversarial variant per domain, mine tasks from frozen candidate artifacts, reconstruct truth independently, calibrate Judges with three full deliverable tiers, and only then run two solvers. Do not reuse old Bibles, candidate files, tasks, answers or receipts in R10.9.

## Architecture Boundaries

```text
Public Work Seed + Professional Rules
→ Professional Skill / natural-difficulty deliberation
→ frozen work world and candidate business artifacts
→ independent Task Mining
→ independent Teacher Truth / Rubric reconstruction
→ Judge calibration → Behavioral Admission
```

- A `WorkSeed` explains why a real worker receives a task; it is not a prompt or complete case.
- Historical `ScenarioBible` remains a teacher-only parent authority. R10.9 does not reuse those Bibles or introduce Bible V2; its new teacher-only world ledger is campaign-scoped and exists before task mining.
- Candidate files are projections of the same world state. Facts, not labels such as `Questionable` or `Exception`, must reveal conflicts and gaps.
- Professional Skill is an agent-native, source-grounded knowledge package for factory-side professional judgment, coverage and failure attribution. Generic tool skills are reused rather than duplicated. Motif is a relationship label and analysis dimension; neither determines task form alone.
- GDPval is `eval_calibration_only`; never use its tasks, hidden rubrics or content as generation or training inputs.
- Candidate-visible truth, teacher-only supervision and run/governance evidence must remain separate.
- LLM may propose semantic content and evidence extensions. Deterministic code retains only the hard boundaries: source linkage, candidate/teacher isolation, openable files, answer-leakage checks, submission paths, manifests and state changes.

## Repository Layout

- Reusable implementation: `src/task_generator/`.
- CLI and smoke runners: `Test/`.
- Active architecture docs: `docs/architecture/`.
- Operational docs: `docs/operations/`.
- Historical plans and reports: `docs/archive/`.
- Historical registry: `SkillRegistry/` (read-only for R10); draft professional Skill packages live in `.agents/skills/r10/`, with discovery metadata in `data/r10/professional_skills/catalog.json`.
- Generated outputs and run reports: ignored `artifacts/`.

Do not add implementation modules, experiments, screenshots, generated outputs or notebooks to the repository root. `Test/v2_outputs/` is no-touch unless the user explicitly reopens it.

## Documentation Governance

- `项目概要.md` alone owns macro status, evidence, bottlenecks and roadmap.
- Architecture documents own only structure and interfaces; the runbook owns executable boundaries.
- Completed workstream detail goes to `artifacts/` and later `docs/archive/`; do not append campaign logs to active docs.
- Code schemas are the source of truth for implemented field-level contracts. Proposed docs must say `not_implemented`.

## Secrets and Artifacts

- `.env`, `deepseek-key.txt`, API keys, bearer tokens and authentication files must never be printed, committed, copied into images or written into artifacts.
- Provider output, task packages, graders, retry logs and execution logs remain ignored artifacts.
- Preserve user-owned dirty changes and unrelated artifacts. Never reset or overwrite them.
- External evaluation authorization is campaign-scoped; a previous consent never authorizes a new private-package upload.

## Engineering Rules

- Use `apply_patch` for hand edits; preserve unrelated worktree changes.
- Prefer report-first diagnostics and convert recurring defects into contracts, validators or compiler improvements.
- Compile prompt submission instructions, expected deliverables, staging and grading from one `DeliverableContract`.
- Keep structural validity, professional validity, delivery success and model behavior as separate evidence axes.
- Do not grade invalid deliveries or redraw a low-score answer.
- Before costly execution, run structural readiness, verifier/export checks, package fingerprinting and applicable parity.
- Treat static checks and LLM proxies as provisional; they do not establish expert validity, training admission or default-chain promotion.

## R10 Implementation Boundary

The implemented foundation defines `WorkSeedV1`, `ProfessionalRuleSetV1`, `ScenarioBibleV1`, `EvidenceProjectionPlanV1`, `TaskDecisionMatrixV1`, `ScenarioFirstAdmissionReportV1`, `ProfessionalSkillCatalogEntryV1`, source-bound professional-Skill curation, thin paired-evidence experiment contracts, and the R10.6 task/truth compiler. For the active R10 path, file and record counts are quality guidance, not new hard contracts. Hard boundaries are source linkage, normal business context, candidate/teacher isolation, no answer-label leakage, solvability (including supported uncertainty), openable deliverables, evidence-map closure and exact submission paths. R10.6 compiles two user-review tasks from frozen winning bundles; it must not run solver/grader. Four tasks require static and multi-model behavioral admission before any ten-task production plan.
