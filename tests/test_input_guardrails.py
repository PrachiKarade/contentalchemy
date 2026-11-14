
import pytest
from pydantic import ValidationError

from src.guardrails.input_guardrails import (
    UserRequestInput,
    QueryAnalysisOutput,
)


# ---------------------------------------------------------
# User Request Input Tests
# ---------------------------------------------------------

def test_valid_user_request():
    result = UserRequestInput(
        user_request="Create an SEO blog about artificial intelligence."
    )

    assert result.user_request == (
        "Create an SEO blog about artificial intelligence."
    )


def test_user_request_is_trimmed():
    result = UserRequestInput(
        user_request="   Create a LinkedIn post about AI.   "
    )

    assert result.user_request == "Create a LinkedIn post about AI."


def test_empty_user_request():
    with pytest.raises(ValidationError):
        UserRequestInput(user_request="")


def test_whitespace_only_user_request():
    with pytest.raises(ValidationError):
        UserRequestInput(user_request="   ")


def test_user_request_below_minimum_length():
    with pytest.raises(ValidationError):
        UserRequestInput(user_request="AI")


def test_user_request_exceeds_maximum_length():
    with pytest.raises(ValidationError):
        UserRequestInput(user_request="A" * 5001)


def test_user_request_rejects_extra_fields():
    with pytest.raises(ValidationError):
        UserRequestInput(
            user_request="Create an SEO blog about AI.",
            unexpected_field="Not allowed",
        )


# ---------------------------------------------------------
# Query Analysis Output Tests
# ---------------------------------------------------------

def valid_query_analysis():
    return {
        "intent": "blog",
        "topic": "Artificial Intelligence",
        "target_audience": "Technology professionals",
        "tone": "Professional",
        "keywords": ["AI", "Machine Learning"],
        "objective": "Educate readers about AI.",
        "requested_agents": ["blog"],
    }


def test_valid_query_analysis():
    result = QueryAnalysisOutput.model_validate(
        valid_query_analysis()
    )

    assert result.intent == "blog"
    assert result.topic == "Artificial Intelligence"
    assert result.keywords == ["AI", "Machine Learning"]


def test_query_analysis_rejects_unsupported_intent():
    data = valid_query_analysis()
    data["intent"] = "podcast"

    with pytest.raises(ValidationError):
        QueryAnalysisOutput.model_validate(data)


def test_query_analysis_requires_topic():
    data = valid_query_analysis()
    data["topic"] = "A"

    with pytest.raises(ValidationError):
        QueryAnalysisOutput.model_validate(data)


def test_query_analysis_rejects_too_many_keywords():
    data = valid_query_analysis()
    data["keywords"] = [f"keyword-{i}" for i in range(21)]

    with pytest.raises(ValidationError):
        QueryAnalysisOutput.model_validate(data)


def test_query_analysis_rejects_extra_fields():
    data = valid_query_analysis()
    data["extra_field"] = "Not allowed"

    with pytest.raises(ValidationError):
        QueryAnalysisOutput.model_validate(data)


def test_query_analysis_removes_duplicate_keywords():
    data = valid_query_analysis()
    data["keywords"] = ["AI", "Machine Learning", "AI"]

    result = QueryAnalysisOutput.model_validate(data)

    assert result.keywords == ["AI", "Machine Learning"]


def test_query_analysis_strips_text_fields():
    data = valid_query_analysis()
    data["topic"] = "  Artificial Intelligence  "

    result = QueryAnalysisOutput.model_validate(data)

    assert result.topic == "Artificial Intelligence"
