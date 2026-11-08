"""Research view: the research report and the content strategy built from it.

The research agent gathers sources; the content strategist then writes a
"# Research Report" and a "# Content Strategy" (see content_strategist_prompt),
joined by a "---" line. Sections are parsed from the Markdown (not the stored
JSON) so edits made during review show up too.

Older reports from research_agent.format_research_report ("## Summary",
"## Key findings", "## Sources") are still understood.
"""

import re

import streamlit as st

from src.web_app.components.theme import DRAFT_HEIGHT

# Headings may be numbered ("## 2. Executive Summary"), as the strategist prompt asks.
SUMMARY_HEADINGS = r"(?:Executive\s+)?Summary"
FINDINGS_HEADINGS = r"Key(?:\s+Research)?\s+Findings"
SOURCES_HEADINGS = r"Sources(?:\s+and\s+References)?|References"

STRATEGY_HEADING = re.compile(r"^#\s+Content\s+Strategy\s*$", re.MULTILINE | re.IGNORECASE)
MARKDOWN_LINK = re.compile(r"\[(?P<title>[^\]]+)\]\((?P<url>https?://[^)\s]+)\)")
BARE_URL = re.compile(r"(?<![(\[])(?P<url>https?://[^\s)\]>]+)")


def section(body: str, heading: str) -> str:
    """The text under a "## heading" (optionally numbered), up to the next "## " or "# " heading."""

    pattern = rf"^##\s+(?:\d+\.\s*)?(?:{heading})\s*:?\s*$(.*?)(?=^#{{1,2}}\s|\Z)"
    match = re.search(pattern, body, re.MULTILINE | re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


def split_report(body: str) -> tuple[str, str]:
    """Split the strategist's output into (research report, content strategy)."""

    match = STRATEGY_HEADING.search(body)
    if not match:
        return body.strip(), ""
    report = body[: match.start()].rstrip()
    # Drop the "---" separator the strategist puts between the two parts.
    report = re.sub(r"\n-{3,}\s*$", "", report).strip()
    return report, body[match.start():].strip()


def parse_findings(text: str) -> list[str]:
    """Finding titles: "### ..." headings, or top-level bullets when there are none."""

    headings = re.findall(r"^###\s+(?:\d+\.\s*)?(.+)$", text, re.MULTILINE)
    if headings:
        return [heading.strip().strip("*") for heading in headings]
    bullets = re.findall(r"^(?:[-*]|\d+\.)\s+(.+)$", text, re.MULTILINE)
    return [bullet.strip() for bullet in bullets]


def parse_sources(text: str) -> list[dict]:
    """Sources as {"title", "url", "snippet"}, from Markdown links or bare URLs, one per URL."""

    sources = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        for match in MARKDOWN_LINK.finditer(line):
            rest = line[match.end():].strip(" -:–—")
            sources.setdefault(match["url"], {"title": match["title"], "url": match["url"], "snippet": rest})
        for match in BARE_URL.finditer(MARKDOWN_LINK.sub("", line)):
            url = match["url"].rstrip(".,;")
            title = re.sub(r"^(?:[-*]|\d+\.)\s+", "", line[: match.start()]).strip(" -:–—*") or url
            sources.setdefault(url, {"title": title, "url": url, "snippet": ""})
    return list(sources.values())


def parse_research(body: str) -> dict:
    report, strategy = split_report(body)
    return {
        "report": report,
        "strategy": strategy,
        "summary": section(report, SUMMARY_HEADINGS),
        "findings": parse_findings(section(report, FINDINGS_HEADINGS)),
        "sources": parse_sources(section(report, SOURCES_HEADINGS)),
    }


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


def render_strategy(strategy: str) -> None:
    if strategy:
        st.markdown(strategy)
    else:
        st.caption("No content strategy in this report.")


def render_research(body: str, key: str) -> None:
    """Show the research report, content strategy and sources in tabs."""

    research = parse_research(body)

    report_tab, strategy_tab, sources_tab = st.tabs(
        [":material/description: Research report", ":material/strategy: Content strategy", ":material/link: Sources"]
    )
    with report_tab, st.container(border=True, height=DRAFT_HEIGHT, key=key):
        st.markdown(research["report"])
    with strategy_tab, st.container(border=True, height=DRAFT_HEIGHT, key=f"{key}_strategy"):
        render_strategy(research["strategy"])
    with sources_tab, st.container(border=True, height=DRAFT_HEIGHT, key=f"{key}_sources"):
        render_sources(research["sources"])
