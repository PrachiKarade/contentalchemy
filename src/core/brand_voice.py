from src.core.state import ContentState


def build_brand_voice_context(state: ContentState) -> str:
    """Build writing instructions from optional conversation preferences."""

    instructions = []

    tone = state.get("tone", "").strip()
    audience = state.get("target_audience", "").strip()
    keywords = state.get("keywords", [])

    if tone:
        instructions.append(f"- Tone: {tone}")

    if audience:
        instructions.append(f"- Target audience: {audience}")

    if keywords:
        keyword_text = ", ".join(
            keyword.strip()
            for keyword in keywords
            if keyword.strip()
        )
        if keyword_text:
            instructions.append(f"- Preferred keywords: {keyword_text}")

    if not instructions:
        return ""

    return (
        "WRITING PREFERENCES:\n"
        + "\n".join(instructions)
        + "\n\nApply these preferences consistently. "
          "Incorporate keywords naturally without keyword stuffing. "
          "Do not force preferences where they do not fit the content."
    )