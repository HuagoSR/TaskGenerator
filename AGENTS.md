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
6. `docs/architecture/pipeline_reconstruction_problem_statement.md` — evidence-backed reconstruction problem definition.
7. `docs/architecture/pipeline_reconstruction_optimization_plan.md` — active R0–R7 workstream plan, gates, metrics, and promotion boundary.
8. `docs/operations/pipeline_reconstruction_runbook.md` — governed execution order for authorization, provider generation, evaluation, server reproduction, and rollback.

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
- D. Server reproduction — complete; its accepted release was `milestone-d-094c6cb`, while the current production release is recorded below.
- E. Warehouse-inventory vertical slice — complete; offline, public-source DeepSeek, contamination, and server evidence passed.
- F. Training-data readiness — `pipeline_reconstruction_active`. F4.3 real rw-task execution produced actual deliverables for only 15/32 solver combinations and exposed both output-contract failure and score saturation. Follow the active reconstruction plan: output contract first, then upstream LLM task design, independent behavioral validation, Validity/Utility separation, and a matched route comparison. Do not start RL or default-chain promotion.

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

Pipeline B is Skill-to-Task. The legacy route assembles task subgraphs into blueprints, reference files, GoldenRun, TrainingAnnotation, rubric, packages, and rw-task exports. Reconstruction may give an LLM proposal-level authority over the whole task design before materialization, while deterministic code retains truth, provenance, candidate/teacher isolation, deliverable paths, packaging and promotion authority.

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
- Compile prompt submission instructions, templates, expected deliverables, rw-task paths and grader staging from one authoritative deliverable contract.
- Keep Validity and Utility as separate evidence axes; `candidate_ready` is not behaviorally validated or training-ready.
- LLM output may propose task design, but it must not become authoritative truth, registry mutation, deliverable path or promotion state.
- Keep source provenance and candidate-visible evidence explicit.
- Prefer report-first diagnostics before canonical mutation.
- Keep promotion and rollback reviewable.
- Prefer small bounded experiments over broad uncontrolled model or domain sweeps.
- Do not add new root-level modules.
- Use `apply_patch` for hand edits and preserve unrelated worktree changes.
- Update active docs when an expected path, interface, or operational boundary changes.

## 10. Next Workstream Boundary

Milestones C, D, and E are complete. Milestone F produced 60/60 candidate-ready tasks, followed by the governed 30-task evaluation, 8-task diagnosis, F2/F3/F3.1 semantic experiments, F4 whole-task repair, F4.2 fresh source-to-task validation, and F4.3 real execution. F4.3 showed that internal semantic validity and export compatibility did not guarantee exact submission, while the tasks that did execute were highly score-saturated.

The active boundary is `docs/architecture/pipeline_reconstruction_optimization_plan.md`:

1. R0 is complete and R1 container core is implemented: Slots 2/5/8 are frozen regressions and the opt-in blocking `DeliverableContract` is live. The current local suite and fixed Linux/amd64 parity both pass 283 tests; network is disabled, the root is read-only, credentials are absent, and cleanup passed. The V31 route manifest retains its frozen provider-era code fingerprint; behavioral authorization separately binds each executable source fingerprint and parity report SHA. This is contract parity, not real solver validation.
2. R2 offline core and R2.1 schema-interface hardening are implemented. Provider calls request `v3.task_design_semantic_proposal.1`; every relation now requires non-empty `from_join_field` and `to_join_field` at provider-schema level. Deterministic normalization may add only execution syntax and zero authority while preserving hashes for all provider-owned semantics, with zero fact additions/removals and productive-complexity preservation required; it never invents join keys. Strict V2 input remains compatible. Tracked malformed cases include a missing relation join contract. A single repair is legal for either `proposal_blocked` with a persisted strict proposal or `semantic_proposal_blocked` with a parseable persisted semantic draft, sanitized normalization findings, canonical IDs and the exact initial prompt. Broad schema/provider/materialization failures remain non-retryable. V16 and v25 provide bounded real feedback-conditioned repair observations; the semantic-draft path is offline-only pending fresh provider verification. `claude-sonnet-4-6` remains hard-blocked.
3. R3 structural materialization was reopened by the v15/v16 content audit: all 58 audited candidate XLSX files used the same five-column placeholder schema, and v16 LLM-led modeled a candidate-authored synthesis as reference input. The local V2 replacement is now implemented: provider proposals must use `v3.task_design_proposal.2`; each candidate-visible node carries a typed `EvidenceArtifactSpec`, governed scenario records, fact-origin mode and relation join/comparison contract. V2 materialization writes semantic fields, readable widths, wrapped long text, adaptive row heights and a styled Provenance sheet, recomputes relation anchors from actual files and blocks the generic schema. Node-level `source_ref_ids` must now be projected exactly into each artifact's `methodological_source_ref_ids`; omission or addition is proposal-blocking and repair-eligible. The content-leak detector distinguishes an explicit governed prior draft from a candidate-authored final output and no longer treats negated phrases such as `not candidate-authored` as positive evidence. Content-role/header comparison conservatively canonicalizes observed regular and irregular plural forms and uses the provider-owned typed `record_type` as role-side semantics; it deliberately excludes field display names so the gate cannot pass tautologically, while role-unrelated negative controls remain blocking. V1 remains readable historical evidence only. V2 output sizing sets a blocking 16,000-token provider completion floor while retaining the 2 USD per-attempt and 32 USD campaign ceilings.
4. R4 offline/container core is implemented: solver tool preflight, behavioral failure taxonomy, exact-delivery inspection and grader eligibility are enforced locally and reproduced in the fixed container suite. Authorized V3 request `15dc3224...4141` ran only the public fixture: weak/medium/strong used 8/7/8 calls, zero retries, 73,054 provider tokens and about 0.85862 USD frozen-schedule contract cost. Audited results are fail/pass/fail: weak wrote 15/16-byte plain text under `.xlsx` names; strong hit the eight-call ceiling without delivery. The wrapper now applies exact-path and openability checks before success. The evidence auditor recomputes budget, outcome, stdout/stderr and output-tree hashes plus status identity: V3 integrity passes, while V2 is downgraded because V3 overwrote its shared budget and stdout paths. Future budgets are request-SHA partitioned and process logs follow the execution output root. Contract cost is not provider billing telemetry. Real Slots 2/5/8, blind packages and all business solver/grader execution remain separately authorization-gated.
5. R5 offline core is implemented: `ValidityVector`, `UtilityProfile`, skill ablation, accidental-difficulty findings, a frozen seven-dimensional rubric, weak/medium/strong solver-panel validation, repeated-grader stability analysis and professional-review evidence ceilings exist. Formal evidence now fails closed unless each embedded solver preflight matches its persisted report, package fingerprints still match, the actual blind candidate input and solver output trees match their fingerprints, grader output files match their declared SHA256, and professional-review support files exist. No real panel, repeated grader or independent expert observations exist yet, so exports are still draft and not training-ready.
6. R6 historical provider evidence through v22 is frozen. R2.1/R3.1 and the sequential-slice governance fix pass local and fixed-container evidence under fingerprint `e6b25300...efd`. The authorized v23 policy-application exact pair used only `gpt-5.6-sol`: both skill-guided and LLM-led passed semantic normalization, validation and materialization on attempt 1. Total usage was 25,721 tokens, 281.86 provider seconds and 4/8 USD reserved. Both normalization reports prove zero fact additions/removals, equal provider-semantic hashes, preserved productive complexity and program-stamped zero authority. The routes produced 11/5 workbooks and 17/10 anchors; all 16 candidate/export pairs are byte-identical. Artifact-tool rendered and visually checked 54 sheets across the matched three routes with zero failures or formula errors and no machine-facing values in provider Evidence sheets. Partial screening remains `awaiting_provider_completion`; this is one-brief interface evidence, not cross-brief stability, behavioral validation, route superiority or training readiness. Claude, solver, grader, review and mutation remain unused.
7. The authorized v24 cross-check pair used only `gpt-5.6-sol` and made two first attempts, with 28,192 total tokens, 294.265 provider seconds and 4/8 USD reserved. LLM-led passed and materialized; skill-guided passed proposal validation but was blocked by the content gate. Artifact-tool audited all 30 workbooks and 60 Evidence/Provenance sheets with zero render or formula failures and byte-identical candidate/export copies. The skill block was a false positive on an explicitly governed prior draft, while its 12 Provenance sheets exposed empty artifact-level source projection. Both defects are fixed offline. A deterministic `replay_persisted_proposal` path regenerates validation/authority evidence with `allow_external_provider=false`; it produced a 1/1 portable repair-readiness bundle from the preserved v24 proposal. Its historical parity snapshot was 243/243 under `103b59ad...01fb`; item 1 owns the current parity state.
8. The authorized v25 cross-check pair used only `gpt-5.6-sol`: skill-guided passed and materialized on attempt 1; LLM-led preserved a first `proposal_blocked` observation for one unused frozen source, then passed a feedback-conditioned repair and materialized. The slice made 3 calls, used 52,513 tokens and 446.531 provider seconds, and reserved 6/8 USD. Both final proposals have exact node/artifact provenance projection; their 12/7 workbooks, 21/14 anchors, content gates and visual gates pass. Artifact-tool imported 31 workbooks across the matched three routes, rendered and visually checked 62 Evidence/Provenance sheets, found zero render/formula failures, zero machine tokens in Evidence and zero blank provenance rows; all 31 candidate/export copies are byte-identical.
9. The authorized v25 fan-in pair also used only `gpt-5.6-sol`; both routes passed and materialized on attempt 1 with no repair. The two calls used 23,926 tokens and 253.187 provider seconds and reserved 4/8 USD. Skill-guided produced 8 workbooks/12 anchors and LLM-led 5 workbooks/8 anchors; both preserve equal provider-semantic hashes, zero fact additions/removals, exact source projection, productive complexity and program-stamped zero authority. Artifact-tool imported 21 matched-route workbooks, rendered and visually checked 42 Evidence/Provenance sheets, found zero failures, formula errors, Evidence machine tokens or blank provenance; all 21 candidate/export copies are byte-identical. V25 cumulative screening is still `awaiting_provider_completion`: 4/8 provider assignments materialized, 5 calls, one feedback-conditioned retry, zero unconditioned retries, 76,439 tokens, 699.718 seconds and 10 USD reserved. This is two-brief provider conformance, not behavioral validity, route superiority or training readiness.
10. The authorized v25 policy-application exact request used only `gpt-5.6-sol`. Both proposals passed semantic schema, lossless normalization, validation and authority gates on attempt 1. LLM-led materialized; skill-guided was frozen as `hybrid_materialization_blocked` because the content gate compared plural role tokens (`thresholds/metrics`) with singular headers literally. Two calls used 24,303 tokens and 255.220 provider seconds and reserved 4/8 USD; no second call was legal or made. Artifact-tool imported 26 matched-route workbooks, rendered and visually checked 52 sheets, found zero failures, formula errors, Evidence machine tokens or blank provenance; all 26 candidate/export copies are byte-identical. The validator now applies conservative plural canonicalization; a zero-provider-call replay passes all 11 skill-guided content checks, with unrelated-role negative control retained. The original block remains frozen evidence.
11. V25 is frozen after the validator code change: screening remains `awaiting_provider_completion` with 5/8 provider assignments materialized, 1 blocked, 2 unrun experimental assignments, 7 calls, one feedback-conditioned retry, zero unconditioned retries, 100,742 tokens, 954.938 provider seconds and 14 USD reserved. Do not execute its remaining `evidence_to_deliverable` assignments or reuse its receipts. Any next external provider or behavioral slice requires a newly synchronized fingerprint and immutable exact request/receipt. Solver, grader, professional review and all mutation authority remain unused.
12. V26 is frozen after two authorized slices. Policy exact request `7457b1f7...57dc` produced 2/2 first-call materializations, 27,194 tokens, 303.000 seconds and 4/8 USD. Fan-in exact request `79559adc...60da` made three `gpt-5.6-sol` calls: skill-guided passed proposal validation but was frozen by a deterministic `criteria/Criterion` content-gate false positive; LLM-led preserved one unused-source proposal block, then passed a feedback-conditioned repair and materialized. Fan-in used 38,247 tokens, 310.297 seconds and 6/8 USD. Its 12 workbooks/24 Evidence-Provenance sheets all passed import, visual, formula, readable-label, provenance and 12/12 candidate/export identity audit. The validator now has a conservative irregular-plural mapping; targeted tests are 13/13, zero-provider replay passes 8/8, and full local/container suites pass 247/247 under `f5561a97...20c5`. V26 screening is frozen at 3/8 materialized, 1 blocked, 4 pending, 5 calls, 1 feedback retry, 65,441 tokens, 613.297 seconds and 10 USD reserved. Claude, solver, grader, review and mutation remain unused.
13. V27 fan-in exact request `f187ccd...45fc` was authorized and consumed with only `gpt-5.6-sol`. LLM-led passed and materialized on attempt 1; skill-guided passed proposal validation but was frozen by a deterministic content-gate false positive because the gate ignored typed `record_type=evidence_assessment_criterion`. Two calls used 23,976 tokens, 284.375 seconds and 4/8 USD; no retry was legal or made. Artifact-tool imported 13 workbooks and visually checked 26 Evidence/Provenance sheets with zero failures, formula errors or Evidence machine tokens; all 13 provenance sheets were populated and all candidate/export copies were byte-identical. The validator now includes typed record semantics but not field labels; targeted tests pass 15/15, zero-provider replay passes 8/8, and full local/container suites pass 249/249 under `0c1b3705...858a`. V27 is frozen; a formal screening write correctly fails closed on fingerprint mismatch.
14. V28–V30 remain frozen; never overwrite them. Preflight requires an exact match between receipt `authorization_request_sha256` and the active request SHA; mismatch fails closed without state mutation. Full local/fixed-container parity passes 254 tests; container fingerprint `b31a79b3...505d`, campaign code fingerprint `b28556f0...b392`. V31 has now completed all four matched briefs with only `gpt-5.6-sol`: 8/8 provider assignments materialized, 10 calls, two feedback-conditioned retries, zero unconditioned retries, 148,709 tokens, 1410.874 provider seconds and 20 USD reserved. The final experimental `evidence_to_deliverable` pair consumed exact request `588d7708...0af3f`: skill-guided passed on attempt 1; LLM-led preserved an unused-source `proposal_blocked` first failure, then passed the single feedback repair and materialized. Its 12 workbooks/24 sheets passed artifact-tool formula, display and provenance review, with 12/12 candidate/export identity. Formal provider screening is `proceed_to_behavioral_evaluation`; route-blind staging passed for all 12 assignments and the campaign is `evaluation_ready`. This is not behavioral validation or permission to run solver/grader: solver, grader, professional review and all mutation authority remain unused and separately authorization-gated.
15. R7 report-only promotion core is implemented with artifact-bound confirmation. Screening must recompute exactly from the frozen comparison manifest and all 12 compiled evidence records. Confirmation is compiled from five independently hashed gate reports: absolute gates, matched environment, server reproduction, rollback and major-validity closure. Missing, mutated or self-inconsistent evidence yields `hold` or `redesign_again`. A `promote` record remains opt-in-only and has no default-chain, release, registry or training authority.

