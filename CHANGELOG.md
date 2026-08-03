# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- `apple_search_ads.__version__` was hardcoded to "0.1.0" and had drifted from the real
  release version since the first release (`release.sh` bumps only `setup.py` and
  `pyproject.toml`). It is now derived from the installed dist metadata via
  `importlib.metadata`, so it can never drift again and needs no per-release edit.

## [3.1.0] - 2026-08-03

### Added
- **Request timeouts.** Every HTTP request — API calls, the OAuth token fetch, and the
  impression-share report download — now carries a timeout (default 30s) instead of
  blocking indefinitely on a stalled connection. Configure via the new `timeout` client
  parameter: a float, a `(connect, read)` tuple, or `None` to restore the old unbounded
  behavior. A tripped timeout raises `requests.exceptions.Timeout`.

## [3.0.0] - 2026-08-03

**Migration note (breaking):** metrics now raise instead of defaulting to 0; money is
`Decimal`; ratios are `None` when absent; reports now page automatically. Pass
`strict=False` to the client to restore v2 zero-fill parsing as a temporary migration aid
(pagination remains on regardless).

### Changed (breaking)
- **Strict metric parsing is the default.** A required metric key missing from an API row
  raises `MissingMetricError` (naming the missing key and listing the keys that were
  present) instead of silently substituting `0`.
- **Money is exact.** `spend`, `avg_cpa`, `avg_cpt`, and `avg_cpm` are `decimal.Decimal`
  built from the original JSON string Apple sent — no float rounding. In DataFrames these
  columns have `object` dtype.
- **Absent ratios are `None`, not `0`.** `ttr`, `conversion_rate`, and `tap_install_rate`
  are legitimately absent on 0-denominator days; `None` keeps that distinguishable from a
  genuine zero.
- **LAT metrics are optional.** `lat_on_installs` / `lat_off_installs` are `None` when
  absent — the live API no longer returns them (Apple retired LAT reporting).

### Added
- **Automatic pagination for all reports and `get_keywords`.** Reports over 1000 rows are
  no longer silently truncated; the client follows `totalResults`/`startIndex`/`itemsPerPage`
  until complete and raises `PaginationError` if a page makes no progress.
- **Raw report accessors** for consumers that validate entries themselves:
  `get_campaign_report_raw()`, `get_adgroup_report_raw()`, `get_keyword_report_raw()`,
  `get_search_term_report_raw()`, `get_adgroup_search_term_report_raw()` return the fully
  paginated `List[Dict[str, Any]]` rows exactly as Apple sent them (money as original
  strings).
- `strict: bool = True` client parameter; `MissingMetricError` and `PaginationError`
  exception types.

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