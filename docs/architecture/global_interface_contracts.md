# Global Interface Contracts

## Status

Document lifecycle: `active / reference`.

This document records implementation-facing interface contracts for the current four-layer architecture. It was originally derived from the historical `pipeline_next_stage_global_plan.md`, which is now preserved under `docs/archive/foundations/`; current project status and priorities are maintained only in the root `项目概要.md`.

These contracts are intentionally schema-first and report-first. The original V1 contracts below are now largely implemented as diagnostic or experimental objects; they remain the compatibility reference for existing Pipeline A/B behavior. The active reconstruction adds new versioned contracts without silently changing registry state, sampler behavior, legacy package readiness, rw-task export semantics, or sampler weights. Planned extensions and migration order are owned by [`pipeline_reconstruction_optimization_plan.md`](pipeline_reconstruction_optimization_plan.md).

## Domain Profile And GDPVal Isolation

The unified pipeline freezes `domain_profile` and `domain_profile_path` in each request. A profile owns domain tags, allowed motifs, actor role, typed-resource aliases, reference schema, deliverable contract, and forbidden vocabulary. `finance_audit` is the compatibility default; a new profile must preserve the established public-smoke fingerprint before it can be used as evidence.

GDPVal remains `eval_calibration_only`. Domain selection may inspect aggregate sector, occupation, and file-extension metadata, but generation and external providers must not receive GDPVal prompts, rubrics, attachments, task IDs, or URIs. The post-generation contamination ledger is an isolated release gate: it records hashes, hit counts, and artifact paths without storing protected GDPVal text, and its output must not be used to tune or rewrite generated tasks.

## Priority Rules

- Preserve the current Pipeline A and Pipeline B runners.
- Prefer additive reports and optional fields before changing core behavior.
- Keep all persistent registry, readiness, transition-prior, and sampler-weight updates behind explicit review or apply commands.
- Treat single rw-task draft smoke scores as diagnostic observations, not final model-separation evidence.
- Prefer small Pipeline B batches and repeated reason-code analysis over single-task prompt tuning.
- Treat `candidate_ready` as legacy structural/export readiness, not proof of actual delivery or training value.
- Compile prompt submission instructions, expected deliverables, rw-task paths and grader staging from one versioned deliverable contract.
- Allow LLM whole-task design only as a proposal layer; deterministic truth, path, registry and promotion authority remain outside the LLM.

## Layer Map

### Source / Skill / Resource Substrate

Owns source provenance, extracted semantic skills, typed resources, local traces, motif hints, and workflow episode proposals.

Existing objects:

- `RawSource`
- `NormalizedSource`
- `SourceBlock`
- `ExtractedSkillCandidate`
- `SkillEvidence`
- `SemanticResource`
- `SkillTraceEdge`
- `SkillMotifHint`
- `SkillRegistryEntry`

Implemented experimental contracts:

- `WorkflowEpisode`

Still-open extension:

- `SourceQualityReport`

### Workflow / Motif / Task Graph Planning

Owns the bridge from isolated skills to workflow-conditioned task structure.

Existing objects:

- `PipelineBSubgraph`
- readiness and transition reports
- composition readiness reports

Implemented V1 or experimental contracts:

- `WorkflowArchetype`
- `MotifGraphGrammar`
- `TaskConstraintGraph`
- `ExecutionPlanDAG`

### Task Package Generation

Owns concrete task artifacts and candidate/teacher contracts.

Existing objects:

- `TaskBlueprint`
- `ReferenceFilePlan`
- `generated_file_manifest.json`
- `evidence_index.json`
- `teacher_input_manifest.json`
- `GoldenRun`
- `TrainingAnnotation`
- `Rubric`
- `pipeline_b_quality_report.json`
- `package_manifest.json`
- `rw_task_export_report.json`

Implemented optional contract:

- `EvidenceDossierPlan`

### Validity / Feedback / Promotion

Owns global task validity, failure attribution, model-separation readiness, and controlled durable updates.

Existing objects:

- `pipeline_b_batch_report.json`
- `pipeline_b_batch_feedback_report.json`
- `pipeline_a_substrate_audit_report.json`
- `typed_resource_patch_proposal_report.json`
- `pipeline_b_eval_summary_report.json`
- `pipeline_b_eval_feedback_report.json`

Implemented V1 or experimental contracts:

- `GlobalTaskValidityReport`
- `RealWorldnessReport`
- `DifficultyProfile`
- `ModelSeparationProfile`
- `TaskVerifierReport`
- `FeedbackAttributionReport`
- `PromotionRecord`
- `RollbackRecord`

Reconstruction extensions:

- `ValidityVector`
- `BehavioralExecutionReport`
- `UtilityProfile`
- `RouteComparisonRecord`

Implemented under the opt-in reconstruction profile:

- `DeliverableContract`
- `CapabilityBrief`
- `TaskDesignProposal`
- `BehavioralExecutionReport`
- `ValidityVector`
- `UtilityProfile`
- `RubricPlanV2`
- `RouteComparisonManifest`
- `RouteComparisonReport`

All remain opt-in reconstruction objects. Their phase gates and promotion semantics are maintained in `pipeline_reconstruction_optimization_plan.md`; implementation does not authorize external execution or default-chain promotion.

## Contract Drafts

### CapabilityBrief V1

Purpose: freeze source-grounded task-design intent before any LLM proposal or deterministic materialization.

Every selected skill now carries registry-level `source_candidate_ids` and `evidence_refs`; resource-node evidence is additive, not the sole provenance source. Opaque `registry-source-candidate:` locators are intermediate values only and are not formal-generation evidence.

### Source Provenance Ledger / Formal Brief Cohort Admission V1

Purpose: resolve each source candidate to its governed source identity, locator and evidence spans, and fail closed before a route-comparison campaign is frozen.

Each provenance record also carries a governed `source_group_id`, normally derived from the Pipeline A batch/workflow collection that produced the accepted candidate. Formal admission blocks GDPVal, fixture, synthetic or unresolved sources; opaque locators; selected skills without both source-candidate and evidence references; missing source groups; more than one source/workflow group inside a brief; non-high workflow fit; missing roles; duplicate motifs, briefs or subgraphs; and incomplete cohort size. Admission is report-only and has no registry, provider, promotion or release authority.

`v3.workflow_group_seed.1` is a report-only selector that admits only registry skills whose source candidates all resolve exclusively to one requested source/workflow group. It may create isolated experiment seeds but cannot change registry readiness or canonical sampling state.

`RouteComparisonCampaignManifestV1.input_class` distinguishes `contract_only` from `formal_public_source`. Formal preparation must freeze a passing admission report whose admitted brief IDs exactly equal the four campaign briefs. Its fingerprint participates in campaign preflight. Contract-only campaigns cannot execute provider routes even when presented with an otherwise valid authorization receipt.

`CampaignAuthorizationReceiptV1` must enumerate exact `authorized_blind_task_ids`. Provider generation defaults to that set and rejects any requested assignment outside it. The receipt binds the non-executable authorization-request fingerprint plus the frozen route manifest, source snapshot, admission report and execution policy fingerprints. Requests are preserved under `governance/authorization_requests/<sha256>.json`. Receipt creation is compiler-governed rather than hand-authored: `RouteComparisonCampaign.compile_authorization_receipt(...)` accepts only a hash-addressed request inside that immutable directory, permits the initial `authorization_required` state or a sequential pending slice in `package_generation_in_progress`, verifies the current frozen campaign state, copies the exact requested scope/model/task IDs/budget, requires an explicit authorization ID, user authorization statement and timezone-aware future expiry, and writes a pending receipt without accepting it or changing campaign state. Accepted receipts are copied to immutable hash-addressed governance storage only by a subsequent passing preflight. Provider execution rechecks the active receipt SHA. Each authorization ID has its own reserved-cost ledger while the campaign-wide ceiling remains additive, so a later bounded receipt neither inherits an earlier slice's usage nor resets total cost. Model, comparison ID, scope, cost, timezone-aware issue/expiry and hard-blocked-model checks remain additive; budget alone never broadens assignment authority.

When `governance/provider_smoke_authorization_request.json` exists, receipt preflight additionally requires `receipt.authorization_request_sha256` to equal that active file's content SHA. A historically valid receipt for a previous sequential slice is not sufficient: it fails closed as `authorization_receipt_active_request_mismatch`, is not copied as the active receipt, and must not change campaign status. This check is additive to exact task IDs, model, budget and frozen fingerprints; downstream scope rejection is not a substitute for correct preflight state.

