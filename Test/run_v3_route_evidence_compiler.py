from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_route_evidence_compiler import (  # noqa: E402
    RouteComparisonEvidenceCompiler,
    RouteComparisonEvidenceInputManifestV1,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compile governed route-comparison evidence. This reads existing "
            "offline, solver, grader and professional evidence and makes no "
            "external calls."
        )
    )
    parser.add_argument("--evidence-input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = RouteComparisonEvidenceInputManifestV1.model_validate_json(
        args.evidence_input.read_text(encoding="utf-8")
    )
    report = RouteComparisonEvidenceCompiler().compile(manifest)
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
                "evidence_count": report.evidence_count,
                "blocking_reasons": report.blocking_reasons,
                "output": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if report.decision != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
