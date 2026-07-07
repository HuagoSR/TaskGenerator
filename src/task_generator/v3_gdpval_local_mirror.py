from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from task_generator.v3_gdpval_utils import (
    DEFAULT_CACHE_DIR,
    DEFAULT_GDPVAL_DATASET,
    DEFAULT_GDPVAL_SPLIT,
    compact_text,
    copy_hf_dataset_file,
    ensure_dir,
    file_extensions,
    keyword_hits,
    load_gdpval_rows,
    sha256_text,
    slugify,
)


class MirroredReferenceFile(BaseModel):
    source_relative_path: str
    destination_path: str
    file_name: str
    sha256: str
    size_bytes: int
    cached_path: Optional[str] = None


class GDPValMirrorTaskRecord(BaseModel):
    task_id: str
    sector: str
    occupation: str
    prompt_path: str
    metadata_path: str
    file_manifest_path: str
    source_hashes_path: str
    reference_files_dir: str
    reference_file_count: int = 0
    mirrored_reference_file_count: int = 0
    deliverable_file_count: int = 0
    reference_file_extensions: List[str] = Field(default_factory=list)
    deliverable_file_extensions: List[str] = Field(default_factory=list)
    reference_files: List[MirroredReferenceFile] = Field(default_factory=list)
    use: str = "eval_calibration_only"
    not_for_training_generation: bool = True


class GDPValLocalMirrorRequest(BaseModel):
    dataset_name: str = DEFAULT_GDPVAL_DATASET
    split: str = DEFAULT_GDPVAL_SPLIT
    output_dir: str
    allow_network: bool = False
    cache_dir: str = str(DEFAULT_CACHE_DIR)
    limit: int = 0
    overwrite: bool = False
    include_rubrics: bool = True


