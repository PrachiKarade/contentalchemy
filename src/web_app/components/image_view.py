
"""Image generator UI: the generated image, its review actions and the download.

The preference questions use the chat's normal question bubbles (one question at a time).

Shared by the chat window and the Content tab. Review buttons only queue the
decision (state.queue_image_action); the chat page runs it so the user sees
progress while a new image is generated.
"""

from pathlib import Path

import streamlit as st

from src.web_app.components.state import (
    cancel_image_edit,
    queue_image_action,
    start_image_edit,
)

# Display width in pixels; generated images are 1024px or larger.
IMAGE_WIDTH = 560


# Image and review


def read_image(path: str) -> bytes | None:
    try:
        return Path(path).read_bytes()
    except OSError:
        return None


def render_image(path: str, prompt: str = "", expanded_prompt: bool = False) -> bytes | None:
    """Show the image (or a notice if the file is gone) and its prompt. Returns the image bytes."""

    data = read_image(path)
    if data is None:
        st.warning("The image file could not be found on this server.", icon=":material/broken_image:")
    else:
        st.image(data, width=IMAGE_WIDTH)

    if prompt:
        with st.expander("Image prompt", icon=":material/edit_note:", expanded=expanded_prompt):
            st.markdown(prompt)
    return data


def render_download(data: bytes | None, conversation_id: str, key: str, primary: bool = True) -> None:
    st.download_button(
        "Download image",
        data=data or b"",
        file_name=f"image-{conversation_id[-8:]}.png",
        mime="image/png",
        type="primary" if primary else "secondary",
        icon=":material/download:",
        on_click="ignore",
        disabled=data is None,
        key=key,
    )


def render_image_actions(prefix: str, can_regenerate: bool = True) -> None:
    """Approve / edit / regenerate / reject for the image under review."""

    error = st.session_state.get("review_error")
    if error:
        st.error(error, icon=":material/error:")

    if st.session_state.get("image_editing"):
        st.text_area(
            "Edit the image prompt",
            height=160,
            key="image_edit_prompt",
            help="The agent refines your prompt with your preferences, then generates a new image.",
        )
        with st.container(horizontal=True):
            st.button(
                "Generate with this prompt",
                type="primary",
                icon=":material/auto_awesome:",
                key=f"{prefix}_image_save",
                on_click=queue_image_action,
                args=("edit",),
            )
            st.button("Cancel", icon=":material/close:", key=f"{prefix}_image_cancel", on_click=cancel_image_edit)
        return

    if not can_regenerate:
        st.caption("This image can only be approved or rejected because the app was restarted.")

    with st.container(horizontal=True):
        st.button(
            "Approve",
            type="primary",
            icon=":material/verified:",
            key=f"{prefix}_image_approve",
            on_click=queue_image_action,
            args=("approve",),
        )
        st.button(
            "Edit prompt",
            icon=":material/edit:",
            key=f"{prefix}_image_edit",
            disabled=not can_regenerate,
            on_click=start_image_edit,
        )
        st.button(
            "Regenerate",
            icon=":material/refresh:",
            key=f"{prefix}_image_regenerate",
            disabled=not can_regenerate,
            on_click=queue_image_action,
            args=("regenerate",),
        )
        st.button(
            "Reject",
            icon=":material/delete:",
            key=f"{prefix}_image_reject",
            on_click=queue_image_action,
            args=("reject",),
        )


def render_image_message(message: dict, active: bool, approved: bool) -> None:
    """A generated image in the chat: review actions while pending, download once approved."""

    review = st.session_state.get("review") or {}
    pending = st.session_state.get("pending") or {}

    if active:
        st.markdown("**Here's your image.** Approve it, edit the prompt, regenerate it or reject it.")
    elif approved:
        st.markdown("**Your approved image.**")

    data = render_image(message["content"], message.get("image_prompt", ""), expanded_prompt=False)

    if active:
        render_image_actions("chat", can_regenerate=not pending.get("checkpoint_lost"))
    elif approved:
        render_download(data, review.get("conversation_id", "image"), key="chat_image_download")
