
import json
import os
import re
from collections.abc import Callable, Iterator

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.config import get_stream_writer

from src.core.logger import setup_logger
from src.core.state import ContentState
from src.integrations.openai_client import stream_text
from src.prompts.seo_blog_writer_agent_prompt import get_seo_blog_article_prompt, get_seo_blog_system_prompt
from src.tools.blog_writer_tools import blog_writer_tools
from src.repositories.conversation_repository import get_conversation
from src.repositories.message_repository import add_message


DEFAULT_MODEL = "gpt-4o-mini"

logger = setup_logger("seo_blog_writer")

SEO_BLOG_SYSTEM_PROMPT = get_seo_blog_system_prompt()
SEO_BLOG_ARTICLE_PROMPT = get_seo_blog_article_prompt()

# The repositories call the blog type "seo_blog".
BLOG_CONTENT_TYPE = "seo_blog"

# Progress shown in the UI when the agent calls a tool.
TOOL_STATUS = {
    "call_content_research_agent": "Researching topic...",
    "internet_search": "Analyzing SEO opportunities...",
}

URL_PATTERN = re.compile(r"https?://[^\s\"'<>\\]+")


# ------------------------------------------------
# 1. Build SEO Blog Writer Agent
# ------------------------------------------------

def build_seo_blog_writer():
    """
    Build the SEO Blog Writer agent with Research and Internet Search tools.
    """
    logger.info("Building SEO Blog Writer agent with tools: %s", blog_writer_tools)

    model_name = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)

    return create_agent(
        model = f"openai:{model_name}",
        tools = blog_writer_tools,
        system_prompt = SEO_BLOG_SYSTEM_PROMPT,
    )


# ------------------------------------------------
# 2. Parse Agent Response
# ------------------------------------------------

def extract_response_text(content) -> str:
    """Extract text from a LangChain AIMessage response."""

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        text_parts = []

        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(item.get("text", ""))

        return "\n".join(text_parts).strip()

    raise ValueError("Unsupported agent response format.")


def parse_blog_response(response: str) -> dict:
    """Parse the structured JSON returned by the SEO Blog Writer."""

    cleaned = re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        response.strip(),
        flags=re.IGNORECASE,
    ).strip()

    try:
        blog_data = json.loads(cleaned)
    except json.JSONDecodeError as error:
        logger.exception("SEO Blog Writer returned invalid JSON.")
        raise ValueError("SEO Blog Writer returned invalid JSON.") from error

    if not isinstance(blog_data, dict):
        raise ValueError("SEO Blog Writer response must be a JSON object.")

    return blog_data


# ------------------------------------------------
# 3. Validate Structured Blog Output
# ------------------------------------------------

def validate_blog_data(blog_data: dict, require_article: bool = True) -> None:
    """Validate the required SEO blog fields.

    The plan from the agent has no article yet, so require_article=False skips it.
    """

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
    }

    if require_article:
        required_fields.add("blog_article")

    missing_fields = required_fields - blog_data.keys()

    if missing_fields:
        raise ValueError(
            f"SEO blog response is missing fields: {sorted(missing_fields)}"
        )

    string_fields = [
        "seo_title",
        "meta_description",
        "url_slug",
        "primary_keyword",
        "search_intent",
        "call_to_action",
    ]

    if require_article:
        string_fields.append("blog_article")

    for field in string_fields:
        if not isinstance(blog_data[field], str):
            raise ValueError(f"{field} must be a string.")

    if require_article and not blog_data["blog_article"].strip():
        raise ValueError("Blog article cannot be empty.")

    list_fields = [
        "secondary_keywords",
        "article_outline",
        "faqs",
        "sources",
    ]

    for field in list_fields:
        if not isinstance(blog_data[field], list):
            raise ValueError(f"{field} must be a list.")

    for faq in blog_data["faqs"]:
        if not isinstance(faq, dict):
            raise ValueError("Each FAQ must be an object.")

        if not isinstance(faq.get("question"), str):
            raise ValueError("FAQ question must be a string.")

        if not isinstance(faq.get("answer"), str):
            raise ValueError("FAQ answer must be a string.")

    for source in blog_data["sources"]:
        if not isinstance(source, dict):
            raise ValueError("Each source must be an object.")

        if not isinstance(source.get("url"), str):
            raise ValueError("Source URL must be a string.")


