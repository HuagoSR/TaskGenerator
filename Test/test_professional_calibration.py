from __future__ import annotations

import sys
import tempfile
import hashlib
import unittest
from pathlib import Path

from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_compact_screening_grader import (  # noqa: E402
    CompactGraderDraftV2,
    CompactGraderReviewV2,
    CompactScoreVectorV2,
)
from task_generator.v3_professional_calibration import (  # noqa: E402
    CALIBRATION_REPLICATE_BY_CELL,
    ProfessionalCalibrationBindingV1,
    ProfessionalCalibrationRunnerV1,
    ProfessionalCalibrationScopeV1,
    _write_immutable_scope,
)
from task_generator.v3_semantic_review_executor import (  # noqa: E402
    tuzi_semantic_config,
)


def score_vector(value: int = 3, *, factual: int | None = None):
    return CompactScoreVectorV2(
        factual_accuracy=value if factual is None else factual,
        evidence_traceability=value,
        method_process=value,
        exception_handling=value,
        reproducibility=value,
        structural_usability=value,
        professional_expression=value,
    )


def bindings():
    result = []
    for index, ((route, motif), replicate) in enumerate(
        CALIBRATION_REPLICATE_BY_CELL.items()
    ):
        result.append(
            ProfessionalCalibrationBindingV1(
                blind_task_id=f"ms_{index}",
                route_id=route,
                motif=motif,
                replicate_id=replicate,
                candidate_package_path="candidate",
                teacher_package_path="teacher",
                delivery_path="delivery.xlsx",
                delivery_sha256="a" * 64,
                rubric_sha256="b" * 64,
                fact_anchors_sha256="c" * 64,
                compact_review_path="review.json",
                compact_review_sha256="d" * 64,
            )
        )
    return result


def scope_payload():
    return {
        "campaign_id": "campaign",
        "compact_scope_path": "compact_scope.json",
        "compact_scope_sha256": "e" * 64,
        "compact_outcome_path": "compact_outcome.json",
        "compact_outcome_sha256": "f" * 64,
        "parity_report_path": "parity.json",
        "parity_report_sha256": "1" * 64,
        "source_fingerprint": "2" * 64,
        "bindings": bindings(),
    }


class ProfessionalCalibrationTests(unittest.TestCase):
    def test_scope_covers_both_routes_all_motifs_and_both_replicates(self):
        scope = ProfessionalCalibrationScopeV1(**scope_payload())
        self.assertEqual(len(scope.bindings), 6)
        self.assertEqual(
            {(item.route_id, item.motif) for item in scope.bindings},
            set(CALIBRATION_REPLICATE_BY_CELL),
        )
        self.assertEqual({item.replicate_id for item in scope.bindings}, {"a", "b"})
        self.assertFalse(scope.training_authorized)
        self.assertFalse(scope.confirmation_authorized)

    def test_scope_rejects_duplicate_or_missing_stratum(self):
        payload = scope_payload()
        payload["bindings"][-1] = payload["bindings"][0].model_copy(
            update={"blind_task_id": "ms_duplicate_cell"}
        )
        with self.assertRaises(ValidationError):
            ProfessionalCalibrationScopeV1(**payload)

    def test_scope_filename_hashes_exact_utf8_bytes(self):
        scope = ProfessionalCalibrationScopeV1(**scope_payload())
        with tempfile.TemporaryDirectory() as directory:
            path, digest = _write_immutable_scope(scope, Path(directory))
            self.assertEqual(path.stem, digest)
            self.assertEqual(
                hashlib.sha256(path.read_bytes()).hexdigest(), digest
            )
            self.assertTrue(path.read_bytes().endswith(b"\n"))
            self.assertNotIn(b"\r\n", path.read_bytes())

    def test_independent_review_comparison_is_programmatic(self):
        independent = CompactGraderDraftV2(
            blind_task_id="ms_test",
            scores=score_vector(),
            findings=[],
            exceptional_evidence=[],
            major_defect=False,
        )
        compact = CompactGraderReviewV2(
            blind_task_id="ms_test",
            scores=score_vector(factual=2),
            findings=[
                {
                    "criterion_id": "criterion_factual_accuracy",
                    "severity": "material",
                    "locator": "Summary!A2",
                    "issue": "A material factual reconciliation remains unsupported.",
                }
            ],
            exceptional_evidence=[],
            major_defect=False,
            weighted_score=0.7,
            professional_plausibility="pass",
        )
        runner = object.__new__(ProfessionalCalibrationRunnerV1)
        comparison = runner._comparison(independent, compact)
        self.assertEqual(comparison.exact_dimension_agreement_count, 6)
        self.assertEqual(comparison.maximum_absolute_delta, 1)
        self.assertAlmostEqual(comparison.mean_absolute_delta, 1 / 7, places=6)
        self.assertTrue(comparison.professional_plausibility_agrees)

    def test_provider_prompt_is_independent_and_route_blind(self):
        prompt = ProfessionalCalibrationRunnerV1.SYSTEM_PROMPT
        self.assertIn("independent route-blind", prompt)
        self.assertIn("not been given another reviewer's scores", prompt)
        self.assertNotIn("skill_guided_llm", prompt)
        self.assertNotIn("llm_led_hybrid", prompt)

    def test_tuzi_config_accepts_existing_agent_aliases_without_rewriting_env(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            original = (
                "AGENT_API_KEY=secret-test-value\n"
                "AGENT_BASE_URL=https://example.invalid/v1\n"
            )
            path.write_text(original, encoding="utf-8")
            config = tuzi_semantic_config(
                path, "gemini-3.1-pro-preview", 321
            )
            self.assertEqual(config.provider_name, "tuzi")
            self.assertEqual(config.model, "gemini-3.1-pro-preview")
            self.assertEqual(config.timeout_seconds, 321)
            self.assertEqual(path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
