
class ImageProviderError(Exception):
    """Base exception for image provider failures."""

    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class InsufficientCreditsError(ImageProviderError):
    pass


class ProviderAccessError(ImageProviderError):
    pass


class ProviderRateLimitError(ImageProviderError):
    pass


class ProviderTemporaryError(ImageProviderError):
    pass
