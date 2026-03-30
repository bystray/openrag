"""Tests for flows/chunk_text_filters.py (LLM context post-filter)."""

import sys
from pathlib import Path

import pytest

_FLOWS = Path(__file__).resolve().parents[2] / "flows"
if str(_FLOWS) not in sys.path:
    sys.path.insert(0, str(_FLOWS))

from chunk_text_filters import (  # noqa: E402
    filter_search_results_for_llm,
    is_garbage_table_separator_chunk,
)


@pytest.mark.parametrize(
    "text",
    [
        "|-----|-----|-----|",
        "| --- | --- | --- | --- |",
        "|:----|:----|:----|",
        "|   |   |   |   |   |   |",
    ],
)
def test_separator_lines_dropped(text: str):
    assert is_garbage_table_separator_chunk(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "",
        "ab",
        "|",
        "||",
        "КБЖУ морковь сырой",
        "морковь 35 1.3 0.1 6.2",
        "Vitamin A 12 mg",
        "Пер 100 г  Белки 1.2  Жиры 0.1  Углеводы 6.0",
        "| Название | Ккал | Б | Ж | У |",
    ],
)
def test_useful_content_kept(text: str):
    assert is_garbage_table_separator_chunk(text) is False


def test_filter_search_results_removes_only_garbage():
    rows = [
        {"page_content": "|-----|-----|", "metadata": {"filename": "a.pdf"}, "score": 1.0},
        {"page_content": "морковь 41 0.9 1.3 7.2", "metadata": {"filename": "a.pdf"}, "score": 0.9},
    ]
    out = filter_search_results_for_llm(rows)
    assert len(out) == 1
    assert "морковь" in out[0]["page_content"]


def test_fallback_when_filter_removes_everything():
    rows = [
        {"page_content": "|-----|-----|", "metadata": {"a": 1}, "score": 1.0},
        {"page_content": "| --- | --- |", "metadata": {"a": 2}, "score": 0.9},
        {"page_content": "|:----|", "metadata": {"a": 3}, "score": 0.8},
    ]
    out = filter_search_results_for_llm(rows)
    assert len(out) == 3
    assert out == rows
