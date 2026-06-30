# TaskGenerator V2 Schema Design

## Document Status

This document records the V2 schema design, finance prototype, and experiment history.

The current macro roadmap is now maintained in:

- `docs/architecture/pipeline_architecture_v3.md`

Use the documents as follows:

- `docs/architecture/schema_design_v2.md`: schema details, V2 object definitions, finance prototype evidence, and quality-gate lessons
- `docs/architecture/pipeline_architecture_v3.md`: project-level plan for batch automatic task generation, source-to-skill extraction, skill-to-task assembly, and GoldenRun engineering

The main project direction is no longer to keep polishing one finance task. The finance task is a prototype for discovering pipeline constraints.

## Goal

Build a GDPVal-style real-world-task generation framework for **training** rather than only evaluation.

The core split is:

- `SemanticSkill`: reusable semantic capability unit
- `TaskBlueprint`: one concrete task instance assembled from semantic skills
- `TrainingAnnotation`: supervision metadata for training and diagnosis
- `GoldenRun`: teacher-mode canonical solution and grading anchors

This separation lets us keep skill extraction semantic-only, while moving difficult task construction and supervision design into the assembly stage.

## Design Shift

The old pipeline leaned toward:

- slow extraction of very specific skill/operator bundles
- fast deterministic task assembly
- tightly coupled prompt and rubric logic

The new pipeline leans toward:

- extracting only semantic capabilities
- assembling realistic tasks with stronger LLM assistance
- generating explicit `GoldenRun` artifacts for result-based supervision

## V3 Atomic Skill Extraction Update

V3 now inherits the useful parts of the old skill-extraction line without keeping its brittle operator-heavy payloads.

Already carried forward:

- old `ports.requires/provides` are represented as `input_contract` and `output_contract`
- old business intent and data-profile context are represented as `business_meaning`, `common_deliverables`, and `assembly_hints`
- old Fact / Reasoning / Robustness / Compliance review dimensions are represented as tags and reviewer checks
- evidence grounding is mandatory through `SkillEvidence` spans that cite source and block IDs

The key correction after the first GDPVal prompt-only run is that `SemanticSkill` must be more atomic than a full task.

Task-level candidates such as:

- `Individual Tax Return (Form 1040) Preparation`
- `Profit and Loss Report Preparation with Tax Withholding`
- `Prepaid Expense Amortization Schedule Preparation`

are useful signals, but they are too broad for direct registry insertion unless decomposed. The registry should prefer reusable atomic capabilities such as:

- mapping source-document fields to filing inputs
- detecting missing supporting schedules or policy notes
- reconciling source totals to report line items
- computing period allocation schedules
- validating jurisdiction-specific compliance evidence

This means Pipeline A should optimize for:

- diversity across capability types
- reusability across future tasks
- composability inside Pipeline B
- source-grounded evidence
- no leakage of exact files, rows, generated values, forms, or rubric wording into the skill identity

The deterministic reviewer now treats task-level overbreadth as a first-class risk. Broad `Preparation` candidates, form-bound tax candidates, and jurisdiction-bound candidates should generally be marked `revise` with a suggested abstraction rather than entering the registry unchanged.

Current GDPVal prompt-only validation:

- old DeepSeek run on 5 `Accountants and Auditors` prompts produced 5 candidates and the earlier reviewer accepted all 5
- rerunning the stricter reviewer on that old output now gives 2 accepted and 3 revise decisions
- `Individual Tax Return (Form 1040) Preparation` is now revised toward `Structured Statutory Filing Input Mapping` or `Jurisdiction-Specific Compliance Schedule Selection`
- a new DeepSeek run with the atomic prompt and `max_candidates=30` produced 12 candidates
- the stricter reviewer accepted 10 and revised 2 broad/form-bound candidates
- the resulting per-run registry contains 10 entries and excludes the revised task-level candidates
- the persistent registry update loop now stores accepted atomic skills in `SkillRegistry/v3_skill_registry.json`
- this persistent registry had 44 entries from four GDPVal prompt-only occupation batches before the first web-source Pipeline A smoke:
  - `Accountants and Auditors`
  - `Financial Managers`
  - `Financial and Investment Analysts`
  - `Compliance Officers`
- per-run registries are still useful inspection artifacts, but the persistent registry is the source that future Pipeline B sampling should eventually consume
- the multi-batch runner is `Test/run_v3_gdpval_pipeline_a_batch.py`
- the latest aggregate batch report is `SkillRegistry/v3_pipeline_a_batch_report.json`
- current batch-scale lesson: `max_candidates=30` can produce truncated JSON from DeepSeek on larger prompt batches, so the batch runner defaults to `max_candidates=15` and `max_tokens=12000`
- batch diagnostics now record reason-code counts, suspicious accepted candidates, and provider/parameter metadata
- after stricter reviewer calibration, the three multi-batch rerun results are:
  - `Financial Managers`: 14 candidates, 11 accepted, 3 revise
  - `Financial and Investment Analysts`: 15 candidates, 11 accepted, 4 revise
  - `Compliance Officers`: 8 candidates, 6 accepted, 2 revise
- after the first web-source smoke and the 3-topic web-source batch, the persistent registry has 66 entries; the older GDPVal update report still lists 6 unmatched existing entries that should be audited rather than silently deleted
- a non-destructive persistent registry audit now exists:
  - module: `v3_skill_registry_audit.py`
  - CLI: `Test/run_v3_skill_registry_audit.py`
  - default output: `SkillRegistry/v3_skill_registry_audit_report.json`
  - default scope: `unmatched_existing_entries` from the latest registry update report
  - current result: 6 audited entries, all reported as `quarantine_recommended`
  - the audit recognized open-web retrieval as `source_collection_leakage`
  - the audit recognized profiles, slides, visualizations, and risk-assessment-question construction as broad deliverable or task-level risks
  - this is report-only; no `SkillRegistryEntry` schema migration, deletion, inactive flag, or automatic quarantine has been introduced
  - audit decisions are deterministic governance hints for future sampling, not ground-truth labels
