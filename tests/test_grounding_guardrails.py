
import pytest

from src.guardrails.grounding_guardrails import (
    extract_search_result_urls,
    normalize_url,
    validate_research_grounding,
)


@pytest.fixture
def search_results():
    return [
        {
            "title": "AI in Content Marketing",
            "link": "https://example.com/ai-content",
            "snippet": "AI supports content workflows.",
        },
        {
            "title": "Marketing Trends",
            "url": "https://marketing.example.com/trends/",
            "snippet": "Recent marketing trends.",
        },
    ]


@pytest.fixture
def research_data():
    return {
        "topic": "AI in Content Marketing",
        "findings": [
            {
                "claim": "AI tools support content creation.",
                "explanation": "The source discusses AI-assisted workflows.",
                "source_urls": [
                    "https://example.com/ai-content"
                ],
            }
        ],
        "research_summary": (
            "AI tools are being used in content marketing workflows."
        ),
        "sources": [
            {
                "title": "AI in Content Marketing",
                "url": "https://example.com/ai-content",
                "snippet": "AI supports content workflows.",
            }
        ],
    }


def test_valid_research_urls_pass(research_data, search_results):
    result = validate_research_grounding(research_data, search_results)

    assert result == research_data


def test_unknown_finding_url_is_rejected(research_data, search_results):
    research_data["findings"][0]["source_urls"] = [
        "https://unknown.example.com/article"
    ]

    with pytest.raises(ValueError, match="not present"):
        validate_research_grounding(research_data, search_results)


def test_unknown_top_level_source_is_rejected(
    research_data, search_results
):
    research_data["sources"][0]["url"] = (
        "https://unknown.example.com/article"
    )

    with pytest.raises(ValueError, match="not present"):
        validate_research_grounding(research_data, search_results)


def test_trailing_slash_is_normalized():
    assert normalize_url("https://example.com/article/") == (
        normalize_url("https://example.com/article")
    )


def test_host_case_is_normalized():
    assert normalize_url("HTTPS://EXAMPLE.COM/article") == (
        normalize_url("https://example.com/article")
    )


def test_fragment_is_ignored():
    assert normalize_url("https://example.com/article#section") == (
        normalize_url("https://example.com/article")
    )


def test_query_parameters_are_preserved():
    assert normalize_url("https://example.com/article?id=1") != (
        normalize_url("https://example.com/article?id=2")
    )


def test_extract_urls_from_search_results(search_results):
    urls = extract_search_result_urls(search_results)

    assert "https://example.com/ai-content" in urls
    assert "https://marketing.example.com/trends" in urls


def test_finding_without_source_urls_is_rejected(
    research_data, search_results
):
    research_data["findings"][0]["source_urls"] = []

    with pytest.raises(ValueError, match="must contain source URLs"):
        validate_research_grounding(research_data, search_results)


def test_invalid_url_is_rejected(research_data, search_results):
    research_data["findings"][0]["source_urls"] = ["not-a-url"]

    with pytest.raises(ValueError, match="Invalid HTTP/HTTPS URL"):
        validate_research_grounding(research_data, search_results)


def test_empty_search_result_urls_are_rejected(research_data):
    with pytest.raises(ValueError, match="No valid source URLs"):
        validate_research_grounding(research_data, [])


def test_non_dictionary_research_data_is_rejected(search_results):
    with pytest.raises(TypeError, match="dictionary"):
        validate_research_grounding([], search_results)
