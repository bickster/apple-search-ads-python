# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a Python client library for Apple Search Ads API v5. The main package is `apple_search_ads` located in `src/apple_search_ads/`.

## Key Commands

### Testing
```bash
# Run all tests with coverage
pytest tests -v --cov=apple_search_ads --cov-report=html --cov-report=term-missing

# Run a specific test
pytest tests/test_client.py::TestClass::test_method

# Run tests for a specific test class
pytest tests/test_client.py::TestClass
```

### Code Quality
```bash
# Format code with black (100 char line length)
black src tests

# Check formatting without changes
black --check src tests

# Lint with flake8 (127 char line length)
flake8 src tests --max-line-length=127

# Type checking with mypy (strict mode)
mypy src
```

### Development Setup
```bash
# Install package in development mode
pip install -e .

# Install development dependencies
pip install -r requirements-dev.txt

# Build the package
python -m build
```

## Architecture Overview

### Core Components

1. **AppleSearchAdsClient** (`src/apple_search_ads/client.py`): The main client class that handles:
   - OAuth2 authentication using JWT tokens
   - API request management with built-in rate limiting
   - Multi-organization support
   - Automatic token refresh
   - Returns pandas DataFrames for data operations

2. **Exception Hierarchy** (`src/apple_search_ads/exceptions.py`):
   - `AppleSearchAdsError`: Base exception
   - `AuthenticationError`: Auth failures
   - `RateLimitError`: API rate limits
   - `InvalidRequestError`: Bad requests
   - `OrganizationNotFoundError`: Missing org
   - `ConfigurationError`: Client config issues

### Authentication Flow

The client supports three authentication methods:
1. Direct parameters (client_id, team_id, key_id, private_key)
2. Private key file path
3. Environment variables (APPLE_CLIENT_ID, APPLE_TEAM_ID, APPLE_KEY_ID, APPLE_PRIVATE_KEY)

JWT tokens are generated using PyJWT with ES256 algorithm and automatically refreshed before expiry.

### API Integration Patterns

- All API methods follow a consistent pattern of building requests, handling responses, and converting to DataFrames
- Rate limiting is implemented using the `ratelimit` decorator
- Error responses are parsed and raised as appropriate exception types
- The client handles pagination automatically when fetching large datasets

### Testing Approach

Tests use pytest with fixtures defined in `tests/conftest.py`. Key testing patterns:
- Mock the `requests` library for API calls
- Use `pytest.mark.parametrize` for testing multiple scenarios
- Test both success and error cases
- Verify DataFrame outputs and data transformations

## Important Notes

- Python 3.8+ is required
- The package follows strict type checking with mypy
- All code should be formatted with black (100 char line length)
- The CI/CD pipeline tests on Python 3.8-3.12
- Version tags trigger automatic PyPI publishing