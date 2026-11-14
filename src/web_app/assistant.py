
"""Bridge between the UI, the LangGraph workflow and the MongoDB repositories.

A content conversation is one workflow thread (thread_id = conversation_id).
The workflow pauses with interrupt() whenever it needs the user: the LinkedIn
agent's profile questions, the image generator's preference questions,
content_review's approve / edit / reject decision and image_review's
approve / edit / regenerate / reject decision. The chat answers those
interrupts by resuming the thread.

Research runs research_agent -> content_strategist -> content_review, so the
research draft is a research report followed by a content strategy. If the
image provider fails, the workflow ends with image_status "failed" instead of
pausing for image review; the conversation is then marked failed.
"""

import os
import re
import time
from collections.abc import Callable

import streamlit as st
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.core.logger import setup_logger
from src.core.workflow import build_workflow
from src.integrations.openai_client import generate_text
from src.repositories.conversation_repository import (
    create_conversation,
    get_conversation,
    list_conversations,
    update_conversation,
)
from src.repositories.message_repository import (
    add_message,
    list_messages,
    list_user_messages_by_type,
    update_message,
)
from src.repositories.user_repository import get_user_by_id

logger = setup_logger("assistant")

DEFAULT_USER_ID = "usr_local_001"

CONTENT_TYPES = {
    "auto": {
        "label": "Auto",
        "icon": ":material/auto_awesome:",
        "color": "gray",
    },
    "research": {
        "label": "Research",
        "icon": ":material/travel_explore:",
        "color": "blue",
    },
    "blog": {
        "label": "SEO blog",
        "icon": ":material/article:",
        "color": "green",
    },
    "linkedin": {
        "label": "LinkedIn post",
        "icon": ":material/work:",
        "color": "violet",
    },
    "image": {
        "label": "Image",
        "icon": ":material/image:",
        "color": "orange",
    },
    "multi": {
        "label": "Multi-content",
        "icon": ":material/dashboard_customize:",
        "color": "yellow",
    },
    # Only produced as part of a multi-content request.
    "strategy": {
        "label": "Content strategy",
        "icon": ":material/strategy:",
        "color": "blue",
    },
    "chat": {
        "label": "Chat",
        "icon": ":material/forum:",
        "color": "gray",
    },
}

# What each agent says when the user picks its content type. {name} is the user's name.
AGENT_INTROS = {
    "auto": (
        "Hi {name}! I'm your **ContentAlchemy assistant**. Ask me anything, or describe what you need: "
        "a LinkedIn post, an SEO blog, a research report or an image. I'll hand it to the right agent automatically."
    ),
    "research": (
        "Hi {name}! I'm your **Research agent**. Give me a topic and I'll search the web for the latest data, "
        "trends and sources, then write a research report with a content strategy for your review.\n\n"
        "*Try: \"Research AI adoption trends in B2B marketing\"*"
    ),
    "blog": (
        "Hi {name}! I'm your **SEO blog writer**. Tell me the topic and I'll research it, pick the right keywords "
        "and write a long-form, search-optimized article for your review.\n\n"
        "*Tip: set the tone, audience and keywords under Brand voice for a sharper draft.*"
    ),
    "linkedin": (
        "Hi {name}! I'm your **LinkedIn agent**. Tell me what you want to post about. I'll ask a few quick questions "
        "about you and your goals, then write an engaging post with hashtags for your review."
    ),
    "image": (
        "Hi {name}! I'm your **Image generator**. Describe the image you want. If you don't mention its purpose, "
        "style, orientation or quality, I'll ask one question at a time, then create it for your review. "
        "You can approve, edit the prompt, regenerate or reject it, and download it once approved."
    ),
    "multi": (
        "Hi {name}! I'm your **Multi-content orchestrator**. Ask for several pieces at once and I'll run each "
        "agent in turn: a LinkedIn post, an SEO blog, an image, and research or a content strategy if you ask. "
        "LinkedIn and image agents ask their questions here; every piece gets its own tab in the **Content** tab "
        "for review.\n\n"
        "*Try: \"Write a LinkedIn post and an SEO blog about AI in marketing, with an image\"*"
    ),
}