# ------------------------------------------------
# 4. Verify Source URLs
# ------------------------------------------------

def validate_source_urls(blog_data: dict, available_results: list[dict]) -> None:
    """
    Keep only URLs actually returned by the research and search tools.

    This prevents the model from introducing fabricated source URLs.
    """

    allowed_urls = {
        result.get("url", "").strip()
        for result in available_results
        if result.get("url")
    }

    validated_sources = []

    for source in blog_data.get("sources", []):
        url = source.get("url", "").strip()

        if url in allowed_urls:
            validated_sources.append(source)
        else:
            logger.warning("Ignoring unverified source URL: %s", url)

    blog_data["sources"] = validated_sources


# ------------------------------------------------
# 5. Format Blog as Markdown
# ------------------------------------------------

def format_blog_markdown(blog_data: dict) -> str:
    """
    Format the complete reader-facing blog.
    Excludes SEO metadata and article outline.
    """

    article = blog_data.get("blog_article", "").strip()

    if not article:
        raise ValueError("Blog article is empty.")

    sections = [article]

    # FAQs
    faqs = blog_data.get("faqs", [])

    if faqs:
        sections.append("## Frequently Asked Questions")

        for faq in faqs:
            sections.append(
                f"### {faq.get('question', '')}\n\n"
                f"{faq.get('answer', '')}"
            )

    # Call to action
    cta = blog_data.get("call_to_action", "").strip()

    if cta:
        sections.append(f"## Call to Action\n\n{cta}")

    # Sources
    sources = blog_data.get("sources", [])

    if sources:
        sections.append("## References")

        for index, source in enumerate(sources, start=1):
            title = source.get("title", "").strip()
            url = source.get("url", "").strip()

            if url:
                display_title = title or url
                sections.append(f"{index}. [{display_title}]({url})")

    return "\n\n".join(sections)


def format_blog_header(blog_data: dict) -> str:
    """The title above the article.

    SEO details and the outline are kept in the stored blog data, not in the reader-facing draft.
    """

    return f"# {blog_data['seo_title']}"


def format_blog_footer(blog_data: dict) -> str:
    """FAQs, call to action and sources: everything below the article. Empty sections are left out."""

    lines = []

    faqs = [faq for faq in blog_data.get("faqs", []) if faq.get("question")]
    if faqs:
        lines += ["## Frequently Asked Questions", ""]

    for faq in faqs:
        lines += [
            f"### {faq.get('question', '')}",
            "",
            faq.get("answer", ""),
            "",
        ]

    if blog_data.get("call_to_action", "").strip():
        lines += [
            "## Call to Action",
            "",
            blog_data["call_to_action"].strip(),
            "",
        ]

    sources = [source for source in blog_data.get("sources", []) if source.get("url")]
    if sources:
        lines += ["## Sources", ""]

    for index, source in enumerate(sources, start=1):
        title = source.get("title", "").strip() or source.get("url", "")
        url = source.get("url", "")

        lines.append(f"{index}. [{title}]({url})")

    return "\n".join(lines).strip()


# ------------------------------------------------
# 6. Plan with the agent, then stream the article
# ------------------------------------------------

def collect_tool_results(messages: list) -> list[dict]:
    """URLs the research and search tools actually returned, for source validation."""

    urls = set()

    for message in messages:
        if isinstance(message, ToolMessage):
            urls.update(URL_PATTERN.findall(str(message.content)))

    return [{"url": url.rstrip(".,;:)]}")} for url in urls]


