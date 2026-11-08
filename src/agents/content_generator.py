
import json
import re
from collections.abc import Callable

from langchain_core.messages import AIMessage
from langgraph.config import get_stream_writer

from src.core.logger import setup_logger
from src.core.state import ContentState
from src.integrations.text_provider_manager import text_provider_manager
from src.repositories.conversation_repository import get_conversation
from src.repositories.message_repository import add_message
from src.core.brand_voice import build_brand_voice_context

from src.agents.linkedin_writer import write_linkedin_post
from src.agents.blog_writer import (
    parse_blog_response,
    validate_blog_data,
    validate_source_urls,
    format_blog_markdown,
    BLOG_CONTENT_TYPE,
    SEO_BLOG_ARTICLE_PROMPT,
)

logger = setup_logger("content_generator")

JSON_ESCAPES = {"n": "\n", "t": "\t", "r": "", "b": "", "f": "", "/": "/", '"': '"', "\\": "\\"}


class JsonStringFieldStreamer:
    """Pulls one string field's text out of a JSON object while it is still being streamed."""

    def __init__(self, field: str):
        self.marker = re.compile(r'"%s"\s*:\s*"' % re.escape(field))
        self.buffer = ""
        self.pos: int | None = None
        self.done = False

    def feed(self, chunk: str) -> str:
        """Add a chunk; return the field text decoded since the last call."""

        self.buffer += chunk
        if self.done:
            return ""
        if self.pos is None:
            match = self.marker.search(self.buffer)
            if not match:
                return ""
            self.pos = match.end()

        out = []
        buffer, i = self.buffer, self.pos
        while i < len(buffer):
            char = buffer[i]
            if char == '"':
                self.done = True
                i += 1
                break
            if char != "\\":
                out.append(char)
                i += 1
                continue
            # Escapes may be split across chunks; wait for the rest.
            if i + 1 >= len(buffer):
                break
            code = buffer[i + 1]
            if code == "u":
                if i + 6 > len(buffer):
                    break
                try:
                    out.append(chr(int(buffer[i + 2 : i + 6], 16)))
                except ValueError:
                    pass
                i += 6
                continue
            out.append(JSON_ESCAPES.get(code, code))
            i += 2
        self.pos = i
        return "".join(out)


def generate_seo_blog_from_strategy(
    topic: str,
    research_report: str,
    content_strategy: str,
    target_audience: str = "",
    tone: str = "",
    keywords: list[str] | None = None,
    objective: str = "",
    available_results: list[dict] | None = None,
    brand_voice_context: str = "",
    on_event: Callable[[dict], None] | None = None,
) -> dict:
    """Generate an SEO blog using the strategist's research and plan.

    on_event receives {"event": "status" | "text", "text"} so the UI can stream the article.
    """

    if not topic.strip():
        raise ValueError("Blog topic is required.")

    if not research_report.strip():
        raise ValueError("Research report is required.")

    if not content_strategy.strip():
        raise ValueError("Content strategy is required.")

    query = f"""
Create a complete SEO blog article using the research and content strategy below.

TOPIC:
{topic}

RESEARCH REPORT:
{research_report}

CONTENT STRATEGY:
{content_strategy}

BLOG SETTINGS:
Target audience: {target_audience or "General audience"}
Tone: {tone or "Professional and informative"}
Keywords: {json.dumps(keywords or [], ensure_ascii=False)}
Objective: {objective or "Inform and educate readers"}
BRAND VOICE CONTEXT:{brand_voice_context or "No additional brand voice preferences provided."}

Requirements:
1. Follow the content strategy's recommended themes, messages, angles, and outline.
2. Use the research report as the factual foundation.
3. Do not perform new research or invent facts, statistics, or source URLs.
4. Write a complete, readable, well-structured SEO blog article.
5. Include an appropriate SEO title, meta description, URL slug,
   primary and secondary keywords, search intent, article outline,
   FAQs, call to action, and sources.
6. Return ONLY a valid JSON object with these keys:

{{
    "seo_title": "string",
    "meta_description": "string",
    "url_slug": "string",
    "primary_keyword": "string",
    "secondary_keywords": ["string"],
    "search_intent": "string",
    "article_outline": [
        {{"level": "H2", "heading": "string"}}
    ],
    "faqs": [
        {{"question": "string", "answer": "string"}}
    ],
    "call_to_action": "string",
    "sources": [
        {{"title": "string", "url": "string"}}
    ],
    "blog_article": "Complete Markdown article"
}}
"""

    # The model returns JSON; stream the article text to the UI as it arrives.
    emit = on_event or (lambda event: None)
    emit({"event": "status", "text": "Writing your SEO blog..."})
    article = JsonStringFieldStreamer("blog_article")
    chunks = []
    for chunk in text_provider_manager.stream_text(
        query=query,
        system_prompt=SEO_BLOG_ARTICLE_PROMPT,
        max_output_tokens=4000,
    ):
        chunks.append(chunk)
        text = article.feed(chunk)
        if text:
            emit({"event": "text", "text": text})
    raw_output = "".join(chunks)

    blog_data = parse_blog_response(raw_output)
    validate_blog_data(blog_data)    

    if available_results:
        validate_source_urls(blog_data, available_results)

    return blog_data

