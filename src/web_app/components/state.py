
"""Session state shared by all pages.

messages      chat bubbles: {"role", "kind", "content", ...} where kind is "text",
              "question" (agent question with options), "answer", "draft", "image"
              (a generated image), "error" (the workflow failed) or "warning"
              (a step failed but the workflow went on)
conversation  the active conversation id and type ("chat" or a content type)
pending       the interrupt payload the workflow is paused on, if any
review        the draft (or image) shown in the Content tab and its review status
image_action  an image review decision waiting to be run by the chat page
multi         a multi-content conversation: its deliverables (one Content tab each), their
              status and the workflow progress. `review` then holds the deliverable under review.
"""

import re

import streamlit as st

from src.core.logger import setup_logger
from src.web_app.assistant import (
    CONTENT_TYPES,
    IMAGE_REVIEW_LABELS,
    MULTI_DELIVERABLES,
    REVIEW_LABELS,
    agent_intro,
    build_multi_decision,
    get_current_user,
    get_next_nodes,
    get_pending_payload,
    get_thread_state,
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
    "multi",
    "multi_job",
    "multi_failed_job",
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
    for key in [key for key in st.session_state if str(key).startswith(("answer_", "other_next", "multi_answer_", "multi_other_"))]:
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

    if content_type == "multi":
        show_multi_payload(payload, state)
        return

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
        "quality": payload.get("quality") or previous.get("quality"),
        # The content strategist's plan behind an SEO blog, shown in its own tab when present.
        "strategy": state.get("content_strategy") or previous.get("strategy", ""),
        "status": "pending",
        "edited": previous.get("edited", False),
        "final_content": "",
    }
    st.session_state["messages"].append(
        {"role": "assistant", "kind": "draft", "content": payload["content"], "content_type": content_type}
    )


def decide(action: str) -> None:
    """Send approve / edit / reject to the content review agent."""

    if is_multi():
        decide_multi(action)
        return

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

    if is_multi():
        # Multi-content runs the decision in the image's tab on the Content page.
        if queue_multi_review("image", action, edited_prompt=edited_prompt):
            for key in ["image_editing", "image_edit_prompt", "review_error"]:
                st.session_state.pop(key, None)
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


def latest_quality(messages: list[dict]) -> dict | None:
    """The quality score saved with the newest generated draft, if it has one."""

    drafts = [msg for msg in messages if msg.get("message_type") == "generated_content"]
    metadata = drafts[-1].get("metadata", {}) if drafts else {}
    if metadata.get("quality_score") is None:
        return None
    return {
        "score": metadata["quality_score"],
        "grade": metadata.get("quality_grade", ""),
        "checks": metadata.get("quality_details", {}),
        "suggestions": metadata.get("quality_suggestions", []),
    }


def latest_strategy(messages: list[dict]) -> str:
    """The content strategy the content strategist saved in this conversation, if it ran."""

    for message in reversed(messages):
        content = message.get("content")
        if isinstance(content, dict) and (content.get("content_strategy") or "").strip():
            return content["content_strategy"]
    return ""


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

    if content_type == "multi":
        open_multi_conversation(conversation, messages)
        return

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
            "quality": latest_quality(messages),
            "strategy": latest_strategy(messages),
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
            if payload.get("quality"):
                st.session_state["review"]["quality"] = payload["quality"]
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