Behavioral execution uses a separate two-level authority namespace. Historical V1 bounded only solver attempts; V2/V3 hash-bind per-model calls, turns, token/cost ceilings and zero retries. The single-use executor rechecks source fingerprint, accepts one whitelisted public fixture, rejects blind IDs/extra files, and stores manifests under `governance/behavioral_preflight_executions/<authorization_request_sha256>.json`. Budget files live under `governance/solver_execution_budgets/<authorization_request_sha256>/`; process logs live with the execution output root. Neither may use a cross-request model-only path. V2 proved recursive nonempty output insufficient because legacy rw-task moved files under MD5 directories; V3 proved finish, nonempty output and exact paths insufficient when plain text is renamed `.xlsx`. Outcome inspection compares complete paths and runs the same `DeliverableContract` openability inspector. `BehavioralPreflightEvidenceAuditor` independently recomputes budget, outcome, stdout/stderr and deliverable-tree hashes plus model/status identity; integrity pass is distinct from preflight/panel pass. Any mismatch fails closed. No tool-only receipt authorizes blind packages, business tasks, graders, review, mutation or promotion.

`SolverPanelAdmissionPlanV1` combines a persisted frozen panel with a passing evidence-integrity report. A member is reusable only when its persisted report exactly matches the embedded panel report, integrity passes, and tool preflight is business-eligible. Failed members receive typed failure classes and `same_model_retry_allowed=false`; passing members may be retained without another call. `SolverPanelReplacementBoundaryV1` permits only the failed strata, caps the next external model count accordingly, prohibits failed models and Claude Sonnet 4.6, and requires distinct candidates, per-model budgets, fresh parity and a new exact authorization. The boundary itself has no execution authority.

`BehavioralPreflightAuthorizationRequestV3` is the panel-replacement form of level-one authorization. It carries only replacement panel members and their budgets, while hash-binding the admission plan, replacement boundary, retained frozen panel, retained preflight report, retained evidence-integrity report, campaign state and a fresh credential-free container parity report. Its receipt cannot authorize or cause a call for the retained member. The common preflight executor dispatches by request version and emits records only for the replacement budgets. `SolverPanelReplacementMergeReportV1` accepts a final panel only when the retained reports remain byte-consistent, both old and new integrity records pass, replacement identities equal the exact request, every replacement preflight is tool-eligible, and the resulting weak/medium/strong panel passes the existing calibration compiler. None of these records grants blind-package, business-task, grader, review, release, registry or promotion authority.

Solver capability classification requires evidence that a response crossed all four boundaries: provider transport, standard response-field mapping, agent tool-call parsing and sandbox execution. Provider token usage with empty content, no parsed tool calls and no sandbox action is `model_gateway_agent_protocol_indeterminate`, not evidence of weak task-solving ability. Such a run must fail fast after at most two empty assistant responses and cannot enter panel ranking or trigger automatic model replacement. Context-window capacity, summarization threshold and completion-token reservation are separate semantics even when an upstream client exposes one overloaded `max_tokens` parameter.

Current implementation:

- module: `src/task_generator/v3_task_design_frontend.py`
- version: `v3.capability_brief.1`
- output: `task_design_frontend/capability_brief.json`

The brief records source refs and evidence spans, selected semantic skills, observable capability targets, workflow/subgraph/motif context, productive-complexity floor, forbidden shortcuts, domain/safety constraints, allowed file types and an explicit zero-authority proposal boundary.

### TaskDesignSemanticProposal V1 / TaskDesignProposal V2

Purpose: let an LLM propose the complete scenario, business evidence, evidence topology, required judgments and deliverable intent without also authoring execution-only wrappers, then normalize that semantic object into the strict materialization contract without adding or deleting provider-owned semantics.

Current implementation:

- provider schema: `v3.task_design_semantic_proposal.1`
- normalized execution schema: `v3.task_design_proposal.2`
- normalization report: `v3.task_design_normalization.1`
- validation: `v3.task_design_validation.1`
- binding report: `v3.source_skill_binding_report.1`
- proposal-only executor: `src/task_generator/v3_task_design_executor.py`

The semantic provider contract retains scenario, fields, flat records, evidence relations, judgments, skill bindings, deliverable intent and productive complexity. Every relation requires non-empty `from_join_field` and `to_join_field` values in the provider-facing JSON schema; each must name a declared field on the respective endpoint artifact. It omits only proposal/artifact version boilerplate, record wrapper IDs, `candidate_visible`, `proposal_origin` and authority fields. The deterministic normalizer stamps those execution fields, derives each wrapper ID solely from the record's explicit primary-key value, and validates the result as strict V2. It records source/normalized semantic hashes and requires `facts_added=0`, `facts_removed=0`, no semantic loss, productive-complexity preservation and a program-owned all-false authority boundary. It may never synthesize a missing join key, field, value, relation, judgment or binding.

Tracked negative controls cover missing fields, missing relation join contracts, wrong union shapes, legacy nested records, boolean enum display and oversized semantic payloads. Candidate-visible boolean fields, non-text enum values and snake_case enum tokens fail closed. Schema findings contain only location/type/message and never raw provider values. Direct strict V2 remains accepted for compatibility, but future provider system prompts request the semantic contract and explicitly forbid omitted or `null` join keys.

Downstream validation blocks missing/unknown provenance, decorative or unknown skill bindings, incomplete capability-to-behavior mapping, ungrounded evidence topology, exact submission-path claims, governed registry/release mutations, prompt-injection echoes and unresolved design questions. `skill_bindings[].bound_element_ids[]` must exactly equal an evidence `node_id`, evidence `relation_id`, required `judgment_id`, or `deliverable:<exact required section or view>`; raw section text and invented `section_*` aliases are invalid. A pass does not define truth, final paths, rubric authority, registry state or promotion, and does not itself trigger materialization. The executor requires an explicit external-provider gate, defaults to `gpt-5.6-sol`, does not persist raw provider content and blocks `claude-sonnet-4-6` unless separately overridden.

`v3.task_design_execution_request.1.repair_from_execution_report_path` is optional and may be used only for the single governed second attempt. The referenced attempt must match the same brief and route and be either `proposal_blocked` with a persisted strict proposal or `semantic_proposal_blocked` with a parseable persisted semantic draft. The executor compiles a full replacement-proposal prompt containing the preserved strict/semantic proposal, blocking validation or sanitized normalization findings, authority reasons when applicable, and canonical bound-element IDs. The exact initial and repair provider prompts are persisted in their attempt directories, so screening can prove that the second prompt changed and contains governed feedback. A second call without this evidence is rejected rather than merely excluded from repair evidence.

Repair eligibility is narrower than failure status. A semantic draft is repairable only when the complete provider object parses under the compatibility draft schema and the blocked normalization report is persisted; the program never fills the missing semantics itself. Broadly invalid objects remain `contract_failed`. `provider_failed`, materialization failures, or failures without a persisted strict proposal/semantic draft stop without another provider reservation or call. Current-code findings persist only sanitized location/type/message records; raw provider response strings remain excluded. Historical reports, including V28's missing-join failure, keep their original non-repairable meaning and must not be reclassified or backfilled.

Skill-binding cardinality is explicit: `skill_bindings` must contain exactly one entry for every `selected_skills[].skill_id`; selected skills may not be omitted and a skill ID may not appear in multiple binding objects. The causal-binding validator remains authoritative and screening classifies failed findings from their persisted details: invalid element IDs are a namespace failure, duplicate skill IDs are a cardinality failure, and missing/decorative or unknown skills are causal-binding failures. A later successful repair preserves the first classification and never erases the first failure.

`v3.task_design_repair_readiness.1` compiles initial and repair prompts offline from one or more preserved failed execution reports. Every case must prove that the prompt changed, the governed repair marker and prior strict/semantic proposal are present, failure feedback is non-empty and canonical bound-element IDs are available. Formal evidence uses `evidence_mode=portable_bundle`: each failed execution report, brief, strict or semantic proposal, normalization/validation evidence, authority report and binding report is copied into one bundle with a complete relative-path SHA manifest. `v3.task_design_repair_readiness_verification.1` checks the bundle manifest, verifies each execution-report SHA and recompiles both prompts with current code; self-reported pass fields and mutable external paths are not trusted. A formal public-source campaign must freeze both a passing portable readiness report and passing replay verification before it can write a provider authorization request.

