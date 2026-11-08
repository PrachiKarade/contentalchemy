
import os

from dotenv import load_dotenv
from src.core.logger import setup_logger
from src.integrations.providers.images.stability_provider import ( StabilityImageProvider,)
from src.integrations.providers.images.provider_errors import (
    ImageProviderError,
    InsufficientCreditsError,
)

load_dotenv()

logger = setup_logger("ImageProviderManager")

#---------------------------------------------------------
# class ImageProviderManager : manages image providers
#---------------------------------------------------------
class ImageProviderManager:

    def __init__(self):
        self.primary_provider = os.getenv(
            "IMAGE_PRIMARY_PROVIDER", "stability"
        ).strip().lower()

        fallback_value = os.getenv("IMAGE_FALLBACK_PROVIDERS", "")

        self.fallback_providers = [
            name.strip().lower()
            for name in fallback_value.split(",")
            if name.strip()
        ]

        self.providers = {
            "stability": StabilityImageProvider(),
        }

        if self.primary_provider not in self.providers:
            raise ValueError(
                f"Unsupported image provider: {self.primary_provider}"
            )

        logger.info(
            "Primary image provider: %s | Fallback providers: %s",
            self.primary_provider,
            self.fallback_providers or "None",
        )

     #---------------------------------------------------------
     # generate_image method : generate an image using the configured providers
     #---------------------------------------------------------   
        
    def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
    ) -> dict:
        """
        Try configured image providers in order.

        Returns provider name and image bytes.
        """

        provider_names = [ self.primary_provider, *self.fallback_providers, ]

        errors = []

        for provider_name in dict.fromkeys(provider_names):
            provider = self.providers.get(provider_name)

            if provider is None:
                continue

            try:
                logger.info("Trying image provider: %s", provider_name)

                image_bytes = provider.generate(
                    prompt=prompt,
                    size=size,
                )

                logger.info( "Image generated successfully using %s",  provider_name,)

                return {
                    "provider": provider.name,
                    "image_bytes": image_bytes,
                }

            except ImageProviderError as exc:
                logger.warning(
                    "Provider %s failed: %s",
                    provider_name,
                    exc,
                )
                errors.append(f"{provider_name}: {exc}")

                # Continue to the next provider.
                continue

            except Exception as exc:
                logger.exception(
                    "Unexpected error from provider %s",
                    provider_name,
                )
                errors.append(f"{provider_name}: Unexpected error")

        if errors and all(
            isinstance(error, InsufficientCreditsError)
            for error in errors
        ):
            raise InsufficientCreditsError(
                "All configured image providers have insufficient credits."
            )

        raise ImageProviderError(
            "All configured image providers failed. "
            + " | ".join(str(error) for error in errors)
        )
