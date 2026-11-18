
import secrets
import string
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import (
    HashingError,
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)
from pymongo import ASCENDING
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from src.core.logger import setup_logger
from src.integrations.mongodb_client import get_database

logger = setup_logger("user_repository")

password_hasher = PasswordHasher()

MIN_PASSWORD_LENGTH = 8
TEMPORARY_PASSWORD_LENGTH = 12
# No look-alike characters (0/O, 1/l/I) so a temporary password is easy to copy by hand.
TEMPORARY_PASSWORD_ALPHABET = "".join(
    char for char in string.ascii_letters + string.digits if char not in "0O1lI"
)


def validate_password(password: str) -> None:
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must contain at least {MIN_PASSWORD_LENGTH} characters")


def get_users_collection() -> Collection:
    return get_database()["users"]


def ensure_user_indexes() -> None:
    collection = get_users_collection()

    collection.create_index(
        [("email", ASCENDING)],
        unique=True,
        name="unique_user_email",
    )


def create_user(
    username: str,
    email: str,
    password: str,
) -> dict[str, Any]:
    username = username.strip()
    email = email.strip().lower()

    if not username:
        raise ValueError("username cannot be empty")

    if not email or "@" not in email:
        raise ValueError("A valid email address is required")

    validate_password(password)

    collection = get_users_collection()

    password_hash = password_hasher.hash(password)
    user_id = f"user_{uuid4().hex}"
    now = datetime.now(timezone.utc)

    user = {
        "user_id": user_id,
        "username": username,
        "email": email,
        "password_hash": password_hash,
        "auth_provider": "local",
        "auth_subject": email,
        "created_at": now,
        "is_active": True,
        "must_change_password": False,
    }

    try:
        collection.insert_one(user)
    except DuplicateKeyError:
        raise ValueError("An account with this email already exists")

    logger.info("User registered: %s", user_id)

    return get_user_by_id(user_id)


def get_user_by_email(email: str) -> dict[str, Any] | None:
    return get_users_collection().find_one(
        {"email": email.strip().lower()},
    )


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    return get_users_collection().find_one(
        {"user_id": user_id},
        {"_id": 0, "password_hash": 0},
    )


def verify_password(
    stored_hash: str,
    password: str,
) -> bool:
    try:
        return password_hasher.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def authenticate_user(
    email: str,
    password: str,
) -> dict[str, Any] | None:
    user = get_user_by_email(email)

    if not user or not user.get("is_active", False):
        return None

    if not verify_password(user["password_hash"], password):
        return None

    return get_user_by_id(user["user_id"])


def generate_temporary_password() -> str:
    return "".join(
        secrets.choice(TEMPORARY_PASSWORD_ALPHABET)
        for _ in range(TEMPORARY_PASSWORD_LENGTH)
    )


def reset_password_to_temporary(
    email: str,
    username: str,
) -> str | None:
    """Forgot password: replace the password with a random temporary one.

    The registered name must match the email (case-insensitive). Returns the temporary
    password, or None when no active account matches. The user must change it after
    logging in (must_change_password).
    """

    user = get_user_by_email(email)

    if not user or not user.get("is_active", False):
        return None

    if user.get("username", "").strip().casefold() != username.strip().casefold():
        return None

    temporary_password = generate_temporary_password()

    get_users_collection().update_one(
        {"user_id": user["user_id"]},
        {
            "$set": {
                "password_hash": password_hasher.hash(temporary_password),
                "must_change_password": True,
                "password_reset_at": datetime.now(timezone.utc),
            }
        },
    )

    logger.info("Temporary password issued: %s", user["user_id"])

    return temporary_password


def change_password(
    user_id: str,
    current_password: str,
    new_password: str,
) -> None:
    """Change the password after checking the current one. Raises ValueError with a user-facing message."""

    validate_password(new_password)

    if new_password == current_password:
        raise ValueError("The new password must be different from the current one")

    collection = get_users_collection()
    user = collection.find_one({"user_id": user_id})

    if not user or not user.get("is_active", False):
        raise ValueError("Account not found")

    if not verify_password(user["password_hash"], current_password):
        raise ValueError("The current password is incorrect")

    collection.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "password_hash": password_hasher.hash(new_password),
                "must_change_password": False,
                "password_changed_at": datetime.now(timezone.utc),
            }
        },
    )

    logger.info("Password changed: %s", user_id)


def update_username(
    user_id: str,
    username: str,
) -> bool:
    if not username.strip():
        raise ValueError("username cannot be empty")

    result = get_users_collection().update_one(
        {"user_id": user_id},
        {"$set": {"username": username.strip()}},
    )

    return result.matched_count == 1