Batch ingestion uses `v3.batch_task_design_proposals.1`. Its entries map exact deterministic `case_id` values to proposal paths, optional expected brief IDs and optional SHA-256 values. When supplied, the manifest must cover the selected batch exactly; missing or unknown cases, duplicate entries, unreadable files, hash mismatch and brief mismatch fail closed. It is accepted only under `reconstruction_experimental`. A valid entry routes the case directly to hybrid materialization instead of producing an additional legacy prototype/teacher package.

### Hybrid Task Materialization V2

Purpose: deterministically turn a validated proposal into a candidate-visible evidence ecosystem without letting a legacy template or LLM become truth authority.

Current implementation:

- module: `src/task_generator/v3_hybrid_task_materializer.py`
- materialization report: `v3.hybrid_task_materialization.1`
- evidence dossier: `v3.hybrid_evidence_dossier.1`
- fact anchors: `v3.deterministic_fact_anchor.1`
- rubric bindings: `v3.hybrid_rubric_binding_plan.1`
- complexity report: `v3.complexity_preservation.1`
- visual report: `v3.hybrid_visual_validation.1`
- repair context/loop: `v3.whole_task_repair_context.1`, `v3.hybrid_repair_loop.1`

The materializer assigns filenames and output paths programmatically, creates candidate-visible evidence files, reopens those files to recompute fact anchors, compiles the submission clause from `DeliverableContract`, preserves skill/capability bindings, validates layout/openability, compiles R5 Validity/Utility/rubric artifacts, and exports an rw-task structural draft. Semantic XLSX output wraps long text, applies adaptive row heights and preserves typed date/numeric formats; prompt-level artifact specs must prefer readable business labels and explicit `Yes/No` enums over snake_case states or human-facing booleans. Rubric weights are frozen before results, but the draft remains `not_final_training_data` because behavioral and professional evidence are unresolved. The repair loop allows one initial attempt plus one revision; every revision is rematerialized from scratch. Truth anchors, submission paths, registry state and promotion remain immutable editor inputs.

### Behavioral Execution V1

Purpose: distinguish solver/tool execution from exact delivery, file validity, business validity and professional quality.

Current implementation:

- module: `src/task_generator/v3_behavioral_validation.py`
- solver preflight: `v3.solver_tool_preflight.1`
- execution report: `v3.behavioral_execution.1`
- runner integration: `src/task_generator/v3_rw_task_eval_runner.py`
- governed process budget: `v3.solver_execution_budget.1`
- governed process outcome: `v3.solver_process_outcome.1`
- V2 authorization/executor: `v3_behavioral_authorization.py` and `v3_behavioral_preflight_execution.py`

Hybrid routes require a passing preflight for the same solver model before execution. Preflight covers create, copy, edit, save and submit. A process return code is insufficient: governed execution also requires a real finish signal, nonempty output, matching model/budget outcome and exact delivery inspection. Failure attribution distinguishes budget block, provider failure, tool failure, non-delivery, wrong path, invalid file, business error and insufficient professional quality. Only a successful solver process with an exact valid delivery is grader-eligible.

### Validity, Utility And Rubric V1/V2

Purpose: prevent structural readiness or one aggregate score from standing in for correctness, professional usefulness or training admission.

Current implementation:

- module: `src/task_generator/v3_validity_utility.py`
- validity vector: `v3.validity_vector.1`
- utility profile: `v3.utility_profile.1`
- rubric: `v3.rubric_plan.2`
- calibration contract: `v3.evaluation_calibration_contract.1`
- solver panel: `v3.frozen_solver_panel.1`
- grader stability: `v3.grader_stability.1`
- professional review: `v3.professional_validity_review.1`

`ValidityVector` records factual, semantic, contract, behavioral and professional axes with evidence tier, owner, authority and independence. `UtilityProfile` records evidence integration, planning, judgment, audit trail, deliverable design, accidental-difficulty findings and skill-ablation contribution. `RubricPlanV2` uses seven independent dimensions and freezes factual weight at 0.20; each criterion has its own failure signal, evidence requirement and 0/0.5/1 partial-score semantics. LLM-only professional evidence remains provisional and cannot authorize training admission.

The calibration compiler freezes one distinct, preflight-passed solver for each weak/medium/strong stratum before formal results. Each embedded preflight must match its persisted report. Grader stability accepts only valid-delivery observations whose persisted grader outputs match the declared SHA256, and separates repeated-score disagreement, saturation and cross-solver informative spread. Formal route evidence additionally rechecks the frozen package fingerprint and requires every professional-review support path to exist. LLM proxy professional review cannot emit an expert `pass` or training-admission authority; an authoritative professional pass requires a generator-independent expert record.

### Route Comparison V1

Purpose: compare strict-template, skill-guided LLM and LLM-led hybrid routes under a frozen matched contract.

Current implementation:

- module: `src/task_generator/v3_route_comparison.py`
- manifest: `v3.route_comparison_manifest.1`
- thresholds: `v3.route_comparison_thresholds.1`
- report: `v3.route_comparison_report.1`

Screening freezes four briefs, three routes, twelve route-blind assignments, environment, timeout, retry, budget, solver-preflight and grader-calibration contracts before results. Relative ranking occurs only after absolute gates pass. If all routes fail, the required decision is `redesign_again`. The current implementation is an offline scaffold and does not authorize package generation, provider calls, solver/grader execution or promotion.

`v3.route_blind_staging.1` accepts already-materialized rw-task exports, rejects teacher/provider artifacts, copies each candidate export under its blind task ID, normalizes task and contract identities, removes route-only metadata, revalidates the staged package and records source/staged fingerprints in a separate governance report. Route identity must not be present in the staged candidate package.

`v3.design_authority_validation.1` makes the comparison routes substantively distinct. `skill_guided_llm` must preserve the frozen actor, trigger, workflow graph shape, evidence-node count, evidence-relation count, source/skill/capability set and output formats. `llm_led_hybrid` may propose the scenario and complete evidence topology, but retains the same truth, path, rubric, registry and promotion restrictions.

`v3.reconstruction_promotion_record.2` consumes a completed screening report and optional `v3.route_confirmation_report.2`. Screening must bind a frozen comparison manifest and a passing 12-record evidence compile report; the promotion compiler reruns `RouteComparisonAnalyzer` and requires an exact result match. Confirmation is compiled from five `v3.route_confirmation_gate_evidence.1` records covering absolute gates, matched environment, server reproduction, rollback and major-validity closure. Every gate record and support file is SHA-bound and generator-independent. Screening alone can only hold or redesign. The record is report-only: even `decision=promote` authorizes only an opt-in candidate profile and never activates a release, mutates the default chain or admits training data.

`v3.route_comparison_campaign.1` freezes full briefs, source snapshot, code fingerprint, route manifest, portable repair-readiness bundle and `v3.route_comparison_execution_policy.1`. The strict route uses `StrictTemplateProposalCompiler`; both LLM routes use `TaskDesignProposalExecutor` with `gpt-5.6-sol`, then the shared `HybridTaskMaterializer`. The policy hard-blocks `claude-sonnet-4-6`, disallows provider fallback and raw-response persistence, reserves a per-attempt cost ceiling, limits each assignment to two attempts, and declares `proposal_second_attempt_mode=feedback_conditioned_repair`, `repair_requires_prior_execution_report=true` and `bound_element_namespace_version=v3.canonical_bound_element.1`. Every structural preflight reruns portable-bundle hash verification and current-code prompt replay; a prepare-time pass cannot survive later bundle tampering. Provider generation requires a separately supplied `v3.route_comparison_authorization.1` receipt. When a failed first attempt exists, the second campaign attempt must set `repair_from_execution_report_path` to that preserved evidence. The authorization request includes the readiness and replay-verification SHAs plus repair-policy fields. A receipt can never authorize release activation or registry mutation.

`v3.route_comparison_campaign_preflight.3` reports `external_calls_made` from the persisted campaign rather than assuming every preflight is pre-execution. It also reopens each strict control's governed V2 proposal and materialization report, requires semantic-V2 backend, content and visual pass, provisional Validity/Utility rather than self-awarded pass, and four distinct motif field signatures. Structural checks remain separate from execution authorization.

