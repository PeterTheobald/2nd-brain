"""
Tests for pipeline/analyze.py.

The Claude API is mocked — these tests verify prompt construction and
JSON parsing without making real API calls or incurring costs.
"""

import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

SAMPLE_RESPONSE = {
    "transcript": "called Alex about the house",
    "actions": [
        {
            "type": "contact_journal",
            "file": "ppl/Alex Carter.md",
            "content": "2026-06-01 called re: house",
            "update_last_contact": "2026-06-01",
            "new_contact": False,
        },
        {
            "type": "journal_entry",
            "file": "Journal 2026.md",
            "date": "2026-06-01",
            "content": "called [[Alex Carter]] re: house",
        },
    ],
}


def _make_mock_client_from_text(text):
    """Build a mock Anthropic client whose single text block is `text`."""
    mock_content = MagicMock()
    mock_content.text = text
    mock_message = MagicMock()
    mock_message.content = [mock_content]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    return mock_client


def _make_mock_client(response_dict):
    """Build a mock Anthropic client that returns response_dict as JSON."""
    return _make_mock_client_from_text(json.dumps(response_dict))


class TestAnalyze:

    def test_returns_parsed_actions(self):
        import pipeline.analyze as analyze_module
        mock_client = _make_mock_client(SAMPLE_RESPONSE)
        with patch.object(analyze_module, "client", mock_client):
            result = analyze_module.analyze(
                "called Alex about the house", {"Alex Carter": "Alex Carter.md"}
            )
        assert result["transcript"] == "called Alex about the house"
        assert len(result["actions"]) == 2

    def test_system_prompt_includes_today(self):
        import pipeline.analyze as analyze_module
        mock_client = _make_mock_client(SAMPLE_RESPONSE)
        with patch.object(analyze_module, "client", mock_client):
            analyze_module.analyze("test", {})
        call_kwargs = mock_client.messages.create.call_args
        system_prompt = call_kwargs.kwargs["system"]
        assert date.today().isoformat() in system_prompt

    def test_system_prompt_includes_contact_index(self):
        import pipeline.analyze as analyze_module
        mock_client = _make_mock_client(SAMPLE_RESPONSE)
        contact_index = {"Alex Carter": "Alex Carter.md", "alex": "Alex Carter.md"}
        with patch.object(analyze_module, "client", mock_client):
            analyze_module.analyze("test", contact_index)
        call_kwargs = mock_client.messages.create.call_args
        system_prompt = call_kwargs.kwargs["system"]
        assert "Alex Carter" in system_prompt

    def test_transcript_sent_as_user_message(self):
        import pipeline.analyze as analyze_module
        mock_client = _make_mock_client(SAMPLE_RESPONSE)
        with patch.object(analyze_module, "client", mock_client):
            analyze_module.analyze("my specific transcript", {})
        call_kwargs = mock_client.messages.create.call_args
        messages = call_kwargs.kwargs["messages"]
        assert messages[0]["content"] == "my specific transcript"

    def test_raises_on_invalid_json_response(self):
        import pipeline.analyze as analyze_module
        mock_client = _make_mock_client_from_text("this is not json")
        with patch.object(analyze_module, "client", mock_client):
            with pytest.raises(json.JSONDecodeError):
                analyze_module.analyze("test", {})

    def test_strips_markdown_json_fence(self):
        import pipeline.analyze as analyze_module
        fenced = "```json\n" + json.dumps(SAMPLE_RESPONSE) + "\n```"
        mock_client = _make_mock_client_from_text(fenced)
        with patch.object(analyze_module, "client", mock_client):
            result = analyze_module.analyze("called Alex", {})
        assert len(result["actions"]) == 2

    def test_extracts_json_embedded_in_prose(self):
        import pipeline.analyze as analyze_module
        prose = "Sure! Here is the filing:\n" + json.dumps(SAMPLE_RESPONSE) + "\nHope that helps."
        mock_client = _make_mock_client_from_text(prose)
        with patch.object(analyze_module, "client", mock_client):
            result = analyze_module.analyze("called Alex", {})
        assert result["transcript"] == "called Alex about the house"

    def test_defaults_transcript_to_input_when_absent(self):
        import pipeline.analyze as analyze_module
        mock_client = _make_mock_client({"actions": []})
        with patch.object(analyze_module, "client", mock_client):
            result = analyze_module.analyze("my raw input", {})
        assert result["transcript"] == "my raw input"

    def test_raises_when_actions_missing(self):
        import pipeline.analyze as analyze_module
        mock_client = _make_mock_client({"transcript": "x"})
        with patch.object(analyze_module, "client", mock_client):
            with pytest.raises(ValueError):
                analyze_module.analyze("test", {})

    def test_raises_when_no_text_block(self):
        import pipeline.analyze as analyze_module
        non_text = MagicMock(spec=[])  # no .text attribute
        mock_message = MagicMock()
        mock_message.content = [non_text]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_message
        with patch.object(analyze_module, "client", mock_client):
            with pytest.raises(ValueError):
                analyze_module.analyze("test", {})
