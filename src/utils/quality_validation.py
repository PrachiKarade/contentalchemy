
import re

# Maximum points per check.
MAX_POINTS = {
    "linkedin": {
        "hook": 20,
        "readability": 20,
        "call_to_action": 20,
        "hashtags": 20,
        "structure": 20,
    },
    "blog": {
        "title": 15,
        "meta_description": 15,
        "headings": 20,
        "keyword_usage": 15,
        "article_length": 20,
        "call_to_action": 15,
    },
}


def _score_linkedin(content: str) -> dict:
    """Evaluate the quality of a LinkedIn post."""

    checks = {}
    suggestions = []

    text = content.strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # 1. Hook (20 points)
    first_line = lines[0] if lines else ""

    hook_score = 20 if (
        15 <= len(first_line) <= 250
        and not first_line.startswith("#")
    ) else 10

    checks["hook"] = hook_score

    if hook_score < 20:
        suggestions.append("Improve the opening hook to capture attention.")

    # 2. Readability and length (20 points)
    word_count = len(re.findall(r"\b\w+\b", text))

    if 100 <= word_count <= 800:
        readability_score = 20
    elif 50 <= word_count < 100 or 800 < word_count <= 1200:
        readability_score = 15
    else:
        readability_score = 8

    checks["readability"] = readability_score

    if readability_score < 20:
        suggestions.append("Review post length and readability.")

    # 3. Call to action (20 points)
    cta_pattern = (
        r"\b(what do you think|share your thoughts|"
        r"comment|let me know|follow|try this|"
        r"what's your experience|have you)\b"
    )

    cta_score = 20 if re.search(
        cta_pattern, text, re.IGNORECASE
    ) else 5

    checks["call_to_action"] = cta_score

    if cta_score < 20:
        suggestions.append("Add a clear call to action.")

    # 4. Hashtags (20 points)
    hashtags = re.findall(r"(?<!\w)#\w+", text)

    if 3 <= len(hashtags) <= 5:
        hashtag_score = 20
    elif 1 <= len(hashtags) < 3 or 5 < len(hashtags) <= 8:
        hashtag_score = 15
    else:
        hashtag_score = 5

    checks["hashtags"] = hashtag_score

    if hashtag_score < 20:
        suggestions.append("Use approximately 3–5 relevant hashtags.")

    # 5. Paragraph structure (20 points)
    paragraphs = [p for p in text.split("\n\n") if p.strip()]

    structure_score = 20 if len(paragraphs) >= 3 else 10
    checks["structure"] = structure_score

    if structure_score < 20:
        suggestions.append("Break the post into shorter, readable paragraphs.")

    return _build_result("linkedin", checks, suggestions)


def _score_blog(
    content: str,
    keywords: list[str] | None = None,
    blog_data: dict | None = None,
) -> dict:
    """Evaluate SEO blog using structured fields when available."""

    checks = {}
    suggestions = []

    blog_data = blog_data or {}

    # Use actual article rather than the complete formatted Markdown.
    article = (
        blog_data.get("blog_article")
        or content
    ).strip()

    seo_title = (
        blog_data.get("seo_title")
        or ""
    ).strip()

    meta_description = (
        blog_data.get("meta_description")
        or ""
    ).strip()

    call_to_action = (
        blog_data.get("call_to_action")
        or ""
    ).strip()

    lower_text = article.lower()

    # 1. SEO Title (15 points)
    if seo_title:
        title_score = 15
    else:
        title_match = re.search(
            r"^\s*#\s+(.+)",
            article,
            re.MULTILINE,
        )
        title_score = 15 if title_match else 5

    checks["title"] = title_score

    if title_score < 15:
        suggestions.append("Add a clear SEO title.")

    # 2. Meta Description (15 points)
    if meta_description:
        meta_length = len(meta_description)

        if 120 <= meta_length <= 160:
            meta_score = 15
        else:
            meta_score = 10
    else:
        meta_match = re.search(
            r"meta\s+description\s*:\s*(.+)",
            content,
            re.IGNORECASE,
        )

        meta_length = (
            len(meta_match.group(1).strip())
            if meta_match else 0
        )

        if 120 <= meta_length <= 160:
            meta_score = 15
        elif meta_length > 0:
            meta_score = 10
        else:
            meta_score = 0

    checks["meta_description"] = meta_score

    if meta_score < 15:
        suggestions.append(
            "Add an SEO meta description of approximately 120–160 characters."
        )

    # 3. Headings and Structure (20 points)
    headings = re.findall(
        r"^#{2,3}\s+.+",
        article,
        re.MULTILINE,
    )

    if len(headings) >= 4:
        heading_score = 20
    elif len(headings) >= 2:
        heading_score = 15
    else:
        heading_score = 5

    checks["headings"] = heading_score

    if heading_score < 20:
        suggestions.append(
            "Improve article structure with descriptive H2 and H3 headings."
        )

    # 4. Keyword Usage (15 points)
    matched_keywords = [
        keyword for keyword in (keywords or [])
        if keyword.strip()
        and keyword.lower() in lower_text
    ]

    if matched_keywords:
        keyword_score = (
            15
            if len(matched_keywords) >= min(2, len(keywords or []))
            else 10
        )
    else:
        keyword_score = 5 if not keywords else 0

    checks["keyword_usage"] = keyword_score

    if keyword_score < 15:
        suggestions.append(
            "Include the target keywords naturally in the article."
        )

    # 5. Article Length (20 points)
    word_count = len(re.findall(r"\b\w+\b", article))

    if word_count >= 1000:
        length_score = 20
    elif word_count >= 600:
        length_score = 15
    elif word_count >= 300:
        length_score = 10
    else:
        length_score = 5

    checks["article_length"] = length_score

    if length_score < 20:
        suggestions.append(
            "Consider expanding the article with useful details and examples."
        )

    # 6. Call to Action (15 points)
    if call_to_action:
        cta_score = 15
    else:
        cta_pattern = (
            r"\b(get started|contact us|learn more|"
            r"sign up|try now|book a demo|"
            r"subscribe|download|read more|"
            r"explore more|check out|discover)\b"
        )

        cta_score = (
            15
            if re.search(cta_pattern, article, re.IGNORECASE)
            else 5
        )

    checks["call_to_action"] = cta_score

    if cta_score < 15:
        suggestions.append("Include a relevant call to action.")

    return _build_result("blog", checks, suggestions)


def _build_result(
    content_type: str,
    checks: dict,
    suggestions: list[str],
) -> dict:
    """Build a normalized quality scoring result."""

    score = sum(checks.values())

    if score >= 85:
        grade = "Excellent"
    elif score >= 70:
        grade = "Good"
    elif score >= 50:
        grade = "Needs Improvement"
    else:
        grade = "Poor"

    return {
        "content_type": content_type,
        "score": score,
        "grade": grade,
        "checks": checks,
        "suggestions": suggestions,
    }


def evaluate_content_quality(
    content: str,
    content_type: str,
    keywords: list[str] | None = None,
    blog_data: dict | None = None,
) -> dict:
    """Evaluate generated LinkedIn or SEO blog content."""

    if not content or not content.strip():
        raise ValueError("Content cannot be empty.")

    content_type = content_type.lower().strip()

    if content_type == "linkedin":
        return _score_linkedin(content)

    if content_type in ("blog", "seo_blog"):
        return _score_blog(content, keywords, blog_data)

    raise ValueError(
        f"Unsupported content type: {content_type}"
    )
