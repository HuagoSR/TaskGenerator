import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v3_skill_graph_diagnostics import (  # noqa: E402
    build_graph_extraction_diagnostics,
    load_graph_extraction_inputs,
    write_graph_extraction_diagnostics,
)
from v3_source_schema import SkillExtractionPromptPackage, load_json_file  # noqa: E402


def load_optional_package(path: Path | None) -> SkillExtractionPromptPackage | None:
    if path is None or not path.exists():
        return None
    return SkillExtractionPromptPackage.model_validate(load_json_file(str(path)))


def extraction_dir_summary(extraction_dir: Path, prompt_package: SkillExtractionPromptPackage | None) -> Dict[str, object]:
    candidates_path = extraction_dir / "extracted_skill_candidates.json"
    if not candidates_path.exists():
        return {
            "extraction_dir": str(extraction_dir),
            "status": "missing_candidates",
            "warning_codes": ["missing_candidates"],
        }
    candidates, trace_edges, motif_hints = load_graph_extraction_inputs(
        candidates_path=candidates_path,
        trace_edges_path=extraction_dir / "skill_trace_edges.json",
        motif_hints_path=extraction_dir / "skill_motif_hints.json",
    )
    diagnostics = build_graph_extraction_diagnostics(
        candidates=candidates,
        trace_edges=trace_edges,
        motif_hints=motif_hints,
        package=prompt_package,
    )
    write_graph_extraction_diagnostics(diagnostics, extraction_dir / "graph_extraction_diagnostics.json")
    warning_details = diagnostics["warnings"]
    return {
        "extraction_dir": str(extraction_dir),
        "status": "ok",
        "artifact_generation": _artifact_generation(extraction_dir, diagnostics),
        "candidate_count": diagnostics["candidate_count"],
        "resource_count": diagnostics["typed_resource_summary"]["resource_count"],
        "trace_edge_count": diagnostics["trace_edge_summary"]["trace_edge_count"],
        "motif_hint_count": diagnostics["motif_hint_summary"]["motif_hint_count"],
        "trace_candidate_coverage_ratio": diagnostics["trace_edge_summary"]["candidate_coverage_ratio"],
        "motif_candidate_coverage_ratio": diagnostics["motif_hint_summary"]["candidate_coverage_ratio"],
        "warning_codes": [warning["code"] for warning in warning_details],
        "warning_details": warning_details,
        "is_graph_ready": diagnostics["is_graph_ready"],
    }


def aggregate(summaries: List[Dict[str, object]]) -> Dict[str, object]:
    warning_counts: Counter[str] = Counter()
    warning_severity_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    artifact_generation_counts: Counter[str] = Counter()
    for summary in summaries:
        status_counts.update([str(summary.get("status", "unknown"))])
        warning_counts.update(summary.get("warning_codes", []))
        artifact_generation_counts.update([str(summary.get("artifact_generation", "unknown"))])
        warning_severity_counts.update(
            str(warning.get("severity", "unknown"))
            for warning in summary.get("warning_details", [])
        )
    ok_summaries = [summary for summary in summaries if summary.get("status") == "ok"]
    return {
        "calibration_report_version": "v3.graph_calibration_report.2",
        "extraction_dir_count": len(summaries),
        "status_counts": dict(sorted(status_counts.items())),
        "artifact_generation_counts": dict(sorted(artifact_generation_counts.items())),
        "graph_ready_count": sum(1 for summary in ok_summaries if summary.get("is_graph_ready")),
        "candidate_count": sum(int(summary.get("candidate_count") or 0) for summary in ok_summaries),
        "resource_count": sum(int(summary.get("resource_count") or 0) for summary in ok_summaries),
        "trace_edge_count": sum(int(summary.get("trace_edge_count") or 0) for summary in ok_summaries),
        "motif_hint_count": sum(int(summary.get("motif_hint_count") or 0) for summary in ok_summaries),
        "warning_counts": dict(sorted(warning_counts.items())),
        "warning_severity_counts": dict(sorted(warning_severity_counts.items())),
        "calibration_notes": [
            "pre_graph_or_legacy outputs are useful baselines, but their missing graph fields should not be treated as current extractor failures.",
            "attention warnings mark calibration targets for Pipeline A; they do not block Pipeline B experiments by themselves.",
        ],
        "summaries": summaries,
    }


def _artifact_generation(extraction_dir: Path, diagnostics: Dict[str, object]) -> str:
    path_text = str(extraction_dir).replace("\\", "/")
    if "pipeline_a_run_graph_calibration" in path_text or "deepseek_extraction_graph_calibration" in path_text:
        return "graph_calibration"
    if diagnostics["typed_resource_summary"]["resource_count"] == 0 and diagnostics["candidate_count"] > 1:
        return "pre_graph_or_legacy"
    return "graph_capable"


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate graph extraction diagnostics across extraction directories.")
    parser.add_argument("--extraction-dir", action="append", type=Path, default=[], help="Extraction output directory. Can be repeated.")
    parser.add_argument("--prompt-package", type=Path, help="Optional prompt package used for block-ref validation.")
    parser.add_argument("--output-path", type=Path, default=ROOT / "SkillRegistry" / "v3_graph_calibration_report.json")
    args = parser.parse_args()

    if not args.extraction_dir:
        raise SystemExit("At least one --extraction-dir is required.")

    prompt_package = load_optional_package(args.prompt_package)
    report = aggregate([extraction_dir_summary(path, prompt_package) for path in args.extraction_dir])
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(
        json.dumps(
            {
                "output_path": str(args.output_path),
                "extraction_dir_count": report["extraction_dir_count"],
                "candidate_count": report["candidate_count"],
                "resource_count": report["resource_count"],
                "trace_edge_count": report["trace_edge_count"],
                "motif_hint_count": report["motif_hint_count"],
                "warning_counts": report["warning_counts"],
                "warning_severity_counts": report["warning_severity_counts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