def plan_seo_blog(
    topic: str,
    target_audience: str = "",
    tone: str = "",
    keywords: list[str] | None = None,
    objective: str = "",
    on_event: Callable[[dict], None] | None = None,
) -> tuple[dict, list[dict]]:
    """
    Invoke the SEO Blog Writer agent to research the topic and plan the blog.

    The agent decides when to call:
    - call_content_research_agent
    - internet_search

    Returns (blog plan, tool results).
    """

    if not topic or not topic.strip():
        raise ValueError("Blog topic cannot be empty.")

    keywords = keywords or []

    logger.info("Planning SEO blog for topic: %s", topic)

    agent = build_seo_blog_writer()

    user_request = f"""
Plan an SEO blog post using the available research and internet
search tools.

BLOG CONTEXT

Topic: {topic}

Target audience: {target_audience or "General audience"}

Writing tone: {tone or "Professional and informative"}

Target keywords: {json.dumps(keywords, ensure_ascii=False)}

Blog objective: {objective or "Inform and educate readers"}

TOOL REQUIREMENTS

1. Call call_content_research_agent to research the topic.
2. Call internet_search to investigate SEO opportunities.
3. Use the actual results from both tools.
4. Do not invent facts, source URLs, or SEO metrics.

OUTPUT REQUIREMENTS

Return ONLY a valid JSON object. Do not use Markdown code fences.
Do not write the article itself; it is written from this plan.

Use exactly these keys:

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
    "key_points": [
        {{"point": "string", "source_urls": ["string"]}}
    ],
    "faqs": [
        {{"question": "string", "answer": "string"}}
    ],
    "call_to_action": "string",
    "sources": [
        {{"title": "string", "url": "string"}}
    ]
}}
"""

    emit = on_event or (lambda event: None)

    # Stream the agent's steps so the UI can show which tool it is using.
    messages = []
    for update in agent.stream(
        {"messages": [{"role": "user", "content": user_request}]},
        stream_mode="updates",
    ):
        for node_update in update.values():
            for message in (node_update or {}).get("messages", []):
                messages.append(message)
                if isinstance(message, AIMessage) and message.tool_calls:
                    for call in message.tool_calls:
                        emit({"event": "status", "text": TOOL_STATUS.get(call["name"], "Researching...")})
                elif isinstance(message, ToolMessage):
                    emit({"event": "status", "text": "Planning the article..."})

    if not messages:
        raise RuntimeError("SEO Blog Writer returned no messages.")

    final_message = messages[-1]

    if not isinstance(final_message, AIMessage):
        raise RuntimeError("SEO Blog Writer did not return an AI response.")

    response_text = extract_response_text(final_message.content)

    if not response_text:
        raise RuntimeError("SEO Blog Writer returned empty content.")

    plan = parse_blog_response(response_text)

    validate_blog_data(plan, require_article=False)

    return plan, collect_tool_results(messages)


def stream_blog_article(
    plan: dict,
    target_audience: str = "",
    tone: str = "",
    objective: str = "",
) -> Iterator[str]:
    """Write the article from the plan, yielding Markdown as it is generated."""

    query = f"""
BLOG PLAN

{json.dumps(plan, ensure_ascii=False, indent=2)}

Target audience: {target_audience or "General audience"}

Writing tone: {tone or "Professional and informative"}

Blog objective: {objective or "Inform and educate readers"}

Write the complete article now.
"""

    yield from stream_text(
        query = query,
        system_prompt = SEO_BLOG_ARTICLE_PROMPT,
        max_output_tokens = 4000,
    )


