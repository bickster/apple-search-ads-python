# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> ## ⭐ ACTIVE WORK — read `docs/v3-fix-spec.md` FIRST
>
> A **v3.0.0 (breaking)** change is specced and approved: **[`docs/v3-fix-spec.md`](docs/v3-fix-spec.md)**.
> Read it before touching `src/apple_search_ads/client.py`. Two defects, both verified against the live
> Apple API on 2026-08-03:
>
> 1. **No pagination anywhere.** `_build_report_request` hardcodes `limit: 1000` with no offset and there
>    is no offset loop in the file, so any report over 1000 rows is **silently truncated**. Two of the
>    consumer's production campaigns already exceed it.
> 2. **Metrics zero-fill.** `_parse_metrics` defaults every field to `0`, so a renamed or dropped Apple key
>    lands `0` instead of raising — an invisible failure that downstream validation cannot catch.
>
> Driven by `bickster_os` (ASA Pass 2), which will consume this SDK **wholesale** and needs money exact to
> the cent. **Breaking the `apple-search-ads-save` donor project is explicitly accepted.** No deadline —
> the consumer is deliberately gated on this release, so prefer the correct fix over the fast one.

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
python3 -m pip install -e .

# Install development dependencies
python3 -m pip install -r requirements-dev.txt

# Build the package
python -m build
```

### Development Workflow

After making changes to source code, always follow this workflow:

```bash
# 1. Reinstall package in dev mode (IMPORTANT: tests import from installed package)
python3 -m pip install -e .

# 2. Format code first
black src tests

# 3. Run tests
pytest tests -v --cov=apple_search_ads --cov-report=term-missing

# 4. Check linting
flake8 src tests --max-line-length=127
```

**Key gotchas:**
- Use `python3 -m pip` instead of `pip` (more reliable across environments, especially macOS)
- Always reinstall with `pip install -e .` after editing source files, or tests will run against the old installed version
- Run `black` before committing to avoid formatting-only commits

### Creating a Release

**Always use the release script - do not create releases manually.**

```bash
./release.sh <version>
# Example: ./release.sh 2.2.0
```

The script handles everything automatically:
1. Validates version format and checks it doesn't already exist
2. Updates version in `pyproject.toml`
3. Runs tests and code quality checks
4. Creates commit and tag
5. Pushes to GitHub
6. Waits for GitHub Actions (which publishes to PyPI and creates the GitHub release)
7. Verifies PyPI publication

**Do NOT manually run `gh release create`** - the GitHub Actions workflow creates the release automatically when a tag is pushed.

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

- Python 3.13+ is required
- The package follows strict type checking with mypy
- All code should be formatted with black (100 char line length)
- The CI/CD pipeline tests on Python 3.13
- Version tags trigger automatic PyPI publishing