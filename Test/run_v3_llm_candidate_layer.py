import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_llm_candidate_layer import (  # noqa: E402
    LlmCandidateLayerBuilder,
    LlmCandidateLayerRequest,
)


PHASE15 = ROOT / "artifacts" / "phase15"
DEFAULT_ADOPTION_GATE = PHASE15 / "llm_shadow_review" / "llm_adoption_gate_report.json"
DEFAULT_REFORM_SPEC = PHASE15 / "generator_reform" / "evidence_to_deliverable_reform_spec.json"
DEFAULT_OUTPUT = PHASE15 / "llm_candidate_layer"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Phase 15 guarded LLM candidate-layer report.")
    parser.add_argument("--adoption-gate-path", type=Path, default=DEFAULT_ADOPTION_GATE)
    parser.add_argument("--reform-spec-path", type=Path, default=DEFAULT_REFORM_SPEC)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    request = LlmCandidateLayerRequest(
        adoption_gate_path=str(args.adoption_gate_path),
        reform_spec_path=str(args.reform_spec_path),
        output_dir=str(args.output_dir),
    )
    report = LlmCandidateLayerBuilder().build(request)
    print(
        json.dumps(
            {
                "target_motif": report.target_motif,
                "experiment_candidate_enabled": report.experiment_candidate_enabled,
                "approved_candidate_roles": report.approved_candidate_roles,
                "diagnostic_only_roles": report.diagnostic_only_roles,
                "blocked_roles": report.blocked_roles,
                "report_path": str(Path(args.output_dir) / "llm_candidate_layer_report.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
