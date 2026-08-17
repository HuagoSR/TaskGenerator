# Production MVP Definition

## Status

Document lifecycle: `active / reference`.

This document defines the implemented legacy production contract that began in Phase 13 and was later used by the Milestone F finance/audit production campaign.

It remains the current production-state reference, but project status and next-stage priorities are maintained only in the root `项目概要.md`.

The active server release is `milestone-f-data-production-6304e84`. F4.2/F4.3 candidate releases are not active. F4.3 proved that legacy `candidate_ready`, semantic validity and export compatibility do not by themselves guarantee exact deliverable submission or training usefulness, so new-route promotion is frozen during pipeline reconstruction. The reconstruction plan is [`pipeline_reconstruction_optimization_plan.md`](pipeline_reconstruction_optimization_plan.md).

It does not replace the existing Pipeline B quality gate, verifier, or global validity diagnostics.
Instead, it adds a production-facing state machine and batch-manifest contract on top of the current candidate-ready path.

Current implementation scope in this repo:

- `candidate_ready` remains the highest automatically assigned legacy structural/export state
- `production_candidate` is assigned only through the explicit QA/reviewer promotion path and must never be inferred from `candidate_ready`
- `diagnostic_eval_sampled`, `released`, and `deprecated` remain downstream lifecycle states
- the first production runner is manifest-first and report-first
- production manifests now retain per-case production-facing metadata such as blueprint, subgraph, template-family, deliverable, and selected-skill signatures
- the first production diversity report now exists as a report-only dedup / concentration layer
- the first production QA gate now exists as a report-first governed review layer and can explicitly keep a case at `review_required`
- the first release-packaging layer now exists and can produce either:
  - a strict `production_ready_only` release bundle
  - or an explicit `internal_review_release` bundle for review-required cases during Phase 13
- the first production dashboard layer now exists and can distinguish:
  - strong `candidate_ready` closure
  - missing governed `production_ready` promotion
  - release readiness that is still blocked by governance rather than structure
- the first explicit production-promotion layer now exists and lets reviewer-authored policy approve bounded `review_required` cases into governed `production_candidate` state without changing the base QA gate thresholds
- the first within-batch diversification hardening now exists:
  - repeated motif slots can carry a deterministic occurrence index into the sampler
  - repeated motif occurrences now rotate across near-top eligible candidates instead of reusing the exact same subgraph by default
  - the `phase13_pilot8_diversified_smoke` result preserves `8 / 8 candidate_ready` while dropping `duplicate_subgraph_count` from `4` to `0` and `duplicate_skill_signature_count` to `0`
  - after that fix, the remaining concentration is mainly duplicate deliverable signatures at the motif-template layer rather than exact subgraph reuse
  - the same diversified 8-case batch now also proves the governed review path still scales: the existing reviewer policy promotes `3 / 8` cases to `approved_production_candidate`, and a strict reviewed release now packages those `3` cases without including the remaining `5 review_required` cases
- the current closure pass now strengthens the same path further:
  - full grammar coverage now exists for all four active production motifs
  - repeated motif occurrences now widen the deterministic diversification window enough to swap in bounded second-tier alternatives instead of only permuting the same top skill clique
  - the resulting `phase13_pilot8_diversity_final_smoke` preserves `8 / 8 candidate_ready` and `8 / 8 verifier pass` while keeping `duplicate_subgraph_count = 0` and lifting `unique_skill_signature_count` to `8`
  - the reviewed production promotion path on that final batch now yields `8 / 8 approved_production_candidate`
  - the strict reviewed release bundle `artifacts/releases/finance_audit_mvp_v0_1_pilot8_diversity_final_reviewed_strict/` now packages all `8` tasks
  - the reviewed production dashboard now reports `release_readiness_status = release_ready`
  - at the current governed finance/audit scope, this document should therefore be read as an implemented MVP contract rather than only a forward-looking shell

## Scope

Phase 13 productionization is limited to:

- finance / audit / compliance-style tasks
- existing file ecosystems such as `.xlsx`, `.docx`, `.md`, and `.txt`
- deterministic Pipeline B generation plus explicit reports

It does not yet include:

- broad domain expansion
- complex PDF / OCR / scanned evidence ecosystems
- automatic registry mutation
- formal benchmark-grade model-separation claims
- LLM teacher production mode

## State Machine

The legacy production lifecycle is defined as:

```text
generated
-> structurally_valid
-> verifier_passed
-> candidate_ready
-> production_candidate
-> training_pool_candidate
-> diagnostic_eval_sampled
-> released
-> deprecated
```

Pipeline reconstruction keeps this lifecycle for compatibility and adds separate factual, semantic, contract, behavioral, professional and utility axes. Until those contracts are implemented and promoted, the lifecycle name alone must not be used to claim actual delivery, model separation or training readiness.

### `generated`

Meaning:
The case has been planned or emitted by the production runner, but no structural conclusion should be inferred yet.

### `structurally_valid`

Entry conditions:

- the case completed deterministic generation
- task artifacts were written successfully
- package assembly and export-facing artifacts exist

### `verifier_passed`

Entry conditions:

- `structurally_valid`
- `task_verifier_report.json` reports `verification_status = pass`

### `candidate_ready`

Entry conditions:

- `quality_gate = candidate_ready`
- `verifier_status = pass`
- `validation_status = candidate_ready_compatible`
- `global_validity_status` is `diagnostic_only`, `pass`, or omitted

This is the highest state the current deterministic production runner may assign automatically.

`candidate_ready` means the package passed its legacy structural, verifier and export-compatibility contract. It does not mean:

- prompt/template/deliverable-path consistency has been behaviorally proven;
- a solver generated the exact expected file;
- the task is professionally realistic or sufficiently difficult;
- the rubric has useful model-separation resolution;
- the task is approved for a training pool.

For an opt-in `finance_semantic_contract_v2` run, `candidate_ready` additionally requires:

- `contract_origin = generator_owned_v2`;
- lifecycle reaches `verified` after candidate-visible deterministic recomputation;
- every deterministic claim has a fact-rubric binding;
- semantic-contract consistency decision is `pass`.

Legacy inferred contracts remain diagnostic and cannot satisfy this additional production contract.

F3.1 进一步要求外部 secondary review 使用显式 key slot 和原子成本账本，并在输入投影超限、累计费用超过 campaign 上限或 provider 合同连续失败时停止。该机制当前仍为 opt-in diagnostic；`f3_1_semantic_gate_hold` 不改变既有 production profile 的默认门禁。

F4 新增的 whole-task editorial workflow 仅用于固定8题版本化修订和汇报收口。它允许编辑模型提出完整任务修订，但任何数值 truth 必须由candidate-visible文件独立重算，独立复核模型不得读取teacher artifacts。`holistic_editorial_review_completed` 不自动升级历史60题或默认production profile。

从零 F4 validation 进一步证明：`WholeTaskRevisionBundle` 目前只是 proposal contract，不是已物化任务。只要候选文件修改尚未由受治理的 materializer 写入新版本并重新通过 truth、rubric、verifier、export 和人工式放行，任务就必须保持 `revise_system/blocked`。

### `production_candidate`

Entry conditions:

- `candidate_ready`
- production batch manifest is complete
- provenance is complete enough for replay
- no unresolved critical production QA finding
- no hidden-artifact exposure
- no negative-control regression failure

Current implementation note:
The production QA gate and reviewer-authored promotion manager exist. This state is intentionally not auto-assigned: it requires an explicit reviewed promotion record, and reconstruction candidates remain ineligible until the active workstream reaches a promotion decision.

### `training_pool_candidate`

Entry conditions:

- `production_candidate`
- candidate-facing rubric hygiene passes
- evidence closure passes
- no manual blocker remains

Reconstruction freeze:

- no new task may be interpreted as `training_pool_candidate` solely from these legacy conditions;
- future admission additionally requires all frozen Validity axes, governed behavioral evidence and the Utility threshold defined before route comparison;
- historical tasks without those reports remain `not_evaluated`, not implicitly passed.

### `diagnostic_eval_sampled`

Entry conditions:

- `production_candidate`
- selected by an explicit eval sampling policy
- executed eval completed or was explicitly skipped with a recorded reason

Executed-eval reports must distinguish process completion from exact valid delivery. A missing, wrongly named, empty or unopenable file is a delivery failure and must not be sent to the business-quality grader.

