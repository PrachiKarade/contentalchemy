import os
import re
import time

from pathlib import Path
from uuid import uuid4

import requests
from dotenv import load_dotenv

from src.core.logger import setup_logger
from src.integrations.image_storage import AzuriteImageStorage
from src.integrations.image_provider_manager import ImageProviderManager


load_dotenv()

logger = setup_logger("ImageClient")


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

image_storage = AzuriteImageStorage() 
image_provider_manager = ImageProviderManager()

STABILITY_API_URL = ( "https://api.stability.ai/v2beta/stable-image/generate/core")

STABILITY_IMAGE_MODEL = os.getenv( "STABILITY_IMAGE_MODEL",  "core")

IMAGE_TIMEOUT_SECONDS = int( os.getenv("IMAGE_TIMEOUT_SECONDS", "120"))

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_IMAGE_DIR = (  PROJECT_ROOT / "generated" / "images")

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
        raise ValueError( "STABILITY_API_KEY is missing from environment.")

    return api_key


def _get_safe_conversation_id(  conversation_id: str) -> str:
    return re.sub(
        r"[^a-zA-Z0-9_-]",
        "_",
        conversation_id
    )


def _get_image_directory( conversation_id: str) -> Path:

    safe_id = _get_safe_conversation_id( conversation_id)

    directory = DEFAULT_IMAGE_DIR / safe_id

    directory.mkdir( parents=True,  exist_ok=True)
    return directory


# ---------------------------------------------------------
# Image Generation with Stability AI Stable Image Core
# ---------------------------------------------------------

def _generate_with_stability(
    prompt: str,
    conversation_id: str,
    quality: str = "standard",
    size: str = "1024x1024",
    style: str = "vivid",
) -> dict:
    """
    Generate an image through ImageProviderManager
    and save the returned bytes to Azurite.
    """

    if not prompt or not prompt.strip():
        raise ValueError("Image prompt cannot be empty.")

    if not conversation_id:
        raise ValueError("conversation_id is required.")

    if quality not in IMAGE_QUALITY_MAP:
        raise ValueError(f"Unsupported image quality: {quality}")

    if size not in ASPECT_RATIO_MAP:
        raise ValueError(f"Unsupported image size: {size}")

    logger.info("Starting image generation.")

    # Generate image using configured providers.
    result = image_provider_manager.generate_image(
        prompt=prompt,
        size=size,
    )

    image_bytes = result["image_bytes"]
    provider_name = result["provider"]

    # Store the generated image.
    safe_id = _get_safe_conversation_id(conversation_id)
    blob_name = f"{safe_id}/image_{uuid4().hex}.png"

    storage_result = image_storage.upload_image(
        image_bytes=image_bytes,
        blob_name=blob_name,
    )

    logger.info(
        "Image generated using %s and saved to storage.",
        provider_name,
    )

    return {
         "image_path": storage_result["image_path"],
         "image_url": storage_result["image_url"],
         "revised_prompt": None,
         "provider": provider_name,
    }


# ---------------------------------------------------------
# Image Generation with other providers (e.g., Gemini, OpenAI) can be implemented here
# ---------------------------------------------------------
def generate_image(
    prompt: str,
    conversation_id: str,
    quality: str = "standard",
    size: str = "1024x1024",
    style: str = "vivid",
) -> dict:
    """
    Public image generation interface.

    Stability AI is currently the primary provider.
    Future fallback providers will be managed here.
    """

    logger.info("Image generation started.")

    result = _generate_with_stability(
        prompt=prompt,
        conversation_id=conversation_id,
        quality=quality,
        size=size,
        style=style,
    )

    result["provider"] = "stability"

    return result