- the first SourceCollector MVP now exists:
  - module: `v3_source_collector.py`
  - search tools: `v3_source_search_tools.py`
  - web collection CLI: `Test/run_v3_stirrup_source_collector.py`
  - connector CLI: `Test/run_v3_collected_sources_to_skill_package.py`
  - web-source Pipeline A runner: `Test/run_v3_web_source_pipeline_a.py`
  - web-source Pipeline A batch runner: `Test/run_v3_web_source_pipeline_a_batch.py`
  - default env source: `E:\THU\2026Spring\SRT\rw-task\.env`
  - default search backend: Serper via `SERPER_API_KEY`
  - Brave remains a compatibility backend only; the default path no longer requires `BRAVE_API_KEY`
  - SourceCollector emits `RawSource` records and raw text artifacts, not skills
  - collected `RawSource` records can be normalized into a `SkillExtractionPromptPackage`
  - formal web collection requires `--allow-web-collection`; dry-run prompt generation works offline
  - Serper smoke `audit_smoke_serper_02` collected 3 accepted RawSources and produced a normalized skill extraction prompt package
  - web-source Pipeline A dry-run on `audit_smoke_serper_02` produced source quality status `pass`
  - formal web-source Pipeline A with DeepSeek official `deepseek-v4-flash` produced 5 candidates, 5 accepted, 0 revise, and 0 reject
  - persistent registry update added 5 web-derived entries, raising `SkillRegistry/v3_skill_registry.json` from 44 to 49 entries
  - idempotency rerun with `--reuse-existing` produced 0 new entries and 5 merged candidates, keeping entry_count at 49
  - the 3-topic web-source batch collected 9 sources, all source-quality reports passed, and DeepSeek produced 17 candidates
  - the first deterministic reviewer accepted all 17 web-source batch candidates; this was a useful plumbing success but also a reviewer-calibration warning
  - reviewer calibration now reviews the same 17 extracted candidates as 8 accept and 9 revise
  - new review reason codes target broad documentation deliverables, broad control-assessment skills, and weak action granularity
  - the web-source batch raised the persistent registry to 66 entries; idempotency rerun produced 0 new entries and 17 merged candidates
  - after calibration, idempotency rerun keeps entry_count at 66 and reports 8 merged accepted candidates because 9 former accepted candidates now revise
  - reviewer calibration and web-source governance audit are report-only and do not mutate `SkillRegistryEntry`
  - web-source Pipeline A runners now support `--skip-registry-update` for report-only calibration and `--calibration-only` for graph calibration runs that also build transition reports
  - calibration-only outputs should use a separate output directory and should not be interpreted as accepted persistent registry growth
  - 3-topic web-source graph calibration with `--calibration-only --max-candidates 8` produced graph-rich outputs for all default topics while keeping registry entry_count at 66 and `registry_entry_delta_this_run=0`
  - no new schema was introduced for web-source batch mode; it reuses `RawSource`, `NormalizedSource`, `ExtractedSkillCandidate`, and `SkillRegistryEntry`
  - this preserves the boundary between source gathering and semantic skill extraction
- a non-destructive sampling readiness layer now exists:
  - module: `v3_registry_sampling_readiness.py`
  - CLI: `Test/run_v3_registry_sampling_readiness.py`
  - default output: `SkillRegistry/v3_registry_sampling_readiness_report.json`
  - it combines persistent registry entries, registry audit records, and reviewer calibration records
  - current result on 66 registry entries: 30 `sample_ready`, 7 `sample_with_caution`, and 29 `exclude_until_revised`
  - this layer does not add `status`, `inactive`, or `quarantine` fields to `SkillRegistryEntry`
  - `single_source_support` is a sampling weight signal, not a standalone rejection reason
  - future Pipeline B sampling should default to `sample_ready`, downweight `sample_with_caution`, and avoid `exclude_until_revised`

## V3 Composability Planning Update

The next Pipeline A design target is not merely to grow the registry. The target is to make the registry composable by Pipeline B.

The old system already had the right intuition with `ports.requires` and `ports.provides`: a skill should declare what it consumes and what it produces. The failure mode was treating port compatibility as string matching or repeatedly asking an LLM to judge all possible successor pairs.

The updated direction is:

- keep ports, but refine them into typed semantic resources rather than plain names
- keep transition likelihoods, but store them in a separate graph/report layer instead of embedding static `possible_successors` inside every skill
- initialize transition priors from local source traces, such as skills extracted in natural order from the same GDPVal prompt or professional guide
- let future task-quality feedback update transition and motif weights
- treat task assembly as sampling a small executable skill-resource subgraph, not necessarily a single skill chain

### Semantic Resource Ports

`SemanticContract` now keeps the original natural-language lists:

- `requires_semantics`
- `optional_semantics`
- `provides_semantics`

It also adds typed resource lists for future composition:

- `required_resources`
- `optional_resources`
- `provided_resources`

Each resource is a lightweight `SemanticResource` record:

```json
{
  "resource_type": "MonetaryAmount",
  "subtype": "NetProfit",
  "attributes": {
    "currency": "unknown_or_explicit",
    "period": "required",
    "entity": "required"
  },
  "domain": "finance",
  "evidence_refs": []
}
```

This lets `NetProfit` satisfy a later requirement for `MonetaryAmount` even though the surface names differ. It also lets Pipeline B distinguish cases where the value is compatible in type but missing required attributes such as period, jurisdiction, entity, or source currency.

Initial finance/audit/compliance resource vocabulary should stay small:

- `SourceDocument`
- `StructuredTable`
- `FinancialMetric`
- `MonetaryAmount`
- `TimePeriod`
- `Entity`
- `Jurisdiction`
- `PolicyRule`
- `ComplianceRequirement`
- `ControlEvidence`
- `AuditSample`
- `ExceptionRecord`
- `AuditFinding`
- `ReconciliationDifference`
- `DeliverableSection`

### Transition Priors

The project should avoid full all-pairs LLM successor judging. Instead, Pipeline A should produce local transition evidence while extracting skills.

Example:

```text
source trace: A -> B -> C
edge priors: A->B += local_order_observation, B->C += local_order_observation
optional weak edge: A->C += same_context_observation
```

These edges are not hard dependencies. They are priors that Pipeline B can combine with semantic compatibility, readiness, domain fit, difficulty target, and exploration bonuses.

The future transition artifact should probably be separate from `SkillRegistryEntry`:

```json
{
  "from_skill_id": "skill_a",
  "to_skill_id": "skill_b",
  "transition_prior": 0.7,
  "compatibility_score": 0.8,
  "observed_count": 3,
  "success_count": 0,
  "failure_count": 0,
  "evidence_traces": ["source_x:block_1->block_2"],
  "reason_codes": ["same_source_order", "resource_compatible"]
}
```

The first implementation is now report-only rather than a persistent transition database:

