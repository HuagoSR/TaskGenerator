import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from v2_schema import FileSpec, SheetSpec, TaskBlueprint, TrapSpec


COUNTRY_CITY_OPTIONS: Dict[str, List[str]] = {
    "United Kingdom": ["London", "Manchester", "Bristol"],
    "France": ["Paris", "Lyon", "Marseille"],
    "Germany": ["Berlin", "Hamburg", "Munich"],
    "Spain": ["Madrid", "Barcelona", "Valencia"],
    "Netherlands": ["Amsterdam", "Rotterdam"],
}

TAX_RATE_BY_COUNTRY: Dict[str, float] = {
    "United Kingdom": 0.20,
    "France": 0.15,
    "Germany": 0.15825,
    "Spain": 0.24,
    "Netherlands": 0.19,
}

DESCRIPTION_OPTIONS = [
    "Venue settlement adjustment",
    "Crew travel reimbursement",
    "Hotel block invoice",
    "Local transport charge",
    "Merchandise revenue settlement",
    "Production runner expense",
]

ACCOUNT_OPTIONS = [
    "Tour Revenue",
    "Band and Crew Expense",
    "Hotel and Restaurant Expense",
    "Travel Expense",
    "Production Services",
]


@dataclass
class GeneratedWorkbook:
    file_name: str
    sheets: Dict[str, pd.DataFrame] = field(default_factory=dict)


