"""Unit tests for file_utils (safe storage filename, etc.)."""

import re

import pytest

from src.utils.file_utils import make_safe_storage_filename

# Only these chars allowed in safe storage filename
SAFE_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")


def _is_ascii_only(s: str) -> bool:
    return all(ord(c) < 128 for c in s)


def test_make_safe_storage_filename_russian_pdf():
    """Russian PDF filename must become ASCII-only; ingestion must not fail on non-ASCII path."""
    original = "Заявка 20.08.24 ИП Ломовцев_ИП Абдуллина -Екатеринбург_Челябинск.pdf"
    result = make_safe_storage_filename(original)
    assert _is_ascii_only(result), "Safe storage filename must be ASCII-only"
    assert SAFE_PATTERN.match(result), f"Only a-z A-Z 0-9 . _ - allowed, got: {result!r}"
    assert result.endswith(".pdf")
    assert " " not in result, "Spaces must be replaced with _"


def test_make_safe_storage_filename_mixed_spaces_underscores():
    """Mixed filename with spaces and underscores -> ASCII, spaces to _."""
    original = "file name_2024 report.PDF"
    result = make_safe_storage_filename(original)
    assert _is_ascii_only(result)
    assert SAFE_PATTERN.match(result)
    assert " " not in result
    assert result.endswith(".PDF") or result.endswith(".pdf")


def test_make_safe_storage_filename_ascii_only_unchanged():
    """Already safe ASCII name is normalized (spaces -> _) but otherwise preserved."""
    original = "Report 2024_final.pdf"
    result = make_safe_storage_filename(original)
    assert _is_ascii_only(result)
    assert SAFE_PATTERN.match(result)
    assert " " not in result
    assert "Report_2024_final.pdf" == result


def test_make_safe_storage_filename_empty_fallback():
    """Empty or whitespace-only filename yields file_<uuid>.ext."""
    result = make_safe_storage_filename("")
    assert _is_ascii_only(result)
    assert SAFE_PATTERN.match(result)
    assert result.startswith("file_") and result.endswith(".bin")
    result2 = make_safe_storage_filename("   ")
    assert result2.startswith("file_") and result2.endswith(".bin")
