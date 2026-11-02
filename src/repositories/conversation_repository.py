
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pymongo.collection import Collection
from pymongo import ASCENDING, DESCENDING

from src.core.logger import setup_logger
from src.integrations.mongodb_client import get_database

logger = setup_logger("conversation_repository")

ContentType = Literal[
    "research",
    "seo_blog",
    "linkedin",
    "image",
    "strategy",
    "multi",
    "chat",
]

ConversationStatus = Literal[
    "active",
    "awaiting_approval",
    "completed",
    "failed",
    "archived",
]


def get_conversations_collection() -> Collection:
    """Return the conversations collection."""
    return get_database()["conversations"]


def ensure_indexes() -> None:
    """Create indexes required by conversation queries."""
    collection = get_conversations_collection()

    collection.create_index(
        [("conversation_id", ASCENDING)],
        unique=True,
        name="uq_conversation_id",
    )

    collection.create_index(
        [("thread_id", ASCENDING)],
        unique=True,
        name="uq_conversation_thread_id",
    )

    collection.create_index(
        [
            ("user_id", ASCENDING),
            ("updated_at", DESCENDING),
        ],
        name="ix_conversations_user_updated",
    )

    collection.create_index(
        [
            ("user_id", ASCENDING),
            ("status", ASCENDING),
            ("updated_at", DESCENDING),
        ],
        name="ix_conversations_user_status_updated",
    )


def create_conversation(
    user_id: str,
    content_type: ContentType,
    title: str,
    topic: str = "",
    target_audience: str = "",
    tone: str = "Professional",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a conversation for any supported content type."""

    if not user_id or not user_id.strip():
        raise ValueError("user_id cannot be empty")

    if not title or not title.strip():
        raise ValueError("title cannot be empty")

    allowed_types = {
        "research",
        "seo_blog",
        "linkedin",
        "image",
        "strategy",
        "multi",
        "chat",
    }

    if content_type not in allowed_types:
        raise ValueError(f"Unsupported content_type: {content_type}")

    conversation_id = f"conv_{uuid4().hex}"
    now = datetime.now(timezone.utc)

    conversation = {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "thread_id": conversation_id,
        "content_type": content_type,
        "title": title.strip(),
        "topic": topic.strip(),
        "target_audience": target_audience.strip(),
        "tone": tone.strip(),
        "status": "active",
        "metadata": metadata or {},
        "created_at": now,
        "updated_at": now,
    }

    get_conversations_collection().insert_one(conversation)

    logger.info(
        "Created conversation %s for user %s (%s)",
        conversation_id,
        user_id,
        content_type,
    )

    # Return a plain dictionary without MongoDB's internal _id.
    conversation.pop("_id", None)
    return conversation


def get_conversation(
    conversation_id: str,
    user_id: str,
) -> dict[str, Any] | None:
    """Get one conversation belonging to the specified user."""

    return get_conversations_collection().find_one(
        {
            "conversation_id": conversation_id,
            "user_id": user_id,
        },
        {"_id": 0},
    )


def list_conversations(
    user_id: str,
    limit: int = 20,
    status: ConversationStatus | None = None,
) -> list[dict[str, Any]]:
    """List a user's conversations, newest updated first."""

    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")

    query: dict[str, Any] = {"user_id": user_id}

    if status is not None:
        query["status"] = status

    cursor = (
        get_conversations_collection()
        .find(query, {"_id": 0})
        .sort("updated_at", DESCENDING)
        .limit(limit)
    )

    return list(cursor)


def update_conversation(
    conversation_id: str,
    user_id: str,
    *,
    title: str | None = None,
    status: ConversationStatus | None = None,
    topic: str | None = None,
    target_audience: str | None = None,
    tone: str | None = None,
    metadata_updates: dict[str, Any] | None = None,
) -> bool:
    """Update selected fields on a conversation."""

    allowed_statuses = {
        "active",
        "awaiting_approval",
        "completed",
        "failed",
        "archived",
    }

    if status is not None and status not in allowed_statuses:
        raise ValueError(f"Unsupported status: {status}")

    updates: dict[str, Any] = {}

    if title is not None:
        if not title.strip():
            raise ValueError("title cannot be empty")
        updates["title"] = title.strip()

    if status is not None:
        updates["status"] = status

    if topic is not None:
        updates["topic"] = topic.strip()

    if target_audience is not None:
        updates["target_audience"] = target_audience.strip()

    if tone is not None:
        updates["tone"] = tone.strip()

    if metadata_updates:
        # Update individual metadata keys rather than replacing the
        # entire metadata object.
        for key, value in metadata_updates.items():
            if not key.strip():
                raise ValueError("Metadata keys cannot be empty")
            updates[f"metadata.{key}"] = value

    if not updates:
        return get_conversation(conversation_id, user_id) is not None

    updates["updated_at"] = datetime.now(timezone.utc)

    result = get_conversations_collection().update_one(
        {
            "conversation_id": conversation_id,
            "user_id": user_id,
        },
        {"$set": updates},
    )

    if result.matched_count:
        logger.info("Updated conversation %s", conversation_id)

    return result.matched_count == 1


def delete_conversation(
    conversation_id: str,
    user_id: str,
) -> bool:
    """Delete a conversation document owned by the specified user.

    This deletes only the conversation record. Associated messages
    and LangGraph checkpoints must be handled separately.
    """

    result = get_conversations_collection().delete_one(
        {
            "conversation_id": conversation_id,
            "user_id": user_id,
        }
    )

    if result.deleted_count:
        logger.info("Deleted conversation %s", conversation_id)

    return result.deleted_count == 1
