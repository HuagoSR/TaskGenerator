from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import unittest

from pydantic import ValidationError

from task_generator.v3_representative_reality import (
    RepresentativeRealityCaseScopeV1,
    RepresentativeRealityScopeV1,
    _json_safe,
)


def _case(index: int) -> RepresentativeRealityCaseScopeV1:
    token = f"{index:064x}"
    return RepresentativeRealityCaseScopeV1(
        case_id=f"rp_{index:016x}",
        package_fingerprint=token,
        candidate_tree_sha256=token,
        rubric_input_sha256=token,
        scoring_audit_path=f"/audit/{index}.json",
        scoring_audit_sha256=token,
        scoring_semantic_signature=f"semantic_{index % 6}",
    )


def _scope_payload() -> dict:
    return {
        "cohort_id": "representative-production-pilot-r8-3",
        "package_readiness_path": "/governance/package_readiness.json",
        "package_readiness_sha256": "a" * 64,
        "blind_staging_report_path": "/governance/blind_staging.json",
        "blind_staging_report_sha256": "b" * 64,
        "parity_report_path": "/governance/parity.json",
        "parity_report_sha256": "c" * 64,
        "source_fingerprint": "d" * 64,
        "standing_authorization_basis": (
            "The user authorized project-scoped external review calls."
        ),
        "cases": [_case(index).model_dump(mode="json") for index in range(24)],
    }


class RepresentativeRealityTests(unittest.TestCase):
    def test_json_safe_freezes_extracted_datetime_as_string(self) -> None:
        moment = datetime(2026, 7, 31, 4, 5, tzinfo=timezone.utc)
        payload = _json_safe({"rows": [{"observed_at": moment}]})
        self.assertEqual(
            payload,
            {"rows": [{"observed_at": "2026-07-31 04:05:00+00:00"}]},
        )

    def test_scope_is_fixed_and_training_disabled(self) -> None:
        scope = RepresentativeRealityScopeV1.model_validate(_scope_payload())
        self.assertEqual(len(scope.cases), 24)
        self.assertEqual(scope.maximum_provider_calls, 96)
        self.assertEqual(scope.maximum_attempts_per_stage, 2)
        self.assertEqual(scope.provider_sdk_retries, 0)
        self.assertFalse(scope.training_authorized)
        self.assertFalse(scope.registry_mutation_authorized)
        self.assertFalse(scope.expert_review_claim_authorized)

    def test_scope_rejects_incomplete_cohort(self) -> None:
        payload = _scope_payload()
        payload["cases"].pop()
        with self.assertRaises(ValidationError):
            RepresentativeRealityScopeV1.model_validate(payload)

    def test_scope_rejects_duplicate_identity(self) -> None:
        payload = deepcopy(_scope_payload())
        payload["cases"][-1]["case_id"] = payload["cases"][0]["case_id"]
        with self.assertRaisesRegex(ValidationError, "case_id_duplicate"):
            RepresentativeRealityScopeV1.model_validate(payload)

    def test_scope_rejects_duplicate_package(self) -> None:
        payload = deepcopy(_scope_payload())
        payload["cases"][-1]["package_fingerprint"] = payload["cases"][0][
            "package_fingerprint"
        ]
        with self.assertRaisesRegex(ValidationError, "package_duplicate"):
            RepresentativeRealityScopeV1.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
