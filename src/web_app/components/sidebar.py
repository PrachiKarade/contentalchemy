
"""Sidebar with the user, new conversation, content type, brand voice and history.

Content type, tone and audience are small option buttons (pills) so every choice is visible.
Picking a content type makes its agent introduce itself in the chat (see state.change_content_type).
"""

from datetime import date, datetime, timezone

import streamlit as st

from src.web_app.assistant import CONTENT_TYPES, get_current_user, list_history, ui_type
from src.web_app.components.state import change_content_type, open_conversation, reset_session

# "auto" picks the agent from the message, or chats generally.
CREATE_TYPES = ["auto", "linkedin", "blog", "research", "image", "multi"]

TONES = ["Professional", "Friendly", "Bold", "Witty", "Inspirational"]

OTHER_AUDIENCE = "Other"
AUDIENCES = ["Marketers", "SaaS founders", "Small businesses", "Developers", "Executives", "Students", OTHER_AUDIENCE]

CONTENT_TYPE_CAPTIONS = {
    "auto": "Picks the right agent from your message",
    "research": "Research report with a content strategy",
    "blog": "Long-form, search-optimized article",
    "linkedin": "Engaging post with hashtags",
    "image": "AI-generated image you can review and download",
    "multi": "Several pieces in one request, e.g. LinkedIn post + SEO blog + image",
}

HISTORY_TITLE_LENGTH = 34

# Past this many topics the history list keeps a fixed height (px, about five rows) and scrolls.
HISTORY_VISIBLE = 5
HISTORY_HEIGHT = 200

SIDEBAR_KEYS = ["content_type", "tone", "audience", "audience_custom", "keywords", "history_date"]


def date_label(day: date, today: date, count: int) -> str:
    days = (today - day).days
    if days == 0:
        name = "Today"
    elif days == 1:
        name = "Yesterday"
    else:
        name = day.strftime("%a, %b %d, %Y")
    return f"{name} ({count})"


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


def open_searched_conversation(user_id: str) -> None:
    conversation_id = st.session_state.get("history_search")
    # Clear the search so the dropdown is ready for the next lookup.
    st.session_state["history_search"] = None
    if conversation_id:
        open_conversation(user_id, conversation_id)


def render_history_search(user_id: str, conversations: list[dict]) -> None:
    """Type-to-search dropdown over every conversation, across all days."""

    if not conversations:
        return
    by_id = {conversation["conversation_id"]: conversation for conversation in conversations}

    def label(conversation_id: str) -> str:
        conversation = by_id[conversation_id]
        info = CONTENT_TYPES.get(ui_type(conversation["content_type"]), CONTENT_TYPES["chat"])
        day = conversation["updated_at"].strftime("%b %d")
        return f"{info['icon']} {conversation['title']} · {day}"

    st.selectbox(
        "Search history",
        list(by_id),
        index=None,
        format_func=label,
        placeholder="Search history...",
        key="history_search",
        on_change=open_searched_conversation,
        args=(user_id,),
        label_visibility="collapsed",
    )


def render_history(user_id: str) -> None:
    st.markdown(":material/history: **History**")
    conversations = list_history(user_id)

    # MongoDB returns naive UTC datetimes.
    today = datetime.now(timezone.utc).date()
    by_day: dict[str, list[dict]] = {today.isoformat(): []}
    for conversation in conversations:
        day = conversation["updated_at"].replace(tzinfo=None).date().isoformat()
        by_day.setdefault(day, []).append(conversation)
    days = [today.isoformat()] + sorted((day for day in by_day if day != today.isoformat()), reverse=True)

    # Today is selected by default; a stale pick (e.g. after midnight) falls back to it.
    if st.session_state.get("history_date") not in days:
        st.session_state["history_date"] = days[0]
    selected = st.selectbox(
        "History date",
        days,
        format_func=lambda day: date_label(date.fromisoformat(day), today, len(by_day[day])),
        key="history_date",
        label_visibility="collapsed",
    )

    render_history_search(user_id, conversations)

    # Up to HISTORY_VISIBLE topics show in full; more than that scroll in a fixed-height list.
    active_id = st.session_state.get("conversation_id")
    height = HISTORY_HEIGHT if len(by_day[selected]) > HISTORY_VISIBLE else "content"
    with st.container(height=height, gap="xxsmall", border=False, key="history_list"):
        if not by_day[selected]:
            st.caption("No conversations on this day yet." if conversations else "Your conversations will appear here.")
        for conversation in by_day[selected]:
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


