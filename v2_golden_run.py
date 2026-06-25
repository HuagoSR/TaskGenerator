import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

from v2_schema import GoldenRun, TaskBlueprint, TrainingAnnotation


COUNTRY_CURRENCY = {
    "United Kingdom": "GBP",
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
    "United Kingdom": 0.20,
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

        tour_df = pd.read_excel(reference_path / "tour_manager_data.xlsx", sheet_name="Transactions")
        ledger_df = pd.read_excel(reference_path / "production_ledger.xlsx", sheet_name="Ledger")
        tax_df = pd.read_excel(reference_path / "tax_rates.xlsx", sheet_name="Rates")

        normalized_tour_df, currency_mapping = self._normalize_tour_transactions(tour_df)
        resolved_tax_df, tax_resolution = self._resolve_tax_rates(tax_df)

        tax_lookup = resolved_tax_df.set_index("Country")["Resolved_Withholding_Tax_Rate"].to_dict()
        normalized_tour_df["Resolved_Tax_Rate"] = normalized_tour_df["Country"].map(tax_lookup)
        normalized_tour_df["Withholding_Tax_USD"] = (
            normalized_tour_df["Gross_Revenue_USD"] * normalized_tour_df["Resolved_Tax_Rate"]
        ).round(2)
        normalized_tour_df["Net_Income_USD"] = (
            normalized_tour_df["Gross_Revenue_USD"]
            - normalized_tour_df["Expense_Amount_USD"]
            - normalized_tour_df["Withholding_Tax_USD"]
        ).round(2)

        normalized_ledger_df = self._normalize_ledger(ledger_df)
        source_summary = self._build_source_summary(normalized_tour_df, normalized_ledger_df)
        expense_bucket_mapping = self._build_expense_bucket_mapping(normalized_ledger_df)

        intermediate_values = {
            "currency_resolution_mapping": currency_mapping,
            "tax_rate_resolution": tax_resolution,
            "expense_bucket_mapping": expense_bucket_mapping,
            "source_level_net_revenue": [
                {
                    "source_name": row["source_name"],
                    "net_revenue_usd": round(row["revenue_usd"] - row["tax_usd"], 2),
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
            "tour_manager_row_metrics_sample": normalized_tour_df.head(10).to_dict(orient="records"),
        }
        grading_anchors = self._build_grading_anchors(
            blueprint=blueprint,
            annotation=annotation,
            source_summary=source_summary,
            tax_resolution=tax_resolution,
        )
        run_log = {
            "golden_run_id": golden_run.golden_run_id,
            "blueprint_id": blueprint.blueprint_id,
            "reference_files_read": [
                "tour_manager_data.xlsx",
                "production_ledger.xlsx",
                "tax_rates.xlsx",
            ],
            "assumptions": [
                "GBP rows are converted to USD using 1.27.",
                "EUR rows are converted to USD using 1.09.",
                "Missing country tax rates are restored from the canonical teacher reference table.",
            ],
            "trap_handling": [
                {
                    "trap_type": "implicit_currency",
                    "resolution": "Country-aware locale parsing and FX normalization applied before aggregation.",
                },
                {
                    "trap_type": "reference_omission",
                    "resolution": "Missing tax rates restored explicitly and logged in tax_rate_resolution.",
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

    def _normalize_tour_transactions(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[Dict[str, object]]]:
        normalized = df.copy()
        normalized["Gross_Revenue_Local"] = normalized.apply(
            lambda row: self._parse_localized_amount(row["Gross_Revenue"], row["Country"]),
            axis=1,
        )
        normalized["Expense_Amount_Local"] = normalized.apply(
            lambda row: self._parse_localized_amount(row["Expense_Amount"], row["Country"]),
            axis=1,
        )
        normalized["Currency_Code"] = normalized["Country"].map(COUNTRY_CURRENCY)
        normalized["FX_To_USD"] = normalized["Currency_Code"].map(FX_TO_USD)
        normalized["Gross_Revenue_USD"] = (
            normalized["Gross_Revenue_Local"] * normalized["FX_To_USD"]
        ).round(2)
        normalized["Expense_Amount_USD"] = (
            normalized["Expense_Amount_Local"] * normalized["FX_To_USD"]
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
        resolution_notes: List[Dict[str, object]] = []
        resolved["Resolved_Withholding_Tax_Rate"] = resolved["Withholding_Tax_Rate"]

        for idx, row in resolved.iterrows():
            if pd.isna(row["Resolved_Withholding_Tax_Rate"]):
                country = row["Country"]
                restored = DEFAULT_TAX_RATES[country]
                resolved.loc[idx, "Resolved_Withholding_Tax_Rate"] = restored
                resolution_notes.append(
                    {
                        "country": country,
                        "city": row["City"],
                        "original_rate": None,
                        "resolved_rate": restored,
                        "resolution_basis": "teacher_default_country_tax_table",
                    }
                )

        return resolved, resolution_notes

    def _normalize_ledger(self, df: pd.DataFrame) -> pd.DataFrame:
        normalized = df.copy()
        normalized["Debit_Amount"] = pd.to_numeric(normalized["Debit_Amount"], errors="coerce").fillna(0.0)
        normalized["Credit_Amount"] = pd.to_numeric(normalized["Credit_Amount"], errors="coerce").fillna(0.0)
        normalized["Expense_USD"] = normalized["Debit_Amount"].round(2)
        normalized["Revenue_USD"] = normalized["Credit_Amount"].round(2)
        normalized["Net_Income_USD"] = (
            normalized["Revenue_USD"] - normalized["Expense_USD"]
        ).round(2)
        return normalized

    def _build_expense_bucket_mapping(self, ledger_df: pd.DataFrame) -> List[Dict[str, str]]:
        bucket_by_account = {
            "Band and Crew Expense": "personnel",
            "Hotel and Restaurant Expense": "lodging_and_meals",
            "Travel Expense": "travel",
            "Production Services": "production_ops",
            "Tour Revenue": "revenue",
        }
        mappings = []
        for account_name in sorted(ledger_df["Account_Name"].dropna().astype(str).unique().tolist()):
            mappings.append(
                {
                    "account_name": account_name,
                    "mapped_bucket": bucket_by_account.get(account_name, "other"),
                }
            )
        return mappings

    def _build_source_summary(self, tour_df: pd.DataFrame, ledger_df: pd.DataFrame) -> Dict[str, object]:
        summary_rows = [
            {
                "source_name": "Tour Manager",
                "revenue_usd": round(float(tour_df["Gross_Revenue_USD"].sum()), 2),
                "expense_usd": round(float(tour_df["Expense_Amount_USD"].sum()), 2),
                "tax_usd": round(float(tour_df["Withholding_Tax_USD"].sum()), 2),
                "net_income_usd": round(float(tour_df["Net_Income_USD"].sum()), 2),
            },
            {
                "source_name": "Production Company",
                "revenue_usd": round(float(ledger_df["Revenue_USD"].sum()), 2),
                "expense_usd": round(float(ledger_df["Expense_USD"].sum()), 2),
                "tax_usd": 0.0,
                "net_income_usd": round(float(ledger_df["Net_Income_USD"].sum()), 2),
            },
        ]
        overall = {
            "revenue_usd": round(sum(row["revenue_usd"] for row in summary_rows), 2),
            "expense_usd": round(sum(row["expense_usd"] for row in summary_rows), 2),
            "tax_usd": round(sum(row["tax_usd"] for row in summary_rows), 2),
            "net_income_usd": round(sum(row["net_income_usd"] for row in summary_rows), 2),
        }
        return {"by_source": summary_rows, "overall_totals": overall}

    def _build_grading_anchors(
        self,
        blueprint: TaskBlueprint,
        annotation: TrainingAnnotation,
        source_summary: Dict[str, object],
        tax_resolution: List[Dict[str, object]],
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

        if country == "United Kingdom":
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
