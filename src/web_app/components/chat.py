
"""Chat window: talk to the content agents, or chat generally in Auto mode.

With a content type selected (or detected in Auto mode), each message drives the LangGraph workflow:
the agent's questions appear here, the user answers here, and the draft
comes back for approve / edit / reject. The image generator asks for its
preferences in one form, then shows the image for approve / edit / regenerate /
reject, and offers the download once approved.
"""

import time
from contextlib import nullcontext

import streamlit as st

from src.agents.linkedin_interaction import LINKEDIN_PROFILE_QUESTIONS
from src.core.logger import setup_logger
from src.web_app.assistant import (
    CONTENT_TYPES,
    answer_question,
    chat_reply,
    detect_content_type,
    get_current_user,
    save_chat_turn,
    start_agent,
    submit_image_decision,
)
from src.web_app.components.image_view import render_image_message
from src.web_app.components.sidebar import get_settings
from src.web_app.components.theme import DRAFT_HEIGHT
from src.web_app.components.state import (
    decide,
    finish_image_review,
    go_to,
    is_image_review,
    is_review,
    reset_conversation,
    show_payload,
    start_edit,
    start_image_edit,
)

logger = setup_logger("chat")

# Chat title for each content agent picked in the sidebar.
AGENT_TITLES = {
    "research": "Research agent",
    "blog": "SEO blog writer",
    "linkedin": "LinkedIn post writer",
    "image": "Image generator",
}

IMAGE_SPINNER = "Creating your image. This usually takes 15 to 60 seconds..."

# Redraw the streamed draft at most this often (seconds); redrawing on every token is slow.
STREAM_REFRESH = 0.15

# Auto mode suggestions: content requests start an agent, the rest is general chat.
SUGGESTIONS = {
    ":violet[:material/work:] Draft a LinkedIn post": "Write a LinkedIn post about how AI agents are changing software development",
    ":green[:material/article:] Write an SEO blog": "Write an SEO blog about how small businesses can use AI for content marketing",
    ":blue[:material/travel_explore:] Research a topic": "Research the latest trends in AI content marketing",
    ":orange[:material/image:] Generate an image": "Create an image of a team collaborating with AI agents in a modern office",
    ":gray[:material/lightbulb:] Explain a concept": "Explain how large language models work in simple terms",
    ":orange[:material/checklist:] Plan something": "Help me plan a productive work week",
}

DECISION_WORDS = {
    "approve": ["approve", "approved", "yes", "looks good", "lgtm"],
    "edit": ["edit", "change", "modify"],
    "reject": ["reject", "no", "discard"],
}


IMAGE_DECISION_WORDS = {
    **DECISION_WORDS,
    "regenerate": ["regenerate", "retry", "again", "another one", "new one"],
}


def parse_decision(text: str, words_by_action: dict[str, list[str]] = DECISION_WORDS) -> str | None:
    text = text.strip().lower()
    for action, words in words_by_action.items():
        if any(text == word or text.startswith(word + " ") for word in words):
            return action
    return None


def build_answer(payload: dict, selected: list[str] | None, typed: str) -> tuple[dict, str]:
    """Combine picked options and typed text into the agent's expected response.

    Typed text that matches option names counts as picking them; anything else is "Other".
    """

    options = [option for option in payload.get("options", []) if option != "Other"]
    picked = [option for option in (selected or []) if option != "Other"]
    other_text = ""

    typed = typed.strip()
    if typed:
        by_name = {option.lower(): option for option in options}
        parts = [part.strip().lower() for part in typed.split(",") if part.strip()]
        if all(part in by_name for part in parts):
            picked += [by_name[part] for part in parts]
        else:
            other_text = typed

    picked = list(dict.fromkeys(picked))
    answer_text = ", ".join(picked + ([other_text] if other_text else []))
    return {"selected_options": picked, "other_text": other_text}, answer_text


# Rendering


def is_last_question(payload: dict) -> bool:
    # The image agent only asks for missing preferences, so it says which question is last.
    if "is_last" in payload:
        return bool(payload["is_last"])
    return payload.get("lookup_key") == LINKEDIN_PROFILE_QUESTIONS[-1]["key"]