def render_hint(key: str, message: str) -> None:
    """Small blinking alert that nudges the user toward a sidebar setting."""

    with st.container(key=key):
        st.markdown(f":material/tips_and_updates: {message}")


def section_label(text: str) -> None:
    st.html(f'<div class="ca-section-label"><p>{text}</p></div>')


def field_label(text: str) -> None:
    st.html(f'<div class="ca-field-label"><p>{text}</p></div>')


def audience_value() -> str:
    audience = st.session_state.get("audience")
    if audience == OTHER_AUDIENCE:
        return (st.session_state.get("audience_custom") or "").strip()
    return audience or ""


def brand_voice_empty(content_type: str) -> bool:
    tone_set = content_type != "linkedin" and st.session_state.get("tone")
    keywords = (st.session_state.get("keywords") or "").strip()
    return not (tone_set or audience_value() or keywords)


def normalize_sidebar_state() -> None:
    """Saved conversations may hold values the option buttons don't offer."""

    if st.session_state.get("content_type") not in CREATE_TYPES:
        st.session_state["content_type"] = "auto"

    if st.session_state.get("tone") not in TONES:
        st.session_state.pop("tone", None)

    audience = st.session_state.get("audience")
    if audience and audience not in AUDIENCES:
        # A free-text audience (from history) goes into the "Other" field.
        st.session_state["audience_custom"] = audience
        st.session_state["audience"] = OTHER_AUDIENCE
    elif not audience:
        st.session_state["audience"] = None


def render_content_type() -> str:
    with st.container(border=True, key="content_type_box"):
        section_label("Content type")
        if st.session_state.get("content_type", "auto") == "auto":
            render_hint("content_type_hint", "Pick a content type to meet its agent")
        content_type = st.pills(
            "Content type",
            CREATE_TYPES,
            format_func=lambda key: f"{CONTENT_TYPES[key]['icon']} {CONTENT_TYPES[key]['label']}",
            required=True,
            key="content_type",
            on_change=change_content_type,
            label_visibility="collapsed",
        )
        st.caption(CONTENT_TYPE_CAPTIONS[content_type])
    return content_type


def render_brand_voice(content_type: str) -> None:
    with st.container(border=True, key="brand_voice"):
        section_label("Brand voice")
        if brand_voice_empty(content_type):
            render_hint("brand_voice_hint", "Set your brand voice so content sounds like you")

        # LinkedIn posts take their tone from the user profile.
        if content_type != "linkedin":
            field_label("Tone")
            st.pills("Tone", TONES, key="tone", label_visibility="collapsed")

        field_label("Target audience")
        audience = st.pills("Target audience", AUDIENCES, key="audience", label_visibility="collapsed")
        if audience == OTHER_AUDIENCE:
            st.text_input(
                "Custom audience",
                placeholder="e.g. HR leaders in fintech",
                key="audience_custom",
                label_visibility="collapsed",
            )

        field_label("Target keywords")
        st.text_input(
            "Target keywords",
            placeholder="e.g. AI marketing, automation",
            key="keywords",
            label_visibility="collapsed",
        )
        st.caption("All optional. Leave blank to let the assistant decide.")


def render_sidebar() -> None:
    user = get_current_user()

    # New conversation, reject or a history pick queue the sidebar values; set them before the widgets render.
    for key, value in st.session_state.pop("sidebar_values", {}).items():
        st.session_state[key] = value

    normalize_sidebar_state()

    # Streamlit drops widget values when the page changes; re-store them so they persist.
    for key in SIDEBAR_KEYS:
        if key in st.session_state:
            st.session_state[key] = st.session_state[key]

    with st.sidebar:
        render_user(user["username"])
        content_type = render_content_type()
        render_brand_voice(content_type)
        render_history(user["user_id"])


def get_settings() -> dict:
    """Read the sidebar values from session state."""

    return {
        "content_type": st.session_state.get("content_type") or "auto",
        "tone": st.session_state.get("tone"),
        "audience": audience_value(),
        "keywords": (st.session_state.get("keywords") or "").strip(),
    }