# Multi-content
#
# st.session_state["multi"] = {
#     "conversation_id", "topic",
#     "requested": deliverables in the order the orchestrator runs them (one Content tab each),
#     "items": {deliverable: {"status", "content", "quality"?, "image_prompt"?, "edited", "error"?}},
#     "active": the deliverable under review, or None,
#     "tab": the deliverable whose tab is open; "tab_seq" changes whenever the app opens another tab,
#     "notice": the latest hand-off message, e.g. "LinkedIn post is drafted. Now working on SEO blog",
#     "qa": {deliverable: [[question, answer], ...]} the agent questions answered so far,
#     "question_seq": numbers the agent questions so each one gets fresh answer widgets,
#     "done": True once every deliverable is reviewed,
#     "progress": which workflow steps have finished (for the progress tracker),
# }
#
# Item status: waiting (not generated yet), draft (generated, reviewed later), pending (under review),
# approved, rejected or failed (the image provider failed).
#
# The multi-content workflow runs on the Content page one agent step at a time (assistant.advance_multi),
# so each step's progress and questions show in the tab of the content type it works on.
# st.session_state["multi_job"] is the work waiting to run there:
#     {"kind": "start", "prompt", "settings"}         a new request
#     {"kind": "answer", "response", "answer_text"}   the answer to an agent question
#     {"kind": "review", "deliverable", "decision"}   a review decision
#     {"kind": "continue"}                            the next agent step
# each with "owner": the deliverable whose tab shows the progress (None before the request is analyzed).

FINAL_ITEM_STATUSES = {"approved", "rejected", "failed"}

IMAGE_PREFERENCE_KEYS = ["image_purpose", "image_visual_style", "image_orientation", "image_quality"]

# Research and strategy are shared by every text deliverable; their progress shows in the first of these tabs.
SHARED_STEP_OWNERS = ["research", "strategy", "linkedin", "blog"]

IMAGE_NODES = {"image_request_analyzer", "image_preference_interaction", "image_generator", "image_review"}


def is_multi() -> bool:
    return st.session_state.get("conversation_type") == "multi"


def tab_label(deliverable: str) -> str:
    info = CONTENT_TYPES[deliverable]
    return f"{info['icon']} {info['label']}"


def type_label(deliverable: str | None) -> str:
    return CONTENT_TYPES[deliverable]["label"] if deliverable else "your request"


def select_tab(deliverable: str | None) -> None:
    """Open a deliverable's tab on the next run (the tabs are rebuilt when tab_seq changes)."""

    multi = st.session_state.get("multi")
    if multi is None or deliverable is None or multi.get("tab") == deliverable:
        return
    multi["tab"] = deliverable
    multi["tab_seq"] = multi.get("tab_seq", 0) + 1


def new_multi(conversation_id: str | None, topic: str = "") -> dict:
    return {
        "conversation_id": conversation_id,
        "topic": topic,
        "requested": [],
        "items": {},
        "active": None,
        "tab": None,
        "tab_seq": 0,
        "notice": "",
        "qa": {},
        "question_seq": 0,
        "done": False,
        "progress": {},
    }


def new_item() -> dict:
    return {"status": "waiting", "content": "", "edited": False}


def quality_of(result: dict) -> dict | None:
    if result.get("quality_score") is None:
        return None
    return {
        "score": result["quality_score"],
        "grade": result.get("quality_grade", ""),
        "checks": result.get("quality_details", {}),
        "suggestions": result.get("quality_suggestions", []),
    }


def sync_multi(state: dict) -> dict:
    """Update the deliverables and progress from the workflow state."""

    multi = st.session_state.get("multi") or new_multi(st.session_state.get("conversation_id"), state.get("topic", ""))
    multi["topic"] = state.get("topic") or multi["topic"]

    requested = state.get("requested_agents") or multi["requested"]
    multi["requested"] = [deliverable for deliverable in requested if deliverable in MULTI_DELIVERABLES]
    results = state.get("multi_agent_results") or {}

    for deliverable in multi["requested"]:
        item = multi["items"].setdefault(deliverable, new_item())
        result = results.get(deliverable) or {}
        status = result.get("status")
        # A decision made in this session is newer than a "draft" still in the state.
        decided = item["status"] in FINAL_ITEM_STATUSES

        if deliverable == "image":
            if status in FINAL_ITEM_STATUSES:
                item.update(
                    status=status,
                    content=result.get("content") or item["content"],
                    image_prompt=result.get("image_prompt") or item.get("image_prompt", ""),
                )
            elif state.get("image_status") == "failed":
                item.update(status="failed", error=state.get("image_error", ""))
            elif state.get("image_path") and not decided and item["status"] != "pending":
                item.update(status="draft", content=state["image_path"], image_prompt=state.get("image_prompt", ""))
            continue

        if status == "draft" and not decided and item["status"] != "pending":
            item.update(status="draft", content=result.get("content_text", ""), quality=quality_of(result))
        elif status in ("approved", "rejected"):
            item.update(
                status=status,
                content=result.get("content_text") or item["content"],
                quality=quality_of(result) or item.get("quality"),
                edited=item["edited"] or result.get("review_action") == "edit",
            )

    completed = state.get("completed_agents") or []
    multi["progress"] = {
        "profile": bool(state.get("linkedin_profile_answers")),
        "research": "research_agent" in completed,
        "strategy": "content_strategist" in completed,
        "image_prefs": all(state.get(key) for key in IMAGE_PREFERENCE_KEYS),
        "reviewed": state.get("current_agent") == "multi_content_review",
    }

    st.session_state["multi"] = multi
    return multi


