
"""Session state shared by all pages.

messages      chat bubbles: {"role", "kind", "content", ...} where kind is "text",
              "question" (agent question with options), "answer" or "draft"
conversation  the active conversation id and type ("chat" or a content type)
pending       the interrupt payload the workflow is paused on, if any
review        the draft shown in the Content tab and its review status
"""

import re

import streamlit as st

from src.core.logger import setup_logger
from src.web_app.assistant import (
    REVIEW_LABELS,
    get_current_user,
    get_pending_payload,
    load_conversation,
    submit_decision,
    ui_type,
)

logger = setup_logger("web_state")

# Cleared when a conversation ends or the user picks another content type.
CONVERSATION_KEYS = [
    "messages",
    "conversation_id",
    "conversation_type",
    "pending",
    "review",
    "review_editing",
    "review_error",
    "edit_draft",
    "conversation_closed",
]

# Sidebar values for a new conversation: Auto content type and empty brand voice.
SIDEBAR_DEFAULTS = {"content_type": "auto", "tone": None, "audience": "", "keywords": ""}

# Conversation status in MongoDB -> review status in the Content tab.
REVIEW_STATUSES = {
    "awaiting_approval": "pending",
    "completed": "approved",
    "archived": "rejected",
}


def init_state() -> None:
    """Create the per-user session state keys used across the app."""

    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("conversation_id", None)
    st.session_state.setdefault("conversation_type", None)
    st.session_state.setdefault("pending", None)
    st.session_state.setdefault("review", None)


def go_to(page: str) -> None:
    """Ask the app to switch page on the next run."""

    st.session_state["switch_to"] = page


def reset_conversation() -> None:
    """Clear the chat and draft but keep the sidebar inputs."""

    for key in CONVERSATION_KEYS:
        st.session_state.pop(key, None)
    # Answer pills and "Other" inputs are keyed by message position; stale values would preselect options.
    for key in [key for key in st.session_state if str(key).startswith(("answer_", "other_next"))]:
        st.session_state.pop(key, None)
    init_state()


def reset_session() -> None:
    """Start a new conversation: clear the chat, draft and sidebar inputs."""

    reset_conversation()
    # Applied by the sidebar before its widgets render. Removing the keys is not enough:
    # the browser would send the old selection back on the next run.
    st.session_state["sidebar_values"] = dict(SIDEBAR_DEFAULTS)
    go_to("chat")


def change_content_type() -> None:
    """A different content type means a different agent, so start over.

    Auto fits any conversation, so switching to it keeps the current one.
    """

    content_type = st.session_state.get("content_type")
    if content_type != "auto" and st.session_state.get("conversation_type") not in (None, content_type):
        reset_conversation()
    go_to("chat")


# Workflow results


def is_review(payload: dict | None) -> bool:
    return bool(payload) and payload.get("interaction_type") == "content_review"


def show_payload(payload: dict, state: dict, content_type: str) -> None:
    """Show what the paused workflow needs: a question in the chat, or a draft to review."""

    st.session_state["pending"] = payload

    if not is_review(payload):
        st.session_state["messages"].append(
            {"role": "assistant", "kind": "question", "content": payload["question"], "options": payload.get("options", [])}
        )
        return

    previous = st.session_state.get("review") or {}
    st.session_state["review"] = {
        "conversation_id": st.session_state["conversation_id"],
        "type": content_type,
        "topic": state.get("topic") or previous.get("topic", ""),
        "content": payload["content"],
        "status": "pending",
        "edited": previous.get("edited", False),
        "final_content": "",
    }
    st.session_state["messages"].append(
        {"role": "assistant", "kind": "draft", "content": payload["content"], "content_type": content_type}
    )


def decide(action: str) -> None:
    """Send approve / edit / reject to the content review agent."""

    review = st.session_state["review"]
    edited_content = st.session_state.get("edit_draft", "") if action == "edit" else ""

    if action == "edit" and not edited_content.strip():
        st.session_state["review_error"] = "The edited draft cannot be empty."
        return

    try:
        payload, state = submit_decision(
            get_current_user()["user_id"],
            review["conversation_id"],
            review["type"],
            review["content"],
            action,
            edited_content,
        )
    except Exception as error:
        logger.exception("Review failed")
        st.session_state["review_error"] = f"Could not save your review: {error}"
        return

    for key in ["review_editing", "review_error", "edit_draft"]:
        st.session_state.pop(key, None)
    st.session_state["messages"].append({"role": "user", "kind": "text", "content": REVIEW_LABELS[action]})

    if payload is not None:
        # The edited draft is back for review.
        review["edited"] = True
        show_payload(payload, state, review["type"])
        st.toast("Draft updated. Approve it to finish.", icon=":material/edit:")
        return

    if state["approval_status"] == "rejected":
        reset_session()
        st.toast("Draft rejected. Starting a new conversation.", icon=":material/delete:")
        return

    st.session_state["pending"] = None
    review["status"] = "approved"
    review["final_content"] = state["final_content"]
    st.session_state["dashboard_selected"] = review["conversation_id"]
    st.session_state["messages"].append(
        {
            "role": "assistant",
            "kind": "text",
            "content": "Approved! Your final content is in the **Content** tab and the **Content dashboard**.",
        }
    )
    st.toast("Approved and ready to download", icon=":material/verified:")


