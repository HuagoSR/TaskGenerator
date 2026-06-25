import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_BATCH_DIR = ROOT / "Test" / "v2_outputs" / "rw_task_batch_finance_01"
DEFAULT_QUALITY_REPORT = ROOT / "Test" / "v2_outputs" / "finance_batch_01" / "quality_report.json"
DEFAULT_EVAL_INPUT_DIR = ROOT / "Test" / "v2_outputs" / "rw_task_eval_selected"
DEFAULT_EVAL_OUTPUT_DIR = ROOT / "Test" / "v2_outputs" / "rw_task_eval_selected_results"
DEFAULT_GRADE_OUTPUT_DIR = ROOT / "Test" / "v2_outputs" / "rw_task_eval_selected_grades"
RW_TASK_ROOT = Path(r"E:\THU\2026Spring\SRT\rw-task")
REAL_WORLD_TASK_PYTHON = Path(r"D:\miniconda3\envs\real-world-task\python.exe")


def select_tasks(quality_report_path: Path, top_k: int, min_score: float) -> list[str]:
    report = json.loads(quality_report_path.read_text(encoding="utf-8"))
    chosen = []
    for row in report:
        if float(row["total_score"]) < min_score:
            continue
        chosen.append(str(row["task_id"]))
        if len(chosen) >= top_k:
            break
    return chosen


def prepare_eval_input(batch_dir: Path, eval_input_dir: Path, task_ids: list[str]) -> None:
    if eval_input_dir.exists():
        shutil.rmtree(eval_input_dir)
    eval_input_dir.mkdir(parents=True, exist_ok=True)

    for task_id in task_ids:
        src = batch_dir / task_id
        if not src.exists():
            raise FileNotFoundError(f"Missing task case: {src}")
        shutil.copytree(src, eval_input_dir / task_id)


def run_command(command: list[str], cwd: Path) -> None:
    proc = subprocess.run(command, cwd=str(cwd), check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {proc.returncode}: {' '.join(command)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Select top-quality rw-task cases, run evaluation, and grade them.")
    parser.add_argument("--top-k", type=int, default=1, help="How many tasks to select from the quality report.")
    parser.add_argument("--min-score", type=float, default=72.0, help="Minimum static quality score to include.")
    parser.add_argument("--model", default="gpt-5-mini", help="Model name passed to stirrup batch runner.")
    parser.add_argument("--workers", type=int, default=1, help="Worker count for stirrup batch runner.")
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH_DIR, help="Directory containing rw-task cases.")
    parser.add_argument("--quality-report", type=Path, default=DEFAULT_QUALITY_REPORT, help="Static quality report JSON.")
    parser.add_argument("--eval-input-dir", type=Path, default=DEFAULT_EVAL_INPUT_DIR, help="Prepared eval input directory.")
    parser.add_argument("--eval-output-dir", type=Path, default=DEFAULT_EVAL_OUTPUT_DIR, help="rw-task run output directory.")
    parser.add_argument("--grade-output-dir", type=Path, default=DEFAULT_GRADE_OUTPUT_DIR, help="rw-task grade output directory.")
    args = parser.parse_args()

    task_ids = select_tasks(args.quality_report, args.top_k, args.min_score)
    if not task_ids:
        raise RuntimeError("No tasks satisfied the selection criteria.")

    prepare_eval_input(args.batch_dir, args.eval_input_dir, task_ids)

    if args.eval_output_dir.exists():
        shutil.rmtree(args.eval_output_dir)
    if args.grade_output_dir.exists():
        shutil.rmtree(args.grade_output_dir)
    args.eval_output_dir.mkdir(parents=True, exist_ok=True)
    args.grade_output_dir.mkdir(parents=True, exist_ok=True)

    batch_cmd = [
        str(REAL_WORLD_TASK_PYTHON),
        "-m",
        "bench_standalone.stirrup_batch",
        str(args.eval_input_dir),
        "--output",
        str(args.eval_output_dir),
        "-w",
        str(args.workers),
        "--model",
        args.model,
    ]
    grade_cmd = [
        str(REAL_WORLD_TASK_PYTHON),
        "-m",
        "bench_standalone.grade_deliverables",
        str(args.eval_output_dir),
        "--out-dir",
        str(args.grade_output_dir),
    ]

    print(f"Selected tasks: {task_ids}")
    print(f"Prepared eval input: {args.eval_input_dir}")
    run_command(batch_cmd, RW_TASK_ROOT)
    run_command(grade_cmd, RW_TASK_ROOT)
    print(f"Evaluation outputs: {args.eval_output_dir}")
    print(f"Grading outputs: {args.grade_output_dir}")


if __name__ == "__main__":
    main()
