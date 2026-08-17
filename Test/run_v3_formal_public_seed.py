from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_domain_profile import (  # noqa: E402
    DEFAULT_DOMAIN_PROFILE_PATH,
    load_domain_profile,
)
from task_generator.v3_formal_public_seed import FormalPublicSeedCompiler  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile a report-only public-source formal seed."
    )
    parser.add_argument("--registry-path", type=Path, required=True)
    parser.add_argument("--readiness-report", type=Path, required=True)
    parser.add_argument("--web-audit-report", type=Path, required=True)
    parser.add_argument("--provenance-ledger", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--domain-profile", default="finance_audit")
    parser.add_argument(
        "--domain-profile-path", type=Path, default=DEFAULT_DOMAIN_PROFILE_PATH
    )
    args = parser.parse_args()
    report = FormalPublicSeedCompiler().compile(
        registry_path=args.registry_path,
        readiness_report_path=args.readiness_report,
        web_audit_report_path=args.web_audit_report,
        provenance_ledger_path=args.provenance_ledger,
        output_dir=args.output_dir,
        domain_profile=load_domain_profile(
            args.domain_profile, args.domain_profile_path
        ),
    )
    report_path = args.output_dir / "formal_public_seed_compile_report.json"
    report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "decision": report.decision,
                "public_source_skill_count": report.public_source_skill_count,
                "admitted_skill_count": report.admitted_skill_count,
                "seed_report_path": report.seed_report_path,
                "report_path": str(report_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
