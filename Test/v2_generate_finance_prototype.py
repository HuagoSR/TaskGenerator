import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.FileGenerator.v2_blueprint_generator import V2BlueprintFileGenerator
from task_generator.rw_task_adapter import RwTaskCaseExporter
from task_generator.v2_golden_run import FinanceAuditGoldenRunExecutor
from task_generator.v2_task_compiler import FinanceAuditTaskCompiler


OUTPUT_DIR = Path(__file__).resolve().parent / "v2_outputs" / "finance_prototype_01"
RW_TASK_BATCH_DIR = Path(__file__).resolve().parent / "v2_outputs" / "rw_task_batch_finance_prototype"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    compiler = FinanceAuditTaskCompiler()
    compiled = compiler.compile(
        [
            "load_multi_source_financials",
            "infer_implicit_currency",
            "handle_missing_tax_rate",
            "categorize_operating_expense",
            "aggregate_source_level_pnl",
        ]
    )

    blueprint = compiled["blueprint"]
    annotation = compiled["training_annotation"]
    golden_run = compiled["golden_run"]
    dataset_shell = compiled["dataset_shell"]
    prompt = compiled["prompt"]
    file_generator = V2BlueprintFileGenerator(seed=42)
    golden_executor = FinanceAuditGoldenRunExecutor()
    rw_task_exporter = RwTaskCaseExporter()

    reference_dir = OUTPUT_DIR / "reference_files"
    ground_truth = file_generator.generate_reference_files(blueprint, reference_dir)
    dataset_shell.extra["ground_truth"] = ground_truth
    golden_dir = OUTPUT_DIR / "golden_run"
    golden_artifacts = golden_executor.execute(
        blueprint=blueprint,
        annotation=annotation,
        golden_run=golden_run,
        reference_dir=reference_dir,
        output_dir=golden_dir,
    )
    dataset_shell.extra["golden_run_outputs"] = {
        "intermediate_values": golden_artifacts.intermediate_values,
        "grading_anchors": golden_artifacts.grading_anchors,
        "run_log": golden_artifacts.run_log,
    }
    rw_task_case_dir = rw_task_exporter.export_case(
        dataset_shell=dataset_shell,
        blueprint=blueprint,
        annotation=annotation,
        golden_run=golden_run,
        reference_dir=reference_dir,
        output_case_dir=RW_TASK_BATCH_DIR / dataset_shell.task_id,
    )

    (OUTPUT_DIR / "task_blueprint.json").write_text(
        blueprint.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "training_annotation.json").write_text(
        annotation.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "dataset_shell.json").write_text(
        dataset_shell.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "prompt.md").write_text(prompt, encoding="utf-8")
    (OUTPUT_DIR / "golden_prompt.md").write_text(golden_run.golden_prompt, encoding="utf-8")
    (OUTPUT_DIR / "golden_run_package.json").write_text(
        golden_run.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "rw_task_case_path.txt").write_text(str(rw_task_case_dir), encoding="utf-8")

    print(f"Wrote V2 prototype artifacts to {OUTPUT_DIR}")
    print(f"Exported rw-task case to {rw_task_case_dir}")


if __name__ == "__main__":
    main()