### `released`

Entry conditions:

- packaged into a release manifest
- included in a release-ready dataset bundle
- not marked `deprecated`

### `deprecated`

Entry conditions:

- explicit review marks the case as no longer suitable for active production use
- deprecation reason is recorded in production artifacts

## Batch Contract

Every production batch should record:

- `production_batch_id`
- `created_at`
- `code_commit`
- `registry_version`
- `workflow_asset_version`
- `motif_grammar_version`
- `sampler_policy_version`
- `selection_policy`
- `domain_scope`
- `file_type_scope`
- `mode`
- `promotion_state`
- output artifact paths

Reconstruction experimental batches additionally record contract versions, `CapabilityBrief`, design-frontend state, optional `TaskDesignProposal`, `DeliverableContract`, Validity/Utility report paths, solver preflight state and actual-delivery metrics. `DeliverableContract` is implemented as an additive opt-in blocking contract and compiles the final submission path for export validation and runner delivery inspection. `CapabilityBrief` is generated before the legacy prototype; a proposal is recorded only when a schema-valid provider or tracked input exists. `awaiting_provider` must not be represented as an LLM-designed task, and a proposal pass alone must never be represented as a materialized package pass. Validity/Utility, solver-preflight and behavioral-report fields are implemented for the experimental route, but remain provisional or `not_evaluated` until independent evidence exists. These fields remain additive until a route is explicitly promoted.

R3–R5 hybrid materialization and offline governance are now implemented as an experimental route. Its rw-task export includes a frozen seven-dimensional rubric, `ValidityVector` and `UtilityProfile`, but must remain `draft_revise_only`, `not_final_training_data=true`, and `rw_task_export_ready=false` while behavioral and independent professional validity are unresolved. For any case with `design_frontend_status`, production candidate readiness additionally requires `proposal_validation_decision=pass` and `hybrid_materialization_decision=pass`; legacy package readiness, verifier pass, rubric compilation, or structural export compatibility cannot bypass these requirements.

For a hybrid behavioral run:

- a `v3.solver_tool_preflight.1` report must pass for the exact solver model;
- process completion, exact delivery, file validity, business validity and professional quality remain separate evidence axes;
- grader execution is permitted only after exact valid delivery;
- `not_evaluated` or LLM-only professional evidence cannot satisfy training admission.

Governed batch proposal ingestion additionally requires:

- `target_difficulty_profile=reconstruction_experimental`;
- a `v3.batch_task_design_proposals.1` manifest that exactly covers the selected deterministic case IDs;
- matching proposal SHA-256 and `brief_id`;
- direct hybrid materialization, without treating a separately generated legacy package as evidence for the same route.

Even after proposal and hybrid materialization pass, production candidate readiness requires R5 offline governance, full `ValidityVector=pass`, `UtilityProfile=pass`, and `RubricPlanV2=pass`. Current offline hybrid exports remain provisional and therefore cannot enter `candidate_ready`.

Formal comparison additionally requires a frozen, distinct weak/medium/strong solver panel whose members have passing tool preflight and persisted preflight reports identical to the embedded panel records, repeated valid-delivery grader observations whose output artifacts match their declared SHA256 and remain within the frozen disagreement/saturation thresholds, frozen package fingerprints, and generator-independent professional evidence with present support files. LLM proxy review may support screening only and cannot supply a final professional pass.

R6 comparison manifests and reports are screening/confirmation governance artifacts only. `advance_two_routes` means “eligible for confirmation,” not production promotion. `redesign_again` is mandatory when all routes miss absolute thresholds.

R6 provider execution must go through `v3.route_comparison_campaign.1`. Direct one-off proposal calls are diagnostic and do not count toward the matched comparison. The campaign must preserve the frozen brief and route identities, use the frozen `gpt-5.6-sol` design policy, reject `claude-sonnet-4-6` even if an authorization receipt lists it, reserve the configured cost ceiling before each request, preserve the first failure, and allow at most one repair. A repair must reference the failed execution report and include its proposal, blocking validation evidence, authority findings and canonical bound-element IDs; repeating the original prompt is not repair evidence. Four strict-template controls may be materialized offline; the eight LLM assignments require explicit campaign authorization.

