from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_formal_brief_admission import (  # noqa: E402
    FormalBriefCohortAdmission,
    SourceProvenanceLedgerCompiler,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile source provenance, hydrate briefs, and run formal cohort admission."
    )
    parser.add_argument("--brief", action="append", type=Path, required=True)
    parser.add_argument("--candidate-file", action="append", type=Path, required=True)
    parser.add_argument("--raw-source", action="append", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-brief-count", type=int, default=4)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    compiler = SourceProvenanceLedgerCompiler()
    ledger = compiler.compile(args.candidate_file, args.raw_source)
    ledger_path = args.output_dir / "source_provenance_ledger.json"
    ledger_path.write_text(ledger.model_dump_json(indent=2), encoding="utf-8")

    admission = FormalBriefCohortAdmission()
    briefs = []
    hydrated_dir = args.output_dir / "hydrated_briefs"
    hydrated_dir.mkdir(parents=True, exist_ok=True)
    for path in args.brief:
        from task_generator.v3_task_design_frontend import CapabilityBriefV1

        brief = CapabilityBriefV1.model_validate_json(path.read_text(encoding="utf-8"))
        hydrated = admission.hydrate_brief(brief, ledger)
        (hydrated_dir / f"{hydrated.brief_id}.json").write_text(
            hydrated.model_dump_json(indent=2), encoding="utf-8"
        )
        briefs.append(hydrated)
    report = admission.evaluate(briefs, ledger, args.expected_brief_count)
    report_path = args.output_dir / "formal_brief_cohort_admission_report.json"
    report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "decision": report.decision,
                "cohort_id": report.cohort_id,
                "ledger_record_count": len(ledger.records),
                "admitted_brief_count": len(report.admitted_brief_ids),
                "blocked_brief_count": len(report.blocked_brief_ids),
                "report_path": str(report_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
