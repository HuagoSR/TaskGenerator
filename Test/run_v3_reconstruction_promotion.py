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
    ReconstructionPromotionCompiler,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile a report-only reconstruction promotion record."
    )
    parser.add_argument("--screening-report", type=Path, required=True)
    parser.add_argument("--confirmation-report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    record = ReconstructionPromotionCompiler().compile(
        screening_report_path=args.screening_report,
        confirmation_report_path=args.confirmation_report,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "decision": record.decision,
                "selected_route": record.selected_route,
                "blocking_reasons": record.blocking_reasons,
                "output": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