The first authorized R6 provider slice covered exactly two cross-check assignments. Skill-guided passed on its first proposal; LLM-led was blocked for causal-binding and mutation-authority violations, preserved that first failure, and passed the one permitted retry. Both packages passed deterministic materialization and draft export, but their Validity and Utility remain provisional and `training_admission_eligible=false`. This smoke does not satisfy the twelve-task matched-comparison contract, authorize solver/grader execution, or change any production state.

The completed v7 provider screening supersedes that smoke as the current redesign evidence. Across eight authorized LLM assignments, 13 `gpt-5.6-sol` calls produced four materialized packages and four blocked assignments. Five second calls repeated the original prompt without failure feedback. `v3.provider_screening_outcome.1` therefore records `redesign_again`; v7 is ineligible for blind staging, solver/grader execution or route-superiority claims. The repaired prompt contract requires a new campaign fingerprint and new explicit authorization before external validation.

Formal campaigns created after v7 must freeze a passing portable `v3.task_design_repair_readiness.1` bundle and current-code replay; their fingerprints remain part of the manifest and authorization request. V15, v16, v21 and v22 are immutable diagnostic campaigns. The authorized v23 exact pair covered only one policy-application brief: both `gpt-5.6-sol` routes passed semantic normalization and materialization on attempt 1, with 25,721 tokens and 4/8 USD reserved. Normalization added or removed zero facts and preserved productive complexity; 16 candidate workbooks matched their export copies byte-for-byte, and 54 rendered sheets across the matched three routes passed read-only visual inspection. V23 remains partial provider evidence with provisional Validity/Utility and no behavioral, review or mutation authority.

Package materialization is no longer sufficient for campaign continuation. The v15/v16 content audit found that all 58 candidate workbooks across six route packages used the same generic placeholder schema and node-index-derived values; actual renders also showed clipped headers and IDs. `v3.evidence_content_quality.1` blocks every audited file and additionally detects a candidate-authored synthesis modeled as v16 reference input. Future formal campaigns must include a versioned semantic artifact/scenario-fact contract, pass a blocking content gate and consume actual render evidence before `packages_ready`. Recomputability alone cannot set factual validity to pass, and methodological source provenance must not be presented as the source of invented scenario values. V16 is frozen diagnostic evidence and is ineligible for further provider expansion.

The local V2 core now enforces that boundary through two interfaces. Future provider calls request `v3.task_design_semantic_proposal.1`; deterministic normalization may add only execution versions, primary-key-derived record wrappers, `candidate_visible=true`, `proposal_origin=llm` and an all-false authority boundary. It must prove identical provider-semantic hashes, zero fact additions/removals and productive-complexity preservation before emitting strict `v3.task_design_proposal.2`. Direct strict V2 remains compatible; V1 output is a contract failure. Every semantic relation now requires non-empty endpoint join fields in the provider schema; missing keys, undeclared fields, wrong unions, legacy nested records, candidate-facing boolean or machine enum values, oversized payloads and semantic loss fail closed with value-free findings. Every selected skill must have exactly one binding object. The normalizer never invents a join key or skill binding. A parseable semantic draft blocked during normalization may be preserved as `semantic_proposal_blocked` for the single governed feedback repair, but only with its exact initial prompt and sanitized findings; broad schema/provider/materialization failures remain non-retryable. The V2 materializer writes semantic XLSX content plus a visible provenance boundary and applies the content report as a blocking gate. Deterministic recomputability yields provisional factual validity, never a generator-owned business-grounded pass. The complete local suite and fixed-container parity both pass 254 tests; parity fingerprint is `b31a79b3eea9aeddc6d45c097e717f07f1e589f1f401326d3521d83467b9505d`, and campaign code fingerprint is `b28556f07089c017c2496c4e59b76baf58360b30ec173f69cd1de4f4c3aab392`. Governed provider routes must reserve at least 16,000 completion tokens per attempt; cost authority remains 2 USD per attempt and 32 USD per campaign. Any new provider slice still requires a fresh fingerprint-bound request and explicit authorization.

