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

COMPACT_COUNTRY_LABEL = {
    "United Kingdom": "UK",
    "France": "France",
    "Germany": "Germany",
    "Spain": "Spain",
    "Netherlands": "Netherlands",
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
    "Band & Crew",
    "Hotel & Restaurants",
    "Venue & Production",
    "Other Costs",
]

FINANCE_TOUR_PROFILES = [
    {
        "tour_rows": [
            ("Show 1", "2024-10-07", "London", "United Kingdom", 230754.0),
            ("Show 2", "2024-10-09", "Paris", "France", 175880.0),
            ("Show 3", "2024-10-10", "Paris", "France", 168432.0),
            ("Show 4", "2024-10-12", "Barcelona", "Spain", 125932.0),
            ("Show 5", "2024-10-14", "Madrid", "Spain", 110823.0),
            ("Show 6", "2024-10-16", "Munich", "Germany", 99117.0),
            ("Show 7", "2024-10-18", "Berlin", "Germany", 132812.0),
        ],
        "expense_rows": [
            ("Band & Crew", "10 members", 345000.0),
            ("Hotel & Restaurants", "London", 34200.0),
            ("Hotel & Restaurants", "Paris", 41800.0),
            ("Hotel & Restaurants", "Barcelona", 22150.0),
            ("Hotel & Restaurants", "Madrid", 23750.0),
            ("Hotel & Restaurants", "Munich", 29640.0),
            ("Hotel & Restaurants", "Berlin", 31860.0),
            ("Venue & Production", "Equipment Rental", 82400.0),
            ("Venue & Production", "Ground Transport", 38220.0),
            ("Venue & Production", "Lighting Support", 90480.0),
            ("Venue & Production", "Backline", 38400.0),
            ("Other Costs", "Insurance", 29610.0),
            ("Other Costs", "Freight", 48240.0),
            ("Other Costs", "Petty Cash", 12000.0),
        ],
    },
    {
        "tour_rows": [
            ("Show 1", "2024-08-03", "Manchester", "United Kingdom", 198640.0),
            ("Show 2", "2024-08-05", "Lyon", "France", 149520.0),
            ("Show 3", "2024-08-07", "Marseille", "France", 157330.0),
            ("Show 4", "2024-08-10", "Valencia", "Spain", 118944.0),
            ("Show 5", "2024-08-12", "Madrid", "Spain", 121875.0),
            ("Show 6", "2024-08-15", "Hamburg", "Germany", 102410.0),
            ("Show 7", "2024-08-17", "Berlin", "Germany", 128560.0),
        ],
        "expense_rows": [
            ("Band & Crew", "11 members", 328000.0),
            ("Hotel & Restaurants", "Manchester", 28110.0),
            ("Hotel & Restaurants", "Lyon", 24680.0),
            ("Hotel & Restaurants", "Marseille", 27120.0),
            ("Hotel & Restaurants", "Valencia", 21490.0),
            ("Hotel & Restaurants", "Madrid", 23340.0),
            ("Hotel & Restaurants", "Hamburg", 26570.0),
            ("Hotel & Restaurants", "Berlin", 28980.0),
            ("Venue & Production", "Venue Rebills", 73400.0),
            ("Venue & Production", "Lighting Support", 84500.0),
            ("Venue & Production", "Backline", 36220.0),
            ("Other Costs", "Ground Transport", 34100.0),
            ("Other Costs", "Insurance", 25400.0),
            ("Other Costs", "Freight", 43860.0),
        ],
    },
    {
        "tour_rows": [
            ("Show 1", "2024-11-02", "Bristol", "United Kingdom", 186420.0),
            ("Show 2", "2024-11-05", "Paris", "France", 172240.0),
            ("Show 3", "2024-11-07", "Lyon", "France", 164980.0),
            ("Show 4", "2024-11-10", "Barcelona", "Spain", 134760.0),
            ("Show 5", "2024-11-12", "Valencia", "Spain", 119305.0),
            ("Show 6", "2024-11-15", "Munich", "Germany", 108560.0),
            ("Show 7", "2024-11-18", "Hamburg", "Germany", 125740.0),
            ("Show 8", "2024-11-20", "Berlin", "Germany", 138490.0),
        ],
        "expense_rows": [
            ("Band & Crew", "12 members", 392000.0),
            ("Hotel & Restaurants", "Bristol", 24940.0),
            ("Hotel & Restaurants", "Paris", 39210.0),
            ("Hotel & Restaurants", "Lyon", 26880.0),
            ("Hotel & Restaurants", "Barcelona", 24760.0),
            ("Hotel & Restaurants", "Valencia", 21940.0),
            ("Hotel & Restaurants", "Munich", 29840.0),
            ("Hotel & Restaurants", "Hamburg", 27430.0),
            ("Hotel & Restaurants", "Berlin", 31560.0),
            ("Venue & Production", "PA and Staging", 96400.0),
            ("Venue & Production", "Backline", 41800.0),
            ("Other Costs", "Ground Transport", 38980.0),
            ("Other Costs", "Insurance", 28320.0),
            ("Other Costs", "Freight", 46120.0),
        ],
    },
    {
        "tour_rows": [
            ("Show 1", "2024-09-04", "London", "United Kingdom", 221340.0),
            ("Show 2", "2024-09-07", "Paris", "France", 181460.0),
            ("Show 3", "2024-09-09", "Marseille", "France", 152740.0),
            ("Show 4", "2024-09-12", "Madrid", "Spain", 127620.0),
            ("Show 5", "2024-09-14", "Barcelona", "Spain", 129880.0),
            ("Show 6", "2024-09-17", "Berlin", "Germany", 141530.0),
            ("Show 7", "2024-09-19", "Munich", "Germany", 112840.0),
        ],
        "expense_rows": [
            ("Band & Crew", "10 members", 336000.0),
            ("Hotel & Restaurants", "London", 32650.0),
            ("Hotel & Restaurants", "Paris", 40330.0),
            ("Hotel & Restaurants", "Marseille", 23840.0),
            ("Hotel & Restaurants", "Madrid", 24120.0),
            ("Hotel & Restaurants", "Barcelona", 25220.0),
            ("Hotel & Restaurants", "Berlin", 31710.0),
            ("Hotel & Restaurants", "Munich", 28640.0),
            ("Venue & Production", "Equipment Rental", 78100.0),
            ("Venue & Production", "Lighting Support", 88750.0),
            ("Venue & Production", "Venue Labor", 36420.0),
            ("Other Costs", "Ground Transport", 35920.0),
            ("Other Costs", "Insurance", 27280.0),
            ("Other Costs", "Freight", 45210.0),
        ],
    },
    {
        "tour_rows": [
            ("Show 1", "2024-07-05", "Manchester", "United Kingdom", 214980.0),
            ("Show 2", "2024-07-08", "Paris", "France", 169240.0),
            ("Show 3", "2024-07-10", "Lyon", "France", 158610.0),
            ("Show 4", "2024-07-13", "Madrid", "Spain", 124330.0),
            ("Show 5", "2024-07-15", "Valencia", "Spain", 117420.0),
            ("Show 6", "2024-07-18", "Munich", "Germany", 104980.0),
            ("Show 7", "2024-07-20", "Berlin", "Germany", 136250.0),
            ("Show 8", "2024-07-22", "Hamburg", "Germany", 109430.0),
        ],
        "expense_rows": [
            ("Band & Crew", "11 members", 358000.0),
            ("Hotel & Restaurants", "Manchester", 29640.0),
            ("Hotel & Restaurants", "Paris", 38120.0),
            ("Hotel & Restaurants", "Lyon", 25780.0),
            ("Hotel & Restaurants", "Madrid", 23240.0),
            ("Hotel & Restaurants", "Valencia", 21480.0),
            ("Hotel & Restaurants", "Munich", 28730.0),
            ("Hotel & Restaurants", "Berlin", 30410.0),
            ("Hotel & Restaurants", "Hamburg", 26390.0),
            ("Venue & Production", "Stage and Rigging", 91800.0),
            ("Venue & Production", "Backline", 40260.0),
            ("Other Costs", "Ground Transport", 37240.0),
            ("Other Costs", "Insurance", 26950.0),
            ("Other Costs", "Freight", 43880.0),
        ],
    },
]