- module: `v3_skill_transition_graph.py`
- CLI: `Test/run_v3_skill_transition_graph.py`
- default transition report: `SkillRegistry/v3_skill_transition_graph_report.json`
- default composition readiness report: `SkillRegistry/v3_composition_readiness_report.json`
- GDPVal and web-source batch runners can generate these reports with `--build-transition-graph`
- web-source runners can now use `--calibration-only` to generate graph diagnostics and transition reports while skipping persistent registry updates
- the graph builder uses local `SkillTraceEdge` records when available, and deterministic adjacent-candidate fallback when old extraction outputs have no trace edges
- transition reports now include `edge_scope_counts`, `registry_mapped_edge_count`, and `candidate_local_edge_count`
- `edge_scope=candidate_local` means at least one endpoint is not mapped to a persistent `SkillRegistryEntry`; this is expected for calibration-only outputs and should not be treated as persistent transition evidence
- no `possible_successors` list is written into `SkillRegistryEntry`
- no registry schema migration, inactive flag, or quarantine field is introduced

The first graph reports include placeholders for future feedback:

- `success_count`
- `failure_count`

These are intentionally not updated yet because Pipeline B task generation and quality feedback are not in this stage.

### Motif-Based Task Subgraphs

Pipeline B should not only sample chains. Many realistic GDPVal-style tasks are trees or DAG-like skill-resource graphs.

Recommended initial motifs:

- `fan_in_reconciliation`: several evidence paths converge into one reconciliation or conclusion
- `policy_application`: extract a rule or policy, then apply it to transactions or cases
- `exception_escalation`: detect exception, classify severity, and propose or document response
- `cross_check_validation`: use independent evidence paths to validate the same answer
- `evidence_to_deliverable`: synthesize facts and judgments into a workbook, memo, report, checklist, or narrative

The undirected task constraint graph may contain cycles, but the executable solve plan should still be staged and acyclic. Cycles should usually appear as validation or consistency constraints rather than impossible directed dependencies.

Current motif implementation:

- `SkillMotifHint` records motif type, candidate IDs, evidence block IDs, confidence, reason codes, and summary
- LLM extraction prompt now asks for top-level JSON with `candidates`, `trace_edges`, and `motif_hints`
- old candidate-only outputs remain valid; trace and motif lists default to empty
- mock extraction emits deterministic typed resources and simple local trace/motif hints for smoke testing
- `v3_skill_graph_diagnostics.py` emits `graph_extraction_diagnostics.json` to check typed resource coverage, trace edge coverage, motif coverage, and invalid graph references
- diagnostics are written automatically by extractor CLIs and batch runners, and can be regenerated with `Test/run_v3_skill_graph_diagnostics.py`
- calibration summaries across multiple extraction directories can be generated with `Test/run_v3_graph_calibration_report.py`
- current GDPVal accountants offline graph smoke produced 7 transition edges and 1 motif hint
- current web-source reuse batch with graph enabled produced 9 transition edges and 3 motif hints
- first real DeepSeek graph smoke produced typed resources and a motif but no trace edges; diagnostics correctly flagged `multi_candidate_without_trace_edges`
- after tightening the trace-edge prompt, a second DeepSeek graph smoke produced 3 candidates, 11 typed resources, 2 trace edges, 1 motif hint, and no diagnostics warnings
- current aggregate calibration report over public smoke outputs plus old web-source batches shows that old batches lack typed resources, trace edges, and motif hints; this is expected because those extra fields did not exist when they were generated
- after explicit user approval, real GDPVal prompt-only graph calibration succeeded on the `Accountants and Auditors` package:
  - 10 candidates
  - 20 typed resources
  - 5 trace edges
  - 1 motif hint
  - no graph diagnostics warnings
  - 8 accepted candidates and 2 revise candidates
  - transition graph produced 2 caution edges and 3 blocked edges
- web-source graph calibration now succeeds across all 3 default topics:
  - `audit_evidence_reconciliation`: 5 candidates, 10 typed resources, 3 trace edges, 2 motif hints
  - `internal_control_testing`: 8 candidates, 16 typed resources, 7 trace edges, 2 motif hints
  - `compliance_documentation_review`: 5 candidates, 14 typed resources, 4 trace edges, 2 motif hints
  - all three outputs have no graph diagnostics warnings, `registry_update_skipped=true`, and zero registry entry delta
- aggregate graph calibration over 9 extraction dirs now reports 51 candidates, 80 typed resources, 21 trace edges, and 9 motif hints; remaining warnings are concentrated in old pre-graph web-source outputs
- aggregate graph calibration now also distinguishes `graph_calibration`, `graph_capable`, and `pre_graph_or_legacy` artifacts, and separates `warning` from `attention` severity
- the LLM prompt now asks motif hints to cover the relevant candidate subset for a local workflow, because motif count alone can hide narrow motif coverage
- the transition graph now allows source-local `resource_compatible` trace evidence to produce a cautious edge when deterministic type matching is still incomplete; this is a soft prior, not a verified dependency

### Pipeline A To B Handoff Objects

Pipeline A now has report-only handoff artifacts for a minimal Pipeline B prototype:

- handoff document: `docs/handoffs/PIPELINE_A_TO_B_HANDOFF_2026-06-30.md`
- seed set report: `SkillRegistry/v3_pipeline_b_seed_set_report.json`
- calibration admission report: `SkillRegistry/v3_calibration_registry_admission_report.json`

The seed set report selects a conservative first sampling slice:

- 20 selected skills
- all selected skills are `sample_ready`
- selected motif counts: 12 `policy_application`, 8 `evidence_to_deliverable`, 7 `cross_check_validation`, and 5 `fan_in_reconciliation`

The calibration admission report reviews accepted graph calibration candidates without mutating the registry:

- 15 accepted candidates reviewed
- 14 `recommend_admit`
- 1 `merge_existing`

These reports do not introduce a new registry schema. They are decision aids for Pipeline B and for a later explicit registry admission step.

### Pipeline A Completion Reassessment

Current Pipeline A has a strong node-level MVP:

- source collection works for GDPVal prompt-only and Serper web-source batches
- LLM extraction, deterministic review, persistent registry update, audit, calibration, and sampling readiness all exist
- registry has 66 entries, with 30 currently `sample_ready`, 7 `sample_with_caution`, and 29 `exclude_until_revised`

Pipeline A is not yet complete as a compositional substrate for Pipeline B:

- typed resource ports now exist in schema and extraction prompt; early real LLM smoke shows usable resources, but batch-scale quality still needs calibration
- web-source graph calibration has a safe non-mutating path through `--calibration-only`, so old graph-poor web-source outputs can be compared with tightened-prompt outputs before any registry update decision
- transition priors now exist as per-run graph reports, but not yet as a persistent accumulated transition store
- source traces can encode local relations; tightened prompt can elicit trace edges in smoke tests, while old outputs mostly rely on adjacent-candidate fallback
- composition readiness can label graph roles, but motif-level sampling policy is not yet implemented
- no feedback loop yet updates transition weights from generated task quality

Updated completion estimate:

- Pipeline A node-level MVP: about 85%
- Pipeline A scalable registry governance: about 65-70%
- Pipeline A composable graph layer: about 45%
- Pipeline A as a substrate for Pipeline B: about 70%

Current recommendation: begin a minimal Pipeline B prototype using the seed set report, while keeping Pipeline A graph calibration and registry admission report-first.

## Object 1: SemanticSkill

`SemanticSkill` should be execution-agnostic. It does not commit to exact files, rows, operators, or final rubric wording.

It should capture:

- capability meaning
- semantic input/output contracts
- hidden challenge intent
- common business contexts
- assembly hints

Example:

```json
{
  "skill_id": "infer_implicit_currency",
  "skill_name": "Infer Implicit Currency",
  "skill_type": "reasoning",
  "version": "2.0",
  "domain_tags": ["finance", "audit", "reporting"],
  "capability_tags": ["currency_inference", "cross_source_normalization"],
  "difficulty_tags": ["multi_source", "implicit_business_rule"],
  "input_contract": {
    "requires_semantics": [
      "Financial:LocalizedAmount",
      "Dimension:Jurisdiction"
    ],
    "optional_semantics": [
      "Reference:ExchangePolicy"
    ]
  },
  "output_contract": {
    "provides_semantics": [
      "Financial:NormalizedAmountUSD"
    ]
  },
  "semantic_intent": {
    "goal": "Infer the correct transaction currency from business context and normalize monetary values into a shared reporting currency.",
    "business_meaning": "Amounts may be recorded without explicit currency symbols and must be interpreted from location, source system, or reporting conventions.",
    "hidden_difficulty": "The candidate should discover the missing currency cues without being explicitly instructed to clean them."
  },
  "usage_priors": {
    "common_scenarios": [
      "cross-border revenue consolidation",
      "tour accounting",
      "regional sales reporting"
    ],
    "common_deliverables": [
      "profit and loss report",
      "reconciliation workbook"
    ],
    "common_traps": [
      "implicit currency",
      "mixed formatting",
      "partial exchange-rate references"
    ]
  }
}
```

## Object 2: TaskBlueprint

`TaskBlueprint` is the concrete compiled task plan. It binds semantic skills to:

- scenario framing
- concrete files and sheets
- trap injection
- deliverable requirements
- golden-run execution requirements

Current finance prototype direction:

- template family: `financial_workbook_rollforward`
- style: GDPVal-like free deliverable generation from realistic evidence files
- not output-template completion by default
- not raw multi-ledger reconstruction from scratch

Example:

```json
{
  "blueprint_id": "bp_financial_audit_0001",
  "template_family": "financial_workbook_rollforward",
  "task_metadata": {
    "sector": "Financial Audit",
    "occupation": "Senior Auditor",
    "scenario_title": "2024 Fall Music Tour Reconciliation",
    "task_goal": "Produce a consolidated cross-source profit and loss report for executive review.",
    "difficulty_level": "medium"
  },
  "selected_skills": [
    "load_multi_source_financials",
    "infer_implicit_currency",
    "handle_missing_tax_rate",
    "categorize_operating_expense",
    "aggregate_source_level_pnl"
  ],
  "scenario_spec": {
    "role": "You are the finance lead supporting a post-period audit review.",
    "business_context": "The client operated an international music tour and prepared a partially structured audit workbook with separate tabs for tour-manager revenue, withholding-tax assumptions, and production-company costs.",
    "time_context": "Reporting is being completed in January 2025 for an as-of date of December 31, 2024.",
    "tone": "professional, business-realistic, non-tutorial"
  },
  "data_spec": {
    "reference_files": [
      {
        "file_name": "fall_music_tour_ref_file.xlsx",
        "file_role": "source_data",
        "sheet_specs": [
          {
            "sheet_name": "Inc_Costs_Tracked_by_Tour_Mgr",
            "columns": [
              {"name": "Line_Type", "semantic_type": "free_text_description"},
              {"name": "Tour_Date", "semantic_type": "date"},
              {"name": "City", "semantic_type": "location_city"},
              {"name": "Country", "semantic_type": "location_country_compact"},
              {"name": "Gross_Revenue", "semantic_type": "localized_amount"}
            ],
            "row_count_target": 7
          },
          {
            "sheet_name": "Assump_Withholding_Tax",
            "columns": [
              {"name": "Country", "semantic_type": "location_country_compact"},
              {"name": "Withholding_Tax_Rate", "semantic_type": "tax_rate"}
            ],
            "row_count_target": 6
          }
        ]
      },
      {
        "file_name": "production_company_costs.xlsx",
        "file_role": "source_data",
        "sheet_specs": [
          {
            "sheet_name": "Costs_Tracked_by_Production_Co",
            "columns": [
              {"name": "Cost_Category", "semantic_type": "account_name"},
              {"name": "Cost_Item", "semantic_type": "free_text_description"},
              {"name": "Amount_USD", "semantic_type": "amount"}
            ],
            "row_count_target": 14
          }
        ]
      }
    ],
    "data_relationships": [
      {
        "relation_type": "lookup",
        "left": "fall_music_tour_ref_file.xlsx:Inc_Costs_Tracked_by_Tour_Mgr.Country",
        "right": "fall_music_tour_ref_file.xlsx:Assump_Withholding_Tax.Country"
      }
    ]
  },
  "trap_spec": [
    {
      "trap_id": "trap_implicit_currency_01",
      "source_skill_id": "infer_implicit_currency",
      "trap_type": "implicit_currency",
      "injection_target": {
        "file_name": "fall_music_tour_ref_file.xlsx",
        "sheet_name": "Inc_Costs_Tracked_by_Tour_Mgr",
        "columns": ["Gross_Revenue"]
      },
      "injection_policy": {
        "pattern": "mixed_local_currency_without_header_signal",
        "severity": "medium",
        "affected_row_count": 3
      },
      "expected_solver_behavior": "Infer currency from geographic context and avoid reporting mixed-currency totals."
    },
    {
      "trap_id": "trap_missing_tax_rate_01",
      "source_skill_id": "handle_missing_tax_rate",
      "trap_type": "reference_omission",
      "injection_target": {
        "file_name": "fall_music_tour_ref_file.xlsx",
        "sheet_name": "Assump_Withholding_Tax",
        "columns": ["Withholding_Tax_Rate"]
      },
      "injection_policy": {
        "pattern": "omit_one_jurisdiction",
        "severity": "medium",
        "affected_entities": ["Germany"]
      },
      "expected_solver_behavior": "Detect the missing reference and resolve it using business logic or defensible assumptions."
    }
  ],
  "deliverable_spec": [
    {
      "file_name": "fall_music_tour_output.xlsx",
      "file_role": "final_deliverable",
      "requirements": [
        "must include header 'As of 12/31/2024'",
        "must present Tour Manager, Production Company, and Total columns",
        "must compute gross revenue, withholding tax, total costs, and net income"
      ]
    }
  ],
  "golden_plan": {
    "required_intermediate_states": [
      "currency_resolution_mapping",
      "tax_rate_resolution",
      "expense_bucket_mapping",
      "source_level_net_revenue",
      "net_income_totals"
    ],
    "required_final_checks": [
      "deliverable file existence",
      "format compliance",
      "net revenue totals",
      "expense totals",
      "net income totals"
    ]
  }
}
```

