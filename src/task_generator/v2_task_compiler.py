import json
import uuid
from pathlib import Path
from typing import Dict, List

from task_generator.v2_schema import (
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
            template_family="financial_workbook_rollforward",
            task_metadata=TaskMetadata(
                sector="Financial Audit",
                occupation="Senior Auditor",
                scenario_title=scenario_title,
                task_goal=task_goal,
                difficulty_level="medium",
            ),
            selected_skills=selected_ids,
            scenario_spec=ScenarioSpec(
                role="You are the finance lead supporting a post-period audit review.",
                business_context=(
                    "The client operated an international music tour and prepared a partially structured audit workbook with separate tabs "
                    "for tour-manager revenue, withholding-tax assumptions, and production-company costs."
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
                        file_name="fall_music_tour_ref_file.xlsx",
                        file_role="source_data",
                        sheet_specs=[
                            SheetSpec(
                                sheet_name="Inc_Costs_Tracked_by_Tour_Mgr",
                                row_count_target=7,
                                columns=[
                                    ColumnSpec(name="Line_Type", semantic_type="free_text_description"),
                                    ColumnSpec(name="Tour_Date", semantic_type="date"),
                                    ColumnSpec(name="City", semantic_type="location_city"),
                                    ColumnSpec(name="Country", semantic_type="location_country_compact"),
                                    ColumnSpec(name="Gross_Revenue", semantic_type="localized_amount"),
                                ],
                            ),
                            SheetSpec(
                                sheet_name="Assump_Withholding_Tax",
                                row_count_target=6,
                                columns=[
                                    ColumnSpec(name="Country", semantic_type="location_country_compact"),
                                    ColumnSpec(name="Withholding_Tax_Rate", semantic_type="tax_rate"),
                                ],
                            ),
                            SheetSpec(
                                sheet_name="Tax_Policy_Notes",
                                row_count_target=1,
                                columns=[
                                    ColumnSpec(name="Jurisdiction", semantic_type="location_country"),
                                    ColumnSpec(name="Policy_Topic", semantic_type="free_text_description"),
                                    ColumnSpec(name="Resolved_Withholding_Tax_Rate", semantic_type="tax_rate"),
                                    ColumnSpec(name="Source_Note", semantic_type="free_text_description"),
                                ],
                            ),
                        ],
                    ),
                    FileSpec(
                        file_name="production_company_costs.xlsx",
                        file_role="source_data",
                        sheet_specs=[
                            SheetSpec(
                                sheet_name="Costs_Tracked_by_Production_Co",
                                row_count_target=14,
                                columns=[
                                    ColumnSpec(name="Cost_Category", semantic_type="account_name"),
                                    ColumnSpec(name="Cost_Item", semantic_type="free_text_description"),
                                    ColumnSpec(name="Amount_USD", semantic_type="amount"),
                                ],
                            )
                        ],
                    ),
                    FileSpec(
                        file_name="fx_policy.xlsx",
                        file_role="reference_table",
                        sheet_specs=[
                            SheetSpec(
                                sheet_name="FX_Policy",
                                row_count_target=3,
                                columns=[
                                    ColumnSpec(name="Currency_Code", semantic_type="currency_code"),
                                    ColumnSpec(name="Reporting_Currency", semantic_type="currency_code"),
                                    ColumnSpec(name="FX_To_USD", semantic_type="fx_rate"),
                                    ColumnSpec(name="Effective_Date", semantic_type="date"),
                                ],
                            )
                        ],
                    ),
                ]
            )
        return files

    def _build_data_relationships(self, selected_ids: List[str]) -> List[DataRelationship]:
        relationships: List[DataRelationship] = []
        if "handle_missing_tax_rate" in selected_ids:
            relationships.append(
                DataRelationship(
                    relation_type="lookup",
                    left="fall_music_tour_ref_file.xlsx:Inc_Costs_Tracked_by_Tour_Mgr.Country",
                    right="fall_music_tour_ref_file.xlsx:Assump_Withholding_Tax.Country",
                )
            )
            relationships.append(
                DataRelationship(
                    relation_type="fallback_lookup",
                    left="fall_music_tour_ref_file.xlsx:Assump_Withholding_Tax.Country",
                    right="fall_music_tour_ref_file.xlsx:Tax_Policy_Notes.Jurisdiction",
                )
            )
        if "infer_implicit_currency" in selected_ids:
            relationships.append(
                DataRelationship(
                    relation_type="lookup",
                    left="fall_music_tour_ref_file.xlsx:Inc_Costs_Tracked_by_Tour_Mgr.Country",
                    right="fx_policy.xlsx:FX_Policy.Currency_Code",
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
                        file_name="fall_music_tour_ref_file.xlsx",
                        sheet_name="Inc_Costs_Tracked_by_Tour_Mgr",
                        columns=["Gross_Revenue"],
                    ),
                    injection_policy=InjectionPolicy(
                        pattern="mixed_local_currency_without_header_signal",
                        severity="medium",
                        affected_row_count=3,
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
                        file_name="fall_music_tour_ref_file.xlsx",
                        sheet_name="Assump_Withholding_Tax",
                        columns=["Withholding_Tax_Rate"],
                    ),
                    injection_policy=InjectionPolicy(
                        pattern="omit_one_jurisdiction",
                        severity="medium",
                        affected_entities=["Germany"],
                    ),
                    expected_solver_behavior=(
                        "Detect the missing reference and resolve it from the supporting tax policy notes before finalizing totals."
                    ),
                )
            )
        return traps

    def _build_deliverable_spec(self) -> List[DeliverableSpec]:
        return [
            DeliverableSpec(
                file_name="fall_music_tour_output.xlsx",
                file_role="final_deliverable",
                requirements=[
                    "must include header 'As of 12/31/2024'",
                    "must present Tour Manager, Production Company, and Total columns",
                    "must compute gross revenue, withholding tax, total costs, and net income",
                ],
            ),
        ]

    def _build_prompt_spec(self, selected_skills) -> PromptSpec:
        visible = [
            "complete a structured P&L workbook",
            "use the attached files",
            "report all revenues in USD",
            "apply the provided FX policy when normalizing local revenue amounts",
            "resolve incomplete withholding-tax assumptions using supporting policy notes",
            "produce an executive-ready output workbook",
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
            "fallback_reference_lookup": "tax_policy_note_lookup",
            "expense_mapping": "expense_bucket_mapping",
            "aggregation": "source_level_net_revenue",
            "net_income_calculation": "net_income_totals",
        }
        for skill in selected_skills:
            for tag in skill.capability_tags:
                if tag in capability_to_state:
                    intermediate.append(capability_to_state[tag])
            if skill.skill_id == "infer_implicit_currency":
                intermediate.append("fx_policy_table")
            if skill.skill_id == "handle_missing_tax_rate":
                intermediate.append("tax_policy_note_lookup")
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
                description="Validate final workbook totals against the golden run.",
            ),
            SupervisionTarget(
                target_id="deliverable_presence",
                target_type="binary_check",
                description="Check that the required workbook is produced with the correct name.",
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
                    description="Verify that the missing tax rate is resolved from supporting tax policy notes before final calculations.",
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
            fact_checks=["Final workbook totals match the golden run."],
            reasoning_checks=[
                "The model correctly infers implicit currencies from business context.",
                "The model resolves incomplete withholding-tax assumptions from supporting policy notes.",
            ],
            robustness_checks=["The missing tax-rate omission does not break downstream calculations."],
            compliance_checks=["Required workbook exists and satisfies naming and structural requirements."],
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
        deliverable_names = [item.file_name for item in blueprint.deliverable_spec]
        return (
            f"### Audit Assignment: {blueprint.task_metadata.scenario_title}\n\n"
            f"**Role:** {blueprint.task_metadata.occupation}\n\n"
            f"**Engagement Context:**\n"
            f"{blueprint.scenario_spec.business_context} {blueprint.scenario_spec.time_context}\n\n"
            f"Management needs a completed profit-and-loss workbook that rolls the provided support tabs into one coherent audit-ready summary. "
            f"Your work should preserve the workbook structure, complete the required calculations, and keep the final result suitable for executive review.\n\n"
            f"**Objective:**\n"
            f"{blueprint.task_metadata.task_goal}\n\n"
            f"**Working Expectations:**\n"
            f"- Use the attached reference files as the sole working data sources.\n"
            f"- Complete a final P&L workbook that shows Tour Manager, Production Company, and Total columns.\n"
            f"- Report revenues in USD and apply withholding-tax adjustments before presenting net income.\n"
            f"- Use the attached FX policy for local-currency revenue normalization.\n"
            f"- Use supporting tax policy notes to resolve incomplete withholding-tax assumptions.\n"
            f"- If the source materials contain irregularities or incomplete information, resolve them carefully inside the workbook logic.\n\n"
            f"**Required Deliverables:**\n"
            f"1. Create an Excel workbook named `{deliverable_names[0]}`.\n"
            f"2. Include a clear header stating `As of 12/31/2024`.\n"
            f"3. The workbook must present gross revenue, withholding taxes, total costs, and final net income.\n"
            f"4. The workbook should be professionally structured and readable without adding unrelated files.\n\n"
            f"**Quality Bar:**\n"
            f"The final package should read like a real client-facing audit work product: numerically coherent, professionally formatted, and decision-ready."
        )

    def _build_golden_run(self, blueprint: TaskBlueprint, candidate_prompt: str) -> GoldenRun:
        revealed_traps = []
        business_assumptions = [
            "Revenue and expense amounts from operational files must be normalized to USD before cross-source comparison.",
            "Missing withholding-tax values must be resolved from supporting policy notes before final totals are computed.",
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

