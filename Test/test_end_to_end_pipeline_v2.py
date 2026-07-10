from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_end_to_end_pipeline import (  # noqa: E402
    STAGE_ORDER,
    EndToEndManifest,
    EndToEndPipeline,
    EndToEndRequest,
    StageStatus,
)


class FakePipeline(EndToEndPipeline):
    def __init__(self, repo_root: Path, fail_stage: str | None = None) -> None:
        super().__init__(repo_root)
        self.fail_stage = fail_stage
        self.calls: list[str] = []
        self.revisions: dict[str, int] = {stage: 1 for stage in STAGE_ORDER}

    def _run_stage(self, stage, request, run_dir, manifest):  # type: ignore[override]
        self.calls.append(stage)
        if self.fail_stage == stage:
            raise RuntimeError(f"injected failure at {stage}")
        stage_dir = Path(run_dir) / self._stage_dir_name(stage)
        stage_dir.mkdir(parents=True, exist_ok=True)
        marker = stage_dir / "marker.json"
        marker.write_text(
            json.dumps({"stage": stage, "revision": self.revisions[stage]}),
            encoding="utf-8",
        )
        return StageStatus(
            stage=stage,
            state="completed",
            artifact_paths={"marker": str(marker)},
            summary={"stage": stage, "revision": self.revisions[stage]},
        )


class EndToEndPipelineV2Tests(unittest.TestCase):
    def _repo(self, root: Path) -> Path:
        repo = root / "repo"
        registry_dir = repo / "SkillRegistry"
        registry_dir.mkdir(parents=True)
        (repo / "Test").mkdir()
        (registry_dir / "v3_skill_registry.json").write_text(
            json.dumps({"registry_version": "v3.0", "entry_count": 0, "entries": []}),
            encoding="utf-8",
        )
        return repo

    def _request(self, run_id: str, *, action: str = "run", from_stage: str | None = None) -> EndToEndRequest:
        return EndToEndRequest(
            run_id=run_id,
            selected_stages=list(STAGE_ORDER),
            action=action,
            profile="custom",
            from_stage=from_stage,
            source_mode="existing",
            registry_mode="snapshot_scratch",
            eval_mode="prepare_only",
        )

    def test_stage_dependency_expansion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pipeline = EndToEndPipeline(self._repo(Path(tmp)))
            self.assertEqual(
                pipeline._expanded_stages(["task_generation"]),
                ["source_to_skills", "registry_prepare", "task_generation"],
            )

    def test_atomic_json_write_leaves_no_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pipeline = EndToEndPipeline(self._repo(Path(tmp)))
            target = Path(tmp) / "manifest.json"
            pipeline._atomic_write_json(target, {"ok": True})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"ok": True})
            self.assertFalse(target.with_name("manifest.json.tmp").exists())

    def test_external_eval_requires_both_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(Path(tmp))
            pipeline = EndToEndPipeline(repo)
            request = self._request("gated").model_copy(
                update={"eval_mode": "execute", "run_eval": True, "allow_external_eval": False}
            )
            manifest = EndToEndManifest(
                run_id="gated",
                created_at="now",
                updated_at="now",
                request=request,
                run_dir=str(Path(tmp) / "run"),
                stage_status_path=str(Path(tmp) / "run" / "stages.json"),
                summary_report_path=str(Path(tmp) / "run" / "summary.json"),
            )
            with self.assertRaisesRegex(ValueError, "External eval requires"):
                pipeline._stage_rw_task_eval(
                    StageStatus(stage="rw_task_eval"), request, Path(tmp) / "eval", manifest
                )

    def test_failure_at_each_stage_resumes_without_repeating_completed_upstream(self) -> None:
        for failed_stage in STAGE_ORDER:
            with self.subTest(stage=failed_stage), tempfile.TemporaryDirectory() as tmp:
                repo = self._repo(Path(tmp))
                output = Path(tmp) / "runs"
                pipeline = FakePipeline(repo, fail_stage=failed_stage)
                with self.assertRaisesRegex(RuntimeError, "injected failure"):
                    pipeline.run(self._request("fault"), output)
                prior_calls = list(pipeline.calls)
                pipeline.fail_stage = None
                resumed = pipeline.run(self._request("fault", action="resume"), output)
                failed_index = STAGE_ORDER.index(failed_stage)
                self.assertEqual(pipeline.calls[len(prior_calls) :], STAGE_ORDER[failed_index:])
                self.assertTrue(all(status.state in {"completed", "reused"} for status in resumed.stages.values()))

    def test_rerun_from_stage_increments_downstream_attempts_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(Path(tmp))
            output = Path(tmp) / "runs"
            pipeline = FakePipeline(repo)
            initial = pipeline.run(self._request("rerun"), output)
            self.assertTrue(all(status.attempt_count == 1 for status in initial.stages.values()))
            rerun = pipeline.run(
                self._request("rerun", action="rerun", from_stage="task_generation"), output
            )
            self.assertEqual(rerun.stages["source_to_skills"].attempt_count, 1)
            self.assertEqual(rerun.stages["registry_prepare"].attempt_count, 1)
            self.assertEqual(rerun.stages["task_generation"].attempt_count, 2)
            self.assertEqual(rerun.stages["production_review"].attempt_count, 2)
            self.assertEqual(rerun.stages["rw_task_eval"].attempt_count, 2)

    def test_missing_checksum_artifact_forces_stage_rerun(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(Path(tmp))
            output = Path(tmp) / "runs"
            pipeline = FakePipeline(repo)
            first = pipeline.run(self._request("checksum"), output)
            marker = Path(first.stages["registry_prepare"].artifact_paths["marker"])
            marker.unlink()
            resumed = pipeline.run(self._request("checksum", action="resume"), output)
            self.assertEqual(resumed.stages["source_to_skills"].state, "reused")
            self.assertEqual(resumed.stages["registry_prepare"].attempt_count, 2)

    def test_resume_rejects_conflicting_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(Path(tmp))
            output = Path(tmp) / "runs"
            pipeline = FakePipeline(repo)
            pipeline.run(self._request("frozen"), output)
            conflicting = self._request("frozen", action="resume").model_copy(
                update={"source_mode": "web", "allow_web_collection": True}
            )
            with self.assertRaisesRegex(ValueError, "conflicts with the frozen request"):
                pipeline.run(conflicting, output)

    def test_command_redaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pipeline = EndToEndPipeline(self._repo(Path(tmp)))
            self.assertEqual(
                pipeline._redact_command(["runner", "--api-key", "secret-value", "--model", "x"]),
                ["runner", "--api-key", "<redacted>", "--model", "x"],
            )


if __name__ == "__main__":
    unittest.main()
