"""
Custom exceptions for Apple Search Ads Python Client.
"""

from typing import List


class AppleSearchAdsError(Exception):
    """Base exception for Apple Search Ads API errors."""

    pass


class AuthenticationError(AppleSearchAdsError):
    """Raised when authentication fails."""

    pass


class RateLimitError(AppleSearchAdsError):
    """Raised when API rate limit is exceeded."""

    pass


class InvalidRequestError(AppleSearchAdsError):
    """Raised when the API request is invalid."""

    pass


class OrganizationNotFoundError(AppleSearchAdsError):
    """Raised when no organization is found for the account."""

    pass


class ConfigurationError(AppleSearchAdsError):
    """Raised when the client is not configured properly."""

    pass


class PaginationError(AppleSearchAdsError):
    """Raised when a paged fetch cannot make progress or a result would be truncated."""

    pass


class MissingMetricError(AppleSearchAdsError):
    """Raised in strict mode when a required metric key is absent from an API row.

    Attributes:
        field: The missing metric key.
        available_keys: The keys that were present in the row, to make an
            upstream Apple field rename a one-line diagnosis.
    """

    def __init__(self, field: str, available_keys: List[str]):
        self.field = field
        self.available_keys = sorted(available_keys)
        super().__init__(
            f"Required metric '{field}' is missing from the API response row. "
            f"Available keys: {self.available_keys}"
        )
