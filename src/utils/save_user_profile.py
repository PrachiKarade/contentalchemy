
from pathlib import Path

from src.core.logger import setup_logger
from src.repositories.profile_repository import (
    ensure_indexes,
    upsert_profile,
)
from src.repositories.conversation_repository import get_conversation

logger = setup_logger("save_user_profile")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = PROJECT_ROOT / "inputs" / "user_profile.md"


def main() -> None:
    if not PROFILE_PATH.exists():
        raise FileNotFoundError( f"Markdown profile not found: {PROFILE_PATH}" )
    user_id = "usr_local_001" #input("Enter user_id: ").strip()
    conversation_id = "conv_d7c2eca703e7405691c134622eb1e3e9" #input( "Enter an existing LinkedIn conversation_id: " ).strip()

    if not user_id or not conversation_id:
        raise ValueError("Both IDs are required.")

    # Verify that the conversation exists and belongs to this user.
    conversation = get_conversation(conversation_id, user_id)

    if conversation is None:
        raise ValueError( "Conversation not found for this user." )

    if conversation.get("content_type") != "linkedin":
        raise ValueError(
            "A Markdown profile can only be saved "
            "for a LinkedIn conversation."
        )

    profile_markdown = PROFILE_PATH.read_text(encoding="utf-8")

    if not profile_markdown.strip():
        raise ValueError("The Markdown profile file is empty.")

    ensure_indexes()

    profile = upsert_profile(
        user_id=user_id,
        conversation_id=conversation_id,
        profile_markdown=profile_markdown,
    )

    print("Profile saved successfully.")
    print(f"User ID: {profile['user_id']}")
    print(f"Conversation ID: {profile['conversation_id']}")
    print(f"Markdown characters: {len(profile['profile_markdown'])}")


if __name__ == "__main__":
    main()
