from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.task_generator.v3_formal_brief_admission import (
    SourceProvenanceLedgerV1,
    SourceProvenanceRecordV1,
)
from src.task_generator.v3_workflow_group_seed import WorkflowGroupSeedCompiler


class WorkflowGroupSeedTests(unittest.TestCase):
    def test_compiler_is_available(self):
        self.assertTrue(callable(WorkflowGroupSeedCompiler().compile))

    def test_ledger_schema_preserves_source_group(self):
        ledger = SourceProvenanceLedgerV1(
            records=[
                SourceProvenanceRecordV1(
                    source_candidate_id="source_candidate_001",
                    source_id="source_001",
                    source_kind="public_web",
                    source_group_id="audit_reconciliation",
                    locator="https://example.org/source",
                    evidence_refs=["evidence_001"],
                    evidence_spans=["block_001"],
                )
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "ledger.json"
            path.write_text(ledger.model_dump_json(indent=2), encoding="utf-8")
            loaded = SourceProvenanceLedgerV1.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        self.assertEqual(
            loaded.records[0].source_group_id,
            "audit_reconciliation",
        )


if __name__ == "__main__":
    unittest.main()
