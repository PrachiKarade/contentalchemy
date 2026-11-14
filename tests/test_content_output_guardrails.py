
import pytest

from src.guardrails.content_output_guardrails import (
    validate_content_text,
    validate_linkedin_output,
    validate_blog_output,
)


def test_valid_content_passes():
    content = "This is a valid article about AI content marketing."
    assert validate_content_text(content) == content


@pytest.mark.parametrize(
    "content",
    [
        "<script>alert('x')</script>",
        '<iframe src="https://example.com"></iframe>',
        '<img src="x" onerror="alert(1)">',
        "[Insert your company name here]",
    ],
)
def test_unsafe_or_unfinished_content_is_rejected(content):
    with pytest.raises(ValueError):
        validate_content_text(content)


def test_empty_content_is_rejected():
    with pytest.raises(ValueError, match="too short"):
        validate_content_text("")


def test_non_string_content_is_rejected():
    with pytest.raises(TypeError):
        validate_content_text(None)


def test_content_over_maximum_length_is_rejected():
    with pytest.raises(ValueError, match="maximum length"):
        validate_content_text("A" * 101, max_length=100)


def test_valid_linkedin_output_passes():
    data = {
        "hook": "AI is changing content marketing.",
        "post_body": "Here are three ways teams can use AI responsibly.",
        "hashtags": ["#AI", "#ContentMarketing"],
        "call_to_action": "What has worked for your team?",
    }

    result = validate_linkedin_output(data)
    assert result == data


def test_invalid_linkedin_hashtag_is_rejected():
    data = {
        "hook": "AI is changing content marketing.",
        "post_body": "Here are three ways teams can use AI responsibly.",
        "hashtags": ["AI Marketing"],
        "call_to_action": "Share your experience with us.",
    }

    with pytest.raises(ValueError, match="Invalid LinkedIn hashtag"):
        validate_linkedin_output(data)


def test_linkedin_missing_field_is_rejected():
    data = {
        "hook": "AI is changing content marketing.",
        "post_body": "A useful post about AI.",
        "hashtags": ["#AI"],
    }

    with pytest.raises(ValueError, match="exactly"):
        validate_linkedin_output(data)


def test_valid_blog_output_passes():
    data = {
        "seo_title": "AI in Content Marketing",
        "meta_description": "An overview of AI in content marketing.",
        "url_slug": "ai-content-marketing",
        "primary_keyword": "AI content marketing",
        "secondary_keywords": ["AI tools"],
        "search_intent": "informational",
        "article_outline": [],
        "faqs": [],
        "call_to_action": "Explore how AI can support your workflow.",
        "sources": [],
        "blog_article": (
            "# AI in Content Marketing\n\n"
            "AI tools can support research and content workflows."
        ),
    }

    result = validate_blog_output(data)
    assert result["blog_article"] == data["blog_article"]


def test_blog_missing_field_is_rejected():
    with pytest.raises(ValueError, match="missing fields"):
        validate_blog_output({"blog_article": "A valid article body."})
