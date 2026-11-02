
"""Content tab: the agent's draft for review, then the approved final content."""

import streamlit as st

from src.web_app.assistant import CONTENT_TYPES
from src.web_app.components.research_view import render_research
from src.web_app.components.state import cancel_edit, decide, go_to, is_review, reset_session, start_edit
from src.web_app.components.theme import DRAFT_HEIGHT

# Shown above a fresh draft to ask for the user's review.
READY_TITLES = {
    "research": "Your research report is ready",
    "blog": "Your SEO blog is ready",
    "linkedin": "Your LinkedIn post is ready",
    "image": "Your image prompt is ready",
}

STATUS_BADGES = {
    "pending": ("Awaiting review", ":material/pending:", "orange"),
    "approved": ("Approved", ":material/verified:", "green"),
    "rejected": ("Rejected", ":material/block:", "red"),
}


def render_preview(review: dict, content: str, key: str) -> None:
    if review["type"] == "research":
        render_research(content, key)
        return
    with st.container(border=True, height=DRAFT_HEIGHT, key=key):
        st.markdown(content)


def render_pending(review: dict) -> None:
    editing = st.session_state.get("review_editing", False)
    can_review = is_review(st.session_state.get("pending"))

    if review["edited"] and not editing:
        st.info("You edited this draft. Approve it to finish.", icon=":material/edit:")

    if editing:
        st.text_area("Edit draft", height=DRAFT_HEIGHT, key="edit_draft", label_visibility="collapsed")
    else:
        if review["type"] in READY_TITLES and not review["edited"]:
            st.info(
                "Review it below, then approve it, edit it or reject it.",
                title=READY_TITLES[review["type"]],
                icon=":material/rate_review:",
            )
        else:
            st.caption("Approve, edit or reject this draft. You can also reply in the Chat tab.")
        render_preview(review, review["content"], "preview_draft")

    error = st.session_state.get("review_error")
    if error:
        st.error(error, icon=":material/error:")

    with st.container(horizontal=True):
        if editing:
            st.button("Save changes", type="primary", icon=":material/save:", key="review_save", on_click=decide, args=("edit",))
            st.button("Cancel", icon=":material/close:", key="review_cancel", on_click=cancel_edit)
        else:
            st.button(
                "Approve",
                type="primary",
                icon=":material/verified:",
                disabled=not can_review,
                key="review_approve",
                on_click=decide,
                args=("approve",),
            )
            st.button("Edit", icon=":material/edit:", disabled=not can_review, key="review_edit", on_click=start_edit)
        st.button(
            "Reject",
            icon=":material/delete:",
            disabled=not can_review,
            key="review_reject",
            on_click=decide,
            args=("reject",),
        )


def render_final(review: dict) -> None:
    if review["status"] == "approved":
        st.success("Approved. Your final content is ready to download.", icon=":material/verified:")
        content = review["final_content"] or review["content"]
    else:
        st.warning("This draft was rejected.", icon=":material/block:")
        content = review["content"]

    render_preview(review, content, "preview_final")

    with st.container(horizontal=True):
        if review["status"] == "approved":
            st.download_button(
                "Download markdown",
                data=content,
                file_name=f"{review['type']}-{review['conversation_id'][-8:]}.md",
                mime="text/markdown",
                type="primary",
                icon=":material/download:",
                on_click="ignore",
                key="review_download",
            )
        st.button("New conversation", icon=":material/add_comment:", key="review_new", on_click=reset_session)


def render_content() -> None:
    st.subheader(":material/description: Content", anchor=False)

    review = st.session_state.get("review")
    if not review:
        st.info(
            "Choose a content type in the sidebar and describe what you need in the Chat tab. "
            "The agent's draft appears here for review.",
            title="No draft yet",
            icon=":material/forum:",
        )
        st.button("Go to chat", icon=":material/forum:", on_click=go_to, args=("chat",))
        return

    info = CONTENT_TYPES[review["type"]]
    status_label, status_icon, status_color = STATUS_BADGES[review["status"]]

    with st.container(horizontal=True, vertical_alignment="center"):
        st.badge(info["label"], icon=info["icon"], color=info["color"])
        st.badge(status_label, icon=status_icon, color=status_color)
        if review["edited"]:
            st.badge("Edited", icon=":material/edit:", color="blue")
    if review["topic"]:
        st.caption(f"Request: {review['topic']}")

    if review["status"] == "pending":
        render_pending(review)
    else:
        render_final(review)
