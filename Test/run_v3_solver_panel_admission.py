from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_solver_panel_admission import (  # noqa: E402
    SolverPanelAdmissionCompiler,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile retain/replace solver-panel admission without external calls."
    )
    parser.add_argument("--frozen-panel", type=Path, required=True)
    parser.add_argument("--evidence-integrity", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--replacement-boundary-output", type=Path)
    args = parser.parse_args()
    plan = SolverPanelAdmissionCompiler().compile(
        frozen_panel_path=args.frozen_panel,
        evidence_integrity_path=args.evidence_integrity,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2))
    if args.replacement_boundary_output:
        boundary = SolverPanelAdmissionCompiler().compile_replacement_boundary(
            admission_plan_path=args.output
        )
        args.replacement_boundary_output.parent.mkdir(parents=True, exist_ok=True)
        args.replacement_boundary_output.write_text(
            boundary.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                boundary.model_dump(mode="json"), ensure_ascii=False, indent=2
            )
        )


if __name__ == "__main__":
    main()
