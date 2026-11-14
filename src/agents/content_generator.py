
import json
import re
from collections.abc import Callable

from langchain_core.messages import AIMessage
from langgraph.config import get_stream_writer

from src.core.logger import setup_logger
from src.core.state import ContentState
from src.core.brand_voice import build_brand_voice_context

from src.integrations.text_provider_manager import text_provider_manager

from src.repositories.conversation_repository import get_conversation
from src.repositories.message_repository import add_message

from src.agents.linkedin_writer import write_linkedin_post
from src.utils.quality_validation import evaluate_content_quality

from src.agents.blog_writer import (
    parse_blog_response,
    validate_blog_data,
    validate_source_urls,
    format_blog_markdown,
    BLOG_CONTENT_TYPE,
    SEO_BLOG_ARTICLE_PROMPT,
)

from src.guardrails.content_output_guardrails import (
    validate_linkedin_output,
    validate_blog_output,
)

logger = setup_logger("content_generator")

JSON_ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "",
    "b": "",
    "f": "",
    "/": "/",
    '"': '"',
    "\\": "\\",
}


class JsonStringFieldStreamer:
    """Extract a string field from streamed JSON."""

    def __init__(self, field: str):
        self.marker = re.compile(
            r'"%s"\s*:\s*"' % re.escape(field)
        )
        self.buffer = ""
        self.pos: int | None = None
        self.done = False

    def feed(self, chunk: str) -> str:
        """Return newly received text from the target JSON field."""

        self.buffer += chunk

        if self.done:
            return ""

        if self.pos is None:
            match = self.marker.search(self.buffer)

            if not match:
                return ""

            self.pos = match.end()

        output = []
        buffer = self.buffer
        index = self.pos

        while index < len(buffer):
            char = buffer[index]

            if char == '"':
                self.done = True
                index += 1
                break

            if char != "\\":
                output.append(char)
                index += 1
                continue

            # Wait if an escape sequence is split across chunks.
            if index + 1 >= len(buffer):
                break

            code = buffer[index + 1]

            if code == "u":
                if index + 6 > len(buffer):
                    break

                try:
                    output.append(
                        chr(int(buffer[index + 2:index + 6], 16))
                    )
                except ValueError:
                    pass

                index += 6
                continue

            output.append(JSON_ESCAPES.get(code, code))
            index += 2

        self.pos = index

        return "".join(output)


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
    """Generate an SEO blog using research and content strategy."""

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

BRAND VOICE CONTEXT:
{brand_voice_context or "No additional brand voice preferences provided."}

Requirements:
1. Follow the content strategy's recommended themes, messages, angles, and outline.
2. Use the research report as the factual foundation.
3. Do not perform new research or invent facts, statistics, or source URLs.
4. Write a complete, readable, well-structured SEO blog article.
5. Include SEO title, meta description, URL slug, keywords, search intent,
   article outline, FAQs, call to action, and sources.
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

    emit = on_event or (lambda event: None)

    emit({
        "event": "status",
        "text": "Writing your SEO blog..."
    })

    article_streamer = JsonStringFieldStreamer("blog_article")
    chunks = []

    for chunk in text_provider_manager.stream_text(
        query=query,
        system_prompt=SEO_BLOG_ARTICLE_PROMPT,
        max_output_tokens=4000,
    ):
        chunks.append(chunk)

        article_text = article_streamer.feed(chunk)

        if article_text:
            emit({
                "event": "text",
                "text": article_text,
            })

    raw_output = "".join(chunks)

    blog_data = parse_blog_response(raw_output)

    validate_blog_data(blog_data)

    if available_results:
        validate_source_urls(blog_data, available_results)

    blog_data = validate_blog_output(blog_data)

    return blog_data


# ------------------------------------------------------------------
# Content Generator Node
# ------------------------------------------------------------------