def is_image_payload(payload: dict | None) -> bool:
    return bool(payload) and payload.get("agent") == "image_generator"


def render_question(message: dict, index: int, active: bool) -> tuple[dict, str] | None:
    """Show an agent question. Returns the answer once the user picks one."""

    with st.container(key=f"agent_question_{index}"):
        st.markdown(f":material/help: {message['content']}")
        if not active:
            return None

        payload = st.session_state.pending
        key = f"answer_{len(st.session_state.messages)}"
        choice = st.pills("Options", message.get("options", []), key=key, label_visibility="collapsed")

        if choice is None:
            st.caption("Pick an option, or type your own answer in the chat box.")
            return None
        if choice != "Other":
            return build_answer(payload, [choice], "")

        other_text = st.text_input(
            "Your answer", placeholder="Type your answer", key=f"{key}_other", label_visibility="collapsed"
        )
        if is_image_payload(payload):
            label = "Generate image" if is_last_question(payload) else "Next question"
        else:
            label = "Generate draft" if is_last_question(payload) else "Next question"
        if not st.button(label, type="primary", icon=":material/arrow_forward:", key="other_next"):
            return None
        if not other_text.strip():
            st.toast("Type your answer first", icon=":material/info:")
            return None
        return build_answer(payload, [], other_text)


def render_draft(message: dict, active: bool) -> None:
    content_type = message.get("content_type", "chat")
    info = CONTENT_TYPES[content_type]
    noun = "research report" if content_type == "research" else "draft"
    with st.container(horizontal=True, vertical_alignment="center"):
        st.markdown(f"**Here's your {noun}.** Please review it.")
        st.badge(info["label"], icon=info["icon"], color=info["color"])

    with st.expander(noun.capitalize(), icon=":material/description:", expanded=active):
        with st.container(height=DRAFT_HEIGHT, border=False):
            st.markdown(message["content"])

    if not active:
        return

    st.caption(f"Approve, edit or reject the {noun}. It is also shown in the Content tab.")
    with st.container(horizontal=True):
        st.button("Approve", type="primary", icon=":material/verified:", key="chat_approve", on_click=decide, args=("approve",))
        st.button("Edit", icon=":material/edit:", key="chat_edit", on_click=start_edit)
        st.button("Reject", icon=":material/delete:", key="chat_reject", on_click=decide, args=("reject",))
        st.button("Open in Content tab", icon=":material/open_in_new:", type="tertiary", key="chat_open", on_click=go_to, args=("create",))


def render_messages() -> tuple[dict, str] | None:
    """Render the conversation. Returns the answer picked for the agent's current question."""

    messages = st.session_state.messages
    pending = st.session_state.pending
    review = st.session_state.get("review") or {}
    answer = None

    # Only the newest image can be reviewed or downloaded; older ones are earlier attempts.
    image_indexes = [index for index, message in enumerate(messages) if message["kind"] == "image"]
    latest_image = image_indexes[-1] if image_indexes else None

    for index, message in enumerate(messages):
        latest = index == len(messages) - 1
        with st.chat_message(message["role"]):
            if message["kind"] == "image":
                is_current = index == latest_image
                render_image_message(
                    message,
                    # Hide the buttons while a queued decision runs below.
                    active=is_current and is_image_review(pending) and not st.session_state.get("image_action"),
                    approved=is_current and review.get("type") == "image" and review.get("status") == "approved",
                )
            elif message["kind"] == "question":
                answer = render_question(message, index, latest and pending is not None and not is_review(pending))
            elif message["kind"] == "draft":
                render_draft(message, latest and is_review(pending))
            elif message["kind"] == "answer":
                with st.container(key=f"agent_answer_{index}"):
                    st.markdown(message["content"])
            else:
                st.markdown(message["content"])

    return answer


def chat_placeholder(content_type: str | None) -> str:
    pending = st.session_state.pending
    if st.session_state.get("conversation_closed"):
        return "Start a new conversation to continue"
    if is_review(pending):
        return "Type approve, edit or reject..."
    if is_image_review(pending):
        return "Type approve, regenerate, reject, or edit: <new prompt>..."
    if pending:
        return "Type your answer, or pick options above..."
    if content_type:
        return f"Describe the {CONTENT_TYPES[content_type]['label'].lower()} you want..."
    return "Ask anything..."


