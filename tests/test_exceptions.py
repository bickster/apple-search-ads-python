"""
Tests for Apple Search Ads exception classes.
"""

import pytest
from apple_search_ads.exceptions import (
    AppleSearchAdsError,
    AuthenticationError,
    RateLimitError,
    InvalidRequestError,
    OrganizationNotFoundError,
    ConfigurationError,
)


class TestExceptions:
    """Test all exception classes."""

    def test_apple_search_ads_error(self):
        """Test base exception class."""
        error = AppleSearchAdsError("Base error message")
        assert str(error) == "Base error message"
        assert isinstance(error, Exception)

    def test_authentication_error(self):
        """Test authentication error."""
        error = AuthenticationError("Auth failed")
        assert str(error) == "Auth failed"
        assert isinstance(error, AppleSearchAdsError)

    def test_rate_limit_error(self):
        """Test rate limit error."""
        error = RateLimitError("Rate limit exceeded")
        assert str(error) == "Rate limit exceeded"
        assert isinstance(error, AppleSearchAdsError)

    def test_invalid_request_error(self):
        """Test invalid request error."""
        error = InvalidRequestError("Invalid request")
        assert str(error) == "Invalid request"
        assert isinstance(error, AppleSearchAdsError)

    def test_organization_not_found_error(self):
        """Test organization not found error."""
        error = OrganizationNotFoundError("Org not found")
        assert str(error) == "Org not found"
        assert isinstance(error, AppleSearchAdsError)

    def test_configuration_error(self):
        """Test configuration error."""
        error = ConfigurationError("Config error")
        assert str(error) == "Config error"
        assert isinstance(error, AppleSearchAdsError)

    def test_exception_inheritance(self):
        """Test that all exceptions inherit properly."""
        # Test that specific exceptions can be caught as AppleSearchAdsError
        with pytest.raises(AppleSearchAdsError):
            raise AuthenticationError("test")

        with pytest.raises(AppleSearchAdsError):
            raise RateLimitError("test")

        with pytest.raises(AppleSearchAdsError):
            raise InvalidRequestError("test")

        with pytest.raises(AppleSearchAdsError):
            raise OrganizationNotFoundError("test")

        with pytest.raises(AppleSearchAdsError):
            raise ConfigurationError("test")
