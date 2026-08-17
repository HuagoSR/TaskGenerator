from __future__ import annotations

import argparse
import json
from pathlib import Path

from task_generator.v3_huago_cone_eval import (
    R9DualJudgeRunner,
    R9NativeSolverRunner,
    compile_r9_evaluation_records,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one native R9 solver stack on Huago-cone.")
    parser.add_argument(
        "--action", choices=["probe", "solve", "grade", "compile-evaluations"], required=True
    )
    parser.add_argument("--stack")
    parser.add_argument("--judge")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--generation-result", type=Path)
    parser.add_argument("--solver-campaign", type=Path)
    parser.add_argument("--campaign-map", type=Path)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    args = parser.parse_args()
    if args.action in {"probe", "solve"}:
        if args.stack is None:
            parser.error("--stack is required for probe/solve")
        runner = R9NativeSolverRunner(
            stack_id=args.stack,
            output_root=args.output_root,
            timeout_seconds=args.timeout_seconds,
        )
    if args.action == "probe":
        result = runner.public_probe()
    elif args.action == "solve":
        if args.generation_result is None:
            parser.error("--generation-result is required for solve")
        result = runner.solve(generation_result_path=args.generation_result)
    elif args.action == "grade":
        if args.judge is None or args.solver_campaign is None or args.generation_result is None:
            parser.error("--judge, --solver-campaign and --generation-result are required for grade")
        result = R9DualJudgeRunner(
            judge_id=args.judge,
            output_root=args.output_root,
            timeout_seconds=args.timeout_seconds,
        ).grade(
            solver_campaign_path=args.solver_campaign,
            generation_result_path=args.generation_result,
        )
    else:
        if args.campaign_map is None or args.generation_result is None:
            parser.error("--campaign-map and --generation-result are required for compile-evaluations")
        mapping = json.loads(args.campaign_map.read_text(encoding="utf-8"))
        result = compile_r9_evaluation_records(
            generation_result_path=args.generation_result,
            solver_campaign_paths={key: value["solver_campaign"] for key, value in mapping.items()},
            judge_manifest_paths={key: value["judges"] for key, value in mapping.items()},
            output_path=args.output_root / "evaluation_records.json",
        )
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
