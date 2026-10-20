# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **v3.0.0 (shipped 2026-08-03):** strict metric parsing is the default — missing base facts raise
> `MissingMetricError`, money is `Decimal`, absent ratios are `None`, and all reports paginate
> automatically. `strict=False` restores v2 zero-fill as a migration aid. History: `docs/v3-fix-spec.md`.

## Repository Overview

This is a Python client library for the Apple Ads Platform API v1 (v5 until 4.0; Apple sunsets v5 on 2027-01-26). The main package is `apple_search_ads` located in `src/apple_search_ads/`.

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

## Important Notes

- Python 3.13+ is required
- The package follows strict type checking with mypy
- All code should be formatted with black (100 char line length)
- The CI/CD pipeline tests on Python 3.13
- Version tags trigger automatic PyPI publishing