
"""Content dashboard: approved content from all conversations, stored in MongoDB."""

import streamlit as st

from src.core.logger import setup_logger
from src.web_app.assistant import (
    CONTENT_TYPES,
    get_current_user,
    list_approved_content,
    remove_approved_content,
    save_approved_content,
)
from src.web_app.components.image_view import render_download, render_image
from src.web_app.components.research_view import STRATEGY_TAB, parse_research, render_sources, render_strategy
from src.web_app.components.state import go_to, make_title
from src.web_app.components.theme import DRAFT_HEIGHT

logger = setup_logger("content_dashboard")

SOURCES_TAB = ":material/link: Sources"
SEO_TAB = ":material/travel_explore: SEO details"

META_DESCRIPTION_LIMIT = 160


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
        # A multi-content piece belongs to a conversation with other pieces; all of them are removed.
        remove_approved_content(get_current_user()["user_id"], item.get("conversation_id", item["id"]))
    except Exception:
        logger.exception("Could not remove dashboard item")
        st.toast("Could not remove this content", icon=":material/error:")
        return
    st.toast("Removed from the dashboard", icon=":material/delete:")


def render_image_item(item: dict) -> None:
    """An approved image: preview, prompt and download. Images are not edited here."""

    data = render_image(item["body"], item.get("metadata", {}).get("image_prompt", ""))
    with st.container(horizontal=True):
        render_download(data, item["id"], key=f"download_{item['id']}", primary=False)
        st.button(
            "Remove",
            icon=":material/delete:",
            help="Remove from the dashboard. The conversation stays in your history.",
            key=f"delete_{item['id']}",
            on_click=remove_item,
            args=(item,),
        )


def item_title(item: dict) -> str:
    if item["type"] == "blog":
        # A blog body opens with "## Introduction"; use its SEO title instead.
        return item.get("data", {}).get("seo_title") or item["title"]
    if item["type"] == "research":
        return make_title(item["body"], item["title"])
    return item["title"]


def render_header(item: dict) -> None:
    """One line: "<Content type>: <title>" with the approval date beside it."""

    label = CONTENT_TYPES[item["type"]]["label"]
    with st.container(horizontal=True, vertical_alignment="bottom", gap="small"):
        st.subheader(f"{label}: {item_title(item)}", anchor=False, width="content")
        st.caption(f"{item['created_at']:%b %d, %Y}", width="content")


def render_item(item: dict) -> None:
    render_header(item)

    if item["type"] == "image":
        render_image_item(item)
        return

    research = parse_research(item["body"]) if item["type"] == "research" else None
    # The Content strategy tab shows only when the content strategist ran for this piece.
    strategy = ""
    if research:
        strategy = research["strategy"]
    elif item["type"] == "blog":
        strategy = item.get("strategy", "")
    strategy = strategy.strip()

    tab_names = [":material/visibility: Preview", ":material/edit_note: Edit"]
    if strategy:
        tab_names.append(STRATEGY_TAB)
    if research:
        tab_names.append(SOURCES_TAB)
    elif item["type"] == "blog":
        tab_names.append(SEO_TAB)
    tabs = dict(zip(tab_names, st.tabs(tab_names)))

    with tabs[tab_names[0]]:
        with st.container(border=True, height=DRAFT_HEIGHT, key=f"preview_{item['id']}"):
            st.markdown(research["report"] if research else item["body"])
    if strategy:
        with tabs[STRATEGY_TAB], st.container(height=DRAFT_HEIGHT, border=False):
            render_strategy(strategy)
    if SOURCES_TAB in tabs:
        with tabs[SOURCES_TAB], st.container(height=DRAFT_HEIGHT, border=False):
            render_sources(research["sources"])
    if SEO_TAB in tabs:
        with tabs[SEO_TAB], st.container(height=DRAFT_HEIGHT, border=False):
            render_seo_details(item["data"])
    with tabs[tab_names[1]]:
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
    items = list_approved_content(get_current_user()["user_id"])
    if not items:
        st.info(
            "Content you approve appears here.",
            title="No content yet",
            icon=":material/inventory_2:",
        )
        return

    # Preselect the conversation picked in the sidebar history, if it has approved content.
    selected = st.session_state.pop("dashboard_selected", None)
    # A multi-content conversation has one item per approved piece; select its first one.
    if selected:
        selected = next(
            (item["id"] for item in items if item["id"] == selected or item.get("conversation_id") == selected),
            selected,
        )
    approved_ids = {item["id"] for item in items}
    if selected and selected not in approved_ids and selected == st.session_state.get("conversation_id"):
        # Opened from history, but nothing approved yet: its draft is in the Content tab.
        st.info(
            "The conversation you opened has no approved content yet. Review its draft in the Content tab.",
            icon=":material/pending:",
        )
        st.button("Open Content tab", icon=":material/description:", on_click=go_to, args=("create",))

    present_types = [key for key in CONTENT_TYPES if any(item["type"] == key for item in items)]
    with st.container(horizontal=True, vertical_alignment="center"):
        selected_types = st.pills(
            "Filter by type",
            present_types,
            selection_mode="multi",
            default=present_types,
            format_func=lambda key: f"{CONTENT_TYPES[key]['icon']} {CONTENT_TYPES[key]['label']}",
            label_visibility="collapsed",
            width="content",
        )
        visible = [item for item in items if item["type"] in selected_types]
        items_by_id = {item["id"]: item for item in visible}

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
            label_visibility="collapsed",
            placeholder="No content matches the selected types",
            disabled=not items_by_id,
        )

    if item_id is None:
        return
    st.divider()
    render_item(items_by_id[item_id])