# Handling input


def add_bubble(role: str, content: str, kind: str = "text") -> None:
    message = {"role": role, "kind": kind, "content": content}
    st.session_state.messages.append(message)
    with st.chat_message(role):
        with st.container(key=f"agent_{kind}_{len(st.session_state.messages) - 1}"):
            st.markdown(content)


class LiveProgress:
    """Shows workflow progress in an assistant bubble: step messages, then the draft as it is written."""

    def __init__(self, label: str):
        self.status = st.status(label, expanded=True)
        self.slot = st.empty()
        self.text_slot = None
        self.header = ""
        self.body = ""
        self.last_status = None
        self.drawn = 0.0

    def note(self, text: str) -> None:
        """A progress message, e.g. "Researching topic..." or a finished workflow step."""

        if text == self.last_status:
            return
        self.last_status = text
        self.status.update(label=text)
        self.status.caption(f":material/check_small: {text}")

    def event(self, event: dict) -> None:
        """Events the agents stream with get_stream_writer()."""

        kind = event.get("event")
        if kind == "status":
            self.note(event["text"])
            return
        if event.get("type") == "progress":
            self.note(event.get("message", ""))
            return
        if kind == "header":
            self.header = event["text"]
        elif kind == "text":
            self.body += event["text"]
        else:
            return

        if self.text_slot is None:
            box = self.slot.container(border=True, height=DRAFT_HEIGHT, autoscroll=True, key="preview_live")
            self.text_slot = box.empty()
        now = time.monotonic()
        if kind == "header" or now - self.drawn >= STREAM_REFRESH:
            body = self.body or "*Writing...*"
            self.text_slot.markdown(f"{self.header}\n\n{body} ▌")
            self.drawn = now

    def finish(self, label: str, state: str = "complete") -> None:
        self.status.update(label=label, state=state, expanded=False)


def run_agent_step(label: str, step, spinner: str | None = None) -> bool:
    """Run one workflow step with live progress in an assistant bubble. Returns True on success.

    step(on_step, on_event) runs the workflow and returns (payload, state, content_type).
    """

    with st.chat_message("assistant"):
        progress = LiveProgress(label)
        try:
            # Image generation streams no text, so a spinner shows it is still working.
            with st.spinner(spinner, show_time=True) if spinner else nullcontext():
                payload, state, content_type = step(progress.note, progress.event)
        except Exception as error:
            logger.exception("Workflow step failed")
            progress.finish("Something went wrong", state="error")
            st.error(str(error), icon=":material/error:")
            return False
        if is_image_review(payload):
            progress.finish("Image ready for review")
        else:
            progress.finish("Draft ready for review" if is_review(payload) else "Done")

    if payload is None:
        errors = state.get("errors") or ["The workflow finished without a draft."]
        st.session_state.messages.append({"role": "assistant", "kind": "text", "content": errors[-1]})
        return True

    show_payload(payload, state, content_type)
    # Every draft is reviewed in the Content tab.
    if is_review(payload):
        go_to("create")
    return True


def handle_answer(response: dict, answer_text: str) -> None:
    pending = st.session_state.pending
    content_type = st.session_state.conversation_type
    add_bubble("user", answer_text, kind="answer")

    def step(on_step, on_event):
        payload, state = answer_question(
            get_current_user()["user_id"],
            st.session_state.conversation_id,
            content_type,
            response,
            answer_text,
            on_step,
            on_event,
        )
        return payload, state, content_type

    spinner = None
    if is_image_payload(pending) and is_last_question(pending):
        label = "Generating your image..."
        spinner = IMAGE_SPINNER
    elif is_last_question(pending):
        label = "Writing your draft..."
    else:
        label = "Loading the next question..."
    if run_agent_step(label, step, spinner):
        st.rerun()
    else:
        st.session_state.messages.pop()


def handle_decision_text(prompt: str) -> None:
    action = parse_decision(prompt)
    if action == "edit":
        start_edit()
    elif action:
        decide(action)
    else:
        st.session_state.messages += [
            {"role": "user", "kind": "text", "content": prompt},
            {"role": "assistant", "kind": "text", "content": "Please reply with **approve**, **edit** or **reject**, or use the buttons above."},
        ]
    st.rerun()


