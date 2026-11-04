import os
import re
import time

from pathlib import Path
from uuid import uuid4

import requests
from dotenv import load_dotenv

from src.core.logger import setup_logger


load_dotenv()

logger = setup_logger("ImageClient")


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

STABILITY_API_URL = (
    "https://api.stability.ai/v2beta/stable-image/generate/core"
)

STABILITY_IMAGE_MODEL = os.getenv(
    "STABILITY_IMAGE_MODEL",
    "core"
)

IMAGE_TIMEOUT_SECONDS = int(
    os.getenv("IMAGE_TIMEOUT_SECONDS", "120")
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_IMAGE_DIR = (
    PROJECT_ROOT / "generated" / "images"
)


# Existing project dimensions mapped to Stability aspect ratios.
ASPECT_RATIO_MAP = {
    "1024x1024": "1:1",
    "1024x1792": "9:16",
    "1792x1024": "16:9",
}

# Stable Image Core does not expose the same standard/HD
# quality parameter used by your previous image provider.
IMAGE_QUALITY_MAP = {
    "standard": "standard",
    "hd": "hd",
}


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def _get_stability_api_key() -> str:
    api_key = os.getenv("STABILITY_API_KEY")

    if not api_key:
        raise ValueError(
            "STABILITY_API_KEY is missing from environment."
        )

    return api_key


def _get_safe_conversation_id(
    conversation_id: str
) -> str:
    return re.sub(
        r"[^a-zA-Z0-9_-]",
        "_",
        conversation_id
    )


def _get_image_directory(
    conversation_id: str
) -> Path:

    safe_id = _get_safe_conversation_id(
        conversation_id
    )

    directory = DEFAULT_IMAGE_DIR / safe_id

    directory.mkdir(
        parents=True,
        exist_ok=True
    )

    return directory


# ---------------------------------------------------------
# Image Generation
# ---------------------------------------------------------

def generate_image(
    prompt: str,
    conversation_id: str,
    quality: str = "standard",
    size: str = "1024x1024",
    style: str = "vivid",
) -> dict:
    """
    Generate an image using Stability AI Stable Image Core.

    Keeps the existing function signature and return structure
    for compatibility with image_generator.py.
    """

    if not prompt or not prompt.strip():
        raise ValueError(
            "Image prompt cannot be empty."
        )

    if not conversation_id:
        raise ValueError(
            "conversation_id is required."
        )

    if quality not in IMAGE_QUALITY_MAP:
        raise ValueError(
            f"Unsupported image quality: {quality}"
        )

    if size not in ASPECT_RATIO_MAP:
        raise ValueError(
            f"Unsupported image size: {size}"
        )

    api_key = _get_stability_api_key()

    aspect_ratio = ASPECT_RATIO_MAP[size]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "image/*",
    }

    # Stable Image Core accepts prompt and aspect_ratio.
    # Quality is retained for compatibility with the existing
    # workflow but does not change Core's generation settings.
    payload = {
        "prompt": prompt.strip(),
        "aspect_ratio": aspect_ratio,
        "output_format": "png",
    }

    logger.info(
        "Sending image request to Stability AI. "
        "Model=%s, Conversation=%s, "
        "Quality=%s, Aspect ratio=%s",
        STABILITY_IMAGE_MODEL,
        conversation_id,
        quality,
        aspect_ratio,
    )

    start_time = time.perf_counter()

    try:
        response = requests.post(
            STABILITY_API_URL,
            headers=headers,
            files={
                "none": ""
            },
            data=payload,
            timeout=IMAGE_TIMEOUT_SECONDS,
        )

        elapsed = time.perf_counter() - start_time

        logger.info(
            "Stability AI response received in %.2f seconds. "
            "HTTP status=%s",
            elapsed,
            response.status_code,
        )

        # Raise an exception for HTTP errors.
        if not response.ok:
            try:
                error_details = response.json()
            except ValueError:
                error_details = response.text

            logger.error(
                "Stability AI API error: %s",
                error_details,
            )

            raise RuntimeError(
                f"Stability AI API returned "
                f"{response.status_code}: {error_details}"
            )

        # Confirm that the API returned image data.
        content_type = response.headers.get(
            "Content-Type",
            ""
        )

        if not content_type.startswith("image/"):
            raise RuntimeError(
                "Expected image response, but received: "
                f"{content_type}. Response: {response.text[:500]}"
            )

        image_bytes = response.content

        if not image_bytes:
            raise RuntimeError(
                "Stability AI returned an empty image."
            )

        logger.info(
            "Image received successfully. Bytes=%s",
            len(image_bytes),
        )

        # Save generated image.
        image_directory = _get_image_directory(
            conversation_id
        )

        image_path = (
            image_directory
            / f"image_{uuid4().hex}.png"
        )

        image_path.write_bytes(image_bytes)

        logger.info(
            "Image successfully saved: %s",
            image_path,
        )

        return {
            "image_path": str(image_path),
            "image_url": "",
            "revised_prompt": None,
        }

    except requests.Timeout as error:

        logger.exception(
            "Stability AI request timed out."
        )

        raise RuntimeError(
            "Stability AI image generation timed out."
        ) from error

    except requests.RequestException as error:

        logger.exception(
            "Stability AI network request failed."
        )

        raise RuntimeError(
            f"Stability AI request failed: {error}"
        ) from error

    except Exception:

        logger.exception(
            "Stability AI image generation failed."
        )

        raise