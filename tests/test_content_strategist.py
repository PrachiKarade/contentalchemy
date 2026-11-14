from unittest.mock import patch

import pytest

from src.agents.content_strategist import content_strategist_node


@patch("src.agents.content_strategist.get_conversation")
def test_missing_research_data_propagates_error(mock_get_conversation):
    mock_get_conversation.return_value = {
        "target_audience": "Developers",
        "tone": "Professional",
        "objective": "Education",
    }

    state = {
        "user_id": "test-user",
        "conversation_id": "test-conversation",
        "topic": "Agentic AI",
        "research_data": {},
    }

    with pytest.raises(ValueError, match="Research data is missing"):
        content_strategist_node(state)


@patch("src.agents.content_strategist.text_provider_manager.generate_text")
@patch("src.agents.content_strategist.get_conversation")
def test_llm_failure_propagates(
    mock_get_conversation,
    mock_generate_text,
):
    mock_get_conversation.return_value = {
        "target_audience": "Developers",
        "tone": "Professional",
        "objective": "Education",
    }

    mock_generate_text.side_effect = RuntimeError("Simulated LLM failure")

    state = {
        "user_id": "test-user",
        "conversation_id": "test-conversation",
        "topic": "Agentic AI",
        "research_data": {
            "topic": "Agentic AI",
            "research_summary": "Research summary for testing",
            "findings": [],
            "sources": [],
        },
    }

    with pytest.raises(RuntimeError, match="Simulated LLM failure"):
        content_strategist_node(state)

    mock_generate_text.assert_called_once()