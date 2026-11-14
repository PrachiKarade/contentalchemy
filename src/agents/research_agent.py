
import json
import re
import time
from collections.abc import Callable

from src.integrations.serp_client import search_web
from src.integrations.text_provider_manager import text_provider_manager
from src.core.logger import setup_logger
from src.prompts.research_agent_prompt import get_research_agent_system_prompt

from langchain_core.messages import AIMessage
from langgraph.config import get_stream_writer

from src.core.state import ContentState
from src.repositories.conversation_repository import get_conversation
from src.repositories.message_repository import add_message

from src.guardrails.research_guardrails import validate_research_output
from src.guardrails.prompt_injection_guard import check_prompt_injection
from src.guardrails.grounding_guardrails import validate_research_grounding


logger = setup_logger("research_agent")

RESEARCH_SYSTEM_PROMPT = get_research_agent_system_prompt()


# ------------------------------------------------------------------
# Helper Methods
# ------------------------------------------------------------------

def log_injection_warning(text: str, location: str) -> None:
    """Log suspicious instruction patterns without blocking research."""

    result = check_prompt_injection(text)

    if result.is_suspicious:
        logger.warning(
            "Possible prompt injection detected in %s. Matched patterns: %s",
            location,
            result.matched_patterns,
        )


def inspect_search_result_text(value, location: str) -> None:
    """Inspect textual search-result content recursively."""

    if isinstance(value, dict):
        for key, item in value.items():

            # URLs are references, not instructions to the research model.
            if key.lower() in {"url", "link"}:
                continue

            inspect_search_result_text(
                item,
                f"{location}.{key}",
            )

    elif isinstance(value, list):
        for index, item in enumerate(value):
            inspect_search_result_text(
                item,
                f"{location}[{index}]",
            )

    elif isinstance(value, str):
        log_injection_warning(value, location)


# ------------------------------------------------------------------
# Research Function
# ------------------------------------------------------------------

