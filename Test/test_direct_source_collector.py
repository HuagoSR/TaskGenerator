from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from task_generator.v3_direct_source_collector import (  # noqa: E402
    DirectWebSourceCollector,
)


class DirectSourceCollectorTests(unittest.TestCase):
    def test_exact_urls_bypass_search_and_preserve_public_provenance(self):
        collector = DirectWebSourceCollector(api_key="")
        url = "https://www.acquisition.gov/far/part-46"
        request = collector.build_request(
            topic="procurement controls",
            domain_tags=["procurement_operations"],
            queries=[url],
            source_count=1,
            collector_model="direct_url_trafilatura",
            search_backend="direct_url",
        )
        fetched = {
            "title": "FAR Part 46",
            "text_excerpt": "x" * 180,
            "raw_text": "y" * 600,
        }
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(
                collector,
                "_search",
                side_effect=AssertionError("search_must_not_run"),
            ), patch.object(collector, "_fetch_record", return_value=fetched):
                result = collector.collect(
                    output_dir=directory,
                    request=request,
                    seed_urls=[url],
                )
            self.assertEqual(result["report"].status, "success")
            self.assertEqual(result["metadata"]["input_mode"], "exact_urls")
            self.assertEqual(result["metadata"]["search_hits_examined"], 1)
            self.assertEqual(result["metadata"]["record_count"], 1)
            self.assertEqual(request.search_backend, "direct_url")
            raw_sources = list((Path(directory) / "raw_sources").glob("*.json"))
            self.assertEqual(len(raw_sources), 1)

    def test_https_hostname_allows_transparent_proxy_benchmark_mapping_only(self):
        collector = DirectWebSourceCollector(api_key="")
        mapped = [(None, None, None, None, ("198.18.0.194", 443))]
        with patch(
            "task_generator.v3_direct_source_collector.socket.getaddrinfo",
            return_value=mapped,
        ):
            collector._validate_public_url(  # pylint: disable=protected-access
                "https://www.acquisition.gov/far/part-46"
            )
            with self.assertRaises(RuntimeError):
                collector._validate_public_url(  # pylint: disable=protected-access
                    "http://www.acquisition.gov/far/part-46"
                )
            with self.assertRaises(RuntimeError):
                collector._validate_public_url(  # pylint: disable=protected-access
                    "https://198.18.0.194/far/part-46"
                )


if __name__ == "__main__":
    unittest.main()
