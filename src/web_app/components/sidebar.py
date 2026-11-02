
"""Sidebar with the user, new conversation, content type, brand voice and history."""

from datetime import datetime, timezone

import streamlit as st

from src.web_app.assistant import CONTENT_TYPES, get_current_user, list_history, ui_type
from src.web_app.components.state import change_content_type, open_conversation, reset_session

# "auto" picks the agent from the message, or chats generally.
CREATE_TYPES = ["auto", "linkedin", "blog", "research", "image"]

TONES = ["Professional", "Friendly", "Bold", "Witty", "Inspirational"]

CONTENT_TYPE_CAPTIONS = {
    "auto": "Picks the right agent from your message",
    "research": "In-depth brief with key findings",
    "blog": "Long-form, search-optimized article",
    "linkedin": "Engaging post with hashtags",
    "image": "Optimized image-generation prompt",
}

HISTORY_TITLE_LENGTH = 34

SIDEBAR_KEYS = ["content_type", "tone", "audience", "keywords"]


def history_group(updated_at: datetime, now: datetime) -> str:
    days = (now.date() - updated_at.date()).days
    if days <= 0:
        return "Today"
    if days == 1:
        return "Yesterday"
    if days < 7:
        return "Previous 7 days"
    if days < 30:
        return "Previous 30 days"
    return "Older"


def render_user(username: str) -> None:
    with st.container(key="user_card"):
        st.caption("Signed in as")
        st.markdown(f":material/account_circle: **{username}**")
    st.button(
        "New conversation",
        icon=":material/add_comment:",
        width="stretch",
        key="new_conversation",
        on_click=reset_session,
    )


def render_history(user_id: str) -> None:
    st.markdown(":material/history: **History**")
    conversations = list_history(user_id)
    if not conversations:
        st.caption("Your conversations will appear here.")
        return

    # MongoDB returns naive UTC datetimes.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    active_id = st.session_state.get("conversation_id")
    group = None

    with st.container(gap="xxsmall", key="history_list"):
        for conversation in conversations:
            updated_at = conversation["updated_at"].replace(tzinfo=None)
            if history_group(updated_at, now) != group:
                group = history_group(updated_at, now)
                st.caption(group)

            info = CONTENT_TYPES.get(ui_type(conversation["content_type"]), CONTENT_TYPES["chat"])
            title = conversation["title"]
            if len(title) > HISTORY_TITLE_LENGTH:
                title = title[: HISTORY_TITLE_LENGTH - 3] + "..."
            is_active = conversation["conversation_id"] == active_id

            st.button(
                title,
                icon=info["icon"],
                type="secondary" if is_active else "tertiary",
                width="stretch",
                help=f"{info['label']} · {conversation['status'].replace('_', ' ')}",
                key=f"history_{conversation['conversation_id']}",
                on_click=open_conversation,
                args=(user_id, conversation["conversation_id"]),
            )


def render_sidebar() -> None:
    user = get_current_user()

    # New conversation, reject or a history pick queue the sidebar values; set them before the widgets render.
    for key, value in st.session_state.pop("sidebar_values", {}).items():
        st.session_state[key] = value

    # Saved conversations may use a tone that is not offered here.
    if st.session_state.get("tone") not in TONES:
        st.session_state.pop("tone", None)

    # Streamlit drops widget values when the page changes; re-store them so they persist.
    for key in SIDEBAR_KEYS:
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]

    with st.sidebar:
        render_user(user["username"])

        content_type = st.selectbox(
            "Content type",
            CREATE_TYPES,
            format_func=lambda key: CONTENT_TYPES[key]["label"],
            key="content_type",
            on_change=change_content_type,
        )
        st.caption(CONTENT_TYPE_CAPTIONS[content_type])

        with st.container(border=True, key="brand_voice"):
            st.markdown(":material/record_voice_over: **Brand voice**")
            st.caption("Optional. Leave blank to let the assistant decide.")
            # LinkedIn posts take their tone from the user profile.
            if content_type != "linkedin":
                st.selectbox("Tone", TONES, index=None, placeholder="Choose a tone", key="tone")
            st.text_input("Target audience", placeholder="e.g. SaaS founders", key="audience")
            st.text_input("Target keywords", placeholder="e.g. AI marketing, automation", key="keywords")

        render_history(user["user_id"])


def get_settings() -> dict:
    """Read the sidebar values from session state."""

    return {
        "content_type": st.session_state.get("content_type", "auto"),
        "tone": st.session_state.get("tone"),
        "audience": st.session_state.get("audience", "").strip(),
        "keywords": st.session_state.get("keywords", "").strip(),
    }

