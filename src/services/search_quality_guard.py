"""Pure helpers for optional /api/search quality guard (PR-5)."""

from __future__ import annotations

from typing import Any


def max_chunk_score(chunks: list[dict[str, Any]]) -> float | None:
    """Best hybrid score from result chunks (OpenSearch _score per hit)."""
    scores: list[float] = []
    for c in chunks:
        s = c.get("score")
        if isinstance(s, (int, float)):
            scores.append(float(s))
    if not scores:
        return None
    return max(scores)


def is_noise_like_query(q: str) -> bool:
    """Heuristic: long random-ish alphanumeric / digit-heavy strings."""
    if len(q) < 8:
        return False
    digits = sum(1 for c in q if c.isdigit())
    alnum = sum(1 for c in q if c.isalnum())
    if alnum == 0:
        return False
    if digits / len(q) >= 0.35:
        return True
    tokens = q.split()
    if len(tokens) == 1 and len(q) >= 10 and digits >= 3:
        return True
    return False


def query_requires_strict_lexical_evidence(query: str) -> bool:
    """Single-token queries or noise-like strings need strong lexical signal."""
    q = (query or "").strip()
    if not q:
        return False
    if len(q.split()) == 1:
        return True
    return is_noise_like_query(q)


def _apply_search_quality_guard(
    query: str,
    chunks: list[dict[str, Any]],
    top_score: float | None,
    lex_max_score: float | None,
    lex_threshold: float,
    hybrid_threshold: float,
    guard_enabled: bool,
    is_wildcard: bool,
) -> tuple[bool, list[dict[str, Any]]]:
    """
    Decide whether to keep hybrid search results.

    Returns (keep, chunks). When keep is False, chunks is [].

    lex_max_score None: lexical probe failed — fail-open (keep results).
    """
    if not guard_enabled or is_wildcard:
        return True, chunks

    if not chunks:
        return True, chunks

    if lex_max_score is None:
        return True, chunks

    lex_ok = lex_max_score >= lex_threshold

    if query_requires_strict_lexical_evidence(query):
        if lex_ok:
            return True, chunks
        return False, []

    top = top_score if top_score is not None else 0.0
    hybrid_ok = top >= hybrid_threshold
    if lex_ok or hybrid_ok:
        return True, chunks
    return False, []