def start_edit() -> None:
    st.session_state["review_editing"] = True
    st.session_state["edit_draft"] = st.session_state["review"]["content"]
    st.session_state.pop("review_error", None)
    go_to("create")


def cancel_edit() -> None:
    for key in ["review_editing", "review_error", "edit_draft"]:
        st.session_state.pop(key, None)


# History


def message_text(message: dict) -> str:
    """Generated content is stored as structured data; its text is in the metadata."""

    content = message["content"]
    return message.get("metadata", {}).get("content_text") or (content if isinstance(content, str) else "")


def messages_from_history(messages: list[dict]) -> list[dict]:
    """Turn stored messages into chat bubbles."""

    bubbles = []
    for message in messages:
        message_type = message.get("message_type")
        if message_type == "question":
            options = message.get("metadata", {}).get("options", [])
            bubbles.append({"role": "assistant", "kind": "question", "content": message["content"], "options": options})
        elif message_type in {"generated_content", "draft"}:
            bubbles.append(
                {
                    "role": "assistant",
                    "kind": "draft",
                    "content": message_text(message),
                    "content_type": ui_type(message["content_type"]),
                }
            )
        elif message_type == "answer":
            bubbles.append({"role": "user", "kind": "answer", "content": message["content"]})
        elif message_type == "final_content":
            bubbles.append(
                {"role": "assistant", "kind": "text", "content": "Approved! The final content is in the **Content** tab."}
            )
        elif message["role"] in {"user", "assistant"} and isinstance(message["content"], str):
            bubbles.append({"role": message["role"], "kind": "text", "content": message["content"]})
    return bubbles


def latest(messages: list[dict], message_types: set[str]) -> str:
    matches = [message_text(msg) for msg in messages if msg.get("message_type") in message_types]
    return matches[-1] if matches else ""


def open_conversation(user_id: str, conversation_id: str) -> None:
    """Show a conversation from history in the chat window, and its draft in the Content tab."""

    try:
        conversation, messages = load_conversation(user_id, conversation_id)
    except Exception:
        logger.exception("Could not open conversation %s", conversation_id)
        st.toast("Could not open this conversation", icon=":material/error:")
        return

    reset_session()
    st.session_state["conversation_id"] = conversation_id
    # The content dashboard shows this conversation's approved content.
    st.session_state["dashboard_selected"] = conversation_id
    st.session_state["messages"] = messages_from_history(messages)

    if conversation["content_type"] == "chat":
        st.session_state["conversation_type"] = "chat"
        return

    content_type = ui_type(conversation["content_type"])
    st.session_state["conversation_type"] = content_type
    st.session_state["sidebar_values"].update(
        content_type=content_type,
        audience=conversation.get("target_audience", ""),
        keywords=", ".join(conversation.get("metadata", {}).get("keywords", [])),
    )
    if conversation.get("tone"):
        st.session_state["sidebar_values"]["tone"] = conversation["tone"]

    draft = latest(messages, {"generated_content", "draft"})
    if draft:
        st.session_state["review"] = {
            "conversation_id": conversation_id,
            "type": content_type,
            "topic": conversation.get("topic") or conversation["title"],
            "content": draft,
            "status": REVIEW_STATUSES.get(conversation["status"], "pending"),
            "edited": any(msg.get("metadata", {}).get("review_action") == "edit" for msg in messages),
            "final_content": latest(messages, {"final_content"}),
        }

    # Resume where the workflow paused, if its checkpoint survived.
    try:
        payload = get_pending_payload(conversation_id)
    except Exception:
        logger.exception("Could not read the workflow state for %s", conversation_id)
        payload = None

    if payload is not None:
        st.session_state["pending"] = payload
        if is_review(payload) and st.session_state["review"]:
            st.session_state["review"]["content"] = payload["content"]
    elif conversation["status"] == "awaiting_approval" and draft:
        # The draft can still be reviewed without the checkpoint.
        st.session_state["pending"] = {"interaction_type": "content_review", "content": draft}
    elif conversation["status"] in {"active", "failed"}:
        st.session_state["conversation_closed"] = True


# Titles


def make_title(body: str, fallback: str) -> str:
    """Use the first markdown heading as the title, otherwise the request text."""

    match = re.search(r"^#{1,3}\s+(.+)$", body, re.MULTILINE)
    title = match.group(1) if match else fallback
    title = title.strip().strip("*")
    return title if len(title) <= 70 else title[:67] + "..."