V27 is frozen provider/materialization diagnostic evidence under the prior validator fingerprint. V28 is now also frozen after all four authorized sequential pairs completed. Its four strict controls pass; seven of eight provider assignments materialized on attempt 1. The only block was skill-guided semantic normalization when a relation omitted its required join contract; no strict proposal existed, so the contract failure was not repair-eligible. The final exact request `3b563b61...c4f3` produced two first-call materializations. Across V28, eight `gpt-5.6-sol` calls used 102,082 tokens and 1,076.593 provider seconds; 47 materialized provider-route workbooks/94 sheets passed content, render, provenance and export-identity audit. Formal provider screening is `redesign_again`: LLM-led is 4/4, skill-guided is 3/4, and package completion is below contract. Incomplete matched packages prohibit solver/grader execution and route-superiority claims. Neither campaign provides behavioral, professional, training-admission or production-promotion authority; any successor requires an offline redesign and a new fingerprint-bound authorization.

The post-V28 redesign cannot retroactively change historical screening. V30's later authorization `74a6e65f...5d47` was not consumed because preflight exposed an active-request binding gap; the current contract rejects such a receipt before state mutation and passes 254 local/container tests. V31 consumed all four exact provider requests, including final experimental request `588d7708...0af3f`. All eight provider assignments materialized across four briefs: ten calls, two feedback-conditioned retries, zero unconditioned retries, 148,709 tokens and 1410.874 seconds. All 58 provider workbooks/116 sheets passed artifact-tool import, render, formula, provenance and export-identity audit. Formal provider screening is `proceed_to_behavioral_evaluation`, and route-blind staging passed for all 12 assignments with teacher artifacts excluded. This is an evaluation-entry decision, not behavioral evidence: solver, grader, professional review, registry, release and promotion remain separately authorization-gated, and completion cannot promote the experimental evidence-to-deliverable motif.

The authorized V31 V2 public tool preflight did not satisfy the behavioral entry gate. Its call/turn controls bounded the three models to 4/6/7 calls and zero retries, but the weak model's files were located under legacy MD5 subdirectories rather than the candidate-visible exact paths, while the medium and strong models were stopped by the conservative request-byte input upper bound. Post-run exact-path audit overrides the weak raw outcome, so the panel remains blocked and no blind package or business task was executed. The governed wrapper now permits only an unambiguous one-to-one legacy-path normalization and compares the full expected/observed file sets before success; any new execution requires a new source fingerprint and exact authorization.

The subsequent authorized V3 public preflight also closed `blocked`. It used 8/7/8 calls with zero retries and produced audited fail/pass/fail results: the weak solver submitted plain-text marker strings under `.xlsx` extensions, the medium solver produced two openable and semantically correct workbooks, and the strong solver reached the call ceiling without delivery. A finish signal, nonempty file and exact relative path are therefore still insufficient. Governed process success now additionally requires the same `DeliverableContract` delivery inspector to open and validate the expected files. V3 did not upload blind packages or authorize business execution, grading, review, release, registry mutation or promotion.

Behavioral authorization is a two-level production boundary. V31's first Level-one execution exposed that an attempt ceiling did not bound Stirrup's internal calls and that max-turn exhaustion could be reported as process success without a deliverable. Level-one V2 therefore freezes one weak, medium and strong model plus per-model call/turn/request-byte/token/completion/contract-cost budgets, disables SDK and runner retries, binds current source/container/campaign evidence, and permits only one exact public XLSX fixture. The executor is single-use, rejects blind-package contamination and source drift, and requires a finish signal, nonempty output and matching outcome identity. Contract cost is schedule-derived authorization evidence, not a provider billing claim. It cannot upload blind task packages or execute business tasks, graders, review or mutation. Only three passing reports may form the panel. Level two remains separately scoped to that panel, all 12 blind fingerprints, execution limits, grader repeats and review scope.

When a level-one panel has hash-complete passing evidence for only some strata, replacement request V3 must retain those members without another provider call and authorize only the failed strata. It must bind the admission and replacement-boundary records, retained panel/report/integrity, exact replacement models and budgets, and a fresh fixed-container fingerprint. The final three-stratum panel is not reconstructed by hand: the merge compiler verifies the replacement request SHA, old and new integrity reports, persisted preflight reports and member identities before emitting a hash-addressed passing panel. Until that merge passes, level two remains unavailable.