16. V31 behavioral V1–V3 requests were consumed only for the same public XLSX fixture. V3 integrity passes, but the behavioral interpretation is now fail/pass/indeterminate: `gpt-4o-mini` made tool calls and produced invalid pseudo-XLSX, Gemini passed, while `gpt-5.6-sol` had successful provider transport/token usage but seven empty assistant turns, zero tool calls and no sandbox entry. The capped offline fix is implemented: sanitized response-shape observations, a two-empty-response fail-fast rule, and separate context/completion semantics are live. Request `993d31a4...f37a4` failed locally before provider entry on a timeout-field mapping bug and is frozen with zero calls. After the fix passed local/container 293/293, authorized request `ea3afe62...aae45` made exactly two `gpt-5.6-sol` public-fixture calls: both had provider token usage but mapped to empty content/tool/reasoning, with zero sandbox entry and delivery; fail-fast stopped the run. Evidence integrity passes. Track A is closed as current Tuzi Chat Completions → Stirrup incompatibility, not model capability failure, and no third adapter probe is allowed. This does not invalidate the separate task-design provider path. The active path is now the six-case independent reality cohort, excluding experimental `evidence_to_deliverable`; external solver/review/grader scopes remain separately authorization-gated.
17. The replacement-slice implementation parity snapshot passed local and fixed Linux/amd64 287/287 at source fingerprint `e4c208f5c377bf8d3f9dc7941f4593036b9d9cbb11a7d586490e4418511cb865`; report SHA is `ec159667a91648d56e033f4e3a9842e2a11cad6ef9057e08d3a0578166a64aa5`, with network disabled, read-only root, no provider credentials and cleanup success. Because governed documentation participates in the source fingerprint, candidate binding and any exact request require a post-document-sync parity report rather than reusing this implementation snapshot. Neither snapshot authorizes replacement models.
18. The six-case reality cohort is fixed to three non-experimental motifs and two reconstructed routes, with `evidence_to_deliverable` excluded. The active LLM proxy is official `deepseek-v4-pro` and must start a homogeneous 12-stage cohort: all candidate-visible reviews first, then rubric-focus reviews. Each stage has one normal attempt; only timeout/408/429/5xx, empty content, truncation, invalid JSON or schema failure may receive one governed formatting retry on the same frozen input. SDK retries are zero; ceilings are 24 provider calls, 12k input/4k completion per call and 0.25 USD total. LLM-only pass may authorize bounded screening but remains provisional and cannot claim expert review, training readiness, promotion, registry or release authority.
19. Reality review request `1dfe222e...32916` was authorized but failed before provider-client entry because extracted XLSX datetime values were not JSON serializable. Its manifest is frozen `incomplete` with zero completed calls; the receipt must not be reused. Payload serialization now converts datetime values safely, and execution-time validation recomputes candidate trees, package fingerprints and rubric hashes. A fresh full suite, parity and exact request are mandatory before any Gemini upload/call.
20. Reality request `2cff1fa3...ceae9` made three Gemini calls: the first two candidate-blind reviews parsed and passed all five dimensions; the third response violated the JSON contract. The campaign is frozen `incomplete` with two completed reviews and no rubric calls. These observations remain historical provider diagnostics only and cannot be merged into the new DeepSeek cohort. Gemini continuation request `76c34304...d554` is `superseded_model_change`; receipt compilation and execution must reject it.
21. Project-level external model policy blocks every Tuzi `claude-*` model and `gpt-5.4-pro`. Active provider builders, execution entrypoints and authorization compilers fail closed. The block may be removed only after the user explicitly reverses it; historical evidence remains readable and is not rewritten.
22. Official DeepSeek V4 Pro Reality request `8d04b2c0...acee0` completed all 12 stages on first attempts: 12 provider calls, zero controlled retries, 73,776 prompt tokens, 26,943 completion tokens and 420.531 provider seconds. All six candidate-blind five-dimension reviews passed. Five rubric reviews passed; fan-in case `cmp_34da237cf93dcc20` was `revise` because multiple criteria share skill/evidence bindings and may duplicate scoring. Cohort decision is `revise_before_screening`, so screening is not authorized. Any repair must be rubric-scoped, update its hash, preserve the original evidence and obtain a new exact request for the changed rubric-focus stage.
23. Report-first cross-case audit found the six rubrics scoring-semantically identical: seven final weighted criteria, 21 unordered pairs, unique observable behaviors and unique independent failure signals. All six strengthened `RubricScoringAuthorityAudit` records pass with common structure signature `0e4bbcae...43ca9` and scoring-semantic signature `1c4ffda4...b9525ec`; binding entries are trace-only because final weights are false and scoring authority is not-final-weight. Rubric Focus V3, full-message token preflight, V2 compatibility and governed retry/cost evidence pass the complete local 313-test suite. Any executable recalibration request must bind a fixed Linux/amd64 parity report generated after the final documentation sync, then pause for exact SHA authorization. The scope may reuse six candidate-pass trees and call only six rubric stages, with at most 12 DeepSeek calls/0.13 USD and no screening execution authority.
24. Authorized recalibration request `63a9b799...e0897` is consumed and frozen `incomplete`: `cmp_000f7ca3889507c9` passed on its first call, while both the normal and only controlled retry for `cmp_3146d2f399790f96` reached exactly 4,000 completion tokens with `finish_reason=length`. The run stopped after 3 calls, 1 retry and 0.03 USD reserved ceiling; four cases were not called. Manifest SHA is `656c1d50...ead31`. This is a Rubric Focus V3 output-contract ceiling failure, not substantive revise/blocked evidence. Never reuse the receipt or add a third attempt; any continuation requires an offline contract/budget change, fresh parity and a new exact authorization.
25. Compact Rubric Focus V4 is implemented without increasing ceilings. It preserves all seven criteria and 21 pair classifications, removes repeated rationale/locators from non-risk pairs, and requires bounded `risk_findings` exactly for potential/actual duplicate pairs. Across the six frozen payloads, complete input estimates are 8,131–10,114 tokens and the standard pass JSON is about 977 estimated tokens. Related offline/documentation tests pass 39/39. V1/V3 evidence remains readable. Any next external scope must use six `rubric_focus_v4_compact` stages, retain 12k input/4k completion/12 calls/0.13 USD, complete final local and post-document parity, and obtain a new exact SHA authorization.
26. Authorized Compact V4 request `f96a2ab6...af1b1` completed all six rubric stages on first calls: 6 calls, zero retries, 42,476 prompt tokens, 16,285 completion tokens and 0.06 USD reserved ceiling. All six reviews pass with one identical pair pattern: 17 `distinct`, 4 `shared_evidence_distinct_behavior`, zero risk findings and no reviewer inconsistency. Result SHA is `d2a9dee6...0f840`; manifest SHA is `bb66391e...b2202`. Combined with the retained six candidate passes, the reality cohort is `screening_ready`, while professional validity remains provisional. No screening, solver, grader, training, release or promotion authority was used; the consumed receipt cannot authorize the next phase.

