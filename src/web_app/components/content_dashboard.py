
"""Content dashboard: approved content from all conversations, stored in MongoDB."""

import re

import streamlit as st

from src.core.logger import setup_logger
from src.web_app.assistant import (
    CONTENT_TYPES,
    get_current_user,
    list_approved_content,
    remove_approved_content,
    save_approved_content,
)
from src.web_app.components.research_view import parse_research, render_sources
from src.web_app.components.state import go_to, make_title
from src.web_app.components.theme import DRAFT_HEIGHT

logger = setup_logger("content_dashboard")

LINKEDIN_CHAR_LIMIT = 3000
META_DESCRIPTION_LIMIT = 160
WORDS_PER_MINUTE = 200


def content_stats(item: dict) -> dict:
    body = item["body"]
    words = len(body.split())
    return {
        "words": words,
        "read_time": max(1, round(words / WORDS_PER_MINUTE)),
        "characters": len(body),
        "headings": len(re.findall(r"^#{1,6}\s", body, re.MULTILINE)),
        "hashtags": len(re.findall(r"#\w+", body)),
    }


def render_stats(item: dict) -> None:
    stats = content_stats(item)
    with st.container(horizontal=True):
        st.metric("Words", stats["words"], border=True)
        st.metric("Read time", f"{stats['read_time']} min", border=True)
        if item["type"] == "linkedin":
            st.metric(
                "Characters",
                f"{stats['characters']} / {LINKEDIN_CHAR_LIMIT}",
                border=True,
                help="LinkedIn posts are limited to 3000 characters.",
            )
            st.metric("Hashtags", stats["hashtags"], border=True)
        elif item["type"] == "research":
            research = parse_research(item["body"])
            st.metric("Findings", len(research["findings"]), border=True)
            st.metric("Sources", len(research["sources"]), border=True)
        else:
            st.metric("Characters", stats["characters"], border=True)
            st.metric("Headings", stats["headings"], border=True)


def render_seo_details(data: dict) -> None:
    """The SEO blog's metadata, kept out of the article itself."""

    if not data.get("seo_title"):
        st.caption("No SEO details were saved for this blog.")
        return

    meta = data.get("meta_description", "")
    st.markdown(f"**SEO title**  \n{data['seo_title']}")
    st.markdown(f"**Meta description** ({len(meta)} / {META_DESCRIPTION_LIMIT} characters)  \n{meta}")
    st.markdown(f"**URL slug**  \n`{data.get('url_slug', '')}`")
    st.markdown(f"**Search intent**  \n{data.get('search_intent', '')}")

    st.markdown("**Keywords**")
    with st.container(horizontal=True):
        if data.get("primary_keyword"):
            st.badge(data["primary_keyword"], icon=":material/key:", color="green")
        for keyword in data.get("secondary_keywords", []):
            st.badge(keyword, color="gray")

    outline = [item for item in data.get("article_outline", []) if isinstance(item, (dict, str))]
    if outline:
        st.markdown("**Article outline**")
        st.markdown(
            "\n".join(
                f"- {item}" if isinstance(item, str)
                else f"{'    ' if item.get('level') == 'H3' else ''}- {item.get('heading', '')}"
                for item in outline
            )
        )


def save_edit(item: dict) -> None:
    try:
        save_approved_content(get_current_user()["user_id"], item, st.session_state[f"edit_{item['id']}"])
    except Exception as error:
        logger.exception("Could not save dashboard edit")
        st.toast(f"Could not save: {error}", icon=":material/error:")
        return
    st.toast("Changes saved", icon=":material/check_circle:")


def remove_item(item: dict) -> None:
    try:
        remove_approved_content(get_current_user()["user_id"], item["id"])
    except Exception:
        logger.exception("Could not remove dashboard item")
        st.toast("Could not remove this content", icon=":material/error:")
        return
    st.toast("Removed from the dashboard", icon=":material/delete:")