## Object 3: TrainingAnnotation

`TrainingAnnotation` should tell us what the sample teaches and how to supervise it.

It should include:

- primary and secondary capability labels
- final outcome checks
- intermediate reasoning targets
- expected failure modes
- rubric projection

Example supervision style:

- final workbook totals match the golden run
- required workbook exists with correct filename
- implicit currency is resolved correctly
- missing tax-rate assumption is handled explicitly
- expense lines are mapped into the intended reporting taxonomy

## Object 4: GoldenRun

`GoldenRun` is the teacher-mode canonical solution package. It is not just a final score.

It should produce:

- canonical intermediate states
- canonical final totals
- trap-resolution log
- grading anchors consumable by evaluation code

Current finance prototype emits:

- `golden_intermediate_values.json`
- `golden_grading_anchors.json`
- `golden_run_log.json`

Important design point:

- `GoldenRun` is where result-based supervision becomes reliable
- it should expose enough structure that rubric generation is not tied to the prompt wording

## Current Finance Prototype

The current prototype intentionally moved closer to GDPVal finance tasks:

- one structured reference workbook for tour manager data and tax assumptions
- one structured workbook for production-company costs
- one final workbook deliverable
- free workbook generation framing instead of free-form reporting plus PDF summary

This is preferable for training because:

- the business task is easier to understand from the prompt
- the file structure is more realistic and more reusable
- the final deliverable stays open-ended in the same way as GDPVal finance tasks
- supervision can focus on workbook totals and key reasoning steps

## GDPVal Findings

We verified the current understanding against the original HuggingFace dataset `openai/gdpval`, not only local cached workspace files.

Current evidence summary:

- GDPVal has 220 rows in total
- many tasks have `0` reference files, so GDPVal does not assume an input-file-first workflow
- many tasks have exactly `1` deliverable file, but multi-deliverable tasks also exist
- deliverables span multiple file types including `.xlsx`, `.pdf`, `.docx`, and `.pptx`
- there are `0` rows where reference and deliverable filenames overlap exactly, which supports the interpretation that outputs are generally newly created artifacts rather than in-place completions

For `Accountants and Auditors` samples specifically:

- there are 5 tasks
- deliverables are mostly `.xlsx`, with one case that also includes `.pdf`
- at least two prompts explicitly say things like `Create a new Excel document` or `Create a new spreadsheet`
- the finance-tour GDPVal sample (`7b08cd4d-df60-41ae-9102-8aaa49306ba2`) explicitly asks the model to create a new Excel document named `Fall Music Tour Output.xlsx`

Implication for V2:

- the core target is not "output template completion"
- the core target is "given realistic evidence files and a realistic business request, generate a new professional deliverable file"
- validation must therefore tolerate layout variation while still checking business-critical outcomes
- GDPVal-style supervision is often highly structural and numeric at the same time: file type, worksheet presence, headers, key rows, exact totals, and absence of spreadsheet errors can all appear in the same rubric

Local analysis artifact:

- `Test/v2_outputs/gdpval_analysis/summary.json`
- `Test/v2_outputs/gdpval_analysis/summary.md`

## Current Progress

The V2 finance prototype has already completed these steps:

1. replaced old operator-heavy task design with semantic-skill-driven assembly
2. implemented `TaskBlueprint`, `TrainingAnnotation`, and `GoldenRun` based generation flow
3. built a finance/audit prototype centered on the Fall Music Tour scenario
4. exported the prototype into rw-task-compatible case format
5. added static quality scoring for generated finance tasks
6. validated the crucial GDPVal-style assumption that deliverables can be newly generated files rather than template completions
7. upgraded the finance prototype supervision from aggregate totals to GDPVal-style mixed checks over workbook structure, line items, grouped subtotals, overall totals, and spreadsheet-error absence
8. expanded the finance prototype into a 5-case variant batch with distinct underlying reference-file profiles, distinct golden outputs, and rubric sizes in the 35-36 item range

Current prototype status:

- input side: closer to GDPVal than before
- output side: conceptually aligned with GDPVal free-generation behavior
- supervision side: materially closer to GDPVal, though still missing executable cell-level verification
- batch generation side: now supports multiple finance variants instead of a single canonical case
- evaluation side: partly operational, with some model/provider instability still unresolved

## Early Evaluation Findings

We have now run real rw-task evaluations on the current finance cases, not only static inspection.

Current takeaways:

- the provider environment is unstable across model families, so "probe success" is not enough to trust a model for full task evaluation
- `gemini-3-pro-preview` can fail because it triggers external search during the task and the search backend returns an error
- some GPT-family runs can appear responsive on a tiny probe but still stall or fail to finish cleanly in a long multi-turn task
- `claude-3-7-sonnet-latest` and `deepseek-v3.2` currently look like the most usable models for iterative dataset validation in this environment

More importantly, the finance task is already showing a meaningful error pattern:

- several models successfully produce a professional-looking workbook
- several models correctly aggregate production-company costs
- several models make a defensible assumption for the missing Germany withholding-tax rate
- but multiple models still fail the same core step: inferring that source revenue is in local currency and converting it into the shared reporting currency before final aggregation

This is useful because it suggests that:

- the current task is not trivially solved by spreadsheet formatting ability alone
- the implicit-currency skill is currently a stronger discriminator than the missing-tax-rate skill
- the next round of task design should preserve this business-realistic ambiguity while making evaluation more executable

At the current stage, the main scoring signal is:

- models often get structure and expense taxonomy mostly right
- models often miss cross-jurisdiction currency normalization
- therefore score separation is driven primarily by numeric business reasoning rather than by cosmetic workbook layout

## Pipeline View

The V2 project should now be treated as a **data production pipeline**, not just a collection of prototype tasks.

From a systems perspective, the pipeline has six layers:

1. `SemanticSkill` extraction layer
2. `TaskBlueprint` assembly layer
3. reference-file generation layer
4. `GoldenRun` teacher-solution layer
5. dataset export and evaluation-adapter layer
6. quality-control and filtering layer

