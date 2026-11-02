
from datetime import datetime, timezone
from typing import Any

from pymongo.collection import Collection

from src.core.logger import setup_logger
from src.integrations.mongodb_client import get_database

logger = setup_logger("user_repository")


def get_users_collection() -> Collection:
    return get_database()["users"]


def create_user(
    user_id: str,
    username: str,
    auth_provider: str = "local",
    auth_subject: str | None = None,
) -> dict[str, Any]:
    if not user_id.strip():
        raise ValueError("user_id cannot be empty")

    if not username.strip():
        raise ValueError("username cannot be empty")

    subject = auth_subject or user_id
    now = datetime.now(timezone.utc)

    collection = get_users_collection()

    collection.update_one(
        {
            "auth_provider": auth_provider,
            "auth_subject": subject,
        },
        {
            "$setOnInsert": {
                "user_id": user_id,
                "auth_provider": auth_provider,
                "auth_subject": subject,
                "created_at": now,
                "is_active": True,
            },
            "$set": {
                "username": username.strip(),
            },
        },
        upsert=True,
    )

    user = collection.find_one(
        {
            "auth_provider": auth_provider,
            "auth_subject": subject,
        },
        {"_id": 0},
    )

    if user is None:
        raise RuntimeError("User could not be retrieved after saving")

    logger.info("User saved: %s", user["user_id"])
    return user


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    return get_users_collection().find_one(
        {"user_id": user_id},
        {"_id": 0},
    )


def update_username(
    user_id: str,
    username: str,
) -> bool:
    if not username.strip():
        raise ValueError("username cannot be empty")

    result = get_users_collection().update_one(
        {"user_id": user_id},
        {
            "$set": {
                "username": username.strip(),
            }
        },
    )

    return result.matched_count == 1
