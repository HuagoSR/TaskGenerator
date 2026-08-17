from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from task_generator.v3_representative_production_pilot import (
    DOMAINS,
    MOTIFS,
    ROUTES,
    RepresentativePilotAssignmentV1,
    RepresentativePilotBriefRecordV1,
    RepresentativePilotGenerationRunner,
    RepresentativePilotPackageReadinessCompiler,
    RepresentativeProductionPilotManifestV1,
)
from task_generator.v3_skill_extractor import ProviderConfig
from task_generator.v3_task_design_executor import TaskDesignExecutionReportV1


FIXTURE_ROOT = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "pipeline_reconstruction"
    / "task_design"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _SuccessfulExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def run(self, request, config):
        self.calls += 1
        brief = json.loads(Path(request.capability_brief_path).read_text("utf-8"))
        proposal = json.loads((FIXTURE_ROOT / "valid_proposal.json").read_text("utf-8"))
        proposal["brief_id"] = brief["brief_id"]
        proposal["proposal_id"] = f"proposal_{brief['brief_id']}_{request.route_id}"
        output = Path(request.output_dir)
        output.mkdir(parents=True, exist_ok=True)
        proposal_path = output / "task_design_proposal.json"
        proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
        report = TaskDesignExecutionReportV1(
            status="completed",
            request=request,
            brief_id=brief["brief_id"],
            proposal_id=proposal["proposal_id"],
            proposal_interface_mode="strict_v2",
            proposal_path=str(proposal_path),
        )
        (output / "task_design_execution_report.json").write_text(
            report.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return report


class _SuccessfulMaterializer:
    def materialize(self, brief, proposal, package_root):
        root = Path(package_root)
        root.mkdir(parents=True, exist_ok=True)
        (root / "package_identity.txt").write_text(
            f"{brief.brief_id}:{proposal.proposal_id}",
            encoding="utf-8",
        )
        (root / "hybrid_materialization_report.json").write_text(
            '{"decision":"pass"}',
            encoding="utf-8",
        )
        return SimpleNamespace(decision="pass")


class RepresentativeProductionPilotTests(unittest.TestCase):
    def _manifest(self, root: Path) -> Path:
        base_brief = json.loads(
            (FIXTURE_ROOT / "capability_brief.json").read_text(encoding="utf-8")
        )
        briefs = []
        assignments = []
        index = 0
        for domain in DOMAINS:
            for motif in MOTIFS:
                for replicate in ("a", "b"):
                    index += 1
                    brief_id = f"brief_r8_3_{index:02d}"
                    payload = json.loads(json.dumps(base_brief))
                    payload["brief_id"] = brief_id
                    payload["case_id"] = f"case_r8_3_{index:02d}"
                    payload["motif"] = motif
                    payload["workflow_context"]["subgraph_id"] = (
                        f"subgraph_r8_3_{index:02d}"
                    )
                    brief_path = root / "briefs" / f"{brief_id}.json"
                    brief_path.parent.mkdir(parents=True, exist_ok=True)
                    brief_path.write_text(json.dumps(payload), encoding="utf-8")
                    briefs.append(
                        RepresentativePilotBriefRecordV1(
                            brief_id=brief_id,
                            domain=domain,
                            motif=motif,
                            replicate_id=replicate,
                            brief_path=str(brief_path),
                            brief_sha256=_sha(brief_path),
                            source_group_ids=["source_group_test"],
                        )
                    )
                    for route in ROUTES:
                        assignments.append(
                            RepresentativePilotAssignmentV1(
                                blind_task_id=f"rp_{index:02d}_{route}",
                                brief_id=brief_id,
                                domain=domain,
                                motif=motif,
                                replicate_id=replicate,
                                route_id=route,
                            )
                        )
        ledger = root / "ledger.json"
        admission = root / "admission.json"
        ledger.write_text("{}", encoding="utf-8")
        admission.write_text("{}", encoding="utf-8")
        manifest = RepresentativeProductionPilotManifestV1(
            campaign_id="r8_3_test",
            source_ledger_path=str(ledger),
            source_ledger_sha256=_sha(ledger),
            admission_report_path=str(admission),
            admission_report_sha256=_sha(admission),
            briefs=briefs,
            assignments=assignments,
        )
        path = root / "pilot_manifest.json"
        path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        return path

    def test_generation_reuses_existing_executor_and_materializer_for_24(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = self._manifest(root)
            executor = _SuccessfulExecutor()
            result = RepresentativePilotGenerationRunner().execute(
                pilot_manifest_path=manifest_path,
                output_root=root / "generation",
                provider_config=ProviderConfig(
                    provider_name="tuzi",
                    base_url="https://example.invalid",
                    api_key="not-used",
                    model="gpt-5.6-sol",
                ),
                executor=executor,
                materializer=_SuccessfulMaterializer(),
            )
            self.assertEqual(result.decision, "packages_ready")
            self.assertEqual(executor.calls, 24)
            self.assertEqual(result.provider_call_count, 24)
            self.assertEqual(
                len({item.package_fingerprint for item in result.cases}),
                24,
            )
            self.assertFalse(result.training_authorized)
            self.assertFalse(result.registry_mutation_authorized)
            readiness = RepresentativePilotPackageReadinessCompiler().compile(
                pilot_manifest_path=manifest_path,
                generation_result_path=root / "generation" / "generation_result.json",
                replay_roots_by_task={},
                output_path=root / "package_readiness_result.json",
            )
            self.assertEqual(readiness.decision, "packages_ready")
            self.assertEqual(len(readiness.packages), 24)
            self.assertFalse(readiness.external_provider_calls_made)

    def test_generation_rejects_provider_or_model_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest_path = self._manifest(root)
            with self.assertRaisesRegex(ValueError, "provider_mismatch"):
                RepresentativePilotGenerationRunner().execute(
                    pilot_manifest_path=manifest_path,
                    output_root=root / "generation",
                    provider_config=ProviderConfig(
                        provider_name="deepseek",
                        base_url="https://example.invalid",
                        api_key="not-used",
                        model="gpt-5.6-sol",
                    ),
                )


if __name__ == "__main__":
    unittest.main()
