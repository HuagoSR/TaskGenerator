from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_reconstruction_promotion import (  # noqa: E402
    RouteConfirmationCompiler,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compile an artifact-bound route confirmation report without "
            "executing providers, solvers, graders, servers or mutations."
        )
    )
    parser.add_argument("--screening-report", type=Path, required=True)
    parser.add_argument(
        "--gate",
        action="append",
        default=[],
        help="Required form: gate_name=path/to/gate_report.json",
    )
    parser.add_argument("--winning-route", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    gate_paths = {}
    for item in args.gate:
        if "=" not in item:
            parser.error("--gate must use gate_name=path")
        gate, path = item.split("=", 1)
        gate_paths[gate] = Path(path)
    report = RouteConfirmationCompiler().compile(
        screening_report_path=args.screening_report,
        gate_evidence_paths=gate_paths,
        winning_route=args.winning_route,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        report.model_dump_json(indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "comparison_id": report.comparison_id,
                "decision": report.decision,
                "winning_route": report.winning_route,
                "output": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
