
"""Content tab: the agent's draft for review, then the approved final content."""

import streamlit as st

from langgraph.types import Command

from src.agents.linkedin_interaction import LINKEDIN_PROFILE_QUESTIONS
from src.core.logger import setup_logger
from src.web_app.assistant import (
    CONTENT_TYPES,
    advance_multi,
    create_content_conversation,
    get_current_user,
    get_pending_payload,
    get_thread_state,
    record_multi_answer,
    record_multi_review,
)
from src.web_app.components.chat import LiveProgress, build_answer, run_content_job
from src.web_app.components.image_view import render_download, render_image, render_image_actions
from src.web_app.components.research_view import parse_research, render_research, render_with_strategy
from src.web_app.components.state import (
    announce_handoff,
    apply_multi_review,
    cancel_edit,
    decide,
    finish_multi,
    go_to,
    is_image_review,
    is_multi,
    is_review,
    queue_multi_answer,
    question_owner,
    reset_session,
    show_multi_payload,
    start_edit,
    step_owner,
    sync_multi,
    tab_label,
    type_label,
)
from src.web_app.components.theme import DRAFT_HEIGHT
from src.utils.quality_validation import MAX_POINTS

logger = setup_logger("content_creation")

# Shown above a fresh draft to ask for the user's review.
READY_TITLES = {
    "research": "Your research report and content strategy are ready",
    "blog": "Your SEO blog is ready",
    "linkedin": "Your LinkedIn post is ready",
    "image": "Your image is ready",
}

STATUS_BADGES = {
    "pending": ("Awaiting review", ":material/pending:", "orange"),
    "approved": ("Approved", ":material/verified:", "green"),
    "rejected": ("Rejected", ":material/block:", "red"),
}


GRADE_COLORS = {
    "Excellent": "green",
    "Good": "blue",
    "Needs Improvement": "orange",
    "Poor": "red",
}


def render_quality(review: dict,key: str = "quality_score") -> None:
    """The draft's quality score, each check against its maximum, and how to improve it."""

    quality = review.get("quality")
    if review["type"] not in MAX_POINTS or not quality:
        return

    checks = quality.get("checks", {})
    max_points = MAX_POINTS[review["type"]]
    suggestions = quality.get("suggestions", [])

    color = GRADE_COLORS.get(quality.get("grade"), "gray")
    grade = f" · {quality['grade']}" if quality.get("grade") else ""

    # One compact row: highlighted score and grade, with the breakdown in a popover.
    with st.container(horizontal=True, vertical_alignment="center", gap="small", key=key):
        st.markdown(
            f":small[Quality score] :{color}-background[:small[**{quality['score']}**/100{grade}]]",
            width="content",
        )
        with st.popover("Breakdown", icon=":material/checklist:", type="tertiary"):
            for name, points in checks.items():
                ceiling = max_points.get(name, 20)
                st.progress(
                    min(points / ceiling, 1.0),
                    text=f"{name.replace('_', ' ').capitalize()}: {points}/{ceiling}",
                )
            if suggestions:
                st.markdown("**Suggestions**")
                st.markdown("\n".join(f"- {tip}" for tip in suggestions))


def render_preview(review: dict, content: str, key: str) -> None:
    # A multi-content research deliverable is the report alone, without a strategy section.
    if review["type"] == "research" and not review.get("multi"):
        render_research(content, key)
        return
    if review["type"] == "blog" and not review.get("multi"):
        render_with_strategy(content, review.get("strategy", ""), key, tab_label("blog"))
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
            title = READY_TITLES[review["type"]]
            if review["type"] == "research" and not parse_research(review["content"])["strategy"].strip():
                title = "Your research report is ready"
            st.info(
                "Review it below, then approve it, edit it or reject it.",
                title=title,
                icon=":material/rate_review:",
            )
        else:
            st.caption("Approve, edit or reject this draft. You can also reply in the Chat tab.")
        render_quality(review)
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
        content = review["final_content"] or review["content"]
    else:
        st.warning("This draft was rejected.", icon=":material/block:")
        content = review["content"]

    render_quality(review)
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


def render_image_review(review: dict) -> None:
    """The generated image: review it (decisions run in the Chat tab), or download it once approved."""

    if review["status"] == "pending":
        pending = st.session_state.get("pending")
        if not review["edited"]:
            where = "right here" if review.get("multi") else "in the Chat tab"
            st.info(
                f"Approve it, edit the prompt, regenerate it or reject it. A new image is generated {where}.",
                title=READY_TITLES["image"],
                icon=":material/rate_review:",
            )
        else:
            st.info("You edited the prompt for this image. Approve it to finish.", icon=":material/edit:")
        render_image(review["content"], review.get("image_prompt", ""), expanded_prompt=True)
        if is_image_review(pending):
            render_image_actions("review", can_regenerate=not pending.get("checkpoint_lost"))
        return

    if review["status"] != "approved":
        st.warning("This image was rejected.", icon=":material/block:")
    path = review["final_content"] or review["content"]
    data = render_image(path, review.get("image_prompt", ""))

    with st.container(horizontal=True):
        if review["status"] == "approved":
            render_download(data, review["conversation_id"], key="review_image_download")
        st.button("New conversation", icon=":material/add_comment:", key="review_new", on_click=reset_session)


