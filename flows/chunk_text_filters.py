"""
Post-retrieval filters for chunk text before passing context to the LLM.

Does not change OpenSearch queries — only filters already-returned hits.
"""

from __future__ import annotations

import re
from typing import Any

# Words of 3+ letters: Latin or Cyrillic (explicit, predictable)
_WORD_3_PLUS_CYR_LAT = re.compile(r"(?:[a-zA-Z]{3,}|[а-яёА-ЯЁ]{3,})")


def is_garbage_table_separator_chunk(text: str | None) -> bool:
    """
    True only for lines that look like pure table borders (pipes/dashes/colons),
    with no digits and no Cyrillic/Latin words of length >= 3.

    Conservative: when in doubt, returns False (keep the chunk).
    """
    if text is None:
        return False
    s = text.strip()
    if len(s) < 6:
        return False

    # Keep: any digit
    if any(ch.isdigit() for ch in s):
        return False

    # Keep: word of 3+ letters (Cyrillic or Latin)
    if _WORD_3_PLUS_CYR_LAT.search(s):
        return False

    # Keep: other scripts / mixed Unicode letters (safety net)
    if re.search(r"[^\W\d_]{3,}", s, re.UNICODE):
        return False

    # Separator lines should contain a pipe and almost no alphanumeric content
    if "|" not in s:
        return False

    n = len(s)
    alnum = sum(1 for c in s if c.isalnum())
    if alnum / n > 0.06:
        return False

    # After stripping decorative chars, nothing (or almost nothing) should remain
    rest = re.sub(r"[\s|:\-–—=_+.]", "", s)
    if len(rest) > 2:
        return False

    return True


def filter_search_results_for_llm(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop obvious table-separator chunks; preserve order. If nothing left, keep first 3 hits."""
    if not results:
        return []

    out: list[dict[str, Any]] = []
    for r in results:
        pc = r.get("page_content")
        text = pc if isinstance(pc, str) else ""
        if not is_garbage_table_separator_chunk(text):
            out.append(r)

    if not out:
        return list(results[:3])
    return out
