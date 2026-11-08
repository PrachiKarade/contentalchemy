
import os
import time
import requests
from dotenv import load_dotenv
from src.core.logger import setup_logger
from src.integrations.providers.images.provider_errors import (
    InsufficientCreditsError,
    ProviderAccessError,
    ProviderRateLimitError,
    ProviderTemporaryError,
)


load_dotenv()

logger = setup_logger("StabilityProvider")

STABILITY_API_URL = ( "https://api.stability.ai/v2beta/stable-image/generate/core")

IMAGE_TIMEOUT_SECONDS = int( os.getenv("IMAGE_TIMEOUT_SECONDS", "120"))

ASPECT_RATIO_MAP = {
    "1024x1024": "1:1",
    "1024x1792": "9:16",
    "1792x1024": "16:9",
}

# ---------------------------------------------------------
# class StabilityImageProvider : interface to Stability AI image generation API
# ---------------------------------------------------------

class StabilityImageProvider:

    name = "stability"

    # ---------------------------------------------------------
    # constructor
    # ---------------------------------------------------------
    def __init__(self):
        self.api_key = os.getenv("STABILITY_API_KEY")

        if not self.api_key:
            raise ValueError("STABILITY_API_KEY is missing from environment.")

    #---------------------------------------------------------
    # generate method: generate an image using Stability AI
    #---------------------------------------------------------
    def generate(
        self,
        prompt: str,
        size: str = "1024x1024",
    ) -> bytes:
        """Generate an image and return its raw bytes."""

        if not prompt or not prompt.strip():
            raise ValueError("Image prompt cannot be empty.")

        if size not in ASPECT_RATIO_MAP:
            raise ValueError(  f"Unsupported image size: {size}")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "image/*",
        }

        payload = {
            "prompt": prompt.strip(),
            "aspect_ratio": ASPECT_RATIO_MAP[size],
            "output_format": "png",
        }

        logger.info( "Sending image request to Stability AI. Size=%s", size,)

        start_time = time.perf_counter()

        try:
            response = requests.post(
                STABILITY_API_URL,
                headers = headers,
                files = {"none": ""},
                data = payload,
                timeout = IMAGE_TIMEOUT_SECONDS,
            )

            elapsed = time.perf_counter() - start_time

            logger.info(
                "Stability response received. Status=%s, Time=%.2fs",
                response.status_code,
                elapsed,
            )

            if not response.ok:
                try:
                    error_details = response.json()
                except ValueError:
                    error_details = response.text

                status_code = response.status_code

                if status_code == 402:
                    logger.error("Stability AI account has insufficient credits.")
                    raise InsufficientCreditsError(
                        "Stability AI has insufficient credits. "
                        "Please check your account balance."
                    )

                if status_code in (401, 403):
                    logger.error(
                        "Stability AI authentication or access error: %s",
                        status_code,
                    )
                    raise ProviderAccessError(
                        f"Stability AI access failed ({status_code}). "
                        "Check API key and model access."
                    )

                if status_code == 429:
                    raise ProviderRateLimitError(
                        "Stability AI rate limit exceeded.",
                        retryable=True,
                    )

                if status_code >= 500:
                    raise ProviderTemporaryError(
                        f"Stability AI server error ({status_code}).",
                        retryable=True,
                    )

                raise ProviderAccessError(
                    f"Stability AI request failed ({status_code}): "
                    f"{error_details}"
                )

            return response.content

        except requests.Timeout as error:
            logger.exception("Stability AI request timed out.")

            raise ProviderTemporaryError(
                "Stability AI image generation timed out.",
                retryable=True,
            ) from error

        except requests.RequestException as error:
            logger.exception( "Stability AI network request failed.")

            raise ProviderTemporaryError(
                f"Stability AI network request failed: {error}",
                retryable=True,
            ) from error
