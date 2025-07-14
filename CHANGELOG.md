# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2024-XX-XX

### Added
- Initial release of Apple Search Ads Python Client
- OAuth2 authentication with JWT support
- Campaign management endpoints
- Performance reporting with pandas DataFrames
- Multi-organization support
- Per-app spend tracking
- Built-in rate limiting
- Comprehensive documentation and examples
- Unit tests with pytest
- GitHub Actions CI/CD pipeline

### Features
- `get_all_organizations()` - Fetch all organizations
- `get_campaigns()` - Get campaigns for an organization
- `get_all_campaigns()` - Get campaigns from all organizations
- `get_campaign_report()` - Get campaign performance metrics
- `get_daily_spend()` - Get daily spend data
- `get_daily_spend_by_app()` - Get spend grouped by app
- Environment variable support for credentials
- Type hints for better IDE support

[Unreleased]: https://github.com/bickster/apple-search-ads-python/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/bickster/apple-search-ads-python/releases/tag/v0.1.0