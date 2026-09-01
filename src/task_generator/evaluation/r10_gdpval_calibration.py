"""Read-only morphology comparison for the R10 compiler-revision experiment.

GDPval is calibration material only.  This module deliberately emits aggregate
task-shape observations and never returns task text, reference content, hidden
rubrics, or data that could be forwarded into a generation prompt.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_object_required:{path.name}")
    return value


def _candidate_shape(task_root: Path) -> dict[str, Any]:
    candidate = task_root / "reference_files"
    files = sorted(path for path in candidate.rglob("*") if path.is_file())
    if not files:
        raise ValueError(f"candidate_files_missing:{task_root.name}")
    text_lines = 0
    for path in files:
        if path.suffix.lower() in {".txt", ".csv"}:
            text_lines += len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    prompt = (task_root / "TASK.md").read_text(encoding="utf-8")
    matrix = _read_json(task_root / "teacher" / "decision_matrix.json")
    rubric = _read_json(task_root / "teacher" / "task_specific_rubric.json")
    contract = _read_json(task_root / "deliverable_contract.json")
    return {
        "task_id": task_root.name,
        "reference_file_count": len(files),
        "reference_extensions": sorted({path.suffix.lower() for path in files}),
        "candidate_byte_count": sum(path.stat().st_size for path in files),
        "candidate_text_line_count": text_lines,
        "prompt_character_count": len(prompt),
        "decision_point_count": len(matrix.get("decision_points", [])),
        "rubric_criterion_count": len(rubric.get("criteria", [])),
        "deliverable_formats": sorted({str(item.get("format", "")) for item in contract.get("deliverables", [])}),
    }


def build_r10_gdpval_calibration_report(
    *,
    task_roots: list[Path],
    gdpval_distribution_path: Path,
    discrimination_path: Path,
) -> dict[str, Any]:
    """Return a content-free comparison used only to guide compiler prompts."""

    if len(task_roots) != 4:
        raise ValueError("r10_calibration_requires_four_frozen_tasks")
    gdpval = _read_json(gdpval_distribution_path)
    diagnosis = _read_json(discrimination_path)
    task_shapes = [_candidate_shape(path) for path in sorted(task_roots)]
    diagnosis_by_task = {item["task_id"]: item for item in diagnosis.get("task_diagnoses", [])}
    for task in task_shapes:
        item = diagnosis_by_task.get(task["task_id"], {})
        task["pilot_classification"] = item.get("classification", "incomplete")
        task["compiler_signals"] = item.get("compiler_signals", [])
    return {
        "report_version": "r10.gdpval_compiler_calibration.1",
        "use": "eval_calibration_only",
        "generation_safe": True,
        "gdpval_aggregate": {
            "task_count": gdpval.get("task_count"),
            "reference_file_extension_counts": gdpval.get("reference_file_extension_counts", {}),
            "reasoning_requirement_counts": gdpval.get("reasoning_requirement_counts", {}),
            "evidence_density_counts": gdpval.get("evidence_density_counts", {}),
            "ambiguity_level_counts": gdpval.get("ambiguity_level_counts", {}),
        },
        "r10_frozen_task_shapes": task_shapes,
        "observed_gap": [
            "R10 candidate bundles are compact, predominantly text/CSV summaries with few decision points.",
            "The GDPval calibration subset more often combines native office formats with calculation, reconciliation, cross-file synthesis, or policy application.",
            "R10 pilot diagnoses show score saturation, insufficient evidence tension, and one judge-boundary ambiguity.",
        ],
        "compiler_revision_guidance": [
            "Generate operational records as normal process by-products, with ordinary activity and connected evidence rather than an answer-organized case summary.",
            "Ask for a business work product without enumerating hidden discrepancies or preferred conclusions.",
            "Use independent, evidence-backed decision points with explicit met/partial/not-met boundaries and concrete major errors.",
        ],
        "prohibited_generation_inputs": [
            "GDPval task prompts", "GDPval reference files", "GDPval hidden rubrics", "GDPval gold deliverables",
        ],
    }
