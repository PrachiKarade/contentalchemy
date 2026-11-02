"""Research report view: the research agent's Markdown report as summary, findings and sources.

The report layout comes from research_agent.format_research_report. It is parsed
from the Markdown (not the stored JSON) so edits made during review show up too.
"""

import re

import streamlit as st

from src.web_app.components.theme import DRAFT_HEIGHT

SOURCE_LINE = re.compile(r"^\d+\.\s+\[(?P<title>.+?)\]\((?P<url>[^)\s]+)\)(?:\s+-\s+(?P<snippet>.*))?$")


def section(body: str, heading: str) -> str:
    """The text under a "## heading", up to the next "## " heading."""

    match = re.search(rf"^##\s+{heading}\s*$(.*?)(?=^##\s|\Z)", body, re.MULTILINE | re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def parse_research(body: str) -> dict:
    findings = re.findall(r"^###\s+\d+\.\s+(.+)$", section(body, "Key findings"), re.MULTILINE)
    sources = [match.groupdict() for line in section(body, "Sources").splitlines() if (match := SOURCE_LINE.match(line.strip()))]
    return {"summary": section(body, "Summary"), "findings": findings, "sources": sources}


def research_stats(body: str) -> dict:
    research = parse_research(body)
    return {"findings": len(research["findings"]), "sources": len(research["sources"])}


def render_sources(sources: list[dict]) -> None:
    if not sources:
        st.caption("No sources listed in this report.")
        return
    for index, source in enumerate(sources, start=1):
        with st.container(border=True):
            st.markdown(f"**{index}. [{source['title']}]({source['url']})**")
            if source.get("snippet"):
                st.caption(source["snippet"])


def render_research(body: str, key: str) -> None:
    """Show a research report with its key numbers, in the same scroll box as other drafts."""

    research = parse_research(body)

    with st.container(horizontal=True):
        st.metric("Findings", len(research["findings"]), border=True)
        st.metric("Sources", len(research["sources"]), border=True)
        st.metric("Words", len(body.split()), border=True)

    with st.container(border=True, height=DRAFT_HEIGHT, key=key):
        st.markdown(body)