class GDPValLocalMirrorManifest(BaseModel):
    mirror_manifest_version: str = "v3.gdpval_local_mirror.1"
    request: GDPValLocalMirrorRequest
    dataset_name: str
    split: str
    mirror_created_at: str
    use: str = "eval_calibration_only"
    task_count: int = 0
    task_ids: List[str] = Field(default_factory=list)
    hash_policy: str = "prompt_and_reference_files"
    not_for_training_generation: bool = True
    mirrored_reference_file_count: int = 0
    mirrored_reference_bytes: int = 0
    rubric_included_for_calibration_only: bool = True
    tasks: List[GDPValMirrorTaskRecord] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class GDPValLocalMirrorBuilder:
    def build(
        self,
        *,
        output_dir: str | Path,
        dataset_name: str = DEFAULT_GDPVAL_DATASET,
        split: str = DEFAULT_GDPVAL_SPLIT,
        allow_network: bool = False,
        cache_dir: str | Path = DEFAULT_CACHE_DIR,
        limit: int = 0,
        overwrite: bool = False,
        include_rubrics: bool = True,
    ) -> GDPValLocalMirrorManifest:
        request = GDPValLocalMirrorRequest(
            dataset_name=dataset_name,
            split=split,
            output_dir=str(output_dir),
            allow_network=allow_network,
            cache_dir=str(cache_dir),
            limit=limit,
            overwrite=overwrite,
            include_rubrics=include_rubrics,
        )
        rows = load_gdpval_rows(
            dataset_name=dataset_name,
            split=split,
            allow_network=allow_network,
            cache_dir=cache_dir,
        )
        selected_rows = rows[:limit] if limit > 0 else rows
        mirror_root = ensure_dir(output_dir)
        tasks_root = ensure_dir(mirror_root / "tasks")

        task_records: List[GDPValMirrorTaskRecord] = []
        mirrored_bytes = 0
        mirrored_file_count = 0
        for row in selected_rows:
            record = self._mirror_task(
                row=row,
                tasks_root=tasks_root,
                dataset_name=dataset_name,
                allow_network=allow_network,
                cache_dir=cache_dir,
                overwrite=overwrite,
                include_rubrics=include_rubrics,
            )
            task_records.append(record)
            mirrored_file_count += record.mirrored_reference_file_count
            mirrored_bytes += sum(item.size_bytes for item in record.reference_files)

        manifest = GDPValLocalMirrorManifest(
            request=request,
            dataset_name=dataset_name,
            split=split,
            mirror_created_at=datetime.now(timezone.utc).isoformat(),
            task_count=len(task_records),
            task_ids=[record.task_id for record in task_records],
            mirrored_reference_file_count=mirrored_file_count,
            mirrored_reference_bytes=mirrored_bytes,
            rubric_included_for_calibration_only=include_rubrics,
            tasks=task_records,
            notes=[
                "GDPVal local mirror is calibration-only and must not be used as TaskGenerator training input.",
                "Reference files are mirrored locally; deliverable files remain metadata-only to avoid leaking target outputs into generation paths.",
                "Rubric artifacts stay isolated inside the calibration mirror and must not be routed into Pipeline A or production generation.",
            ],
        )
        manifest_path = mirror_root / "dataset_manifest.json"
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        return manifest

    def _mirror_task(
        self,
        *,
        row: Dict[str, Any],
        tasks_root: Path,
        dataset_name: str,
        allow_network: bool,
        cache_dir: str | Path,
        overwrite: bool,
        include_rubrics: bool,
    ) -> GDPValMirrorTaskRecord:
        task_id = str(row["task_id"])
        task_slug = slugify(task_id)
        task_dir = ensure_dir(tasks_root / task_slug)
        reference_dir = ensure_dir(task_dir / "reference_files")
        prompt_path = task_dir / "prompt.txt"
        metadata_path = task_dir / "metadata.json"
        file_manifest_path = task_dir / "file_manifest.json"
        source_hashes_path = task_dir / "source_hashes.json"
        calibration_dir = ensure_dir(task_dir / "calibration_only")

        prompt_text = str(row.get("prompt", ""))
        if overwrite or not prompt_path.exists():
            prompt_path.write_text(prompt_text, encoding="utf-8")

        mirrored_files: List[MirroredReferenceFile] = []
        for relative_path in row.get("reference_files") or []:
            file_name = Path(str(relative_path)).name
            destination_path = reference_dir / file_name
            if overwrite or not destination_path.exists():
                download_info = copy_hf_dataset_file(
                    dataset_name=dataset_name,
                    relative_path=str(relative_path),
                    destination_path=destination_path,
                    allow_network=allow_network,
                    cache_dir=cache_dir,
                )
            else:
                download_info = {
                    "source_relative_path": str(relative_path),
                    "destination_path": str(destination_path),
                    "cached_path": None,
                    "sha256": "",
                    "size_bytes": destination_path.stat().st_size,
                }
            mirrored_files.append(
                MirroredReferenceFile(
                    source_relative_path=str(relative_path),
                    destination_path=str(destination_path),
                    file_name=file_name,
                    sha256=download_info["sha256"] or self._sha256_from_existing(source_hashes_path, file_name),
                    size_bytes=int(download_info["size_bytes"]),
                    cached_path=download_info.get("cached_path"),
                )
            )

        if include_rubrics:
            rubric_pretty_path = calibration_dir / "rubric_pretty.txt"
            rubric_json_path = calibration_dir / "rubric_json.json"
            if overwrite or not rubric_pretty_path.exists():
                rubric_pretty_path.write_text(str(row.get("rubric_pretty", "")), encoding="utf-8")
            if overwrite or not rubric_json_path.exists():
                rubric_payload = row.get("rubric_json", "")
                try:
                    pretty_json = json.dumps(json.loads(str(rubric_payload)), ensure_ascii=False, indent=2)
                except json.JSONDecodeError:
                    pretty_json = json.dumps({"raw_rubric_json": str(rubric_payload)}, ensure_ascii=False, indent=2)
                rubric_json_path.write_text(pretty_json, encoding="utf-8")

        metadata = {
            "task_id": task_id,
            "sector": str(row.get("sector", "")),
            "occupation": str(row.get("occupation", "")),
            "prompt_char_count": len(prompt_text),
            "reference_files": list(row.get("reference_files") or []),
            "reference_file_urls": list(row.get("reference_file_urls") or []),
            "reference_file_hf_uris": list(row.get("reference_file_hf_uris") or []),
            "deliverable_files": list(row.get("deliverable_files") or []),
            "deliverable_file_urls": list(row.get("deliverable_file_urls") or []),
            "deliverable_file_hf_uris": list(row.get("deliverable_file_hf_uris") or []),
            "deliverable_file_extensions": file_extensions(row.get("deliverable_files") or []),
            "reference_file_extensions": file_extensions(row.get("reference_files") or []),
            "use": "eval_calibration_only",
            "not_for_training_generation": True,
            "contains_rubrics_for_calibration_only": include_rubrics,
            "prompt_keyword_hits": keyword_hits(
                prompt_text,
                [
                    "audit",
                    "account",
                    "finance",
                    "budget",
                    "memo",
                    "report",
                    "reconcile",
                    "policy",
                    "control",
                    "spreadsheet",
                    "workbook",
                ],
            ),
        }
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        file_manifest = {
            "task_id": task_id,
            "prompt_path": "prompt.txt",
            "reference_files_dir": "reference_files",
            "reference_files": [item.model_dump(mode="json") for item in mirrored_files],
            "calibration_only_dir": "calibration_only" if include_rubrics else None,
            "contains_rubric_artifacts": include_rubrics,
            "deliverable_files_metadata_only": list(row.get("deliverable_files") or []),
        }
        file_manifest_path.write_text(json.dumps(file_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        source_hashes = {
            "task_id": task_id,
            "hash_policy": "prompt_and_reference_files",
            "prompt_sha256": sha256_text(prompt_text),
            "reference_file_hashes": {
                item.file_name: item.sha256
                for item in mirrored_files
            },
            "reference_file_sizes": {
                item.file_name: item.size_bytes
                for item in mirrored_files
            },
            "calibration_artifact_hashes": (
                {
                    "rubric_pretty_sha256": sha256_text(str(row.get("rubric_pretty", ""))),
                    "rubric_json_sha256": sha256_text(str(row.get("rubric_json", ""))),
                }
                if include_rubrics
                else {}
            ),
        }
        source_hashes_path.write_text(json.dumps(source_hashes, ensure_ascii=False, indent=2), encoding="utf-8")

        return GDPValMirrorTaskRecord(
            task_id=task_id,
            sector=str(row.get("sector", "")),
            occupation=str(row.get("occupation", "")),
            prompt_path=str(prompt_path),
            metadata_path=str(metadata_path),
            file_manifest_path=str(file_manifest_path),
            source_hashes_path=str(source_hashes_path),
            reference_files_dir=str(reference_dir),
            reference_file_count=len(list(row.get("reference_files") or [])),
            mirrored_reference_file_count=len(mirrored_files),
            deliverable_file_count=len(list(row.get("deliverable_files") or [])),
            reference_file_extensions=file_extensions(row.get("reference_files") or []),
            deliverable_file_extensions=file_extensions(row.get("deliverable_files") or []),
            reference_files=mirrored_files,
        )

    def _sha256_from_existing(self, source_hashes_path: Path, file_name: str) -> str:
        if not source_hashes_path.exists():
            return ""
        try:
            payload = json.loads(source_hashes_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return ""
        hash_map = payload.get("reference_file_hashes") or {}
        return str(hash_map.get(file_name) or "")
