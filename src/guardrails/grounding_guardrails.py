
from urllib.parse import urlsplit, urlunsplit


def normalize_url(url: str) -> str:
    """Normalize a URL for comparison without changing its identity."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("URL must be a non-empty string.")

    parsed = urlsplit(url.strip())

    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"Invalid HTTP/HTTPS URL: {url!r}")

    scheme = parsed.scheme.lower()
    hostname = parsed.hostname.lower()

    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"Invalid URL port: {url!r}") from exc

    if port and not (
        (scheme == "http" and port == 80)
        or (scheme == "https" and port == 443)
    ):
        hostname = f"{hostname}:{port}"

    path = parsed.path.rstrip("/") or "/"

    # Keep query parameters because they can identify different resources.
    # Remove fragments because they do not identify a different page.
    return urlunsplit(
        (scheme, hostname, path, parsed.query, "")
    )


def extract_search_result_urls(search_results: list) -> set[str]:
    """Collect URLs from the original search results."""
    if not isinstance(search_results, list):
        raise TypeError("Search results must be a list.")

    urls = set()

    def visit(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key.lower() in {"url", "link"} and isinstance(item, str):
                    try:
                        urls.add(normalize_url(item))
                    except ValueError:
                        # Ignore malformed URLs in search results.
                        continue
                elif isinstance(item, (dict, list)):
                    visit(item)

        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(search_results)
    return urls


def validate_research_grounding(
    research_data: dict,
    search_results: list,
) -> dict:
    """
    Ensure research findings and listed sources reference
    URLs present in the original search results.
    """
    if not isinstance(research_data, dict):
        raise TypeError("Research data must be a dictionary.")

    allowed_urls = extract_search_result_urls(search_results)

    if not allowed_urls:
        raise ValueError("No valid source URLs found in search results.")

    findings = research_data.get("findings")
    sources = research_data.get("sources")

    if not isinstance(findings, list):
        raise ValueError("Research findings must be a list.")

    if not isinstance(sources, list):
        raise ValueError("Research sources must be a list.")

    # Validate URLs cited by individual findings.
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            raise ValueError(f"Finding {index + 1} must be an object.")

        source_urls = finding.get("source_urls")

        if not isinstance(source_urls, list) or not source_urls:
            raise ValueError(
                f"Finding {index + 1} must contain source URLs."
            )

        for url in source_urls:
            normalized = normalize_url(str(url))

            if normalized not in allowed_urls:
                raise ValueError(
                    f"Finding {index + 1} cites a URL not present "
                    f"in the original search results: {url}"
                )

    # Validate URLs in the report's top-level sources list.
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            raise ValueError(f"Source {index + 1} must be an object.")

        url = source.get("url")

        if not url:
            raise ValueError(f"Source {index + 1} has no URL.")

        normalized = normalize_url(str(url))

        if normalized not in allowed_urls:
            raise ValueError(
                f"Source {index + 1} contains a URL not present "
                f"in the original search results: {url}"
            )

    return research_data
