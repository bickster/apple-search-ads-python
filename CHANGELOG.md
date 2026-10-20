# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [4.0.1] - Unreleased (retitle with the release date when tagging)

Fixes from an independent review of 4.0.0. Each one is pinned by a test in
`tests/test_review_fixes.py` that fails on 4.0.0.

### Fixed
- **One unreadable ad account no longer fails every all-accounts total.** 4.0.0 added a
  per-account details lookup to `get_all_organizations()` with no error handling, so a
  single 403 or 5xx made `get_daily_spend*` raise for every account. The account is now
  kept, with its spend still counted and its currency, time zone and payment model
  `None`, and a warning is printed. Failed lookups aren't cached, so the next call
  retries. Because a failed account's Basic status is unknown, it is kept even with
  `include_basic=False`.
- **The default account is never a Basic account.** With no `org_id`, 4.0.0 used the
  first ACL entry, which in v1 can be a Basic account, and v1 refuses campaign queries
  on those (403). It now uses the first non-Basic account. Correction: the 4.0.0
  migration notes said `include_basic=False` reproduces 3.x exactly, but that didn't
  hold for calls without an `org_id` when a Basic account was listed first.
- `get_daily_spend_by_app` could produce `app_id` values like `"1134998522.0"` when any
  report row lacked an app (pandas turns the column into float). IDs are always plain
  digit strings again.
- `get_impression_share_data` returns `adamId` as an int, as in v5 (4.0.0 returned a
  string). It now raises `ValueError` for `granularity="WEEKLY"` with a start date that
  isn't a Sunday; v1 weeks run Sunday–Saturday and Apple would reject the request.
- Campaign, ad group and keyword reports for a single day date any row that arrives
  without per-day data with the requested day, instead of leaving `date=None` (which
  the spend helpers then dropped). Apple documents that shape for single-day requests
  without granularity; live DAILY single-day requests still return per-day data
  (checked 2026-10-20), so this is a guard, not a behavior change.

## [4.0.0] - 2026-10-20

**Migration note (breaking):** every call now goes to the Apple Ads Platform API v1, because
Apple shuts down Campaign Management API v5 on 2027-01-26 and 3.x stops working then. Public
method signatures and return shapes are unchanged, and existing v5 API keys keep working.
Read [docs/v4-migration.md](docs/v4-migration.md), which also records the live 3.2.0-vs-4.0
comparison this release was validated against.

### Changed
- **Totals now include Search Ads Basic spend.** v5 never listed Basic (automated) ad
  accounts, so 3.x `fetch_all_orgs` totals silently excluded them. For the account this was
  validated on, that was 2.0% of weekly spend. The new `include_basic` client parameter
  (default `True`) controls this; `include_basic=False` reproduces 3.x numbers exactly.
- `get_daily_spend_by_app` attributes spend from report metadata instead of a campaign
  lookup. That makes fewer API calls, and it counts Basic accounts, whose campaigns v1
  won't list.
- `get_all_campaigns` skips Basic accounts, because v1 returns 403 to campaign queries on
  them.
- Returned objects are v1 dicts with the v5 field names added (`adamId`, `supplySources`,
  `adChannelType`, `bidAmount`, `defaultBidAmount`, `isPreOrder`, …). Where v1 reuses a
  v5 key with a new vocabulary (keyword `status`, ad group `pricingModel`, paused
  campaigns' `displayStatus`), the v5 value is returned. A few v5 fields have no v1
  equivalent and are absent (`budgetAmount`, `budgetOrders`, `targetingDimensions`, …);
  `servingStateReasons` uses v1 reason codes.
- `*_raw` report methods return v1 rows (`metadata`, `totalMetrics`, `granularMetrics`).
- `get_campaign_report` now fills `adam_id` (3.x returned `None` on every row), and keyword
  reports fill `avg_cpm`.
- `get_all_organizations` makes one extra request per ad account to get currency, time
  zone and payment model, which v1's ACL omits. The results are cached per client.
- `get_campaigns`, `get_adgroups` and `get_keywords` page through all results; 3.x's
  campaign and ad group calls read a single page of up to 1000.

### Removed
- `create_impression_share_report()` and `get_impression_share_report()` now raise
  `NotImplementedError`: v1 has no queued custom reports. `get_impression_share_data()`
  queries impression share directly instead; it keeps its signature (`name`,
  `poll_interval` and `max_wait` are ignored) and accepts only `time_zone=None` or `"UTC"`.

### Fixed
- The README said the report time-zone default (`None`) was UTC. Both v5 and v1 actually
  default to each account's own zone (ORTZ): a live comparison matched 35/35 daily rows
  under ORTZ and 0/35 under UTC.

## [3.2.0] - 2026-08-04

### Added
- **Bounded retry for transient failures.** Connection errors, timeouts, and HTTP
  429/502/503/504 are now retried with capped backoff (1s, then 2s); all other errors
  still fail immediately. Configure via the new `retries` client parameter (default 2;
  0 disables). The budget is per public call and spans a whole paged fetch — a
  systemically-down API cannot multiply retries by page count. **Note: this changes
  failure timing** — a persistently failing call now takes up to ~3 attempts plus ~3s
  of backoff before raising, where 3.1.0 raised on the first error. Cross-campaign
  circuit breaking is deliberately left to callers, who own that loop and its
  alerting policy.

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