@dataclass
class GeneratedWorkbook:
    file_name: str
    sheets: Dict[str, pd.DataFrame] = field(default_factory=dict)


class V2BlueprintFileGenerator:
    def __init__(self, seed: int = 42, profile_index: int | None = None):
        self.seed = seed
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)
        self.ground_truth: Dict[str, Dict[str, List[int] | Dict[str, List[int]]]] = {}
        chosen_index = seed % len(FINANCE_TOUR_PROFILES) if profile_index is None else profile_index % len(FINANCE_TOUR_PROFILES)
        self.profile = FINANCE_TOUR_PROFILES[chosen_index]

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
        if file_spec.file_name == "fall_music_tour_ref_file.xlsx":
            return self._build_finance_template_sheet(sheet_spec)
        if file_spec.file_name == "production_company_costs.xlsx":
            return self._build_production_cost_sheet(sheet_spec)

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
            elif col.semantic_type == "location_country_compact":
                data[col.name] = [COMPACT_COUNTRY_LABEL[country] for country in countries]
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

    def _build_finance_template_sheet(self, sheet_spec: SheetSpec) -> pd.DataFrame:
        if sheet_spec.sheet_name == "Inc_Costs_Tracked_by_Tour_Mgr":
            rows = self.profile["tour_rows"]
            return pd.DataFrame(
                {
                    "Line_Type": [row[0] for row in rows],
                    "Tour_Date": [row[1] for row in rows],
                    "City": [row[2] for row in rows],
                    "Country": [COMPACT_COUNTRY_LABEL[row[3]] for row in rows],
                    "Gross_Revenue": [row[4] for row in rows],
                }
            )

        if sheet_spec.sheet_name == "Assump_Withholding_Tax":
            rows = [
                ("UK", 0.20),
                ("France", 0.15),
                ("Spain", 0.24),
                ("Germany", 0.15825),
                ("Netherlands", 0.19),
                ("Notes", None),
            ]
            return pd.DataFrame(rows, columns=["Country", "Withholding_Tax_Rate"])

        return pd.DataFrame()

    def _build_production_cost_sheet(self, sheet_spec: SheetSpec) -> pd.DataFrame:
        rows = self.profile["expense_rows"]
        return pd.DataFrame(rows, columns=["Cost_Category", "Cost_Item", "Amount_USD"])

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
            locale_hint = "GBP" if country in {"United Kingdom", "UK"} else "EUR"
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