# Multi-content: one tab per deliverable

MULTI_STATUS_BADGES = {
    "waiting": ("Not generated yet", ":material/hourglass_empty:", "gray"),
    "draft": ("Draft · review comes next", ":material/schedule:", "blue"),
    "unavailable": ("Not available", ":material/cloud_off:", "gray"),
    "failed": ("Unavailable", ":material/cloud_off:", "gray"),
    **STATUS_BADGES,
}

IMAGE_UNAVAILABLE = "Image generation is currently unavailable. Please try again later."

# What a deliverable that is not generated yet is waiting for.
MULTI_WAITING_HINTS = {
    "linkedin": "The LinkedIn writer starts after your profile answers, the research and the content strategy.",
    "blog": "The SEO blog writer starts after the research and the content strategy.",
    "research": "The research agent runs first; its report appears here once the content strategist has finished.",
    "strategy": "The content strategist plans the content after the research.",
    "image": "The image agent asks for any missing preferences in this tab, then generates the image.",
}


def multi_badge(status: str) -> None:
    label, icon, color = MULTI_STATUS_BADGES.get(status, MULTI_STATUS_BADGES["waiting"])
    st.badge(label, icon=icon, color=color)


def render_multi_item(deliverable: str, item: dict, conversation_id: str) -> None:
    """A deliverable that is not under review: waiting, drafted, or reviewed."""

    status = item["status"]
    with st.container(horizontal=True, vertical_alignment="center"):
        multi_badge(status)
        if item.get("edited"):
            st.badge("Edited", icon=":material/edit:", color="blue")

    if status == "waiting":
        st.caption(MULTI_WAITING_HINTS.get(deliverable, "This deliverable has not been generated yet."))
        return
    if status == "unavailable":
        st.caption("This draft was not reviewed before the app restarted, so it can't be shown.")
        return
    if status == "failed":
        st.info(IMAGE_UNAVAILABLE if deliverable == "image" else "This content could not be generated. Please try again later.",
                icon=":material/cloud_off:")
        return

    content = item["content"]
    preview = {"type": deliverable, "multi": True, "quality": item.get("quality")}

    if deliverable == "image":
        if status == "draft":
            st.caption("The image is generated. It comes up for review here next.")
        data = render_image(content, item.get("image_prompt", ""))
        if status == "approved":
            render_download(data, conversation_id, key="multi_image_download")
        return

    if status == "draft":
        st.caption("Drafted. Each piece comes up for review in turn after all pieces are written.")
    elif status == "rejected":
        st.warning("This draft was rejected.", icon=":material/block:")

    render_quality(preview, key=f"quality_score_{deliverable}",)
    
    with st.container(border=True, height=DRAFT_HEIGHT, key=f"multi_preview_{deliverable}"):
        st.markdown(content)

    if status == "approved":
        st.download_button(
            "Download markdown",
            data=content,
            file_name=f"{deliverable}-{conversation_id[-8:]}.md",
            mime="text/markdown",
            type="primary",
            icon=":material/download:",
            on_click="ignore",
            key=f"multi_download_{deliverable}",
        )


def tab_title(deliverable: str, multi: dict, pending: dict | None, job: dict | None) -> str:
    """The tab label with the content type's status, so each type's progress shows at a glance."""

    status = multi["items"].get(deliverable, {}).get("status", "waiting")
    if job and job.get("owner") == deliverable:
        suffix = " · working"
    elif not job and pending and status == "pending":
        suffix = " · your review"
    elif not job and pending and not (is_review(pending) or is_image_review(pending)) and question_owner(pending) == deliverable:
        suffix = " · your answer"
    elif status == "approved":
        suffix = " · approved"
    elif status == "rejected":
        suffix = " · rejected"
    elif status == "failed":
        suffix = " · unavailable"
    elif status == "draft":
        suffix = " · drafted"
    else:
        suffix = ""
    return tab_label(deliverable) + suffix


def question_position(payload: dict) -> str:
    if payload.get("interaction_type") == "linkedin_profile_question":
        keys = [question["key"] for question in LINKEDIN_PROFILE_QUESTIONS]
        if payload.get("lookup_key") in keys:
            return f"Question {keys.index(payload['lookup_key']) + 1} of {len(keys)}"
    if payload.get("is_last"):
        return "Last question"
    return ""


