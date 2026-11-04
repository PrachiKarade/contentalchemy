
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import interrupt

from src.core.logger import setup_logger
from src.core.state import ContentState
from src.repositories.message_repository import update_message

logger = setup_logger("image_review")


def _update_image_message(
    state: ContentState,
    status: str,
    metadata_updates: dict,
) -> None:
    """Update the existing generated-image message in MongoDB."""

    message_id = state.get("generated_image_message_id")
    conversation_id = state.get("conversation_id")
    user_id = state.get("user_id")

    if not message_id or not conversation_id or not user_id:
        raise ValueError(
            "Image message ID, conversation ID, and user ID are required."
        )

    updated = update_message(
        message_id=message_id,
        conversation_id=conversation_id,
        user_id=user_id,
        status=status,
        metadata_updates=metadata_updates,
    )

    if not updated:
        raise RuntimeError(
            f"Could not update image message {message_id}."
        )


def image_review_node(state: ContentState) -> dict:
    """Pause for image review and process the user's decision."""

    image_path = state.get("image_path", "")
    agent = "image_generator"

    if not image_path:
        raise ValueError("There is no generated image to review.")

    decision = interrupt({
        "interaction_type": "image_review",
        "agent": agent,
        "question": "Please review your generated image.",
        "content": image_path,
        "image_prompt": state.get("image_prompt", ""),
        "options": ["approve", "edit", "regenerate", "reject"],
        "status": "pending",
    })

    if not isinstance(decision, dict):
        raise ValueError("Image review response must be a dictionary.")

    action = decision.get("action")

    if not isinstance(action, str):
        raise ValueError("Image review action must be a string.")

    action = action.strip().lower()

    if action not in {"approve", "edit", "regenerate", "reject"}:
        raise ValueError(f"Unsupported image review action: {action}")

    # 1. Edit the prompt and regenerate.
    if action == "edit":
        edited_prompt = decision.get("edited_prompt")

        if not isinstance(edited_prompt, str) or not edited_prompt.strip():
            raise ValueError("Edited image prompt cannot be empty.")

        edited_prompt = edited_prompt.strip()

        _update_image_message(
            state,
            status="pending",
            metadata_updates={
                "image_status": "pending",
                "image_prompt": edited_prompt,
            },
        )

        logger.info("Image prompt edit requested.")

        return {
            "image_prompt": edited_prompt,
            "image_status": "pending",
            "image_review_action": "edit",
            "human_interaction": {
                "interaction_type": "image_review",
                "agent": agent,
                "status": "completed",
                "response": decision,
                "approved": False,
            },
            "messages": [
                HumanMessage(content="User requested an image prompt edit."),
                AIMessage(
                    content="The image will be regenerated using the edited prompt."
                ),
            ],
        }

    # 2. Regenerate using the existing enhanced prompt.
    if action == "regenerate":
        _update_image_message(
            state,
            status="pending",
            metadata_updates={"image_status": "pending"},
        )

        logger.info("Image regeneration requested.")

        return {
            "image_status": "pending",
            "image_review_action": "regenerate",
            "human_interaction": {
                "interaction_type": "image_review",
                "agent": agent,
                "status": "completed",
                "response": decision,
                "approved": False,
            },
            "messages": [
                HumanMessage(content="User requested image regeneration."),
            ],
        }

    # 3. Reject the generated image.
    if action == "reject":
        _update_image_message(
            state,
            status="rejected",
            metadata_updates={"image_status": "rejected"},
        )

        logger.info("Image rejected: %s", image_path)

        return {
            "image_status": "rejected",
            "image_review_action": "reject",
            "final_content": "",
            "human_interaction": {
                "interaction_type": "image_review",
                "agent": agent,
                "question": "The generated image was rejected.",
                "content": image_path,
                "status": "completed",
                "response": decision,
                "approved": False,
            },
            "messages": [
                HumanMessage(content="Image review action: reject"),
                AIMessage(content="Image rejected."),
            ],
        }

    # 4. Approve the generated image.
    _update_image_message(
        state,
        status="approved",
        metadata_updates={"image_status": "approved"},
    )

    logger.info("Image approved: %s", image_path)

    return {
        "image_status": "approved",
        "image_review_action": "approve",
        "final_content": image_path,
        "human_interaction": {
            "interaction_type": "image_review",
            "agent": agent,
            "question": "The generated image has been approved.",
            "content": image_path,
            "status": "completed",
            "response": decision,
            "approved": True,
        },
        "messages": [
            HumanMessage(content="Image review action: approve"),
            AIMessage(content="Image approved."),
        ],
    }
