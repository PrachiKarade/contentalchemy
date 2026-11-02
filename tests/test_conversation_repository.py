
from src.repositories.conversation_repository import (
    ensure_indexes,
    create_conversation,
    get_conversation,
    list_conversations,
    update_conversation,
)

USER_ID = "usr_local_001"


def main():
    # Create the required indexes.
    ensure_indexes()
    print("Conversation indexes ready.")

    # Create a LinkedIn content session.
    conversation = create_conversation(
        user_id=USER_ID,
        content_type="linkedin",
        title="AI Agents for .NET Developers",
        topic="AI Agents",
        target_audience=".NET developers",
        tone="Professional",
        metadata={
            "platform": "LinkedIn",
            "requested_by": "user",
        },
    )

    conversation_id = conversation["conversation_id"]
    print("Created:", conversation_id)

    # Retrieve the conversation.
    saved = get_conversation(conversation_id, USER_ID)
    print("Retrieved:", saved["title"])
    print("Content type:", saved["content_type"])
    print("Thread ID:", saved["thread_id"])

    # Update the status when the draft awaits human review.
    updated = update_conversation(
        conversation_id,
        USER_ID,
        status="awaiting_approval",
        metadata_updates={"draft_version": 1},
    )
    print("Updated:", updated)

    # List recent conversations for this user.
    conversations = list_conversations(USER_ID, limit=10)

    print("\nUser conversations:")
    for item in conversations:
        print(
            f"- {item['title']} | "
            f"{item['content_type']} | "
            f"{item['status']}"
        )


if __name__ == "__main__":
    main()
