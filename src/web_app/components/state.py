
"""Session state shared by all pages.

messages      chat bubbles: {"role", "kind", "content", ...} where kind is "text",
              "question" (agent question with options), "answer", "draft", "image"
              (a generated image), "error" (the workflow failed) or "warning"
              (a step failed but the workflow went on)
conversation  the active conversation id and type ("chat" or a content type)
pending       the interrupt payload the workflow is paused on, if any
review        the draft (or image) shown in the Content tab and its review status
image_action  an image review decision waiting to be run by the chat page
"""

import re

import streamlit as st

from src.core.logger import setup_logger
from src.web_app.assistant import (
    REVIEW_LABELS,
    agent_intro,
    get_current_user,
    get_pending_payload,
    image_failed,
    load_conversation,
    submit_decision,
    ui_type,
    workflow_error,
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
    "image_action",
    "image_editing",
    "image_edit_prompt",
]

# Sidebar values for a new conversation: Auto content type and empty brand voice.
SIDEBAR_DEFAULTS = {"content_type": "auto", "tone": None, "audience": None, "audience_custom": "", "keywords": ""}

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

    # The picked agent introduces itself in the chat. Skip it while the workflow waits for an
    # answer or review, so the agent's open question stays the latest message.
    if st.session_state.get("pending") is None:
        name = get_current_user()["username"]
        st.session_state["messages"].append(
            {"role": "assistant", "kind": "text", "content": agent_intro(content_type, name)}
        )
    go_to("chat")


# Workflow results


def is_review(payload: dict | None) -> bool:
    return bool(payload) and payload.get("interaction_type") == "content_review"


def is_image_review(payload: dict | None) -> bool:
    return bool(payload) and payload.get("interaction_type") == "image_review"


def show_image_review(payload: dict, state: dict) -> None:
    """A generated image is waiting for approve / edit / regenerate / reject."""

    previous = st.session_state.get("review") or {}
    st.session_state["review"] = {
        "conversation_id": st.session_state["conversation_id"],
        "type": "image",
        "topic": state.get("topic") or previous.get("topic", ""),
        "content": payload["content"],
        "image_prompt": payload.get("image_prompt") or state.get("image_prompt", ""),
        "message_id": state.get("generated_image_message_id") or previous.get("message_id"),
        "status": "pending",
        "edited": previous.get("edited", False),
        "final_content": "",
    }
    st.session_state["messages"].append(
        {
            "role": "assistant",
            "kind": "image",
            "content": payload["content"],
            "image_prompt": st.session_state["review"]["image_prompt"],
        }
    )


def show_payload(payload: dict, state: dict, content_type: str) -> None:
    """Show what the paused workflow needs: a question in the chat, or a draft to review."""

    st.session_state["pending"] = payload

    if is_image_review(payload):
        show_image_review(payload, state)
        return

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


def queue_image_action(action: str) -> None:
    """Queue an image review decision; the chat page runs it with live progress."""

    edited_prompt = ""
    if action == "edit":
        edited_prompt = st.session_state.get("image_edit_prompt", "").strip()
        if not edited_prompt:
            st.session_state["review_error"] = "The image prompt cannot be empty."
            return

    st.session_state["image_action"] = {"action": action, "edited_prompt": edited_prompt}
    for key in ["image_editing", "image_edit_prompt", "review_error"]:
        st.session_state.pop(key, None)
    go_to("chat")


def start_image_edit() -> None:
    review = st.session_state["review"]
    st.session_state["image_editing"] = True
    st.session_state["image_edit_prompt"] = review.get("image_prompt", "")
    st.session_state.pop("review_error", None)


def cancel_image_edit() -> None:
    for key in ["image_editing", "image_edit_prompt", "review_error"]:
        st.session_state.pop(key, None)


