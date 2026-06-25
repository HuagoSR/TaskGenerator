import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v2_task_compiler import FinanceAuditTaskCompiler


OUTPUT_DIR = Path(__file__).resolve().parent / "v2_outputs" / "finance_prototype_01"


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
    dataset_shell = compiled["dataset_shell"]
    prompt = compiled["prompt"]

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

    print(f"Wrote V2 prototype artifacts to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
