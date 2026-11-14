from langchain_core.tools import tool

from src.agents.research_agent import research_topic
from src.tools.internet_search_tool import internet_search_tool
from src.guardrails.tool_guardrails import  ResearchToolInput


@tool
def call_content_research_agent(
    topic: str,
    target_audience: str = "",
) -> dict:
    """
    Research a topic using the Content Research Agent.

    Returns research findings, a summary, and source information.
    Use this tool to gather factual information before writing a blog.
    """

    validated = ResearchToolInput(
        topic=topic,
        target_audience=target_audience,
    )
    return research_topic(  topic = validated.topic, target_audience= validated.target_audience, num_results=5, )


@tool
def internet_search(
    topic: str,
    primary_keyword: str = "",
) -> dict:
    """
    Search the internet for SEO opportunities.

    Returns search results and competitor page information.
    Use this tool to investigate primary keywords and related content.
    """
    return internet_search_tool(
        topic = topic,
        primary_keyword = primary_keyword,
        num_results = 5,
    )

blog_writer_tools = [ call_content_research_agent,  internet_search,]