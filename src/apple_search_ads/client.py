"""
Apple Search Ads API Client for Python

A Python client for the Apple Ads Platform API v1, the successor to Campaign
Management API v5 (which Apple sunsets on 2027-01-26). Public methods keep
their v5-era signatures and return shapes; see docs/v4-migration.md.
"""

import jwt
import time
import os
import requests
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Tuple, Union, Any
import pandas as pd
from ratelimit import limits, sleep_and_retry

from .exceptions import MissingMetricError, PaginationError


class _RetryBudget:
    """Mutable retry allowance shared across the requests of one public call.

    Paged fetches pass one budget through every page so a systemically-down
    API cannot multiply retries by page count."""

    def __init__(self, remaining: int):
        self.remaining = remaining


class AppleSearchAdsClient:
    """
    Client for the Apple Ads Platform API v1.

    This client provides methods to interact with Apple Search Ads,
    including campaign management, reporting, and spend tracking.

    Objects returned by the API (organizations, campaigns, ad groups, keywords,
    apps) are Apple's v1 dicts with the v5 field names added alongside, so code
    written against 3.x keeps reading the same keys. Where v1 reuses a v5 key
    with a different vocabulary (keyword ``status``, ad group ``pricingModel``)
    the v5 value wins. See docs/v4-migration.md for the full mapping.

    Args:
        client_id: Apple Search Ads client ID
        team_id: Apple Search Ads team ID
        key_id: Apple Search Ads key ID
        private_key_path: Path to the private key .p8 file
        private_key_content: Private key content as string (alternative to file path)
        org_id: Optional ad account ID (v5 called it orgId; the values are the same).
            Fetched automatically if not provided.
        strict: If True (default), report metric parsing raises MissingMetricError
            when a required field is absent, returns None for absent ratios, and
            returns money as exact Decimal values. If False, restores the v2
            zero-fill behavior (floats, 0 defaults) as a migration aid only.
        timeout: Timeout in seconds applied to every HTTP request (default 30.0).
            Accepts a float or a (connect, read) tuple, passed straight to
            requests. None disables the timeout entirely — requests will then
            block indefinitely on a stalled connection, as in versions <= 3.0.0.
            A tripped timeout raises requests.exceptions.Timeout.
        retries: Retries allowed per public call for transient failures only —
            connection errors, timeouts, and HTTP 429/502/503/504 (default 2,
            with backoff of 1s then 2s, capped). Other errors fail immediately.
            The budget spans a whole paged fetch, not each page. 0 disables
            retries. Cross-campaign circuit breaking is deliberately left to
            the caller, which owns that loop.
        include_basic: If True (default), Apple Search Ads Basic (automated)
            ad accounts are included in get_all_organizations() and therefore
            in every fetch_all_orgs total. v5 never exposed Basic accounts, so
            3.x totals silently excluded their spend; pass False to reproduce
            3.x numbers exactly. Basic accounts report on their own time zone
            (UTC for Bickster's), not the advanced accounts' one.

    Example:
        >>> client = AppleSearchAdsClient(
        ...     client_id="your_client_id",
        ...     team_id="your_team_id",
        ...     key_id="your_key_id",
        ...     private_key_path="/path/to/private_key.p8"
        ... )
        >>> campaigns = client.get_campaigns()
    """

    BASE_URL = "https://api.ads.apple.com/v1"

    def __init__(
        self,
        client_id: Optional[str] = None,
        team_id: Optional[str] = None,
        key_id: Optional[str] = None,
        private_key_path: Optional[str] = None,
        private_key_content: Optional[str] = None,
        org_id: Optional[str] = None,
        strict: bool = True,
        timeout: Optional[Union[float, Tuple[float, float]]] = 30.0,
        retries: int = 2,
        include_basic: bool = True,
    ):
        # Try to get credentials from parameters, then environment variables
        self.client_id = client_id or os.environ.get("APPLE_SEARCH_ADS_CLIENT_ID")
        self.team_id = team_id or os.environ.get("APPLE_SEARCH_ADS_TEAM_ID")
        self.key_id = key_id or os.environ.get("APPLE_SEARCH_ADS_KEY_ID")
        self.private_key_path = private_key_path or os.environ.get(
            "APPLE_SEARCH_ADS_PRIVATE_KEY_PATH"
        )
        self.private_key_content = private_key_content

        # Validate required credentials
        if not all([self.client_id, self.team_id, self.key_id]):
            raise ValueError(
                "Missing required credentials. Please provide client_id, team_id, and key_id "
                "either as parameters or environment variables."
            )

        if not self.private_key_path and not self.private_key_content:
            raise ValueError(
                "Missing private key. Please provide either private_key_path or private_key_content."
            )

        self.org_id = org_id
        self.strict = strict
        self.timeout = timeout
        self.retries = retries
        self.include_basic = include_basic
        self._ad_account_cache: Dict[str, Dict[str, Any]] = {}
        self._token: Optional[str] = None
        self._token_expiry: Optional[float] = None

    def _load_private_key(self) -> str:
        """Load private key from file or content."""
        if self.private_key_content:
            return self.private_key_content

        if not self.private_key_path:
            raise ValueError("No private key path provided")

        if not os.path.exists(self.private_key_path):
            raise FileNotFoundError(f"Private key file not found: {self.private_key_path}")

        with open(self.private_key_path, "r") as f:
            return f.read()

    def _generate_client_secret(self) -> str:
        """Generate client secret JWT for Apple Search Ads."""
        # Token expires in 180 days (max allowed by Apple)
        expiry = int(time.time() + 86400 * 180)

        payload = {
            "sub": self.client_id,
            "aud": "https://appleid.apple.com",
            "iat": int(time.time()),
            "exp": expiry,
            "iss": self.team_id,
        }

        headers = {"alg": "ES256", "kid": self.key_id}

        private_key = self._load_private_key()

        return jwt.encode(payload, private_key, algorithm="ES256", headers=headers)

    def _get_access_token(self) -> str:
        """Get access token using client credentials flow.

        The Platform API uses the same token endpoint and scope as v5, so
        existing v5 API keys keep working (verified 2026-10-19)."""
        if self._token and self._token_expiry and time.time() < self._token_expiry:
            return self._token

        token_url = "https://appleid.apple.com/auth/oauth2/token"

        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self._generate_client_secret(),
            "scope": "searchadsorg",
        }

        response = requests.post(token_url, data=data, timeout=self.timeout)
        response.raise_for_status()

        token_data = response.json()
        self._token = token_data["access_token"]
        # Token expires in 1 hour, refresh 5 minutes before
        self._token_expiry = time.time() + 3300

        if self._token is None:
            raise ValueError("Failed to obtain access token")
        return self._token

    def _get_headers(self, include_org_context: bool = True) -> Dict[str, str]:
        """Get headers for API requests."""
        headers = {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json",
        }

        # Scope to the ad account if we have one (not needed for the ACLs endpoint)
        if include_org_context and self.org_id:
            headers["X-AP-Context"] = f"adAccountId={self.org_id}"

        return headers

    def _get_org_id(self) -> str:
        """Get the ad account ID (v5 orgId) of the first account the user can access.

        Basic (automated) accounts are passed over: v5 never listed them, and v1
        refuses campaign queries on them, so defaulting to one would break every
        org-scoped call. Falls back to the first account if all are Basic."""
        if self.org_id:
            return self.org_id

        acls = self._get_acls()
        if acls:
            account_ids = [str(acl["adAccount"]["id"]) for acl in acls]
            self.org_id = next(
                (a for a in account_ids if not self._is_basic(self._try_get_ad_account(a))),
                account_ids[0],
            )
            return self.org_id

        raise ValueError("No organization found for this account")

    _RETRYABLE_STATUSES = (429, 502, 503, 504)
    _BACKOFF_CAP_SECONDS = 2.0

    @sleep_and_retry
    @limits(calls=10, period=1)  # Apple Search Ads rate limit
    def _send_request(
        self,
        url: str,
        method: str,
        json_data: Optional[Union[Dict, List]],
        params: Optional[Dict],
        include_org_context: bool,
    ) -> Dict[str, Any]:
        """Send a single rate-limited request to the API."""
        response = requests.request(
            method=method,
            url=url,
            headers=self._get_headers(include_org_context=include_org_context),
            json=json_data,
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _is_retryable_error(exc: requests.exceptions.RequestException) -> bool:
        if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
            return True
        if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
            return exc.response.status_code in AppleSearchAdsClient._RETRYABLE_STATUSES
        return False

    @staticmethod
    def _retry_sleep(seconds: float) -> None:
        """Backoff sleep, separated from the rate limiter's sleep for testability."""
        time.sleep(seconds)

    def _make_request(
        self,
        url: str,
        method: str = "GET",
        json_data: Optional[Union[Dict, List]] = None,
        params: Optional[Dict] = None,
        include_org_context: bool = True,
        retry_budget: Optional[_RetryBudget] = None,
    ) -> Dict[str, Any]:
        """Make an API request, retrying transient failures within a bounded budget.

        Only connection errors, timeouts, and HTTP 429/502/503/504 are retried;
        everything else fails fast. When retry_budget is shared (paged fetches),
        retries are bounded across the whole fetch, not per page.
        """
        budget = retry_budget if retry_budget is not None else _RetryBudget(self.retries)
        attempt = 0
        while True:
            try:
                return self._send_request(url, method, json_data, params, include_org_context)
            except requests.exceptions.RequestException as exc:
                if not self._is_retryable_error(exc) or budget.remaining <= 0:
                    raise
                budget.remaining -= 1
                self._retry_sleep(min(2.0**attempt, self._BACKOFF_CAP_SECONDS))
                attempt += 1

    def _parse_date_param(self, date: Union[datetime, str]) -> datetime:
        """Convert string date to datetime if needed."""
        if isinstance(date, str):
            return datetime.strptime(date, "%Y-%m-%d")
        return date

    @staticmethod
    def _equals_filter(field: str, value: Union[int, str]) -> Dict[str, Any]:
        return {"field": field, "operator": "EQUALS", "value": str(value)}

    def _build_report_request(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: Optional[str] = None,
        time_zone: Optional[str] = None,
        offset: int = 0,
        limit: int = 1000,
        filters: Optional[List[Dict[str, Any]]] = None,
        group_by: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Build standard report request data.

        No timeZone means the API default, ORTZ — the same default v5 applied
        (3.x and 4.0 daily rows matched 35/35 under ORTZ, 0/35 under UTC)."""
        time_range: Dict[str, Any] = {
            "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
        }
        if granularity:
            time_range["granularity"] = granularity
        if time_zone:
            time_range["timeZone"] = time_zone
        request: Dict[str, Any] = {
            "timeRange": time_range,
            "sorting": [{"field": "localSpend", "order": "DESC"}],
            "pagination": {"offset": offset, "pageSize": limit},
        }
        if filters:
            request["filters"] = filters
        if group_by:
            request["groupBy"] = list(group_by)
        return request

    def _extract_rows_from_response(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract rows from a response: `result.rows` for reports, `result` for queries."""
        if not response:
            return []
        result = response.get("result")
        if isinstance(result, list):
            return result
        if isinstance(result, dict) and isinstance(result.get("rows"), list):
            return result["rows"]
        return []

    def _extract_pagination_from_response(
        self, response: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Extract the top-level pagination block (a sibling of `result`, not nested in it)."""
        if not response:
            return None
        pagination = response.get("pagination")
        if isinstance(pagination, dict):
            return pagination
        return None

    def _fetch_paged(
        self,
        url: str,
        build_request: Callable[[int, int], Dict[str, Any]],
        limit: int = 1000,
        paginate: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        POST build_request(offset, limit) page by page until every row is fetched.

        Raises PaginationError if a page makes no progress (would loop forever)
        or if paginate=False and the single page does not contain all rows.
        """
        rows: List[Dict[str, Any]] = []
        offset = 0
        retry_budget = _RetryBudget(self.retries)
        while True:
            response = self._make_request(
                url,
                method="POST",
                json_data=build_request(offset, limit),
                retry_budget=retry_budget,
            )
            page_rows = self._extract_rows_from_response(response)
            pagination = self._extract_pagination_from_response(response)
            rows.extend(page_rows)

            if pagination is None:
                break

            start_index = int(pagination.get("offset", offset))
            items = len(page_rows)
            total = pagination.get("totalCount")

            if total is None:
                # Without a total, a short page is the last one.
                if items < limit:
                    break
                if not paginate:
                    raise PaginationError(
                        f"Result may be truncated: received a full page of {items} rows "
                        f"from {url} with pagination disabled"
                    )
            else:
                total = int(total)
                if start_index + items >= total:
                    break
                if not paginate:
                    raise PaginationError(
                        f"Result truncated: received {len(rows)} of {total} rows from {url} "
                        "with pagination disabled"
                    )
                if items == 0:
                    raise PaginationError(
                        f"No pagination progress from {url}: page at offset {offset} returned "
                        f"0 rows with totalCount={total}"
                    )
            offset = start_index + items

        return rows

    def _fetch_report_rows(
        self,
        url: str,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        granularity: Optional[str] = None,
        time_zone: Optional[str] = None,
        limit: int = 1000,
        paginate: bool = True,
        filters: Optional[List[Dict[str, Any]]] = None,
        group_by: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch all rows for a report, following pagination until complete."""
        start_dt = self._parse_date_param(start_date)
        end_dt = self._parse_date_param(end_date)

        def build(offset: int, page_size: int) -> Dict[str, Any]:
            return self._build_report_request(
                start_dt, end_dt, granularity, time_zone, offset, page_size, filters, group_by
            )

        return self._fetch_paged(url, build, limit=limit, paginate=paginate)

    def _query_all(
        self,
        url: str,
        filters: Optional[List[Dict[str, Any]]] = None,
        sorting: Optional[List[Dict[str, Any]]] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Fetch every object from a v1 `/…/query` endpoint."""

        def build(offset: int, page_size: int) -> Dict[str, Any]:
            request: Dict[str, Any] = {
                "pagination": {"offset": offset, "pageSize": page_size, "fetchTotalCount": True}
            }
            if filters:
                request["filters"] = filters
            if sorting:
                request["sorting"] = sorting
            return request

        return self._fetch_paged(url, build, limit=limit)

    # Output field -> Apple key.
    # Count facts must be present in strict mode; ratios may legitimately be
    # absent (0-denominator days); optional money is ratio-derived.
    _COUNT_FACTS = (
        ("impressions", "impressions"),
        ("taps", "taps"),
        ("installs", "totalInstalls"),
        ("new_downloads", "totalNewDownloads"),
        ("redownloads", "totalRedownloads"),
        ("tap_installs", "tapInstalls"),
        ("view_installs", "viewInstalls"),
        ("tap_new_downloads", "tapNewDownloads"),
        ("tap_redownloads", "tapRedownloads"),
        ("view_new_downloads", "viewNewDownloads"),
        ("view_redownloads", "viewRedownloads"),
    )
    # Retired by Apple (LAT ended with ATT); the live API omits them entirely
    # (verified 2026-08-03). Absent -> None, never 0.
    _OPTIONAL_COUNTS = (
        ("lat_on_installs", "latOnInstalls"),
        ("lat_off_installs", "latOffInstalls"),
    )
    # v1 renamed avgCPT/avgCPM to cpt/cpm.
    _OPTIONAL_MONEY = (
        ("avg_cpa", "totalAvgCPI"),
        ("avg_cpt", "cpt"),
        ("avg_cpm", "cpm"),
    )
    _RATIOS = (
        ("ttr", "ttr"),
        ("conversion_rate", "totalInstallRate"),
        ("tap_install_rate", "tapInstallRate"),
    )

    @staticmethod
    def _require_metric(day_data: Dict[str, Any], key: str) -> Any:
        if key not in day_data:
            raise MissingMetricError(key, list(day_data.keys()))
        return day_data[key]

    def _parse_metrics(self, day_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse common metrics from row data."""
        if self.strict:
            return self._parse_metrics_strict(day_data)
        return self._parse_metrics_zero_fill(day_data)

    def _parse_metrics_strict(self, day_data: Dict[str, Any]) -> Dict[str, Any]:
        """Strict parsing: base facts must be present, absent ratios are None,
        money is Decimal built from the original JSON string."""
        metrics: Dict[str, Any] = {}

        for out_name, key in self._COUNT_FACTS:
            metrics[out_name] = self._require_metric(day_data, key)

        for out_name, key in self._OPTIONAL_COUNTS:
            metrics[out_name] = day_data.get(key)

        local_spend = self._require_metric(day_data, "localSpend") or {}
        if "amount" not in local_spend:
            raise MissingMetricError("localSpend.amount", list(local_spend.keys()))
        metrics["spend"] = Decimal(str(local_spend["amount"]))
        metrics["currency"] = local_spend.get("currency")

        for out_name, key in self._OPTIONAL_MONEY:
            amount = (day_data.get(key) or {}).get("amount")
            metrics[out_name] = Decimal(str(amount)) if amount is not None else None

        for out_name, key in self._RATIOS:
            metrics[out_name] = day_data.get(key)

        return metrics

    def _parse_metrics_zero_fill(self, day_data: Dict[str, Any]) -> Dict[str, Any]:
        """v2 parsing, preserved exactly for strict=False: every field defaults
        to 0 and money is float. Migration aid only — silently masks missing data."""
        metrics: Dict[str, Any] = {}
        for out_name, key in self._COUNT_FACTS + self._OPTIONAL_COUNTS:
            metrics[out_name] = day_data.get(key, 0)
        metrics["spend"] = float((day_data.get("localSpend") or {}).get("amount", 0))
        metrics["currency"] = (day_data.get("localSpend") or {}).get("currency", "USD")
        for out_name, key in self._OPTIONAL_MONEY:
            metrics[out_name] = float((day_data.get(key) or {}).get("amount", 0))
        for out_name, key in self._RATIOS:
            metrics[out_name] = day_data.get(key, 0)
        return metrics

    @classmethod
    def _zero_day(cls, day_data: Dict[str, Any], row: Dict[str, Any]) -> Dict[str, Any]:
        """Expand v1's date-only entry for an idle day into the explicit zero row
        v5 sent for it (all 798 such rows in a live week were all-zero in v5,
        with null ratios). Any other partial entry is left for strict parsing."""
        if any(key != "date" for key in day_data):
            return day_data
        currency = ((row.get("totalMetrics") or {}).get("localSpend") or {}).get("currency")
        zero: Dict[str, Any] = {key: 0 for _, key in cls._COUNT_FACTS}
        zero["localSpend"] = {"amount": "0", "currency": currency}
        zero.update(day_data)
        return zero

    def _single_day(
        self, start_date: Union[datetime, str], end_date: Union[datetime, str]
    ) -> Optional[str]:
        """The date of a one-day range, else None. Apple documents single-day
        requests without granularity as totalMetrics-only (no per-day date);
        DAILY requests get granularMetrics today (verified 2026-10-20), so this
        only guards against that changing — it never guesses a multi-day date."""
        start = self._parse_date_param(start_date).strftime("%Y-%m-%d")
        end = self._parse_date_param(end_date).strftime("%Y-%m-%d")
        return start if start == end else None

    def _report_rows_to_df(
        self,
        rows: List[Dict[str, Any]],
        parse_row: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
        fallback_date: Optional[str] = None,
    ) -> pd.DataFrame:
        """Flatten report rows into one record per row per granular period.

        Rows without granularMetrics (search term reports) yield one record
        from totalMetrics, dated fallback_date."""
        data = []
        for row in rows:
            metadata = row.get("metadata", {})
            if "granularMetrics" in row:
                for day_data in row["granularMetrics"] or []:
                    day_data = self._zero_day(day_data, row)
                    entry = {"date": day_data.get("date")}
                    entry.update(parse_row(day_data, metadata))
                    data.append(entry)
            else:
                metrics = row.get("totalMetrics", {})
                entry = {"date": metrics.get("date", fallback_date)}
                entry.update(parse_row(metrics, metadata))
                data.append(entry)
        return pd.DataFrame(data)

    # --- v5 compatibility -------------------------------------------------
    # v1 values that differ from the v5 vocabulary for the same concept.
    # Each mapping was verified against live v5 objects on 2026-10-19.
    _SUPPLY_SOURCE_TO_V5 = {"APPSTORE_PRODUCT_PAGES": "APPSTORE_PRODUCT_PAGES_BROWSE"}
    _PRICING_MODEL_TO_V5 = {"CPT": "CPC"}
    _KEYWORD_STATUS_TO_V5 = {"ENABLED": "ACTIVE"}
    _BASIC_PRODUCT_FEATURE = "APPSTORE_APP_AUTOMATED"

    @staticmethod
    def _to_int(value: Any) -> Any:
        """v5 sent adamIds as ints; v1 sends some as strings."""
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return value

    @staticmethod
    def _add_missing(target: Dict[str, Any], aliases: Dict[str, Any]) -> Dict[str, Any]:
        """Add v5-named keys without clobbering any key v1 already sent."""
        for key, value in aliases.items():
            target.setdefault(key, value)
        return target

    def _compat_campaign(self, campaign: Dict[str, Any]) -> Dict[str, Any]:
        targeting = campaign.get("targeting") or {}
        placements = (targeting.get("supplyPlacement") or {}).get("include") or []
        supply_sources = [self._SUPPLY_SOURCE_TO_V5.get(p, p) for p in placements]
        bid_strategy = campaign.get("bidStrategy") or {}
        countries = (targeting.get("countryOrRegion") or {}).get("include")
        sapin = [
            r.get("responseValue")
            for r in campaign.get("regulationResponses") or []
            if r.get("regulationType") == "CAMPAIGN_SAPIN_LAW"
        ]
        # v1 splits v5's PAUSED into ON_HOLD/LIMITED; v5 showed every user-paused
        # campaign as PAUSED (131/131).
        if campaign.get("status") == "PAUSED" and "displayStatus" in campaign:
            campaign["displayStatus"] = "PAUSED"
        return self._add_missing(
            campaign,
            {
                "adamId": self._to_int(campaign.get("promotedObjectId")),
                "orgId": campaign.get("adAccountId"),
                "countriesOrRegions": sorted(countries) if countries is not None else None,
                "supplySources": supply_sources,
                # Search results is SEARCH; every other placement is DISPLAY (143/143).
                "adChannelType": (
                    "SEARCH" if supply_sources == ["APPSTORE_SEARCH_RESULTS"] else "DISPLAY"
                ),
                "dailyBudgetAmount": (campaign.get("dailyBudget") or {}).get("value"),
                "biddingStrategy": bid_strategy.get("bidStrategyType"),
                # v5's targetCpa is the bid of a MAX_CONVERSIONS strategy (3/3).
                "targetCpa": (
                    bid_strategy.get("bid")
                    if bid_strategy.get("bidStrategyType") == "MAX_CONVERSIONS"
                    else None
                ),
                "sapinLawResponse": sapin[0] if sapin else None,
                "servingStatus": campaign.get("systemStatus"),
                # v1 vocabulary (e.g. AD_GROUPS_NOT_RUNNING, not NO_AVAILABLE_AD_GROUPS).
                "servingStateReasons": campaign.get("systemStatusReasons") or None,
            },
        )

    def _compat_adgroup(self, adgroup: Dict[str, Any]) -> Dict[str, Any]:
        bid_strategy = adgroup.get("bidStrategy") or {}
        if "pricingModel" in adgroup:
            adgroup["pricingModel"] = self._PRICING_MODEL_TO_V5.get(
                adgroup["pricingModel"], adgroup["pricingModel"]
            )
        return self._add_missing(
            adgroup,
            {
                "orgId": adgroup.get("adAccountId"),
                "defaultBidAmount": bid_strategy.get("bid"),
                "cpaGoal": (adgroup.get("cpaCap") or {}).get("value"),
                "biddingStrategy": bid_strategy.get("bidStrategyType"),
                "servingStatus": adgroup.get("systemStatus"),
                "servingStateReasons": adgroup.get("systemStatusReasons") or None,
            },
        )

    def _compat_keyword(self, keyword: Dict[str, Any]) -> Dict[str, Any]:
        if "status" in keyword:
            keyword["status"] = self._KEYWORD_STATUS_TO_V5.get(keyword["status"], keyword["status"])
        return self._add_missing(keyword, {"bidAmount": keyword.get("bid")})

    def _compat_app(self, app: Dict[str, Any]) -> Dict[str, Any]:
        is_preorder = app.get("isPreorder")
        return self._add_missing(
            app,
            {
                "adamId": self._to_int(app.get("id")),
                # v5 sent this as the string "true"/"false".
                "isPreOrder": None if is_preorder is None else str(bool(is_preorder)).lower(),
            },
        )

    def _get_acls(self) -> List[Dict[str, Any]]:
        response = self._make_request(f"{self.BASE_URL}/acls", include_org_context=False)
        return ((response or {}).get("result") or {}).get("acls") or []

    def _get_ad_account(self, ad_account_id: str) -> Dict[str, Any]:
        """Ad account details, fetched once per client: the v1 ACL lacks the
        currency/timezone/features v5's ACL carried, and fetch_all_orgs calls
        get_all_organizations repeatedly."""
        if ad_account_id in self._ad_account_cache:
            return self._ad_account_cache[ad_account_id]
        current_org_id = self.org_id
        self.org_id = ad_account_id
        try:
            response = self._make_request(f"{self.BASE_URL}/ad-accounts/{ad_account_id}")
        finally:
            self.org_id = current_org_id
        details: Dict[str, Any] = (response or {}).get("result") or {}
        self._ad_account_cache[ad_account_id] = details
        return details

    def _try_get_ad_account(self, ad_account_id: str) -> Dict[str, Any]:
        """_get_ad_account, but an API failure yields {} (not cached, so a
        later call retries) instead of raising."""
        try:
            return self._get_ad_account(ad_account_id)
        except requests.exceptions.RequestException as e:
            print(f"Error fetching details for ad account {ad_account_id}: {e}")
            return {}

    @classmethod
    def _is_basic(cls, details: Dict[str, Any]) -> bool:
        return cls._BASIC_PRODUCT_FEATURE in (details.get("productFeatures") or [])

    def get_all_organizations(self) -> List[Dict[str, Any]]:
        """
        Get all organizations (v1 ad accounts) the user has access to.

        Returns:
            List of organization dictionaries in the v5 shape: orgId, orgName,
            displayName, currency, paymentModel, roleNames, parentOrgId,
            timeZone, plus productFeatures. orgId is the v1 ad account id.
            Basic (automated) accounts are omitted when include_basic=False.
        """
        organizations = []
        for acl in self._get_acls():
            ad_account = acl.get("adAccount") or {}
            account_id = ad_account.get("id")
            # One unreadable account must not fail every fetch_all_orgs total;
            # it is kept (its spend still counts) with its details unknown.
            details = self._try_get_ad_account(str(account_id))
            features = details.get("productFeatures") or []
            if not self.include_basic and self._is_basic(details):
                continue
            parent_id = ad_account.get("orgId")
            organizations.append(
                {
                    "orgId": account_id,
                    "orgName": ad_account.get("name"),
                    "displayName": ad_account.get("name"),
                    "currency": details.get("currency"),
                    "paymentModel": details.get("paymentModel"),
                    "roleNames": acl.get("roles"),
                    # v5 gave the parent org itself parentOrgId=None (9/9 matched).
                    "parentOrgId": parent_id if parent_id != account_id else None,
                    "timeZone": details.get("timezone"),
                    "productFeatures": features,
                }
            )
        return organizations

    def get_app_details(self, adam_id: Union[int, str]) -> Dict[str, Any]:
        """
        Get app metadata for a specific app.

        Args:
            adam_id: The App Store app identifier

        Returns:
            Dict with app details including:
            - adamId: App Store app identifier
            - appName: The app name
            - artistName: Developer/artist name
            - primaryLanguage: Primary language code (e.g., "en-US")
            - primaryGenre: Primary app category
            - secondaryGenre: Secondary app category (if any)
            - deviceClasses: List of supported devices (e.g., ["IPHONE", "IPAD"])
            - iconPictureUrl: URL to the app icon
            - isPreOrder: Whether app is in pre-order ("true"/"false", as v5 sent it)
            - availableStorefronts: List of country codes where app is available
        """
        if not self.org_id:
            self._get_org_id()

        url = f"{self.BASE_URL}/apps/{adam_id}"
        response = self._make_request(url, method="GET")

        if response and isinstance(response.get("result"), dict):
            return self._compat_app(response["result"])

        return {}

    def get_adgroups(self, campaign_id: str) -> List[Dict[str, Any]]:
        """
        Get all ad groups for a specific campaign.

        Args:
            campaign_id: The campaign ID to get ad groups for

        Returns:
            List of ad group dictionaries
        """
        # Ensure we have org_id for the context header
        if not self.org_id:
            self._get_org_id()

        adgroups = self._query_all(
            f"{self.BASE_URL}/adgroups/query",
            filters=[self._equals_filter("campaignId", campaign_id)],
        )
        return [self._compat_adgroup(adgroup) for adgroup in adgroups]

    def get_keywords(
        self,
        campaign_id: Union[int, str],
        adgroup_id: Optional[Union[int, str]] = None,
        include_deleted: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get targeting keywords for a campaign or specific ad group.

        Args:
            campaign_id: The campaign ID to get keywords for
            adgroup_id: Optional ad group ID to filter keywords to a specific ad group
            include_deleted: Whether to include deleted keywords (default: False)

        Returns:
            List of keyword dictionaries with fields:
            - id: Unique keyword identifier
            - adGroupId: Parent ad group identifier
            - text: The keyword text
            - status: Keyword status (ACTIVE, PAUSED)
            - matchType: Match type (EXACT, BROAD)
            - bidAmount: Bid amount dict with 'amount' and 'currency'
            - modificationTime: Last modification timestamp
            - deleted: Whether the keyword is deleted
        """
        if not self.org_id:
            self._get_org_id()

        filters = [self._equals_filter("campaignId", campaign_id)]
        if not include_deleted:
            filters.append(self._equals_filter("deleted", "false"))
        if adgroup_id is not None:
            filters.append(self._equals_filter("adGroupId", adgroup_id))

        keywords = self._query_all(
            f"{self.BASE_URL}/keywords/query",
            filters=filters,
            sorting=[{"field": "id", "order": "ASC"}],
        )
        return [self._compat_keyword(keyword) for keyword in keywords]

    def update_keyword_bid(
        self,
        campaign_id: Union[int, str],
        adgroup_id: Union[int, str],
        keyword_id: Union[int, str],
        bid_amount: Union[float, str],
        currency: str,
    ) -> Dict[str, Any]:
        """
        Update the bid amount for a targeting keyword.

        Args:
            campaign_id: The campaign ID containing the keyword (unused by v1,
                which addresses keywords by id alone; kept for compatibility)
            adgroup_id: The ad group ID containing the keyword (unused, as above)
            keyword_id: The keyword ID to update
            bid_amount: The new bid amount (e.g., 1.50 or "1.50")
            currency: The currency code (e.g., "USD", "EUR")

        Returns:
            Dict with the updated keyword data

        Raises:
            ValueError: If bid_amount is not positive or currency is invalid
        """
        if not self.org_id:
            self._get_org_id()

        # Validate and convert bid_amount
        try:
            bid_value = float(bid_amount)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid bid_amount: {bid_amount}. Must be a positive number.")

        if bid_value <= 0:
            raise ValueError(f"bid_amount must be positive, got: {bid_value}")

        # Validate currency (must be 3-letter code)
        currency = str(currency).strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError(
                f"Invalid currency: {currency}. Must be a 3-letter currency code (e.g., 'USD')."
            )

        url = f"{self.BASE_URL}/keywords/{keyword_id}"
        request_data = {"bid": {"amount": str(bid_value), "currency": currency}}

        response = self._make_request(url, method="PUT", json_data=request_data)

        if response and isinstance(response.get("result"), dict):
            return self._compat_keyword(response["result"])

        return {}

    def get_campaigns(
        self,
        org_id: Optional[str] = None,
        supply_source: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get all campaigns for a specific organization or the default one.

        Args:
            org_id: Optional organization ID. If not provided, uses the default org.
            supply_source: Optional filter by supply source type. Valid values:
                - APPSTORE_SEARCH_RESULTS: Search results ads
                - APPSTORE_SEARCH_TAB: Search tab ads
                - APPSTORE_TODAY_TAB: Today tab ads
                - APPSTORE_PRODUCT_PAGES_BROWSE: "You Might Also Like" ads

        Returns:
            List of campaign dictionaries. Each campaign includes 'supplySources'
            field indicating the ad placement type(s).
        """
        # Use provided org_id or get the default one
        original_org_id = None
        if org_id:
            original_org_id = self.org_id
            self.org_id = str(org_id)
        elif not self.org_id:
            self._get_org_id()

        try:
            campaigns = [
                self._compat_campaign(campaign)
                for campaign in self._query_all(f"{self.BASE_URL}/campaigns/query")
            ]

            # Add org_id to each campaign for tracking
            for campaign in campaigns:
                campaign["fetched_org_id"] = self.org_id

            # Filter by supply_source if specified
            if supply_source:
                campaigns = [c for c in campaigns if supply_source in c.get("supplySources", [])]

            return campaigns
        finally:
            # Restore original org_id if we changed it
            if original_org_id is not None:
                self.org_id = original_org_id

    def get_all_campaigns(self, supply_source: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get campaigns from all organizations.

        Args:
            supply_source: Optional filter by supply source type. Valid values:
                - APPSTORE_SEARCH_RESULTS: Search results ads
                - APPSTORE_SEARCH_TAB: Search tab ads
                - APPSTORE_TODAY_TAB: Today tab ads
                - APPSTORE_PRODUCT_PAGES_BROWSE: "You Might Also Like" ads

        Returns:
            List of all campaigns across all organizations. Basic (automated)
            accounts are skipped: v1 refuses campaign queries on them (403),
            though their spend still appears in the report-based methods.
        """
        all_campaigns = []
        organizations = self.get_all_organizations()

        for org in organizations:
            if self._BASIC_PRODUCT_FEATURE in (org.get("productFeatures") or []):
                continue
            org_id = str(org["orgId"])
            org_name = org.get("orgName", "Unknown")

            try:
                campaigns = self.get_campaigns(org_id=org_id, supply_source=supply_source)

                # Add organization info to each campaign
                for campaign in campaigns:
                    campaign["org_name"] = org_name
                    campaign["parent_org_id"] = org.get("parentOrgId")

                all_campaigns.extend(campaigns)
            except Exception as e:
                print(f"Error fetching campaigns from {org_name}: {e}")

        return all_campaigns

    def _parse_campaign_row(self, row: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Parse a single campaign row into a flat dict."""
        base = {
            "campaign_id": metadata.get("id"),
            "campaign_name": metadata.get("name"),
            "campaign_status": metadata.get("status"),
            "app_name": (metadata.get("promotedObject") or {}).get("name"),
            "adam_id": self._to_int(metadata.get("promotedObjectId")),
        }
        base.update(self._parse_metrics(row))
        return base

    def get_campaign_report_raw(
        self,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        granularity: str = "DAILY",
        time_zone: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get campaign performance report as raw API rows.

        Returns every row across all pages, exactly as Apple sent them —
        no metric parsing, money amounts left as their original JSON strings.

        Args:
            start_date: Start date for the report (datetime or YYYY-MM-DD string)
            end_date: End date for the report (datetime or YYYY-MM-DD string)
            granularity: DAILY, WEEKLY, or MONTHLY
            time_zone: Optional timezone (e.g., "ORTZ" for org timezone, "UTC")

        Returns:
            List of raw report row dicts (metadata + totalMetrics/granularMetrics).
        """
        if not self.org_id:
            self._get_org_id()

        url = f"{self.BASE_URL}/reports/apps/campaigns/query"
        return self._fetch_report_rows(url, start_date, end_date, granularity, time_zone)

    def get_campaign_report(
        self,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        granularity: str = "DAILY",
        time_zone: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Get campaign performance report.

        Args:
            start_date: Start date for the report (datetime or YYYY-MM-DD string)
            end_date: End date for the report (datetime or YYYY-MM-DD string)
            granularity: DAILY, WEEKLY, or MONTHLY
            time_zone: Optional timezone (e.g., "ORTZ" for org timezone, "UTC")

        Returns:
            DataFrame with campaign performance metrics.
        """
        rows = self.get_campaign_report_raw(start_date, end_date, granularity, time_zone)
        return self._report_rows_to_df(
            rows, self._parse_campaign_row, self._single_day(start_date, end_date)
        )

    def _parse_adgroup_row(
        self, row: Dict[str, Any], metadata: Dict[str, Any], campaign_id: str
    ) -> Dict[str, Any]:
        """Parse a single ad group row into a flat dict."""
        base = {
            "campaign_id": campaign_id,
            "adgroup_id": metadata.get("id"),
            "adgroup_name": metadata.get("name"),
            "adgroup_status": metadata.get("status"),
        }
        base.update(self._parse_metrics(row))
        return base

    def get_adgroup_report_raw(
        self,
        campaign_id: str,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        granularity: str = "DAILY",
        time_zone: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get ad group performance report as raw API rows.

        Returns every row across all pages, exactly as Apple sent them —
        no metric parsing, money amounts left as their original JSON strings.
        """
        if not self.org_id:
            self._get_org_id()

        url = f"{self.BASE_URL}/reports/apps/adgroups/query"
        return self._fetch_report_rows(
            url,
            start_date,
            end_date,
            granularity,
            time_zone,
            filters=[self._equals_filter("campaignId", campaign_id)],
        )

    def get_adgroup_report(
        self,
        campaign_id: str,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        granularity: str = "DAILY",
        time_zone: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Get ad group performance report for a specific campaign.

        Args:
            campaign_id: The campaign ID to get ad group reports for
            start_date: Start date for the report (datetime or YYYY-MM-DD string)
            end_date: End date for the report (datetime or YYYY-MM-DD string)
            granularity: DAILY, WEEKLY, or MONTHLY
            time_zone: Optional timezone (e.g., "ORTZ" for org timezone, "UTC")

        Returns:
            DataFrame with ad group performance metrics.
        """
        rows = self.get_adgroup_report_raw(
            campaign_id, start_date, end_date, granularity, time_zone
        )
        return self._report_rows_to_df(
            rows,
            lambda row, metadata: self._parse_adgroup_row(row, metadata, campaign_id),
            self._single_day(start_date, end_date),
        )

    def _parse_keyword_row(
        self, row: Dict[str, Any], metadata: Dict[str, Any], campaign_id: str
    ) -> Dict[str, Any]:
        """Parse a single keyword row into a flat dict."""
        bid_amount = metadata.get("bid") or {}
        status = metadata.get("status")
        base = {
            "campaign_id": campaign_id,
            "adgroup_id": metadata.get("adGroupId"),
            "keyword_id": metadata.get("id"),
            "keyword": metadata.get("text"),
            "keyword_status": (
                self._KEYWORD_STATUS_TO_V5.get(status, status) if status is not None else None
            ),
            "match_type": metadata.get("matchType"),
            "bid_amount": float(bid_amount.get("amount", 0)) if bid_amount else 0,
        }
        base.update(self._parse_metrics(row))
        return base

    def get_keyword_report_raw(
        self,
        campaign_id: str,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        granularity: str = "DAILY",
        time_zone: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get keyword performance report as raw API rows.

        Returns every row across all pages, exactly as Apple sent them —
        no metric parsing, money amounts left as their original JSON strings.
        """
        if not self.org_id:
            self._get_org_id()

        url = f"{self.BASE_URL}/reports/apps/keywords/query"
        return self._fetch_report_rows(
            url,
            start_date,
            end_date,
            granularity,
            time_zone,
            filters=[self._equals_filter("campaignId", campaign_id)],
        )

    def get_keyword_report(
        self,
        campaign_id: str,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        granularity: str = "DAILY",
        time_zone: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Get keyword performance report for a specific campaign.

        Args:
            campaign_id: The campaign ID to get keyword reports for
            start_date: Start date for the report (datetime or YYYY-MM-DD string)
            end_date: End date for the report (datetime or YYYY-MM-DD string)
            granularity: DAILY, WEEKLY, or MONTHLY
            time_zone: Optional timezone (e.g., "ORTZ" for org timezone, "UTC")

        Returns:
            DataFrame with keyword performance metrics.
        """
        rows = self.get_keyword_report_raw(
            campaign_id, start_date, end_date, granularity, time_zone
        )
        return self._report_rows_to_df(
            rows,
            lambda row, metadata: self._parse_keyword_row(row, metadata, campaign_id),
            self._single_day(start_date, end_date),
        )

    def _parse_search_term_row(
        self,
        row: Dict[str, Any],
        metadata: Dict[str, Any],
        campaign_id: str,
    ) -> Dict[str, Any]:
        """Parse a single search term row into a flat dict."""
        # v1 dropped v5's `other` flag; a null searchTermText marks the same
        # aggregated low-volume rows (14/14 matched on a live campaign).
        search_term = metadata.get("searchTermText")
        is_low_volume = search_term is None
        if is_low_volume:
            search_term = "(Low volume terms)"

        keyword = metadata.get("keyword") or {}
        base = {
            "campaign_id": campaign_id,
            "adgroup_id": metadata.get("adGroupId"),
            "keyword_id": keyword.get("id"),
            "keyword": keyword.get("text"),
            "search_term": search_term,
            "search_term_source": metadata.get("searchTermSource"),
            "match_type": keyword.get("matchType"),
            "country_or_region": metadata.get("countryOrRegion"),
            "is_low_volume": is_low_volume,
        }
        base.update(self._parse_metrics(row))
        return base

    def _search_term_filters(
        self, campaign_id: str, adgroup_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        filters = [self._equals_filter("campaignId", campaign_id)]
        if adgroup_id is not None:
            filters.append(self._equals_filter("adGroupId", adgroup_id))
        return filters

    def get_search_term_report_raw(
        self,
        campaign_id: str,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        group_by: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get search term performance report as raw API rows.

        Returns every row across all pages, exactly as Apple sent them —
        no metric parsing, money amounts left as their original JSON strings.
        Uses ORTZ (Organization Reference Time Zone) as required by the API.
        group_by: optional dimensions, e.g. ["countryOrRegion"] for one row per
        search term per country (as v5's groupBy did).
        """
        if not self.org_id:
            self._get_org_id()

        url = f"{self.BASE_URL}/reports/apps/searchterms/query"
        return self._fetch_report_rows(
            url,
            start_date,
            end_date,
            time_zone="ORTZ",
            filters=self._search_term_filters(campaign_id),
            group_by=group_by,
        )

    def get_search_term_report(
        self,
        campaign_id: str,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        group_by: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        Get search term performance report for a specific campaign.

        Args:
            campaign_id: The campaign ID to get search term reports for
            start_date: Start date for the report (datetime or YYYY-MM-DD string)
            end_date: End date for the report (datetime or YYYY-MM-DD string)
            group_by: Optional dimensions, e.g. ["countryOrRegion"] to split each
                search term by country (filling country_or_region). Matched v5's
                groupBy row for row on a live multi-country campaign (132/132).

        Returns:
            DataFrame with search term performance metrics including:
            - search_term: The actual search term used
            - search_term_source: AUTO or TARGETED
            - keyword: The matched keyword (if targeted)
            - match_type: BROAD, EXACT, or SEARCH_MATCH
            - Standard metrics (impressions, taps, installs, spend, etc.)

        Note:
            Search term reports require a minimum of 10 impressions to appear.
            Uses ORTZ (Organization Reference Time Zone) as required by the API.
            Search term reports do not support granularity grouping.
        """
        start_date = self._parse_date_param(start_date)
        end_date = self._parse_date_param(end_date)

        rows = self.get_search_term_report_raw(campaign_id, start_date, end_date, group_by)
        return self._report_rows_to_df(
            rows,
            lambda row, metadata: self._parse_search_term_row(row, metadata, campaign_id),
            fallback_date=start_date.strftime("%Y-%m-%d"),
        )

    def get_adgroup_search_term_report_raw(
        self,
        campaign_id: str,
        adgroup_id: str,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        group_by: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get ad group search term performance report as raw API rows.

        Returns every row across all pages, exactly as Apple sent them —
        no metric parsing, money amounts left as their original JSON strings.
        Uses ORTZ (Organization Reference Time Zone) as required by the API.
        group_by: optional dimensions, e.g. ["countryOrRegion"] for one row per
        search term per country (as v5's groupBy did).
        """
        if not self.org_id:
            self._get_org_id()

        url = f"{self.BASE_URL}/reports/apps/searchterms/query"
        return self._fetch_report_rows(
            url,
            start_date,
            end_date,
            time_zone="ORTZ",
            filters=self._search_term_filters(campaign_id, adgroup_id),
            group_by=group_by,
        )

    def get_adgroup_search_term_report(
        self,
        campaign_id: str,
        adgroup_id: str,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        group_by: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        Get search term performance report for a specific ad group.

        Use this endpoint for high volume search term reports within an ad group.

        Args:
            campaign_id: The campaign ID
            adgroup_id: The ad group ID to get search term reports for
            start_date: Start date for the report (datetime or YYYY-MM-DD string)
            end_date: End date for the report (datetime or YYYY-MM-DD string)
            group_by: Optional dimensions, e.g. ["countryOrRegion"] to split each
                search term by country (filling country_or_region). Matched v5's
                groupBy row for row on a live multi-country campaign (132/132).

        Returns:
            DataFrame with search term performance metrics including:
            - search_term: The actual search term used
            - search_term_source: AUTO or TARGETED
            - keyword: The matched keyword (if targeted)
            - match_type: BROAD, EXACT, or SEARCH_MATCH
            - Standard metrics (impressions, taps, installs, spend, etc.)

        Note:
            Search term reports require a minimum of 10 impressions to appear.
            Uses ORTZ (Organization Reference Time Zone) as required by the API.
            Search term reports do not support granularity grouping.
        """
        start_date = self._parse_date_param(start_date)
        end_date = self._parse_date_param(end_date)

        rows = self.get_adgroup_search_term_report_raw(
            campaign_id, adgroup_id, start_date, end_date, group_by
        )
        return self._report_rows_to_df(
            rows,
            lambda row, metadata: self._parse_search_term_row(row, metadata, campaign_id),
            fallback_date=start_date.strftime("%Y-%m-%d"),
        )

    def get_daily_spend(self, days: int = 30, fetch_all_orgs: bool = True) -> pd.DataFrame:
        """
        Get daily spend across all campaigns.

        Args:
            days: Number of days to fetch
            fetch_all_orgs: If True, fetches from all organizations

        Returns:
            DataFrame with daily spend metrics.
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        return self.get_daily_spend_with_dates(start_date, end_date, fetch_all_orgs)

    def get_daily_spend_with_dates(
        self,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        fetch_all_orgs: bool = True,
    ) -> pd.DataFrame:
        """
        Get daily spend across all campaigns for a specific date range.

        Args:
            start_date: Start date for the report
            end_date: End date for the report
            fetch_all_orgs: If True, fetches from all organizations

        Returns:
            DataFrame with daily spend metrics.
        """
        all_campaign_data = self._fetch_campaign_reports_from_orgs(
            start_date, end_date, fetch_all_orgs
        )

        if not all_campaign_data:
            return pd.DataFrame()

        # Combine all campaign data
        campaign_df = pd.concat(all_campaign_data, ignore_index=True)

        # Group by date
        daily_df = (
            campaign_df.groupby("date")
            .agg({"spend": "sum", "impressions": "sum", "taps": "sum", "installs": "sum"})
            .reset_index()
        )

        # Calculate average metrics
        daily_df["avg_cpi"] = daily_df.apply(
            lambda row: row["spend"] / row["installs"] if row["installs"] > 0 else 0, axis=1
        )

        daily_df["avg_cpt"] = daily_df.apply(
            lambda row: row["spend"] / row["taps"] if row["taps"] > 0 else 0, axis=1
        )

        daily_df["conversion_rate"] = daily_df.apply(
            lambda row: row["installs"] / row["taps"] * 100 if row["taps"] > 0 else 0, axis=1
        )

        return daily_df

    def get_campaigns_with_details(self, fetch_all_orgs: bool = True) -> List[Dict[str, Any]]:
        """
        Get all campaigns with their app details including adamId.

        Args:
            fetch_all_orgs: If True, fetches from all organizations

        Returns:
            List of campaign dictionaries with app details.
        """
        if fetch_all_orgs:
            campaigns = self.get_all_campaigns()
        else:
            if not self.org_id:
                self._get_org_id()
            campaigns = self.get_campaigns()

        return campaigns

    def _fetch_campaign_reports_from_orgs(
        self,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        fetch_all_orgs: bool,
        add_org_info: bool = False,
    ) -> List[pd.DataFrame]:
        """Fetch campaign reports from one or all organizations."""
        all_campaign_data: List[pd.DataFrame] = []

        if fetch_all_orgs:
            for org in self.get_all_organizations():
                org_id = str(org["orgId"])
                current_org_id = self.org_id
                self.org_id = org_id
                try:
                    df = self.get_campaign_report(start_date, end_date)
                    if not df.empty:
                        if add_org_info:
                            df["org_id"] = org_id
                            df["org_name"] = org.get("orgName", "Unknown")
                        all_campaign_data.append(df)
                except Exception:
                    pass
                finally:
                    self.org_id = current_org_id
        else:
            df = self.get_campaign_report(start_date, end_date)
            if not df.empty:
                all_campaign_data.append(df)

        return all_campaign_data

    def _add_derived_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add derived metrics (cpi, ctr, cvr) to a DataFrame.

        Derived ratios are floats even in strict mode (spend may be Decimal);
        exact money stays in the source `spend` column.
        """
        df["cpi"] = df.apply(
            lambda x: float(x["spend"]) / x["installs"] if x["installs"] > 0 else 0.0, axis=1
        ).round(2)
        df["ctr"] = df.apply(
            lambda x: (x["taps"] / x["impressions"] * 100) if x["impressions"] > 0 else 0.0, axis=1
        ).round(2)
        df["cvr"] = df.apply(
            lambda x: (x["installs"] / x["taps"] * 100) if x["taps"] > 0 else 0.0, axis=1
        ).round(2)
        return df

    def _filter_by_date_range(
        self, df: pd.DataFrame, start_date: datetime, end_date: datetime
    ) -> pd.DataFrame:
        """Filter DataFrame to only include rows within the date range."""
        df["date_dt"] = pd.to_datetime(df["date"])
        start_date_only = start_date.date() if hasattr(start_date, "date") else start_date
        end_date_only = end_date.date() if hasattr(end_date, "date") else end_date
        filtered = df[
            (df["date_dt"].dt.date >= start_date_only) & (df["date_dt"].dt.date <= end_date_only)
        ].copy()
        filtered.drop("date_dt", axis=1, inplace=True)
        return filtered

    def get_daily_spend_by_app(
        self,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        fetch_all_orgs: bool = True,
    ) -> pd.DataFrame:
        """
        Get daily advertising spend grouped by app (adamId).

        Args:
            start_date: Start date for the report
            end_date: End date for the report
            fetch_all_orgs: If True, fetches from all organizations

        Returns:
            DataFrame with columns:
            - date: The date
            - app_id: Apple App Store ID (adamId)
            - spend: Total spend in USD
            - impressions: Total impressions
            - taps: Total taps on ads
            - installs: Total conversions/installs
            - campaigns: Number of active campaigns
        """
        all_data = self._fetch_campaign_reports_from_orgs(
            start_date, end_date, fetch_all_orgs, add_org_info=True
        )

        if not all_data:
            return pd.DataFrame()

        campaign_df = pd.concat(all_data, ignore_index=True)
        campaign_df["campaign_id"] = campaign_df["campaign_id"].astype(str)
        # v1 report rows carry the promoted app directly, so no campaign lookup
        # is needed to attribute spend (3.x needed get_campaigns_with_details).
        # int() first: one row without an app turns the column float64, and
        # str(1134998522.0) would break joins on app_id.
        campaign_df["app_id"] = campaign_df["adam_id"].map(
            lambda adam_id: None if adam_id is None or pd.isna(adam_id) else str(int(adam_id))
        )

        app_df = campaign_df[campaign_df["app_id"].notna()].copy()
        if app_df.empty:
            return pd.DataFrame()

        aggregated = (
            app_df.groupby(["date", "app_id"])
            .agg(
                {
                    "spend": "sum",
                    "impressions": "sum",
                    "taps": "sum",
                    "installs": "sum",
                    "campaign_id": "nunique",
                }
            )
            .reset_index()
        )

        aggregated.rename(columns={"campaign_id": "campaigns"}, inplace=True)
        aggregated = self._add_derived_metrics(aggregated)
        aggregated.sort_values(["date", "app_id"], inplace=True)

        start_dt = self._parse_date_param(start_date)
        end_dt = self._parse_date_param(end_date)
        return self._filter_by_date_range(aggregated, start_dt, end_dt)

    _IMPRESSION_SHARE_REMOVED = (
        "Apple Ads Platform API v1 has no asynchronous custom reports; "
        "use get_impression_share_data(), which queries impression share directly."
    )

    def create_impression_share_report(
        self,
        name: str,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        granularity: str = "DAILY",
        countries: Optional[List[str]] = None,
        adam_ids: Optional[List[str]] = None,
        time_zone: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Removed in 4.0: v1 replaced v5's queued custom reports with a synchronous query.

        Raises:
            NotImplementedError: Always. Use get_impression_share_data().
        """
        raise NotImplementedError(self._IMPRESSION_SHARE_REMOVED)

    def get_impression_share_report(self, report_id: Union[int, str]) -> Dict[str, Any]:
        """
        Removed in 4.0: v1 replaced v5's queued custom reports with a synchronous query.

        Raises:
            NotImplementedError: Always. Use get_impression_share_data().
        """
        raise NotImplementedError(self._IMPRESSION_SHARE_REMOVED)

    _IMPRESSION_SHARE_GRANULARITY = {"DAILY": "DAILY", "WEEKLY": "WEEKLY_SUN_SAT"}

    def get_impression_share_data(
        self,
        name: str,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        granularity: str = "DAILY",
        countries: Optional[List[str]] = None,
        adam_ids: Optional[List[str]] = None,
        time_zone: Optional[str] = None,
        poll_interval: int = 5,
        max_wait: int = 300,
    ) -> pd.DataFrame:
        """
        Get impression share data as a DataFrame.

        v1 answers synchronously, so name, poll_interval and max_wait are
        accepted for compatibility and ignored.

        Args:
            name: Ignored (v5 report name)
            start_date: Start date for the report (datetime or YYYY-MM-DD string)
            end_date: End date for the report (datetime or YYYY-MM-DD string)
            granularity: DAILY or WEEKLY (v1's Sunday-Saturday weeks)
            countries: Optional list of country codes to filter (e.g., ["US", "AU"])
            adam_ids: Optional list of app Adam IDs to filter. v1 requires at least
                one, so when omitted every app promoted by the current
                organization's campaigns is used.
            time_zone: Must be None or "UTC"; v1 fixes impression share to UTC.
            poll_interval: Ignored
            max_wait: Ignored

        Returns:
            DataFrame with impression share metrics including:
            - appName, adamId, countryOrRegion, searchTerm, date (dimensions)
            - lowImpressionShare, highImpressionShare, rank, searchPopularity (metrics)
        """
        if not self.org_id:
            self._get_org_id()

        if time_zone not in (None, "UTC"):
            raise ValueError(
                f"Impression share is UTC-only in Apple Ads Platform API v1: {time_zone}"
            )
        if granularity not in self._IMPRESSION_SHARE_GRANULARITY:
            raise ValueError(f"granularity must be DAILY or WEEKLY, got: {granularity}")
        if granularity == "WEEKLY" and self._parse_date_param(start_date).weekday() != 6:
            raise ValueError(
                "WEEKLY impression share uses Sunday-Saturday weeks; start on a Sunday"
            )

        if not adam_ids:
            adam_ids = sorted(
                {str(c["adamId"]) for c in self.get_campaigns() if c.get("adamId") is not None}
            )
            if not adam_ids:
                return pd.DataFrame()

        start_dt = self._parse_date_param(start_date)
        end_dt = self._parse_date_param(end_date)
        filters: List[Dict[str, Any]] = [
            {"field": "promotedObjectId", "operator": "IN", "value": [str(a) for a in adam_ids]}
        ]
        if countries:
            filters.append({"field": "countryOrRegion", "operator": "IN", "value": countries})

        def build(offset: int, page_size: int) -> Dict[str, Any]:
            return {
                "filters": filters,
                "timeRange": {
                    "start": start_dt.strftime("%Y-%m-%d"),
                    "end": end_dt.strftime("%Y-%m-%d"),
                    "granularity": self._IMPRESSION_SHARE_GRANULARITY[granularity],
                },
                "pagination": {"offset": offset, "pageSize": page_size},
            }

        rows = self._fetch_paged(f"{self.BASE_URL}/insights/apps/impression-share/query", build)
        for row in rows:
            self._add_missing(
                row,
                {
                    "adamId": self._to_int(row.get("promotedObjectId")),
                    "searchPopularity": row.get("searchPopularity1to5"),
                    "date": row.get("day", row.get("week")),
                },
            )
        return pd.DataFrame(rows)