# Deliverables a multi-content request can ask for, in display order.
MULTI_DELIVERABLES = ["research", "strategy", "linkedin", "blog", "image"]


def agent_intro(content_type: str, name: str) -> str:
    return AGENT_INTROS.get(content_type, AGENT_INTROS["auto"]).format(name=name)


# The repositories call the blog type "seo_blog"; the UI and workflow call it "blog".
REPO_TYPES = {"blog": "seo_blog"}
UI_TYPES = {repo: ui for ui, repo in REPO_TYPES.items()}

# Progress messages shown while the workflow runs, by node name.
STEP_LABELS = {
    "query_handler": "Analyzed your request",
    "linkedin_profile_interaction": "Saved your profile answers",
    "linkedin_writer": "Wrote the LinkedIn draft",
    "content_writer": "Wrote the draft",
    "research_agent": "Researched the topic",
    "content_strategist": "Wrote the research report and content strategy",
    "seo_blog_writer": "Wrote the SEO blog",
    "image_request_analyzer": "Read your image request",
    "image_preference_interaction": "Saved your answer",
    "image_generator": "Generated the image",
    "image_review": "Recorded your review",
    # Multi-content workflow
    "multi_agent_orchestrator": "Planned the next deliverable",
    "multi_content_generator": "Wrote a deliverable",
    "multi_content_review": "Recorded your reviews",
}

# multi_content_generator writes one deliverable per run; its current_agent says which.
MULTI_WRITER_LABELS = {
    "blog_writer": "Wrote the SEO blog",
    "linkedin_writer": "Wrote the LinkedIn post",
}

# Auto mode starts an agent when the message clearly asks for that content.
ROUTING_KEYWORDS = {
    "linkedin": ["linkedin"],
    "blog": ["blog", "article", "seo"],
    "image": ["image", "banner", "illustration", "picture", "graphic", "visual"],
    "research": ["research", "trends", "report", "analyze", "analysis"],
}

REVIEW_LABELS = {
    "approve": "Approved the draft",
    "edit": "Edited the draft",
    "reject": "Rejected the draft",
}

IMAGE_REVIEW_LABELS = {
    "approve": "Approved the image",
    "edit": "Edited the image prompt",
    "regenerate": "Regenerate the image",
    "reject": "Rejected the image",
}

# Interrupts that wait for a review decision rather than an answer to a question.
REVIEW_INTERACTIONS = {"content_review", "image_review"}

CHAT_SYSTEM_PROMPT = (
    "You are a helpful, knowledgeable general-purpose assistant. Answer any "
    "question clearly and concisely. Use markdown when it helps readability."
)

HISTORY_LIMIT = 6


def repo_type(content_type: str) -> str:
    return REPO_TYPES.get(content_type, content_type)


def ui_type(content_type: str) -> str:
    return UI_TYPES.get(content_type, content_type)


def short_title(text: str, limit: int = 60) -> str:
    title = " ".join(text.split())
    return title if len(title) <= limit else title[: limit - 3] + "..."


def detect_content_type(prompt: str) -> str | None:
    """Pick a content agent from keywords in the message; None means general chat."""

    text = prompt.lower()
    for content_type, keywords in ROUTING_KEYWORDS.items():
        if any(re.search(rf"\b{keyword}", text) for keyword in keywords):
            return content_type
    return None


def thread_config(conversation_id: str) -> dict:
    # The conversation id doubles as the LangGraph thread id.
    return {"configurable": {"thread_id": conversation_id}}


@st.cache_resource
def get_workflow():
    """Compile the workflow once; its in-memory checkpointer holds paused threads."""

    return build_workflow(checkpointer=MemorySaver())


# User and history


@st.cache_data(ttl=600, show_spinner=False)
def get_current_user() -> dict:
    user_id = os.getenv("CONTENTALCHEMY_USER_ID", DEFAULT_USER_ID)
    try:
        user = get_user_by_id(user_id) or {}
    except Exception:
        logger.exception("Could not load user %s", user_id)
        user = {}
    return {"user_id": user_id, "username": user.get("username") or "Guest"}