This framing matters because the long-term goal is not to handcraft one good finance task. The goal is to repeatedly produce many GDPVal-style training tasks with:

- stable semantics
- realistic evidence files
- reliable supervision
- low manual review cost
- measurable model-separation value

## Layer Responsibilities

### 1. SemanticSkill extraction layer

This layer should answer only:

- what capability is being tested
- what semantic inputs are required
- what semantic outputs are expected
- what hidden challenge is intended

This layer should **not** decide:

- exact workbook schema
- exact file names
- exact row counts
- exact rubric wording
- exact data-generation operators

Its job is to keep the capability inventory reusable across domains and task templates.

### 2. TaskBlueprint assembly layer

This layer is the main scenario-construction layer.

It should decide:

- task role and business framing
- selected skill combination
- deliverable type
- evidence package structure
- hidden traps and challenge mix
- target difficulty and realism profile

This is the right place for stronger LLM involvement, because this layer benefits from flexible composition and realistic scenario writing.

### 3. Reference-file generation layer

This layer turns the blueprint into concrete evidence files.

Its job is to produce:

- realistic spreadsheets, documents, or other inputs
- business-plausible values and inconsistencies
- traceable source structure for later verification

Current macro judgment:

- this layer should be **code-led by default**
- LLMs may help with realism, naming, wording, and document-style variation
- but the numeric backbone should remain deterministic enough that `GoldenRun` can trust it

In other words:

- use code for structured numeric generation
- use LLMs as controlled assistants for semantic enrichment, not as the sole source of truth

### 4. GoldenRun teacher-solution layer

This layer is the core supervision engine.

Its job is to produce:

- canonical intermediate states
- canonical final outputs
- trap-resolution records
- grading anchors

Macro principle:

- this layer should be as deterministic as possible
- it is the main defense against supervision drift
- it should not depend on prompt wording or one specific candidate layout

### 5. Dataset export and evaluation-adapter layer

This layer packages tasks for two different downstream uses:

- training-data export
- external evaluation export such as rw-task / GDPVal-style runners

The same core sample should ideally support both:

- a training-facing representation
- an evaluation-facing representation

This avoids building two disconnected pipelines.

### 6. Quality-control and filtering layer

This layer decides whether a generated sample is actually worth keeping.

It should answer:

- is the schema complete
- are the files internally consistent
- does `GoldenRun` execute cleanly
- is the rubric verifiable
- does the task appear too trivial, too noisy, or too brittle
- does the task create meaningful model separation

This layer is what turns a generator into a dataset factory.

## Layer Interfaces

The most important engineering priority now is to make the boundaries between layers explicit.

The intended contracts are:

- `SemanticSkill` -> `TaskBlueprint`
  - passes semantic capability requirements and assembly hints
- `TaskBlueprint` -> reference-file generation
  - passes concrete file specs, traps, and deliverable plan
- reference-file generation -> `GoldenRun`
  - passes concrete evidence files and scenario metadata
- `GoldenRun` -> `TrainingAnnotation`
  - passes executable intermediate states and final grading anchors
- dataset package -> export adapters
  - passes prompt, files, deliverables, rubric, and metadata
- quality-control layer -> final dataset
  - passes only accepted samples forward

Without these contracts, the system risks collapsing back into tightly coupled prompt-and-rubric bundles.

## Automation Strategy

The right macro question is not "should we use code or LLMs?" in general.

The right question is "which layer benefits from flexibility, and which layer needs determinism?"

Current recommended allocation:

- `SemanticSkill` extraction: LLM-heavy
- `TaskBlueprint` assembly: hybrid, with meaningful LLM involvement
- reference-file generation: code-heavy, with optional LLM assistance
- `GoldenRun`: code-heavy and deterministic
- export adapters: code-heavy
- quality control: code-first, with selective LLM review only for ambiguous cases

This allocation preserves realism without losing supervision reliability.

## Quality Funnel

Not every generated sample should go through full model evaluation.

The intended quality funnel is:

1. schema validation
2. reference-file sanity checks
3. `GoldenRun` execution check
4. rubric / grading-anchor consistency check
5. static quality scoring
6. limited real-model evaluation on a filtered subset
7. final keep / revise / discard decision

This is important for scale.

If full rw-task evaluation is run on every sample:

- generation becomes too expensive
- provider instability dominates research velocity
- debugging becomes noisy

If full rw-task evaluation is used only at the end of the funnel:

- we can scale sample generation much more cheaply
- we can reserve expensive evaluation for the most promising candidates

## Accepted Sample Checklist

Before a generated sample is allowed into expensive evaluation or the retained training pool, it should satisfy a minimal acceptance checklist.

The checklist should be enforced by code, not only by manual inspection.

Current required checks are:

1. required case files exist
2. required `golden_run` artifacts exist
3. `TaskBlueprint`, `TrainingAnnotation`, `GoldenRun`, and dataset shell all parse successfully
4. cross-file IDs are linked correctly
5. reference files on disk match the blueprint manifest
6. required intermediate states promised by the blueprint are present in `golden_intermediate_values.json`
7. rw-task export exists and is linked to the same task identity

This checklist is now implemented as a first-pass quality gate in:

- `v2_quality_gate.py`
- `Test/run_v2_quality_gate.py`

For batch-level use, the current finance prototype also has a funnel runner:

- `Test/run_v2_batch_funnel.py`

Its purpose is to combine:

1. structural gate pass/fail
2. static quality score
3. next-step routing

So the pipeline can distinguish between:

- samples that are structurally broken
- samples that are structurally valid but weak
- samples that are strong enough to justify expensive real-model evaluation

This is intentionally different from static quality scoring:

- the quality gate asks "is this sample structurally valid and pipeline-safe?"
- the quality scorer asks "is this sample likely to be a good training/evaluation task?"

Both are needed, but the gate should run first.

## Failure Modes at the Pipeline Level

The most important macro risks are no longer single-task spreadsheet bugs.

They are:

- `SemanticSkill` entries becoming too vague to assemble reliably
- `TaskBlueprint` becoming too template-specific and losing reuse value
- reference-file generation becoming unrealistic or overly synthetic
- `GoldenRun` becoming too teacher-specific and hard to generalize
- rubrics becoming descriptive but not executable
- quality control depending too much on unstable provider-side evaluation

These are the pipeline-level risks we should optimize against.

## Current Bottleneck

The current bottleneck is not "can we make one finance task harder?"

The current bottleneck is:

- can we define a repeatable, low-friction path from semantic skill inventory to accepted high-quality dataset samples

That means the next engineering value comes more from:

- contract hardening
- funnel design
- verification design
- modularization of generation layers

than from additional micro-tuning of one candidate workbook.

## Status on 2026-06-26

