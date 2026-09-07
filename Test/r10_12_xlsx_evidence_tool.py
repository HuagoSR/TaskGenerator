"""Read-only XLSX evidence service staged inside the fixed eval image."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from r10_12_remote_packet_grader_v2 import spreadsheet


ROOT = Path("/workspace")


def build() -> dict:
    result = {}
    for directory in (ROOT / "reference_files", ROOT / "anonymous_submission"):
        for path in sorted(directory.rglob("*.xlsx")):
            relative = path.relative_to(ROOT).as_posix()
            result[relative] = spreadsheet(path, relative)
    if not result:
        raise RuntimeError("xlsx_evidence_no_workbooks")
    output = {"evidence_service_version": "r10.xlsx_evidence_service.1", "workbooks": result}
    (ROOT / "spreadsheet_evidence.json").write_text(
        json.dumps(output, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return output


def query(path: str, sheet: str, cell_range: str) -> dict:
    source = ROOT / "spreadsheet_evidence.json"
    if not source.is_file():
        raise RuntimeError("xlsx_evidence_not_built")
    value = json.loads(source.read_text(encoding="utf-8"))
    workbook = value["workbooks"].get(path)
    if workbook is None:
        raise ValueError("xlsx_evidence_path_unknown")
    tab = next((row for row in workbook["sheets"] if row["name"] == sheet), None)
    if tab is None:
        raise ValueError("xlsx_evidence_sheet_unknown")
    from openpyxl.utils.cell import range_boundaries
    min_col, min_row, max_col, max_row = range_boundaries(cell_range)
    cells = []
    for cell in tab["cells"]:
        col, row, _, _ = range_boundaries(cell["address"])
        if min_col <= col <= max_col and min_row <= row <= max_row:
            cells.append(cell)
    return {
        "relative_path": path,
        "sheet_name": sheet,
        "cell_range": cell_range,
        "cells": cells,
        "diagnostics": [row for row in workbook["diagnostics"] if any(item.startswith(f"{sheet}!") for item in row["locations"])],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build")
    inspect = sub.add_parser("range")
    inspect.add_argument("relative_path")
    inspect.add_argument("sheet_name")
    inspect.add_argument("cell_range")
    args = parser.parse_args()
    value = build() if args.command == "build" else query(args.relative_path, args.sheet_name, args.cell_range)
    print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