def next_button_label(payload: dict) -> str:
    if payload.get("agent") == "image_generator":
        return "Generate image" if payload.get("is_last") else "Next question"
    if payload.get("lookup_key") == LINKEDIN_PROFILE_QUESTIONS[-1]["key"]:
        return "Start writing"
    return "Next question"


def render_multi_question(payload: dict, multi: dict) -> None:
    """The agent's question, answered right in its content type's tab."""

    seq = multi.get("question_seq", 0)
    with st.container(border=True, key=f"multi_question_{seq}"):
        position = question_position(payload)
        if position:
            st.caption(position)
        st.markdown(f":material/help: **{payload['question']}**")
        choice = st.pills(
            "Options", payload.get("options", []), key=f"multi_answer_{seq}", label_visibility="collapsed"
        )

        if choice is None:
            st.caption("Pick an option, or choose Other to type your own answer.")
            return
        if choice != "Other":
            queue_multi_answer(*build_answer(payload, [choice], ""))
            st.rerun()

        other_text = st.text_input(
            "Your answer", placeholder="Type your answer", key=f"multi_other_{seq}", label_visibility="collapsed"
        )
        if st.button(next_button_label(payload), type="primary", icon=":material/arrow_forward:", key=f"multi_next_{seq}"):
            if not other_text.strip():
                st.toast("Type your answer first", icon=":material/info:")
                return
            queue_multi_answer(*build_answer(payload, [], other_text))
            st.rerun()


def render_answers(deliverable: str, multi: dict) -> None:
    answers = multi.get("qa", {}).get(deliverable) or []
    if answers:
        with st.expander(f"Your answers ({len(answers)})", icon=":material/fact_check:"):
            for question, answer in answers:
                st.markdown(f"**{question}**  \n{answer}")


def render_multi_tab(deliverable: str, multi: dict, review: dict | None, pending: dict | None, job: dict | None) -> None:
    item = multi["items"].get(deliverable, {"status": "waiting", "content": "", "edited": False})
    render_answers(deliverable, multi)

    if job:
        if job.get("owner") == deliverable:
            # The live progress of the running step is drawn below this tab's content.
            st.badge("Working on it", icon=":material/progress_activity:", color="blue")
            return
        render_multi_item(deliverable, item, multi["conversation_id"])
        return

    is_question = pending and not (is_review(pending) or is_image_review(pending))
    if is_question and question_owner(pending) == deliverable:
        render_multi_question(pending, multi)
        return

    active = review is not None and review["type"] == deliverable and item["status"] == "pending"
    if active and deliverable == "image":
        render_image_review(review)
    elif active:
        render_pending(review)
    else:
        render_multi_item(deliverable, item, multi["conversation_id"])


def working_title(job: dict) -> str:
    owner = job.get("owner")
    if owner is None:
        return "Analyzing your request..."
    if job["kind"] == "answer":
        return f"Saving your answer for the {type_label(owner)}..."
    if job["kind"] == "review":
        if job["decision"]["action"] in {"edit", "regenerate"} and owner == "image":
            return "Generating a new image..."
        return f"Saving your review of the {type_label(owner)}..."
    return f"Working on the {type_label(owner)}..."


def prepare_multi_job(job: dict, user_id: str):
    """(conversation id, value to run the workflow with) for a queued multi-content job."""

    multi = st.session_state["multi"]

    if job["kind"] == "start":
        if not job.get("conversation_id"):
            conversation_id, initial_state = create_content_conversation(user_id, "multi", job["prompt"], job["settings"])
            job.update(conversation_id=conversation_id, initial_state=initial_state)
            st.session_state["conversation_id"] = conversation_id
            multi["conversation_id"] = conversation_id
        conversation_id = job["conversation_id"]
        # Restarted after an interruption: carry on from the last finished step.
        return conversation_id, None if get_thread_state(conversation_id) else job["initial_state"]

    conversation_id = multi["conversation_id"]
    if not get_thread_state(conversation_id):
        raise ValueError(
            "This multi-content conversation can no longer continue (the app was restarted). Start a new conversation."
        )

    if job["kind"] in {"answer", "review"}:
        if not job.get("recorded"):
            if job["kind"] == "answer":
                record_multi_answer(user_id, conversation_id, job["answer_text"])
            else:
                record_multi_review(user_id, conversation_id, job["deliverable"], job["decision"])
            job["recorded"] = True
        if get_pending_payload(conversation_id) is None:
            # Already resumed before this run was interrupted.
            return conversation_id, None
        return conversation_id, Command(resume=job["response"] if job["kind"] == "answer" else job["decision"])

    return conversation_id, None


def retry_multi_job() -> None:
    st.session_state["multi_job"] = st.session_state.pop("multi_failed_job", None)


