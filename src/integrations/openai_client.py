
import os
import logging
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

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"


# ---------------------------------------------------------------------------
# OpenAI client
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    """Return a shared OpenAI client configured from .env."""

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise TextProviderAccessError(
            "OPENAI_API_KEY is missing from environment configuration."
        )

    # Retries are managed centrally by TextProviderManager.
    return OpenAI(
        api_key=api_key,
        max_retries=0,
        timeout=60,
    )


# ---------------------------------------------------------------------------
# Exception mapping
# ---------------------------------------------------------------------------

def _raise_openai_error(error: OpenAIError) -> None:
    """Convert OpenAI SDK errors into shared provider exceptions."""

    status_code = getattr(error, "status_code", None)
    error_message = str(error)
    message_lower = error_message.lower()

    # Network and timeout errors
    if isinstance(error, (APIConnectionError, APITimeoutError)):
        raise TextProviderTemporaryError(
            f"OpenAI connection or timeout error: {error_message}",
            retryable=True,
        ) from error

    # Rate limit and quota errors
    if status_code == 429:

        if "insufficient_quota" in message_lower:
            raise TextProviderQuotaError(
                f"OpenAI quota exhausted: {error_message}"
            ) from error

        raise TextProviderRateLimitError(
            f"OpenAI rate limit exceeded: {error_message}",
            retryable=True,
        ) from error

    # Authentication and access errors
    if status_code in (401, 403):
        raise TextProviderAccessError(
            f"OpenAI authentication/access error: {error_message}"
        ) from error

    # Temporary server errors
    if status_code is not None and status_code >= 500:
        raise TextProviderTemporaryError(
            f"OpenAI server error: {error_message}",
            retryable=True,
        ) from error

    # Other request errors
    raise TextProviderRequestError(
        f"OpenAI request failed: {error_message}",
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
    """Send a prompt to OpenAI and return generated text."""

    if not query or not query.strip():
        raise ValueError("Query cannot be empty.")

    params = {
        "model": model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
        "input": query.strip(),
    }

    if system_prompt:
        params["instructions"] = system_prompt

    if max_output_tokens is not None:
        params["max_output_tokens"] = max_output_tokens

    try:
        response = get_client().responses.create(**params)

    except OpenAIError as error:
        _raise_openai_error(error)

    text = response.output_text.strip()

    if not text:
        raise TextProviderRequestError(
            f"OpenAI returned no text. Response status: {response.status}",
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
    """Send a prompt to OpenAI and yield generated text chunks."""

    if not query or not query.strip():
        raise ValueError("Query cannot be empty.")

    params = {
        "model": model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
        "input": query.strip(),
        "stream": True,
    }

    if system_prompt:
        params["instructions"] = system_prompt

    if max_output_tokens is not None:
        params["max_output_tokens"] = max_output_tokens

    try:
        stream = get_client().responses.create(**params)

        for event in stream:

            if event.type == "response.output_text.delta":
                if event.delta:
                    yield event.delta

            elif event.type in {"response.failed", "error"}:
                # A stream failure must not be silently treated as success.
                raise TextProviderTemporaryError(
                    "OpenAI streaming response failed.",
                    retryable=True,
                )

    except OpenAIError as error:
        _raise_openai_error(error)


# ---------------------------------------------------------------------------
# Local test
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)

    answer = generate_text(
        query="Give me 3 short blog title ideas about AI content marketing trends.",
        system_prompt="You are an expert content marketing strategist.",
    )

    print(answer)

    print("\nStreaming test:\n")

    for chunk in stream_text(
        query="Explain agentic AI in three short paragraphs.",
        system_prompt="You are an AI technology educator.",
    ):
        print(chunk, end="", flush=True)
