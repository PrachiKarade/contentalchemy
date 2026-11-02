
from src.repositories.conversation_repository import create_conversation
from src.repositories.message_repository import (
    ensure_indexes,
    add_message,
    list_messages,
    count_messages,
)

USER_ID = "usr_local_001"


def main():
    ensure_indexes()

    # Create a test conversation.
    conversation = create_conversation(
        user_id=USER_ID,
        content_type="linkedin",
        title="AI Agents for .NET Developers",
        topic="AI Agents",
        target_audience=".NET developers",
    )

    conversation_id = conversation["conversation_id"]

    # Save the user's request.
    add_message(
        conversation_id=conversation_id,
        user_id=USER_ID,
        role="user",
        message_type="request",
        content_type="linkedin",
        content="Write a LinkedIn post explaining AI agents.",
    )

    # Save the agent's generated content.
    add_message(
        conversation_id=conversation_id,
        user_id=USER_ID,
        role="assistant",
        message_type="generated_content",
        content_type="linkedin",
        content={
            "hook": "AI agents are changing software development.",
            "post_body": "Here is how AI agents can help .NET developers...",
            "hashtags": ["#AI", "#DotNet"],
            "call_to_action": "What are you building with AI?",
        },
        agent_name="linkedin_writer",
    )

    # Save review feedback as a separate, auditable message.
    add_message(
        conversation_id=conversation_id,
        user_id=USER_ID,
        role="user",
        message_type = "review_feedback",
        content_type = "linkedin",
        content = "Make the opening more engaging.",
    )

    # Read the full conversation.
    messages = list_messages(
        conversation_id = conversation_id,
        user_id = USER_ID,
    )

    print(f"\nConversation: {conversation_id}")
    print(f"Message count: {count_messages(conversation_id, USER_ID)}")

    for message in messages:
        print(
            f"\nSequence: {message['sequence']}"
            f"\nRole: {message['role']}"
            f"\nType: {message['message_type']}"
            f"\nContent: {message['content']}"
        )


if __name__ == "__main__":
    main()