IMAGE_ACTION_PROGRESS = {
    "approve": "Approving your image...",
    "edit": "Generating a new image from your prompt...",
    "regenerate": "Regenerating your image...",
    "reject": "Rejecting the image...",
}

IMAGE_ACTION_BUBBLES = {
    "approve": "Approve",
    "edit": "Edit prompt",
    "regenerate": "Regenerate",
    "reject": "Reject",
}


def handle_image_action(action: dict) -> None:
    """Send approve / edit / regenerate / reject to image_review, showing progress while it runs."""

    review = st.session_state.review
    name = action["action"]
    text = IMAGE_ACTION_BUBBLES[name]
    if name == "edit":
        text += f": {action['edited_prompt']}"
    add_bubble("user", text)

    with st.chat_message("assistant"):
        progress = LiveProgress(IMAGE_ACTION_PROGRESS[name])
        try:
            spinner = IMAGE_SPINNER if name in {"edit", "regenerate"} else "Saving your decision..."
            with st.spinner(spinner, show_time=True):
                payload, state = submit_image_decision(
                    get_current_user()["user_id"],
                    review["conversation_id"],
                    name,
                    action["edited_prompt"],
                    image={"path": review["content"], "prompt": review.get("image_prompt", ""), "message_id": review.get("message_id")},
                    on_step=progress.note,
                    on_event=progress.event,
                )
        except Exception as error:
            logger.exception("Image review failed")
            progress.finish("Something went wrong", state="error")
            st.error(str(error), icon=":material/error:")
            st.session_state.messages.pop()
            return
        progress.finish("Image ready for review" if payload else "Done")

    finish_image_review(name, payload, state)
    st.rerun()


def handle_image_decision_text(prompt: str) -> None:
    """Typed review replies: approve, regenerate, reject, "edit" or "edit: <new prompt>"."""

    text = prompt.strip()
    new_prompt = ""
    if text.lower().startswith("edit"):
        action = "edit"
        new_prompt = text[len("edit"):].lstrip(" :").strip()
    else:
        action = parse_decision(text, IMAGE_DECISION_WORDS)
    can_regenerate = not st.session_state.pending.get("checkpoint_lost")

    if action == "edit":
        if new_prompt and can_regenerate:
            handle_image_action({"action": "edit", "edited_prompt": new_prompt})
            return
        if can_regenerate:
            start_image_edit()
            st.rerun()
    elif action in {"approve", "reject"} or (action == "regenerate" and can_regenerate):
        handle_image_action({"action": action, "edited_prompt": ""})
        return

    st.session_state.messages += [
        {"role": "user", "kind": "text", "content": prompt},
        {
            "role": "assistant",
            "kind": "text",
            "content": "Please reply with **approve**, **regenerate**, **reject** or **edit: your new prompt**, "
            "or use the buttons above.",
        },
    ]
    st.rerun()


def handle_request(prompt: str, content_type: str) -> None:
    # A finished workflow or a different agent starts a new conversation.
    if st.session_state.conversation_id and (
        st.session_state.pending is None or st.session_state.conversation_type != content_type
    ):
        reset_conversation()
    st.session_state.conversation_type = content_type
    add_bubble("user", prompt)

    def step(on_step, on_event):
        conversation_id, payload, state = start_agent(
            get_current_user()["user_id"], content_type, prompt, get_settings(), on_step, on_event
        )
        st.session_state.conversation_id = conversation_id
        return payload, state, content_type

    spinner = IMAGE_SPINNER if content_type == "image" else None
    if run_agent_step("Analyzing your request...", step, spinner):
        st.rerun()
    else:
        st.session_state.messages.pop()


