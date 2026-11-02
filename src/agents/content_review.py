
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import interrupt

from src.core.logger import setup_logger
from src.core.state import ContentState
from src.repositories.message_repository import update_message

logger = setup_logger("content_review")

# ------------------------------------------------
# Content Review 
# ------------------------------------------------

def content_review_node(state: ContentState) -> dict:
    content = state.get("current_content", "").strip()
    content_type = state.get("intent", "content")
    agent = state.get("current_agent", "content_generator")

    if not content:
        raise ValueError("There is no generated content to review.")

    decision = interrupt({
        "interaction_type": "content_review",
        "content_type": content_type,
        "agent": agent,
        "question": f"Please review your generated {content_type} content.",
        "content": content,
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

    updated = update_message(
        message_id=message_id,
        conversation_id=conversation_id,
        user_id=user_id,
        metadata_updates={
            "status": status,
            "content_text": final_content,
        },
    )

    if not updated:
        raise ValueError("Could not update the generated content.")

    logger.info(  "Review completed for message %s with status %s", message_id,  status, )

    return {
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
