from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


CAMPAIGN_STATES = {
    "new", "collecting_sources", "source_frozen", "generating",
    "awaiting_holistic_review", "awaiting_assistant_review", "revising_system",
    "completed", "blocked",
}


class AssistantReviewRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slot: int = Field(ge=1, le=8)
    revision: int = Field(ge=1, le=2)
    decision: Literal["pass", "revise_system", "blocked"]
    candidate_blind_completed: bool
    deterministic_recomputation_pass: bool
    visual_review_pass: bool
    teacher_rubric_review_pass: bool
    verifier_export_pass: bool
    unresolved_material_ambiguity: bool
    findings: list[str] = Field(default_factory=list, max_length=20)
    responsibility: Literal[
        "none", "source_skill", "generator", "terra_editorial_contract",
        "deterministic_validation", "luna_blind_solve", "release_gate",
    ] = "none"
    reviewed_at: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


class F4FromScratchCampaign:
    """Persistent gatekeeper for one-source-freeze, one-task-at-a-time F4 validation."""

    def __init__(self, root: Path, spec_path: Path, canonical_registry: Path) -> None:
        self.root = root
        self.spec_path = spec_path
        self.spec = load_json(spec_path)
        self.canonical_registry = canonical_registry
        self.manifest_path = root / "campaign_manifest.json"
        self.source_freeze_path = root / "source_freeze_manifest.json"
        self.registry_path = root / "state" / "scratch_registry.json"

    def initialize(self) -> dict[str, Any]:
        self.root.mkdir(parents=True, exist_ok=True)
        if self.manifest_path.exists():
            return self.read()
        atomic_json(self.registry_path, {"registry_version": "v3.0", "entry_count": 0, "entries": []})
        manifest = {
            "manifest_version": "v3.finance_f4_from_scratch_manifest.1",
            "campaign_id": self.spec["campaign_id"],
            "state": "new",
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "spec_sha256": sha256_file(self.spec_path),
            "canonical_registry_sha256_before": sha256_file(self.canonical_registry),
            "canonical_registry_sha256_after": None,
            "source_collection_count": 0,
            "source_frozen": False,
            "current_slot": 1,
            "slots": [self._slot_record(item) for item in self.spec["slots"]],
            "external_effects": dict(self.spec["external_effects"]),
            "external_solver_eval": False,
            "external_grader_eval": False,
        }
        self._write(manifest)
        return manifest

    def read(self) -> dict[str, Any]:
        manifest = load_json(self.manifest_path)
        if manifest["state"] not in CAMPAIGN_STATES:
            raise ValueError("unknown campaign state")
        return manifest

    def begin_source_collection(self) -> dict[str, Any]:
        manifest = self.initialize()
        if manifest["source_collection_count"] != 0 or manifest["source_frozen"]:
            raise RuntimeError("source_collection_is_single_use")
        manifest["state"] = "collecting_sources"
        manifest["source_collection_count"] = 1
        self._write(manifest)
        return manifest

    def freeze_sources(self, files: list[Path], source_run_manifest: Path) -> dict[str, Any]:
        manifest = self.read()
        if manifest["state"] != "collecting_sources":
            raise RuntimeError("source_collection_not_running")
        entries = []
        for path in sorted(files):
            if path.is_file():
                entries.append({"path": str(path), "sha256": sha256_file(path), "size": path.stat().st_size})
        if not entries or not self.registry_path.exists():
            raise RuntimeError("source_or_registry_empty")
        freeze = {
            "freeze_version": "v3.finance_f4_source_freeze.1",
            "created_at": utc_now(),
            "source_run_manifest": str(source_run_manifest),
            "source_run_manifest_sha256": sha256_file(source_run_manifest),
            "scratch_registry_sha256": sha256_file(self.registry_path),
            "files": entries,
        }
        atomic_json(self.source_freeze_path, freeze)
        manifest["state"] = "source_frozen"
        manifest["source_frozen"] = True
        manifest["source_freeze_sha256"] = sha256_file(self.source_freeze_path)
        self._write(manifest)
        return manifest

    def assert_frozen_inputs(self) -> None:
        manifest = self.read()
        if not manifest["source_frozen"] or not self.source_freeze_path.exists():
            raise RuntimeError("source_not_frozen")
        freeze = load_json(self.source_freeze_path)
        if sha256_file(self.registry_path) != freeze["scratch_registry_sha256"]:
            raise RuntimeError("scratch_registry_changed_after_freeze")
        for item in freeze["files"]:
            path = Path(item["path"])
            if not path.exists() or sha256_file(path) != item["sha256"]:
                raise RuntimeError("source_file_changed_after_freeze")

    def begin_slot(self, slot: int) -> dict[str, Any]:
        self.assert_frozen_inputs()
        manifest = self.read()
        if slot != manifest["current_slot"]:
            raise RuntimeError("slot_out_of_order")
        if slot > 1 and manifest["slots"][slot - 2]["state"] != "passed":
            raise RuntimeError("previous_slot_not_released")
        record = manifest["slots"][slot - 1]
        if record["state"] not in {"pending", "revising_system"}:
            raise RuntimeError("slot_not_startable")
        record["state"] = "generating"
        record["attempts"] += 1
        manifest["state"] = "generating"
        self._write(manifest)
        return manifest

    def mark_generated(self, slot: int, run_manifest: Path) -> dict[str, Any]:
        manifest = self.read()
        record = manifest["slots"][slot - 1]
        if record["state"] != "generating":
            raise RuntimeError("slot_not_generating")
        record.update({
            "state": "awaiting_holistic_review",
            "task_run_manifest": str(run_manifest),
            "task_run_manifest_sha256": sha256_file(run_manifest),
        })
        manifest["state"] = "awaiting_holistic_review"
        self._write(manifest)
        return manifest

    def mark_holistic_complete(self, slot: int, evidence_dir: Path) -> dict[str, Any]:
        manifest = self.read()
        record = manifest["slots"][slot - 1]
        if record["state"] != "awaiting_holistic_review":
            raise RuntimeError("holistic_review_not_expected")
        required = [
            evidence_dir / "provider" / "whole_task_revision_bundle_v2.json",
            evidence_dir / "luna_candidate_solve.json",
            evidence_dir / "deterministic_validation.json",
            evidence_dir / "visual_qa" / "visual_qa_report.json",
            evidence_dir / "final_package" / "materialization_report.json",
        ]
        missing = [str(path.relative_to(evidence_dir)) for path in required if not path.exists()]
        if missing:
            raise RuntimeError("holistic_evidence_incomplete:" + ",".join(missing))
        record["state"] = "awaiting_assistant_review"
        record["holistic_evidence_dir"] = str(evidence_dir)
        record["holistic_evidence_sha256"] = self._tree_sha(evidence_dir)
        manifest["state"] = "awaiting_assistant_review"
        self._write(manifest)
        return manifest

    def apply_review(self, review: AssistantReviewRecord) -> dict[str, Any]:
        manifest = self.read()
        record = manifest["slots"][review.slot - 1]
        if record["state"] != "awaiting_assistant_review":
            raise RuntimeError("assistant_review_not_expected")
        if review.decision == "pass" and not all([
            review.candidate_blind_completed,
            review.deterministic_recomputation_pass,
            review.visual_review_pass,
            review.teacher_rubric_review_pass,
            review.verifier_export_pass,
            not review.unresolved_material_ambiguity,
        ]):
            raise ValueError("pass_review_has_failed_gate")
        review_path = self.root / "slots" / f"slot_{review.slot:02d}" / f"revision_{review.revision:02d}" / "assistant_review.json"
        atomic_json(review_path, review.model_dump(mode="json"))
        record["assistant_review_path"] = str(review_path)
        record["assistant_review_sha256"] = sha256_file(review_path)
        if review.decision == "pass":
            record["state"] = "passed"
            manifest["current_slot"] = review.slot + 1
            if review.slot == len(manifest["slots"]):
                manifest["state"] = "completed"
                manifest["decision"] = "f4_from_scratch_validation_passed"
                manifest["canonical_registry_sha256_after"] = sha256_file(self.canonical_registry)
                if manifest["canonical_registry_sha256_after"] != manifest["canonical_registry_sha256_before"]:
                    raise RuntimeError("canonical_registry_changed")
            else:
                manifest["state"] = "source_frozen"
        elif review.decision == "revise_system" and record["attempts"] < self.spec["maximum_system_revisions_per_slot"]:
            record["state"] = "revising_system"
            manifest["state"] = "revising_system"
        else:
            record["state"] = "blocked"
            manifest["state"] = "blocked"
            manifest["decision"] = "f4_from_scratch_validation_blocked"
        self._write(manifest)
        return manifest

    def _write(self, manifest: dict[str, Any]) -> None:
        manifest["updated_at"] = utc_now()
        atomic_json(self.manifest_path, manifest)

    @staticmethod
    def _slot_record(item: dict[str, Any]) -> dict[str, Any]:
        return {
            **item,
            "state": "pending",
            "attempts": 0,
            "default_promotion_allowed": False if item.get("experimental_motif") else None,
        }

    @staticmethod
    def _tree_sha(root: Path) -> str:
        digest = hashlib.sha256()
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            digest.update(str(path.relative_to(root)).encode())
            digest.update(bytes.fromhex(sha256_file(path)))
        return digest.hexdigest()