def step_owner(node: str, state: dict, multi: dict, current: str | None) -> str | None:
    """The deliverable whose tab shows the progress of a workflow node."""

    requested = multi["requested"]
    if node == "query_handler":
        return None
    if node == "linkedin_profile_interaction":
        return "linkedin"
    if node in {"research_agent", "content_strategist"}:
        return next((deliverable for deliverable in SHARED_STEP_OWNERS if deliverable in requested), current)
    if node == "multi_content_generator":
        return state.get("next_agent") or current
    if node in IMAGE_NODES:
        return "image"
    # The orchestrator and the final review stay where the work is.
    return current


def question_owner(payload: dict) -> str | None:
    if payload.get("agent") == "image_generator":
        return "image"
    if payload.get("interaction_type") == "linkedin_profile_question":
        return "linkedin"
    multi = st.session_state.get("multi") or {}
    return multi.get("tab")


def set_multi_review(payload: dict) -> dict:
    """Make the deliverable in a review payload the one under review. Returns the review."""

    multi = st.session_state["multi"]
    image = is_image_review(payload)
    deliverable = "image" if image else payload.get("deliverable") or payload.get("content_type")
    item = multi["items"].setdefault(deliverable, new_item())
    if deliverable not in multi["requested"]:
        multi["requested"].append(deliverable)

    item.update(status="pending", content=payload["content"])
    if image:
        item["image_prompt"] = payload.get("image_prompt", "")
    elif payload.get("quality"):
        item["quality"] = payload["quality"]

    multi["active"] = deliverable
    st.session_state["review"] = {
        "conversation_id": multi["conversation_id"],
        "type": deliverable,
        "topic": multi["topic"],
        "content": payload["content"],
        "image_prompt": item.get("image_prompt", ""),
        "quality": item.get("quality"),
        "status": "pending",
        "edited": item["edited"],
        "final_content": "",
        "multi": True,
    }
    select_tab(deliverable)
    return st.session_state["review"]


def notify(text: str, icon: str) -> None:
    """A hand-off message: shown above the tabs, in the chat and as a toast."""

    st.session_state["multi"]["notice"] = text
    st.session_state["messages"].append({"role": "assistant", "kind": "text", "content": text})
    st.toast(text.replace("**", ""), icon=icon)


def show_multi_payload(payload: dict, state: dict) -> None:
    """An agent waits for the user: open its tab with the question, or the deliverable to review."""

    st.session_state["pending"] = payload
    multi = sync_multi(state)

    if not (is_review(payload) or is_image_review(payload)):
        owner = question_owner(payload)
        multi["active"] = None
        multi["question_seq"] = multi.get("question_seq", 0) + 1
        st.session_state["review"] = None
        # Announce the first question of an agent, not every one.
        if owner != multi.get("tab") or not multi["qa"].get(owner):
            notify(f"Answer a few questions to proceed with the {type_label(owner)}.", ":material/help:")
        select_tab(owner)
        return

    set_multi_review(payload)
    notify("Your drafts are ready for review.", ":material/rate_review:")


