import json
import shutil
from pathlib import Path
from typing import Dict, List

from v2_schema import GoldenRun, TaskBlueprint, TrainingAnnotation, V2DatasetPackage


class RwTaskCaseExporter:
    def export_case(
        self,
        dataset_shell: V2DatasetPackage,
        blueprint: TaskBlueprint,
        annotation: TrainingAnnotation,
        golden_run: GoldenRun,
        reference_dir: str | Path,
        output_case_dir: str | Path,
    ) -> Path:
        case_dir = Path(output_case_dir)
        reference_src = Path(reference_dir)
        reference_dst = case_dir / "reference_files"
        deliverable_dir = case_dir / "deliverable_files"

        if case_dir.exists():
            shutil.rmtree(case_dir)
        reference_dst.mkdir(parents=True, exist_ok=True)
        deliverable_dir.mkdir(parents=True, exist_ok=True)

        for file_path in reference_src.iterdir():
            if file_path.is_file():
                shutil.copy2(file_path, reference_dst / file_path.name)

        dataset_row = self._build_dataset_row(
            dataset_shell=dataset_shell,
            blueprint=blueprint,
            annotation=annotation,
            golden_run=golden_run,
        )
        with open(case_dir / "dataset_row.json", "w", encoding="utf-8") as f:
            json.dump(dataset_row, f, ensure_ascii=False, indent=2)

        return case_dir

    def _build_dataset_row(
        self,
        dataset_shell: V2DatasetPackage,
        blueprint: TaskBlueprint,
        annotation: TrainingAnnotation,
        golden_run: GoldenRun,
    ) -> Dict[str, object]:
        rubric_items = self._build_export_rubric_items(dataset_shell, blueprint, annotation)
        normalized_rubric = self._normalize_rubric_items(rubric_items)
        deliverable_paths = [f"deliverable_files/{Path(path).name}" for path in dataset_shell.deliverable_files]

        extra = dict(dataset_shell.extra)
        extra["rw_task_adapter"] = {
            "source": "TaskGenerator V2",
            "blueprint_id": blueprint.blueprint_id,
            "golden_run_id": golden_run.golden_run_id,
            "training_annotation_id": annotation.annotation_id,
        }

        return {
            "task_id": dataset_shell.task_id,
            "sector": blueprint.task_metadata.sector,
            "occupation": blueprint.task_metadata.occupation,
            "motif": self._infer_motif(annotation),
            "prompt": dataset_shell.prompt,
            "reference_files": [f"reference_files/{Path(path).name}" for path in dataset_shell.reference_files],
            "deliverable_files": deliverable_paths,
            "rubric": self._build_rw_task_rubric_text(normalized_rubric),
            "rubric_json": json.dumps(normalized_rubric, ensure_ascii=False),
            "extra": extra,
        }

    def _build_export_rubric_items(
        self,
        dataset_shell: V2DatasetPackage,
        blueprint: TaskBlueprint,
        annotation: TrainingAnnotation,
    ) -> List[Dict[str, object]]:
        golden_outputs = dataset_shell.extra.get("golden_run_outputs") or {}
        grading_anchors = golden_outputs.get("grading_anchors") or {}
        golden_targets = grading_anchors.get("golden_targets") or {}
        intermediate_targets = grading_anchors.get("intermediate_targets") or {}
        summary = ((golden_targets.get("final_pnl_totals") or {}).get("expected_value") or {})

        if not summary:
            return json.loads(dataset_shell.rubric_json)

        rubric_items: List[Dict[str, object]] = []
        row_id = 1

        for source_row in summary.get("by_source", []):
            source_name = source_row["source_name"]
            rubric_items.extend(
                [
                    self._make_rubric_item(row_id, 3, f"The submission reports `{source_name}` revenue in USD consistent with the golden run totals.", ["outcome"]),
                    self._make_rubric_item(row_id + 1, 3, f"The submission reports `{source_name}` expenses in USD consistent with the golden run totals.", ["outcome"]),
                    self._make_rubric_item(row_id + 2, 3, f"The submission reports `{source_name}` net income consistent with the golden run totals.", ["outcome"]),
                ]
            )
            row_id += 3

        overall = summary.get("overall_totals") or {}
        if overall:
            rubric_items.extend(
                [
                    self._make_rubric_item(row_id, 4, "The overall revenue total matches the golden run within normal rounding tolerance.", ["outcome"]),
                    self._make_rubric_item(row_id + 1, 4, "The overall expense total matches the golden run within normal rounding tolerance.", ["outcome"]),
                    self._make_rubric_item(row_id + 2, 4, "The overall net income total matches the golden run within normal rounding tolerance.", ["outcome"]),
                ]
            )
            row_id += 3

        if "currency_resolution_mapping" in intermediate_targets.get("required_states", []):
            rubric_items.append(
                self._make_rubric_item(
                    row_id,
                    3,
                    "Rows with implicit local formatting are normalized using jurisdiction-aware currency reasoning instead of being summed as raw strings.",
                    ["reasoning", "robustness"],
                )
            )
            row_id += 1

        tax_events = intermediate_targets.get("tax_resolution_events") or []
        if tax_events:
            rubric_items.append(
                self._make_rubric_item(
                    row_id,
                    3,
                    "Missing withholding-tax reference values are detected and resolved with an explicit, defensible assumption rather than silently ignored.",
                    ["reasoning", "robustness"],
                )
            )
            row_id += 1

        if "expense_bucket_mapping" in intermediate_targets.get("required_states", []):
            rubric_items.append(
                self._make_rubric_item(
                    row_id,
                    3,
                    "Operating expenses are mapped into a consistent reporting taxonomy before final aggregation.",
                    ["reasoning"],
                )
            )
            row_id += 1

        rubric_items.append(
            self._make_rubric_item(
                row_id,
                2,
                "Required deliverables exist with the requested filenames and appear professionally structured for business review.",
                ["compliance"],
            )
        )
        row_id += 1

        for projected_check in annotation.rubric_projection.reasoning_checks:
            rubric_items.append(
                self._make_rubric_item(
                    row_id,
                    2,
                    projected_check,
                    ["reasoning"],
                )
            )
            row_id += 1

        return rubric_items

    def _make_rubric_item(self, row_id: int, score: int, criterion: str, tags: List[str]) -> Dict[str, object]:
        return {
            "score": score,
            "criterion": criterion,
            "required": True,
            "rubric_item_id": f"R_{row_id:03d}",
            "author_type": "model",
            "tags": tags,
            "read_only": None,
            "form_content": None,
        }

    def _normalize_rubric_items(self, rubric_items: List[Dict[str, object]]) -> List[Dict[str, object]]:
        normalized = []
        for item in rubric_items:
            tags = item.get("tags") or []
            normalized.append(
                {
                    "score": int(item.get("score", 0)),
                    "criterion": str(item.get("criterion", "")),
                    "required": True,
                    "rubric_item_id": str(item.get("rubric_item_id", "")),
                    "author_type": "model",
                    "tags": tags,
                    "read_only": None,
                    "form_content": None,
                }
            )
        return normalized

    def _build_rw_task_rubric_text(self, rubric_items: List[Dict[str, object]]) -> str:
        lines = []
        for item in rubric_items:
            lines.append(f"- [+{item['score']}] {item['criterion']}")
        return "\n".join(lines)

    def _infer_motif(self, annotation: TrainingAnnotation) -> str:
        primary = set(annotation.capability_profile.primary_capabilities)
        if {"currency_inference", "aggregation"} & primary:
            return "extract-organize-calculate"
        return "analyze-synthesize-report"
