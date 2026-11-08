
import os
from collections.abc import Iterator
from functools import lru_cache

from dotenv import load_dotenv
from openai import (
    OpenAI,
    OpenAIError,
    APIConnectionError,
    APITimeoutError,
)

from src.integrations.providers.text.text_provider_errors import (
    TextProviderQuotaError,
    TextProviderAccessError,
    TextProviderRateLimitError,
    TextProviderTemporaryError,
    TextProviderRequestError,
)

load_dotenv()

DEFAULT_MODEL = "perplexity/sonar"
DEFAULT_MAX_OUTPUT_TOKENS = 4096


# ---------------------------------------------------------------------------
# Perplexity client
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    """Return a shared Perplexity client using OpenAI SDK compatibility."""

    api_key = os.getenv("PERPLEXITY_API_KEY")

    if not api_key:
        raise TextProviderAccessError(
            "PERPLEXITY_API_KEY is missing from environment configuration."
        )

    # Retries are managed centrally by TextProviderManager.
    return OpenAI(
        api_key=api_key,
        base_url="https://api.perplexity.ai/v1",
        max_retries=0,
        timeout=60,
    )


# ---------------------------------------------------------------------------
# Exception mapping
# ---------------------------------------------------------------------------

def _raise_perplexity_error(error: OpenAIError) -> None:
    """Convert Perplexity API errors into shared provider exceptions."""

    status_code = getattr(error, "status_code", None)
    error_message = str(error)
    message_lower = error_message.lower()

    # Network and timeout errors
    if isinstance(error, (APIConnectionError, APITimeoutError)):
        raise TextProviderTemporaryError(
            f"Perplexity connection or timeout error: {error_message}",
            retryable=True,
        ) from error

    # Authentication and access errors
    if status_code in (401, 403):
        raise TextProviderAccessError(
            f"Perplexity authentication/access error: {error_message}"
        ) from error

    # Billing and quota errors
    if any(
        term in message_lower
        for term in (
            "insufficient_quota",
            "quota exceeded",
            "insufficient credits",
            "credit balance",
            "billing limit",
        )
    ):
        raise TextProviderQuotaError(
            f"Perplexity quota or billing issue: {error_message}"
        ) from error

    # Rate limits
    if status_code == 429:
        raise TextProviderRateLimitError(
            f"Perplexity rate limit exceeded: {error_message}",
            retryable=True,
        ) from error

    # Temporary server and timeout errors
    if status_code == 408 or (
        isinstance(status_code, int) and 500 <= status_code <= 599
    ):
        raise TextProviderTemporaryError(
            f"Perplexity temporary service error: {error_message}",
            retryable=True,
        ) from error

    # Other request errors
    raise TextProviderRequestError(
        f"Perplexity request failed: {error_message}",
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
    """Generate text using Perplexity Sonar."""

    if not query or not query.strip():
        raise ValueError("Query cannot be empty.")

    params = {
        "model": model or os.getenv(
            "PERPLEXITY_DEFAULT_MODEL",
            DEFAULT_MODEL,
        ),
        "input": query.strip(),
        "max_output_tokens": (
            max_output_tokens
            if max_output_tokens is not None
            else DEFAULT_MAX_OUTPUT_TOKENS
        ),
    }

    if system_prompt:
        params["instructions"] = system_prompt

    try:
        response = get_client().responses.create(**params)

    except OpenAIError as error:
        _raise_perplexity_error(error)

    text = (response.output_text or "").strip()

    if not text:
        raise TextProviderRequestError(
            f"Perplexity returned no text. Response status: {response.status}",
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
    """Stream generated text from Perplexity."""

    if not query or not query.strip():
        raise ValueError("Query cannot be empty.")

    params = {
        "model": model or os.getenv(
            "PERPLEXITY_DEFAULT_MODEL",
            DEFAULT_MODEL,
        ),
        "input": query.strip(),
        "stream": True,
        "max_output_tokens": (
            max_output_tokens
            if max_output_tokens is not None
            else DEFAULT_MAX_OUTPUT_TOKENS
        ),
    }

    if system_prompt:
        params["instructions"] = system_prompt

    try:
        response_stream = get_client().responses.create(**params)

        for event in response_stream:

            if event.type == "response.output_text.delta":
                if event.delta:
                    yield event.delta

            elif event.type in {"response.failed", "error"}:
                raise TextProviderTemporaryError(
                    "Perplexity streaming response failed.",
                    retryable=True,
                )

    except OpenAIError as error:
        _raise_perplexity_error(error)


# ---------------------------------------------------------------------------
# Local test
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    answer = generate_text(
        query="Give me three current AI content marketing trends.",
        system_prompt="You are an expert content marketing strategist.",
    )

    print(answer)

    print("\nStreaming test:\n")

    for chunk in stream_text(
        query="Explain agentic AI in three short paragraphs.",
    ):
        print(chunk, end="", flush=True)
