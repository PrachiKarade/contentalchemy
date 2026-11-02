
from langchain_core.messages import AIMessage

from src.core.logger import setup_logger
from src.core.state import ContentState
from src.integrations.openai_client import generate_text
from src.repositories.message_repository import add_message

logger = setup_logger("content_writer")

# The repositories call the blog type "seo_blog".
REPO_CONTENT_TYPES = {"blog": "seo_blog"}

# Placeholder writer for the content types that do not have a dedicated agent yet.
SYSTEM_PROMPTS = {
    "research": (
        "You are a deep research analyst. Produce a well-structured research "
        "brief with key findings, supporting data points, trends and a short "
        "summary. Use markdown headings and bullet points. Do not invent "
        "statistics or sources; say when something needs verification."
    ),
    "blog": (
        "You are an SEO blog writer. Write a long-form, search-optimized blog "
        "post in markdown. Start with an H1 title, then a 'Meta description:' "
        "line under 160 characters, then an introduction, H2/H3 sections and "
        "a conclusion with a call to action. Use the target keywords naturally."
    ),
    "image": (
        "You are a visual content designer. Image generation is not connected "
        "yet, so write an optimized image-generation prompt instead: describe "
        "subject, composition, style, lighting, color palette and mood. Start "
        "with a one-line H1 title, then the prompt, then 2 alternative variations."
    ),
}


def content_writer_node(state: ContentState) -> dict:
    """Generate a research brief, SEO blog or image prompt draft."""

    intent = state.get("intent")

    if intent not in SYSTEM_PROMPTS:
        raise ValueError(f"content_writer_node does not support intent: {intent!r}")

    topic = state.get("topic") or state.get("user_request", "")

    if not topic.strip():
        raise ValueError("A topic is required to generate content.")

    parts = [SYSTEM_PROMPTS[intent]]
    if state.get("tone"):
        parts.append(f"Write in a {state['tone'].lower()} tone.")
    if state.get("target_audience"):
        parts.append(f"Target audience: {state['target_audience']}.")
    if state.get("keywords"):
        parts.append(f"Target keywords: {', '.join(state['keywords'])}.")

    logger.info("Generating %s draft for topic: %s", intent, topic)

    draft = generate_text(
        query = f"TOPIC: {topic.strip()}\n\nREQUEST: {state.get('user_request', topic).strip()}",
        system_prompt = "\n".join(parts),
    )

    # Save the draft so content_review can record the decision on it.
    generated_message = add_message(
        conversation_id=state["conversation_id"],
        user_id=state["user_id"],
        role="assistant",
        message_type="generated_content",
        content_type=REPO_CONTENT_TYPES.get(intent, intent),
        content=draft,
        agent_name="content_writer",
        metadata={"status": "draft", "version": 1, "content_text": draft},
    )

    completed_agents = list(state.get("completed_agents", []))
    if "content_writer" not in completed_agents:
        completed_agents.append("content_writer")

    updates = {
        "current_agent": "content_writer",
        "current_content": draft,
        "generated_content_message_id": generated_message["message_id"],
        "completed_agents": completed_agents,
        "messages": [AIMessage(content=draft)],
    }

    if intent == "blog":
        updates["blog_draft"] = draft
    elif intent == "research":
        updates["research_summary"] = draft
    else:
        updates["image_prompt"] = draft

    return updates
