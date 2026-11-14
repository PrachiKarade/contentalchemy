
import json
import pytest
from unittest.mock import patch

from pydantic import ValidationError

from src.agents.query_handler import analyze_query


def valid_llm_response():
    return {
        "intent": "blog",
        "topic": "Artificial Intelligence",
        "target_audience": "Technology professionals",
        "tone": "Professional",
        "keywords": ["AI", "Machine Learning"],
        "objective": "Educate readers about AI.",
        "requested_agents": ["blog"],
    }


def test_analyze_query_valid_request():
    response = valid_llm_response()

    with patch(
        "src.agents.query_handler.text_provider_manager.generate_text",
        return_value=json.dumps(response),
    ) as mock_generate:

        result = analyze_query(
            "Create an SEO blog about Artificial Intelligence."
        )

    assert result["intent"] == "blog"
    assert result["topic"] == "Artificial Intelligence"
    assert result["keywords"] == ["AI", "Machine Learning"]
    assert result["requested_agents"] == ["blog"]

    mock_generate.assert_called_once()


def test_analyze_query_rejects_empty_request_before_llm():
    with patch(
        "src.agents.query_handler.text_provider_manager.generate_text"
    ) as mock_generate:

        with pytest.raises(ValidationError):
            analyze_query("   ")

        mock_generate.assert_not_called()


def test_analyze_query_rejects_short_request_before_llm():
    with patch(
        "src.agents.query_handler.text_provider_manager.generate_text"
    ) as mock_generate:

        with pytest.raises(ValidationError):
            analyze_query("AI")

        mock_generate.assert_not_called()


def test_analyze_query_rejects_long_request_before_llm():
    with patch(
        "src.agents.query_handler.text_provider_manager.generate_text"
    ) as mock_generate:

        with pytest.raises(ValidationError):
            analyze_query("A" * 5001)

        mock_generate.assert_not_called()


def test_analyze_query_rejects_invalid_llm_json():
    with patch(
        "src.agents.query_handler.text_provider_manager.generate_text",
        return_value="This is not valid JSON",
    ):

        with pytest.raises(ValueError, match="invalid JSON"):
            analyze_query("Create a blog about AI.")


def test_analyze_query_rejects_unsupported_llm_intent():
    response = valid_llm_response()
    response["intent"] = "podcast"

    with patch(
        "src.agents.query_handler.text_provider_manager.generate_text",
        return_value=json.dumps(response),
    ):

        with pytest.raises(ValidationError):
            analyze_query("Create a blog about AI.")


def test_analyze_query_rejects_missing_llm_field():
    response = valid_llm_response()
    del response["topic"]

    with patch(
        "src.agents.query_handler.text_provider_manager.generate_text",
        return_value=json.dumps(response),
    ):

        with pytest.raises(ValidationError):
            analyze_query("Create a blog about AI.")


def test_analyze_query_multi_deliverables():
    response = valid_llm_response()
    response["intent"] = "multi"
    response["requested_agents"] = [
        "research",
        "blog",
        "linkedin",
    ]

    with patch(
        "src.agents.query_handler.text_provider_manager.generate_text",
        return_value=json.dumps(response),
    ):
        result = analyze_query(
            "Research AI trends, write an SEO blog, and create a LinkedIn post."
        )

    assert result["intent"] == "multi"
    assert result["requested_agents"] == [
        "research",
        "blog",
        "linkedin",
    ]


def test_analyze_query_single_deliverable():
    response = valid_llm_response()

    with patch(
        "src.agents.query_handler.text_provider_manager.generate_text",
        return_value=json.dumps(response),
    ):
        result = analyze_query("Write an SEO blog about AI.")

    assert result["intent"] == "blog"
    assert result["requested_agents"] == ["blog"]


def test_analyze_query_rejects_invalid_requested_agent():
    response = valid_llm_response()
    response["requested_agents"] = ["blog", "podcast"]

    with patch(
        "src.agents.query_handler.text_provider_manager.generate_text",
        return_value=json.dumps(response),
    ):
        with pytest.raises(ValidationError):
            analyze_query("Write a blog about AI.")


def test_analyze_query_rejects_missing_requested_agents():
    response = valid_llm_response()
    del response["requested_agents"]

    with patch(
        "src.agents.query_handler.text_provider_manager.generate_text",
        return_value=json.dumps(response),
    ):
        with pytest.raises(ValidationError):
            analyze_query("Write a blog about AI.")


def test_analyze_query_rejects_duplicate_requested_agents():
    response = valid_llm_response()
    response["requested_agents"] = ["blog", "blog"]

    with patch(
        "src.agents.query_handler.text_provider_manager.generate_text",
        return_value=json.dumps(response),
    ):
        with pytest.raises(ValidationError):
            analyze_query("Write a blog about AI.")