def research_topic(
    topic: str,
    target_audience: str = "",
    num_results: int = 5,
    on_event: Callable[[dict], None] | None = None,
) -> dict:
    """
    Research a topic using web search and synthesize findings with an LLM.

    on_event receives progress events for the UI:
    {"event": "status", "text": "..."}
    """

    total_start = time.perf_counter()

    emit = on_event or (lambda event: None)

    logger.info(
        "Research agent initialized for topic: %s",
        topic,
    )

    if not topic or not topic.strip():
        raise ValueError("Research topic cannot be empty.")

    logger.info("Starting research for topic: %s", topic)

    # --------------------------------------------------------------
    # 1. Search the web
    # --------------------------------------------------------------

    emit({
        "event": "status",
        "text": "Searching the web for sources...",
    })

    search_start = time.perf_counter()

    search_results = search_web(topic, num_results)

    logger.info( "Research search results:\n%s", json.dumps(search_results, indent=2, ensure_ascii=False),)

    search_duration = time.perf_counter() - search_start

    logger.info(
        "Research search completed | Duration: %.2f seconds | Results: %d",
        search_duration,
        len(search_results or []),
    )

    if not search_results:
        raise RuntimeError(
            "No search results found for the given topic."
        )

    # --------------------------------------------------------------
    # 2. Inspect search results for prompt injection
    # --------------------------------------------------------------

    inspection_start = time.perf_counter()

    for index, search_result in enumerate(search_results):
        inspect_search_result_text(
            search_result,
            f"search_results[{index}]",
        )

    inspection_duration = time.perf_counter() - inspection_start

    logger.info(
        "Search result inspection completed | Duration: %.2f seconds",
        inspection_duration,
    )

    # --------------------------------------------------------------
    # 3. Prepare research context
    # --------------------------------------------------------------

    context_start = time.perf_counter()

    search_context = json.dumps(
        search_results,
        ensure_ascii=False,
        indent=2,
    )

    context_duration = time.perf_counter() - context_start

    logger.info(
        "Research context prepared | Duration: %.2f seconds | Characters: %d",
        context_duration,
        len(search_context),
    )

    query = f"""
Research topic: {topic}

Target audience: {target_audience or "General audience"}

Analyze the following web search results:

{search_context}

Extract useful findings and return the required JSON structure.
"""

    # --------------------------------------------------------------
    # 4. Synthesize research using the LLM
    # --------------------------------------------------------------

    emit({
        "event": "status",
        "text": f"Analyzing {len(search_results)} sources...",
    })

    llm_start = time.perf_counter()

    response = text_provider_manager.generate_text(
        query=query,
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        max_output_tokens=3000,
    )

    llm_duration = time.perf_counter() - llm_start

    logger.info(
        "Research LLM synthesis completed | Duration: %.2f seconds",
        llm_duration,
    )

    logger.info(
        "Research synthesis completed for topic: %s",
        topic,
    )

    # --------------------------------------------------------------
    # 5. Parse JSON response
    # --------------------------------------------------------------

    parsing_start = time.perf_counter()

    cleaned = re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        response.strip(),
        flags=re.IGNORECASE,
    ).strip()

    try:
        research_data = json.loads(cleaned)

    except json.JSONDecodeError as error:
        logger.exception("Research agent returned invalid JSON.")

        raise ValueError(
            "Research agent returned invalid JSON."
        ) from error

    parsing_duration = time.perf_counter() - parsing_start

    logger.info(
        "Research JSON parsing completed | Duration: %.4f seconds",
        parsing_duration,
    )

    # --------------------------------------------------------------
    # 6. Validate research output
    # --------------------------------------------------------------

    validation_start = time.perf_counter()

    try:
        research_data = validate_research_output(research_data)

    except Exception:
        logger.exception(
            "Research output failed guardrail validation."
        )
        raise

    validation_duration = time.perf_counter() - validation_start

    logger.info(
        "Research output validation completed | Duration: %.4f seconds",
        validation_duration,
    )

    # --------------------------------------------------------------
    # 7. Validate source grounding
    # --------------------------------------------------------------

    grounding_start = time.perf_counter()

    try:
        research_data = validate_research_grounding(
            research_data=research_data,
            search_results=search_results,
        )

    except Exception:
        logger.exception(
            "Research output failed grounding validation."
        )
        raise

    grounding_duration = time.perf_counter() - grounding_start

    logger.info(
        "Research grounding validation completed | Duration: %.4f seconds",
        grounding_duration,
    )

    # --------------------------------------------------------------
    # 8. Additional response structure validation
    # --------------------------------------------------------------

    if not isinstance(research_data["findings"], list):
        raise ValueError("Research findings must be a list.")

    if not isinstance(research_data["sources"], list):
        raise ValueError("Research sources must be a list.")

    if not isinstance(research_data["research_summary"], str):
        raise ValueError("Research summary must be a string.")

    logger.info(
        "Research completed for topic: %s",
        topic,
    )

    # --------------------------------------------------------------
    # 9. Log total research execution time
    # --------------------------------------------------------------

    total_duration = time.perf_counter() - total_start

    logger.info(
        "Research execution summary | "
        "Search: %.2fs | "
        "Inspection: %.2fs | "
        "Context: %.2fs | "
        "LLM: %.2fs | "
        "JSON parsing: %.4fs | "
        "Output validation: %.4fs | "
        "Grounding: %.4fs | "
        "Total: %.2fs",
        search_duration,
        inspection_duration,
        context_duration,
        llm_duration,
        parsing_duration,
        validation_duration,
        grounding_duration,
        total_duration,
    )

    return research_data


# ------------------------------------------------------------------
# Research Report Formatter
# ------------------------------------------------------------------

