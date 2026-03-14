"""Unit tests for duplicate check: API uses safe storage filename for OpenSearch query."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.utils.file_utils import make_safe_storage_filename


@pytest.mark.asyncio
async def test_check_filename_exists_uses_safe_name_for_cyrillic():
    """When checking if filename exists, OpenSearch query must use safe (ASCII) name so duplicate detection works."""
    cyrillic_filename = "Заявка 20.08.24 ИП Ломовцев.pdf"
    expected_safe = make_safe_storage_filename(cyrillic_filename)
    assert expected_safe != cyrillic_filename
    assert expected_safe.isascii()

    captured_search_filename = None

    def capture_build_filename_search_body(filename, size=1, source=False):
        nonlocal captured_search_filename
        captured_search_filename = filename
        return {"query": {"term": {"filename": filename}}, "size": size, "_source": source}

    mock_opensearch = MagicMock()
    mock_opensearch.search = AsyncMock(return_value={"hits": {"hits": []}})
    mock_session_manager = MagicMock()
    mock_session_manager.get_user_opensearch_client = MagicMock(return_value=mock_opensearch)
    mock_user = MagicMock()
    mock_user.user_id = "test-user"
    mock_user.jwt_token = "fake-jwt"

    with patch("utils.opensearch_queries.build_filename_search_body", side_effect=capture_build_filename_search_body):
        from api.documents import check_filename_exists

        await check_filename_exists(
            cyrillic_filename,
            session_manager=mock_session_manager,
            user=mock_user,
        )

    assert captured_search_filename == expected_safe, (
        f"Duplicate check must query by safe name; got {captured_search_filename!r}, expected {expected_safe!r}"
    )
