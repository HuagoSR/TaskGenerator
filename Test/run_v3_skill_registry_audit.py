import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v3_skill_registry_audit import SkillRegistryAuditor, write_audit_report  # noqa: E402


DEFAULT_REGISTRY_PATH = ROOT / "SkillRegistry" / "v3_skill_registry.json"
DEFAULT_UPDATE_REPORT_PATH = ROOT / "SkillRegistry" / "v3_skill_registry_update_report.json"
DEFAULT_AUDIT_REPORT_PATH = ROOT / "SkillRegistry" / "v3_skill_registry_audit_report.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit the persistent V3 registry without modifying it.")
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--update-report-path", type=Path, default=DEFAULT_UPDATE_REPORT_PATH)
    parser.add_argument("--audit-report-path", type=Path, default=DEFAULT_AUDIT_REPORT_PATH)
    parser.add_argument("--include-all", action="store_true", help="Audit all registry entries instead of only unmatched entries.")
    args = parser.parse_args()

    auditor = SkillRegistryAuditor()
    report = auditor.audit_registry(
        registry_path=args.registry_path,
        update_report_path=args.update_report_path,
        include_all=args.include_all,
    )
    write_audit_report(args.audit_report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
