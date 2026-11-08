from unittest.mock import Mock, patch

from src.integrations.text_provider_manager import TextProviderManager
from src.integrations.providers.text.text_provider_errors import (
    TextProviderTemporaryError,
    TextProviderQuotaError,
)


def test_retryable_error_then_success():
    manager = TextProviderManager()

    # Simulate two temporary failures followed by success.
    mock_provider = Mock(
        side_effect=[
            TextProviderTemporaryError("Temporary failure"),
            TextProviderTemporaryError("Temporary failure"),
            "Successful response",
        ]
    )

    # Avoid actual waiting during the test.
    with patch("src.integrations.text_provider_manager.time.sleep") as mock_sleep:

        result = manager._call_with_retries(
            "mock_provider",
            mock_provider,
        )

    assert result == "Successful response"
    assert mock_provider.call_count == 3

    # Exponential backoff: 1 second, then 2 seconds.
    assert [call.args[0] for call in mock_sleep.call_args_list] == [1, 2]

    print("PASS: Retryable errors retried and eventually succeeded.")


def test_non_retryable_error():
    manager = TextProviderManager()

    # Quota errors should not be retried.
    mock_provider = Mock(
        side_effect=TextProviderQuotaError("Quota exhausted")
    )

    with patch("src.integrations.text_provider_manager.time.sleep") as mock_sleep:

        try:
            manager._call_with_retries(
                "mock_provider",
                mock_provider,
            )
            assert False, "Expected TextProviderQuotaError"

        except TextProviderQuotaError:
            pass

    assert mock_provider.call_count == 1
    mock_sleep.assert_not_called()

    print("PASS: Non-retryable errors were not retried.")


if __name__ == "__main__":
    test_retryable_error_then_success()
    test_non_retryable_error()

    print("\nAll retry tests passed!")