As of June 26, 2026, the V2 finance line has already moved beyond a pure prototype sketch.

What has been completed:

1. the old operator-heavy direction has been replaced with the `SemanticSkill` -> `TaskBlueprint` -> reference-file generation -> `GoldenRun` -> export flow
2. the finance/audit domain has a working end-to-end prototype that generates:
   - reference spreadsheets
   - prompt and golden prompt
   - `TrainingAnnotation`
   - `GoldenRun` artifacts
   - rw-task-compatible exports
3. GDPVal alignment has been verified using the original HuggingFace dataset, especially the fact that many tasks require creating a new deliverable file rather than filling an output template
4. finance supervision has been upgraded from coarse aggregate totals to mixed structure-plus-numeric checks
5. a 5-case finance batch has been generated and statically scored
6. a first-pass `quality gate` has been implemented to check structural completeness and pipeline linkage before expensive evaluation
7. a batch-level funnel runner has been implemented to combine:
   - structural gate pass/fail
   - static quality score
   - next-step routing
8. real rw-task evaluations have already been run on selected finance cases, which confirmed that the current tasks do create meaningful failure patterns rather than only formatting differences

What has been learned:

- the pipeline itself is now much more stable than before
- the main separator in the current finance tasks is cross-jurisdiction currency normalization, not spreadsheet formatting
- provider-side instability is real, so expensive model evaluation should remain late in the funnel
- the current finance cases are mostly **structurally valid**, but still not strong enough on average to be automatically prioritized for expensive rw-task evaluation

Current evidence from the funnel:

- all 5 current finance batch cases pass the structural quality gate
- none of the 5 current finance batch cases yet cross the static threshold for "prioritize for rw-task evaluation"
- the immediate weakness is therefore not pipeline breakage, but sample-quality uplift

In short:

- pipeline health: improved substantially
- sample validity: already good
- sample quality: improving, but still the main bottleneck
- scaling readiness: close for deterministic layers, not yet ready for indiscriminate large-scale generation

## Generation Workflow

The V2 generation flow is:

1. select semantic skills
2. compile a `TaskBlueprint`
3. generate reference files from the blueprint
4. run `GoldenRun` to compute canonical outputs
5. assemble `TrainingAnnotation`
6. export dataset package and rw-task-compatible case

## Current Open Questions

The next major improvements are:

- make free-generation deliverables easier to verify without assuming a fixed workbook layout
- use stronger models for assembly and validation while keeping teacher artifacts deterministic
- compare generated tasks with GDPVal samples using the rw-task evaluation stack
- decide whether the missing-tax-rate trap should remain a secondary skill while implicit-currency reasoning stays the primary separator
- decide how much layout freedom should be tolerated before verification quality drops too much
- formalize layer-by-layer contracts so the pipeline scales beyond the finance prototype
- decide what the minimal "accepted sample" checklist is before expensive evaluation is allowed

## Near-Term Plan

The next execution plan is:

1. formalize the V2 pipeline as a layered production system with explicit interfaces and acceptance criteria
2. implement the quality funnel so cheap deterministic checks happen before expensive model evaluation
3. strengthen the executable verification contract between reference-file generation, `GoldenRun`, and rubric export
4. keep the finance prototype as the first domain, but use it mainly to validate pipeline design rather than endlessly hand-tuning one task
5. after the funnel is stable, expand the finance batch and then consider additional domains
6. only after the pipeline is stable, revisit where more LLM involvement is actually worth the added variance

## Next Concrete Plan

The next practical step should not be another round of ad hoc model testing.

The next practical step should be to improve the **quality-improvement loop** for structurally valid samples.

That loop should be:

1. inspect funnel outputs
2. identify why a sample is rated as `revise_before_eval`
3. map each weak score component back to:
   - blueprint design
   - reference-file generation
   - golden supervision design
   - prompt framing
4. encode the fix into the generator instead of patching individual outputs
5. regenerate the batch and rerun the same funnel

So the immediate engineering plan is:

1. define a finance-specific optimization playbook for low-scoring but gate-passing samples
2. connect each weak static-quality component to explicit generator-side interventions
3. regenerate the 5-case finance batch after those interventions
4. rerun the batch funnel and compare before/after quality distributions
5. only then send the improved subset into another round of rw-task evaluation

## Finance Optimization Playbook

The first version of the finance optimization playbook has now been implemented.

Files:

- `v2_finance_optimization.py`
- `Test/run_v2_finance_optimization_playbook.py`

Inputs:

- `Test/v2_outputs/finance_batch_01/quality_report.json`
- `Test/v2_outputs/quality_gate_reports/finance_batch_01_funnel_report.json`

Outputs:

- `Test/v2_outputs/optimization_reports/finance_batch_01_optimization_playbook.json`
- `Test/v2_outputs/optimization_reports/finance_batch_01_optimization_playbook.md`

Current diagnosis:

- all 5 finance cases pass the structural quality gate
- 3 cases are primarily limited by `result_supervision`
- 2 cases are primarily limited by `challenge_balance`

Current recommended actions:

1. `improve_result_supervision`
   - target layer: `GoldenRun + rw_task_adapter`
   - add more executable worksheet-level grading anchors
   - make show-level FX-normalized revenue, country-level withholding, source-level subtotals, and formula-error checks easier to verify

2. `rebalance_financial_profile`
   - target layer: `FileGenerator finance profiles`
   - tune revenue and cost profiles so net margins remain in the preferred challenge band
   - adjust generated business data rather than patching prompts after generation

This changes the workflow from:

- generate cases
- inspect scores manually
- decide informally what to fix

to:

- generate cases
- run quality gate
- run static scoring
- generate optimization playbook
- modify generator-side logic
- regenerate and compare quality distribution

This is the beginning of a real feedback loop for dataset construction.

## First Optimization Pass

The first generator-side optimization pass has been completed.

Implemented changes:

1. `GoldenRun` now emits explicit `executable_verification_targets`
   - show-level FX-normalized revenue
   - show-level withholding
   - country-level withholding
   - expense category totals
   - source-level P&L totals
   - spreadsheet error absence

2. `FinanceTaskQualityScorer` now gives `result_supervision` credit for:
   - line-item numeric anchors
   - group-total numeric anchors
   - source-level and overall P&L anchors
   - executable verification target coverage

3. `FileGenerator` finance profiles were rebalanced for the two previously high-margin cases
   - profile 2 production costs were increased to bring net margin close to 10%
   - profile 4 production costs were increased to bring net margin close to 10%

4. The challenge-balance scorer was adjusted for this finance template
   - the previous metric over-penalized tasks with one revenue source and one cost source
   - the revised metric includes expense pressure relative to revenue

Before this pass:

