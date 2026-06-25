# TaskGenerator V2 Schema Design

## Goal

Build a generation framework for GDPVal-style real-world tasks that is optimized for **training**, not only evaluation.

The key design shift is:

- `Skill` should represent **semantic capability units**
- `TaskBlueprint` should represent **one concrete task instance**
- `TrainingAnnotation` should represent **what the sample teaches and how it can be checked**

This separates:

1. reusable capability semantics
2. task-specific concretization
3. training/evaluation supervision

## Design Principles

### 1. Semantic skills must be execution-agnostic

A semantic skill should not directly contain:

- hardcoded file names
- low-level Python operator details
- rigid data generators
- final static rubric text

A semantic skill should contain:

- capability meaning
- typical prerequisites
- semantic outputs
- suitable business contexts
- hidden challenge intent

### 2. Task construction is a separate compilation step

The system should use LLMs during assembly to turn semantic skills into:

- realistic scenario framing
- concrete files and schemas
- trap instantiation
- deliverable requirements
- golden-run computation plan

### 3. Training supervision is richer than a final score

For training, each sample should ideally expose:

- capability labels
- concrete result checks
- important intermediate targets
- known failure modes

This is more useful than only storing a flat rubric string.

## Object 1: SemanticSkill

`SemanticSkill` is the reusable unit in the skill library.

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
  },
  "assembly_hints": {
    "preferred_task_roles": [
      "Financial Auditor",
      "Finance Lead",
      "Business Analyst"
    ],
    "preferred_evidence": [
      "country column",
      "city column",
      "reference FX table"
    ],
    "suggested_intermediate_artifacts": [
      "currency_assumption_mapping",
      "normalized_amount_column"
    ]
  }
}
```

### Notes

- `skill_type` can be `fact`, `reasoning`, `robustness`, `compliance`, or a small internal taxonomy you prefer.
- `input_contract` and `output_contract` replace the old idea that a skill must already know physical columns or exact files.
- `assembly_hints` are optional and help the task compiler, but they are still semantic rather than executable.

## Object 2: TaskBlueprint

`TaskBlueprint` is a task-specific compiled plan produced during assembly.

It is the bridge between semantic skills and actual files/prompts.

```json
{
  "blueprint_id": "bp_financial_audit_0001",
  "template_family": "cross_border_pnl",
  "task_metadata": {
    "sector": "Financial Audit",
    "occupation": "Senior Auditor",
    "scenario_title": "2024 Fall Music Tour Reconciliation",
    "task_goal": "Produce a consolidated cross-source profit and loss report for executive review.",
    "difficulty_level": "medium-high"
  },
  "selected_skills": [
    "load_multi_source_financials",
    "infer_implicit_currency",
    "handle_missing_tax_rate",
    "categorize_operating_expense",
    "aggregate_source_level_pnl",
    "export_formatted_workbook"
  ],
  "scenario_spec": {
    "role": "You are the finance lead supporting a post-period audit review.",
    "business_context": "The client operated an international music tour with revenues and costs captured by different teams and systems.",
    "time_context": "Reporting is performed in January 2025 for an as-of date of December 31, 2024.",
    "tone": "professional, business-realistic, non-tutorial"
  },
  "data_spec": {
    "reference_files": [
      {
        "file_name": "tour_manager_data.xlsx",
        "file_role": "source_data",
        "sheet_specs": [
          {
            "sheet_name": "Transactions",
            "columns": [
              {"name": "Receipt_ID", "semantic_type": "identifier"},
              {"name": "City", "semantic_type": "location_city"},
              {"name": "Country", "semantic_type": "location_country"},
              {"name": "Gross_Revenue", "semantic_type": "localized_amount"},
              {"name": "Expense_Amount", "semantic_type": "localized_amount"}
            ],
            "row_count_target": 150
          }
        ]
      },
      {
        "file_name": "production_ledger.xlsx",
        "file_role": "source_data",
        "sheet_specs": [
          {
            "sheet_name": "Ledger",
            "columns": [
              {"name": "Posting_Date", "semantic_type": "date"},
              {"name": "Account_Name", "semantic_type": "account"},
              {"name": "Debit_Amount", "semantic_type": "amount"},
              {"name": "Credit_Amount", "semantic_type": "amount"}
            ],
            "row_count_target": 400
          }
        ]
      },
      {
        "file_name": "tax_rates.xlsx",
        "file_role": "reference_table",
        "sheet_specs": [
          {
            "sheet_name": "Rates",
            "columns": [
              {"name": "Country", "semantic_type": "location_country"},
              {"name": "Withholding_Tax_Rate", "semantic_type": "tax_rate"}
            ],
            "row_count_target": 12
          }
        ]
      }
    ],
    "data_relationships": [
      {
        "relation_type": "lookup",
        "left": "tour_manager_data.xlsx:Transactions.Country",
        "right": "tax_rates.xlsx:Rates.Country"
      }
    ]
  },
  "trap_spec": [
    {
      "trap_id": "trap_implicit_currency_01",
      "source_skill_id": "infer_implicit_currency",
      "trap_type": "implicit_currency",
      "injection_target": {
        "file_name": "tour_manager_data.xlsx",
        "sheet_name": "Transactions",
        "columns": ["Gross_Revenue", "Expense_Amount"]
      },
      "injection_policy": {
        "pattern": "mixed_local_currency_without_header_signal",
        "severity": "medium",
        "affected_row_count": 20
      },
      "expected_solver_behavior": "Infer currency from geographic context and avoid reporting mixed-currency totals."
    },
    {
      "trap_id": "trap_missing_tax_rate_01",
      "source_skill_id": "handle_missing_tax_rate",
      "trap_type": "reference_omission",
      "injection_target": {
        "file_name": "tax_rates.xlsx",
        "sheet_name": "Rates",
        "columns": ["Withholding_Tax_Rate"]
      },
      "injection_policy": {
        "pattern": "omit_one_jurisdiction",
        "severity": "medium",
        "affected_entities": ["Netherlands"]
      },
      "expected_solver_behavior": "Detect the missing reference and resolve it using business logic or defensible assumptions."
    }
  ],
  "deliverable_spec": [
    {
      "file_name": "profit_and_loss_report.xlsx",
      "file_role": "final_deliverable",
      "requirements": [
        "must include header 'As of 12/31/2024'",
        "must present source-level totals",
        "must normalize revenue to USD"
      ]
    },
    {
      "file_name": "task_summary.pdf",
      "file_role": "final_deliverable",
      "requirements": [
        "must summarize reconciliation approach",
        "must mention any assumptions or anomalies"
      ]
    }
  ],
  "prompt_spec": {
    "visible_requirements": [
      "prepare a structured P&L report",
      "use the attached files",
      "report all revenues in USD",
      "provide an executive-ready workbook"
    ],
    "hidden_requirements": [
      "discover implicit currencies",
      "handle missing tax reference values",
      "avoid leaking intermediate solution steps into the prompt"
    ],
    "style_constraints": [
      "realistic business memo tone",
      "no explicit data-cleaning tutorial",
      "no trap disclosure"
    ]
  },
  "golden_plan": {
    "required_intermediate_states": [
      "currency_resolution_mapping",
      "tax_rate_resolution",
      "source_level_net_revenue",
      "source_level_total_expenses"
    ],
    "required_final_checks": [
      "net revenue totals",
      "expense totals",
      "net income totals",
      "deliverable file existence",
      "format compliance"
    ]
  }
}
```

### Notes

- `TaskBlueprint` is the right place for file names, schemas, and trap injection policies.
- This object can be generated by LLM plus rule-based validators.
- This object should become the main input to your file generator and prompt compiler.

## Object 3: TrainingAnnotation

`TrainingAnnotation` stores supervision signals for learning.

It can later be partially converted into evaluation-time rubric items, but it should be richer than a rubric.

```json
{
  "annotation_id": "ann_bp_financial_audit_0001",
  "blueprint_id": "bp_financial_audit_0001",
  "capability_profile": {
    "primary_capabilities": [
      "multi_source_reconciliation",
      "currency_inference",
      "tax_reasoning",
      "financial_aggregation"
    ],
    "secondary_capabilities": [
      "format_compliance",
      "robustness_to_missing_reference_data"
    ]
  },
  "supervision_targets": {
    "final_outcomes": [
      {
        "target_id": "final_pnl_totals",
        "target_type": "exact_or_tolerance_check",
        "description": "Validate final source-level and total P&L figures against the golden run."
      },
      {
        "target_id": "deliverable_presence",
        "target_type": "binary_check",
        "description": "Check that the required workbook and summary file are produced with correct names."
      }
    ],
    "intermediate_outcomes": [
      {
        "target_id": "currency_resolution",
        "target_type": "reasoning_check",
        "description": "Verify that implicit local amounts are interpreted using the correct jurisdictional cues."
      },
      {
        "target_id": "missing_tax_resolution",
        "target_type": "reasoning_or_robustness_check",
        "description": "Verify that the missing tax rate does not silently corrupt final calculations."
      }
    ]
  },
  "failure_modes": [
    {
      "failure_id": "fm_mixed_currency_sum",
      "description": "The model aggregates amounts before normalizing currencies."
    },
    {
      "failure_id": "fm_null_tax_propagation",
      "description": "A missing tax rate causes null propagation or skipped rows without acknowledgement."
    },
    {
      "failure_id": "fm_format_only_success",
      "description": "The report looks polished but contains wrong financial logic."
    }
  ],
  "rubric_projection": {
    "fact_checks": [
      "Final P&L totals match the golden run."
    ],
    "reasoning_checks": [
      "The model correctly infers implicit currencies from business context."
    ],
    "robustness_checks": [
      "The missing tax-rate omission does not break downstream calculations."
    ],
    "compliance_checks": [
      "Required deliverables exist and satisfy naming/format requirements."
    ]
  }
}
```

### Notes

- `TrainingAnnotation` is the natural home for result-based rubric generation.
- You can derive final evaluation rubrics from this object later.
- For training, this object also supports auxiliary losses or chain supervision if you ever want them.

## Object 4: GoldenRun Package

`GoldenRun` should be treated as a teacher-mode execution package used during task construction and dataset validation.

It is related to evaluation, but it is not identical to ordinary candidate evaluation.

Its role is to produce:

1. a standard deliverable bundle
2. intermediate ground-truth states
3. grading anchors for result-based evaluation
4. task-quality diagnostics

### Core Principle

The candidate-facing task and the golden task should share the same:

- reference files
- deliverable interface
- sandbox execution style

But they should differ in **information privileges**.

### Candidate mode vs Golden mode

`candidate_prompt`:

- hides traps
- hides intended intermediate reasoning path
- only describes realistic business requirements

`golden_prompt`:

- explicitly reveals hidden traps
- states task-construction assumptions
- asks for intermediate derivations and teacher artifacts
- is allowed to expose expected solution structure

### Suggested GoldenRun package

```json
{
  "golden_run_id": "gold_bp_financial_audit_0001",
  "blueprint_id": "bp_financial_audit_0001",
  "candidate_prompt": "...",
  "golden_prompt": "...",
  "teacher_hints": {
    "revealed_traps": [
      "Some rows intentionally omit explicit currency symbols.",
      "The tax-rate reference file intentionally omits one jurisdiction."
    ],
    "expected_intermediate_artifacts": [
      "currency_resolution_mapping",
      "tax_rate_resolution_note",
      "source_level_pnl_summary"
    ],
    "business_assumptions": [
      "Revenue must be normalized to USD before source-level aggregation.",
      "Missing tax rates must be resolved explicitly rather than silently skipped."
    ]
  },
  "expected_outputs": {
    "deliverables": [
      "profit_and_loss_report.xlsx",
      "task_summary.pdf"
    ],
    "teacher_artifacts": [
      "golden_intermediate_values.json",
      "golden_grading_anchors.json",
      "golden_run_log.json"
    ]
  }
}
```

### GoldenRun outputs

The GoldenRun should persist at least:

1. `golden_deliverables/`
   The standard answer files in the same interface shape expected from a candidate.

2. `golden_intermediate_values.json`
   Exact or tolerance-checked target values and intermediate tables.

3. `golden_grading_anchors.json`
   Structured grading anchors derived from execution, not manually guessed.

4. `golden_run_log.json`
   Audit trail of assumptions, trap handling, and execution notes.

### Why GoldenRun matters

Without GoldenRun:

- result-based rubrics are hard to define
- task-quality analysis is mostly subjective
- score gaps across models are harder to explain

With GoldenRun:

- `Fact` checks can be tied to exact final outputs
- `Reasoning` checks can be tied to intermediate derived states
- `Robustness` checks can be tied to explicit trap handling outcomes
- `Compliance` checks can still use deliverable/file validation

## Recommended V2 Pipeline

### Line A: Semantic skill extraction

`raw task text -> atomic semantic steps -> semantic skill candidates -> reviewed skill library`

Output:

- `SemanticSkill` objects only

Do not output:

- executable operators
- physical schemas
- final static rubrics

### Line B: Task assembly

`selected semantic skills -> task blueprint compiler -> data/file generation -> prompt generation -> golden-run packaging -> training annotation generation`

Output:

1. `TaskBlueprint`
2. generated reference files
3. visible task prompt
4. `GoldenRun` package
5. `TrainingAnnotation`
6. final dataset package

## Suggested Final Dataset Package

Your final dataset item can remain compatible with the current `dataset_row.json` style, but should be expanded internally.

```json
{
  "task_id": "TASK_0001",
  "prompt": "...",
  "reference_files": [
    "reference_files/tour_manager_data.xlsx",
    "reference_files/production_ledger.xlsx",
    "reference_files/tax_rates.xlsx"
  ],
  "deliverable_files": [
    "deliverable_files/profit_and_loss_report.xlsx",
    "deliverable_files/task_summary.pdf"
  ],
  "rubric": "...projected human-readable rubric...",
  "rubric_json": "...projected machine-readable rubric...",
  "extra": {
    "blueprint_id": "bp_financial_audit_0001",
    "training_annotation_id": "ann_bp_financial_audit_0001",
    "ground_truth": {},
    "task_blueprint": {},
    "training_annotation": {},
    "golden_run": {}
  }
}
```

## GoldenRun and `rw-task`

The existing `rw-task` framework should be reused as much as possible.

Recommended relationship:

- `rw-task` in normal mode = candidate execution
- `rw-task` in teacher mode = GoldenRun execution

This means the two modes should preferably share:

- task directory structure
- reference file mounting behavior
- deliverable collection behavior
- sandbox/runtime interface

Only the prompt construction and teacher-only side-channel inputs should differ.

### Recommended integration strategy

Do not build a completely separate GoldenRun executor if avoidable.

Instead:

1. keep the existing candidate execution path
2. add a teacher-mode prompt builder
3. allow teacher-mode runs to emit extra intermediate artifacts
4. use those artifacts to derive grading anchors and task diagnostics

This keeps the teacher and candidate flows comparable while reducing implementation drift.

## Task Quality Criteria

The final goal is not only that tasks look realistic, but that they are useful for both training and model differentiation.

A good task should be measured on at least three axes:

1. `separation`
   Stronger and weaker models should show a stable score gap.

2. `stability`
   The same model should not have wildly inconsistent scores across reruns.

3. `diagnostic_value`
   The score gap should be explainable in terms of concrete capability failures:
   - numerical reasoning
   - business reasoning
   - trap robustness
   - deliverable compliance

GoldenRun is the key mechanism that turns these from intuitions into auditable evidence.

## Migration Strategy

### Phase 1: Freeze the new schemas

First stabilize:

- `SemanticSkill`
- `TaskBlueprint`
- `TrainingAnnotation`
- `GoldenRun` package

before rewriting the whole pipeline.

### Phase 2: Keep the old package format as an outer shell

Do not break `dataset_row.json` immediately.

Instead:

- keep `prompt`, `reference_files`, `deliverable_files`, `rubric`, `rubric_json`
- move the real V2 logic into `extra.task_blueprint`, `extra.training_annotation`, and `extra.golden_run`

### Phase 3: Replace old skill content gradually

Start by converting a few finance skills from:

- semantic + operator + static rubric

to:

- semantic only

### Phase 4: Reassign module responsibilities

Suggested mapping:

- `agent_01_slicer.py`: still useful, but should slice semantic actions only
- `agent_02_port_architect.py`: should infer semantic dependencies, not physical columns
- `agent_03_abstractor.py`: should output `SemanticSkill`
- new compiler module: should assemble `TaskBlueprint`
- file generator: should consume `TaskBlueprint.data_spec` and `trap_spec`
- teacher-mode runner: should consume `GoldenRun` package and emit golden artifacts
- validator/rubric generator: should consume `TrainingAnnotation` and golden-run outputs

## What Not To Do In V2

- Do not let a library skill directly own final deliverable file names unless they are only soft hints.
- Do not force every semantic skill to map to one concrete Python operator.
- Do not store final rubric text as the primary truth source.
- Do not let prompt generation reuse low-level transformation language too literally.

## Success Criteria

The V2 design is working if:

1. one semantic skill can appear in many different business tasks
2. one business task can be realized with different concrete file schemas
3. rubrics can be regenerated from blueprint plus golden truth
4. prompts look like GDPVal-style work tasks rather than disguised data-processing instructions
5. the same underlying capability can produce many training variants
