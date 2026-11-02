
import os
from collections.abc import Iterator
from functools import lru_cache

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

load_dotenv()

DEFAULT_MODEL = "gpt-4o-mini"


@lru_cache(maxsize = 1)
def get_client() -> OpenAI:
    """Return a shared OpenAI client configured from .env."""

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is missing from .env")

    return OpenAI(api_key = api_key, max_retries=3, timeout=60)


def generate_text(
    query: str, # user query
    system_prompt: str | None = None, #system prompt to guide the model's behavior
    model: str | None = None,
    max_output_tokens: int | None = None,
) -> str:
    """Send a prompt to OpenAI and return the generated text."""

    if not query or not query.strip():
        raise ValueError("Query cannot be empty")

    params = {
        "model": model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
        "input": query.strip(),
    }
    if system_prompt:
        params["instructions"] = system_prompt

    if max_output_tokens:
        params["max_output_tokens"] = max_output_tokens

    try:
        response = get_client().responses.create(**params)
    except OpenAIError as error:
        raise RuntimeError(f"OpenAI error: {error}") from error

    text = response.output_text.strip()

    if not text:
        raise RuntimeError(f"OpenAI returned no text (status: {response.status})")

    return text


def stream_text(
    query: str,
    system_prompt: str | None = None,
    model: str | None = None,
    max_output_tokens: int | None = None,
) -> Iterator[str]:
    """Send a prompt to OpenAI and yield the generated text as it arrives."""

    if not query or not query.strip():
        raise ValueError("Query cannot be empty")

    params = {
        "model": model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
        "input": query.strip(),
        "stream": True,
    }
    if system_prompt:
        params["instructions"] = system_prompt

    if max_output_tokens:
        params["max_output_tokens"] = max_output_tokens

    try:
        for event in get_client().responses.create(**params):
            if event.type == "response.output_text.delta":
                yield event.delta
            elif event.type in {"response.failed", "error"}:
                raise RuntimeError(f"OpenAI streaming failed: {getattr(event, 'message', event.type)}")
    except OpenAIError as error:
        raise RuntimeError(f"OpenAI error: {error}") from error

"""
if __name__ == "__main__":
    answer = generate_text(
        "Give me 3 short blog title ideas about AI content marketing trends.",
        system_prompt="You are an expert content marketing strategist.",
    )
    print(answer)
"""