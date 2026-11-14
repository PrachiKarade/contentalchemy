
import pytest
from unittest.mock import MagicMock, patch

from src.integrations.image_provider_manager import ImageProviderManager
from src.integrations.providers.images.provider_errors import (
    ImageProviderError,
    InsufficientCreditsError,
)


@pytest.fixture
def manager():
    """Create a manager with a mocked Stability provider."""
    with patch(
        "src.integrations.image_provider_manager.StabilityImageProvider"
    ) as mock_provider_class:

        mock_provider = MagicMock()
        mock_provider.name = "stability"
        mock_provider_class.return_value = mock_provider

        with patch.dict(
            "os.environ",
            {
                "IMAGE_PRIMARY_PROVIDER": "stability",
                "IMAGE_FALLBACK_PROVIDERS": "",
            },
        ):
            image_manager = ImageProviderManager()

        yield image_manager, mock_provider


def test_generate_image_success(manager):
    image_manager, mock_provider = manager
    expected_bytes = b"fake-image-bytes"

    mock_provider.generate.return_value = expected_bytes

    result = image_manager.generate_image(
        prompt="A professional RAG architecture illustration",
        size="1024x1024",
    )

    assert result["provider"] == "stability"
    assert result["image_bytes"] == expected_bytes

    mock_provider.generate.assert_called_once_with(
        prompt="A professional RAG architecture illustration",
        size="1024x1024",
    )


def test_generate_image_insufficient_credits(manager):
    image_manager, mock_provider = manager

    mock_provider.generate.side_effect = InsufficientCreditsError(
        "Stability AI has insufficient credits."
    )

    with pytest.raises(InsufficientCreditsError):
        image_manager.generate_image(
            prompt="Test image",
        )


def test_generate_image_provider_failure(manager):
    image_manager, mock_provider = manager

    mock_provider.generate.side_effect = ImageProviderError(
        "Image generation failed."
    )

    with pytest.raises(ImageProviderError):
        image_manager.generate_image(
            prompt="Test image",
        )


def test_generate_image_does_not_call_provider_twice(manager):
    image_manager, mock_provider = manager

    mock_provider.generate.return_value = b"fake-image-bytes"

    image_manager.generate_image(prompt="Test image")

    assert mock_provider.generate.call_count == 1
