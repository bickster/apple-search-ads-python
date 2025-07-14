# Release Guide

## Quick Release

To create a new release, simply run:

```bash
./release.sh <version>
```

Example:
```bash
./release.sh 1.0.4
```

## What the Script Does

The release script (`release.sh`) automates the entire release process with verification steps:

### 1. Prerequisites Check
- ✅ Verifies git is installed
- ✅ Verifies GitHub CLI (gh) is installed and authenticated
- ✅ Confirms you're in a git repository
- ✅ Checks working directory is clean

### 2. Validation Phase
- ✅ Validates version format (X.Y.Z)
- ✅ Ensures version tag doesn't already exist
- ✅ Verifies git working directory is clean

### 3. Version Update Phase
- ✅ Updates version in `setup.py`
- ✅ Updates version in `pyproject.toml`
- ✅ Verifies both files have consistent versions

### 4. Quality Checks Phase
- ✅ Runs pytest test suite with coverage
- ✅ Runs black code formatting check
- ✅ Runs mypy type checking
- ✅ Runs flake8 linting

### 5. Git Operations Phase
- ✅ Creates commit with version bump
- ✅ Creates annotated git tag
- ✅ Pushes both commit and tag to GitHub

### 6. CI/CD Verification Phase
- ✅ Waits for GitHub Actions to complete
- ✅ Verifies all tests pass
- ✅ Confirms PyPI publication succeeds

### 7. GitHub Release Phase
- ✅ Creates GitHub release with auto-generated notes
- ✅ Marks as latest release

### 8. PyPI Verification Phase
- ✅ Verifies package is available on PyPI
- ✅ Provides installation instructions

## Manual Release (Alternative)

If you prefer to do releases manually:

1. **Update versions:**
   ```bash
   # Update setup.py version
   # Update pyproject.toml version
   ```

2. **Run quality checks:**
   ```bash
   pytest tests -v --cov=apple_search_ads
   black --check src tests
   mypy src
   flake8 src tests
   ```

3. **Commit and tag:**
   ```bash
   git add setup.py pyproject.toml
   git commit -m "Bump version to X.Y.Z"
   git tag -a "vX.Y.Z" -m "Release version X.Y.Z"
   git push origin main
   git push origin vX.Y.Z
   ```

4. **Wait for GitHub Actions** to complete (tests + PyPI publish)

5. **Create GitHub release:**
   ```bash
   gh release create vX.Y.Z --title "Release vX.Y.Z" --generate-notes --latest
   ```

## Prerequisites

Before using the release script, ensure you have:

- **Git** installed and configured
- **GitHub CLI** installed and authenticated:
  ```bash
  brew install gh  # macOS
  gh auth login
  ```
- **Python development tools** (optional, for quality checks):
  ```bash
  pip install -r requirements-dev.txt
  ```

## Troubleshooting

### GitHub CLI Not Authenticated
```bash
gh auth login
# Follow the prompts to authenticate
```

### Tests Failing
```bash
# Run tests manually to see detailed output
pytest tests -v --cov=apple_search_ads --cov-report=term-missing
```

### GitHub Actions Failing
- Check the Actions tab on GitHub for detailed logs
- The script will show you the direct link to the failing run

### PyPI Publication Issues
- Verify your `PYPI_API_TOKEN` secret is correctly set in GitHub
- Check the GitHub Actions logs for PyPI upload errors

## Release Checklist

Before running a release:

- [ ] All features for the release are merged to `main`
- [ ] Tests are passing locally
- [ ] Documentation is updated if needed
- [ ] CHANGELOG.md is updated (optional)
- [ ] No uncommitted changes in working directory

## Version Numbering

We use [Semantic Versioning](https://semver.org/):

- **MAJOR.MINOR.PATCH** (e.g., 1.0.4)
- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

## Example Release Session

```bash
$ ./release.sh 1.0.4
=== Apple Search Ads Python Client Release Script ===

[INFO] Checking prerequisites...
[SUCCESS] Prerequisites check passed

=== VALIDATION PHASE ===
[SUCCESS] Version format is valid: 1.0.4
[SUCCESS] Version v1.0.4 is available
[SUCCESS] Working directory is clean

=== RELEASE PLAN ===
Version: 1.0.4
Tag: v1.0.4
Actions:
  1. Update version in setup.py and pyproject.toml
  2. Run tests and code quality checks
  3. Create commit and tag
  4. Push to GitHub
  5. Wait for GitHub Actions (tests + PyPI publish)
  6. Create GitHub release
  7. Verify PyPI publication

Proceed with release? (y/N): y

=== VERSION UPDATE PHASE ===
[INFO] Updating version to 1.0.4 in setup.py...
[INFO] Updating version to 1.0.4 in pyproject.toml...
[SUCCESS] Version updated in both files
[SUCCESS] Version consistency verified: 1.0.4

=== QUALITY CHECKS PHASE ===
[INFO] Running tests...
[SUCCESS] Tests passed
[INFO] Running code quality checks...
[SUCCESS] Code formatting is correct
[SUCCESS] Type checking passed
[SUCCESS] Linting passed

=== GIT OPERATIONS PHASE ===
[INFO] Creating commit for version 1.0.4...
[SUCCESS] Commit created
[INFO] Creating and pushing tag v1.0.4...
[SUCCESS] Tag v1.0.4 created and pushed

=== CI/CD VERIFICATION PHASE ===
[INFO] Waiting for GitHub Actions to complete...
[SUCCESS] GitHub Actions completed successfully

=== GITHUB RELEASE PHASE ===
[INFO] Creating GitHub release...
[SUCCESS] GitHub release created: https://github.com/bickster/apple-search-ads-python/releases/tag/v1.0.4

=== PYPI VERIFICATION PHASE ===
[INFO] Verifying PyPI publication...
[SUCCESS] Package version 1.0.4 found on PyPI

=== RELEASE COMPLETE ===
[SUCCESS] Release v1.0.4 completed successfully!

📦 PyPI: https://pypi.org/project/apple-search-ads-client/1.0.4/
🎉 GitHub: https://github.com/bickster/apple-search-ads-python/releases/tag/v1.0.4
📋 Actions: https://github.com/bickster/apple-search-ads-python/actions

[INFO] Installation command: pip install apple-search-ads-client==1.0.4
```