`v3.provider_screening_outcome.2` is a report-only pre-behavioral decision. It aggregates package completion, per-route materialization, provider attempts, token/duration evidence, feedback-conditioned versus unconditioned retries and reserved cost ceilings. A governed partial slice with pending assignments and no unresolved defect yields `awaiting_provider_completion`, not route instability or `redesign_again`; a first-attempt block that is preserved and closed by the one feedback-conditioned repair counts as a retry observation rather than a currently blocked assignment. Completed-package defects, exhausted blocked assignments, cross-brief instability, unconditioned retry or binding-contract failure yield `redesign_again`. The writer rechecks frozen campaign/package/stage fingerprints and cannot authorize solver, grader, promotion, release or registry actions.

`v3.task_design_proposal.2` adds `v3.evidence_artifact_spec.1` to every candidate-visible evidence node. An artifact spec freezes fact-origin mode (`governed_scenario_fact`, `public_source_fact`, or `methodological_context`), record type, typed fields, units, stable primary key, at least three coherent records and methodological source refs. Required record fields and primary-key identity are validated. Every V2 evidence relation declares from/to join fields and optional typed field comparisons; all referenced fields must exist. Methodological source refs must belong to the node's frozen source refs. Candidate-authored conclusions and final synthesis views are deliverable intent, not reference evidence. V1 remains parseable only for frozen historical artifacts; provider executor now requires V2.

`v3.evidence_content_quality.1` evaluates each materialized evidence workbook separately from openability and path correctness. It blocks the legacy generic-only five-column schema, insufficient business fields, absence of artifact-role semantics in headers, candidate-authored output modeled as reference input, unreadable workbooks and deterministic column-clipping risk. It is report-only for historical V1 packages and a blocking materialization gate for V2. A pass establishes only that candidate files contain readable business-semantic fields matching the proposal; it does not establish business truth, actual rendered display quality or professional validity. Actual workbook rendering remains a distinct audit obligation. V2 materialization writes a candidate-visible Provenance sheet that distinguishes methodological sources from governed fictional scenario values, and deterministic anchors are recomputed from actual materialized join/comparison fields.

V2 provider execution also has an output-size contract. `TaskDesignExecutionRequestV1.max_tokens` permits up to 24,000 tokens, while governed comparison routes freeze 16,000 tokens per attempt as the minimum semantic-V2 completion budget. Preflight blocks any provider route below that floor. This token allowance does not expand cost authority: the route ceiling remains 2 USD per attempt and the campaign ceiling remains 32 USD.

Every `EvidenceNodeProposalV1.artifact_spec.methodological_source_ref_ids` must equal that node's `source_ref_ids` as a set. Empty, missing, or additional artifact-level references are a blocking `artifact_provenance_projection` proposal finding, so a provider may repair the preserved proposal once with explicit validation feedback. Materialization must not silently copy or invent the projection after proposal validation.

`TaskDesignProposalExecutor.replay_persisted_proposal` is a deterministic evidence-replay interface for an already persisted strict `v3.task_design_proposal.2`. It recompiles the current route prompt and writes current proposal, validation, binding, authority and execution reports into a new output root. Its execution request fixes `allow_external_provider=false`; `provider_diagnostics_path` is null; provider, materialization, registry and promotion authority are all absent. This replay may support repair-readiness verification but is not a provider attempt or behavioral observation.

`v3.route_comparison_evidence_input.2` begins as an unfrozen template and must pass an explicit `evidence-freeze` step before compilation. It enumerates exactly 12 blind tasks and SHA-binds the comparison manifest, blind-staging report, solver panel, grader observations, three behavioral reports per task, one professional review and every review support file. Behavioral reports bind the content fingerprint of the actual candidate package seen by the solver, the solver output tree, its preflight report and delivery inspection; absolute paths may change under governed local/server mapping, but content identity may not. `v3.route_comparison_evidence_compile.1` verifies assignment/package/brief identities, exact solver-panel coverage, one shared environment and frozen disagreement/informative-spread thresholds. A task-level valid delivery requires the strong solver and at least two of three grader-eligible panel members to have successful, exact, openable delivery and completed grading. Any task failure blocks release of the entire evidence list; a passing compile report must contain exactly 12 records, and partial cohorts cannot reach `RouteComparisonAnalyzer`.

### DeliverableContract V1

Purpose: make the output filename, relative path, format, creation semantics and delivery inspection rules a single program-owned source of truth.

Current implementation:

- module: `src/task_generator/v3_deliverable_contract.py`
- contract version: `v3.deliverable_contract.1`
- validation version: `v3.deliverable_contract_validation.1`
- output files: `deliverable_contract.json`, `deliverable_contract_validation_report.json`

Minimum contract fields:

```json
{
  "contract_version": "v3.deliverable_contract.1",
  "case_id": "case_id",
  "deliverables": [
    {
      "file_name": "expected_output.xlsx",
      "relative_path": "deliverable_files/expected_output.xlsx",
      "format": "xlsx",
      "creation_mode": "create|copy_then_edit|edit_provided_copy",
      "source_template": null,
      "must_exist": true,
      "must_be_nonempty": true,
      "openability_check": true
    }
  ],
  "prompt_submission_clause": "compiled_by_program",
  "allow_unlisted_deliverables": false
}
```

The compiler owns the final prompt submission clause. The validator blocks filename/path disagreement and undeclared template collisions. Delivery inspection accepts only exact expected paths that exist, are nonempty and pass format openability checks. Invalid delivery stops grading. Legacy exports without this contract retain compatibility behavior and are not retroactively marked as contract-valid.

### WorkflowEpisode

Purpose: preserve source-grounded workflow context around extracted skills.

Initial output files:

- `workflow_episode_proposals.json`
- `workflow_episode_proposal_report.json`

Minimum fields:

```json
{
  "workflow_episode_id": "wfep_...",
  "source_id": "source_...",
  "domain": "audit",
  "business_context": "internal control testing",
  "actor_role": "audit associate",
  "trigger_event": "control exception found",
  "input_artifacts": [],
  "steps": [],
  "motif_hints": [],
  "deliverable_type": "memo",
  "observed_constraints": [],
  "evidence_refs": [],
  "confidence": "low|medium|high",
  "review_status": "proposed"
}
```

Rules:

- Do not write episodes into `SkillRegistry/v3_skill_registry.json`.
- Derive V1 proposals from existing extraction artifacts, trace edges, motif hints, source metadata, and evidence spans.
- Preserve low-confidence and missing-source signals in the report.

### WorkflowArchetype

Purpose: describe recurring real-world workflow types without hard-coding task templates.

Initial output file:

- `SkillRegistry/v3_workflow_archetype_registry.experimental.json`

Minimum fields:

```json
{
  "workflow_archetype_id": "wfa_...",
  "name": "internal_control_exception_documentation",
  "domain": "audit",
  "typical_actor_roles": [],
  "trigger_events": [],
  "common_input_artifacts": [],
  "common_motifs": [],
  "common_deliverables": [],
  "typical_constraints": [],
  "source_episode_ids": [],
  "status": "experimental"
}
```

Rules:

- Start with 3 to 5 hand-written or semi-automatic archetypes.
- Do not make the sampler require archetypes in V1.
- Archetypes provide context, not fixed file/prompt/rubric templates.

### MotifGraphGrammar

Purpose: promote motifs from labels into role/resource/stage contracts.

Initial output file:

- `SkillRegistry/v3_motif_graph_grammar.experimental.json`

Start with:

- `policy_application`
- `fan_in_reconciliation`

Minimum fields:

```json
{
  "motif_grammar_id": "mgg_...",
  "motif_type": "policy_application",
  "required_roles": [],
  "optional_roles": [],
  "required_resource_types": [],
  "provided_resource_types": [],
  "expected_graph_shape": "chain|fan_in|fan_out|dag|constraint_graph",
  "execution_stage_template": [],
  "validation_constraints": [],
  "common_failure_modes": []
}
```

Rules:

- V1 sampler integration should report role coverage only.
- Missing grammar or missing roles should not block existing task generation.
- Batch feedback should aggregate missing roles and fallback reasons.

### TaskConstraintGraph

Purpose: describe task-internal relationships among files, evidence, policy clauses, skills, intermediate artifacts, deliverable sections, and validation constraints.

Initial output file:

- `task_constraint_graph_report.json`

Minimum fields:

