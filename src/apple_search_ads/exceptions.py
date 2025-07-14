"""
Custom exceptions for Apple Search Ads Python Client.
"""


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
