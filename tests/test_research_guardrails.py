
import pytest
from pydantic import ValidationError

from src.guardrails.research_guardrails import (
    ResearchOutput,
    validate_research_output,
)


@pytest.fixture
def valid_research_data():
    return {
        "topic": "Generative AI in Content Marketing",
        "findings": [
            {
                "claim": "AI tools can support content creation.",
                "explanation": (
                    "The search results describe AI-assisted content "
                    "creation and workflow improvements."
                ),
                "source_urls": [
                    "https://example.com/ai-content"
                ],
            }
        ],
        "research_summary": (
            "Generative AI is being used to support content marketing "
            "workflows and content production."
        ),
        "sources": [
            {
                "title": "AI in Content Marketing",
                "url": "https://example.com/ai-content",
                "snippet": "AI tools are used in content workflows.",
            }
        ],
    }


def test_valid_research_output(valid_research_data):
    result = validate_research_output(valid_research_data)

    assert result["topic"] == "Generative AI in Content Marketing"
    assert len(result["findings"]) == 1
    assert len(result["sources"]) == 1


def test_missing_required_field(valid_research_data):
    valid_research_data.pop("research_summary")

    with pytest.raises(ValidationError):
        validate_research_output(valid_research_data)


def test_invalid_finding_structure(valid_research_data):
    valid_research_data["findings"][0].pop("claim")

    with pytest.raises(ValidationError):
        validate_research_output(valid_research_data)


def test_empty_findings(valid_research_data):
    valid_research_data["findings"] = []

    with pytest.raises(ValidationError):
        validate_research_output(valid_research_data)


def test_invalid_finding_source_url(valid_research_data):
    valid_research_data["findings"][0]["source_urls"] = [
        "not-a-valid-url"
    ]

    with pytest.raises(ValidationError):
        validate_research_output(valid_research_data)


def test_invalid_source_url(valid_research_data):
    valid_research_data["sources"][0]["url"] = "invalid-url"

    with pytest.raises(ValidationError):
        validate_research_output(valid_research_data)


def test_empty_research_summary(valid_research_data):
    valid_research_data["research_summary"] = ""

    with pytest.raises(ValidationError):
        validate_research_output(valid_research_data)


def test_unexpected_field(valid_research_data):
    valid_research_data["unexpected_field"] = "unexpected data"

    with pytest.raises(ValidationError):
        validate_research_output(valid_research_data)


def test_invalid_source_structure(valid_research_data):
    valid_research_data["sources"][0].pop("title")

    with pytest.raises(ValidationError):
        validate_research_output(valid_research_data)


def test_invalid_top_level_data():
    with pytest.raises(ValidationError):
        validate_research_output(["not", "a", "dictionary"])


def test_whitespace_only_topic(valid_research_data):
    valid_research_data["topic"] = "   "

    with pytest.raises(ValidationError):
        validate_research_output(valid_research_data)