def content_generator_node(state: ContentState) -> dict:
    """Generate LinkedIn or SEO blog content."""

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

    metadata = conversation.get("metadata", {}) or {}

    keywords = state.get("keywords")

    if keywords is None:
        keywords = metadata.get("keywords", [])

    objective = (
        state.get("objective")
        or conversation.get("objective", "")
    )

    brand_voice_state = {
        **state,
        "tone": tone,
        "target_audience": target_audience,
        "keywords": keywords,
    }

    brand_voice_context = build_brand_voice_context(
        brand_voice_state
    )

    research_report = state.get("research_report", "")
    content_strategy = state.get("content_strategy", "")

    if not topic.strip():
        raise ValueError("Topic is required.")

    if not research_report.strip() or not content_strategy.strip():
        raise ValueError(
            "Content Strategist must generate both "
            "research_report and content_strategy."
        )

    logger.info(
        "Generating %s content for conversation %s",
        intent,
        conversation_id,
    )

    # --------------------------------------------------------------
    # LinkedIn generation
    # --------------------------------------------------------------

    if intent == "linkedin":

        if conversation.get("content_type") != "linkedin":
            raise ValueError("This is not a LinkedIn conversation.")

        profile_answers = state.get(
            "linkedin_profile_answers", {}
        )

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

        draft = validate_linkedin_output(draft)

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

    # --------------------------------------------------------------
    # SEO Blog generation
    # --------------------------------------------------------------

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
        raise ValueError(
            f"Unsupported content generation intent: {intent}"
        )

    # --------------------------------------------------------------
    # Content Quality Scoring
    # --------------------------------------------------------------

    quality_result = evaluate_content_quality(
        content=content_text,
        content_type=content_type,
        keywords=keywords,
        blog_data=content if content_type == BLOG_CONTENT_TYPE else None,
    )
    quality_score = quality_result["score"]

    logger.info(
        "Content quality score: %s/100 (%s)",
        quality_score,
        quality_result["grade"],
    )

    # --------------------------------------------------------------
    # Persist generated content
    # --------------------------------------------------------------

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
            "quality_score": quality_score,
            "quality_grade": quality_result["grade"],
            "quality_details": quality_result["checks"],
            "quality_suggestions": quality_result["suggestions"],
        },
    )

    message_id = saved_message["message_id"]

    completed_agents = list(
        state.get("completed_agents", [])
    )

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
        "quality_score": quality_score,
        "quality_grade": quality_result["grade"],
        "quality_details": quality_result["checks"],
        "quality_suggestions": quality_result["suggestions"],

        "messages": [
            AIMessage(content=content_text)
        ],
    }


# ------------------------------------------------------------
# Multi Content Generator
# ------------------------------------------------------------------


def multi_content_generator_node(state: ContentState) -> dict:
    """Generate one requested blog or LinkedIn deliverable in a multi workflow."""

    user_id = state.get("user_id", "").strip()
    conversation_id = state.get("conversation_id", "").strip()
    next_agent = state.get("next_agent", "").strip().lower()

    if not user_id or not conversation_id:
        raise ValueError("user_id and conversation_id are required.")

    if next_agent not in ("blog", "linkedin"):
        raise ValueError( f"Unsupported multi-content deliverable: {next_agent}"  )

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

    metadata = conversation.get("metadata", {}) or {}
    keywords = state.get("keywords")

    if keywords is None:
        keywords = metadata.get("keywords", [])

    objective = (
        state.get("objective")
        or conversation.get("objective", "")
    )

    if not isinstance(topic, str) or not topic.strip():
      raise ValueError("Topic is required.")

    research_report  = state.get("research_report", "")
    content_strategy = state.get("content_strategy", "")

    if not research_report.strip() or not content_strategy.strip():
        raise ValueError(
            "Research report and content strategy are required."
        )

    brand_voice_context = build_brand_voice_context({
        **state,
        "tone": tone,
        "target_audience": target_audience,
        "keywords": keywords,
    })

    logger.info(
        "Generating multi deliverable: %s | Conversation: %s",
        next_agent,
        conversation_id,
    )

    if next_agent == "linkedin":
        draft = write_linkedin_post(
            topic=topic,
            profile_answers=state.get("linkedin_profile_answers", {}),
            target_audience=target_audience,
            tone=tone,
            keywords=keywords,
            objective=objective,
            research_report=research_report,
            content_strategy=content_strategy,
            brand_voice_context=brand_voice_context,
        )

        draft = validate_linkedin_output(draft)

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

    else:
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

    quality_result = evaluate_content_quality(
        content=content_text,
        content_type=content_type,
        keywords=keywords,
        blog_data=content if content_type == BLOG_CONTENT_TYPE else None,
    )

    saved_message = add_message(
        conversation_id=conversation_id,
        user_id=user_id,
        role="assistant",
        message_type="generated_content",
        content_type=content_type,
        content=content,
        agent_name=f"{next_agent}_writer",
        metadata={
            "status": "draft",
            "version": 1,
            "content_text": content_text,
            "quality_score": quality_result["score"],
            "quality_grade": quality_result["grade"],
            "quality_details": quality_result["checks"],
            "quality_suggestions": quality_result["suggestions"],
        },
    )

    message_id = saved_message["message_id"]

    results = dict(state.get("multi_agent_results", {}))

    results[next_agent] = {
        "content": content,
        "content_text": content_text,
        "content_type": content_type,
        "message_id": message_id,
        "status": "draft",
        "quality_score": quality_result["score"],
        "quality_grade": quality_result["grade"],
        "quality_details": quality_result["checks"],
        "quality_suggestions": quality_result["suggestions"],
    }

    completed_agents = list(state.get("completed_agents", []))
    agent_name = f"{next_agent}_writer"

    if agent_name not in completed_agents:
        completed_agents.append(agent_name)

    logger.info(
        "Multi deliverable saved: %s | Message ID: %s",
        next_agent,
        message_id,
    )

    return {
        "multi_agent_results": results,
        "completed_agents": completed_agents,
        "current_agent": agent_name,
        "current_content": content_text,
        "quality_score": quality_result["score"],
        "quality_grade": quality_result["grade"],
        "quality_details": quality_result["checks"],
        "quality_suggestions": quality_result["suggestions"],
        "messages": [AIMessage(content=content_text)],
    }