@st.cache_data(ttl=300, show_spinner=False)
def fetch_history(user_id: str) -> list[dict]:
    return list_conversations(user_id, limit=30)


def list_history(user_id: str) -> list[dict]:
    """Recent conversations, newest first. Empty if MongoDB is unavailable."""

    try:
        return fetch_history(user_id)
    except Exception:
        logger.exception("Could not load conversation history")
        return []


def refresh_history() -> None:
    fetch_history.clear()
    fetch_approved_content.clear()


# Approved content (content dashboard)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_approved_content(user_id: str) -> list[dict]:
    """The latest approved content of each completed conversation, newest first."""

    conversations = {
        conversation["conversation_id"]: conversation
        for conversation in list_conversations(user_id, limit=100, status="completed")
    }

    # Structured agent output (e.g. the SEO blog's keywords and outline), newest per conversation.
    structured = {}
    # A multi-content conversation has one per deliverable type.
    structured_by_type = {}
    # The content strategist's plan, for conversations where it ran.
    strategies = {}
    for message in list_user_messages_by_type(user_id, "generated_content", limit=200):
        if isinstance(message["content"], dict):
            structured.setdefault(message["conversation_id"], message["content"])
            structured_by_type.setdefault((message["conversation_id"], message["content_type"]), message["content"])
            if (message["content"].get("content_strategy") or "").strip():
                strategies.setdefault(message["conversation_id"], message["content"]["content_strategy"])

    items = {}
    for message in list_user_messages_by_type(user_id, "final_content", limit=200):
        conversation = conversations.get(message["conversation_id"])
        if conversation is None:
            continue

        if conversation["content_type"] == "multi":
            # One dashboard item per approved deliverable.
            piece_type = ui_type(message["content_type"])
            item_id = f"{conversation['conversation_id']}:{piece_type}"
            if item_id in items:
                continue
            items[item_id] = {
                "id": item_id,
                "conversation_id": conversation["conversation_id"],
                "message_id": message["message_id"],
                "type": piece_type,
                "title": conversation["title"],
                "prompt": conversation.get("topic") or conversation["title"],
                "body": message["content"],
                "data": structured_by_type.get((conversation["conversation_id"], message["content_type"]), {}),
                "metadata": message.get("metadata", {}),
                "created_at": message["created_at"],
            }
            continue

        if conversation["conversation_id"] in items:
            continue
        items[conversation["conversation_id"]] = {
            "id": conversation["conversation_id"],
            "message_id": message["message_id"],
            "type": ui_type(conversation["content_type"]),
            "title": conversation["title"],
            "prompt": conversation.get("topic") or conversation["title"],
            "body": message["content"],
            "data": structured.get(conversation["conversation_id"], {}),
            "strategy": strategies.get(conversation["conversation_id"], ""),
            "metadata": message.get("metadata", {}),
            "created_at": message["created_at"],
        }
    return list(items.values())


def list_approved_content(user_id: str) -> list[dict]:
    """Approved content for the dashboard. Empty if MongoDB is unavailable."""

    try:
        return fetch_approved_content(user_id)
    except Exception:
        logger.exception("Could not load approved content")
        return []


def save_approved_content(user_id: str, item: dict, body: str) -> None:
    if not body.strip():
        raise ValueError("Content cannot be empty.")
    update_message(item["message_id"], item.get("conversation_id", item["id"]), user_id, content=body.strip())
    refresh_history()


def remove_approved_content(user_id: str, conversation_id: str) -> None:
    """Take a piece off the dashboard by archiving its conversation."""

    update_conversation(
        conversation_id,
        user_id,
        status="archived",
        metadata_updates={"removed_from_dashboard": True},
    )
    refresh_history()


def load_conversation(user_id: str, conversation_id: str) -> tuple[dict, list[dict]]:
    conversation = get_conversation(conversation_id, user_id)
    if conversation is None:
        raise ValueError("Conversation not found.")
    return conversation, list_messages(conversation_id, user_id, limit=200)


# Content workflow


