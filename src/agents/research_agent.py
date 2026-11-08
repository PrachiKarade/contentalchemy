
import json
import re
from collections.abc import Callable

from src.integrations.serp_client import search_web
from src.integrations.openai_client import generate_text
from src.integrations.text_provider_manager import text_provider_manager
from src.core.logger import setup_logger
from src.prompts.research_agent_prompt import get_research_agent_system_prompt

# library imports for state management and message handling
from langchain_core.messages import AIMessage
from langgraph.config import get_stream_writer
from src.core.state import ContentState
from src.repositories.conversation_repository import get_conversation
from src.repositories.message_repository import add_message

logger = setup_logger("research_agent")


RESEARCH_SYSTEM_PROMPT = get_research_agent_system_prompt() 

def research_topic(
    topic: str,
    target_audience: str = "",
    num_results: int = 5,
    on_event: Callable[[dict], None] | None = None,
) -> dict:
    """
    Research a topic using SerpAPI and synthesize findings with OpenAI.

    on_event receives progress for the UI: {"event": "status", "text"}.
    """
    emit = on_event or (lambda event: None)
    logger.info("Research agent initialized for topic: %s", topic)

    if not topic or not topic.strip():
        raise ValueError("Research topic cannot be empty.")

    logger.info("Starting research for topic: %s", topic)

    # 1. Search the web
    emit({"event": "status", "text": "Searching the web for sources..."})
    search_results = search_web(topic, num_results)

    if not search_results:
        raise RuntimeError("No search results found for the given topic.")

    # 2. Prepare research context
    search_context = json.dumps(
        search_results,
        ensure_ascii=False,
        indent=2,
    )

    query = f"""
Research topic: {topic}

Target audience: {target_audience or "General audience"}

Analyze the following Google search results:

{search_context}

Extract useful findings and return the required JSON structure.
"""

    # 3. Synthesize research
    emit({"event": "status", "text": f"Analyzing {len(search_results)} sources..."})
    response = text_provider_manager.generate_text(
        query=query,
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        max_output_tokens=3000,
    )

    logger.info("Research synthesis completed for topic: %s", topic)

    # 4. Validate JSON response (strip Markdown fences, if the model added them)
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.strip(), flags=re.IGNORECASE).strip()

    try:
        research_data = json.loads(cleaned)
    except json.JSONDecodeError as error:
        logger.exception("Research agent returned invalid JSON.")
        raise ValueError("Research agent returned invalid JSON.") from error

    required_fields = {"topic", "findings", "research_summary", "sources"}

    if not required_fields.issubset(research_data):
        raise ValueError("Research response is missing required fields.")
    
    if not isinstance(research_data["findings"], list):
        raise ValueError("Research findings must be a list.")

    if not isinstance(research_data["sources"], list):
        raise ValueError("Research sources must be a list.")

    if not isinstance(research_data["research_summary"], str):
        raise ValueError("Research summary must be a string.")

    logger.info("Research completed for topic: %s", topic)

    return research_data


def format_research_report(research_data: dict) -> str:
    """Turn the structured research into the Markdown report the user reviews.

    The UI reads the findings and sources back from these headings, so keep
    the "## Key findings" / "### N." / "## Sources" layout.
    """

    lines = [
        f"# Research: {research_data.get('topic', '').strip()}",
        "",
        "## Summary",
        "",
        research_data.get("research_summary", "").strip(),
        "",
        "## Key findings",
    ]

    for index, finding in enumerate(research_data.get("findings", []), start=1):
        lines += ["", f"### {index}. {finding.get('claim', '').strip()}", ""]
        if finding.get("explanation"):
            lines.append(finding["explanation"].strip())
        urls = [url for url in finding.get("source_urls", []) if url]
        if urls:
            links = ", ".join(f"[{number}]({url})" for number, url in enumerate(urls, start=1))
            lines += ["", f"*Sources: {links}*"]

    lines += ["", "## Sources", ""]
    for index, source in enumerate(research_data.get("sources", []), start=1):
        title = source.get("title", "").strip() or source.get("url", "")
        entry = f"{index}. [{title}]({source.get('url', '')})"
        if source.get("snippet"):
            entry += f" - {source['snippet'].strip()}"
        lines.append(entry)

    return "\n".join(lines).strip()


# --------------------------------
# Agent node for langchain integration and langgraph
# -------------------------------
def research_agent_node(state: ContentState) -> dict:
    """Run research and persist the generated research content."""

    user_id = state.get("user_id")
    conversation_id = state.get("conversation_id")

    if not user_id or not conversation_id:
        raise ValueError("user_id and conversation_id are required.")

    conversation = get_conversation(conversation_id, user_id)

    if not conversation:
        raise ValueError("Conversation not found.")

    content_type = conversation.get("content_type", "").strip().lower()

    if content_type not in ("research", "linkedin", "seo_blog"):
        raise ValueError(  f"Research Agent does not support content type: {content_type}"  )

    topic = state.get("topic") or conversation.get("topic", "")
    target_audience = (
        state.get("target_audience")
        or conversation.get("target_audience", "")
    )

    if not topic:
        raise ValueError("Research topic is required.")

    # Execute research
    research_data = research_topic(
        topic=topic,
        target_audience=target_audience,
        num_results=5,
        # Streams progress to the UI (stream_mode="custom").
        on_event=get_stream_writer(),
    )

    # The reviewer sees the whole report, not only the summary.
    report = format_research_report(research_data)

    # Persist structured research output
    saved_message = add_message(
        conversation_id=conversation_id,
        user_id=user_id,
        role="assistant",
        message_type="generated_content",
        content_type="research",
        content=research_data,
        agent_name="research_agent",
        metadata={
            "status": "draft",
            "version": 1,
            "content_text": report,
        },
    )

    message_id = saved_message["message_id"]

    logger.info( "Research output saved. Message ID: %s", message_id, )

    completed_agents = list(state.get("completed_agents", []))

    if "research_agent" not in completed_agents:
        completed_agents.append("research_agent")

    return {
        "current_agent": "research_agent",
        "topic": topic,
        "research_results": research_data.get("sources", []),
        "research_summary": research_data.get("research_summary", ""),
        "research_data": research_data,
        "current_content": report,
        "generated_content_message_id": saved_message["message_id"],
        "completed_agents": completed_agents,
        "messages": [ AIMessage(content=report)],
    }