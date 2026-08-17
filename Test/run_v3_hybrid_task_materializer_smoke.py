from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_hybrid_task_materializer import HybridTaskMaterializer  # noqa: E402
from task_generator.v3_route_generation import StrictTemplateProposalCompiler  # noqa: E402
from task_generator.v3_task_design_frontend import (  # noqa: E402
    CapabilityBriefV1,
)


MOTIFS = [
    "cross_check_validation",
    "fan_in_reconciliation",
    "policy_application",
    "evidence_to_deliverable",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    fixture_root = (
        ROOT
        / "Test"
        / "fixtures"
        / "pipeline_reconstruction"
        / "task_design"
    )
    base_brief = json.loads(
        (fixture_root / "capability_brief.json").read_text(encoding="utf-8")
    )
    base_proposal = json.loads(
        (fixture_root / "valid_proposal.json").read_text(encoding="utf-8")
    )
    output_root = (
        ROOT
        / "artifacts"
        / "pipeline_reconstruction"
        / "hybrid_materializer_smoke"
        / args.run_id
    )
    if output_root.exists():
        raise FileExistsError(f"smoke_output_exists:{output_root}")
    output_root.mkdir(parents=True)

    records = []
    for motif in MOTIFS:
        brief_payload, _ = _variant(
            base_brief,
            base_proposal,
            motif,
        )
        brief = CapabilityBriefV1.model_validate(brief_payload)
        proposal = StrictTemplateProposalCompiler().compile(brief)
        case_root = output_root / motif
        report = HybridTaskMaterializer().materialize(
            brief,
            proposal,
            case_root,
        )
        anchors = json.loads(
            (
                case_root
                / "teacher"
                / "deterministic_fact_anchors.json"
            ).read_text(encoding="utf-8")
        ) if report.decision == "pass" else {"anchors": []}
        records.append(
            {
                "motif": motif,
                "decision": report.decision,
                "evidence_file_count": report.evidence_file_count,
                "deterministic_anchor_count": report.deterministic_anchor_count,
                "deliverable_contract_valid": report.deliverable_contract_valid,
                "complexity_preservation_pass": (
                    report.complexity_preservation_pass
                ),
                "visual_validation_pass": report.visual_validation_pass,
                "evidence_content_quality_decision": (
                    report.evidence_content_quality_decision
                ),
                "materialization_backend": report.materialization_backend,
                "rw_task_export_validation_status": (
                    report.rw_task_export_validation_status
                ),
                "candidate_teacher_isolation_pass": (
                    report.candidate_teacher_isolation_pass
                ),
                "truth_authorities": sorted(
                    {
                        item["truth_authority"]
                        for item in anchors["anchors"]
                    }
                ),
            }
        )
    passed = all(
        item["decision"] == "pass"
        and item["deliverable_contract_valid"]
        and item["complexity_preservation_pass"]
        and item["visual_validation_pass"]
        and item["evidence_content_quality_decision"] == "pass"
        and item["materialization_backend"] == "hybrid_semantic_artifact_v2"
        and item["rw_task_export_validation_status"] == "draft_compatible"
        and item["candidate_teacher_isolation_pass"]
        and item["truth_authorities"]
        == ["deterministic_candidate_visible_recomputation"]
        for item in records
    )
    summary = {
        "report_version": "v3.hybrid_materializer_smoke.1",
        "run_id": args.run_id,
        "passed": passed,
        "external_calls": False,
        "motif_count": len(records),
        "records": records,
        "notes": [
            "All proposals are deterministic strict-template V2 semantic-artifact controls compiled from tracked briefs.",
            "No provider, solver, grader, registry mutation, or promotion was used.",
            "This is offline materialization evidence, not route-comparison evidence.",
        ],
    }
    report_path = output_root / "hybrid_materializer_smoke_report.json"
    report_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"passed": passed, "report_path": str(report_path)}, indent=2))
    return 0 if passed else 1


def _variant(base_brief, base_proposal, motif):
    brief = json.loads(json.dumps(base_brief))
    proposal = json.loads(json.dumps(base_proposal))
    brief["brief_id"] = f"brief_fixture_{motif}"
    brief["case_id"] = f"hybrid_fixture_{motif}"
    brief["motif"] = motif
    brief["allowed_output_file_types"] = ["xlsx", "docx"]
    proposal["brief_id"] = brief["brief_id"]
    proposal["proposal_id"] = f"proposal_fixture_{motif}"
    proposal["scenario"] = (
        f"A finance audit analyst must complete a {motif.replace('_', ' ')} "
        "review before manager approval."
    )
    if motif == "fan_in_reconciliation":
        proposal["evidence_nodes"].append(
            {
                "node_id": "node_support",
                "artifact_role": "supporting schedule evidence",
                "candidate_visible": True,
                "source_ref_ids": ["source_public_001"],
                "intended_contents": "A third independent schedule requiring reconciliation.",
            }
        )
        proposal["evidence_relations"].append(
            {
                "relation_id": "relation_fanin",
                "from_node_id": "node_support",
                "to_node_id": "node_control",
                "relation_type": "fan-in reconciliation",
                "solver_must_infer": True,
            }
        )
        proposal["required_judgments"][0]["input_node_ids"].append(
            "node_support"
        )
        proposal["skill_bindings"][0]["bound_element_ids"].append(
            "relation_fanin"
        )
        proposal["deliverable_intent"]["artifact_kind"] = (
            "reconciliation workpaper"
        )
        proposal["deliverable_intent"]["business_use"] = (
            "Support close by reconciling three evidence paths."
        )
    elif motif == "policy_application":
        proposal["evidence_nodes"][1]["artifact_role"] = "policy clause evidence"
        proposal["evidence_relations"][0]["relation_type"] = "policy application"
        proposal["required_judgments"][0]["description"] = (
            "Apply the candidate-visible policy conditions to each observed item "
            "and explain exceptions."
        )
        proposal["deliverable_intent"]["artifact_kind"] = "policy review memo"
        proposal["deliverable_intent"]["allowed_formats"] = ["docx"]
        proposal["deliverable_intent"]["business_use"] = (
            "Document policy application decisions for manager review."
        )
    elif motif == "evidence_to_deliverable":
        proposal["evidence_nodes"][1]["artifact_role"] = (
            "manager request and control evidence"
        )
        proposal["evidence_relations"][0]["relation_type"] = (
            "evidence-to-conclusion synthesis"
        )
        proposal["required_judgments"][0]["description"] = (
            "Synthesize supported conclusions from the evidence and separate "
            "unsupported requests."
        )
        proposal["deliverable_intent"]["artifact_kind"] = "evidence review memo"
        proposal["deliverable_intent"]["allowed_formats"] = ["docx"]
        proposal["deliverable_intent"]["business_use"] = (
            "Provide an evidence-backed decision memo to the manager."
        )
    return brief, proposal


if __name__ == "__main__":
    raise SystemExit(main())
