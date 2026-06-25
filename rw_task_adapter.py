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
        rubric_items = json.loads(dataset_shell.rubric_json)
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
