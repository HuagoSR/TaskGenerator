# TaskGenerator Project Instructions

## Read First

1. [项目概要.md](项目概要.md): sole source of macro status, evidence, limitations and next direction.
2. [docs/README.md](docs/README.md): document index and lifecycle.
3. [System architecture](docs/architecture/system_architecture.md): structure and responsibilities.
4. [Contracts](docs/architecture/global_interface_contracts.md): interface index; code owns field definitions.
5. [Production MVP](docs/architecture/production_mvp_definition.md): production and evidence semantics.
6. [Research problem](docs/architecture/pipeline_reconstruction_problem_statement.md): hypotheses.
7. [Next direction](docs/architecture/pipeline_reconstruction_optimization_plan.md): proposed work.
8. [Runbook](docs/operations/pipeline_reconstruction_runbook.md): executable boundaries.

Historical docs never override the overview. Do not duplicate campaign status across these files.

## Goal and Current Boundary

Automatically construct realistic, solvable, multi-file occupational tasks with candidate evidence, teacher supervision and fair rubrics. Evaluation supports task generation; building a leaderboard is not the project goal.

All released task packages must remain compatible with the GDPval task shape: `dataset_row.json`, `reference_files/`, `deliverable_files/`, and the original task rubric semantics. GDPval itself remains calibration-only.

The current quality target is a reproducible method that repeatedly produces realistic, evidence-grounded, solvable occupational tasks with fair rubrics. Strong/weak separation is auxiliary behavioral evidence, not the production objective. Controlled Solver calibration uses one frozen Stirrup/E2B harness across models. The retained grading calibration uses constrained native Codex/OpenCode Agents: one anonymous submission at a time, every rubric item exactly once, structured evidence references, integer item awards and controller-computed totals. Pairwise preference, holistic evaluation and high-score-triggered downward audit are diagnostic-only and cannot change the primary score.

RL, training and an automatic score-to-generator feedback optimizer are out of scope. Task-generation research may proceed under a new scope without a fully supported grading baseline; difficulty and separation claims still require adequate behavioral evidence.

Grader expansion is paused. Do not resume old grading queues or execute the prepared G2-B scope. Its execution arrangement is cancelled, not a failed or completed grading run. The G2 runner blocks execution; no bypass is provided. Preserve existing scopes and results. Any future external experiment requires a new explicit input/model/environment/budget-bound scope. Macro results and known limitations belong in the overview.

The coverage/method split is offline-tested only. Labels and valid citations do not prove professional verification. Prioritize reusable generation methods, stage-visible requirements, conditional credit and credible record causality. Separate development from frozen validation, retain every failed position, and report production cost and intervention alongside task quality. Directions and previous batches do not authorize another external batch.

The current direction is a task-production harness with isolated development solving and reproducible calculation evidence for rubric compilation; see the [research record](docs/research/agent_task_production_harness_20260907.md). The earlier 2026-09-08 scopes ended incomplete and must not be resumed. A new procurement development scope finished the full loop on 2026-09-09 using calculation-evidence version 2, draft consultation, atomic snapshots and batch dispositions; its independent review passed and its blind solve produced a valid delivery. Researcher closeout is uncertain because the compiler promoted an affordability calculation seen in design/trial evidence into full-credit rubric language without an unambiguous candidate obligation; the 199 workbook formulas also lacked cached values, so an error-cell scan was not recalculation evidence. Fix obligation provenance, error location, CLI input and evidence metrics offline before the authorized four-position frozen validation. Development feedback must not create candidate obligations or be confused with blind final review; producer intent is not candidate-visible evidence.

## Architecture Rules

- Public Work Seed and Rules describe occupational triggers and methods, not organization-specific facts.
- Professional Skills are source-grounded factory-side knowledge packages, loaded on demand; reuse generic file-tool skills. Motif is an analysis label, not a task template.
- World-First creates business materials before Task Mining. The miner does not read the hidden ledger, difficulty identity or expected answer.
- Historical Scenario Bibles remain frozen; do not build Bible V2 or restore mechanical file/record quotas.
- Keep candidate files, teacher supervision and run evidence separate. Facts rather than answer labels must reveal conflicts.
- Rubric V2 derives requirements from candidate-visible obligations. A decision may have multiple independently observable items. Equivalent forms cannot cancel explicit requirements.
- Code checks identity, safe paths, source linkage, file openability, references, isolation and score consistency. Agents handle professional semantics; avoid new business ontologies or generic validation frameworks.
- GDPval is eval_calibration_only. Its tasks, files, rubrics, Gold and model answers must never enter generation/training inputs. Held-out cases cannot guide prompt tuning.

## Repository and Documentation

- Implementation: src/task_generator/; stage runners: Test/.
- Architecture and operations: docs/architecture/ and docs/operations/.
- Source-backed research notes: docs/research/; proposals do not authorize implementation or model calls.
- Historical material: docs/archive/; generated evidence and logs: ignored artifacts/.
- Historical Registry: SkillRegistry/ (read-only for R10).
- Professional Skills: .agents/skills/r10/; catalog: data/r10/professional_skills/catalog.json.
- Do not add implementation, experiments or generated outputs at repository root.
- Test/v2_outputs/ is no-touch unless explicitly reopened.
- Keep active docs concise and role-specific. Link to code/artifacts rather than duplicating schemas or execution logs. Mark unimplemented proposals explicitly; preserve history instead of creating duplicate snapshots.

## Safety and Execution

- Use apply_patch for manual edits. Preserve unrelated dirty changes; never reset them.
- Never print, commit or package .env, deepseek-key.txt, API keys, tokens or authentication content.
- Provider responses, task packages and execution logs remain ignored artifacts.
- External execution needs an input/model/environment-bound scope and receipt within the user's current authorization; old receipts do not authorize new calls.
- Preserve first failures and immutable inputs. Do not silently rerun started/terminal sessions or redraw low scores and unwanted conclusions.
- Derive submission instructions, expected paths, staging and grading from one DeliverableContract.
- Do not grade invalid deliveries. Keep structural validity, professional judgment, delivery success and model behavior separate.
- Before costly execution perform applicable readiness, fingerprint and environment checks; do not repeat expensive probes when verified environment evidence has not changed.
- Code changes require targeted/full regression and secret/diff checks. Documentation-only changes require link, state and scope checks; do not claim new code tests were run.
- No automatic expansion, deployment, training, public release, registry mutation or default-model change. LLM proxies remain provisional, not expert evidence.
- The 2026-09-07 checkpoint request explicitly authorizes one local commit of reviewed existing implementation, tests and updated documentation after regression and secret/scope checks. It does not authorize a push, new harness implementation or external experiments; prior scope-specific no-commit statements remain historical.
