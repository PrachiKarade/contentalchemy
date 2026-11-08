from src.core.state import ContentState
from src.core.logger import setup_logger
from src.integrations.text_provider_manager import text_provider_manager
from src.prompts.content_strategist_prompt import (
    CONTENT_STRATEGIST_SYSTEM_PROMPT,
)

from langchain_core.messages import AIMessage

from src.repositories.conversation_repository import get_conversation
from src.repositories.message_repository import add_message
from src.core.brand_voice import build_brand_voice_context

logger = setup_logger("content_strategist")


def content_strategist_node(state: ContentState) -> dict:
    """
    Transforms structured research into:
    1. A readable research report.
    2. An actionable content strategy.

    Persists both outputs as a generated-content message.
    """

    user_id = state.get("user_id")
    conversation_id = state.get("conversation_id")

    try:
        logger.info("Content Strategist started.")

        # 1. Validate conversation
        if not user_id or not conversation_id:
            raise ValueError("user_id and conversation_id are required.")

        conversation = get_conversation(conversation_id, user_id)

        if not conversation:
            raise ValueError("Conversation not found.")

        # 2. Read research output from the previous node
        research_data = state.get("research_data", {})

        if not research_data:
            raise ValueError("Research data is missing.")

        topic = state.get("topic") or research_data.get("topic", "")

        research_summary = state.get("research_summary") or research_data.get(
            "research_summary", ""
        )

        target_audience = (
            state.get("target_audience")
            or conversation.get("target_audience", "")
        )

        tone = state.get("tone") or conversation.get("tone", "")

        objective = state.get("objective") or conversation.get("objective", "")

        # 3. Build optional brand voice context
        brand_voice_context = build_brand_voice_context(state)

        # 3. Prepare context for the Content Strategist
        research_context = f"""
TOPIC:
{topic}

RESEARCH DATA:
{research_data}

RESEARCH SUMMARY:
{research_summary}

TARGET AUDIENCE:
{target_audience or "General audience"}

TONE:
{tone or "Professional"}

CONTENT OBJECTIVE:
{objective or "Provide useful and informative content"}

BRAND VOICE PREFERENCES:
{brand_voice_context or "No specific brand voice preferences provided."}

"""

        # 4. Generate readable research report
        logger.info("Generating readable research report.")

        report_prompt = f"""
Using the research context below, generate the Research Report only.

Follow the Research Report requirements in your system instructions.

Preserve the research evidence and source references.
Do not invent facts or sources.

{research_context}
"""

        research_report = text_provider_manager.generate_text(
            query=report_prompt,
            system_prompt=CONTENT_STRATEGIST_SYSTEM_PROMPT,
            max_output_tokens=4000,
        )

        if not research_report or not research_report.strip():
            raise ValueError("Research report generation returned empty content.")

        # 5. Generate content strategy
        logger.info("Generating content strategy.")

        strategy_prompt = f"""
Using the research context and report below, generate the Content Strategy only.

Follow the Content Strategy requirements in your system instructions.
Do not generate a blog article or social media post.

RESEARCH CONTEXT:
{research_context}

RESEARCH REPORT:
{research_report}
"""

        content_strategy = text_provider_manager.generate_text(
            query=strategy_prompt,
            system_prompt=CONTENT_STRATEGIST_SYSTEM_PROMPT,
            max_output_tokens=3000,
        )

        if not content_strategy or not content_strategy.strip():
            raise ValueError("Content strategy generation returned empty content.")

        # 6. Prepare combined content for existing review node
        combined_content = f"""
{research_report.strip()}

---

{content_strategy.strip()}
"""

        # 7. Persist generated output
        saved_message = add_message(
            conversation_id=conversation_id,
            user_id=user_id,
            role="assistant",
            message_type="generated_content",
            content_type="research",
            content={
                "research_report": research_report,
                "content_strategy": content_strategy,
            },
            agent_name="content_strategist",
            metadata={
                "status": "draft",
                "version": 1,
                "content_text": combined_content,
            },
        )

        message_id = saved_message["message_id"]

        logger.info(
            "Content Strategist output saved. Message ID: %s",
            message_id,
        )

        # 8. Update completed agents
        completed_agents = list(state.get("completed_agents", []))

        if "content_strategist" not in completed_agents:
            completed_agents.append("content_strategist")

        # 9. Return updated state
        return {
            "research_report": research_report,
            "content_strategy": content_strategy,
            "current_content": combined_content,
            "current_agent": "content_strategist",
            "generated_content_message_id": message_id,
            "completed_agents": completed_agents,
            "messages": [AIMessage(content=combined_content)],
        }

    except Exception as e:
        logger.exception("Content Strategist failed.")

        return {
            "errors": [f"Content Strategist failed: {str(e)}"],
            "current_agent": "content_strategist",
        }