def write_seo_blog(
    topic: str,
    target_audience: str = "",
    tone: str = "",
    keywords: list[str] | None = None,
    objective: str = "",
    on_event: Callable[[dict], None] | None = None,
) -> dict:
    """
    Research, plan and write an SEO blog.

    on_event receives progress for the UI:
    {"event": "status", "text"}, {"event": "header", "text"} with the
    Markdown above the article, then {"event": "text", "text"} per chunk.
    """

    emit = on_event or (lambda event: None)

    emit({"event": "status", "text": "Researching topic..."})

    plan, tool_results = plan_seo_blog(
        topic = topic,
        target_audience = target_audience,
        tone = tone,
        keywords = keywords,
        objective = objective,
        on_event = emit,
    )

    # Keep only sources the tools actually returned.
    validate_source_urls(plan, tool_results)

    emit({"event": "header", "text": format_blog_header(plan)})
    emit({"event": "status", "text": "Writing blog..."})

    chunks = []
    for chunk in stream_blog_article(plan, target_audience, tone, objective):
        chunks.append(chunk)
        emit({"event": "text", "text": chunk})

    # The live preview ends with the FAQs, call to action and sources, like the draft.
    emit({"event": "text", "text": "\n\n" + format_blog_footer(plan)})

    article = re.sub(
        r"^```(?:markdown|md)?\s*|\s*```$",
        "",
        "".join(chunks).strip(),
        flags=re.IGNORECASE,
    ).strip()

    blog_data = {**plan, "blog_article": article}

    validate_blog_data(blog_data)

    logger.info("SEO Blog Writer completed for topic: %s", topic)

    return blog_data


# ------------------------------------------------
# 7. LangGraph Node
# ------------------------------------------------

def seo_blog_writer_node(state: ContentState) -> dict:
    """Generate an SEO blog and save it to MongoDB."""

    user_id = state.get("user_id")
    conversation_id = state.get("conversation_id")

    writer = get_stream_writer()

    writer({
        "type": "progress",
        "message": "Researching your topic..."
    })

    if not user_id or not conversation_id:
        raise ValueError("user_id and conversation_id are required.")

    conversation = get_conversation(conversation_id, user_id)

    if not conversation:
        raise ValueError("Conversation not found.")

    if conversation.get("content_type") != BLOG_CONTENT_TYPE:
        raise ValueError("This is not a blog conversation.")

    topic = state.get("topic") or conversation.get("topic", "")

    target_audience = (
        state.get("target_audience")
        or conversation.get("target_audience", "")
    )

    tone = state.get("tone") or conversation.get("tone", "")

    keywords = (
        state.get("keywords")
        or conversation.get("keywords", [])
    )

    objective = (
        state.get("objective")
        or conversation.get("objective", "")
    )

    if not topic:
        raise ValueError("Blog topic is required.")

    # Generate structured blog.
    blog_data = write_seo_blog(
        topic = topic,
        target_audience = target_audience,
        tone = tone,
        keywords = keywords,
        objective = objective,
        # Streams progress and the article text to the UI (stream_mode="custom").
        on_event = get_stream_writer(),
    )

    # Format output for the existing review node.
    report = format_blog_markdown(blog_data)

    # Save structured blog in the existing messages collection.
    saved_message = add_message(
        conversation_id = conversation_id,
        user_id = user_id,
        role = "assistant",
        message_type = "generated_content",
        content_type = BLOG_CONTENT_TYPE,
        content = blog_data,
        agent_name = "seo_blog_writer",
        metadata={
            "status": "draft",
            "version": 1,
            "content_text": report,
        },
    )

    message_id = saved_message["message_id"]

    completed_agents = list(state.get("completed_agents", []))

    if "seo_blog_writer" not in completed_agents:
        completed_agents.append("seo_blog_writer")

    logger.info(
        "SEO blog saved successfully. Message ID: %s",
        message_id,
    )

    return {
        "current_agent": "seo_blog_writer",
        "topic": topic,

        "blog_data": blog_data,
        "blog_title": blog_data["seo_title"],
        "blog_meta_description": blog_data["meta_description"],
        "blog_slug": blog_data["url_slug"],
        "blog_primary_keyword": blog_data["primary_keyword"],
        "blog_secondary_keywords": blog_data["secondary_keywords"],
        "blog_search_intent": blog_data["search_intent"],
        "blog_outline": blog_data["article_outline"],
        "blog_article": blog_data["blog_article"],
        "blog_headings": [
            item.get("heading", "")
            for item in blog_data["article_outline"]
            if isinstance(item, dict)
        ],
        "blog_faqs": blog_data["faqs"],
        "blog_call_to_action": blog_data["call_to_action"],

        "current_content": report,
        "generated_content_message_id": message_id,
        "completed_agents": completed_agents,

        "messages": [
            AIMessage(content=report)
        ],
    }