- all 5 finance cases passed the structural gate
- static scores were around 70.15-71.75
- 3 cases were weakest on `result_supervision`
- 2 cases were weakest on `challenge_balance`
- all cases were routed to `revise_before_eval`

After this pass:

- all 5 finance cases still pass the structural gate
- all 5 finance cases score 78.75
- all 5 finance cases are routed to `keep_in_training_pool`
- `result_supervision` improved to 85.0
- `challenge_balance` improved to 80.0
- the new weakest component is `structural_complexity`

Interpretation:

- the first quality-improvement loop worked
- supervision and financial balance are no longer the main blockers
- the next useful improvement is controlled structural richness, not more micro-tuning of numeric traps

Next optimization target:

- add one small, realistic dependency only if it improves the task's business structure
- candidate examples:
  - a small FX policy table
  - a management adjustment table
  - a reconciliation note sheet
  - a simple source-control schedule for excluded or duplicate rows

This should be done carefully. Adding files or sheets only for score inflation would make the task less realistic.

## Second Optimization Pass

The second optimization pass added one realistic structural dependency: an attached FX policy workbook.

Implemented changes:

1. `TaskBlueprint` now includes `fx_policy.xlsx`
   - sheet: `FX_Policy`
   - fields: `Currency_Code`, `Reporting_Currency`, `FX_To_USD`, `Effective_Date`

2. the prompt now explicitly tells the candidate to use the attached FX policy for local-currency revenue normalization

3. `FileGenerator` now emits `fx_policy.xlsx` as part of the reference-file package

4. `GoldenRun` now reads FX rates from `fx_policy.xlsx`
   - this replaces hardcoded FX application inside the teacher run
   - `fx_policy_table` is emitted as a required intermediate state

5. executable verification targets now include `fx_policy_application`

6. prompt-realism scoring now recognizes GDPVal-style prompt structure
   - role
   - engagement context
   - objective
   - working expectations
   - required deliverables
   - quality bar
   - multi-file reference dependency

After this pass:

- all 5 finance cases pass the structural quality gate
- all 5 finance cases score 83.75
- all 5 finance cases are routed to `prioritize_for_rw_task_eval`
- `structural_complexity` improved to 82.25
- `prompt_realism` improved to 92.0
- `result_supervision` remains 85.0
- `challenge_balance` remains 80.0
- the weakest remaining component is `reasoning_depth` at 79.5

Interpretation:

- the finance batch is now strong enough for another limited rw-task evaluation round
- further static optimization is less urgent than validating whether these improved tasks actually separate real models better
- the next meaningful evidence should come from model runs, not another static-score-only iteration

Recommended next evaluation subset:

- run the top 1-2 current finance cases through `claude-3-7-sonnet-latest`
- run the same subset through `deepseek-v3.2`
- optionally test one stronger but less stable provider model only after the stable baseline is collected

The goal is to compare the new FX-policy version against the earlier task behavior:

- old static score: roughly 70-72
- first pass: 78.75
- second pass: 83.75
- expected dynamic question: does this produce better or clearer model separation?

## Third Optimization Pass

The second-pass dynamic evaluation showed that the task's main remaining ambiguity was not FX conversion, but the missing Germany withholding-tax rate.

Observed behavior before this pass:

- `claude-3-7-sonnet-latest` improved to 62/77 after the FX-policy addition
- `deepseek-v3.2` improved to 55/77 after the FX-policy addition
- both models used `fx_policy.xlsx` correctly
- both models still struggled with Germany withholding tax because `Assump_Withholding_Tax` intentionally omitted Germany
- the previous GoldenRun restored Germany from a hidden teacher default, which made exact grading less fair for training data

Design correction:

- keep the missing Germany value in `Assump_Withholding_Tax`
- add a realistic support sheet named `Tax_Policy_Notes` inside `fall_music_tour_ref_file.xlsx`
- include Germany's standard nonresident performer withholding rate of 15.825% in that support sheet
- require candidates to use supporting tax policy notes for incomplete withholding-tax assumptions
- make GoldenRun resolve missing tax rates from `Tax_Policy_Notes`, not from a hidden default

This preserves the intended challenge:

- the model still has to notice that the main tax assumption table is incomplete
- the model still has to perform cross-sheet fallback lookup
- exact grading is now grounded in visible input files rather than hidden teacher knowledge

Implemented changes:

1. `TaskBlueprint` includes a new `Tax_Policy_Notes` sheet in `fall_music_tour_ref_file.xlsx`
   - fields: `Jurisdiction`, `Policy_Topic`, `Resolved_Withholding_Tax_Rate`, `Source_Note`

2. `FileGenerator` emits the policy-note sheet while preserving the Germany omission in `Assump_Withholding_Tax`

3. `GoldenRun` now emits:
   - `tax_policy_note_lookup`
   - `tax_rate_resolution` with resolution basis `Tax_Policy_Notes`

4. executable verification targets now include `tax_policy_note_resolution`

5. the prompt now tells candidates to use supporting tax policy notes to resolve incomplete withholding-tax assumptions

Static validation after this pass:

- all 5 finance cases pass the structural quality gate
- all 5 finance cases have zero blocking issues and zero warnings
- all 5 finance cases remain at static score 83.75
- all 5 finance cases remain routed to `prioritize_for_rw_task_eval`

Dynamic validation after this pass:

- selected case: `TASK_374E0FBA`
- model: `claude-3-7-sonnet-latest`
- grader result: 77/77
- output log explicitly states that Germany WHT was resolved via `Tax_Policy_Notes` to 15.825%
- attempted model: `deepseek-v3.2`
- DeepSeek computed the key FX, withholding-tax, and net-income values correctly in the log, but did not finish writing the final workbook before the 5-minute local timeout

Interpretation:

- the tax ambiguity fix worked
- the task became fairer and more deterministic for training supervision
- the current single task is now too easy for Claude after the support note is added
- the current task can still stress long-horizon execution for slower models, so timeout/completion should be tracked separately from numeric reasoning correctness
- the next dataset-level goal is not to make this exact sample harder by hiding required data again, but to create a controlled difficulty ladder across multiple cases and models

Next recommended direction:

- run the same tax-note version on `deepseek-v3.2` to see whether the model gap remains
- add one additional reasoning dependency only after dynamic evidence shows the current batch no longer separates models
- likely next dependencies:
  - duplicate or excluded-row handling
  - management adjustment table
  - source-control tie-out schedule
  - reconciliation note that affects only one subset of rows

## Summary

The V2 schema is designed so that:

- skill extraction stays semantic
- task construction becomes richer and more flexible
- supervision is explicit and result-grounded
- the final dataset is suitable for training, not only benchmarking

