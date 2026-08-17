from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_evidence_content_quality import (  # noqa: E402
    EvidenceContentQualityValidator,
)
from task_generator.v3_hybrid_task_materializer import (  # noqa: E402
    HybridEvidenceDossierV1,
)
from task_generator.v3_task_design_frontend import TaskDesignProposalV1  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the report-first semantic content audit for materialized evidence files."
    )
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--dossier", type=Path, required=True)
    parser.add_argument("--reference-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    proposal = TaskDesignProposalV1.model_validate_json(
        args.proposal.read_text(encoding="utf-8")
    )
    dossier = HybridEvidenceDossierV1.model_validate_json(
        args.dossier.read_text(encoding="utf-8")
    )
    report = EvidenceContentQualityValidator().validate(
        proposal=proposal,
        files=dossier.files,
        reference_root=args.reference_root,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report.model_dump(mode="json"), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