def get_pending_payload(conversation_id: str) -> dict | None:
    """The interrupt a thread is paused on, if its checkpoint still exists."""

    snapshot = get_workflow().get_state(thread_config(conversation_id))
    return snapshot.interrupts[0].value if snapshot.interrupts else None


def get_thread_state(conversation_id: str) -> dict:
    """The workflow state of a thread; empty if its checkpoint is gone."""

    return dict(get_workflow().get_state(thread_config(conversation_id)).values or {})


def get_next_nodes(conversation_id: str) -> tuple[str, ...]:
    """The nodes a paused thread runs next; empty once the workflow has ended."""

    return tuple(get_workflow().get_state(thread_config(conversation_id)).next)


def run_workflow(
    conversation_id: str,
    value: dict | Command,
    on_step: Callable[[str], None] | None = None,
    on_event: Callable[[dict], None] | None = None,
    interrupt_after: list[str] | None = None,
) -> tuple[dict | None, dict]:
    """Run or resume a thread until it pauses or ends.

    interrupt_after also pauses the thread after those nodes finish (no payload); resume with None.
    """

    payload = None
    config = thread_config(conversation_id)

    start_time = time.perf_counter()
    status = "completed"

    logger.info(
        "Workflow started | Conversation ID: %s",
        conversation_id,
    )

    try:
        for mode, update in get_workflow().stream(
            value,
            config=config,
            stream_mode=["updates", "custom"],
            interrupt_after=interrupt_after,
        ):
            if mode == "custom":
                if on_event:
                    on_event(update)
                continue

            for node in update:
                if node == "__interrupt__":
                    # A pause from interrupt_after has no payload.
                    if update[node]:
                        payload = update[node][0].value
                    status = "interrupted"

                elif node in STEP_LABELS and on_step:
                    output = update[node] if isinstance(update[node], dict) else {}
                    on_step(MULTI_WRITER_LABELS.get(output.get("current_agent"), STEP_LABELS[node]))

        state = get_workflow().get_state(config).values

        return payload, state

    except Exception:
        status = "failed"
        logger.exception(
            "Workflow failed | Conversation ID: %s",
            conversation_id,
        )
        raise

    finally:
        elapsed = time.perf_counter() - start_time

        logger.info(
            "Workflow finished | Conversation ID: %s | "
            "Status: %s | Execution time: %.2f seconds",
            conversation_id,
            status,
            elapsed,
        )


def image_failed(state: dict) -> bool:
    """The image generator ended the workflow because the image provider failed."""

    return state.get("image_status") == "failed"


def workflow_error(state: dict) -> str:
    return state.get("image_error") or (state.get("errors") or ["The workflow stopped unexpectedly."])[-1]


def record_failure(user_id: str, conversation_id: str, content_type: str, state: dict) -> None:
    """Save why the workflow ended without a result and mark the conversation failed."""

    error = workflow_error(state)
    try:
        add_message(
            conversation_id,
            user_id,
            "assistant",
            "error",
            repo_type(content_type),
            error,
            agent_name=state.get("current_agent"),
        )
        update_conversation(conversation_id, user_id, status="failed", metadata_updates={"error": error})
    except Exception:
        logger.exception("Could not record the failure of %s", conversation_id)
    refresh_history()


def record_pause(user_id: str, conversation_id: str, content_type: str, payload: dict | None) -> None:
    """Save the agent's question, or mark the conversation as awaiting approval."""

    if payload is None:
        return

    if payload.get("interaction_type") in REVIEW_INTERACTIONS:
        update_conversation(conversation_id, user_id, status="awaiting_approval")
    else:
        add_message(
            conversation_id,
            user_id,
            "assistant",
            "question",
            repo_type(content_type),
            payload["question"],
            agent_name=payload.get("agent"),
            metadata={"options": payload.get("options", []), "lookup_key": payload.get("lookup_key")},
        )
    refresh_history()


