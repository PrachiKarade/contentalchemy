
import re


# These patterns detect executable or embedded content that should not
# appear in generated Markdown content.
UNSAFE_CONTENT_PATTERNS = {
    "script_tag": r"<\s*/?\s*script\b",
    "iframe_tag": r"<\s*/?\s*iframe\b",
    "object_tag": r"<\s*/?\s*object\b",
    "embed_tag": r"<\s*/?\s*embed\b",
    "javascript_url": r"javascript\s*:",
    "html_event_handler": r"\bon\w+\s*=",
}

# Common unfinished template placeholders.
PLACEHOLDER_PATTERN = re.compile(
    r"\[\s*(?:insert|add|enter|your|placeholder|topic|company|name)\b[^\]]*\]",
    re.IGNORECASE,
)
COMPILED_UNSAFE_PATTERNS = {
    name: re.compile(pattern, re.IGNORECASE | re.DOTALL)
    for name, pattern in UNSAFE_CONTENT_PATTERNS.items()
}


def validate_content_text(
    content: str,
    min_length: int = 20,
    max_length: int = 30000,
) -> str:
    """Validate generated text before it is persisted as content."""

    if not isinstance(content, str):
        raise TypeError("Generated content must be a string.")

    content = content.strip()

    if len(content) < min_length:
        raise ValueError("Generated content is too short.")

    if len(content) > max_length:
        raise ValueError("Generated content exceeds the maximum length.")

    for name, pattern in COMPILED_UNSAFE_PATTERNS.items():
        if pattern.search(content):
            raise ValueError(
                f"Generated content contains unsafe markup: {name}"
            )

    if PLACEHOLDER_PATTERN.search(content):
        raise ValueError(
            "Generated content contains an unresolved placeholder."
        )

    return content


def validate_linkedin_output(data: dict) -> dict:
    """Validate the structured LinkedIn draft."""

    if not isinstance(data, dict):
        raise TypeError("LinkedIn output must be a dictionary.")

    required_fields = {
        "hook",
        "post_body",
        "hashtags",
        "call_to_action",
    }

    if set(data.keys()) != required_fields:
        raise ValueError(
            "LinkedIn output must contain exactly: "
            "hook, post_body, hashtags, call_to_action."
        )

    validated = {
        "hook": validate_content_text(data["hook"], max_length=500),
        "post_body": validate_content_text(
            data["post_body"], max_length=5000
        ),
        "call_to_action": validate_content_text(
            data["call_to_action"], max_length=500
        ),
        "hashtags": data["hashtags"],
    }

    if not isinstance(validated["hashtags"], list):
        raise ValueError("LinkedIn hashtags must be a list.")

    if len(validated["hashtags"]) > 15:
        raise ValueError("LinkedIn output contains too many hashtags.")

    for hashtag in validated["hashtags"]:
        if not isinstance(hashtag, str):
            raise ValueError("Every hashtag must be a string.")

        if not re.fullmatch(r"#[A-Za-z0-9_]+", hashtag.strip()):
            raise ValueError(f"Invalid LinkedIn hashtag: {hashtag!r}")

    return validated


def validate_blog_output(data: dict) -> dict:
    """Validate the structured SEO blog output."""

    if not isinstance(data, dict):
        raise TypeError("Blog output must be a dictionary.")

    required_fields = {
        "seo_title",
        "meta_description",
        "url_slug",
        "primary_keyword",
        "secondary_keywords",
        "search_intent",
        "article_outline",
        "faqs",
        "call_to_action",
        "sources",
        "blog_article",
    }

    missing_fields = required_fields - set(data.keys())

    if missing_fields:
        raise ValueError(
            f"Blog output is missing fields: {sorted(missing_fields)}"
        )

    validated = dict(data)

    validated["blog_article"] = validate_content_text(
        data["blog_article"],
        max_length=30000,
    )

    validated["seo_title"] = validate_content_text(
        data["seo_title"], max_length=100
    )

    validated["meta_description"] = validate_content_text(
        data["meta_description"], max_length=300
    )

    validated["call_to_action"] = validate_content_text(
        data["call_to_action"], max_length=1000
    )

    return validated
