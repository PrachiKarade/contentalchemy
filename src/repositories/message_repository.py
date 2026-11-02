
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pymongo import ASCENDING, ReturnDocument
from pymongo.collection import Collection

from src.core.logger import setup_logger
from src.integrations.mongodb_client import get_database

logger = setup_logger("message_repository")

MessageRole = Literal["user", "assistant", "system", "tool"]

ContentType = Literal[
    "research",
    "seo_blog",
    "linkedin",
    "image",
    "strategy",
    "multi",
    "chat",
]

VALID_ROLES = {"user", "assistant", "system", "tool"}

VALID_CONTENT_TYPES = {
    "research",
    "seo_blog",
    "linkedin",
    "image",
    "strategy",
    "multi",
    "chat",
}

#--------------------------------------------------------------
#  get messages collection
#--------------------------------------------------------------
def get_messages_collection() -> Collection:
    """Return the messages collection."""
    return get_database()["messages"]

#--------------------------------------------------------------
#  create indexes on messages collection
#--------------------------------------------------------------
def ensure_indexes() -> None:
    """Create indexes used by message queries."""
    collection = get_messages_collection()

    collection.create_index(
        [("message_id", ASCENDING)],
        unique=True,
        name="uq_message_id",
    )

    # The conversation_id + sequence index may already exist
    # from the database setup script.
    collection.create_index(
        [
            ("conversation_id", ASCENDING),
            ("sequence", ASCENDING),
        ],
        unique=True,
        name="uq_message_conversation_sequence",
    )

    collection.create_index(
        [
            ("conversation_id", ASCENDING),
            ("sequence", ASCENDING),
        ],
        name="ix_messages_conversation_created",
    )

#--------------------------------------------------------------
#  add new message
#--------------------------------------------------------------

def add_message(
    conversation_id: str,
    user_id: str,
    role: MessageRole,
    message_type: str,
    content_type: ContentType,
    content: Any,
    agent_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Append a message to a conversation.

    Supports text or structured content. For large files and images,
    store the artifact separately and save its path/reference here.
    """

    if not conversation_id.strip():
        raise ValueError("conversation_id cannot be empty")

    if not user_id.strip():
        raise ValueError("user_id cannot be empty")

    if role not in VALID_ROLES:
        raise ValueError(f"Unsupported role: {role}")

    if content_type not in VALID_CONTENT_TYPES:
        raise ValueError(f"Unsupported content_type: {content_type}")

    if not message_type.strip():
        raise ValueError("message_type cannot be empty")

    if content is None or content == "":
        raise ValueError("content cannot be empty")

    db = get_database()
    conversations = db["conversations"]
    messages = get_messages_collection()

    now = datetime.now(timezone.utc)

    # Atomically allocate the next sequence number for this conversation.
    # The user_id condition prevents writing to another user's conversation.
    conversation = conversations.find_one_and_update(
        {
            "conversation_id": conversation_id,
            "user_id": user_id,
        },
        {
            "$inc": {"last_message_sequence": 1},
            "$set": {"updated_at": now},
        },
        projection={
            "_id": 0,
            "conversation_id": 1,
            "last_message_sequence": 1,
        },
        return_document=ReturnDocument.AFTER,
    )

    if conversation is None:
        raise ValueError( "Conversation not found or does not belong to this user" )

    sequence = conversation["last_message_sequence"]

    message = {
        "message_id": f"msg_{uuid4().hex}",
        "conversation_id": conversation_id,
        "user_id": user_id,
        "sequence": sequence,
        "role": role,
        "message_type": message_type,
        "content_type": content_type,
        "content": content,
        "agent_name": agent_name,
        "metadata": metadata or {},
        "created_at": now,
    }

    messages.insert_one(message)

    logger.info(
        "Saved message %s in conversation %s (sequence=%s)",
        message["message_id"],
        conversation_id,
        sequence,
    )

    message.pop("_id", None)
    return message

#--------------------------------------------------------------
#  get  message
#--------------------------------------------------------------
def get_message(  message_id: str,  user_id: str,) -> dict[str, Any] | None:
    """Retrieve one message belonging to the specified user."""
    return get_messages_collection().find_one(
        {
            "message_id": message_id,
            "user_id": user_id,
        },
        {"_id": 0},
    )

#--------------------------------------------------------------
#  get list of messages
#--------------------------------------------------------------
def list_messages(
    conversation_id: str,
    user_id: str,
    limit: int = 100,
    before_sequence: int | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve messages in chronological order.

    Use before_sequence for pagination. For example, if the oldest
    visible message has sequence 21, pass before_sequence=21 to
    retrieve earlier messages.
    """

    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")

    # Verify ownership before returning conversation messages.
    conversation = get_database()["conversations"].find_one(
        {
            "conversation_id": conversation_id,
            "user_id": user_id,
        },
        {"_id": 1},
    )

    if conversation is None:
        raise ValueError( "Conversation not found or does not belong to this user")

    query: dict[str, Any] = {
        "conversation_id": conversation_id,
        "user_id": user_id,
    }

    if before_sequence is not None:
        query["sequence"] = {"$lt": before_sequence}

    # Fetch newest messages first for efficient pagination, then
    # reverse them so the caller receives chronological order.
    documents = list(
        get_messages_collection()
        .find(query, {"_id": 0})
        .sort("sequence", -1)
        .limit(limit)
    )

    return list(reversed(documents))

#--------------------------------------------------------------
#  list messages of one type across conversations
#--------------------------------------------------------------
def list_user_messages_by_type(
    user_id: str,
    message_type: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Retrieve a user's messages of one type from all conversations, newest first."""

    if not 1 <= limit <= 500:
        raise ValueError("limit must be between 1 and 500")

    return list(
        get_messages_collection()
        .find({"user_id": user_id, "message_type": message_type}, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
    )

#--------------------------------------------------------------
#  count message
#--------------------------------------------------------------
def count_messages(  conversation_id: str,  user_id: str,) -> int:
    """Count messages in a conversation owned by the user."""
    conversation = get_database()["conversations"].find_one(
        {
            "conversation_id": conversation_id,
            "user_id": user_id,
        },
        {"_id": 1},
    )

    if conversation is None:
        raise ValueError( "Conversation not found or does not belong to this user"  )

    return get_messages_collection().count_documents(
        {
            "conversation_id": conversation_id,
            "user_id": user_id,
        }
    )

#--------------------------------------------------------------
#  update message
#--------------------------------------------------------------

def update_message(
    message_id: str,
    conversation_id: str,
    user_id: str,
    *,
    content: Any | None = None,
    status: str | None = None,
    metadata_updates: dict[str, Any] | None = None,
) -> bool:
    """Update an existing message belonging to the user's conversation."""

    updates: dict[str, Any] = {}

    if content is not None:
        if content == "":
            raise ValueError("content cannot be empty")
        updates["content"] = content

    if status is not None:
        updates["status"] = status

    if metadata_updates:
        for key, value in metadata_updates.items():
            if not key.strip():
                raise ValueError("Metadata keys cannot be empty")
            updates[f"metadata.{key}"] = value

    if not updates:
        return False

    updates["updated_at"] = datetime.now(timezone.utc)

    result = get_messages_collection().update_one(
        {
            "message_id": message_id,
            "conversation_id": conversation_id,
            "user_id": user_id,
        },
        {"$set": updates},
    )

    return result.matched_count == 1