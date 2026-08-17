from __future__ import annotations

import tempfile
import tarfile
import unittest
from pathlib import Path

from Test.run_v3_reconstruction_docker_parity import (
    ROOT,
    SCP_TIMEOUT_SECONDS,
    build_snapshot,
    iter_snapshot_files,
    source_fingerprint,
)


class ReconstructionDockerParityTests(unittest.TestCase):
    def test_remote_transfer_is_compressed_and_slow_link_tolerant(self):
        source = (
            ROOT / "Test" / "run_v3_reconstruction_docker_parity.py"
        ).read_text(encoding="utf-8")
        self.assertEqual(SCP_TIMEOUT_SECONDS, 600)
        self.assertIn('"scp",\n            "-C"', source)

    def test_snapshot_is_deterministic_and_secret_free(self):
        files = iter_snapshot_files()
        relative = [path.relative_to(ROOT).as_posix() for path in files]
        self.assertEqual(relative, sorted(relative))
        self.assertIn(
            "deploy/docker/Dockerfile.reconstruction-parity",
            relative,
        )
        self.assertFalse(any(".env" in item.split("/") for item in relative))
        self.assertFalse(any("deepseek-key.txt" in item for item in relative))
        self.assertFalse(any("Test/v2_outputs/" in item for item in relative))
        self.assertEqual(source_fingerprint(files), source_fingerprint(files))

    def test_archive_contains_only_selected_snapshot_files(self):
        files = iter_snapshot_files()
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "snapshot.tar.gz"
            build_snapshot(archive_path, files)
            with tarfile.open(archive_path, "r:gz") as archive:
                names = archive.getnames()
        self.assertEqual(
            names,
            [path.relative_to(ROOT).as_posix() for path in files],
        )
        self.assertFalse(any(name.startswith("artifacts/") for name in names))


if __name__ == "__main__":
    unittest.main()
