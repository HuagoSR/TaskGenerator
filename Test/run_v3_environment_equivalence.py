import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_environment_equivalence import compare_environments, write_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare local and server Milestone D manifests.")
    parser.add_argument("--local-manifest", required=True)
    parser.add_argument("--remote-manifest", required=True)
    parser.add_argument("--local-acceptance")
    parser.add_argument("--remote-acceptance")
    parser.add_argument("--expected-image-id")
    parser.add_argument("--expected-rw-task-snapshot")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = compare_environments(
        args.local_manifest,
        args.remote_manifest,
        local_acceptance_path=args.local_acceptance,
        remote_acceptance_path=args.remote_acceptance,
        expected_image_id=args.expected_image_id,
        expected_rw_task_snapshot=args.expected_rw_task_snapshot,
    )
    write_report(report, args.output)
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    raise SystemExit(0 if report.decision == "equivalent" else 1)


if __name__ == "__main__":
    main()
