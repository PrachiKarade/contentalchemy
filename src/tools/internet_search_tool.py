
from src.core.logger import setup_logger
from src.integrations.serp_client import search_web
from src.guardrails.tool_guardrails import  InternetSearchToolInput

logger = setup_logger("internet_search_tool")


def internet_search_tool(
    topic: str,
    primary_keyword: str = "",
    num_results: int = 5,
) -> dict:
    """
    Gather web search results to support SEO content planning.

    Returns search results for the topic and primary keyword.
    """

    if not topic or not topic.strip():
        raise ValueError("Topic cannot be empty.")

    topic = topic.strip()
    primary_keyword = primary_keyword.strip()

    validated = InternetSearchToolInput(topic = topic , primary_keyword= primary_keyword)

    logger.info("Starting SEO search for topic: %s", topic)

    # Search 1: Broad topic research
    topic_results = search_web(
        query = validated.topic,
        num_results = num_results,
    )

    # Search 2: Targeted primary keyword search
    keyword_results = []
    if primary_keyword and primary_keyword.lower() != topic.lower():
        
        keyword_results = search_web(
            query = validated.primary_keyword,
            num_results = num_results,
        )

    # Deduplicate results by URL
    unique_results = []
    seen_urls = set()

    for result in topic_results + keyword_results:
        url = result.get("url", "").strip()

        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_results.append(result)

    if not unique_results:
        logger.warning("No SEO search results found for topic: %s", topic)

    logger.info(
        "SEO search completed. Found %s unique results.",
        len(unique_results),
    )

    return {
        "topic": topic,
        "primary_keyword": primary_keyword or topic,
        "search_results": unique_results,
        "competitor_topics": [
            {
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "snippet": result.get("snippet", ""),
            }
            for result in unique_results
        ],
    }


# --------------------------------------------------------
# Example usage of the internet_search_tool function
# --------------------------------------------------------


"""
if __name__ == "__main__":
    result = internet_search_tool(
        topic="AI content marketing trends",
        primary_keyword="AI content marketing",
        num_results=5,
    )

    print(result)
"""