def format_research_report(research_data: dict) -> str:
    """
    Turn structured research into a Markdown report.

    The UI reads findings and sources back from these headings.
    Keep the existing heading structure.
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

    for index, finding in enumerate(
        research_data.get("findings", []),
        start=1,
    ):

        lines += [
            "",
            f"### {index}. {finding.get('claim', '').strip()}",
            "",
        ]

        if finding.get("explanation"):
            lines.append(finding["explanation"].strip())

        urls = [
            url
            for url in finding.get("source_urls", [])
            if url
        ]

        if urls:
            links = ", ".join(
                f"[{number}]({url})"
                for number, url in enumerate(urls, start=1)
            )

            lines += [
                "",
                f"*Sources: {links}*",
            ]

    lines += [
        "",
        "## Sources",
        "",
    ]

    for index, source in enumerate(
        research_data.get("sources", []),
        start=1,
    ):

        title = (
            source.get("title", "").strip()
            or source.get("url", "")
        )

        entry = (
            f"{index}. [{title}]({source.get('url', '')})"
        )

        if source.get("snippet"):
            entry += f" - {source['snippet'].strip()}"

        lines.append(entry)

    return "\n".join(lines).strip()


# ------------------------------------------------------------------
# LangGraph Research Agent Node
# ------------------------------------------------------------------

def research_agent_node(state: ContentState) -> dict:
    """Run research and persist the generated research content."""

    node_start = time.perf_counter()

    user_id = state.get("user_id")
    conversation_id = state.get("conversation_id")

    if not user_id or not conversation_id:
        raise ValueError(
            "user_id and conversation_id are required."
        )

    # --------------------------------------------------------------
    # 1. Retrieve conversation
    # --------------------------------------------------------------

    database_start = time.perf_counter()

    conversation = get_conversation(
        conversation_id,
        user_id,
    )

    conversation_lookup_duration = (
        time.perf_counter() - database_start
    )

    logger.info(
        "Research conversation lookup completed | Duration: %.4f seconds",
        conversation_lookup_duration,
    )

    if not conversation:
        raise ValueError("Conversation not found.")

    content_type = conversation.get(
        "content_type",
        "",
    ).strip().lower()

    if content_type not in (
        "research",
        "linkedin",
        "seo_blog",
        "multi",
    ):
        raise ValueError(
            f"Research Agent does not support content type: {content_type}"
        )

    topic = (
        state.get("topic")
        or conversation.get("topic", "")
    )

    target_audience = (
        state.get("target_audience")
        or conversation.get("target_audience", "")
    )

    if not topic:
        raise ValueError("Research topic is required.")

    # --------------------------------------------------------------
    # 2. Inspect user-provided topic
    # --------------------------------------------------------------

    log_injection_warning(
        topic,
        "research topic",
    )

    # --------------------------------------------------------------
    # 3. Execute research
    # --------------------------------------------------------------

    research_data = research_topic(
        topic=topic,
        target_audience=target_audience,
        num_results=5,
        on_event=get_stream_writer(),
    )

    # --------------------------------------------------------------
    # 4. Format research report
    # --------------------------------------------------------------

    formatting_start = time.perf_counter()

    report = format_research_report(research_data)

    formatting_duration = time.perf_counter() - formatting_start

    logger.info(
        "Research report formatting completed | Duration: %.4f seconds",
        formatting_duration,
    )

    # --------------------------------------------------------------
    # 5. Persist structured research output
    # --------------------------------------------------------------

    persistence_start = time.perf_counter()

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

    persistence_duration = time.perf_counter() - persistence_start

    logger.info(
        "Research MongoDB persistence completed | Duration: %.4f seconds",
        persistence_duration,
    )

    message_id = saved_message["message_id"]

    logger.info(
        "Research output saved. Message ID: %s",
        message_id,
    )

    # --------------------------------------------------------------
    # 6. Update completed agents
    # --------------------------------------------------------------

    completed_agents = list(
        state.get("completed_agents", [])
    )

    if "research_agent" not in completed_agents:
        completed_agents.append("research_agent")

    # --------------------------------------------------------------
    # 7. Log total node execution time
    # --------------------------------------------------------------

    node_duration = time.perf_counter() - node_start

    logger.info(
        "Research Agent node execution summary | "
        "Conversation lookup: %.4fs | "
        "Report formatting: %.4fs | "
        "MongoDB persistence: %.4fs | "
        "Total node time: %.2fs",
        conversation_lookup_duration,
        formatting_duration,
        persistence_duration,
        node_duration,
    )

    # --------------------------------------------------------------
    # 8. Return updated LangGraph state
    # --------------------------------------------------------------

    return {
        "current_agent": "research_agent",
        "topic": topic,
        "research_results": research_data.get("sources", []),
        "research_summary": research_data.get(
            "research_summary",
            "",
        ),
        "research_data": research_data,
        "current_content": report,
        "generated_content_message_id": message_id,
        "completed_agents": completed_agents,
        "messages": [
            AIMessage(content=report)
        ],
    }
