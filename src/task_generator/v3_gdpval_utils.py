from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from datasets import DownloadConfig, load_dataset
from huggingface_hub import hf_hub_download


DEFAULT_GDPVAL_DATASET = "openai/gdpval"
DEFAULT_GDPVAL_SPLIT = "train"
DEFAULT_CACHE_DIR = Path(".cache") / "gdpval"


def stable_id(prefix: str, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "item"


def ensure_dir(path: str | Path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def load_gdpval_rows(
    dataset_name: str = DEFAULT_GDPVAL_DATASET,
    split: str = DEFAULT_GDPVAL_SPLIT,
    *,
    allow_network: bool = False,
    cache_dir: str | Path | None = None,
) -> List[Dict[str, Any]]:
    download_config = DownloadConfig(local_files_only=not allow_network)
    dataset = load_dataset(
        dataset_name,
        split=split,
        download_config=download_config,
        cache_dir=str(cache_dir) if cache_dir else None,
    )
    return [dict(row) for row in dataset]


def copy_hf_dataset_file(
    *,
    dataset_name: str,
    relative_path: str,
    destination_path: str | Path,
    allow_network: bool,
    cache_dir: str | Path | None = None,
) -> Dict[str, Any]:
    downloaded_path = hf_hub_download(
        repo_id=dataset_name,
        repo_type="dataset",
        filename=relative_path,
        local_files_only=not allow_network,
        cache_dir=str(cache_dir) if cache_dir else None,
    )
    destination = Path(destination_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(downloaded_path, destination)
    return {
        "source_relative_path": relative_path,
        "cached_path": str(downloaded_path),
        "destination_path": str(destination),
        "sha256": sha256_file(destination),
        "size_bytes": destination.stat().st_size,
    }


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compact_text(text: str) -> str:
    return " ".join(text.split())


def file_extensions(paths: Iterable[str]) -> List[str]:
    values = sorted(
        {
            (Path(item).suffix.lower() or "<no_ext>")
            for item in paths
            if str(item).strip()
        }
    )
    return values


def keyword_hits(text: str, keywords: Sequence[str]) -> List[str]:
    lowered = compact_text(text).lower()
    return [keyword for keyword in keywords if keyword in lowered]
