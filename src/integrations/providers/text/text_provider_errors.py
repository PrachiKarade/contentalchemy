class TextProviderError(Exception):
    """Base exception for text provider failures."""

    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class TextProviderQuotaError(TextProviderError):
    """Provider quota or billing limit reached."""
    def __init__(self, message: str):
        super().__init__(message, retryable=False)


class TextProviderAccessError(TextProviderError):
    """Invalid API key or access denied."""
    def __init__(self, message: str):
        super().__init__(message, retryable=False)


class TextProviderRateLimitError(TextProviderError):
    """Provider rate limit exceeded."""
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message, retryable=retryable)


class TextProviderTemporaryError(TextProviderError):
    """Temporary provider outage or service unavailable."""
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message, retryable=retryable)


class TextProviderRequestError(TextProviderError):
    """Invalid or unsupported provider request."""
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message, retryable=retryable)