```json
{
  "task_constraint_graph_id": "tcg_...",
  "nodes": [],
  "edges": [],
  "graph_shape": "chain|tree|dag|constraint_graph",
  "unsupported_required_nodes": [],
  "diagnostics": []
}
```

Rules:

- V1 can be derived from `reference_file_plan.json`, `evidence_index.json`, `teacher_input_manifest.json`, and `golden_run.json`.
- Constraint graphs may contain validation cycles, but execution plans must remain acyclic.
- Do not change rw-task export based on this report in V1.

### ExecutionPlanDAG

Purpose: make the candidate or GoldenRun solve order explicit and checkable.

Initial output file:

- `execution_plan_dag_report.json`

Minimum fields:

```json
{
  "execution_plan_id": "exec_...",
  "stages": [],
  "dag_valid": true,
  "topological_order": [],
  "missing_inputs": [],
  "validation_notes": []
}
```

Rules:

- V1 can be derived from TeacherRunner intermediate states and golden steps.
- A failed DAG check is diagnostic-only at first.
- Later quality gates may consume this report after it stabilizes.

### GlobalTaskValidityReport

Purpose: collect global task diagnostics without replacing the existing Pipeline B quality gate.

Initial output files:

- `global_task_validity_report.json`
- `real_worldness_report.json`
- `difficulty_profile_report.json`

Minimum fields:

```json
{
  "case_id": "case_...",
  "diagnostic_only": true,
  "real_worldness": {},
  "difficulty_profile": {},
  "task_constraint_graph": {},
  "execution_plan_dag": {},
  "findings": [],
  "recommended_next_layer": "pipeline_a|workflow_graph|package_generation|validity_feedback"
}
```

Rules:

- Do not change `candidate_ready`, `revise`, or `reject` decisions in V1.
- Do not call LLMs or external APIs in V1.
- The report should distinguish structure-complete-but-unrealistic cases from truly broken packages.

### EvidenceDossierPlan

Purpose: describe reference files as an evidence ecosystem, not just generated files.

Initial integration:

- Add optional dossier metadata to `reference_file_plan.json`.

Minimum fields:

```json
{
  "dossier_id": "dos_...",
  "business_context": "internal control exception review",
  "candidate_visible_files": [],
  "teacher_only_files": [],
  "file_roles": [],
  "cross_file_constraints": [],
  "distractor_items": [],
  "expected_evidence_paths": []
}
```

Rules:

- Do not rewrite `ReferenceFileGenerator` just to add this contract.
- Start with the current workbook plus policy document path.
- Represent noise, missing fields, version relations, and conflicts as metadata before generating complex file types.

### TaskVerifierReport

Purpose: reduce prompt/GoldenRun/rubric self-confirmation.

Initial output file:

- `task_verifier_report.json`

Minimum fields:

```json
{
  "verification_status": "diagnostic_only|blocking|revise|pass",
  "blocking_findings": [],
  "revise_findings": [],
  "warning_findings": [],
  "unsupported_conclusions": [],
  "rubric_visibility_issues": []
}
```

Rules:

- Deterministic by default.
- Do not modify GoldenRun or rubric.
- Do not gate quality in V1.

### PromotionRecord

Purpose: make durable state changes explicit, auditable, and reversible.

Initial output files:

- `promotion_proposals.json`
- `promotion_report.json`
- `rollback_record.json`

Minimum fields:

```json
{
  "promotion_id": "prom_...",
  "target_type": "typed_resource_patch|workflow_archetype|motif_grammar|source_quality_rule|transition_prior|registry_admission|readiness_status|sampler_rule",
  "source_report": "path/to/report.json",
  "target_path": "SkillRegistry/v3_skill_registry.json",
  "review_status": "proposed|approved|rejected|applied|rolled_back",
  "diff_summary": [],
  "rollback_record_id": null
}
```

Rules:

- Default command behavior should create proposals only.
- Any apply action must require an explicit flag.
- Task generation must never mutate registry or sampler state as a hidden side effect.
- Every apply must write enough information to support rollback.

## Implementation Status And Reconstruction Extensions

The original implementation order has been completed or superseded as follows:

1. Global validity, real-worldness, difficulty and task-constraint diagnostics exist as report-first outputs.
2. WorkflowEpisode proposals, WorkflowArchetype assets and MotifGraphGrammar are implemented as proposal/experimental layers.
3. Sampler role coverage and batch feedback exist without silent sampler mutation.
4. EvidenceDossierPlan metadata, deterministic TaskVerifier diagnostics and rw-task export validation are implemented.
5. Promotion/rollback proposal plumbing exists and durable mutation remains explicit.

The current open work is not another pass over those V1 diagnostics. R0–R5 offline contracts and the R6 comparison scaffold now cover proposal-to-draft-package semantics, local behavioral gating, Validity/Utility separation and frozen comparison analysis. Exact-coverage batch proposal ingestion, formal source admission and fixed Linux/amd64 container contract parity are implemented. The canonical seed failed admission, but an isolated scratch registry built from already accepted public-source graph-calibration candidates now supplies four distinct, high-fit, fully resolved briefs; the formal campaign is structurally ready and awaits explicit provider authorization. Remaining work is bounded proposal/editor validation, authorized solver/grader calibration, formal matched comparison and explicit R7 promotion or redesign. Container parity does not count as real solver execution. Current phase order and exit gates live only in `pipeline_reconstruction_optimization_plan.md`.

Historical tasks and reports that predate reconstruction contracts remain `not_evaluated`; implementation must not backfill a pass state from legacy readiness.

## Anti-Patterns

- Do not hide Pipeline A resource gaps inside Pipeline B fallbacks.
- Do not turn workflow archetypes into fixed task templates.
- Do not update `SkillRegistry/*.json` from task generation.
- Do not implement fake UCB or bandit behavior before comparable batch feedback exists.
- Do not treat draft rw-task smoke scores as final model-separation evidence.
- Do not let prompt, template, dataset row and grader staging maintain separate deliverable names or paths.
- Do not let an LLM proposal become authoritative truth, registry mutation or promotion state.
- Do not interpret `candidate_ready` as behaviorally validated or training-ready.
- Do not grade missing, wrongly named, empty or unopenable deliverables as business-quality outputs.

## Reality Cohort LLM Proxy Contract

Reality review V2 separates candidate-visible review from teacher-rubric review. Candidate payloads may contain only the blind task, deliverable contract and candidate-visible reference contents; rubric payloads may contain candidate requirements plus rubric plan/bindings. Neither payload may expose route, generator model or provider proposal metadata.

`reviewer_kind=llm_proxy` and `evidence_tier=llm_proxy` cap professional validity at `provisional`. The active cohort uses official `deepseek-v4-pro`; Gemini observations are historical diagnostics and cannot be merged. Six complete passing cases may set `screening_eligible=true`; they cannot set expert evidence, training admission, registry/release mutation or promotion authority.

Each of the 12 frozen stages has one normal attempt. Only timeout/HTTP 408/429/5xx, empty content, truncation, invalid JSON or schema-contract failure may receive one governed formatting retry with identical frozen task input and compact validation feedback. The first attempt tree remains immutable; substantive `pass/revise/blocked` output is never retryable. The campaign ceiling is 24 provider calls and 0.25 USD with SDK retries disabled. A second failure, non-eligible failure, hash drift or token/cost violation yields `incomplete`.

### Rubric Recalibration Contract

`RubricScoringAuthorityAudit` treats only `rubric_plan.criteria` as final weighted criteria. A passing audit requires exactly seven unique criteria, coherent total/factual weights and dimension metadata, and all 21 unordered pairs. Binding-plan entries with `final_weights_assigned=false` and `program_compiled_binding_not_final_weight` are trace annotations and cannot increase the scoring-criterion count. Shared skills, capabilities or evidence are descriptive overlap, while exact duplicate observable behavior or independent failure signal is blocking. A normalized scoring-semantic signature binds criterion identity, dimension, axis, weight, observable behavior and independent failure signal; the older structure signature remains descriptive only.

Rubric Focus V3 must return seven lexically ordered criterion IDs and all 21 lexically ordered pairs. Each pair must cite both criterion IDs and agree with the frozen audit about whether evidence is shared. `revise` requires at least one `potential_duplicate`; `blocked` requires at least one `duplicate`. Cases with the same scoring-semantic signature but different decisions or pair classifications yield `reviewer_inconsistency` and `incomplete`, not selective task mutation. Input ceilings are evaluated over the complete provider message tree, including system instructions, schema, example and payload. Recalibration may reuse hash-bound candidate-pass evidence but has no candidate execution, rubric mutation, screening execution, training or promotion authority.

