from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_behavioral_preflight_evidence import (  # noqa: E402
    BehavioralPreflightEvidenceAuditor,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recompute behavioral execution evidence integrity without external calls."
    )
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--execution-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = BehavioralPreflightEvidenceAuditor(args.campaign_root).audit(
        args.execution_manifest
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if report.decision == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
