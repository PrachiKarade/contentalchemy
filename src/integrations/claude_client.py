
import os
from collections.abc import Iterator
from functools import lru_cache

import anthropic
from anthropic import Anthropic
from dotenv import load_dotenv

from src.integrations.providers.text.text_provider_errors import (
    TextProviderQuotaError,
    TextProviderAccessError,
    TextProviderRateLimitError,
    TextProviderTemporaryError,
    TextProviderRequestError,
)

load_dotenv()

DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_MAX_OUTPUT_TOKENS = 4096


# ---------------------------------------------------------------------------
# Anthropic client
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_client() -> Anthropic:
    """Return a shared Anthropic client configured from .env."""

    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        raise TextProviderAccessError(
            "ANTHROPIC_API_KEY is missing from environment configuration."
        )

    # Retries are managed centrally by TextProviderManager.
    return Anthropic(
        api_key=api_key,
        max_retries=0,
        timeout=60,
    )


# ---------------------------------------------------------------------------
# Exception mapping
# ---------------------------------------------------------------------------

def _raise_claude_error(error: anthropic.APIError) -> None:
    """Convert Anthropic API errors into shared provider exceptions."""

    status_code = getattr(error, "status_code", None)
    error_message = str(error)
    message_lower = error_message.lower()

    # Authentication and access errors
    if status_code in (401, 403):
        raise TextProviderAccessError(
            f"Claude authentication/access error: {error_message}"
        ) from error

    # Billing and quota errors
    if status_code == 402 or any(
        term in message_lower
        for term in (
            "insufficient_quota",
            "billing",
            "credit balance",
            "credit limit",
        )
    ):
        raise TextProviderQuotaError(
            f"Claude API quota or billing issue: {error_message}"
        ) from error

    # Rate limits
    if status_code == 429:
        raise TextProviderRateLimitError(
            f"Claude rate limit exceeded: {error_message}",
            retryable=True,
        ) from error

    # Temporary overload, timeout, and server errors
    if status_code == 408 or status_code == 529 or (
        isinstance(status_code, int) and 500 <= status_code <= 599
    ):
        raise TextProviderTemporaryError(
            f"Claude temporary service error: {error_message}",
            retryable=True,
        ) from error

    # Other request errors
    raise TextProviderRequestError(
        f"Claude request failed: {error_message}",
        retryable=False,
    ) from error


# ---------------------------------------------------------------------------
# Generate text
# ---------------------------------------------------------------------------

def generate_text(
    query: str,
    system_prompt: str | None = None,
    model: str | None = None,
    max_output_tokens: int | None = None,
) -> str:
    """Generate text using Claude."""

    if not query or not query.strip():
        raise ValueError("Query cannot be empty.")

    params = {
        "model": model or os.getenv("CLAUDE_DEFAULT_MODEL", DEFAULT_MODEL),
        "max_tokens": (
            max_output_tokens
            if max_output_tokens is not None
            else DEFAULT_MAX_OUTPUT_TOKENS
        ),
        "messages": [
            {
                "role": "user",
                "content": query.strip(),
            }
        ],
    }

    if system_prompt:
        params["system"] = system_prompt

    try:
        response = get_client().messages.create(**params)

    except anthropic.APIError as error:
        _raise_claude_error(error)

    text = "\n".join(
        block.text
        for block in response.content
        if block.type == "text"
    ).strip()

    if not text:
        raise TextProviderRequestError(
            f"Claude returned no text. Stop reason: {response.stop_reason}",
            retryable=False,
        )

    return text


# ---------------------------------------------------------------------------
# Stream text
# ---------------------------------------------------------------------------

def stream_text(
    query: str,
    system_prompt: str | None = None,
    model: str | None = None,
    max_output_tokens: int | None = None,
) -> Iterator[str]:
    """Stream generated text from Claude."""

    if not query or not query.strip():
        raise ValueError("Query cannot be empty.")

    params = {
        "model": model or os.getenv("CLAUDE_DEFAULT_MODEL", DEFAULT_MODEL),
        "max_tokens": (
            max_output_tokens
            if max_output_tokens is not None
            else DEFAULT_MAX_OUTPUT_TOKENS
        ),
        "messages": [
            {
                "role": "user",
                "content": query.strip(),
            }
        ],
    }

    if system_prompt:
        params["system"] = system_prompt

    try:
        with get_client().messages.stream(**params) as stream:
            for text in stream.text_stream:
                if text:
                    yield text

    except anthropic.APIError as error:
        _raise_claude_error(error)


# ---------------------------------------------------------------------------
# Local test
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    answer = generate_text(
        query="Give me three LinkedIn post ideas about Agentic AI.",
        system_prompt="You are an expert AI content marketing strategist.",
    )

    print(answer)

    print("\nStreaming test:\n")

    for chunk in stream_text(
        query="Explain RAG in three short paragraphs.",
    ):
        print(chunk, end="", flush=True)