class V2BlueprintFileGenerator:
    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)
        self.ground_truth: Dict[str, Dict[str, List[int] | Dict[str, List[int]]]] = {}

    def generate_reference_files(self, blueprint: TaskBlueprint, output_dir: str | Path) -> Dict[str, Dict[str, List[int] | Dict[str, List[int]]]]:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        generated = {}
        for file_spec in blueprint.data_spec.reference_files:
            workbook = self._build_workbook(file_spec)
            self._apply_traps(workbook, blueprint.trap_spec)
            self._write_workbook(output_path / file_spec.file_name, workbook)
            generated[file_spec.file_name] = self.ground_truth.get(file_spec.file_name, {"trap_rows": {}})

        return generated

    def _build_workbook(self, file_spec: FileSpec) -> GeneratedWorkbook:
        workbook = GeneratedWorkbook(file_name=file_spec.file_name)
        for sheet_spec in file_spec.sheet_specs:
            workbook.sheets[sheet_spec.sheet_name] = self._build_sheet(file_spec, sheet_spec)
        return workbook

    def _build_sheet(self, file_spec: FileSpec, sheet_spec: SheetSpec) -> pd.DataFrame:
        row_count = sheet_spec.row_count_target
        data: Dict[str, List[object]] = {}

        countries = self._sample_countries(row_count)
        cities = [self.rng.choice(COUNTRY_CITY_OPTIONS[country]) for country in countries]

        for col in sheet_spec.columns:
            if col.semantic_type == "identifier":
                prefix = self._infer_identifier_prefix(file_spec.file_name, col.name)
                data[col.name] = [f"{prefix}_{i:05d}" for i in range(1, row_count + 1)]
            elif col.semantic_type == "date":
                data[col.name] = self._sample_dates(row_count)
            elif col.semantic_type == "location_country":
                data[col.name] = countries
            elif col.semantic_type == "location_city":
                data[col.name] = cities
            elif col.semantic_type == "free_text_description":
                data[col.name] = [self.rng.choice(DESCRIPTION_OPTIONS) for _ in range(row_count)]
            elif col.semantic_type == "account_name":
                data[col.name] = [self.rng.choice(ACCOUNT_OPTIONS) for _ in range(row_count)]
            elif col.semantic_type in {"localized_amount", "amount"}:
                data[col.name] = self._sample_amounts(row_count)
            elif col.semantic_type == "source_system":
                data[col.name] = [self._infer_source_label(file_spec.file_name)] * row_count
            elif col.semantic_type == "tax_rate":
                country_series = data.get("Country", countries)
                data[col.name] = [TAX_RATE_BY_COUNTRY[country] for country in country_series]
            else:
                data[col.name] = ["N/A"] * row_count

        return pd.DataFrame(data)

    def _apply_traps(self, workbook: GeneratedWorkbook, traps: List[TrapSpec]) -> None:
        for trap in traps:
            if trap.injection_target.file_name != workbook.file_name:
                continue
            sheet = workbook.sheets[trap.injection_target.sheet_name]
            trap_rows = self._select_trap_rows(sheet, trap)
            self.ground_truth.setdefault(workbook.file_name, {"trap_rows": {}})
            self.ground_truth[workbook.file_name]["trap_rows"][trap.trap_id] = trap_rows

            if trap.trap_type == "implicit_currency":
                self._inject_implicit_currency(sheet, trap, trap_rows)
            elif trap.trap_type == "reference_omission":
                self._inject_reference_omission(sheet, trap, trap_rows)

    def _select_trap_rows(self, df: pd.DataFrame, trap: TrapSpec) -> List[int]:
        if trap.trap_type == "reference_omission":
            entities = set(trap.injection_policy.affected_entities)
            matched = df.index[
                df.apply(lambda row: any(str(value) in entities for value in row.values), axis=1)
            ].tolist()
            if matched:
                return matched
        requested = trap.injection_policy.affected_row_count or 1
        return self.rng.sample(list(df.index), min(requested, len(df)))

    def _inject_implicit_currency(self, df: pd.DataFrame, trap: TrapSpec, trap_rows: List[int]) -> None:
        for col in trap.injection_target.columns:
            if col in df.columns and df[col].dtype != object:
                df[col] = df[col].astype(object)

        for row_idx in trap_rows:
            country = df.loc[row_idx, "Country"] if "Country" in df.columns else "France"
            locale_hint = "GBP" if country == "United Kingdom" else "EUR"
            for col in trap.injection_target.columns:
                if col not in df.columns:
                    continue
                raw_value = float(df.loc[row_idx, col])
                if locale_hint == "GBP":
                    df.loc[row_idx, col] = f"{raw_value:,.2f}".replace(",", "")
                else:
                    df.loc[row_idx, col] = f"{raw_value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _inject_reference_omission(self, df: pd.DataFrame, trap: TrapSpec, trap_rows: List[int]) -> None:
        for row_idx in trap_rows:
            for col in trap.injection_target.columns:
                if col in df.columns:
                    df.loc[row_idx, col] = None

    def _write_workbook(self, path: Path, workbook: GeneratedWorkbook) -> None:
        with pd.ExcelWriter(path) as writer:
            for sheet_name, df in workbook.sheets.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)

    def _sample_countries(self, row_count: int) -> List[str]:
        countries = list(COUNTRY_CITY_OPTIONS.keys())
        return [self.rng.choice(countries) for _ in range(row_count)]

    def _sample_dates(self, row_count: int) -> List[str]:
        base = pd.Timestamp("2024-10-01")
        offsets = self.np_rng.integers(0, 31, size=row_count)
        return [(base + pd.Timedelta(days=int(offset))).strftime("%Y-%m-%d") for offset in offsets]

    def _sample_amounts(self, row_count: int) -> List[float]:
        values = self.np_rng.normal(loc=8500.0, scale=3200.0, size=row_count)
        values = np.clip(values, a_min=250.0, a_max=None)
        return [round(float(value), 2) for value in values]

    def _infer_identifier_prefix(self, file_name: str, col_name: str) -> str:
        base = Path(file_name).stem.upper()
        if "ledger" in base.lower():
            return "LEDGER"
        if "tax" in base.lower():
            return "TAX"
        if "receipt" in col_name.lower():
            return "RCPT"
        return base[:6]

    def _infer_source_label(self, file_name: str) -> str:
        lower = file_name.lower()
        if "tour_manager" in lower:
            return "Tour Manager"
        if "production" in lower:
            return "Production Company"
        return "Reference System"
