
import base64
import os

from openai import OpenAI

from src.core.logger import setup_logger
from src.integrations.providers.images.provider_errors import (
    ImageProviderError,
    InsufficientCreditsError,
)

logger = setup_logger("OpenAIImageProvider")


class OpenAIImageProvider:

    name = "openai"

    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            raise ImageProviderError("OPENAI_API_KEY is missing.")

        self.client = OpenAI(api_key=api_key)
        self.model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")

    def generate(self, prompt: str, size: str = "1024x1024") -> bytes:
        try:
            # Map application image sizes to OpenAI-supported sizes.
            openai_sizes = {
                "1024x1024": "1024x1024",
                "1536x1024": "1536x1024",
                "1024x1536": "1024x1536",
                "1024x1792": "1024x1536",
            }

            openai_size = openai_sizes.get(size, "1024x1024")

            logger.info(
                "Sending image request to OpenAI. Model=%s, Size=%s",
                self.model,
                openai_size,
            )

            response = self.client.images.generate(
                model=self.model,
                prompt=prompt,
                size=openai_size,
            )

            return base64.b64decode(response.data[0].b64_json)

        except Exception as exc:
            error_message = str(exc).lower()

            if any(term in error_message for term in (
                "billing", "quota", "insufficient_quota", "429"
            )):
                raise InsufficientCreditsError(
                    "OpenAI image generation has insufficient API credits."
                ) from exc

            raise ImageProviderError(
                f"OpenAI image generation failed: {exc}"
            ) from exc