Rubric Focus Compact V4 preserves the same seven-criterion/21-pair coverage and decision rules while separating exhaustive classification from prose evidence. Every pair returns only `criterion_a`, `criterion_b` and `assessment`. `risk_findings` must correspond exactly to `potential_duplicate/duplicate` pairs and alone carry bounded rationale plus locators citing both criterion IDs; pass pairs cannot emit repeated prose. V3 remains readable historical evidence. A V4 authorization request uses six `rubric_focus_v4_compact` stages and retains the existing 12k input, 4k completion, 12-call and 0.13 USD ceilings.

## Matched Screening V2

`DeepSeekSolverPreflightAuthorizationReceiptV1` 只能绑定一个 immutable `DeepSeekSolverPreflightAuthorizationRequestV1`，并继承 campaign manifest、public fixture tree、parity report、source fingerprint、8-call/1-USD 上限和零 SDK/runner retry。receipt 明确排除私有包上传、业务任务、grader、训练与 promotion。

`DeepSeekSolverPreflightReportV1` 保存 request/receipt/fixture SHA、一次 attempt、进程返回码、stdout/stderr SHA、`SolverProcessOutcomeV1` SHA、provider-call/cost usage 与首次失败。只有进程成功、outcome 身份和预算精确匹配、精确非空可打开 XLSX 交付成立时，`status=pass` 且 `eligible_for_business_eval=true`。执行状态在子进程前写入；已有 running/completed 状态禁止复用 receipt。

Public fixture 的权威形态是单 case 的 rw-task dataset：外层目录下必须恰有 `solver_tool_preflight/dataset_row.json`，case 文件集必须恰为 row、prompt、deliverable contract 与一个 XLSX reference。row 必须声明固定 reference、两个固定 deliverables，以及 tool-only/business=false/grader=false。request compiler 与 executor 必须调用同一验证器；仅有 `SolverToolPreflight.create_fixture` 的 case 内容不构成可授权输入。

`MatchedBusinessAuthorizationReceiptV1` 精确继承 business request 的 12 个 package fingerprints、candidate-tree hashes、Reality hashes、solver selection、parity 和 source fingerprint。receipt 只允许 12 个 DeepSeek solver sessions 与有效交付的单次实质 grader；明确排除 expert、training、registry、release 和 promotion。

`MatchedBusinessExecutionManifestV1` 为每题保存一次 solver attempt、预算、process logs、`SolverProcessOutcomeV1`、delivery eligibility、grader attempts、首次失败与评分 SHA。solver 不重试；grader 仅对 transport/empty/truncated/invalid-JSON/schema failure 允许一次格式补跑。`ScreeningGraderDraftV1` 不包含总分，最终 weighted score 由程序按冻结七维权重重算。无效交付不进入 grader；route metadata 不进入 grader payload。

Completed business evidence may legitimately contain zero grader calls when all deliveries are invalid. In that case task/protocol failures still count against their routes, while provider/environment failures produce `incomplete`. Request `f3addd1f...337873` is the frozen reference case: all 12 records were infrastructure-complete task failures, so aggregation returned `redesign_required`, not `incomplete`.

Recovery contract：`v3.matched_generation_recovery_request.1` 只能绑定一个因不可用 schema response 且没有 persisted strict/semantic draft 而缺失的 replicate-B assignment。它必须绑定已消费 request SHA、首次失败 SHA、当前 campaign manifest、最终 source fingerprint 与固定 parity；仅允许一次 `gpt-5.6-sol` 调用、16k completion、2 USD、SDK retry=0，并排除其他 assignments、Reality、solver、grader、训练及 mutation。确定性 materialization false positive 必须零 provider 回放，不能使用 recovery call。

`v3.matched_screening_campaign.1` defines the next execution slice without rewriting `v3.route_comparison_manifest.1`. It freezes two reconstructed routes, three non-experimental motifs, two briefs per motif and twelve unique blind assignments. Replicate A reuses six hash-bound Reality passes; replicate B inherits the corresponding source group, selected skills, capabilities and file-type budget while changing brief, case, subgraph, trigger, goal and governed scenario identity. Strict-template and evidence-to-deliverable assignments are invalid.

`v3.matched_generation_authorization_request.1` binds the six replicate-B assignments, `gpt-5.6-sol` task-design-only path, 12-call/16k-completion/24-USD ceilings, feedback-conditioned repair, parity and source/admission hashes. It excludes solver, grader, expert, training, registry, release and promotion authority. After materialization, all twelve packages are route-blind staged; only the six new packages enter a fresh two-stage DeepSeek Reality cohort.

Official DeepSeek solver preflight uses a non-thinking OpenAI-compatible tool-call adapter with `max_tokens`, one public XLSX fixture, eight calls and zero retry. A pass selects `deepseek-v4-pro`; otherwise the selector may reuse only the existing hash-complete Gemini pass and cannot select `gpt-5.6-sol`. `v3.matched_business_authorization_request.1` binds the selected solver, all twelve candidate trees and Reality evidence. Valid deliveries receive one substantive `v3.matched_screening_grader_review.1`; weighted totals are recomputed from the seven frozen criteria.

`v3.matched_screening_result.1` emits `confirmation_ready_both | single_route_confirmation_candidate | redesign_required | incomplete`. Infrastructure failures make the cohort incomplete rather than lowering a route score. Professional validity remains provisional and all training/promotion flags remain false.
## Codex E2B Compatibility Slice V1

`CodexE2BSliceScopeV1` is a narrow behavioral compatibility contract. It fixes the Tuzi provider, `gpt-5.6-sol`, `wire_api=responses`, stock E2B `codex` template, zero retries, a 300-second public timeout, two 1,800-second private-task timeouts, and exactly two frozen blind-task bindings. Its receipt derives only from the user's standing project-level external-call and private-upload authorization.

The runner may upload only the candidate prompt, deliverable contract, and candidate-visible XLSX references. The API key is supplied only through the environment of the single `codex exec` command. Configuration, commands, logs, manifests, and downloaded artifacts must not contain it. This path must not import or invoke Stirrup, the DeepSeek solver adapter, or `SolverExecutionBudgetLedger`. A public-probe failure prevents every private upload. Results are limited to `compatibility_pass`, `compatibility_failed`, or `incomplete`; they carry no grader, route-comparison, training, release, registry, or promotion authority.

## Local Codex Matched Screening V1

`CodexLocalScreeningScopeV1` replaces the active E2B solver path without rewriting its historical records. It binds exactly twelve blind task IDs, the 2 routes × 3 motifs × 2 replicates matrix, package fingerprints, full candidate-package trees, candidate-visible projection trees, Reality evidence hashes, one pinned `@openai/codex` installation identity, `gpt-5.6-sol`, the post-document parity report and the governed source fingerprint.

The candidate-visible projection contains only `dataset_row.json`, `deliverable_contract.json`, and `reference_files/*.xlsx`. Export reports, expected-deliverable governance files, teacher files, route identity, old E2B deliveries and previous solver outputs are excluded. Each task receives a fresh local workspace and exactly one `codex exec` process. The process inherits only the `CODEX_HOME` path required for existing ChatGPT authentication; the runner does not read or copy `auth.json`, and removes known provider API-key variables from the child environment.

`CodexLocalExecutionStateV1` is written atomically before the public probe and before each task. Resume may continue only `not_started` tasks. A `running` entry observed after interruption becomes `interrupted` and is not automatically retried. `CodexLocalProcessOutcomeV1` preserves the JSONL, stderr, exit code, duration, best-effort usage, workspace/output tree and first failure. Timeout with observed tool activity is a solver task failure; explicit authentication/service/protocol/runtime failure is infrastructure incomplete.

The local process uses `--sandbox danger-full-access` only for the nested Codex CLI layer because the desktop host's managed read-only policy is inherited across the process boundary and overrides CLI `workspace-write`, even after ambient `CODEX_*` variables are removed. The runner remains enclosed by the outer managed workspace boundary and a per-task projected workspace, keeps approval mode `never`, and must not use `--dangerously-bypass-approvals-and-sandbox`. `execution_isolation=outer_managed_workspace_codex_danger_full_access` is immutable scope data.

