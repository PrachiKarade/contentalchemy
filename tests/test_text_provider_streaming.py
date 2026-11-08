from unittest.mock import Mock, patch

from src.integrations.text_provider_manager import TextProviderManager
from src.integrations.providers.text.text_provider_errors import (
    TextProviderTemporaryError,
    TextProviderQuotaError,
)


def make_manager():
    manager = TextProviderManager()

    # Use only mock providers; no real API calls.
    manager.provider_order = ["mock_openai", "mock_gemini"]

    manager.PROVIDERS = {
        "mock_openai": Mock(),
        "mock_gemini": Mock(),
    }

    return manager


def test_stream_retry_before_first_chunk():
    manager = make_manager()

    manager.PROVIDERS["mock_openai"].stream_text.side_effect = [
        TextProviderTemporaryError("Temporary failure", retryable=True),
        iter(["Hello ", "from OpenAI"]),
    ]

    with patch(
        "src.integrations.text_provider_manager.time.sleep"
    ) as mock_sleep:

        result = list(manager.stream_text("Test query"))

    assert result == ["Hello ", "from OpenAI"]
    assert manager.PROVIDERS["mock_openai"].stream_text.call_count == 2
    assert manager.PROVIDERS["mock_gemini"].stream_text.call_count == 0
    assert [call.args[0] for call in mock_sleep.call_args_list] == [1]

    print("PASS: Streaming retried before the first chunk.")


def test_stream_fallback_after_non_retryable_error():
    manager = make_manager()

    manager.PROVIDERS["mock_openai"].stream_text.side_effect = (
        TextProviderQuotaError("Quota exhausted")
    )

    manager.PROVIDERS["mock_gemini"].stream_text.return_value = iter(
        ["Hello ", "from Gemini"]
    )

    result = list(manager.stream_text("Test query"))

    assert result == ["Hello ", "from Gemini"]
    assert manager.PROVIDERS["mock_openai"].stream_text.call_count == 1
    assert manager.PROVIDERS["mock_gemini"].stream_text.call_count == 1

    print("PASS: Streaming fell back after a quota error.")


def test_no_fallback_after_first_chunk():
    manager = make_manager()

    def broken_stream():
        yield "First chunk"
        raise TextProviderTemporaryError(
            "Connection lost",
            retryable=True,
        )

    manager.PROVIDERS["mock_openai"].stream_text.return_value = broken_stream()

    try:
        list(manager.stream_text("Test query"))
        assert False, "Expected TextProviderManagerError"

    except Exception as error:
        assert error.__class__.__name__ == "TextProviderManagerError"

    assert manager.PROVIDERS["mock_openai"].stream_text.call_count == 1
    assert manager.PROVIDERS["mock_gemini"].stream_text.call_count == 0

    print("PASS: No fallback occurred after the first chunk.")


if __name__ == "__main__":
    test_stream_retry_before_first_chunk()
    test_stream_fallback_after_non_retryable_error()
    test_no_fallback_after_first_chunk()

    print("\nAll streaming tests passed!")