def run_multi_job(job: dict) -> None:
    """Run the queued multi-content work one agent step at a time, with live progress in its tab.

    Steps for the same content type run back to back. When the work moves to another content type
    (or an agent needs the user), the user is told and that type's tab opens on the next run.
    """

    multi = st.session_state["multi"]
    user_id = get_current_user()["user_id"]
    owner = new_owner = job.get("owner")
    progress = LiveProgress(working_title(job))

    try:
        conversation_id, value = prepare_multi_job(job, user_id)
        while True:
            payload, state, next_nodes = advance_multi(user_id, conversation_id, value, progress.note, progress.event)
            if job["kind"] == "review":
                apply_multi_review(job)
            # Later steps continue from the checkpoint, even if this run is interrupted.
            value = None
            job = {"kind": "continue", "owner": owner}
            st.session_state["multi_job"] = job
            sync_multi(state)

            if payload is not None or not next_nodes:
                break
            new_owner = step_owner(next_nodes[0], state, multi, owner)
            if new_owner != owner:
                break
    except Exception as error:
        logger.exception("Multi-content step failed")
        progress.finish("Something went wrong", state="error")
        st.error(str(error), icon=":material/error:")
        st.session_state["multi_failed_job"] = st.session_state.pop("multi_job", job)
        st.session_state["messages"].append(
            {"role": "assistant", "kind": "error", "content": f"The {type_label(owner)} step failed: {error}"}
        )
        st.button("Try again", icon=":material/refresh:", type="primary", key="multi_retry", on_click=retry_multi_job)
        return

    st.session_state.pop("multi_job", None)
    if payload is not None:
        waiting = "Ready for your review" if is_review(payload) or is_image_review(payload) else "Waiting for your answer"
        progress.finish(waiting)
        show_multi_payload(payload, state)
    elif not next_nodes:
        progress.finish("All done")
        finish_multi(state)
    else:
        progress.finish(f"{type_label(owner).capitalize()}: step finished")
        announce_handoff(owner, new_owner)
        st.session_state["multi_job"] = {"kind": "continue", "owner": new_owner}
    st.rerun()


def render_multi() -> None:
    """A multi-content conversation: a tab per content type with its progress, questions and drafts."""

    multi = st.session_state["multi"]
    review = st.session_state.get("review")
    pending = st.session_state.get("pending")
    job = st.session_state.get("multi_job")

    with st.container(horizontal=True, vertical_alignment="center"):
        if multi["done"]:
            st.badge("All reviewed", icon=":material/verified:", color="green")
        elif job:
            st.badge(f"Working on: {type_label(job.get('owner'))}", icon=":material/progress_activity:", color="blue")
        elif review:
            st.badge("Drafts ready for review", icon=":material/rate_review:", color="orange")
        elif pending:
            st.badge(f"Your answer: {type_label(question_owner(pending))}", icon=":material/help:", color="orange")
        elif st.session_state.get("multi_failed_job"):
            st.badge("Stopped", icon=":material/error:", color="red")
    if multi["topic"]:
        st.caption(f"Request: {multi['topic']}")

    if multi.get("notice"):
        st.info(multi["notice"], icon=":material/campaign:")

    if not multi["requested"]:
        # The request is still being analyzed; the tabs appear once its content types are known.
        if job:
            run_multi_job(job)
        elif st.session_state.get("multi_failed_job"):
            st.button("Try again", icon=":material/refresh:", type="primary", key="multi_retry", on_click=retry_multi_job)
        return

    selected = multi.get("tab") if multi.get("tab") in multi["requested"] else multi["requested"][0]
    titles = {deliverable: tab_title(deliverable, multi, pending, job) for deliverable in multi["requested"]}
    slot = None

    # A new key rebuilds the tabs, so the tab of the content type now being worked on opens.
    with st.container(key=f"multi_tabs_{multi.get('tab_seq', 0)}"):
        tabs = st.tabs(list(titles.values()), default=titles[selected])
        for tab, deliverable in zip(tabs, multi["requested"]):
            with tab:
                render_multi_tab(deliverable, multi, review, pending, job)
                if job and job.get("owner") == deliverable:
                    slot = st.container()

    if job:
        with slot if slot is not None else st.container():
            run_multi_job(job)
        return

    if st.session_state.get("multi_failed_job"):
        st.button("Try again", icon=":material/refresh:", type="primary", key="multi_retry", on_click=retry_multi_job)
    if multi["done"]:
        st.button("New conversation", icon=":material/add_comment:", key="multi_new", on_click=reset_session)


def render_content() -> None:
    # A request queued by the chat (SEO blog) runs here so its draft streams live on this page.
    job = st.session_state.pop("content_job", None)
    if job:
        run_content_job(job)
        return

    if is_multi() and st.session_state.get("multi"):
        render_multi()
        return

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

    if review["type"] == "image":
        render_image_review(review)
    elif review["status"] == "pending":
        render_pending(review)
    else:
        render_final(review)
