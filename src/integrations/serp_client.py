
import os
from urllib.parse import urlparse

import serpapi
from tavily import TavilyClient
from dotenv import load_dotenv

from src.core.logger import setup_logger


load_dotenv()

logger = setup_logger("Web Search Agent")


def is_valid_source_url(url: str) -> bool:
    if not url:
        return False

    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        return False

    hostname = (parsed.hostname or "").lower()

    if hostname == "google.com" or hostname.endswith(".google.com"):
        return False

    return True


def search_google(query: str, num_results: int) -> list[dict]:
    """Search Google using SerpApi."""

    api_key = os.getenv("SERPAPI_KEY")

    if not api_key:
        logger.warning("SERPAPI_KEY is not configured.")
        return []

    client = serpapi.Client(api_key=api_key)

    response = client.search(
        engine="google",
        q=query,
        num=num_results,
        no_cache=True,
    )

    organic_results = response.get("organic_results", [])

    results = [
        {
            "title": item.get("title", ""),
            "url": item.get("link", ""),
            "snippet": item.get("snippet", ""),
        }
        for item in organic_results
        if is_valid_source_url(item.get("link", ""))
    ]

    logger.info(
        "Google search completed | Received: %d | Valid: %d",
        len(organic_results),
        len(results),
    )

    return results


def search_tavily(query: str, num_results: int) -> list[dict]:
    """Search the web using Tavily."""

    api_key = os.getenv("TAVILY_API_KEY")

    if not api_key:
        logger.warning("TAVILY_API_KEY is not configured.")
        return []

    client = TavilyClient(api_key=api_key)

    response = client.search(
        query=query,
        search_depth="basic",
        max_results=num_results,
    )

    results = [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("content", ""),
        }
        for item in response.get("results", [])
        if is_valid_source_url(item.get("url", ""))
    ]

    logger.info("Tavily search completed | Valid: %d", len(results))

    return results


def search_web(query: str, num_results: int = 5) -> list[dict]:
    """
    Search using SerpApi Google first.
    Fall back to Tavily if Google fails or returns no valid results.
    """

    if not query or not query.strip():
        raise ValueError("Search query cannot be empty")

    num_results = max(1, min(num_results, 10))
    query = query.strip()

    try:
        logger.info("Trying Google search through SerpApi.")

        results = search_google(query, num_results)

        if results:
            logger.info("Using Google search results.")
            return results

        logger.warning(
            "Google returned no valid results. Trying Tavily fallback."
        )

    except Exception:
        logger.exception(
            "Google search failed. Trying Tavily fallback."
        )

    try:
        results = search_tavily(query, num_results)

        if results:
            logger.info("Using Tavily fallback results.")
            return results

    except Exception:
        logger.exception("Tavily search failed.")

    logger.error("All search providers failed for query: %s", query)

    return []
