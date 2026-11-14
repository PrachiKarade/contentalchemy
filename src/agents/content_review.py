
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import interrupt

from src.core.logger import setup_logger
from src.core.state import ContentState
from src.repositories.message_repository import update_message
from src.utils.quality_validation import evaluate_content_quality
from src.repositories.message_repository import (
    update_message,
    get_message,
)

logger = setup_logger("content_review")

# Content types that get a quality score.
SCORED_TYPES = {"linkedin", "blog", "seo_blog"}


def quality_from_state(state: ContentState) -> dict | None:
    """The quality score content_generator computed, in the shape the UI shows."""

    if state.get("quality_score") is None:
        return None

    return {
        "score": state["quality_score"],
        "grade": state.get("quality_grade", ""),
        "checks": state.get("quality_details", {}),
        "suggestions": state.get("quality_suggestions", []),
    }


def quality_from_result(result: dict) -> dict | None:
    """The quality score of one multi deliverable, in the shape the UI shows."""

    if result.get("quality_score") is None:
        return None

    return {
        "score": result["quality_score"],
        "grade": result.get("quality_grade", ""),
        "checks": result.get("quality_details", {}),
        "suggestions": result.get("quality_suggestions", []),
    }


def rescore(content: str, content_type: str, keywords: list[str] | None) -> dict | None:
    """Score an edited draft so the review shows the quality of what the user wrote."""

    try:
        return evaluate_content_quality(content=content, content_type=content_type, keywords=keywords)
    except ValueError:
        logger.exception("Could not score the edited %s content", content_type)
        return None


# ------------------------------------------------
# Content Review
# ------------------------------------------------

def content_review_node(state: ContentState) -> dict:
    content = state.get("current_content", "").strip()
    content_type = state.get("intent", "content")
    agent = state.get("current_agent", "content_generator")

    if not content:
        raise ValueError("There is no generated content to review.")

    scored = content_type in SCORED_TYPES

    decision = interrupt({
        "interaction_type": "content_review",
        "content_type": content_type,
        "agent": agent,
        "question": f"Please review your generated {content_type} content.",
        "content": content,
        "quality": quality_from_state(state) if scored else None,
        "options": ["approve", "edit", "reject"],
    })

    if not isinstance(decision, dict):
        raise ValueError("Review response must be a dictionary.")

    action = decision.get("action")
    edited_content = decision.get("edited_content", "")

    if not isinstance(action, str):
        raise ValueError("Review action must be a string.")

    action = action.strip().lower()

    if action not in {"approve", "edit", "reject"}:
        raise ValueError(f"Unsupported review action: {action}")

    if not isinstance(edited_content, str):
        raise ValueError("Edited content must be a string.")

    edited_content = edited_content.strip()

    if action == "edit" and not edited_content:
        raise ValueError("Edited content cannot be empty.")

    if action == "approve":
        final_content = content
        status = "approved"

    elif action == "edit":
        final_content = edited_content
        status = "edited"
    else:
        final_content = content
        status = "rejected"

    message_id = state.get("generated_content_message_id")
    conversation_id = state.get("conversation_id")
    user_id = state.get("user_id")

    if not message_id or not conversation_id or not user_id:
        raise ValueError("Missing generated message or conversation information.")

    metadata_updates = {
        "status": status,
        "content_text": final_content,
    }

    # An edited draft goes back to review with a fresh score.
    quality_updates = {}
    if action == "edit" and scored:
        quality = rescore(final_content, content_type, state.get("keywords"))
        if quality:
            quality_updates = {
                "quality_score": quality["score"],
                "quality_grade": quality["grade"],
                "quality_details": quality["checks"],
                "quality_suggestions": quality["suggestions"],
            }
            metadata_updates.update(
                quality_score=quality["score"],
                quality_grade=quality["grade"],
                quality_details=quality["checks"],
                quality_suggestions=quality["suggestions"],
            )

    updated = update_message(
        message_id=message_id,
        conversation_id=conversation_id,
        user_id=user_id,
        metadata_updates=metadata_updates,
    )

    if not updated:
        raise ValueError("Could not update the generated content.")

    logger.info(  "Review completed for message %s with status %s", message_id,  status, )

    return {
        **quality_updates,
        "current_content": final_content,
        "final_content": final_content if status == "approved" else "",
        "edited_content": edited_content if action == "edit" else "",
        "review_action": action,
        "approval_status": status,
        "human_interaction": {
            "interaction_type": "content_review",
            "agent": agent,
            "question": f"Review your generated {content_type} content.",
            "content": final_content,
            "status": "completed",
            "response": decision,
            "approved": status == "approved",
        },
        "messages": [
            HumanMessage(content=f"Review action: {action}"),
            AIMessage(content=f"Review status: {status}"),
        ],
    }


