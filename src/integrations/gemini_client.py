
import os
from collections.abc import Iterator
from functools import lru_cache

from dotenv import load_dotenv
from google import genai
from google.genai import errors

from src.integrations.providers.text.text_provider_errors import (
    TextProviderQuotaError,
    TextProviderAccessError,
    TextProviderRateLimitError,
    TextProviderTemporaryError,
    TextProviderRequestError,
)

load_dotenv()

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_MAX_OUTPUT_TOKENS = 4096


# ---------------------------------------------------------------------------
# Gemini client
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_client() -> genai.Client:
    """Return a shared Gemini client configured from .env."""

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise TextProviderAccessError(
            "GEMINI_API_KEY is missing from environment configuration."
        )

    return genai.Client(api_key=api_key)


# ---------------------------------------------------------------------------
# Exception mapping
# ---------------------------------------------------------------------------

def _raise_gemini_error(error: errors.APIError) -> None:
    """Convert Gemini API errors into shared provider exceptions."""

    status_code = getattr(error, "code", None)
    message = str(error)
    message_lower = message.lower()

    # Authentication and access errors
    if status_code in (401, 403):
        raise TextProviderAccessError(
            f"Gemini authentication/access error: {message}"
        ) from error

    # Billing and quota errors
    if any(
        term in message_lower
        for term in (
            "quota exceeded",
            "billing",
            "insufficient quota",
            "limit: 0",
        )
    ):
        raise TextProviderQuotaError(
            f"Gemini API quota or billing issue: {message}"
        ) from error

    # Rate limits
    if status_code == 429:
        raise TextProviderRateLimitError(
            f"Gemini rate limit exceeded: {message}",
            retryable=True,
        ) from error

    # Temporary server or timeout errors
    if status_code == 408 or (
        isinstance(status_code, int) and 500 <= status_code <= 599
    ):
        raise TextProviderTemporaryError(
            f"Gemini temporary service error: {message}",
            retryable=True,
        ) from error

    # Other request errors
    raise TextProviderRequestError(
        f"Gemini request failed: {message}",
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
    """Generate text using Gemini."""

    if not query or not query.strip():
        raise ValueError("Query cannot be empty.")

    config = {
        "max_output_tokens": (
            max_output_tokens
            if max_output_tokens is not None
            else DEFAULT_MAX_OUTPUT_TOKENS
        )
    }

    if system_prompt:
        config["system_instruction"] = system_prompt

    try:
        response = get_client().models.generate_content(
            model=model or os.getenv("GEMINI_DEFAULT_MODEL", DEFAULT_MODEL),
            contents=query.strip(),
            config=config,
        )

    except errors.APIError as error:
        _raise_gemini_error(error)

    text = (response.text or "").strip()

    if not text:
        raise TextProviderRequestError(
            "Gemini returned no text response.",
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
    """Stream generated text from Gemini."""

    if not query or not query.strip():
        raise ValueError("Query cannot be empty.")

    config = {
        "max_output_tokens": (
            max_output_tokens
            if max_output_tokens is not None
            else DEFAULT_MAX_OUTPUT_TOKENS
        )
    }

    if system_prompt:
        config["system_instruction"] = system_prompt

    try:
        response_stream = get_client().models.generate_content_stream(
            model=model or os.getenv("GEMINI_DEFAULT_MODEL", DEFAULT_MODEL),
            contents=query.strip(),
            config=config,
        )

        for chunk in response_stream:
            if chunk.text:
                yield chunk.text

    except errors.APIError as error:
        _raise_gemini_error(error)


# ---------------------------------------------------------------------------
# Local test
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    prompt = "Explain what an AI agent is in three sentences."

    print("Testing normal generation:")
    result = generate_text(prompt)
    print(result)

    print("\nTesting streaming:")
    for chunk in stream_text(prompt):
        print(chunk, end="", flush=True)
