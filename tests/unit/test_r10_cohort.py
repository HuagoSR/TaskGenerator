from __future__ import annotations

import unittest

from task_generator.production.r10_cohort import (
    R10CohortManifestV1,
    R10CohortTaskStateV1,
    advance_task_state,
)


class R10CohortTests(unittest.TestCase):
    def test_ten_task_manifest_requires_balanced_domains_and_formats(self):
        tasks = [
            R10CohortTaskStateV1(
                task_id=f"task-{number}",
                domain="audit_compliance" if number < 5 else "procurement_operations",
                deliverable_format="xlsx" if number in {0, 1, 2, 5, 6} else "docx",
            )
            for number in range(10)
        ]
        manifest = R10CohortManifestV1(campaign_id="r10", source_commit="a" * 40, tasks=tasks)
        self.assertEqual(len(manifest.tasks), 10)
        broken = list(tasks)
        broken[9] = broken[9].model_copy(update={"domain": "audit_compliance"})
        with self.assertRaises(ValueError):
            R10CohortManifestV1(campaign_id="r10", source_commit="a" * 40, tasks=broken)

    def test_terminal_task_cannot_be_silently_resumed(self):
        manifest = R10CohortManifestV1(campaign_id="r10", source_commit="a" * 40, tasks=[
            R10CohortTaskStateV1(task_id="task", domain="audit_compliance", deliverable_format="xlsx")
        ])
        blocked = advance_task_state(manifest, task_id="task", stage="blocked", first_failure="source_missing")
        with self.assertRaises(ValueError):
            advance_task_state(blocked, task_id="task", stage="seed_admitted")


if __name__ == "__main__":
    unittest.main()
