import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_registry_sampling_readiness import (  # noqa: E402
    RegistrySamplingReadinessAssessor,
    default_existing_reports,
    write_sampling_readiness_report,
)


DEFAULT_REGISTRY_PATH = ROOT / "SkillRegistry" / "v3_skill_registry.json"
DEFAULT_OUTPUT_PATH = ROOT / "SkillRegistry" / "v3_registry_sampling_readiness_report.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a non-destructive sampling readiness report for the persistent V3 skill registry."
    )
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--audit-report",
        type=Path,
        action="append",
        default=[],
        help="Audit report to include. Can be repeated. Defaults to existing SkillRegistry audit reports.",
    )
    parser.add_argument(
        "--calibration-report",
        type=Path,
        action="append",
        default=[],
        help="Reviewer calibration report to include. Can be repeated. Defaults to existing calibration report.",
    )
    parser.add_argument(
        "--no-default-reports",
        action="store_true",
        help="Only use explicitly provided audit/calibration reports.",
    )
    args = parser.parse_args()

    audit_reports = list(args.audit_report)
    calibration_reports = list(args.calibration_report)
    if not args.no_default_reports:
        defaults = default_existing_reports(ROOT)
        audit_reports = audit_reports or defaults["audit_report_paths"]
        calibration_reports = calibration_reports or defaults["calibration_report_paths"]

    assessor = RegistrySamplingReadinessAssessor(repo_root=ROOT)
    report = assessor.assess(
        registry_path=args.registry_path,
        audit_report_paths=audit_reports,
        calibration_report_paths=calibration_reports,
    )
    write_sampling_readiness_report(args.output_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()



