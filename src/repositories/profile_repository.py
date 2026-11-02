
from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING
from pymongo.collection import Collection

from src.core.logger import setup_logger
from src.integrations.mongodb_client import get_database

logger = setup_logger("profile_repository")


def get_profiles_collection() -> Collection:
    return get_database()["user_profiles"]


def ensure_indexes() -> None:
    collection = get_profiles_collection()

    # Remove the old index that allowed only one profile per user.
    existing_indexes = collection.index_information()

    if "uq_profile_user_id" in existing_indexes:
        collection.drop_index("uq_profile_user_id")

    # Each user can have one profile for each conversation.
    collection.create_index(
        [
            ("user_id", ASCENDING),
            ("conversation_id", ASCENDING),
        ],
        unique=True,
        name="uq_profile_user_conversation",
    )


def upsert_profile(
    user_id: str,
    conversation_id: str,
    profile_markdown: str,
) -> dict[str, Any]:
    """Create or update the Markdown profile for a conversation."""

    if not user_id or not user_id.strip():
        raise ValueError("user_id cannot be empty")

    if not conversation_id or not conversation_id.strip():
        raise ValueError("conversation_id cannot be empty")

    if not profile_markdown or not profile_markdown.strip():
        raise ValueError("profile_markdown cannot be empty")

    collection = get_profiles_collection()
    now = datetime.now(timezone.utc)

    collection.update_one(
        {
            "user_id": user_id,
            "conversation_id": conversation_id,
        },
        {
            "$setOnInsert": {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "created_at": now,
            },
            "$set": {
                "profile_markdown": profile_markdown,
                "updated_at": now,
            },
        },
        upsert=True,
    )

    profile = get_profile(user_id, conversation_id)

    if profile is None:
        raise RuntimeError("Profile could not be retrieved after saving")

    logger.info(
        "Profile saved for user %s, conversation %s",
        user_id,
        conversation_id,
    )

    return profile


def get_profile(
    user_id: str,
    conversation_id: str,
) -> dict[str, Any] | None:
    """Retrieve a profile for a specific user and conversation."""

    if not user_id or not user_id.strip():
        raise ValueError("user_id cannot be empty")

    if not conversation_id or not conversation_id.strip():
        raise ValueError("conversation_id cannot be empty")

    return get_profiles_collection().find_one(
        {
            "user_id": user_id,
            "conversation_id": conversation_id,
        },
        {"_id": 0},
    )


def delete_profile(
    user_id: str,
    conversation_id: str,
) -> bool:
    """Delete only the profile belonging to this conversation."""

    result = get_profiles_collection().delete_one(
        {
            "user_id": user_id,
            "conversation_id": conversation_id,
        }
    )

    if result.deleted_count:
        logger.info(
            "Profile deleted for user %s, conversation %s",
            user_id,
            conversation_id,
        )

    return result.deleted_count == 1