Executed scope `a23babbc...a3fa0` is the first homogeneous local-Codex business cohort: its public probe passed and all twelve solver processes produced admitted deliveries, six per route, with no retry or infrastructure failure. The retained DeepSeek grader accepts its official key from either an in-memory `.env` value or the existing ignored raw compatibility file; neither path may copy or persist the secret. The grader run produced six completed and six infrastructure-failed records. A completion-length/schema failure remains missing evidence and must not be converted to a zero score. Consequently `MatchedScreeningResultV1.decision=incomplete` even though exact-delivery, offline-validity, productive-complexity and skill-causal counts are 6/6 for each route.

### Compact screening grader V2

`CompactGraderScopeV2` is grader-only. It binds the frozen local-Codex solver manifest, twelve solver-outcome hashes, twelve exact delivery hashes, candidate/teacher paths, rubric hashes, deterministic-anchor hashes, the current source fingerprint and the final no-credential parity report. Legacy scope version `.2` remains readable with its frozen 20k-input/2k-completion contract. Active version `.2.1` retains the same compact seven-score output and high-thinking evaluator but uses 20k input and 4k completion after the 2k external run repeatedly exhausted hidden reasoning before emitting JSON. Both versions permit at most two attempts per task and zero SDK retry. Neither has solver, confirmation, training or promotion authority, and results from different scope versions cannot be merged into one homogeneous cohort.

`ProfessionalCalibrationScopeV1` is a six-task, grader-only cross-model check over the completed Compact V2.1 cohort. It selects exactly one frozen delivery for every route × production-motif cell and includes both replicates across the sample. The provider is fixed to Tuzi `gemini-3.1-pro-preview`, with 20k input, 2.5k completion, one substantive review and at most one format/transport retry. The provider payload contains candidate requirements, the frozen compact rubric, deterministic fact anchors and the actual XLSX; it never contains route identity or the DeepSeek review. Only after the independent response is persisted does the program compare all 42 criterion judgments. `calibration_consistent` requires professional-plausibility agreement ≥5/6, major-defect agreement 6/6, mean absolute criterion delta ≤0.5 and maximum absolute delta ≤1. The result remains `llm_proxy` and provisional, with no solver, confirmation, training, promotion or task-mutation authority.

`CompactGraderDraftV2` replaces seven repeated rationale/locator blocks with one fixed `CompactScoreVectorV2`, at most five deduction findings and at most two exceptional-evidence records. Scores use 0–4 anchors: 3 is professionally adequate and contract-complete; 4 is exceptional beyond the contract and requires matching exceptional evidence; every score at or below 2 requires a criterion-bound finding. Major defects and major findings must agree. The model cannot provide a total, professional-plausibility decision or effective-dimension count; `CompactGraderReviewV2` computes those fields deterministically.

`CompactGraderManifestV2` writes `running` before each call. A stale running task becomes `interrupted` and is never silently regraded. Completed records are reusable; low scores are never retried. `CompactScreeningOutcomeV2` embeds the unchanged matched-screening analyzer result, score distribution and evidence ceilings. Missing grades remain infrastructure-incomplete rather than zero scores. V1 grader artifacts remain readable and immutable.

`CodexLocalDeliveryInspectionV1` admits only the exact contracted path when it is non-empty, is a real openable XLSX, contains at least one non-empty worksheet and does not byte-match an input workbook. Only admitted deliveries enter the existing route-blind DeepSeek JSON grader. The grader keeps one substantive judgment and at most one format/transport repair, programs the seven weighted dimensions itself and never retries a low score. The resulting `MatchedScreeningResultV1` retains its four frozen decisions and provisional professional-validity ceiling.

## Direct public-source exact URL input

`DirectWebSourceCollector.collect(..., seed_urls=[...])` is a bounded input mode of the existing deterministic collector. It bypasses Serper search and fetches only the supplied public URLs; it does not add a second crawler, LLM browsing or registry authority. The collection request records `collector_model=direct_url_trafilatura` and `search_backend=direct_url`, and each source trace records the exact URL.

The SSRF boundary still rejects localhost, literal non-public IPs, HTTP endpoints resolving to non-public space and all ordinary private/reserved addresses. On hosts using a transparent fake-IP DNS proxy, an HTTPS hostname may resolve into `198.18.0.0/15`; this mapping is accepted only for a non-literal hostname and continues through normal TLS hostname verification. A bare `https://198.18.x.x/...` URL and the same hostname over HTTP remain blocked.

Exact URL collection has source-material authority only. Normalization, source quality, skill extraction, review, registry mutation, task generation and promotion remain separate stages.

## Representative Production Pilot V1

`FormalRepresentativePilotAdmissionReportV3` extends the existing per-brief source/trust admission without changing historical V1/V2 reports. It requires exactly 12 unique briefs: two for every `audit_compliance | procurement_operations` × `fan_in_reconciliation | cross_check_validation | policy_application` cell. Case and subgraph IDs must also be unique. Every required capability must be causally bound by a selected skill, and the productive-complexity floor must preserve an evidence gap, exception, conflict or uncertainty requiring judgment.

`RepresentativeProductionPilotManifestV1` binds those 12 briefs to 24 unique assignments across `skill_guided_llm` and `llm_led_hybrid`. It fixes `professional_validity=provisional_ai_assumed_sufficient_for_pilot`, `expert_evidence_present=false`, `training_authorized=false` and `registry_mutation_authorized=false`. The procurement bindings use only the first accepted FAR skill-extraction set; the truncated second extraction cannot enter the manifest.

`RepresentativePilotGenerationResultV1` is task-design-only. It uses the existing `TaskDesignProposalExecutor` and `HybridTaskMaterializer` with Tuzi `gpt-5.6-sol`, 16k completion, zero SDK retry and no cost-ledger preblock. Each assignment receives one normal attempt; only a persisted strict `proposal_blocked` or parseable `semantic_proposal_blocked` may receive one feedback-conditioned repair. The result is atomically written before provider entry, and stale `running` cases cannot be silently rerun.

Generation success requires all 24 packages to materialize with unique package-tree fingerprints. Partial packages cannot enter Reality as a smaller pilot. The first R8.3 provider run is immutable at 22/24: both blocked records were LLM-led `candidate_output_modeled_as_reference_input` findings.

`RepresentativePilotPackageReadinessV1` may correct only a deterministic validator false positive without rewriting that provider record. It requires exact original package-tree matches for every materialized case and zero-provider replay of every blocked proposal. Replay eligibility is limited to the preserved content finding; the replay must pass proposal, content, provenance, visual, export and isolation gates. The resulting record binds all 24 package trees, identifies original versus replay source and keeps provider calls, training and registry mutation false.

`RepresentativeRealityScopeV1` binds exactly 24 unique ready-package fingerprints, route-blind candidate trees, teacher rubric inputs, deterministic scoring-authority audits, fixed Linux/amd64 parity and the governed source fingerprint. Official `deepseek-v4-pro` executes all 24 candidate-blind reviews before 24 Compact Rubric Focus V4 reviews. Each stage receives one normal attempt; only transport, empty, truncated, invalid-JSON or schema-contract failure may receive one controlled retry on the frozen input. SDK retries are zero and the campaign ceiling is 96 calls. The result remains `llm_proxy`, professional validity remains provisional under the user-directed pilot waiver, and training, registry, release, expert and promotion authority remain false.

`CodexLocalScreeningScopeV1` retains historical scope version 1 for the 12-task matched matrix and adds version 2 only for the representative pilot. V2 requires exactly 24 unique bindings over `domain × route × motif × replicate`, and binds each package tree, candidate-only projection, Reality case evidence, exact deliverable, fixed CLI installation, parity and source fingerprint. Both versions use the same `CodexLocalRunner`: one public probe, one process per task, no runner retry, existing ChatGPT authentication, exact-path XLSX inspection and interrupted-task fail-closed recovery. V2 does not add a new agent, provider adapter or sandbox.

`CompactGraderScopeV2` keeps scope versions 2/2.1 readable for the historical 12-task matched cohort and adds scope version 3 only as a 24-binding representative wrapper around the unchanged Compact V2.1 scoring contract. Every V3 binding includes domain and must fill exactly one `domain × route × motif × replicate` cell. The provider remains official `deepseek-v4-pro`; the seven 0–4 score dimensions, programmed weighted score, professional-plausibility rule, 4k completion ceiling, zero SDK retry and one format/transport retry are unchanged. Representative aggregation requires each route to pass 12/12 offline validity and skill-causal coverage, at least 10/12 valid delivery, professional plausibility and productive complexity, zero major defects, at least five effective dimensions for every delivered task, no more than 8/12 scores at or above 0.9, and at least 10 comparable pairs. It additionally emits two fixed 12-task domain summaries and has no training, confirmation or promotion authority.

