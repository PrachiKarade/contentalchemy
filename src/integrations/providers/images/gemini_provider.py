import os
import time

from google import genai
from google.genai import errors, types

from src.core.logger import setup_logger
from src.integrations.providers.images.provider_errors import (
    ImageProviderError,
    InsufficientCreditsError,
)

logger = setup_logger("GeminiImageProvider")

# The app asks for OpenAI-style sizes; Gemini image models take an aspect ratio.
ASPECT_RATIOS = {
    "1024x1024": "1:1",
    "1024x1792": "9:16",
    "1792x1024": "16:9",
    "1024x1536": "2:3",
    "1536x1024": "3:2",
}

QUOTA_TERMS = ("quota", "billing", "resource_exhausted", "insufficient", "429", "402")


class GeminiImageProvider:

    name = "gemini"

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise ImageProviderError("GEMINI_API_KEY is missing.")

        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=120_000,  # milliseconds
                # One attempt only: on quota errors the SDK would otherwise keep retrying
                # for minutes instead of letting the manager fall back to the next provider.
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

        self.model = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image").strip()

    # ---------------------------------------------------------------------
    # generate image method
    # ---------------------------------------------------------------------

    def generate(self, prompt: str, size: str = "1024x1024") -> bytes:
        aspect_ratio = ASPECT_RATIOS.get(size, "1:1")

        try:
            start_time = time.perf_counter()
            logger.info(
                "Sending image request to Gemini. Model=%s AspectRatio=%s",
                self.model,
                aspect_ratio,
            )

            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
                ),
            )

            logger.info(
                "Gemini response received in %.2f seconds.",
                time.perf_counter() - start_time,
            )

            image_bytes = self._extract_image(response)
            logger.info("Gemini image generation successful.")
            return image_bytes

        except ImageProviderError:
            raise

        except errors.APIError as exc:
            logger.error("Gemini image generation failed: %s %s", exc.code, exc.message)

            if exc.code in (402, 429) or any(term in str(exc).lower() for term in QUOTA_TERMS):
                raise InsufficientCreditsError(
                    "Gemini API quota or billing limit reached for "
                    f"{self.model}. Image models need a paid (billing-enabled) Gemini API key."
                ) from exc

            raise ImageProviderError(f"Gemini image generation failed: {exc}") from exc

        except Exception as exc:
            logger.exception("Gemini image generation failed.")
            raise ImageProviderError(f"Gemini image generation failed: {exc}") from exc

    # ---------------------------------------------------------------------
    # helpers
    # ---------------------------------------------------------------------

    @staticmethod
    def _extract_image(response) -> bytes:
        """Return the first image in the response, or explain why there is none."""

        candidates = response.candidates or []
        texts = []

        for candidate in candidates:
            parts = candidate.content.parts if candidate.content and candidate.content.parts else []
            for part in parts:
                if part.inline_data and part.inline_data.data:
                    # The SDK already decodes the base64 payload into bytes.
                    return part.inline_data.data
                if part.text:
                    texts.append(part.text.strip())

        feedback = response.prompt_feedback
        if feedback and feedback.block_reason:
            raise ImageProviderError(f"Gemini blocked the prompt: {feedback.block_reason}")

        reason = candidates[0].finish_reason if candidates else "no candidates"
        detail = f" Model said: {' '.join(texts)[:300]}" if texts else ""
        raise ImageProviderError(f"Gemini did not return an image (finish reason: {reason}).{detail}")