def handle_general_chat(prompt: str) -> None:
    if st.session_state.conversation_type not in (None, "chat"):
        reset_conversation()
    st.session_state.conversation_type = "chat"

    history = [msg for msg in st.session_state.messages if msg["kind"] == "text"]
    add_bubble("user", prompt)

    with st.chat_message("assistant"):
        try:
            with st.spinner("Thinking...", show_time=True):
                reply = chat_reply(prompt, history)
        except (ValueError, RuntimeError) as error:
            st.error(str(error), title="Could not get a reply", icon=":material/error:")
            st.session_state.messages.pop()
            return
        st.markdown(reply)

    st.session_state.messages.append({"role": "assistant", "kind": "text", "content": reply})

    is_new = st.session_state.conversation_id is None
    st.session_state.conversation_id = save_chat_turn(
        get_current_user()["user_id"], st.session_state.conversation_id, prompt, reply
    )
    # Rerun so the new conversation shows up in the sidebar history.
    if is_new and st.session_state.conversation_id:
        st.rerun()


def render_greeting(agent_type: str | None) -> None:
    name = get_current_user()["username"]
    with st.chat_message("assistant"):
        if agent_type == "blog":
            st.markdown(
                f"Hello {name}! I'm your SEO blog writer. What topic should your blog cover? "
                "I'll research it, find the right keywords and write the post for your review."
            )
            st.caption("Tip: set the tone, target audience and keywords in the sidebar.")
        elif agent_type == "image":
            st.markdown(
                f"Hello {name}! I'm your image generator. Describe the image you want. "
                "If you don't mention its purpose, style, orientation or quality, I'll ask you one question at a time, "
                "then create it for your review."
            )
            st.caption("You can approve it, edit the prompt, regenerate it or reject it, and download it once approved.")
        elif agent_type:
            label = CONTENT_TYPES[agent_type]["label"]
            st.markdown(f"Hello {name}! I'm your {label} agent. What would you like to create?")
        else:
            st.markdown(f"Hello {name}! How can I help you today?")


def render_chat() -> None:
    content_type = get_settings()["content_type"]
    # "auto" has no fixed agent: requests are routed by keywords, everything else is general chat.
    agent_type = None if content_type == "auto" else content_type

    info = CONTENT_TYPES[content_type]
    with st.container(horizontal=True, vertical_alignment="center"):
        if agent_type:
            st.subheader(f"{info['icon']} {AGENT_TITLES.get(agent_type, info['label'])}", anchor=False)
            st.badge(info["label"], icon=info["icon"], color=info["color"])
        else:
            st.subheader(":material/forum: Chat", anchor=False)
            st.badge(info["label"], icon=info["icon"], color=info["color"])

    if agent_type:
        st.caption("Describe what you need. The agent may ask a few questions, then drafts your content for review.")
    else:
        st.markdown(
            ":primary-background[:material/left_panel_open: Choose a content type in the sidebar to work with a content agent.]"
        )
        st.caption("Or just ask. In Auto mode, content requests go to the right agent automatically.")

    if not st.session_state.messages:
        render_greeting(agent_type)

    picked_answer = render_messages()

    closed = st.session_state.get("conversation_closed", False)
    if closed:
        st.info(
            "This conversation was interrupted (for example by an app restart) and can't continue.",
            title="Start a new conversation",
            icon=":material/info:",
        )

    prompt = st.chat_input(chat_placeholder(agent_type), submit_mode="disable", disabled=closed)

    # Suggestions only in Auto mode; a picked agent gets a greeting instead.
    if not st.session_state.messages and not agent_type:
        slot = st.empty()
        selected = slot.pills("Try asking", list(SUGGESTIONS), label_visibility="collapsed")
        if selected:
            prompt = SUGGESTIONS[selected]
        if prompt:
            slot.empty()

    pending = st.session_state.pending

    # An image review decision queued by a button here or in the Content tab.
    image_action = st.session_state.pop("image_action", None)

    if image_action and is_image_review(pending):
        handle_image_action(image_action)
    elif picked_answer:
        handle_answer(*picked_answer)
    elif prompt and is_image_review(pending):
        handle_image_decision_text(prompt)
    elif prompt and pending and not is_review(pending):
        response, answer_text = build_answer(pending, None, prompt)
        handle_answer(response, answer_text)
    elif prompt and is_review(pending):
        handle_decision_text(prompt)
    elif prompt and (agent := agent_type or detect_content_type(prompt)):
        handle_request(prompt, agent)
    elif prompt:
        handle_general_chat(prompt)