def start_agent(
    user_id: str,
    content_type: str,
    request: str,
    settings: dict,
    on_step: Callable[[str], None] | None = None,
    on_event: Callable[[dict], None] | None = None,
) -> tuple[str, dict | None, dict]:
    """Create a conversation for the request and run the workflow until it needs the user."""

    conversation_id, initial_state = create_content_conversation(user_id, content_type, request, settings)

    try:
        payload, state = run_workflow(conversation_id, initial_state, on_step, on_event)
    except Exception:
        update_conversation(conversation_id, user_id, status="failed")
        refresh_history()
        raise

    if payload is None and image_failed(state):
        record_failure(user_id, conversation_id, content_type, state)
    record_pause(user_id, conversation_id, content_type, payload)
    return conversation_id, payload, state


def create_content_conversation(user_id: str, content_type: str, request: str, settings: dict) -> tuple[str, dict]:
    """Save the request as a new conversation. Returns its id and the workflow's initial state."""

    keywords = [word.strip() for word in settings["keywords"].split(",") if word.strip()]
    stored_type = repo_type(content_type)

    conversation = create_conversation(
        user_id=user_id,
        content_type=stored_type,
        title=short_title(request),
        topic=request,
        target_audience=settings["audience"],
        tone=settings["tone"] or "",
        metadata={"keywords": keywords},
    )
    conversation_id = conversation["conversation_id"]
    add_message(conversation_id, user_id, "user", "request", stored_type, request)
    refresh_history()

    initial_state = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "intent": content_type,
        "user_request": request,
        "target_audience": settings["audience"],
        "tone": settings["tone"] or "",
        "keywords": keywords,
        "completed_agents": [],
        "errors": [],
    }
    return conversation_id, initial_state


def answer_question(
    user_id: str,
    conversation_id: str,
    content_type: str,
    response: dict,
    answer_text: str,
    on_step: Callable[[str], None] | None = None,
    on_event: Callable[[dict], None] | None = None,
) -> tuple[dict | None, dict]:
    """Resume the thread with the user's answer to the agent's question."""

    add_message(conversation_id, user_id, "user", "answer", repo_type(content_type), answer_text)
    payload, state = run_workflow(conversation_id, Command(resume=response), on_step, on_event)
    if payload is None and image_failed(state):
        record_failure(user_id, conversation_id, content_type, state)
    record_pause(user_id, conversation_id, content_type, payload)
    return payload, state


def submit_decision(
    user_id: str,
    conversation_id: str,
    content_type: str,
    draft: str,
    action: str,
    edited_content: str = "",
) -> tuple[dict | None, dict]:
    """Resume content_review with approve / edit / reject.

    An edit sends the edited draft back to review, so a new payload comes back.
    """

    decision = {"action": action, "edited_content": edited_content.strip() if action == "edit" else ""}
    stored_type = repo_type(content_type)

    if action == "edit" and not decision["edited_content"]:
        raise ValueError("Edited content cannot be empty.")

    if get_pending_payload(conversation_id) is not None:
        payload, state = run_workflow(conversation_id, Command(resume=decision))
    else:
        # The checkpoint is gone (e.g. the app restarted): apply the reviewer's rules here.
        payload = None
        state = {"approval_status": "rejected" if action == "reject" else "approved", "review_action": action}
        state["final_content"] = "" if action == "reject" else decision["edited_content"] or draft

    add_message(
        conversation_id,
        user_id,
        "user",
        "review",
        stored_type,
        REVIEW_LABELS[action],
        metadata={"review_action": action},
    )

    if payload is not None:
        record_pause(user_id, conversation_id, content_type, payload)
        return payload, state

    status = state["approval_status"]
    if status == "approved":
        add_message(
            conversation_id,
            user_id,
            "assistant",
            "final_content",
            stored_type,
            state["final_content"],
            agent_name="content_review",
        )

    update_conversation(
        conversation_id,
        user_id,
        status="completed" if status == "approved" else "archived",
        metadata_updates={"approval_status": status},
    )
    refresh_history()
    return None, state


