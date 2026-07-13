# Production MVP Definition

## Status

Document lifecycle: `active / reference`.

This document defines the first Phase 13 production contract for the finance/audit scope.

It remains the current production-state reference, but project status and next-stage priorities are maintained only in the root `项目概要.md`.

It does not replace the existing Pipeline B quality gate, verifier, or global validity diagnostics.
Instead, it adds a production-facing state machine and batch-manifest contract on top of the current candidate-ready path.

Current implementation scope in this repo:

- `candidate_ready` remains the highest automatically assigned task state
- `production_candidate` is still a governed target state and should not be assigned silently
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

The production lifecycle is defined as:

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
This state is intentionally not auto-assigned until the dedicated production QA gate exists.

### `training_pool_candidate`

Entry conditions:

- `production_candidate`
- candidate-facing rubric hygiene passes
- evidence closure passes
- no manual blocker remains

### `diagnostic_eval_sampled`

Entry conditions:

- `production_candidate`
- selected by an explicit eval sampling policy
- executed eval completed or was explicitly skipped with a recorded reason

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

## Initial Rules

- Keep the current Pipeline B batch runner intact.
- Keep all production metadata additive.
- Do not silently upgrade `candidate_ready` to `production_candidate`.
- Keep eval evidence diagnostic unless a later phase explicitly validates stronger comparison semantics.
- Keep registry and promotion changes explicit and reviewable.
