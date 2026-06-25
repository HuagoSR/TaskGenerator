import json
import uuid
from pathlib import Path
from typing import Dict, List

from v2_schema import (
    CapabilityProfile,
    ColumnSpec,
    DataRelationship,
    DataSpec,
    DeliverableSpec,
    ExpectedOutputs,
    FailureMode,
    FileSpec,
    GoldenRun,
    GoldenPlan,
    InjectionPolicy,
    InjectionTarget,
    PromptSpec,
    RubricProjection,
    ScenarioSpec,
    SheetSpec,
    SupervisionTarget,
    SupervisionTargets,
    TaskBlueprint,
    TaskMetadata,
    TeacherHints,
    TrainingAnnotation,
    TrapSpec,
    V2DatasetPackage,
    load_semantic_skills,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_SKILLS_PATH = ROOT / "v2_semantic_skills_finance.json"


class FinanceAuditTaskCompiler:
    def __init__(self, skills_path: Path = DEFAULT_SKILLS_PATH):
        skills = load_semantic_skills(str(skills_path))
        self.skill_map = {skill.skill_id: skill for skill in skills}

    def compile(
        self,
        selected_skill_ids: List[str],
        scenario_title: str = "2024 Fall Music Tour Reconciliation",
        task_goal: str = "Produce a consolidated cross-source profit and loss report for executive review.",
    ) -> Dict[str, object]:
        selected_skills = [self.skill_map[skill_id] for skill_id in selected_skill_ids]
        blueprint = self._build_blueprint(selected_skills, scenario_title, task_goal)
        annotation = self._build_training_annotation(blueprint, selected_skills)
        prompt = self._build_prompt(blueprint)
        golden_run = self._build_golden_run(blueprint, prompt)
        dataset_shell = self._build_dataset_shell(blueprint, annotation, golden_run, prompt)
        return {
            "blueprint": blueprint,
            "training_annotation": annotation,
            "golden_run": golden_run,
            "prompt": prompt,
            "dataset_shell": dataset_shell,
        }

    def _build_blueprint(self, selected_skills, scenario_title: str, task_goal: str) -> TaskBlueprint:
        blueprint_id = f"bp_financial_audit_{uuid.uuid4().hex[:8]}"
        selected_ids = [skill.skill_id for skill in selected_skills]

        reference_files = self._build_reference_files(selected_ids)
        data_relationships = self._build_data_relationships(selected_ids)
        trap_spec = self._build_trap_spec(selected_ids)
        deliverable_spec = self._build_deliverable_spec()
        prompt_spec = self._build_prompt_spec(selected_skills)
        golden_plan = self._build_golden_plan(selected_skills)

        return TaskBlueprint(
            blueprint_id=blueprint_id,
            template_family="cross_border_pnl",
            task_metadata=TaskMetadata(
                sector="Financial Audit",
                occupation="Senior Auditor",
                scenario_title=scenario_title,
                task_goal=task_goal,
                difficulty_level="medium-high",
            ),
            selected_skills=selected_ids,
            scenario_spec=ScenarioSpec(
                role="You are the finance lead supporting a post-period audit review.",
                business_context=(
                    "The client operated an international music tour with revenues and costs captured by different teams, "
                    "ledgers, and operating systems."
                ),
                time_context="Reporting is being completed in January 2025 for an as-of date of December 31, 2024.",
                tone="professional, business-realistic, non-tutorial",
            ),
            data_spec=DataSpec(
                reference_files=reference_files,
                data_relationships=data_relationships,
            ),
            trap_spec=trap_spec,
            deliverable_spec=deliverable_spec,
            prompt_spec=prompt_spec,
            golden_plan=golden_plan,
        )

    def _build_reference_files(self, selected_ids: List[str]) -> List[FileSpec]:
        files: List[FileSpec] = []
        if "load_multi_source_financials" in selected_ids:
            files.extend(
                [
                    FileSpec(
                        file_name="tour_manager_data.xlsx",
                        file_role="source_data",
                        sheet_specs=[
                            SheetSpec(
                                sheet_name="Transactions",
                                row_count_target=150,
                                columns=[
                                    ColumnSpec(name="Receipt_ID", semantic_type="identifier"),
                                    ColumnSpec(name="Transaction_Date", semantic_type="date"),
                                    ColumnSpec(name="City", semantic_type="location_city"),
                                    ColumnSpec(name="Country", semantic_type="location_country"),
                                    ColumnSpec(name="Description", semantic_type="free_text_description"),
                                    ColumnSpec(name="Gross_Revenue", semantic_type="localized_amount"),
                                    ColumnSpec(name="Expense_Amount", semantic_type="localized_amount"),
                                    ColumnSpec(name="Source", semantic_type="source_system"),
                                ],
                            )
                        ],
                    ),
                    FileSpec(
                        file_name="production_ledger.xlsx",
                        file_role="source_data",
                        sheet_specs=[
                            SheetSpec(
                                sheet_name="Ledger",
                                row_count_target=400,
                                columns=[
                                    ColumnSpec(name="Ledger_Entry_ID", semantic_type="identifier"),
                                    ColumnSpec(name="Posting_Date", semantic_type="date"),
                                    ColumnSpec(name="Account_Name", semantic_type="account_name"),
                                    ColumnSpec(name="Activity_Description", semantic_type="free_text_description"),
                                    ColumnSpec(name="Debit_Amount", semantic_type="amount"),
                                    ColumnSpec(name="Credit_Amount", semantic_type="amount"),
                                    ColumnSpec(name="Source", semantic_type="source_system"),
                                ],
                            )
                        ],
                    ),
                ]
            )
        if "handle_missing_tax_rate" in selected_ids:
            files.append(
                FileSpec(
                    file_name="tax_rates.xlsx",
                    file_role="reference_table",
                    sheet_specs=[
                        SheetSpec(
                            sheet_name="Rates",
                            row_count_target=12,
                            columns=[
                                ColumnSpec(name="Country", semantic_type="location_country"),
                                ColumnSpec(name="City", semantic_type="location_city"),
                                ColumnSpec(name="Withholding_Tax_Rate", semantic_type="tax_rate"),
                            ],
                        )
                    ],
                )
            )
        return files

    def _build_data_relationships(self, selected_ids: List[str]) -> List[DataRelationship]:
        relationships: List[DataRelationship] = []
        if "handle_missing_tax_rate" in selected_ids:
            relationships.append(
                DataRelationship(
                    relation_type="lookup",
                    left="tour_manager_data.xlsx:Transactions.Country",
                    right="tax_rates.xlsx:Rates.Country",
                )
            )
        return relationships

    def _build_trap_spec(self, selected_ids: List[str]) -> List[TrapSpec]:
        traps: List[TrapSpec] = []
        if "infer_implicit_currency" in selected_ids:
            traps.append(
                TrapSpec(
                    trap_id="trap_implicit_currency_01",
                    source_skill_id="infer_implicit_currency",
                    trap_type="implicit_currency",
                    injection_target=InjectionTarget(
                        file_name="tour_manager_data.xlsx",
                        sheet_name="Transactions",
                        columns=["Gross_Revenue", "Expense_Amount"],
                    ),
                    injection_policy=InjectionPolicy(
                        pattern="mixed_local_currency_without_header_signal",
                        severity="medium",
                        affected_row_count=20,
                    ),
                    expected_solver_behavior=(
                        "Infer currency from geographic context and avoid reporting mixed-currency totals."
                    ),
                )
            )
        if "handle_missing_tax_rate" in selected_ids:
            traps.append(
                TrapSpec(
                    trap_id="trap_missing_tax_rate_01",
                    source_skill_id="handle_missing_tax_rate",
                    trap_type="reference_omission",
                    injection_target=InjectionTarget(
                        file_name="tax_rates.xlsx",
                        sheet_name="Rates",
                        columns=["Withholding_Tax_Rate"],
                    ),
                    injection_policy=InjectionPolicy(
                        pattern="omit_one_jurisdiction",
                        severity="medium",
                        affected_entities=["Amsterdam", "Netherlands"],
                    ),
                    expected_solver_behavior=(
                        "Detect the missing reference and resolve it using business logic or defensible assumptions."
                    ),
                )
            )
        return traps

    def _build_deliverable_spec(self) -> List[DeliverableSpec]:
        return [
            DeliverableSpec(
                file_name="profit_and_loss_report.xlsx",
                file_role="final_deliverable",
                requirements=[
                    "must include header 'As of 12/31/2024'",
                    "must present source-level totals",
                    "must normalize revenue to USD",
                ],
            ),
            DeliverableSpec(
                file_name="task_summary.pdf",
                file_role="final_deliverable",
                requirements=[
                    "must summarize reconciliation approach",
                    "must mention any assumptions or anomalies",
                ],
            ),
        ]

    def _build_prompt_spec(self, selected_skills) -> PromptSpec:
        visible = [
            "prepare a structured P&L report",
            "use the attached files",
            "report all revenues in USD",
            "provide an executive-ready workbook",
        ]
        hidden = []
        for skill in selected_skills:
            hidden.append(skill.semantic_intent.hidden_difficulty)
        return PromptSpec(
            visible_requirements=visible,
            hidden_requirements=hidden,
            style_constraints=[
                "realistic business memo tone",
                "no explicit data-cleaning tutorial",
                "no trap disclosure",
            ],
        )

    def _build_golden_plan(self, selected_skills) -> GoldenPlan:
        intermediate = []
        final_checks = [
            "deliverable file existence",
            "format compliance",
        ]
        capability_to_state = {
            "currency_inference": "currency_resolution_mapping",
            "reference_gap_resolution": "tax_rate_resolution",
            "expense_mapping": "expense_bucket_mapping",
            "aggregation": "source_level_net_revenue",
            "net_income_calculation": "net_income_totals",
        }
        for skill in selected_skills:
            for tag in skill.capability_tags:
                if tag in capability_to_state:
                    intermediate.append(capability_to_state[tag])
        if "source_level_net_revenue" in intermediate:
            final_checks.extend(["net revenue totals", "expense totals", "net income totals"])
        return GoldenPlan(
            required_intermediate_states=list(dict.fromkeys(intermediate)),
            required_final_checks=list(dict.fromkeys(final_checks)),
        )

    def _build_training_annotation(self, blueprint: TaskBlueprint, selected_skills) -> TrainingAnnotation:
        primary = []
        secondary = []
        for skill in selected_skills:
            primary.extend(skill.capability_tags[:2])
            secondary.extend(skill.difficulty_tags[:2])

        final_outcomes = [
            SupervisionTarget(
                target_id="final_pnl_totals",
                target_type="exact_or_tolerance_check",
                description="Validate final source-level and total P&L figures against the golden run.",
            ),
            SupervisionTarget(
                target_id="deliverable_presence",
                target_type="binary_check",
                description="Check that the required workbook and summary file are produced with correct names.",
            ),
        ]

        intermediate_outcomes = []
        if "infer_implicit_currency" in blueprint.selected_skills:
            intermediate_outcomes.append(
                SupervisionTarget(
                    target_id="currency_resolution",
                    target_type="reasoning_check",
                    description="Verify that implicit local amounts are interpreted using the correct jurisdictional cues.",
                )
            )
        if "handle_missing_tax_rate" in blueprint.selected_skills:
            intermediate_outcomes.append(
                SupervisionTarget(
                    target_id="missing_tax_resolution",
                    target_type="reasoning_or_robustness_check",
                    description="Verify that the missing tax rate does not silently corrupt final calculations.",
                )
            )
        if "categorize_operating_expense" in blueprint.selected_skills:
            intermediate_outcomes.append(
                SupervisionTarget(
                    target_id="expense_taxonomy_mapping",
                    target_type="reasoning_check",
                    description="Verify that operating expenses are grouped into the intended reporting buckets before final aggregation.",
                )
            )

        failure_modes = [
            FailureMode(
                failure_id="fm_mixed_currency_sum",
                description="The model aggregates amounts before normalizing currencies.",
            ),
            FailureMode(
                failure_id="fm_null_tax_propagation",
                description="A missing tax rate causes null propagation or skipped rows without acknowledgement.",
            ),
            FailureMode(
                failure_id="fm_format_only_success",
                description="The report looks polished but contains wrong financial logic.",
            ),
            FailureMode(
                failure_id="fm_source_double_count",
                description="The model merges multi-source figures in a way that double counts revenue or expenses.",
            ),
        ]

        rubric_projection = RubricProjection(
            fact_checks=["Final source-level and overall P&L totals match the golden run."],
            reasoning_checks=[
                "The model correctly infers implicit currencies from business context.",
                "The model uses a defensible tax-rate resolution path for incomplete reference data.",
            ],
            robustness_checks=["The missing tax-rate omission does not break downstream calculations."],
            compliance_checks=["Required deliverables exist and satisfy naming and format requirements."],
        )

        return TrainingAnnotation(
            annotation_id=f"ann_{blueprint.blueprint_id}",
            blueprint_id=blueprint.blueprint_id,
            capability_profile=CapabilityProfile(
                primary_capabilities=list(dict.fromkeys(primary)),
                secondary_capabilities=list(dict.fromkeys(secondary)),
            ),
            supervision_targets=SupervisionTargets(
                final_outcomes=final_outcomes,
                intermediate_outcomes=intermediate_outcomes,
            ),
            failure_modes=failure_modes,
            rubric_projection=rubric_projection,
        )

    def _build_prompt(self, blueprint: TaskBlueprint) -> str:
        return (
            f"You are supporting a {blueprint.task_metadata.occupation} engagement.\n\n"
            f"Objective: {blueprint.task_metadata.task_goal}\n\n"
            f"Context:\n"
            f"- {blueprint.scenario_spec.business_context}\n"
            f"- {blueprint.scenario_spec.time_context}\n\n"
            f"Using the attached reference files, prepare a structured Excel profit and loss report suitable for executive review. "
            f"The final workbook must report revenues in USD, present source-level totals, and clearly show the resulting net income.\n\n"
            f"Deliverables:\n"
            f"1. Create an Excel workbook named `profit_and_loss_report.xlsx`.\n"
            f"2. Include a clear header stating `As of 12/31/2024`.\n"
            f"3. Prepare a PDF summary named `task_summary.pdf` describing your reconciliation approach and any assumptions.\n\n"
            f"Work carefully with the provided sources. The files may reflect realistic operational inconsistencies, so ensure your final deliverables remain internally coherent, well-formatted, and decision-ready."
        )

    def _build_golden_run(self, blueprint: TaskBlueprint, candidate_prompt: str) -> GoldenRun:
        revealed_traps = []
        business_assumptions = [
            "Revenue and expense amounts from operational files must be normalized to USD before cross-source comparison.",
            "Missing reference values must be resolved explicitly and logged as teacher assumptions.",
        ]
        for trap in blueprint.trap_spec:
            if trap.trap_type == "implicit_currency":
                revealed_traps.append("Some operational rows intentionally omit explicit currency symbols and rely on locale-specific number formatting.")
            elif trap.trap_type == "reference_omission":
                revealed_traps.append("The tax-rate reference workbook intentionally omits at least one jurisdictional value.")

        expected_intermediates = list(dict.fromkeys(blueprint.golden_plan.required_intermediate_states))
        golden_prompt = (
            f"{candidate_prompt}\n\n"
            "Teacher-mode instructions:\n"
            "1. You are producing the canonical solution package for dataset construction.\n"
            "2. Reveal and resolve every intentional trap before producing final totals.\n"
            "3. Emit the intermediate states required by the golden plan.\n"
            "4. Record all assumptions, especially any restored reference values, in the run log.\n"
            "5. Produce grading anchors that can later be consumed by evaluation code."
        )

        return GoldenRun(
            golden_run_id=f"gold_{blueprint.blueprint_id}",
            blueprint_id=blueprint.blueprint_id,
            candidate_prompt=candidate_prompt,
            golden_prompt=golden_prompt,
            teacher_hints=TeacherHints(
                revealed_traps=list(dict.fromkeys(revealed_traps)),
                expected_intermediate_artifacts=expected_intermediates,
                business_assumptions=business_assumptions,
            ),
            expected_outputs=ExpectedOutputs(
                deliverables=[item.file_name for item in blueprint.deliverable_spec],
                teacher_artifacts=[
                    "golden_intermediate_values.json",
                    "golden_grading_anchors.json",
                    "golden_run_log.json",
                ],
            ),
        )

    def _build_dataset_shell(
        self,
        blueprint: TaskBlueprint,
        annotation: TrainingAnnotation,
        golden_run: GoldenRun,
        prompt: str,
    ) -> V2DatasetPackage:
        rubric_lines = []
        rubric_items = []
        idx = 1
        for check in annotation.rubric_projection.fact_checks:
            rubric_lines.append(f"- [+3] {check}")
            rubric_items.append({"rubric_item_id": f"F_{idx:03d}", "score": 3, "criterion": check, "tags": ["outcome"]})
            idx += 1
        for check in annotation.rubric_projection.reasoning_checks:
            rubric_lines.append(f"- [+3] {check}")
            rubric_items.append({"rubric_item_id": f"R_{idx:03d}", "score": 3, "criterion": check, "tags": ["reasoning"]})
            idx += 1
        for check in annotation.rubric_projection.robustness_checks:
            rubric_lines.append(f"- [+3] {check}")
            rubric_items.append({"rubric_item_id": f"B_{idx:03d}", "score": 3, "criterion": check, "tags": ["robustness"]})
            idx += 1
        for check in annotation.rubric_projection.compliance_checks:
            rubric_lines.append(f"- [+2] {check}")
            rubric_items.append({"rubric_item_id": f"C_{idx:03d}", "score": 2, "criterion": check, "tags": ["compliance"]})
            idx += 1

        return V2DatasetPackage(
            task_id=f"TASK_{blueprint.blueprint_id.split('_')[-1].upper()}",
            prompt=prompt,
            reference_files=[f"reference_files/{file.file_name}" for file in blueprint.data_spec.reference_files],
            deliverable_files=[f"deliverable_files/{file.file_name}" for file in blueprint.deliverable_spec],
            rubric="\n".join(rubric_lines),
            rubric_json=json.dumps(rubric_items, ensure_ascii=False),
            extra={
                "blueprint_id": blueprint.blueprint_id,
                "training_annotation_id": annotation.annotation_id,
                "golden_run_id": golden_run.golden_run_id,
                "task_blueprint": blueprint.model_dump(),
                "training_annotation": annotation.model_dump(),
                "golden_run": golden_run.model_dump(),
            },
        )


def main() -> None:
    compiler = FinanceAuditTaskCompiler()
    package = compiler.compile(
        [
            "load_multi_source_financials",
            "infer_implicit_currency",
            "handle_missing_tax_rate",
            "categorize_operating_expense",
            "aggregate_source_level_pnl",
        ]
    )
    print(package["blueprint"].model_dump_json(indent=2))
    print(package["training_annotation"].model_dump_json(indent=2))
    print(package["dataset_shell"].model_dump_json(indent=2))


if __name__ == "__main__":
    main()
