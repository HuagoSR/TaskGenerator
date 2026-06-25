import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

from v2_schema import GoldenRun, TaskBlueprint, TrainingAnnotation


COUNTRY_CURRENCY = {
    "UK": "GBP",
    "France": "EUR",
    "Germany": "EUR",
    "Spain": "EUR",
    "Netherlands": "EUR",
}

FX_TO_USD = {
    "GBP": 1.27,
    "EUR": 1.09,
    "USD": 1.00,
}

DEFAULT_TAX_RATES = {
    "UK": 0.20,
    "France": 0.15,
    "Germany": 0.15825,
    "Spain": 0.24,
    "Netherlands": 0.19,
}


@dataclass
class GoldenRunArtifacts:
    intermediate_values: Dict[str, object]
    grading_anchors: Dict[str, object]
    run_log: Dict[str, object]


class FinanceAuditGoldenRunExecutor:
    def execute(
        self,
        blueprint: TaskBlueprint,
        annotation: TrainingAnnotation,
        golden_run: GoldenRun,
        reference_dir: str | Path,
        output_dir: str | Path,
    ) -> GoldenRunArtifacts:
        reference_path = Path(reference_dir)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        tour_df = pd.read_excel(
            reference_path / "fall_music_tour_ref_file.xlsx",
            sheet_name="Inc_Costs_Tracked_by_Tour_Mgr",
        )
        tax_df = pd.read_excel(
            reference_path / "fall_music_tour_ref_file.xlsx",
            sheet_name="Assump_Withholding_Tax",
        )
        prod_df = pd.read_excel(
            reference_path / "production_company_costs.xlsx",
            sheet_name="Costs_Tracked_by_Production_Co",
        )

        normalized_tour_df, currency_mapping = self._normalize_tour_rows(tour_df)
        resolved_tax_df, tax_resolution = self._resolve_tax_rates(tax_df)

        tax_lookup = resolved_tax_df.set_index("Country")["Resolved_Withholding_Tax_Rate"].to_dict()
        normalized_tour_df["Resolved_Tax_Rate"] = normalized_tour_df["Country"].map(tax_lookup)
        normalized_tour_df["Withholding_Tax_USD"] = (
            normalized_tour_df["Gross_Revenue_USD"] * normalized_tour_df["Resolved_Tax_Rate"]
        ).round(2)
        normalized_tour_df["Net_Revenue_USD"] = (
            normalized_tour_df["Gross_Revenue_USD"] - normalized_tour_df["Withholding_Tax_USD"]
        ).round(2)

        normalized_prod_df = self._normalize_production_costs(prod_df)
        expense_bucket_mapping = self._build_expense_bucket_mapping(normalized_prod_df)
        source_summary = self._build_source_summary(normalized_tour_df, normalized_prod_df)
        revenue_line_items = self._build_revenue_line_items(normalized_tour_df)
        withholding_by_country = self._build_withholding_by_country(normalized_tour_df)
        expense_category_totals = self._build_expense_category_totals(normalized_prod_df)

        intermediate_values = {
            "currency_resolution_mapping": currency_mapping,
            "tax_rate_resolution": tax_resolution,
            "expense_bucket_mapping": expense_bucket_mapping,
            "source_level_net_revenue": [
                {
                    "source_name": row["source_name"],
                    "net_revenue_usd": row["net_revenue_usd"],
                }
                for row in source_summary["by_source"]
            ],
            "source_level_total_expenses": [
                {
                    "source_name": row["source_name"],
                    "expense_usd": row["expense_usd"],
                }
                for row in source_summary["by_source"]
            ],
            "net_income_totals": source_summary["overall_totals"],
            "source_level_pnl_summary": source_summary,
            "revenue_line_items": revenue_line_items,
            "withholding_by_country": withholding_by_country,
            "expense_category_totals": expense_category_totals,
        }
        grading_anchors = self._build_grading_anchors(
            blueprint=blueprint,
            annotation=annotation,
            source_summary=source_summary,
            tax_resolution=tax_resolution,
            revenue_line_items=revenue_line_items,
            withholding_by_country=withholding_by_country,
            expense_category_totals=expense_category_totals,
        )
        run_log = {
            "golden_run_id": golden_run.golden_run_id,
            "blueprint_id": blueprint.blueprint_id,
            "reference_files_read": [
                "fall_music_tour_ref_file.xlsx",
                "production_company_costs.xlsx",
            ],
            "assumptions": [
                "UK rows are converted to USD using 1.27.",
                "France, Germany, Spain, and Netherlands rows are converted to USD using 1.09.",
                "Missing withholding tax assumptions are restored from the canonical teacher tax table.",
            ],
            "trap_handling": [
                {
                    "trap_type": "implicit_currency",
                    "resolution": "Jurisdiction-aware numeric parsing is applied before final workbook totals are computed.",
                },
                {
                    "trap_type": "reference_omission",
                    "resolution": "Missing withholding tax assumptions are restored explicitly before tax-adjusted totals are produced.",
                },
            ],
            "generated_teacher_artifacts": golden_run.expected_outputs.teacher_artifacts,
        }

        self._write_json(output_path / "golden_intermediate_values.json", intermediate_values)
        self._write_json(output_path / "golden_grading_anchors.json", grading_anchors)
        self._write_json(output_path / "golden_run_log.json", run_log)

        return GoldenRunArtifacts(
            intermediate_values=intermediate_values,
            grading_anchors=grading_anchors,
            run_log=run_log,
        )

    def _normalize_tour_rows(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[Dict[str, object]]]:
        normalized = df.copy()
        normalized["Gross_Revenue_Local"] = normalized.apply(
            lambda row: self._parse_localized_amount(row["Gross_Revenue"], row["Country"]),
            axis=1,
        )
        normalized["Currency_Code"] = normalized["Country"].map(COUNTRY_CURRENCY)
        normalized["FX_To_USD"] = normalized["Currency_Code"].map(FX_TO_USD)
        normalized["Gross_Revenue_USD"] = (
            normalized["Gross_Revenue_Local"] * normalized["FX_To_USD"]
        ).round(2)

        mapping = (
            normalized[["Country", "Currency_Code", "FX_To_USD"]]
            .drop_duplicates()
            .sort_values(["Country"])
            .to_dict(orient="records")
        )
        return normalized, mapping

    def _resolve_tax_rates(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[Dict[str, object]]]:
        resolved = df.copy()
        resolved["Resolved_Withholding_Tax_Rate"] = resolved["Withholding_Tax_Rate"]
        resolution_notes: List[Dict[str, object]] = []

        for idx, row in resolved.iterrows():
            country = row["Country"]
            if pd.isna(country) or str(country).strip() == "" or str(country).strip() == "Notes":
                continue
            if pd.isna(row["Resolved_Withholding_Tax_Rate"]):
                restored = DEFAULT_TAX_RATES[str(country)]
                resolved.loc[idx, "Resolved_Withholding_Tax_Rate"] = restored
                resolution_notes.append(
                    {
                        "country": str(country),
                        "original_rate": None,
                        "resolved_rate": restored,
                        "resolution_basis": "teacher_default_country_tax_table",
                    }
                )

        return resolved, resolution_notes

    def _normalize_production_costs(self, df: pd.DataFrame) -> pd.DataFrame:
        normalized = df.copy()
        normalized["Amount_USD"] = pd.to_numeric(normalized["Amount_USD"], errors="coerce").fillna(0.0)
        return normalized

    def _build_expense_bucket_mapping(self, prod_df: pd.DataFrame) -> List[Dict[str, str]]:
        mappings = []
        for category in sorted(prod_df["Cost_Category"].dropna().astype(str).unique().tolist()):
            mappings.append(
                {
                    "account_name": category,
                    "mapped_bucket": category.lower().replace(" & ", "_").replace(" ", "_"),
                }
            )
        return mappings

    def _build_source_summary(self, tour_df: pd.DataFrame, prod_df: pd.DataFrame) -> Dict[str, object]:
        production_cost_total = round(float(prod_df["Amount_USD"].sum()), 2)
        gross_revenue_total = round(float(tour_df["Gross_Revenue_USD"].sum()), 2)
        tax_total = round(float(tour_df["Withholding_Tax_USD"].sum()), 2)
        net_revenue_total = round(float(tour_df["Net_Revenue_USD"].sum()), 2)

        summary_rows = [
            {
                "source_name": "Tour Manager",
                "revenue_usd": gross_revenue_total,
                "expense_usd": 0.0,
                "tax_usd": tax_total,
                "net_revenue_usd": net_revenue_total,
                "net_income_usd": net_revenue_total,
            },
            {
                "source_name": "Production Company",
                "revenue_usd": 0.0,
                "expense_usd": production_cost_total,
                "tax_usd": 0.0,
                "net_revenue_usd": 0.0,
                "net_income_usd": -production_cost_total,
            },
        ]
        overall = {
            "revenue_usd": gross_revenue_total,
            "expense_usd": production_cost_total,
            "tax_usd": tax_total,
            "net_income_usd": round(net_revenue_total - production_cost_total, 2),
        }
        return {"by_source": summary_rows, "overall_totals": overall}

    def _build_revenue_line_items(self, tour_df: pd.DataFrame) -> List[Dict[str, object]]:
        line_items = []
        for _, row in tour_df.iterrows():
            line_items.append(
                {
                    "line_type": str(row["Line_Type"]),
                    "city": str(row["City"]),
                    "country": str(row["Country"]),
                    "gross_revenue_usd": round(float(row["Gross_Revenue_USD"]), 2),
                    "withholding_tax_usd": round(float(row["Withholding_Tax_USD"]), 2),
                    "net_revenue_usd": round(float(row["Net_Revenue_USD"]), 2),
                }
            )
        return line_items

    def _build_withholding_by_country(self, tour_df: pd.DataFrame) -> List[Dict[str, object]]:
        grouped = (
            tour_df.groupby("Country", as_index=False)["Withholding_Tax_USD"]
            .sum()
            .sort_values("Country")
        )
        return [
            {
                "country": str(row["Country"]),
                "withholding_tax_usd": round(float(row["Withholding_Tax_USD"]), 2),
            }
            for _, row in grouped.iterrows()
        ]

    def _build_expense_category_totals(self, prod_df: pd.DataFrame) -> List[Dict[str, object]]:
        grouped = (
            prod_df.groupby("Cost_Category", as_index=False)["Amount_USD"]
            .sum()
            .sort_values("Cost_Category")
        )
        return [
            {
                "cost_category": str(row["Cost_Category"]),
                "amount_usd": round(float(row["Amount_USD"]), 2),
            }
            for _, row in grouped.iterrows()
        ]

    def _build_grading_anchors(
        self,
        blueprint: TaskBlueprint,
        annotation: TrainingAnnotation,
        source_summary: Dict[str, object],
        tax_resolution: List[Dict[str, object]],
        revenue_line_items: List[Dict[str, object]],
        withholding_by_country: List[Dict[str, object]],
        expense_category_totals: List[Dict[str, object]],
    ) -> Dict[str, object]:
        return {
            "blueprint_id": blueprint.blueprint_id,
            "golden_targets": {
                "final_pnl_totals": {
                    "target_type": "exact_or_tolerance_check",
                    "tolerance": 0.05,
                    "expected_value": source_summary,
                },
                "deliverable_presence": {
                    "target_type": "binary_check",
                    "expected_files": [item.file_name for item in blueprint.deliverable_spec],
                },
                "workbook_structure": {
                    "target_type": "structural_check",
                    "expected_header_text": "As of 12/31/2024",
                    "required_source_columns": ["Tour Manager", "Production Company", "Total"],
                    "required_financial_concepts": [
                        "Gross Revenue",
                        "Withholding Tax",
                        "Total Costs",
                        "Net Income",
                    ],
                },
                "revenue_line_items": {
                    "target_type": "line_item_check",
                    "expected_value": revenue_line_items,
                },
                "withholding_by_country": {
                    "target_type": "group_total_check",
                    "expected_value": withholding_by_country,
                },
                "expense_category_totals": {
                    "target_type": "group_total_check",
                    "expected_value": expense_category_totals,
                },
            },
            "intermediate_targets": {
                "required_states": blueprint.golden_plan.required_intermediate_states,
                "tax_resolution_events": tax_resolution,
            },
            "rubric_projection": annotation.rubric_projection.model_dump(),
        }

    def _parse_localized_amount(self, value: object, country: str) -> float:
        if pd.isna(value):
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).strip()
        if not text:
            return 0.0

        if country == "UK":
            text = text.replace(",", "")
            return float(text)

        if "," in text and "." in text:
            text = text.replace(".", "").replace(",", ".")
            return float(text)

        if "," in text:
            text = text.replace(",", ".")
        return float(text)

    def _write_json(self, path: Path, payload: Dict[str, object]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
