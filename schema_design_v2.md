# TaskGenerator V2 Schema Design

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
- style: GDPVal-like workbook completion
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
- workbook-completion framing instead of free-form reporting plus PDF summary

This is preferable for training because:

- the business task is easier to understand from the prompt
- the file structure is more realistic and more reusable
- the final deliverable is easier to validate
- supervision can focus on workbook totals and key reasoning steps

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

- add an explicit output-workbook skeleton so the task is even closer to GDPVal
- make rubric generation line-item-aware rather than generic source-metric-aware
- use stronger models for assembly and validation while keeping teacher artifacts deterministic
- compare generated tasks with GDPVal samples using the rw-task evaluation stack

## Summary

The V2 schema is designed so that:

- skill extraction stays semantic
- task construction becomes richer and more flexible
- supervision is explicit and result-grounded
- the final dataset is suitable for training, not only benchmarking
