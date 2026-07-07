from __future__ import annotations

import argparse
import asyncio
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run bench_standalone.stirrup_batch with TaskGenerator-safe runtime overrides."
    )
    parser.add_argument("--agent-max-tokens", type=int, default=16000)
    parser.add_argument("input_path", type=Path)
    parser.add_argument("--output", metavar="DIR", default=None)
    parser.add_argument("-w", "--workers", type=int, default=1)
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--e2b-template", default="rw-task-sandbox:stable")
    args = parser.parse_args()

    from bench_standalone import stirrup_batch

    stirrup_batch.MAX_TOKENS = args.agent_max_tokens
    input_path = args.input_path.resolve()
    if not input_path.exists():
        raise SystemExit(f"Error: input path does not exist: {input_path}")
    if args.output:
        output_batch_dir = Path(args.output).resolve()
        print(f"[Resume] Output directory : {output_batch_dir}")
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_batch_dir = (Path(stirrup_batch.OUTPUT_BASE) / f"batch_run_{timestamp}").resolve()
        print(f"[New]    Output directory : {output_batch_dir}")
    output_batch_dir.mkdir(parents=True, exist_ok=True)
    log_dir = output_batch_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    test_cases = stirrup_batch.find_test_cases(input_path)
    print(f"Input directory  : {input_path}")
    print(f"Test cases found : {len(test_cases)}")
    print(f"Workers          : {args.workers} (TaskGenerator wrapper runs sequentially)")
    print(f"Model            : {args.model}")
    print(f"E2B template     : {args.e2b_template}")
    print(f"Agent max tokens : {stirrup_batch.MAX_TOKENS}")
    print()
    if not test_cases:
        raise SystemExit(f"No test case found under {input_path}")

    succeeded = 0
    failed = 0
    skipped = 0
    for case_dir in test_cases:
        with (case_dir / stirrup_batch.DATASET_ROW_FILENAME).open(encoding="utf-8") as fh:
            task_id = json.load(fh)["task_id"]
        safe = stirrup_batch._safe_name(case_dir.name)
        output_run_dir = output_batch_dir / f"run_{safe}"
        log_file = log_dir / f"{safe}.txt"
        if stirrup_batch.is_completed(output_run_dir):
            print(f"  [SKIP] {task_id}  ({case_dir.name})")
            skipped += 1
            continue
        try:
            with log_file.open("w", encoding="utf-8", buffering=1) as log:
                with redirect_stdout(log), redirect_stderr(log):
                    asyncio.run(stirrup_batch._run_async(case_dir, output_run_dir, args.model, args.e2b_template))
            print(f"  [OK]   {task_id}")
            succeeded += 1
        except Exception as exc:
            with log_file.open("a", encoding="utf-8", buffering=1) as log:
                print(f"\n[ERROR] {type(exc).__name__}: {exc}", file=log)
            print(f"  [FAIL] {task_id}  (see {log_file})")
            failed += 1

    print()
    print("=== Batch Run Complete ===")
    print(f"Total    : {len(test_cases)}")
    print(f"Skipped  : {skipped}")
    print(f"Succeeded: {succeeded}")
    print(f"Failed   : {failed}")
    print(f"Output   : {output_batch_dir}")
    print(f"Logs     : {log_dir}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