def announce_handoff(previous: str | None, new: str | None) -> None:
    """Tell the user one content type's step is finished and the work moves to another type."""

    multi = st.session_state["multi"]
    new_label = f"**{type_label(new)}**"

    if previous is None:
        created = ", ".join(type_label(deliverable) for deliverable in multi["requested"])
        text = f"I analyzed your request. Creating: {created}. Starting with {new_label}."
    else:
        item = multi["items"].get(previous, new_item())
        previous_label = f"**{type_label(previous)}**"
        if item["status"] == "failed":
            text = f"{previous_label} is currently unavailable. Now working on {new_label}."
        elif item["status"] == "draft":
            text = f"{previous_label} is drafted. Now working on {new_label}."
        elif item["status"] in FINAL_ITEM_STATUSES:
            text = f"{previous_label} is reviewed. Now working on {new_label}."
        elif multi["progress"].get("strategy"):
            text = f"Research and content strategy are ready. Now working on {new_label}."
        else:
            text = f"Finished the {previous_label} step. Now working on {new_label}."

    notify(text, ":material/sync_alt:")
    select_tab(new)


def queue_multi_job(job: dict) -> None:
    """Queue multi-content work; the Content page runs it with live progress in its tab."""

    st.session_state["multi_job"] = job
    go_to("create")


def start_multi_request(prompt: str, settings: dict) -> None:
    st.session_state["multi"] = new_multi(None, prompt)
    st.session_state["messages"] += [
        {"role": "user", "kind": "text", "content": prompt},
        {
            "role": "assistant",
            "kind": "text",
            "content": "On it! Each content type gets its own tab in the **Content** tab, "
            "where you can follow its progress and answer its questions.",
        },
    ]
    queue_multi_job({"kind": "start", "prompt": prompt, "settings": settings, "owner": None})


def queue_multi_answer(response: dict, answer_text: str) -> None:
    pending = st.session_state.get("pending") or {}
    owner = question_owner(pending)
    multi = st.session_state["multi"]
    multi["qa"].setdefault(owner, []).append([pending.get("question", ""), answer_text])
    queue_multi_job({"kind": "answer", "response": response, "answer_text": answer_text, "owner": owner})


def queue_multi_review(deliverable: str, action: str, edited_content: str = "", edited_prompt: str = "") -> bool:
    """Queue a review decision. Returns False (with review_error set) if it is not valid."""

    try:
        decision = build_multi_decision(deliverable, action, edited_content, edited_prompt)
    except ValueError as error:
        st.session_state["review_error"] = str(error)
        return False

    labels = IMAGE_REVIEW_LABELS if deliverable == "image" else REVIEW_LABELS
    st.session_state["messages"].append(
        {"role": "user", "kind": "text", "content": f"{labels[action]} ({type_label(deliverable)})"}
    )
    queue_multi_job({"kind": "review", "deliverable": deliverable, "decision": decision, "owner": deliverable})
    return True


def decide_multi(action: str) -> None:
    """Queue approve, edit or reject for the text deliverable under review."""

    review = st.session_state["review"]
    edited_content = st.session_state.get("edit_draft", "") if action == "edit" else ""
    if queue_multi_review(review["type"], action, edited_content=edited_content):
        for key in ["review_editing", "review_error", "edit_draft"]:
            st.session_state.pop(key, None)


def apply_multi_review(job: dict) -> None:
    """Show a review decision in its tab once the workflow has accepted it."""

    deliverable, decision = job["deliverable"], job["decision"]
    item = st.session_state["multi"]["items"].setdefault(deliverable, new_item())
    action = decision["action"]

    if deliverable == "image":
        if action == "edit":
            item["edited"] = True
        elif action in {"approve", "reject"}:
            item["status"] = "approved" if action == "approve" else "rejected"
        return

    # The reviewer treats an edit as final, so it counts as approved.
    item.update(
        status="rejected" if action == "reject" else "approved",
        content=decision.get("edited_content") or item["content"],
        edited=item["edited"] or action == "edit",
    )


