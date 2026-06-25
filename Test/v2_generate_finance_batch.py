import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from FileGenerator.v2_blueprint_generator import V2BlueprintFileGenerator
from rw_task_adapter import RwTaskCaseExporter
from v2_golden_run import FinanceAuditGoldenRunExecutor
from v2_task_quality import FinanceTaskQualityScorer
from v2_task_compiler import FinanceAuditTaskCompiler


BATCH_DIR = Path(__file__).resolve().parent / "v2_outputs" / "finance_batch_01"
RW_TASK_BATCH_DIR = Path(__file__).resolve().parent / "v2_outputs" / "rw_task_batch_finance_01"

SELECTED_SKILLS = [
    "load_multi_source_financials",
    "infer_implicit_currency",
    "handle_missing_tax_rate",
    "categorize_operating_expense",
    "aggregate_source_level_pnl",
]

SCENARIO_CONFIGS = [
    {
        "slug": "music_tour_q4",
        "scenario_title": "2024 Fall Music Tour Reconciliation",
        "task_goal": "Produce a consolidated cross-source profit and loss report for executive review.",
        "seed": 42,
    },
    {
        "slug": "festival_closeout",
        "scenario_title": "European Festival Closeout Review",
        "task_goal": "Prepare a post-event financial closeout package covering cross-border revenues, withholding taxes, and operating expenses.",
        "seed": 77,
    },
    {
        "slug": "artist_project_margin",
        "scenario_title": "International Artist Project Margin Review",
        "task_goal": "Reconcile multi-entity operating records into a source-level profitability view for management review.",
        "seed": 123,
    },
]


def main() -> None:
    if BATCH_DIR.exists():
        shutil.rmtree(BATCH_DIR)
    if RW_TASK_BATCH_DIR.exists():
        shutil.rmtree(RW_TASK_BATCH_DIR)
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    RW_TASK_BATCH_DIR.mkdir(parents=True, exist_ok=True)

    compiler = FinanceAuditTaskCompiler()
    golden_executor = FinanceAuditGoldenRunExecutor()
    rw_task_exporter = RwTaskCaseExporter()
    quality_scorer = FinanceTaskQualityScorer()

    manifest = []

    for config in SCENARIO_CONFIGS:
        compiled = compiler.compile(
            selected_skill_ids=SELECTED_SKILLS,
            scenario_title=config["scenario_title"],
            task_goal=config["task_goal"],
        )

        blueprint = compiled["blueprint"]
        annotation = compiled["training_annotation"]
        golden_run = compiled["golden_run"]
        dataset_shell = compiled["dataset_shell"]

        case_dir = BATCH_DIR / dataset_shell.task_id
        reference_dir = case_dir / "reference_files"
        golden_dir = case_dir / "golden_run"

        file_generator = V2BlueprintFileGenerator(seed=config["seed"])
        ground_truth = file_generator.generate_reference_files(blueprint, reference_dir)
        dataset_shell.extra["ground_truth"] = ground_truth

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

        (case_dir / "task_blueprint.json").write_text(blueprint.model_dump_json(indent=2), encoding="utf-8")
        (case_dir / "training_annotation.json").write_text(annotation.model_dump_json(indent=2), encoding="utf-8")
        (case_dir / "golden_run_package.json").write_text(golden_run.model_dump_json(indent=2), encoding="utf-8")
        (case_dir / "dataset_shell.json").write_text(dataset_shell.model_dump_json(indent=2), encoding="utf-8")
        (case_dir / "prompt.md").write_text(compiled["prompt"], encoding="utf-8")
        (case_dir / "golden_prompt.md").write_text(golden_run.golden_prompt, encoding="utf-8")

        rw_task_case_dir = rw_task_exporter.export_case(
            dataset_shell=dataset_shell,
            blueprint=blueprint,
            annotation=annotation,
            golden_run=golden_run,
            reference_dir=reference_dir,
            output_case_dir=RW_TASK_BATCH_DIR / dataset_shell.task_id,
        )

        manifest.append(
            {
                "task_id": dataset_shell.task_id,
                "slug": config["slug"],
                "seed": config["seed"],
                "scenario_title": config["scenario_title"],
                "case_dir": str(case_dir),
                "rw_task_case_dir": str(rw_task_case_dir),
                "overall_totals": golden_artifacts.grading_anchors["golden_targets"]["final_pnl_totals"]["expected_value"]["overall_totals"],
                "rubric_item_count": len(json.loads(json.loads((rw_task_case_dir / "dataset_row.json").read_text(encoding="utf-8"))["rubric_json"])),
            }
        )

    (BATCH_DIR / "batch_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    quality_results = quality_scorer.write_batch_reports(
        batch_dir=BATCH_DIR,
        rw_task_batch_dir=RW_TASK_BATCH_DIR,
        output_json_path=BATCH_DIR / "quality_report.json",
        output_md_path=BATCH_DIR / "quality_summary.md",
    )

    print(f"Wrote finance batch to {BATCH_DIR}")
    print(f"Exported rw-task batch to {RW_TASK_BATCH_DIR}")
    print(f"Generated {len(manifest)} cases")
    if quality_results:
        print(f"Top static-quality case: {quality_results[0].task_id} ({quality_results[0].total_score})")


if __name__ == "__main__":
    main()