def submit_image_decision(
    user_id: str,
    conversation_id: str,
    action: str,
    edited_prompt: str = "",
    image: dict | None = None,
    on_step: Callable[[str], None] | None = None,
    on_event: Callable[[dict], None] | None = None,
) -> tuple[dict | None, dict]:
    """Resume image_review with approve / edit / regenerate / reject.

    Edit and regenerate send the thread back to the image generator, so a new
    image_review payload comes back. Approve and reject end the workflow.
    image is the reviewed image ({"path", "prompt", "message_id"}), used when the checkpoint is gone.
    """

    if action not in IMAGE_REVIEW_LABELS:
        raise ValueError(f"Unsupported image review action: {action}")

    decision = {"action": action}
    if action == "edit":
        decision["edited_prompt"] = edited_prompt.strip()
        if not decision["edited_prompt"]:
            raise ValueError("The edited image prompt cannot be empty.")

    image = image or {}
    has_checkpoint = get_pending_payload(conversation_id) is not None
    if not has_checkpoint and action in {"edit", "regenerate"}:
        raise ValueError(
            "This image can no longer be regenerated (the app was restarted). "
            "Approve or reject it, or start a new conversation."
        )

    add_message(
        conversation_id,
        user_id,
        "user",
        "review",
        "image",
        IMAGE_REVIEW_LABELS[action] + (f": {decision['edited_prompt']}" if action == "edit" else ""),
        metadata={"review_action": action},
    )

    if has_checkpoint:
        payload, state = run_workflow(conversation_id, Command(resume=decision), on_step, on_event)
    else:
        # Apply the reviewer's rules here and keep the stored image message in sync.
        payload = None
        status = "rejected" if action == "reject" else "approved"
        state = {
            "image_status": status,
            "image_review_action": action,
            "image_path": image.get("path", ""),
            "image_prompt": image.get("prompt", ""),
            "final_content": "" if action == "reject" else image.get("path", ""),
        }
        if image.get("message_id"):
            update_message(
                image["message_id"],
                conversation_id,
                user_id,
                status=status,
                metadata_updates={"image_status": status},
            )

    if payload is not None:
        record_pause(user_id, conversation_id, "image", payload)
        return payload, state

    if image_failed(state):
        # Edit / regenerate could not create a new image; the workflow has ended.
        record_failure(user_id, conversation_id, "image", state)
        return None, state

    status = state.get("image_status")
    if status == "approved":
        add_message(
            conversation_id,
            user_id,
            "assistant",
            "final_content",
            "image",
            state["final_content"],
            agent_name="image_review",
            metadata={"image_prompt": state.get("image_prompt", "")},
        )

    update_conversation(
        conversation_id,
        user_id,
        status="completed" if status == "approved" else "archived",
        metadata_updates={"approval_status": status},
    )
    refresh_history()
    return None, state


# Multi-content workflow


# A multi-content thread pauses after each of these nodes, so the UI can show every agent step
# in the tab of the content type it works on, and open the next type's tab when the work moves on.
MULTI_STEP_NODES = [
    "query_handler",
    "linkedin_profile_interaction",
    "research_agent",
    "content_strategist",
    "multi_agent_orchestrator",
    "multi_content_generator",
    "image_request_analyzer",
    "image_preference_interaction",
    "image_generator",
    "image_review",
    "multi_content_review",
]


def advance_multi(
    user_id: str,
    conversation_id: str,
    value: dict | Command | None,
    on_step: Callable[[str], None] | None = None,
    on_event: Callable[[dict], None] | None = None,
) -> tuple[dict | None, dict, tuple[str, ...]]:
    """Run a multi-content thread for one agent step.

    value is the initial state, a Command(resume=...) answering the pending interrupt, or None to
    continue after the previous step. Returns (payload, state, next nodes):
    a payload means an agent waits for the user; no payload and no next nodes means the workflow
    has ended (approved pieces are then saved); otherwise call again with None.
    """

    try:
        payload, state = run_workflow(conversation_id, value, on_step, on_event, interrupt_after=MULTI_STEP_NODES)
    except Exception:
        # The thread stays paused at its last checkpoint, so the step can be retried.
        logger.exception("Multi-content step failed for %s", conversation_id)
        raise

    next_nodes = get_next_nodes(conversation_id)

    if payload is not None:
        record_pause(user_id, conversation_id, "multi", payload)
    elif not next_nodes:
        finalize_multi(user_id, conversation_id, state)
    return payload, state, next_nodes