def render_item(item: dict) -> None:
    info = CONTENT_TYPES[item["type"]]

    with st.container(horizontal=True, vertical_alignment="center"):
        st.badge(info["label"], icon=info["icon"], color=info["color"])
        st.badge("Approved", icon=":material/verified:", color="green")
        st.caption(f"Approved {item['created_at']:%b %d, %H:%M}")
    st.subheader(make_title(item["body"], item["title"]), anchor=False)
    st.caption(f"Request: {item['prompt']}")

    render_stats(item)

    tab_names = [":material/visibility: Preview", ":material/edit_note: Edit"]
    if item["type"] == "research":
        tab_names.append(":material/link: Sources")
    elif item["type"] == "blog":
        tab_names.append(":material/travel_explore: SEO details")
    preview_tab, edit_tab, *extra_tab = st.tabs(tab_names)
    with preview_tab:
        with st.container(border=True, height=DRAFT_HEIGHT, key=f"preview_{item['id']}"):
            st.markdown(item["body"])
    if extra_tab:
        with extra_tab[0], st.container(height=DRAFT_HEIGHT, border=False):
            if item["type"] == "research":
                render_sources(parse_research(item["body"])["sources"])
            else:
                render_seo_details(item["data"])
    with edit_tab:
        st.text_area(
            "Content",
            value=item["body"],
            height=DRAFT_HEIGHT,
            key=f"edit_{item['id']}",
            label_visibility="collapsed",
        )
        st.button(
            "Save changes",
            icon=":material/save:",
            type="primary",
            key=f"save_{item['id']}",
            on_click=save_edit,
            args=(item,),
        )

    with st.container(horizontal=True):
        st.download_button(
            "Download markdown",
            data=item["body"],
            file_name=f"{item['type']}-{item['id'][-8:]}.md",
            mime="text/markdown",
            icon=":material/download:",
            on_click="ignore",
        )
        st.button(
            "Remove",
            icon=":material/delete:",
            help="Remove from the dashboard. The conversation stays in your history.",
            key=f"delete_{item['id']}",
            on_click=remove_item,
            args=(item,),
        )


def render_dashboard() -> None:
    st.subheader("Content dashboard", anchor=False)
    st.caption("All content you have approved. Pick a piece to preview, edit or download it.")

    items = list_approved_content(get_current_user()["user_id"])
    if not items:
        st.info(
            "Content you approve appears here.",
            title="No content yet",
            icon=":material/inventory_2:",
        )
        return

    present_types = [key for key in CONTENT_TYPES if any(item["type"] == key for item in items)]
    selected_types = st.pills(
        "Filter by type",
        present_types,
        selection_mode="multi",
        default=present_types,
        format_func=lambda key: f"{CONTENT_TYPES[key]['icon']} {CONTENT_TYPES[key]['label']}",
    )

    visible = [item for item in items if item["type"] in selected_types]
    if not visible:
        st.caption("No content matches the selected types.")
        return

    items_by_id = {item["id"]: item for item in visible}

    # Preselect the conversation picked in the sidebar history, if it has approved content.
    selected = st.session_state.pop("dashboard_selected", None)
    if selected and selected not in items_by_id and selected == st.session_state.get("conversation_id"):
        # Opened from history, but nothing approved yet: its draft is in the Content tab.
        st.info(
            "The conversation you opened has no approved content yet. Review its draft in the Content tab.",
            icon=":material/pending:",
        )
        st.button("Open Content tab", icon=":material/description:", on_click=go_to, args=("create",))
    if selected in items_by_id:
        st.session_state["dashboard_item"] = selected
    elif st.session_state.get("dashboard_item") not in items_by_id:
        st.session_state.pop("dashboard_item", None)

    item_id = st.selectbox(
        "Content piece",
        list(items_by_id),
        format_func=lambda key: (
            f"{CONTENT_TYPES[items_by_id[key]['type']]['label']} · {items_by_id[key]['title']}"
        ),
        key="dashboard_item",
    )
    st.divider()
    render_item(items_by_id[item_id])
