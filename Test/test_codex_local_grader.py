from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_codex_local_grader import (  # noqa: E402
    CandidateDataAdmissionManifestV1,
    CandidateDataAdmissionRecordV1,
    CodexLocalGraderManifestV1,
    CodexLocalGraderOutcomeV1,
    CodexLocalGraderRunnerV1,
    CodexLocalGraderScopeV1,
    _analyze,
    _strict_output_schema,
    compile_route_convergence_report,
)
from task_generator.v3_codex_local_solver import (  # noqa: E402
    CodexLocalCLIIdentityV1,
)
from task_generator.v3_compact_screening_grader import (  # noqa: E402
    CompactGraderBindingV2,
    CompactGraderDraftV2,
    CompactScoreVectorV2,
    RepresentativeScreeningObservationV1,
)


def _binding(
    index: int,
    domain: str,
    route: str,
    motif: str,
    replicate: str,
    root: Path | None = None,
) -> CompactGraderBindingV2:
    base = root or Path("root")
    return CompactGraderBindingV2(
        blind_task_id=f"rp_{index}",
        route_id=route,
        motif=motif,
        replicate_id=replicate,
        domain=domain,
        candidate_package_path=str(base / "candidate"),
        teacher_package_path=str(base / "teacher"),
        solver_outcome_sha256="a" * 64,
        delivery_path=str(base / "deliverable.xlsx"),
        delivery_sha256="b" * 64,
        rubric_sha256="c" * 64,
        fact_anchors_sha256="d" * 64,
    )


def _matrix(root: Path | None = None) -> list[CompactGraderBindingV2]:
    return [
        _binding(index, domain, route, motif, replicate, root)
        for index, (domain, route, motif, replicate) in enumerate(
            (
                (domain, route, motif, replicate)
                for domain in (
                    "audit_compliance",
                    "procurement_operations",
                )
                for route in ("skill_guided_llm", "llm_led_hybrid")
                for motif in (
                    "fan_in_reconciliation",
                    "cross_check_validation",
                    "policy_application",
                )
                for replicate in ("a", "b")
            )
        )
    ]


class _Process:
    def __init__(self, command, payload):
        self.command = command
        self.payload = payload
        self.returncode = 0

    def communicate(self, input=None, timeout=None):
        output = Path(
            self.command[
                self.command.index("--output-last-message") + 1
            ]
        )
        output.write_text(
            json.dumps(self.payload, ensure_ascii=False),
            encoding="utf-8",
        )
        return (
            '{"type":"turn.completed","usage":{"input_tokens":10,'
            '"cached_input_tokens":0,"output_tokens":5}}\n',
            "",
        )