def record_multi_answer(user_id: str, conversation_id: str, answer_text: str) -> None:
    add_message(conversation_id, user_id, "user", "answer", "multi", answer_text)


def build_multi_decision(deliverable: str, action: str, edited_content: str = "", edited_prompt: str = "") -> dict:
    """Validate a review decision for one multi-content deliverable.

    Text deliverables are reviewed by multi_content_review (approve / edit / reject; an edit is
    final). The image is reviewed by image_review (approve / edit / regenerate / reject).
    """

    is_image = deliverable == "image"
    labels = IMAGE_REVIEW_LABELS if is_image else REVIEW_LABELS
    if action not in labels:
        raise ValueError(f"Unsupported review action for {deliverable}: {action}")

    if is_image:
        decision = {"action": action}
        if action == "edit":
            decision["edited_prompt"] = edited_prompt.strip()
            if not decision["edited_prompt"]:
                raise ValueError("The edited image prompt cannot be empty.")
    else:
        decision = {"action": action, "edited_content": edited_content.strip() if action == "edit" else ""}
        if action == "edit" and not decision["edited_content"]:
            raise ValueError("Edited content cannot be empty.")
    return decision


def record_multi_review(user_id: str, conversation_id: str, deliverable: str, decision: dict) -> None:
    action = decision["action"]
    label = (IMAGE_REVIEW_LABELS if deliverable == "image" else REVIEW_LABELS)[action]
    if decision.get("edited_prompt"):
        label += f": {decision['edited_prompt']}"
    add_message(
        conversation_id,
        user_id,
        "user",
        "review",
        repo_type(deliverable),
        label,
        metadata={"review_action": action, "deliverable": deliverable},
    )


def finalize_multi(user_id: str, conversation_id: str, state: dict) -> None:
    """Save every approved deliverable as final content and close the conversation."""

    results = state.get("multi_agent_results", {})
    approved = []

    for deliverable in state.get("requested_agents", []):
        result = results.get(deliverable, {})
        if result.get("status") != "approved":
            continue

        body = result.get("content_text") or result.get("content") or ""
        if not isinstance(body, str) or not body.strip():
            continue

        metadata = {"deliverable": deliverable}
        if deliverable == "image":
            metadata["image_prompt"] = result.get("image_prompt", "")

        add_message(
            conversation_id,
            user_id,
            "assistant",
            "final_content",
            repo_type(deliverable),
            body,
            agent_name="image_review" if deliverable == "image" else "multi_content_review",
            metadata=metadata,
        )
        approved.append(deliverable)

    statuses = {deliverable: results.get(deliverable, {}).get("status", "missing") for deliverable in results}
    update_conversation(
        conversation_id,
        user_id,
        status="completed" if approved else "archived",
        metadata_updates={"approval_status": "approved" if approved else "rejected", "deliverables": statuses},
    )
    refresh_history()


# General chat


def build_query(prompt: str, history: list[dict]) -> str:
    """Prepend recent conversation turns so follow-up questions keep their context."""

    recent = history[-HISTORY_LIMIT:]
    if not recent:
        return prompt

    transcript = "\n\n".join(f"{msg['role'].upper()}: {msg['content']}" for msg in recent)
    return f"Conversation so far:\n\n{transcript}\n\nUSER: {prompt}"


def chat_reply(prompt: str, history: list[dict]) -> str:
    return generate_text(build_query(prompt, history), system_prompt=CHAT_SYSTEM_PROMPT)


def save_chat_turn(user_id: str, conversation_id: str | None, prompt: str, reply: str) -> str | None:
    """Store a chat exchange, creating the conversation on the first message.

    Chat still works without MongoDB, so failures are logged, not raised.
    """

    try:
        if conversation_id is None:
            conversation = create_conversation(user_id, "chat", title=short_title(prompt))
            conversation_id = conversation["conversation_id"]
        add_message(conversation_id, user_id, "user", "chat", "chat", prompt)
        add_message(conversation_id, user_id, "assistant", "chat", "chat", reply)
        refresh_history()
    except Exception:
        logger.exception("Could not save chat message")
    return conversation_id
