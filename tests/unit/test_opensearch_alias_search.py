"""Unit tests for flows/opensearch_alias_search.py (no OpenSearch cluster)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "flows"))

try:
    import opensearch_alias_search as alias  # noqa: E402
except ModuleNotFoundError as e:
    if getattr(e, "name", "") == "opensearchpy":
        alias = None  # type: ignore[assignment]
    else:
        raise


def _gef(model_name: str) -> str:
    return f"chunk_embedding_{model_name}"


@unittest.skipIf(alias is None, "opensearchpy not installed")
class TestKnnQueriesForPhysicalIndex(unittest.TestCase):
    def test_skips_missing_field(self) -> None:
        knn_fields = {"chunk_embedding_a": 3}
        qe = {"a": [1.0, 2.0, 3.0], "b": [1.0, 2.0, 3.0]}
        out = alias.knn_queries_for_physical_index(knn_fields, qe, _gef)
        self.assertEqual(len(out), 1)
        self.assertIn("chunk_embedding_a", out[0]["knn"])

    def test_skips_dimension_mismatch(self) -> None:
        knn_fields = {"chunk_embedding_a": 3}
        qe = {"a": [1.0, 2.0]}
        out = alias.knn_queries_for_physical_index(knn_fields, qe, _gef)
        self.assertEqual(out, [])


@unittest.skipIf(alias is None, "opensearchpy not installed")
class TestRunPerIndexMergedSearch(unittest.TestCase):
    def test_partial_index_failure_still_returns_hits(self) -> None:
        client = MagicMock()
        client.indices.get_mapping.side_effect = [
            {"idx_ok": {"mappings": {"properties": {"chunk_embedding_m": {"type": "knn_vector", "dimension": 2}}}}},
            {"idx_bad": {"mappings": {"properties": {"chunk_embedding_m": {"type": "knn_vector", "dimension": 2}}}}},
        ]

        def search_effect(*args, **kwargs):
            idx = kwargs.get("index")
            if idx == "idx_ok":
                return {
                    "hits": {
                        "hits": [
                            {
                                "_score": 1.0,
                                "_source": {"text": "hello", "filename": "a.txt", "page": 1},
                            }
                        ]
                    }
                }
            raise RuntimeError("simulated failure")

        client.search.side_effect = search_effect

        results, failures = alias.run_per_index_merged_search(
            client=client,
            query_text="hello",
            filter_clauses=[],
            limit=5,
            score_threshold=0,
            query_embeddings={"m": [0.1, 0.2]},
            physical_indices=["idx_ok", "idx_bad"],
            get_embedding_field_name=_gef,
            use_num_candidates=False,
            num_candidates=0,
            log_fn=None,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["page_content"], "hello")
        self.assertTrue(failures)
