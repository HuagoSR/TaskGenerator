from __future__ import annotations

from copy import deepcopy
import inspect
import unittest

from pydantic import ValidationError

from task_generator.v3_codex_local_solver import (
    CodexLocalCLIIdentityV1,
    CodexLocalScreeningScopeV1,
    CodexLocalTaskBindingV1,
)
from task_generator.v3_representative_codex_local import (
    compile_representative_codex_scope,
)


DOMAINS = ("audit_compliance", "procurement_operations")
ROUTES = ("skill_guided_llm", "llm_led_hybrid")
MOTIFS = (
    "fan_in_reconciliation",
    "cross_check_validation",
    "policy_application",
)
REPLICATES = ("a", "b")


def _cli() -> CodexLocalCLIIdentityV1:
    return CodexLocalCLIIdentityV1(
        version="1.2.3",
        package_lock_sha256="1" * 64,
        executable_sha256="2" * 64,
        executable_path="/codex",
        installation_tree_sha256="3" * 64,
    )


def _bindings() -> list[CodexLocalTaskBindingV1]:
    result = []
    index = 0
    for domain in DOMAINS:
        for route in ROUTES:
            for motif in MOTIFS:
                for replicate in REPLICATES:
                    token = f"{index + 10:064x}"
                    result.append(
                        CodexLocalTaskBindingV1(
                            blind_task_id=f"rp_{index:016x}",
                            brief_id=f"brief_{index:016x}",
                            route_id=route,
                            motif=motif,
                            replicate_id=replicate,
                            domain=domain,
                            package_fingerprint=token,
                            candidate_tree_sha256=f"{index + 40:064x}",
                            candidate_projection_sha256=f"{index + 70:064x}",
                            reality_evidence_sha256=f"{index + 100:064x}",
                            expected_deliverable=(
                                f"deliverable_files/output_{index}.xlsx"
                            ),
                        )
                    )
                    index += 1
    return result


class RepresentativeCodexLocalTests(unittest.TestCase):
    def test_compiler_validates_upstream_with_reality_tree_algorithm(self) -> None:
        source = inspect.getsource(compile_representative_codex_scope)
        self.assertIn(
            "_tree_sha(blind) != scope_cases[case_id].candidate_tree_sha256",
            source,
        )
        self.assertIn(
            "candidate_tree_sha256=_tree(blind)",
            source,
        )

    def test_v2_scope_accepts_complete_24_cell_matrix(self) -> None:
        scope = CodexLocalScreeningScopeV1(
            scope_version="v3.codex_local_screening_scope.2",
            cohort_kind="representative_production_pilot",
            campaign_id="representative",
            campaign_manifest_sha256="4" * 64,
            parity_report_sha256="5" * 64,
            source_fingerprint="6" * 64,
            cli=_cli(),
            task_bindings=_bindings(),
        )
        self.assertEqual(len(scope.task_bindings), 24)
        self.assertFalse(scope.training_authorized)
        self.assertFalse(scope.release_authorized)
        self.assertEqual(scope.process_attempts_per_task, 1)
        self.assertEqual(scope.runner_retry_count, 0)

    def test_v2_scope_rejects_missing_domain(self) -> None:
        payload = CodexLocalScreeningScopeV1(
            scope_version="v3.codex_local_screening_scope.2",
            cohort_kind="representative_production_pilot",
            campaign_id="representative",
            campaign_manifest_sha256="4" * 64,
            parity_report_sha256="5" * 64,
            source_fingerprint="6" * 64,
            cli=_cli(),
            task_bindings=_bindings(),
        ).model_dump(mode="json")
        payload = deepcopy(payload)
        payload["task_bindings"][0]["domain"] = None
        with self.assertRaisesRegex(ValidationError, "cells_incomplete"):
            CodexLocalScreeningScopeV1.model_validate(payload)

    def test_v1_scope_still_requires_12_matched_cells(self) -> None:
        bindings = []
        for item in _bindings():
            if item.domain == "audit_compliance":
                copied = item.model_copy(update={"domain": None})
                bindings.append(copied)
        scope = CodexLocalScreeningScopeV1(
            campaign_id="historical-matched",
            campaign_manifest_sha256="4" * 64,
            parity_report_sha256="5" * 64,
            source_fingerprint="6" * 64,
            cli=_cli(),
            task_bindings=bindings,
        )
        self.assertEqual(scope.scope_version, "v3.codex_local_screening_scope.1")
        self.assertEqual(scope.cohort_kind, "matched_screening")
        self.assertEqual(len(scope.task_bindings), 12)


if __name__ == "__main__":
    unittest.main()
