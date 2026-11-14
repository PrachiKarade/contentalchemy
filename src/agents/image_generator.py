
from langgraph.config import get_stream_writer

from src.core.logger import setup_logger
from src.core.state import ContentState
from src.integrations.openai_client import generate_text
from src.integrations.image_clients import generate_image
from src.prompts.image_generator_prompt import IMAGE_PROMPT_SYSTEM
from src.repositories.message_repository import add_message, update_message
from src.integrations.providers.images.provider_errors import (
    ImageProviderError,
    InsufficientCreditsError,
)

logger = setup_logger("image_generator")


IMAGE_SIZE_MAP = {
    "square": "1024x1024",
    "portrait": "1024x1792",
    "landscape": "1792x1024",
}

REQUIRED_IMAGE_FIELDS = {
    "image_purpose": "What will you use this image for?",
    "image_visual_style": "What visual style would you like?",
    "image_orientation": "Which image orientation do you prefer?",
    "image_quality": "Which image quality do you prefer?",
}


def _get_image_preferences(state: ContentState) -> dict:
    """The preferences collected by the image_preferences nodes."""

    missing = [field for field in REQUIRED_IMAGE_FIELDS if not state.get(field)]
    if missing:
        raise ValueError(f"Missing image preferences: {', '.join(missing)}")

    return {field: state[field] for field in REQUIRED_IMAGE_FIELDS}


def multi_image_request(state: ContentState) -> str:
    """The image request inside a multi-deliverable request, focused on its topic."""

    topic = (state.get("topic") or "").strip()
    user_request = (state.get("user_request") or "").strip()

    if not topic:
        return user_request

    return (
        f"An image about: {topic}\n\n"
        f"It accompanies other content from this request (create only the image):\n{user_request}"
    )


def _build_prompt_input(user_request: str, preferences: dict) -> str:
    return f"""
User's original image request:
{user_request}

Image purpose:
{preferences["image_purpose"]}

Visual style:
{preferences["image_visual_style"]}

Orientation:
{preferences["image_orientation"]}

Image quality:
{preferences["image_quality"]}

Create a detailed image-generation prompt that preserves the user's
original intent and incorporates these preferences.
"""


def _save_image_message(
    state: ContentState,
    image_result: dict,
    enhanced_prompt: str,
    preferences: dict,
    generation_count: int,
) -> str:
    """Create or update the MongoDB message for this generated image."""

    conversation_id = state.get("conversation_id")
    user_id = state.get("user_id")

    if not conversation_id or not user_id:
        raise ValueError(
            "conversation_id and user_id are required for image persistence."
        )

    metadata = {
        "image_path": image_result["image_path"],
        "image_url": image_result["image_url"],
        "image_prompt": enhanced_prompt,
        "image_purpose": preferences["image_purpose"],
        "image_visual_style": preferences["image_visual_style"],
        "image_orientation": preferences["image_orientation"],
        "image_quality": preferences["image_quality"],
        "image_status": "generated",
        "image_generation_count": generation_count,
        "revised_prompt": image_result.get("revised_prompt"),
    }

    existing_message_id = state.get("generated_image_message_id")

    if existing_message_id:
        updated = update_message(
            message_id=existing_message_id,
            conversation_id=conversation_id,
            user_id=user_id,
            content=image_result["image_path"],
            status="generated",
            metadata_updates=metadata,
        )

        if not updated:
            raise RuntimeError(
                "Could not update the existing generated-image message."
            )

        return existing_message_id

    message = add_message(
        conversation_id=conversation_id,
        user_id=user_id,
        role="assistant",
        message_type="generated_image",
        content_type="image",
        content=image_result["image_path"],
        agent_name="image_generator",
        metadata=metadata,
    )

    return message["message_id"]


# ------------------------------
# Workflow Node : Image Generation
# ------------------------------

