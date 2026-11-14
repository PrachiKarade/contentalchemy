"""Multi-content progress tracker: the agent steps of the running multi-content workflow.

Mirrors src/core/workflow.py: LinkedIn profile questions first (if a LinkedIn post was
requested), then the research agent and content strategist (for any text deliverable), then
each deliverable in the order the orchestrator runs it (a writer for the LinkedIn post and SEO
blog; preference questions, generation and review for the image), then the review of the
text deliverables. Steps marked INTERRUPT wait for the user.
"""

import streamlit as st

from src.web_app.assistant import CONTENT_TYPES

TEXT_DELIVERABLES = {"research", "strategy", "linkedin", "blog"}
FINAL_ITEM_STATUSES = {"approved", "rejected", "failed"}


def workflow_steps(multi: dict) -> list[dict]:
    """[{"label", "done", "interrupt"}] in the order the workflow runs them."""

    requested = multi["requested"]
    items = multi["items"]
    progress = multi.get("progress", {})
    steps = []

    def status(deliverable: str) -> str:
        return items.get(deliverable, {}).get("status", "waiting")

    if "linkedin" in requested:
        steps.append({"label": "Profile questions", "done": progress.get("profile", False), "interrupt": True})

    text = [deliverable for deliverable in requested if deliverable in TEXT_DELIVERABLES]
    if text:
        steps.append({"label": "Research", "done": progress.get("research", False), "interrupt": False})
        steps.append({"label": "Content strategy", "done": progress.get("strategy", False), "interrupt": False})

    for deliverable in requested:
        if deliverable in {"linkedin", "blog"}:
            steps.append(
                {
                    "label": f"{CONTENT_TYPES[deliverable]['label']} writer",
                    "done": status(deliverable) != "waiting",
                    "interrupt": False,
                }
            )
        elif deliverable == "image":
            generated = status("image") != "waiting"
            steps += [
                {"label": "Image questions", "done": progress.get("image_prefs", False) or generated, "interrupt": True},
                {"label": "Image generation", "done": generated, "interrupt": False},
                {"label": "Image review", "done": status("image") in FINAL_ITEM_STATUSES, "interrupt": True},
            ]

    if text:
        reviewed = progress.get("reviewed", False) or all(status(d) in FINAL_ITEM_STATUSES for d in text)
        steps.append({"label": "Content review", "done": reviewed, "interrupt": True})

    return steps


def render_multi_progress(multi: dict) -> None:
    """One row of badges: finished steps, the current step, and the steps still to come."""

    steps = workflow_steps(multi)
    if not steps:
        return

    current = None if multi.get("done") else next((index for index, step in enumerate(steps) if not step["done"]), None)

    with st.container(horizontal=True, vertical_alignment="center", gap="xsmall", key="multi_progress"):
        st.markdown(":small[**Workflow**]", width="content")
        for index, step in enumerate(steps):
            label = step["label"] + (" · waits for you" if step["interrupt"] and index == current else "")
            if step["done"]:
                st.badge(label, icon=":material/check_circle:", color="green")
            elif index == current:
                icon = ":material/pause_circle:" if step["interrupt"] else ":material/progress_activity:"
                st.badge(label, icon=icon, color="orange")
            else:
                st.badge(label, icon=":material/radio_button_unchecked:", color="gray")