def finish_multi(state: dict) -> None:
    """Every deliverable has been reviewed: summarize."""

    multi = sync_multi(state)
    multi["active"] = None
    multi["done"] = True
    st.session_state["pending"] = None
    st.session_state["review"] = None

    by_status: dict[str, list[str]] = {}
    for deliverable in multi["requested"]:
        status = multi["items"].get(deliverable, new_item())["status"]
        by_status.setdefault(status, []).append(type_label(deliverable))

    lines = []
    if by_status.get("approved"):
        lines.append(f"**Approved:** {', '.join(by_status['approved'])}")
    if by_status.get("rejected"):
        lines.append(f"**Rejected:** {', '.join(by_status['rejected'])}")
    if by_status.get("failed"):
        lines.append(f"**Currently unavailable:** {', '.join(by_status['failed'])}")

    if by_status.get("approved"):
        intro = "All done! Your approved content is in the **Content** tab and the **Content dashboard**."
        st.session_state["dashboard_selected"] = multi["conversation_id"]
    else:
        intro = "All done. Nothing was approved this time; send a new request to try again."

    multi["notice"] = intro
    st.session_state["messages"].append({"role": "assistant", "kind": "text", "content": "\n\n".join([intro, *lines])})
    st.toast("All content types reviewed", icon=":material/verified:")


def open_multi_conversation(conversation: dict, messages: list[dict]) -> None:
    """Restore a multi-content conversation from its checkpoint, or its approved pieces from MongoDB."""

    conversation_id = conversation["conversation_id"]
    st.session_state["multi"] = new_multi(conversation_id, conversation.get("topic") or conversation["title"])

    try:
        state = get_thread_state(conversation_id)
        payload = get_pending_payload(conversation_id)
        next_nodes = get_next_nodes(conversation_id)
    except Exception:
        logger.exception("Could not read the workflow state for %s", conversation_id)
        state, payload, next_nodes = {}, None, ()

    if state:
        multi = sync_multi(state)
        if payload is not None:
            st.session_state["pending"] = payload
            if is_review(payload) or is_image_review(payload):
                set_multi_review(payload)
            else:
                multi["question_seq"] = 1
                select_tab(question_owner(payload))
        elif next_nodes:
            # Paused between two agent steps: carry on where it stopped.
            owner = step_owner(next_nodes[0], state, multi, None)
            select_tab(owner)
            st.session_state["multi_job"] = {"kind": "continue", "owner": owner}
        else:
            multi["done"] = True
        return

    # Without the checkpoint only the approved pieces can be shown.
    multi = st.session_state["multi"]
    for message in messages:
        if message.get("message_type") != "final_content":
            continue
        metadata = message.get("metadata", {})
        deliverable = metadata.get("deliverable") or ui_type(message["content_type"])
        multi["items"][deliverable] = {
            "status": "approved",
            "content": message["content"],
            "image_prompt": metadata.get("image_prompt", ""),
            "edited": False,
        }

    statuses = conversation.get("metadata", {}).get("deliverables", {})
    multi["requested"] = [d for d in MULTI_DELIVERABLES if d in statuses or d in multi["items"]]
    for deliverable in multi["requested"]:
        status = statuses.get(deliverable)
        multi["items"].setdefault(
            deliverable, {**new_item(), "status": status if status in FINAL_ITEM_STATUSES else "unavailable"}
        )

    multi["done"] = conversation["status"] in {"completed", "archived"}
    if not multi["done"]:
        st.session_state["conversation_closed"] = True


# Titles


def make_title(body: str, fallback: str) -> str:
    """Use the first markdown heading as the title, otherwise the request text."""

    match = re.search(r"^#{1,3}\s+(.+)$", body, re.MULTILINE)
    title = match.group(1) if match else fallback
    title = title.strip().strip("*")
    return title if len(title) <= 70 else title[:67] + "..."
