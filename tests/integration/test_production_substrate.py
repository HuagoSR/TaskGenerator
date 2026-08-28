from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from task_generator.core.source_schema import (
    ExtractedSkillCandidate,
    SemanticContract,
    SkillEvidence,
)
from task_generator.production.campaign import (
    ProductionSourceRecordV1,
    atomic_json,
    file_sha,
)
from task_generator.production.substrate import ProductionSubstrateBuilder, _retryable_error
from task_generator.substrate.skill_extractor import ProviderConfig


class _FakeExtractor:
    def __init__(self, config):
        self.last_response_diagnostics = type(
            "Diagnostics", (), {"finish_reason": "stop", "prompt_tokens": 10, "completion_tokens": 10, "response_sha256": "a" * 64}
        )()

    def extract(self, package, max_candidates=8):
        domain = package.normalized_sources[0].domain_tags[0]
        source_ids = [item.source_id for item in package.normalized_sources]
        values = []
        for index in range(3):
            source_id = source_ids[index]
            values.append(
                ExtractedSkillCandidate(
                    candidate_id=f"raw_{domain}_{index}",
                    source_ids=[source_id],
                    proposed_name=f"{domain} capability {index}",
                    domain_tags=[domain],
                    capability_tags=["evidence_validation"],
                    difficulty_tags=["exception_reasoning"],
                    input_contract=SemanticContract(requires_semantics=["Evidence:Record"]),
                    output_contract=SemanticContract(provides_semantics=["Decision:Finding"]),
                    business_meaning="Apply source-grounded evidence review.",
                    hidden_difficulty="Resolve conflicting operational evidence.",
                    common_failure_modes=["misses an exception"],
                    common_deliverables=["review workbook"],
                    assembly_hints=["preserve traceability"],
                    evidence=[
                        SkillEvidence(
                            evidence_id=f"raw_evidence_{index}",
                            source_id=source_id,
                            normalized_source_id=package.normalized_sources[index].normalized_source_id,
                            block_ids=["block_0001"],
                            evidence_summary="Grounded in the first visible source block.",
                        )
                    ],
                )
            )
        return values


class ProductionSubstrateTests(unittest.TestCase):
    def test_cloudflare_524_is_a_single_retryable_transport_failure(self):
        self.assertTrue(_retryable_error(RuntimeError("Error code: 524")))

    def test_builds_two_reviewed_scratch_pools_without_registry_mutation(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            raw = root / "raw_sources"
            raw.mkdir()
            records = []
            domains = ("audit_compliance",) * 3 + ("procurement_operations",) * 3
            for index, domain in enumerate(domains):
                path = raw / f"source_{index}.html"
                path.write_text(
                    "<html><body><main>"
                    "<p>This official requirement explains the evidence and control review needed before approval.</p>"
                    "<p>Reviewers must compare independent records and document each exception with supporting evidence.</p>"
                    "<p>The final workpaper must identify unresolved matters and describe an appropriate disposition.</p>"
                    "</main></body></html>",
                    encoding="utf-8",
                )
                records.append(
                    ProductionSourceRecordV1(
                        source_id=f"source_{index}",
                        domain=domain,
                        canonical_url=("https://pcaobus.org/example" if domain == "audit_compliance" else "https://www.acquisition.gov/example"),
                        allowed_host=("pcaobus.org" if domain == "audit_compliance" else "www.acquisition.gov"),
                        collected_path=str(path),
                        content_sha256=file_sha(path),
                        collected_at="2026-08-26T00:00:00Z",
                    )
                )
            manifest = raw / "source_manifest.json"
            atomic_json(manifest, {"sources": [item.model_dump(mode="json") for item in records]})
            registry = root / "registry"
            registry.mkdir()
            (registry / "canonical.json").write_text('{"entries": []}\n', encoding="utf-8")
            result = ProductionSubstrateBuilder(extractor_factory=_FakeExtractor).build(
                campaign_id="fresh_campaign",
                sources=records,
                source_manifest_path=manifest,
                output_root=root / "substrate",
                canonical_registry_root=registry,
                provider_config=ProviderConfig(provider_name="tuzi", base_url="https://example.test", api_key="secret", model="gpt-5.6-sol"),
            )
            self.assertFalse(result.canonical_registry_mutated)
            self.assertEqual(result.canonical_registry_sha256_before, result.canonical_registry_sha256_after)
            self.assertEqual([item.accepted_count for item in result.domains], [3, 3])
            self.assertTrue(Path(result.scratch_registry_path).is_file())
            for item in result.domains:
                payload = json.loads(Path(item.accepted_candidate_path).read_text(encoding="utf-8"))
                self.assertEqual(len(payload["accepted_candidates"]), 3)
                self.assertEqual(item.provider_attempt_count, 1)


if __name__ == "__main__":
    unittest.main()
