
import os
import serpapi
from dotenv import load_dotenv
from src.core.logger import setup_logger
from urllib.parse import urlparse

load_dotenv()
logger = setup_logger("Google search agent using SerpApi")

print("=" * 90)
print("Google search agent using SerpApi")
print("=" * 90)



def is_valid_source_url(url: str) -> bool:
    if not url:
        return False

    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        return False

    if parsed.netloc.lower() in {"google.com", "www.google.com"}:
        return False

    return True


def search_web(query: str, num_results: int = 5) -> list[dict]:
    """Search Google using SerpAPI and return normalized results."""

    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        raise ValueError("SERPAPI_KEY is missing from .env")

    if not query or not query.strip():
        raise ValueError("Search query cannot be empty")

    num_results = max(1, min(num_results, 10))

    client = serpapi.Client(api_key=api_key)
    response = client.search(
        engine="google",
        q=query.strip(),
        num=num_results,
    )

    return [
    {
        "title": item.get("title", ""),
        "url": item.get("link", ""),
        "snippet": item.get("snippet", ""),
    }
    for item in response.get("organic_results", [])
    if is_valid_source_url(item.get("link", ""))
]


"""

if __name__ == "__main__":
    results = search_web("AI content marketing trends", 5)
 
    for index, result in enumerate(results, start=1):
        print(f"\n{index}. {result['title']}")
        print(f"URL: {result['url']}")
        print(f"Snippet: {result['snippet']}")
"""