# ------------------------------------------------------
# Multi Content Review Node
# ------------------------------------------------------


def multi_content_review_node(state: ContentState) -> dict:
    """Review each explicitly requested non-image deliverable."""

    user_id = state.get("user_id")
    conversation_id = state.get("conversation_id")

    if not user_id or not conversation_id:
        raise ValueError("user_id and conversation_id are required.")

    requested_agents = state.get("requested_agents", [])
    results = dict(state.get("multi_agent_results", {}))

    keywords = state.get("keywords", [])

    for agent in requested_agents:

        # Image has its own image_review_node.
        if agent == "image":
            continue

        result = results.get(agent, {})

        # Review only generated drafts.
        if result.get("status") != "draft":
            continue

        content = result.get("content_text", "")

        if not content:
            logger.warning(  "Skipping %s review because content is empty.",  agent, )
            continue

        message_id = result.get("message_id")

        if not message_id:
            raise ValueError( f"Message ID is missing for {agent}." )

        logger.info("Starting multi-agent review for: %s", agent)

        # Ask the user to review the current deliverable.
        decision = interrupt({
            "interaction_type": "content_review",
            "content_type": agent,
            "deliverable": agent,
            "multi": True,
            "agent": f"{agent}_writer" if agent in {"blog", "linkedin"} else "content_strategist",
            "question": f"Please review your generated {agent} content.",
            "content": content,
            "quality": quality_from_result(result),
            "options": ["approve", "edit", "reject"],
        })

        if not isinstance(decision, dict):
            raise ValueError("Review response must be a dictionary.")

        action = decision.get("action")

        if action not in {"approve", "edit", "reject"}:
            raise ValueError( f"Invalid review action for {agent}: {action}"  )

        final_content = content

        if action == "edit":
            edited_content = decision.get("edited_content", "")

            if not isinstance(edited_content, str) or not edited_content.strip():
                raise ValueError(
                    f"Edited content cannot be empty for {agent}."
                )

            final_content = edited_content.strip()
            status = "approved"

        elif action == "approve":
            status = "approved"

        else:
            status = "rejected"

        # Prepare metadata.
        metadata_updates = {
            "status": status,
            "content_text": final_content,
        }

        # Rescore edited blog and LinkedIn content.
        quality_updates = {}

        content_type = result.get("content_type", agent)

        quality_result = None
        if action == "edit" and agent in {"blog", "linkedin"}:
            quality_result = rescore(
                final_content,
                content_type,
                keywords,
            )

        if quality_result:
            quality_updates = {
                "quality_score": quality_result["score"],
                "quality_grade": quality_result["grade"],
                "quality_details": quality_result["checks"],
                "quality_suggestions": quality_result["suggestions"],
            }

            metadata_updates.update(quality_updates)

        # Research and strategy share one MongoDB message.
        if agent in {"research", "strategy"}:

            message = get_message(message_id, user_id)

            if not message:
                raise ValueError(
                    f"Message not found for {agent}: {message_id}"
                )

            shared_content = dict(message.get("content") or {})

            content_key = (
                "research_report"
                if agent == "research"
                else "content_strategy"
            )

            shared_content[content_key] = final_content

            combined_text = (
                f"{shared_content.get('research_report', '')}"
                f"\n\n---\n\n"
                f"{shared_content.get('content_strategy', '')}"
            )

            updated = update_message(
                message_id=message_id,
                conversation_id=conversation_id,
                user_id=user_id,
                content=shared_content,
                metadata_updates={
                    f"{agent}_status": status,
                    "content_text": combined_text,
                },
            )

        else:
            # Blog and LinkedIn have separate MongoDB messages.
            updated = update_message(
                message_id=message_id,
                conversation_id=conversation_id,
                user_id=user_id,
                metadata_updates=metadata_updates,
            )

        if not updated:
            raise ValueError(
                f"Failed to update MongoDB message for {agent}."
            )

        # Update in-memory result.
        result.update({
            "content_text": final_content,
            "status": status,
            "review_action": action,
            **quality_updates,
        })

        results[agent] = result

        logger.info(
            "Multi-agent review completed for %s. Status: %s",
            agent,
            status,
        )

    # Mark the interaction as completed.
    return {
        "multi_agent_results": results,
        "multi_agent_status": "completed",
        "human_interaction": {
            "interaction_type": "content_review",
            "status": "completed",
            "approved": all(
                result.get("status") == "approved"
                for agent, result in results.items()
                if agent in requested_agents and agent != "image"
            ),
        },
        "current_agent": "multi_content_review",
        "messages": [
            AIMessage(
                content="Multi-agent content review completed."
            )
        ],
    }