class CodexLocalGraderTests(unittest.TestCase):
    def test_candidate_data_manifest_is_report_only_and_route_scoped(self):
        records = []
        for binding in _matrix():
            records.append(
                CandidateDataAdmissionRecordV1(
                    blind_task_id=binding.blind_task_id,
                    route_id=binding.route_id,
                    route_role=(
                        "production_candidate"
                        if binding.route_id == "llm_led_hybrid"
                        else "challenger_control"
                    ),
                    domain=binding.domain,
                    motif=binding.motif,
                    replicate_id=binding.replicate_id,
                    package_fingerprint="a" * 64,
                    candidate_tree_sha256="b" * 64,
                    reality_evidence_sha256="c" * 64,
                    delivery_sha256="d" * 64,
                    grader_review_sha256="e" * 64,
                    weighted_score=0.75,
                )
            )
        manifest = CandidateDataAdmissionManifestV1(
            campaign_id="campaign",
            representative_campaign_sha256="1" * 64,
            grader_outcome_sha256="2" * 64,
            grader_manifest_sha256="3" * 64,
            route_convergence_report_sha256="4" * 64,
            package_readiness_sha256="5" * 64,
            reality_result_sha256="6" * 64,
            solver_manifest_sha256="7" * 64,
            records=records,
            permitted_future_export_components=[
                "candidate_prompt",
                "candidate_reference_files",
                "solver_deliverable",
                "structured_grader_feedback",
            ],
            prohibited_export_components=[
                "teacher_only_rubric",
                "deterministic_fact_anchors",
                "codex_jsonl",
                "hidden_reasoning",
                "authentication_material",
            ],
        )
        self.assertEqual(manifest.admitted_record_count, 24)
        self.assertFalse(manifest.dataset_export_authorized)
        self.assertFalse(manifest.training_started)

    def test_strict_schema_requires_every_property_and_removes_defaults(self):
        schema = _strict_output_schema(
            CompactGraderDraftV2.model_json_schema()
        )
        self.assertEqual(
            set(schema["required"]), set(schema["properties"])
        )
        self.assertFalse(schema["additionalProperties"])

        def walk(value):
            if isinstance(value, dict):
                self.assertNotIn("default", value)
                if "properties" in value:
                    self.assertEqual(
                        set(value["required"]),
                        set(value["properties"]),
                    )
                    self.assertFalse(value["additionalProperties"])
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(schema)

    def test_scope_binds_full_matrix_and_same_model_ceiling(self):
        scope = CodexLocalGraderScopeV1(
            campaign_id="campaign",
            upstream_compact_scope_path="upstream.json",
            upstream_compact_scope_sha256="a" * 64,
            solver_manifest_sha256="b" * 64,
            parity_report_path="parity.json",
            parity_report_sha256="c" * 64,
            source_fingerprint="d" * 64,
            cli=CodexLocalCLIIdentityV1(
                version="0.146.0",
                package_lock_sha256="e" * 64,
                executable_sha256="f" * 64,
                executable_path="codex.cmd",
                installation_tree_sha256="1" * 64,
            ),
            bindings=_matrix(),
        )
        self.assertEqual(len(scope.bindings), 24)
        self.assertEqual(scope.evidence_kind, "same_model_behavioral_proxy")
        self.assertFalse(scope.independent_model_evidence)
        self.assertFalse(scope.training_authorized)

    def test_native_output_schema_path_produces_valid_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = root / "candidate"
            teacher = root / "teacher" / "teacher"
            candidate.mkdir(parents=True)
            teacher.mkdir(parents=True)
            (candidate / "dataset_row.json").write_text(
                json.dumps({"prompt": "Review the workbook."}),
                encoding="utf-8",
            )
            (teacher / "rubric_plan_v2.json").write_text(
                json.dumps({"criteria": []}), encoding="utf-8"
            )
            (teacher / "deterministic_fact_anchors.json").write_text(
                json.dumps({"anchors": []}), encoding="utf-8"
            )
            (root / "deliverable.xlsx").write_bytes(b"xlsx")
            binding = _binding(
                0,
                "audit_compliance",
                "skill_guided_llm",
                "fan_in_reconciliation",
                "a",
                root,
            )
            draft = CompactGraderDraftV2(
                blind_task_id=binding.blind_task_id,
                scores=CompactScoreVectorV2(
                    factual_accuracy=3,
                    evidence_traceability=3,
                    method_process=3,
                    exception_handling=3,
                    reproducibility=3,
                    structural_usability=3,
                    professional_expression=3,
                ),
                major_defect=False,
            )
            commands = []

            def factory(command, **kwargs):
                commands.append(command)
                return _Process(command, draft.model_dump(mode="json"))

            runner = object.__new__(CodexLocalGraderRunnerV1)
            runner.output = root / "output"
            runner.codex_home = root / "codex-home"
            runner.python = Path(sys.executable)
            runner.popen_factory = factory
            runner.scope = SimpleNamespace(
                cli=SimpleNamespace(executable_path="codex.cmd"),
                timeout_seconds_per_task=1800,
            )
            record = runner._run_one(binding)
            self.assertEqual(record.status, "completed")
            self.assertIn("--output-schema", commands[0])
            self.assertIn("--output-last-message", commands[0])
            workspace_files = {
                item.name
                for item in Path(record.workspace_path).iterdir()
            }
            self.assertNotIn("route_id.json", workspace_files)
            self.assertTrue(Path(record.review_path).is_file())

    def test_analyzer_reports_both_routes_without_independence_claim(self):
        rows = []
        for binding in _matrix():
            rows.append(
                RepresentativeScreeningObservationV1(
                    blind_task_id=binding.blind_task_id,
                    route_id=binding.route_id,
                    motif=binding.motif,
                    replicate_id=binding.replicate_id,
                    domain=binding.domain,
                    infrastructure_complete=True,
                    offline_validity_pass=True,
                    exact_valid_delivery=True,
                    major_defect=False,
                    professional_plausibility_pass=True,
                    productive_complexity_pass=True,
                    skill_causal_pass=True,
                    effective_rubric_dimensions=7,
                    weighted_score=0.75,
                )
            )
        result = _analyze("campaign", rows)
        self.assertEqual(result.decision, "production_candidate_both")
        self.assertEqual(result.comparable_pair_count, 12)

    def test_convergence_prefers_smaller_route_without_authority(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bindings = _matrix()
            scope = CodexLocalGraderScopeV1(
                campaign_id="campaign",
                upstream_compact_scope_path="upstream.json",
                upstream_compact_scope_sha256="a" * 64,
                solver_manifest_sha256="b" * 64,
                parity_report_path="parity.json",
                parity_report_sha256="c" * 64,
                source_fingerprint="d" * 64,
                cli=CodexLocalCLIIdentityV1(
                    version="0.146.0",
                    package_lock_sha256="e" * 64,
                    executable_sha256="f" * 64,
                    executable_path="codex.cmd",
                    installation_tree_sha256="1" * 64,
                ),
                bindings=bindings,
            )
            scope_path = root / "scope.json"
            scope_path.write_text(
                json.dumps(scope.model_dump(mode="json")),
                encoding="utf-8",
            )
            import hashlib

            scope_sha = hashlib.sha256(scope_path.read_bytes()).hexdigest()
            observations = []
            assignments = []
            for index, binding in enumerate(bindings):
                cell_index = (
                    (
                        "audit_compliance",
                        "procurement_operations",
                    ).index(binding.domain)
                    * 6
                    + (
                        "fan_in_reconciliation",
                        "cross_check_validation",
                        "policy_application",
                    ).index(binding.motif)
                    * 2
                    + ("a", "b").index(binding.replicate_id)
                )
                if cell_index < 5:
                    score = (
                        0.81
                        if binding.route_id == "skill_guided_llm"
                        else 0.80
                    )
                elif cell_index < 10:
                    score = (
                        0.80
                        if binding.route_id == "skill_guided_llm"
                        else 0.81
                    )
                else:
                    score = 0.805
                observations.append(
                    RepresentativeScreeningObservationV1(
                        blind_task_id=binding.blind_task_id,
                        route_id=binding.route_id,
                        motif=binding.motif,
                        replicate_id=binding.replicate_id,
                        domain=binding.domain,
                        infrastructure_complete=True,
                        offline_validity_pass=True,
                        exact_valid_delivery=True,
                        major_defect=False,
                        professional_plausibility_pass=True,
                        productive_complexity_pass=True,
                        skill_causal_pass=True,
                        effective_rubric_dimensions=7,
                        weighted_score=score,
                    )
                )
                package = root / f"package-{index}"
                references = package / "candidate" / "reference_files"
                references.mkdir(parents=True)
                (references / "one.xlsx").write_bytes(b"x" * 100)
                if binding.route_id == "skill_guided_llm":
                    (references / "two.xlsx").write_bytes(b"y" * 100)
                assignments.append(
                    {
                        "blind_task_id": binding.blind_task_id,
                        "route_id": binding.route_id,
                        "package_root": str(package),
                    }
                )
            outcome = CodexLocalGraderOutcomeV1(
                campaign_id="campaign",
                completed_grades=24,
                infrastructure_failed_grades=0,
                grading_failed_grades=0,
                total_process_seconds=1.0,
                score_distribution={"0.800": 12, "0.810": 12},
                screening_result=_analyze("campaign", observations),
            )
            outcome_path = root / "outcome.json"
            outcome_path.write_text(
                json.dumps(outcome.model_dump(mode="json")),
                encoding="utf-8",
            )
            outcome_sha = hashlib.sha256(
                outcome_path.read_bytes()
            ).hexdigest()
            manifest = CodexLocalGraderManifestV1(
                scope_path=str(scope_path),
                scope_sha256=scope_sha,
                status="completed",
                records={},
                result_path=str(outcome_path),
                result_sha256=outcome_sha,
                created_at="2026-07-31T00:00:00Z",
                updated_at="2026-07-31T00:00:00Z",
            )
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(manifest.model_dump(mode="json")),
                encoding="utf-8",
            )
            campaign_path = root / "campaign.json"
            campaign_path.write_text(
                json.dumps({"assignments": assignments}),
                encoding="utf-8",
            )
            report, _ = compile_route_convergence_report(
                grader_outcome_path=outcome_path,
                grader_manifest_path=manifest_path,
                representative_campaign_path=campaign_path,
                output_path=root / "report.json",
            )
            self.assertEqual(report.recommendation, "llm_led_hybrid")
            self.assertEqual(report.challenger, "skill_guided_llm")
            self.assertFalse(report.training_authorized)
            by_route = {item.route_id: item for item in report.routes}
            self.assertEqual(
                by_route["skill_guided_llm"].candidate_workbook_count,
                24,
            )
            self.assertEqual(
                by_route["llm_led_hybrid"].candidate_workbook_count,
                12,
            )


if __name__ == "__main__":
    unittest.main()