def finish_image_review(action: str, payload: dict | None, state: dict) -> None:
    """Update the chat and Content tab after an image review decision ran."""

    review = st.session_state["review"]

    if payload is not None:
        # Edit / regenerate: a new image is waiting for review.
        if action == "edit":
            review["edited"] = True
        show_payload(payload, state, "image")
        return

    if image_failed(state):
        # The provider could not make a new image and the workflow has ended.
        st.session_state["pending"] = None
        st.session_state["review"] = None
        st.session_state["messages"].append({"role": "assistant", "kind": "error", "content": workflow_error(state)})
        st.toast("Image generation failed", icon=":material/error:")
        return

    if state.get("image_status") == "rejected":
        reset_session()
        st.toast("Image rejected. Starting a new conversation.", icon=":material/delete:")
        return

    st.session_state["pending"] = None
    review["status"] = "approved"
    review["final_content"] = state.get("final_content") or review["content"]
    st.session_state["dashboard_selected"] = review["conversation_id"]
    st.session_state["messages"].append(
        {
            "role": "assistant",
            "kind": "text",
            "content": "Approved! Download your image above. It is also in the **Content** tab and the **Content dashboard**.",
        }
    )
    st.toast("Image approved and ready to download", icon=":material/verified:")


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
        metadata = message.get("metadata", {})
        if message_type == "question":
            options = metadata.get("options", [])
            bubbles.append({"role": "assistant", "kind": "question", "content": message["content"], "options": options})
        elif message_type == "generated_image":
            bubbles.append(
                {
                    "role": "assistant",
                    "kind": "image",
                    "content": message["content"],
                    "image_prompt": metadata.get("image_prompt", ""),
                }
            )
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
        elif message_type == "error":
            bubbles.append({"role": "assistant", "kind": "error", "content": message["content"]})
        elif message_type == "final_content":
            text = (
                "Approved! Download your image above."
                if message.get("content_type") == "image"
                else "Approved! The final content is in the **Content** tab."
            )
            bubbles.append({"role": "assistant", "kind": "text", "content": text})
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

    if content_type == "image":
        open_image_conversation(conversation, messages)
        return

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


def open_image_conversation(conversation: dict, messages: list[dict]) -> None:
    """Restore an image conversation: its preference form or its latest image for review."""

    conversation_id = conversation["conversation_id"]
    images = [msg for msg in messages if msg.get("message_type") == "generated_image"]
    image = images[-1] if images else None

    if image:
        st.session_state["review"] = {
            "conversation_id": conversation_id,
            "type": "image",
            "topic": conversation.get("topic") or conversation["title"],
            "content": image["content"],
            "image_prompt": image.get("metadata", {}).get("image_prompt", ""),
            "message_id": image["message_id"],
            "status": REVIEW_STATUSES.get(conversation["status"], "pending"),
            "edited": any(msg.get("metadata", {}).get("review_action") == "edit" for msg in messages),
            "final_content": latest(messages, {"final_content"}),
        }

    try:
        payload = get_pending_payload(conversation_id)
    except Exception:
        logger.exception("Could not read the workflow state for %s", conversation_id)
        payload = None

    if payload is not None:
        st.session_state["pending"] = payload
        if is_image_review(payload) and st.session_state["review"]:
            st.session_state["review"]["content"] = payload["content"]
            st.session_state["review"]["image_prompt"] = payload.get("image_prompt", "")
    elif conversation["status"] == "awaiting_approval" and image:
        # Without the checkpoint the image can still be approved or rejected, not regenerated.
        st.session_state["pending"] = {
            "interaction_type": "image_review",
            "content": image["content"],
            "image_prompt": st.session_state["review"]["image_prompt"],
            "checkpoint_lost": True,
        }
    elif conversation["status"] in {"active", "failed"}:
        st.session_state["conversation_closed"] = True


# Titles


def make_title(body: str, fallback: str) -> str:
    """Use the first markdown heading as the title, otherwise the request text."""

    match = re.search(r"^#{1,3}\s+(.+)$", body, re.MULTILINE)
    title = match.group(1) if match else fallback
    title = title.strip().strip("*")
    return title if len(title) <= 70 else title[:67] + "..."