# --------------------------------------------------------------------------
# Content Generator Node
# --------------------------------------------------------------------------

def content_generator_node(state: ContentState) -> dict:
    """Generate final content using the Content Strategist's output."""

    user_id = state.get("user_id", "").strip()
    conversation_id = state.get("conversation_id", "").strip()
    intent = state.get("intent", "").strip().lower()

    if not user_id or not conversation_id:
        raise ValueError("user_id and conversation_id are required.")

    conversation = get_conversation(
        conversation_id=conversation_id,
        user_id=user_id,
    )

    if not conversation:
        raise ValueError("Conversation was not found.")

    topic = state.get("topic") or conversation.get("topic", "")

    target_audience = (
        state.get("target_audience")
        or conversation.get("target_audience", "")
    )

    tone = state.get("tone") or conversation.get("tone", "")

    # Keywords are stored in conversation metadata.
    metadata = conversation.get("metadata", {}) or {}

    keywords = state.get("keywords")
    if keywords is None:
        keywords = metadata.get("keywords", [])

    objective = state.get("objective") or conversation.get("objective", "")

    # Build context using the resolved conversation settings.
    brand_voice_state = {
        **state,
        "tone": tone,
        "target_audience": target_audience,
        "keywords": keywords,
    }

    brand_voice_context = build_brand_voice_context(brand_voice_state)

    research_report = state.get("research_report", "")
    content_strategy = state.get("content_strategy", "")

    if not topic.strip():
        raise ValueError("Topic is required.")

    if not research_report.strip() or not content_strategy.strip():
        raise ValueError(
            "Content Strategist must generate both research_report and content_strategy."
        )

    logger.info(
        "Generating %s content for conversation %s",
        intent,
        conversation_id,
    )

    if intent == "linkedin":
        if conversation.get("content_type") != "linkedin":
            raise ValueError("This is not a LinkedIn conversation.")

        profile_answers = state.get("linkedin_profile_answers", {})

        draft = write_linkedin_post(
            topic=topic,
            profile_answers=profile_answers,
            target_audience=target_audience,
            tone=tone,
            keywords=keywords,
            objective=objective,
            research_report=research_report,
            content_strategy=content_strategy,
            brand_voice_context=brand_voice_context,
        )

        content = {
            "hook": draft["hook"],
            "post_body": draft["post_body"],
            "hashtags": draft["hashtags"],
            "call_to_action": draft["call_to_action"],
        }

        content_text = "\n\n".join([
            draft["hook"],
            draft["post_body"],
            draft["call_to_action"],
            " ".join(draft["hashtags"]),
        ]).strip()

        content_type = "linkedin"

    elif intent in ("blog", "seo_blog"):
        if conversation.get("content_type") != BLOG_CONTENT_TYPE:
            raise ValueError("This is not an SEO blog conversation.")

        blog_data = generate_seo_blog_from_strategy(
            topic=topic,
            research_report=research_report,
            content_strategy=content_strategy,
            target_audience=target_audience,
            tone=tone,
            keywords=keywords,
            objective=objective,
            available_results=state.get("research_results", []),
            brand_voice_context=brand_voice_context,
            on_event=get_stream_writer(),
        )

        content = blog_data
        content_text = format_blog_markdown(blog_data)
        content_type = BLOG_CONTENT_TYPE

    else:
        raise ValueError(f"Unsupported content generation intent: {intent}")

    saved_message = add_message(
        conversation_id=conversation_id,
        user_id=user_id,
        role="assistant",
        message_type="generated_content",
        content_type=content_type,
        content=content,
        agent_name="content_generator",
        metadata={
            "status": "draft",
            "version": 1,
            "content_text": content_text,
        },
    )

    message_id = saved_message["message_id"]

    completed_agents = list(state.get("completed_agents", []))
    if "content_generator" not in completed_agents:
        completed_agents.append("content_generator")

    logger.info(
        "Generated content saved successfully. Message ID: %s",
        message_id,
    )

    return {
        "current_agent": "content_generator",
        "current_content": content_text,
        "generated_content_message_id": message_id,
        "completed_agents": completed_agents,
        "messages": [AIMessage(content=content_text)],
    }
