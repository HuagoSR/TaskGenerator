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

R10 Scenario-First is the active research boundary. R10.0 offline contracts, R10.1 public seed admission and R10.2 teacher-only Bible compilation are implemented: four admitted public Work Seeds, two professional rule sets, six V1 contracts, report-only validators and four admitted Scenario Bibles. R10.3 readiness exposed that a deterministic projection of narrative Bibles is the wrong abstraction. Keep those Bibles frozen; do not build a structured Bible V2 or fabricate files from prose. The R10.3 offline Skill foundation is implemented: two draft professional Skill packages, a thin catalog and progressive loader exist, while the historical Registry remains unchanged. The next slice curates their public professional evidence; it must not create tasks. Solver/grader runs, registry mutation, release activation, training and promotion remain unauthorized.

## Architecture Boundaries

```text
Public Work Seed → Professional Rules → Scenario Bible
→ Professional Skill Selection → Derived Evidence Bundle
→ Candidate Task → Teacher Truth / Rubric
→ Static Admission → Behavioral Admission
```

- A `WorkSeed` explains why a real worker receives a task; it is not a prompt or complete case.
- `ScenarioBible` is the teacher-only parent authority for business facts. A frozen derived evidence bundle may add explicit, non-conflicting task facts while retaining its parent Bible link.
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

The implemented foundation defines `WorkSeedV1`, `ProfessionalRuleSetV1`, `ScenarioBibleV1`, `EvidenceProjectionPlanV1`, `TaskDecisionMatrixV1`, `ScenarioFirstAdmissionReportV1` and the draft `ProfessionalSkillCatalogEntryV1` loader contract. For the active R10 path, file and record counts are quality guidance, not new hard contracts. Hard boundaries are source linkage, normal business context, candidate/teacher isolation, no answer-label leakage, solvability (including supported uncertainty), openable deliverables and exact submission paths. The next slice curates public professional evidence for the two draft Skills; it must not create tasks. Four tasks require static and multi-model behavioral admission before any ten-task production plan.