The v21 policy-application pair is the first real-provider V2 evidence. Both routes passed on their first `gpt-5.6-sol` attempt and materialized 15 semantic workbooks with 25 deterministic anchors. Render audit showed that content semantics and openability are insufficient display-quality evidence: long text required wrapping and adaptive row heights, while the frozen proposal used machine-facing labels. V21 remains immutable diagnostic evidence and cannot be post-edited into a pass.

V22 verified those display instructions on a fresh skill-guided package: rendered values use readable business labels and `Yes/No`. Its matched LLM-led response failed V2 schema parsing before proposal persistence and is not eligible for feedback-conditioned repair. The historical v22 report predates sanitized schema findings and records only `ValidationError`; it must not be reclassified under the later semantic-draft repair contract. V22 is partial diagnostic evidence and remains ineligible for behavioral staging.

Before an R6 campaign is eligible for authorization, its four briefs must pass `v3.formal_brief_cohort_admission.1` against a frozen `v3.source_provenance_ledger.1`. GDPVal, fixture, synthetic, opaque or unresolved sources are prohibited generation inputs. Every selected skill must resolve to a governed source group, and all selected skills in one brief must belong to exactly one source/workflow group. A tracked-fixture dry-run, structurally valid campaign manifest or cross-workflow skill graph cannot substitute for formal source admission.

The campaign manifest must declare `input_class=formal_public_source` and freeze the passing admission report fingerprint. `input_class=contract_only` is permanently ineligible for provider generation; an authorization receipt cannot override this boundary.

Provider authorization must be assignment-scoped. A receipt must list the exact route-blind assignment IDs, and execution without an explicit CLI subset defaults only to those IDs. It must bind the authorization request and frozen route/source/admission/policy fingerprints. Requests and accepted receipts are preserved in immutable hash-addressed governance directories; the active receipt SHA is checked immediately before execution. Cost is reserved both per authorization ID and against the campaign total. A two-assignment receipt cannot be reused or broadened for another pair. Expired, future-issued, timezone-free, wrong-model, over-budget or hard-blocked-model receipts fail closed.

Formal R6 analysis must consume `v3.route_comparison_evidence_compile.1`, not hand-authored `RouteTaskEvidence`. All twelve tasks, the exact frozen weak/medium/strong panel, valid-delivery-only repeated grader observations and professional-review records must compile together. Missing tasks, substituted package roots, mismatched blind identities, mixed environments, incomplete repeats or grader observations for invalid deliveries block analysis. A successful compile still authorizes only screening analysis, never production promotion.

R7 must compile `v3.reconstruction_promotion_record.1`. Screening cannot directly produce a production candidate. Confirmation, server reproduction, matched environment, rollback verification and closure of major validity findings are mandatory; `decision=promote` remains an opt-in proposal with all mutation and activation flags false until separate review/apply authorization.

The reconstruction snapshot has passed the complete repository test suite in a fixed Linux/amd64 base with networking disabled, a read-only container root and no provider credentials. This is Docker contract parity only: it does not upgrade any task to `behaviorally_validated`, authorize a solver/grader campaign, create a candidate release or change the server `current` link.

The production batch runner should support three modes:

```text
dry_run
candidate_run
production_run
```

Interpretation:

- `dry_run`: plan and write a manifest only
- `candidate_run`: execute the current deterministic Pipeline B batch flow and record candidate-ready outcomes
- `production_run`: execute the same flow while preparing production-facing manifests and eligibility fields, without silently assigning governed states beyond `candidate_ready`

## Current Rules And Reconstruction Freeze

- Keep the current Pipeline B batch runner intact.
- Keep all production metadata additive.
- Do not silently upgrade `candidate_ready` to `production_candidate`.
- Keep eval evidence diagnostic unless a later phase explicitly validates stronger comparison semantics.
- Keep registry and promotion changes explicit and reviewable.
- Compile prompt submission instructions, dataset-row deliverables, expected-deliverables manifests and grader staging from one authoritative contract.
- Do not grade a solver process that did not produce the exact valid deliverable.
- Keep reconstruction under an opt-in versioned profile until matched route comparison and promotion review are complete.
- Do not activate a new release, expand the training pool or begin RL/SFT without separate explicit approval.
