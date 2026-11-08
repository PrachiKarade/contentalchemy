import os
import time
from  src.core.logger import setup_logger
from collections.abc import Iterator

from dotenv import load_dotenv

from src.integrations.providers.text.text_provider_errors import (  TextProviderError, TextProviderTemporaryError)

from src.integrations import (
    openai_client,
    gemini_client,
    claude_client,
    perplexity_client,
)


load_dotenv()

logger = setup_logger("text_provider_manager")


# --------------------------------------------------------
# class for error handling 
# ----------------------------------------------------
class TextProviderManagerError(RuntimeError):
    """Raised when all configured text providers fail."""

    def __init__(self, failures: list[tuple[str, str]]):
        self.failures = failures

        details = "\n".join(
            f"- {provider}: {reason}"
            for provider, reason in failures
        )

        super().__init__(
            "Content generation failed. All configured providers "
            f"were unsuccessful:\n{details}"
        )


class TextProviderManager:

    PROVIDERS = {
        "openai": openai_client,
        "gemini": gemini_client,
        "claude": claude_client,
        "perplexity": perplexity_client,
    }

    MAX_RETRIES = 2
    BASE_RETRY_DELAY = 1  # seconds

    def __init__(self):
        self.primary_provider = os.getenv( "TEXT_PRIMARY_PROVIDER", "openai" ).strip().lower()

        fallback_value = os.getenv("TEXT_FALLBACK_PROVIDERS", "" )

        self.fallback_providers = [
            provider.strip().lower()
            for provider in fallback_value.split(",")
            if provider.strip()
        ]
        self.provider_order = self._get_provider_order()

    def _get_provider_order(self) -> list[str]:
        """Build provider order and remove duplicates."""

        configured = [ self.primary_provider,*self.fallback_providers, ]

        order = []

        for provider in configured:
            if provider not in self.PROVIDERS:
                logger.warning( "Unknown text provider configured: %s", provider, )
                continue

            if provider not in order:
                order.append(provider)

        if not order:
            raise ValueError( "No valid text providers are configured." )

        return order
    # ----------------------------------------------------------------
    # Method for retry logic for text generation with exponential backoff
    # ----------------------------------------------------------------

    def _call_with_retries(self, provider_name, provider_func, *args, **kwargs):
        """
        Execute a provider call with bounded retries.
        Only retry errors explicitly marked as retryable.
        """

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                logger.info(
                    "Attempt %s/%s for provider: %s",
                    attempt + 1,
                    self.MAX_RETRIES + 1,
                    provider_name,
                )

                return provider_func(*args, **kwargs)

            except TextProviderError as error:
                if not error.retryable:
                    raise

                if attempt >= self.MAX_RETRIES:
                    logger.error(
                        "Retries exhausted for provider: %s | Error type: %s",
                        provider_name,
                        type(error).__name__,
                    )
                    raise

                delay = self.BASE_RETRY_DELAY * (2 ** attempt)

                logger.warning(
                    "Retryable error from provider: %s | Error type: %s | "
                    "Retrying in %s seconds.",
                    provider_name,
                    type(error).__name__,
                    delay,
                )

                time.sleep(delay)


    # ---------------------------------------------------------------------------
    # Method to generate text 
    # ---------------------------------------------------------------------------------

    def generate_text(
        self,
        query: str,
        system_prompt: str | None = None,
        model: str | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        """Generate text with automatic provider fallback."""

        failures = []

        for provider_name in self.provider_order:
            provider = self.PROVIDERS[provider_name]

            logger.info("Attempting text generation with provider: %s", provider_name)

            try:
               
                result = self._call_with_retries(
                            provider_name,
                            provider.generate_text,
                            query=query,
                            system_prompt=system_prompt,
                            model=model,
                            max_output_tokens=max_output_tokens,
                        )

                logger.info("Text generation succeeded with provider: %s", provider_name)
                return result

            except Exception as error:
                reason = str(error)

                logger.error( "Text generation failed with provider: %s | Error type: %s",
                    provider_name,
                    type(error).__name__,
                )

                failures.append((provider_name, reason))

                logger.warning(
                    "Moving to the next configured text provider after %s failed.",
                    provider_name,
                )

        raise TextProviderManagerError(failures)

    # -----------------------------------------------------------------------------------
    # Method : Generate Stream Text
    # ------------------------------------------------------------------------------------


    def stream_text(
        self,
        query: str,
        system_prompt: str | None = None,
        model: str | None = None,
        max_output_tokens: int | None = None,
    ) -> Iterator[str]:
        """Stream text with retries and fallback before the first chunk."""

        failures = []

        for provider_name in self.provider_order:
            provider = self.PROVIDERS[provider_name]

            for attempt in range(self.MAX_RETRIES + 1):
                first_chunk_received = False

                try:
                    logger.info(
                        "Starting text stream using provider: %s | Attempt %s/%s",
                        provider_name,
                        attempt + 1,
                        self.MAX_RETRIES + 1,
                    )

                    stream = provider.stream_text(
                        query=query,
                        system_prompt=system_prompt,
                        model=model,
                        max_output_tokens=max_output_tokens,
                    )

                    for chunk in stream:
                        if chunk:
                            first_chunk_received = True
                            yield chunk

                    if not first_chunk_received:
                        raise TextProviderTemporaryError(
                            f"{provider_name} returned an empty stream.",
                            retryable=True,
                        )

                    # Stream completed successfully.
                    logger.info( "Text streaming succeeded with provider: %s", provider_name,)
                    return
                except Exception as error:
                    logger.error(
                        "Text streaming failed with provider: %s | "
                        "Error type: %s",
                        provider_name,
                        type(error).__name__,
                    )

                    # Once output has been delivered, never retry or switch providers.
                    if first_chunk_received:
                        failures.append((provider_name, str(error)))
                        raise TextProviderManagerError(failures) from error

                    retryable = (
                        isinstance(error, TextProviderError)
                        and error.retryable
                    )

                    # Retry only retryable errors.
                    if retryable and attempt < self.MAX_RETRIES:
                        delay = self.BASE_RETRY_DELAY * (2 ** attempt)

                        logger.warning(
                            "Retryable streaming error from %s. "
                            "Retrying in %s seconds.",
                            provider_name,
                            delay,
                        )

                        time.sleep(delay)
                        continue

                    # Retries exhausted or error is not retryable.
                    failures.append((provider_name, str(error)))
                    break

            # Try the next configured provider.
            logger.warning(
                "Moving to the next configured provider after "
                "%s streaming failed.",
                provider_name,
            )

        raise TextProviderManagerError(failures)

text_provider_manager = TextProviderManager()