def image_generator_node(state: ContentState) -> dict:
    """Enhance the prompt, generate the image and persist it.

    Streams status events so the chat can show what is happening during the
    slow steps (prompt enhancement and DALL-E generation).
    """

    status = get_stream_writer()

    try:
        review_action = state.get("image_review_action", "")

        # Initial generation of a multi request: the request also asks for other
        # deliverables, so focus the image on the topic.
        if review_action not in {"edit", "regenerate"} and state.get("intent") == "multi":
            user_request = multi_image_request(state)

        # Initial generation: use the original user request.
        elif review_action not in {"edit", "regenerate"}:
            user_request = (
                state.get("user_request")
                or state.get("image_prompt")
                or ""
            ).strip()

        # Edit: image_prompt contains the user's edited prompt.
        elif review_action == "edit":
            user_request = (state.get("image_prompt") or "").strip()

        # Regenerate: reuse the already-enhanced prompt.
        else:
            user_request = (state.get("image_prompt") or "").strip()

        if not user_request:
            raise ValueError("The image prompt cannot be empty.")

        preferences = _get_image_preferences(state)

        orientation = preferences["image_orientation"].lower()
        quality = preferences["image_quality"].lower()

        if orientation not in IMAGE_SIZE_MAP:
            raise ValueError(
                "Image orientation must be square, portrait, or landscape."
            )

        if quality not in {"standard", "hd"}:
            raise ValueError("Image quality must be standard or hd.")

        # Reuse the enhanced prompt for regeneration.
        if review_action == "regenerate":
            enhanced_prompt = user_request
        else:
            status({"event": "status", "text": "Crafting a detailed image prompt..."})
            prompt_input = _build_prompt_input(
                user_request=user_request,
                preferences=preferences,
            )

            enhanced_prompt = generate_text(
                query=prompt_input,
                system_prompt=IMAGE_PROMPT_SYSTEM,
                max_output_tokens=500,
            )

        if not enhanced_prompt:
            raise RuntimeError("Prompt enhancement returned an empty prompt.")

        conversation_id = state.get("conversation_id")
        user_id = state.get("user_id")

        if not conversation_id or not user_id:
            raise ValueError(
                "conversation_id and user_id are required for image generation."
            )

        status({"event": "status", "text": "Generating your image (this can take up to a minute)..."})
        image_result = generate_image(
            prompt=enhanced_prompt,
            conversation_id=conversation_id,
            quality=quality,
            size=IMAGE_SIZE_MAP[orientation],
            style=state.get("image_style", "natural"),
        )

        generation_count = state.get("image_generation_count", 0) + 1

        status({"event": "status", "text": "Saving your image..."})

        # Persist the image. Regeneration updates the existing message.
        message_id = _save_image_message(
            state=state,
            image_result=image_result,
            enhanced_prompt=enhanced_prompt,
            preferences=preferences,
            generation_count=generation_count,
        )

        logger.info(
            "Generated image for conversation %s",
            conversation_id,
        )

        return {
            **preferences,
            "image_prompt": enhanced_prompt,
            "image_path": image_result["image_path"],
            "image_url": image_result["image_url"],
            "image_status": "generated",
            "image_review_action": "",
            "image_error": "",
            "image_generation_count": generation_count,
            "generated_image_message_id": message_id,
            "current_agent": "image_generator",
            "current_content": image_result["image_path"],
            "human_interaction": {
                "interaction_type": "image_review",
                "agent": "image_generator",
                "question": "Please review your generated image.",
                "content": image_result["image_path"],
                "options": [
                    "approve",
                    "edit",
                    "regenerate",
                    "reject",
                ],
                "status": "pending",
            },
        }

    except InsufficientCreditsError as exc:
        logger.warning("Image generation stopped: %s", exc)

        error_message = (
            "Image generation is unavailable because the configured "
            "image provider has insufficient credits. "
            "Please try again later."
        )

        status({
            "event": "status",
            "text": error_message,
        })

        return {
            "image_status": "failed",
            "image_error": error_message,
            "human_interaction": None,
            "current_agent": "image_generator",
            "current_content": error_message,
            "errors": [error_message],
        }

    except ImageProviderError as exc:
        logger.warning("Image provider failed: %s", exc)

        error_message = (
            "Image generation is currently unavailable. "
            "Please try again later."
        )

        status({
            "event": "status",
            "text": error_message,
        })

        return {
              "image_status": "failed",
             "image_error": error_message,
             "human_interaction": None,
             "current_agent": "image_generator",
             "current_content": error_message,
             "errors": [error_message],
        }

    except Exception:
        logger.exception("Image generation node failed.")
        raise