Keep `evidence_to_deliverable` experimental. V16 is frozen as placeholder-content diagnostic evidence; v17 is frozen because its 6,000-token provider budget is below the V2 semantic floor, and v19 is frozen because the strict baseline subsequently became motif-aware. V21's authorized policy-application V2 pair completed with 2/2 first-call materialization, 26,806 tokens and no Claude/solver/grader/mutation; its render audit drove wrapping and readable-label changes. V22 verified readable labels on a fresh skill-guided package, while LLM-led failed V2 schema parsing before a proposal could be persisted. Broad provider/schema failures cannot be retried; only a persisted strict blocked proposal or parseable semantic blocked draft with exact failure evidence may enter the single repair. Do not expand or rewrite old campaigns. Any further external call must use a final synchronized fingerprint and immutable exact request/receipt; conversation-level consent does not override model, cost, retry, evidence or mutation gates. Do not start RL/SFT, mutate the canonical registry, switch the production release, or promote a default chain without the explicit gates required by the active plan.

For any case with `design_frontend_status`, production readiness requires both `proposal_validation_decision=pass` and `hybrid_materialization_decision=pass`; legacy package readiness must not bypass this gate.

27. The next execution slice uses `v3.matched_screening_campaign.1`, not the old three-route V31 manifest: two reconstructed routes, three non-experimental motifs, two replicates and twelve blind packages. Existing six packages are immutable replicate A; six fresh replicate-B packages must pass generation, materialization, blind staging and a new DeepSeek Reality cohort. Strict-template and evidence-to-deliverable are excluded.
28. Solver priority is official `deepseek-v4-pro`, then the retained hash-complete Gemini pass; the Tuzi GPT-5.6 Stirrup path stays closed. DeepSeek must first pass one public XLSX tool preflight. Business execution and one-pass DeepSeek grading require a later exact request binding all twelve package/candidate/Reality hashes. Screening never authorizes expert claims, training, registry, release or promotion.
