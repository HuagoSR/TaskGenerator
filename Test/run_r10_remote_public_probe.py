"""Validate the fixed Huago R10 eval stacks without uploading task material."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "Test"))

from run_r10_behavioral_pilot import STACKS, _record_probe, _safe_remote_root


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="huago-cone")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if args.output_root.exists():
        raise FileExistsError("r10_remote_public_probe_output_exists")
    args.output_root.mkdir(parents=True)
    remote_root = _safe_remote_root(args.host, args.run_id)
    results = {
        stack: _record_probe(
            output_root=args.output_root, host=args.host, remote_root=remote_root,
            stack=stack, image=args.image,
        )
        for stack in STACKS
    }
    (args.output_root / "result.json").write_text(
        json.dumps({"probe_version": "r10.remote_public_probe.1", "results": results}, indent=2) + "\n",
        encoding="utf-8",
    )
    if not all(results.values()):
        raise RuntimeError("r10_remote_public_probe_failed")


if __name__ == "__main__":
    main()
