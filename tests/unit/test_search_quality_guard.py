"""Unit tests for PR-5 search quality guard (pure logic, no OpenSearch)."""

import sys
import unittest
from pathlib import Path

# tests/unit -> project root -> src on PYTHONPATH (same pattern as other unit tests)
_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from services.search_quality_guard import (
    _apply_search_quality_guard,
    is_noise_like_query,
    max_chunk_score,
    query_requires_strict_lexical_evidence,
)


class TestSearchQualityGuard(unittest.TestCase):
    def test_guard_disabled_passes_through(self):
        chunks = [{"score": 0.01, "text": "x"}]
        keep, out = _apply_search_quality_guard(
            "anything",
            chunks,
            top_score=0.01,
            lex_max_score=0.0,
            lex_threshold=1.0,
            hybrid_threshold=0.99,
            guard_enabled=False,
            is_wildcard=False,
        )
        self.assertTrue(keep)
        self.assertEqual(out, chunks)

    def test_wildcard_skipped(self):
        chunks = [{"score": 0.01}]
        keep, out = _apply_search_quality_guard(
            "*",
            chunks,
            top_score=0.01,
            lex_max_score=0.0,
            lex_threshold=1.0,
            hybrid_threshold=0.0,
            guard_enabled=True,
            is_wildcard=True,
        )
        self.assertTrue(keep)
        self.assertEqual(out, chunks)

    def test_probe_error_fail_open(self):
        chunks = [{"score": 0.2}]
        keep, out = _apply_search_quality_guard(
            "normal query text here",
            chunks,
            top_score=0.2,
            lex_max_score=None,
            lex_threshold=1.0,
            hybrid_threshold=0.99,
            guard_enabled=True,
            is_wildcard=False,
        )
        self.assertTrue(keep)
        self.assertEqual(out, chunks)

    def test_normal_multi_word_lex_or_hybrid_passes(self):
        chunks = [{"score": 2.0}]
        keep, out = _apply_search_quality_guard(
            "open search relevance",
            chunks,
            top_score=2.0,
            lex_max_score=0.0,
            lex_threshold=1.0,
            hybrid_threshold=0.5,
            guard_enabled=True,
            is_wildcard=False,
        )
        self.assertTrue(keep)
        self.assertEqual(len(out), 1)

    def test_normal_multi_word_blocks_when_neither_lex_nor_hybrid(self):
        chunks = [{"score": 0.1}]
        keep, out = _apply_search_quality_guard(
            "open search relevance",
            chunks,
            top_score=0.1,
            lex_max_score=0.05,
            lex_threshold=1.0,
            hybrid_threshold=0.5,
            guard_enabled=True,
            is_wildcard=False,
        )
        self.assertFalse(keep)
        self.assertEqual(out, [])

    def test_garbage_single_token_requires_lexical(self):
        chunks = [{"score": 5.0}]
        keep, out = _apply_search_quality_guard(
            "qwerty123456",
            chunks,
            top_score=5.0,
            lex_max_score=0.2,
            lex_threshold=1.0,
            hybrid_threshold=0.1,
            guard_enabled=True,
            is_wildcard=False,
        )
        self.assertFalse(keep)
        self.assertEqual(out, [])

    def test_single_token_with_lexical_evidence_passes(self):
        chunks = [{"score": 0.5}]
        keep, out = _apply_search_quality_guard(
            "python",
            chunks,
            top_score=0.5,
            lex_max_score=3.0,
            lex_threshold=1.0,
            hybrid_threshold=0.99,
            guard_enabled=True,
            is_wildcard=False,
        )
        self.assertTrue(keep)

    def test_empty_chunks_unchanged(self):
        keep, out = _apply_search_quality_guard(
            "x",
            [],
            top_score=None,
            lex_max_score=0.0,
            lex_threshold=1.0,
            hybrid_threshold=0.5,
            guard_enabled=True,
            is_wildcard=False,
        )
        self.assertTrue(keep)
        self.assertEqual(out, [])

    def test_max_chunk_score(self):
        self.assertIsNone(max_chunk_score([]))
        self.assertEqual(max_chunk_score([{"score": 1}, {"score": 3.5}]), 3.5)

    def test_noise_like(self):
        self.assertTrue(is_noise_like_query("qwerty123456"))
        self.assertFalse(is_noise_like_query("short"))

    def test_strict_lexical_single_token(self):
        self.assertTrue(query_requires_strict_lexical_evidence("word"))
        self.assertFalse(query_requires_strict_lexical_evidence("two words"))


if __name__ == "__main__":
    unittest.main()
