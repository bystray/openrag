"""Smoke: nudges path must never invoke Langflow with an empty user prompt."""

from services.chat_service import NUDGES_DEFAULT_USER_PROMPT


def test_nudges_default_prompt_is_substantive():
    assert len(NUDGES_DEFAULT_USER_PROMPT.strip()) >= 40
