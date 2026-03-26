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
    """Heuristic: any digits, or long unspaced strings (likely garbage / opaque tokens)."""
    s = (q or "").strip()
    if not s:
        return False
    if any(c.isdigit() for c in s):
        return True
    if len(s) > 6 and " " not in s:
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
    strict = query_requires_strict_lexical_evidence(query)
    top = top_score if top_score is not None else 0.0
    hybrid_ok = top >= hybrid_threshold

    if strict:
        keep = lex_ok
        if lex_ok:
            return True, chunks
        return False, []

    keep = lex_ok or hybrid_ok
    if lex_ok or hybrid_ok:
        return True, chunks
    return False, []