Scope version 3.1 is the sole bounded recovery from a homogeneous V3 high-thinking completion failure. It preserves every V3 binding and scoring invariant but fixes `deepseek_reasoning_mode=disabled`; the provider request omits `reasoning_effort` and sends explicit disabled thinking without temperature. V3.1 must regrade all 24 deliveries from scratch. V3 and V3.1 reviews cannot be merged, and a second V3.1 format failure after the single controlled retry remains infrastructure incomplete.

`CodexLocalGraderScopeV1` is the post-DeepSeek report-only fallback. It imports all 24 immutable delivery/rubric/fact-anchor bindings from one frozen representative Compact scope, binds the pinned Codex CLI, parity and governed source fingerprint, and labels evidence as `same_model_behavioral_proxy`. `CodexLocalGraderRunnerV1` creates one route-blind workspace per task and invokes the native CLI with `--output-schema` plus `--output-last-message`; it does not call a provider adapter or reuse solver workspaces. Each task gets one process and no retry. A valid result must parse as `CompactGraderDraftV2`, preserve the blind task identity and all score/finding/exceptional-evidence invariants; weighted score and professional plausibility are program-owned. Interrupted records cannot be rerun silently. The outcome has no independent-model, expert, training or promotion authority.

`RepresentativeRouteConvergenceReportV1` is a deterministic, report-only consumer of one complete `CodexLocalGraderOutcomeV1`, its completed manifest/scope chain and one frozen `RepresentativeCodexCampaignV1`. It requires 24/24 completed grades, both absolute route gates, twelve complete matched pairs and exact task-identity agreement. Candidate-package complexity is recomputed only from the current route-blind `candidate/reference_files/*.xlsx` projection, including each file hash and byte count. The simplicity tie-break is legal only when the route mean-score gap is at most 0.025, matched-pair wins differ by at most two, and one route reduces both workbook count and bytes by at least 25 percent. The report may name a production candidate and challenger, but `default_generator_change_authorized`, registry, release, training and promotion authority are all fixed false.

`CandidateDataAdmissionManifestV1` is the R8.5 report-only data gate. It requires exact identity across the representative campaign, complete local-grader outcome, completed grader manifest/scope and accepted route-convergence report. Every admitted record binds package fingerprint, candidate tree, Reality evidence, exact delivery, grader review and programmed weighted score. It also requires candidate manifests to declare `teacher_artifacts_included=false` and every behavioral/quality observation to pass. Route roles are fixed to 12 `llm_led_hybrid` production-candidate records and 12 `skill_guided_llm` challenger/control records. The contract explicitly exports no examples and authorizes no dataset export or training.

`ExternalModelComparisonCampaignV1` binds the frozen 24-task representative campaign, GPT baseline solver/grader manifests, fixed parity/source fingerprint and pinned Codex CLI. Its only external stacks are Tuzi `gemini-3.1-pro-preview` and `deepseek-v4-pro`, both using native `wire_api=responses`, process-only `TUZI_API_KEY`, no temperature/reasoning override and zero custom-provider/runner retry. It authorizes private task upload only after that stack's public XLSX probe passes.

`ExternalComparisonExecutionManifestV1` records model-isolated probe/task state, outcome hashes and systemic freeze reason. Interrupted work is never silently rerun. Three consecutive identical infrastructure failure codes freeze that stack; task failure does not stop independent tasks. `ExternalComparisonGraderManifestV1` grades only admitted deliveries with the existing local Codex grader and marks missing/invalid delivery `not_eligible` with zero grader attempts.

`ExternalModelComparisonResultV1` combines the retained GPT baseline and external observations, emits model/domain/motif summaries plus pairwise common-task comparisons, and requires 20 valid and fully graded deliveries for capability eligibility. Its decisions are `comparison_complete`, `comparison_partial_one_external` or `comparison_incomplete`. A pair is `practical_tie` unless the frozen delivery, major-defect or 0.05 score-difference threshold is met. It has no default-solver, training, release or promotion authority.

Failure classification must inspect only structured Codex terminal error events (`error`, `turn.failed`) and process stderr. Candidate-visible prompt, task content, tool output and ordinary assistant events are not failure-taxonomy evidence, because domain text may legitimately contain words such as `unauthorized` or HTTP status codes. A classifier correction may be recorded as an offline evidence audit, but it must not rewrite raw JSONL, stderr or first-run artifacts and cannot authorize a retry.

### Official DeepSeek and OpenCode contracts

`OfficialDeepSeekOpenCodeCampaignV1` binds the same 24 immutable task/package/candidate-tree/Reality identities, the frozen GPT solver/grader baseline, final parity/source fingerprint, official endpoint `https://api.deepseek.com`, model `deepseek-v4-pro`, E2B template `opencode`, WSL Ubuntu fallback and the exact matched-pair admission gate. It contains no cost ledger and grants no training, release or promotion authority.

`OfficialDeepSeekProviderProbeV1` is public-only and must prove both model discovery and one complete streamed tool-call/result continuation before any private package upload. `OpenCodeEnvironmentProbeV1` records OpenCode, Python and openpyxl identity without model credentials. `SolverEnvironmentSelectionV1` selects the first public-agent-probe pass and requires the entire private cohort to remain on that one environment.

`OpenCodeProcessOutcomeV1` stores redacted JSON events, stderr, environment identity, duration, usage, native-retry signals, exact delivery inspection and first failure. Project orchestration starts each task once. Interrupted tasks are never silently rerun. The two frozen matched tasks must both pass before the remaining 22 become runnable; a failed business result cannot be redrawn in a different environment.

`OfficialDeepSeekOpenCodeExecutionAuditV1` is the immutable post-run correction layer for failure-taxonomy defects. It reads but never rewrites process outcomes, classifies infrastructure only from persisted structured diagnostics and stderr, recomputes the first three-consecutive-failure freeze point, and marks every later attempted task `out_of_scope_after_freeze`. DNS resolution failures, `ConnectError`, `RemoteProtocolError`, incomplete chunked responses and peer-closed streams share the governed `service_or_stream_failure` class. A governance breach forces `stack_incomplete`; later files cannot restore capability eligibility.

`OfficialDeepSeekOpenCodeGraderV1` admits only normally completed, exact valid XLSX deliveries and invokes the existing local Codex structured grader once per file. `OfficialDeepSeekOpenCodeResultV1` compares only common completed tasks with the frozen GPT baseline, requires at least 20 valid and fully graded DeepSeek deliveries for comparison readiness, and preserves the existing delivery/major-defect/0.05-score materiality thresholds. All professional validity remains provisional.

Provider usage is best-effort telemetry for this stack: absence of usage fields in valid persisted OpenCode events does not invalidate a normally completed, audited delivery or grade. Duration, exit state, event integrity, output-tree identity and XLSX admission remain mandatory. `practical_winner` is an engineering comparison field computed only after the coverage and materiality gates; it carries no default-solver mutation authority.

## ProductionTaskCohortV1 (R9)

`v3.production_task_cohort.1` binds six freshly collected official-source records and ten unique `CapabilityBriefV1` records. Sources carry HTTPS canonical URL, allowlisted host, collection path, content SHA256, time and TLS-hostname status. The cohort requires five briefs per domain, one `llm_led_hybrid` route and motif counts 4/3/3. Duplicate source/brief content, task IDs or unknown source bindings fail closed.

`v3.production_generation_result.1` permits one Tuzi `gpt-5.6-sol` proposal call and only one feedback-conditioned repair for a persisted strict or semantic finding. It never permits unconditional redraw, canonical registry mutation, training or public release. Package admission retains isolation, provenance, content, render, formula, export-identity and fingerprint gates.

`v3.production_model_comparison.1` accepts only exact valid XLSX and two valid seven-dimension judge records. Composite is their arithmetic mean; either judge's major defect is retained. A score delta of at least 0.15 or major-defect mismatch records judge disagreement. Comparison needs eight dual-graded tasks per model and eight common tasks.
