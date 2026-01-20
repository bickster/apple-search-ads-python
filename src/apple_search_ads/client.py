"""
Apple Search Ads API Client for Python

A Python client for interacting with Apple Search Ads API v5.
"""

import jwt
import time
import os
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Any
import pandas as pd
from ratelimit import limits, sleep_and_retry


class AppleSearchAdsClient:
    """
    Client for Apple Search Ads API v5.

    This client provides methods to interact with Apple Search Ads API,
    including campaign management, reporting, and spend tracking.

    Args:
        client_id: Apple Search Ads client ID
        team_id: Apple Search Ads team ID
        key_id: Apple Search Ads key ID
        private_key_path: Path to the private key .p8 file
        private_key_content: Private key content as string (alternative to file path)
        org_id: Optional organization ID (will be fetched automatically if not provided)

    Example:
        >>> client = AppleSearchAdsClient(
        ...     client_id="your_client_id",
        ...     team_id="your_team_id",
        ...     key_id="your_key_id",
        ...     private_key_path="/path/to/private_key.p8"
        ... )
        >>> campaigns = client.get_campaigns()
    """

    BASE_URL = "https://api.searchads.apple.com/api/v5"

    def __init__(
        self,
        client_id: Optional[str] = None,
        team_id: Optional[str] = None,
        key_id: Optional[str] = None,
        private_key_path: Optional[str] = None,
        private_key_content: Optional[str] = None,
        org_id: Optional[str] = None,
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
        """Get access token using client credentials flow."""
        if self._token and self._token_expiry and time.time() < self._token_expiry:
            return self._token

        token_url = "https://appleid.apple.com/auth/oauth2/token"

        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self._generate_client_secret(),
            "scope": "searchadsorg",
        }

        response = requests.post(token_url, data=data)
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

        # Add organization context if we have it (not needed for ACLs endpoint)
        if include_org_context and self.org_id:
            headers["X-AP-Context"] = f"orgId={self.org_id}"

        return headers

    def _get_org_id(self) -> str:
        """Get the organization ID."""
        if self.org_id:
            return self.org_id

        response = self._make_request(f"{self.BASE_URL}/acls", include_org_context=False)

        if response and "data" in response and len(response["data"]) > 0:
            self.org_id = str(response["data"][0]["orgId"])
            return self.org_id

        raise ValueError("No organization found for this account")

    @sleep_and_retry
    @limits(calls=10, period=1)  # Apple Search Ads rate limit
    def _make_request(
        self,
        url: str,
        method: str = "GET",
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        include_org_context: bool = True,
    ) -> Dict[str, Any]:
        """Make a rate-limited request to the API."""
        response = requests.request(
            method=method,
            url=url,
            headers=self._get_headers(include_org_context=include_org_context),
            json=json_data,
            params=params,
        )
        response.raise_for_status()
        return response.json()

    def _parse_date_param(self, date: Union[datetime, str]) -> datetime:
        """Convert string date to datetime if needed."""
        if isinstance(date, str):
            return datetime.strptime(date, "%Y-%m-%d")
        return date

    def _build_report_request(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: Optional[str] = None,
        time_zone: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build standard report request data."""
        request: Dict[str, Any] = {
            "startTime": start_date.strftime("%Y-%m-%d"),
            "endTime": end_date.strftime("%Y-%m-%d"),
            "selector": {
                "orderBy": [{"field": "localSpend", "sortOrder": "DESCENDING"}],
                "pagination": {"limit": 1000},
            },
            "returnRowTotals": True,
            "returnRecordsWithNoMetrics": False,
        }
        if granularity:
            request["granularity"] = granularity
        if time_zone:
            request["timeZone"] = time_zone
        return request

    def _extract_rows_from_response(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract rows from different API response formats."""
        if not response or "data" not in response:
            return []
        data = response["data"]
        if "reportingDataResponse" in data and "row" in data["reportingDataResponse"]:
            return data["reportingDataResponse"]["row"]
        if "rows" in data:
            return data["rows"]
        return []

    def _parse_metrics(self, day_data: Dict[str, Any], is_legacy: bool = False) -> Dict[str, Any]:
        """Parse common metrics from row data."""
        if is_legacy:
            return {
                "impressions": day_data.get("impressions", 0),
                "taps": day_data.get("taps", 0),
                "installs": day_data.get("installs", 0),
                "new_downloads": day_data.get("newDownloads", 0),
                "redownloads": day_data.get("redownloads", 0),
                "lat_on_installs": day_data.get("latOnInstalls", 0),
                "lat_off_installs": day_data.get("latOffInstalls", 0),
                "tap_installs": day_data.get("tapInstalls", 0),
                "view_installs": day_data.get("viewInstalls", 0),
                "tap_new_downloads": day_data.get("tapNewDownloads", 0),
                "tap_redownloads": day_data.get("tapRedownloads", 0),
                "view_new_downloads": day_data.get("viewNewDownloads", 0),
                "view_redownloads": day_data.get("viewRedownloads", 0),
                "spend": float((day_data.get("localSpend") or {}).get("amount", 0)),
                "currency": (day_data.get("localSpend") or {}).get("currency", "USD"),
                "avg_cpa": float((day_data.get("avgCPA") or {}).get("amount", 0)),
                "avg_cpt": float((day_data.get("avgCPT") or {}).get("amount", 0)),
                "avg_cpm": float((day_data.get("avgCPM") or {}).get("amount", 0)),
                "ttr": day_data.get("ttr", 0),
                "conversion_rate": day_data.get("conversionRate", 0),
                "tap_install_rate": day_data.get("tapInstallRate", 0),
            }
        return {
            "impressions": day_data.get("impressions", 0),
            "taps": day_data.get("taps", 0),
            "installs": day_data.get("totalInstalls", 0),
            "new_downloads": day_data.get("totalNewDownloads", 0),
            "redownloads": day_data.get("totalRedownloads", 0),
            "lat_on_installs": day_data.get("latOnInstalls", 0),
            "lat_off_installs": day_data.get("latOffInstalls", 0),
            "tap_installs": day_data.get("tapInstalls", 0),
            "view_installs": day_data.get("viewInstalls", 0),
            "tap_new_downloads": day_data.get("tapNewDownloads", 0),
            "tap_redownloads": day_data.get("tapRedownloads", 0),
            "view_new_downloads": day_data.get("viewNewDownloads", 0),
            "view_redownloads": day_data.get("viewRedownloads", 0),
            "spend": float((day_data.get("localSpend") or {}).get("amount", 0)),
            "currency": (day_data.get("localSpend") or {}).get("currency", "USD"),
            "avg_cpa": float((day_data.get("totalAvgCPI") or {}).get("amount", 0)),
            "avg_cpt": float((day_data.get("avgCPT") or {}).get("amount", 0)),
            "avg_cpm": float((day_data.get("avgCPM") or {}).get("amount", 0)),
            "ttr": day_data.get("ttr", 0),
            "conversion_rate": day_data.get("totalInstallRate", 0),
            "tap_install_rate": day_data.get("tapInstallRate", 0),
        }

    def get_all_organizations(self) -> List[Dict[str, Any]]:
        """
        Get all organizations the user has access to.

        Returns:
            List of organization dictionaries containing orgId, orgName, etc.
        """
        response = self._make_request(f"{self.BASE_URL}/acls", include_org_context=False)

        if response and "data" in response:
            return response["data"]

        return []

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
            - isPreOrder: Whether app is in pre-order
            - availableStorefronts: List of country codes where app is available
        """
        if not self.org_id:
            self._get_org_id()

        url = f"{self.BASE_URL}/apps/{adam_id}"
        response = self._make_request(url, method="GET")

        if response and "data" in response:
            return response["data"]

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

        url = f"{self.BASE_URL}/campaigns/{campaign_id}/adgroups"

        params = {"limit": 1000}

        response = self._make_request(url, params=params)
        return response.get("data", [])

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

        url = f"{self.BASE_URL}/campaigns/{campaign_id}/adgroups/targetingkeywords/find"

        # Build conditions
        conditions = []
        if not include_deleted:
            conditions.append({"field": "deleted", "operator": "EQUALS", "values": ["false"]})
        if adgroup_id is not None:
            conditions.append(
                {"field": "adGroupId", "operator": "EQUALS", "values": [str(adgroup_id)]}
            )

        request_data: Dict[str, Any] = {
            "pagination": {"offset": 0, "limit": 1000},
            "orderBy": [{"field": "id", "sortOrder": "ASCENDING"}],
        }
        if conditions:
            request_data["conditions"] = conditions

        response = self._make_request(url, method="POST", json_data=request_data)
        return response.get("data", [])

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
            campaign_id: The campaign ID containing the keyword
            adgroup_id: The ad group ID containing the keyword
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

        url = (
            f"{self.BASE_URL}/campaigns/{campaign_id}/adgroups/{adgroup_id}"
            f"/targetingkeywords/bulk"
        )

        request_data = [
            {"id": str(keyword_id), "bidAmount": {"amount": str(bid_value), "currency": currency}}
        ]

        response = self._make_request(url, method="PUT", json_data=request_data)

        if response and "data" in response:
            data = response["data"]
            # Bulk endpoint returns a list, extract the first item
            if isinstance(data, list) and len(data) > 0:
                return data[0]
            return data

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

        url = f"{self.BASE_URL}/campaigns"

        params = {"limit": 1000}

        try:
            response = self._make_request(url, params=params)
            campaigns = response.get("data", [])

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
            List of all campaigns across all organizations.
        """
        all_campaigns = []
        organizations = self.get_all_organizations()

        for org in organizations:
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

    def _parse_campaign_row(
        self, row: Dict[str, Any], metadata: Dict[str, Any], is_legacy: bool
    ) -> Dict[str, Any]:
        """Parse a single campaign row into a flat dict."""
        app_name = metadata.get("appName")
        if not is_legacy and "app" in metadata:
            app_name = (metadata.get("app") or {}).get("appName")
        base = {
            "campaign_id": metadata.get("campaignId"),
            "campaign_name": metadata.get("campaignName"),
            "campaign_status": metadata.get("campaignStatus"),
            "app_name": app_name,
            "adam_id": metadata.get("adamId"),
        }
        base.update(self._parse_metrics(row, is_legacy))
        return base

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
        if not self.org_id:
            self._get_org_id()

        start_date = self._parse_date_param(start_date)
        end_date = self._parse_date_param(end_date)

        url = f"{self.BASE_URL}/reports/campaigns"
        request_data = self._build_report_request(start_date, end_date, granularity, time_zone)
        response = self._make_request(url, method="POST", json_data=request_data)
        rows = self._extract_rows_from_response(response)

        if not rows:
            return pd.DataFrame()

        data = []
        for row in rows:
            metadata = row.get("metadata", {})
            if "granularity" in row:
                for day_data in row["granularity"]:
                    entry = {"date": day_data.get("date")}
                    entry.update(self._parse_campaign_row(day_data, metadata, is_legacy=False))
                    data.append(entry)
            else:
                metrics = row.get("metrics", {})
                entry = {"date": metadata.get("date")}
                entry.update(self._parse_campaign_row(metrics, metadata, is_legacy=True))
                data.append(entry)

        return pd.DataFrame(data)

    def _parse_adgroup_row(
        self, row: Dict[str, Any], metadata: Dict[str, Any], campaign_id: str, is_legacy: bool
    ) -> Dict[str, Any]:
        """Parse a single ad group row into a flat dict."""
        base = {
            "campaign_id": campaign_id,
            "adgroup_id": metadata.get("adGroupId"),
            "adgroup_name": metadata.get("adGroupName"),
            "adgroup_status": metadata.get("adGroupStatus"),
        }
        base.update(self._parse_metrics(row, is_legacy))
        return base

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
        if not self.org_id:
            self._get_org_id()

        start_date = self._parse_date_param(start_date)
        end_date = self._parse_date_param(end_date)

        url = f"{self.BASE_URL}/reports/campaigns/{campaign_id}/adgroups"
        request_data = self._build_report_request(start_date, end_date, granularity, time_zone)
        response = self._make_request(url, method="POST", json_data=request_data)
        rows = self._extract_rows_from_response(response)

        if not rows:
            return pd.DataFrame()

        data = []
        for row in rows:
            metadata = row.get("metadata", {})
            if "granularity" in row:
                for day_data in row["granularity"]:
                    entry = {"date": day_data.get("date")}
                    entry.update(self._parse_adgroup_row(day_data, metadata, campaign_id, False))
                    data.append(entry)
            else:
                metrics = row.get("metrics", {})
                entry = {"date": metadata.get("date")}
                entry.update(self._parse_adgroup_row(metrics, metadata, campaign_id, True))
                data.append(entry)

        return pd.DataFrame(data)

    def _parse_keyword_row(
        self, row: Dict[str, Any], metadata: Dict[str, Any], campaign_id: str, is_legacy: bool
    ) -> Dict[str, Any]:
        """Parse a single keyword row into a flat dict."""
        bid_amount = metadata.get("bidAmount") or {}
        base = {
            "campaign_id": campaign_id,
            "adgroup_id": metadata.get("adGroupId"),
            "keyword_id": metadata.get("keywordId"),
            "keyword": metadata.get("keyword"),
            "keyword_status": metadata.get("keywordStatus"),
            "match_type": metadata.get("matchType"),
            "bid_amount": float(bid_amount.get("amount", 0)) if bid_amount else 0,
        }
        base.update(self._parse_metrics(row, is_legacy))
        return base

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
        if not self.org_id:
            self._get_org_id()

        start_date = self._parse_date_param(start_date)
        end_date = self._parse_date_param(end_date)

        url = f"{self.BASE_URL}/reports/campaigns/{campaign_id}/keywords"
        request_data = self._build_report_request(start_date, end_date, granularity, time_zone)
        response = self._make_request(url, method="POST", json_data=request_data)
        rows = self._extract_rows_from_response(response)

        if not rows:
            return pd.DataFrame()

        data = []
        for row in rows:
            metadata = row.get("metadata", {})
            if "granularity" in row:
                for day_data in row["granularity"]:
                    entry = {"date": day_data.get("date")}
                    entry.update(self._parse_keyword_row(day_data, metadata, campaign_id, False))
                    data.append(entry)
            else:
                metrics = row.get("metrics", {})
                entry = {"date": metadata.get("date")}
                entry.update(self._parse_keyword_row(metrics, metadata, campaign_id, True))
                data.append(entry)

        return pd.DataFrame(data)

    def _parse_search_term_row(
        self,
        row: Dict[str, Any],
        metadata: Dict[str, Any],
        campaign_id: str,
        is_legacy: bool,
        is_low_volume: bool = False,
    ) -> Dict[str, Any]:
        """Parse a single search term row into a flat dict."""
        # Get search term, mapping null to "(Low volume terms)" for aggregated data
        search_term = metadata.get("searchTermText")
        if search_term is None and is_low_volume:
            search_term = "(Low volume terms)"

        base = {
            "campaign_id": campaign_id,
            "adgroup_id": metadata.get("adGroupId"),
            "keyword_id": metadata.get("keywordId"),
            "keyword": metadata.get("keyword"),
            "search_term": search_term,
            "search_term_source": metadata.get("searchTermSource"),
            "match_type": metadata.get("matchType"),
            "country_or_region": metadata.get("countryOrRegion"),
            "is_low_volume": is_low_volume,
        }
        base.update(self._parse_metrics(row, is_legacy))
        return base

    def get_search_term_report(
        self,
        campaign_id: str,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
    ) -> pd.DataFrame:
        """
        Get search term performance report for a specific campaign.

        Args:
            campaign_id: The campaign ID to get search term reports for
            start_date: Start date for the report (datetime or YYYY-MM-DD string)
            end_date: End date for the report (datetime or YYYY-MM-DD string)

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
        if not self.org_id:
            self._get_org_id()

        start_date = self._parse_date_param(start_date)
        end_date = self._parse_date_param(end_date)

        url = f"{self.BASE_URL}/reports/campaigns/{campaign_id}/searchterms"
        request_data = self._build_report_request(start_date, end_date, time_zone="ORTZ")
        response = self._make_request(url, method="POST", json_data=request_data)
        rows = self._extract_rows_from_response(response)

        if not rows:
            return pd.DataFrame()

        data = []
        for row in rows:
            metadata = row.get("metadata", {})
            is_low_volume = row.get("other", False)
            if "granularity" in row:
                for day_data in row["granularity"]:
                    entry = {"date": day_data.get("date")}
                    entry.update(
                        self._parse_search_term_row(
                            day_data, metadata, campaign_id, False, is_low_volume
                        )
                    )
                    data.append(entry)
            else:
                # Search term reports return 'total' instead of 'metrics'
                # Get date from total if available, otherwise use start_date
                metrics = row.get("total", row.get("metrics", {}))
                report_date = metrics.get("date", start_date.strftime("%Y-%m-%d"))
                entry = {"date": report_date}
                entry.update(
                    self._parse_search_term_row(
                        metrics, metadata, campaign_id, False, is_low_volume
                    )
                )
                data.append(entry)

        return pd.DataFrame(data)

    def get_adgroup_search_term_report(
        self,
        campaign_id: str,
        adgroup_id: str,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
    ) -> pd.DataFrame:
        """
        Get search term performance report for a specific ad group.

        Use this endpoint for high volume search term reports within an ad group.

        Args:
            campaign_id: The campaign ID
            adgroup_id: The ad group ID to get search term reports for
            start_date: Start date for the report (datetime or YYYY-MM-DD string)
            end_date: End date for the report (datetime or YYYY-MM-DD string)

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
        if not self.org_id:
            self._get_org_id()

        start_date = self._parse_date_param(start_date)
        end_date = self._parse_date_param(end_date)

        url = (
            f"{self.BASE_URL}/reports/campaigns/{campaign_id}" f"/adgroups/{adgroup_id}/searchterms"
        )
        request_data = self._build_report_request(start_date, end_date, time_zone="ORTZ")
        response = self._make_request(url, method="POST", json_data=request_data)
        rows = self._extract_rows_from_response(response)

        if not rows:
            return pd.DataFrame()

        data = []
        for row in rows:
            metadata = row.get("metadata", {})
            is_low_volume = row.get("other", False)
            if "granularity" in row:
                for day_data in row["granularity"]:
                    entry = {"date": day_data.get("date")}
                    entry.update(
                        self._parse_search_term_row(
                            day_data, metadata, campaign_id, False, is_low_volume
                        )
                    )
                    data.append(entry)
            else:
                # Search term reports return 'total' instead of 'metrics'
                # Get date from total if available, otherwise use start_date
                metrics = row.get("total", row.get("metrics", {}))
                report_date = metrics.get("date", start_date.strftime("%Y-%m-%d"))
                entry = {"date": report_date}
                entry.update(
                    self._parse_search_term_row(
                        metrics, metadata, campaign_id, False, is_low_volume
                    )
                )
                data.append(entry)

        return pd.DataFrame(data)

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
        all_campaign_data = []

        if fetch_all_orgs:
            organizations = self.get_all_organizations()

            for org in organizations:
                org_id = str(org["orgId"])

                # Set org context
                current_org_id = self.org_id
                self.org_id = org_id

                try:
                    # Get campaign report for this org
                    org_campaign_df = self.get_campaign_report(start_date, end_date)
                    if not org_campaign_df.empty:
                        all_campaign_data.append(org_campaign_df)
                except Exception:
                    pass
                finally:
                    # Restore original org_id
                    self.org_id = current_org_id
        else:
            campaign_df = self.get_campaign_report(start_date, end_date)
            if not campaign_df.empty:
                all_campaign_data.append(campaign_df)

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
        """Add derived metrics (cpi, ctr, cvr) to a DataFrame."""
        df["cpi"] = df.apply(
            lambda x: x["spend"] / x["installs"] if x["installs"] > 0 else 0, axis=1
        ).round(2)
        df["ctr"] = df.apply(
            lambda x: (x["taps"] / x["impressions"] * 100) if x["impressions"] > 0 else 0, axis=1
        ).round(2)
        df["cvr"] = df.apply(
            lambda x: (x["installs"] / x["taps"] * 100) if x["taps"] > 0 else 0, axis=1
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
        campaigns = self.get_campaigns_with_details(fetch_all_orgs=fetch_all_orgs)
        campaign_to_app = {str(c["id"]): str(c.get("adamId")) for c in campaigns if c.get("adamId")}

        all_data = self._fetch_campaign_reports_from_orgs(
            start_date, end_date, fetch_all_orgs, add_org_info=True
        )
        if not all_data:
            return pd.DataFrame()

        campaign_df = pd.concat(all_data, ignore_index=True)
        campaign_df["campaign_id"] = campaign_df["campaign_id"].astype(str)
        campaign_df["app_id"] = campaign_df["campaign_id"].map(campaign_to_app)

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
        Create an impression share report request.

        This is an async operation - the report is queued and must be polled
        for completion using get_impression_share_report().

        Args:
            name: A unique name for the report
            start_date: Start date for the report (datetime or YYYY-MM-DD string)
            end_date: End date for the report (datetime or YYYY-MM-DD string)
            granularity: DAILY or WEEKLY
            countries: Optional list of country codes to filter (e.g., ["US", "AU"])
            adam_ids: Optional list of app Adam IDs to filter
            time_zone: Optional timezone (e.g., "ORTZ" for org timezone, "UTC")

        Returns:
            Dict with report info including 'id', 'state', 'downloadUri', etc.

        Note:
            - Max 10 reports per 24 hours
            - Max 30 day range
            - Reports available for dates after 2020-04-12
            - WEEKLY granularity requires dateRange, not custom dates
        """
        if not self.org_id:
            self._get_org_id()

        start_date = self._parse_date_param(start_date)
        end_date = self._parse_date_param(end_date)

        request_data: Dict[str, Any] = {
            "name": name,
            "startTime": start_date.strftime("%Y-%m-%d"),
            "endTime": end_date.strftime("%Y-%m-%d"),
            "granularity": granularity,
        }

        if time_zone:
            request_data["timeZone"] = time_zone

        # Build selector conditions
        conditions = []
        if countries:
            conditions.append(
                {
                    "field": "countryOrRegion",
                    "operator": "IN",
                    "values": countries,
                }
            )
        if adam_ids:
            conditions.append(
                {
                    "field": "adamId",
                    "operator": "IN",
                    "values": adam_ids,
                }
            )

        if conditions:
            request_data["selector"] = {"conditions": conditions}

        url = f"{self.BASE_URL}/custom-reports"
        response = self._make_request(url, method="POST", json_data=request_data)

        if response and "data" in response:
            return response["data"]

        return {}

    def get_impression_share_report(self, report_id: Union[int, str]) -> Dict[str, Any]:
        """
        Get the status and info of an impression share report.

        Args:
            report_id: The report ID returned from create_impression_share_report()

        Returns:
            Dict with report info including:
            - id: Report ID
            - name: Report name
            - state: QUEUED, PROCESSING, or COMPLETED
            - downloadUri: URL to download report (when COMPLETED)
            - dimensions: List of dimension fields
            - metrics: List of metric fields
        """
        if not self.org_id:
            self._get_org_id()

        url = f"{self.BASE_URL}/custom-reports/{report_id}"
        response = self._make_request(url, method="GET")

        if response and "data" in response:
            return response["data"]

        return {}

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

        This is a convenience method that:
        1. Creates an impression share report
        2. Polls until the report is COMPLETED
        3. Downloads and parses the report data

        Args:
            name: A unique name for the report
            start_date: Start date for the report (datetime or YYYY-MM-DD string)
            end_date: End date for the report (datetime or YYYY-MM-DD string)
            granularity: DAILY or WEEKLY
            countries: Optional list of country codes to filter (e.g., ["US", "AU"])
            adam_ids: Optional list of app Adam IDs to filter
            time_zone: Optional timezone (e.g., "ORTZ" for org timezone, "UTC")
            poll_interval: Seconds between status checks (default: 5)
            max_wait: Maximum seconds to wait for report (default: 300)

        Returns:
            DataFrame with impression share metrics including:
            - appName, adamId, countryOrRegion, searchTerm (dimensions)
            - lowImpressionShare, highImpressionShare, rank, searchPopularity (metrics)

        Raises:
            TimeoutError: If report doesn't complete within max_wait seconds
        """
        import time

        # Create the report
        report = self.create_impression_share_report(
            name=name,
            start_date=start_date,
            end_date=end_date,
            granularity=granularity,
            countries=countries,
            adam_ids=adam_ids,
            time_zone=time_zone,
        )

        if not report or "id" not in report:
            return pd.DataFrame()

        report_id = report["id"]
        elapsed = 0

        # Poll for completion
        while elapsed < max_wait:
            report_status = self.get_impression_share_report(report_id)
            state = report_status.get("state", "")

            if state == "COMPLETED":
                download_uri = report_status.get("downloadUri")
                if download_uri:
                    return self._download_impression_share_report(download_uri)
                return pd.DataFrame()

            if state not in ("QUEUED", "PROCESSING"):
                # Unknown or error state
                return pd.DataFrame()

            time.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(
            f"Impression share report {report_id} did not complete within {max_wait} seconds"
        )

    def _download_impression_share_report(self, download_uri: str) -> pd.DataFrame:
        """
        Download and parse an impression share report from the given URI.

        Args:
            download_uri: The downloadUri from a completed report

        Returns:
            DataFrame with the report data
        """
        import requests as req

        try:
            response = req.get(download_uri, timeout=60)
            response.raise_for_status()

            # The response is typically CSV or JSON - try to parse
            content_type = response.headers.get("Content-Type", "")

            if "json" in content_type:
                data = response.json()
                if isinstance(data, list):
                    return pd.DataFrame(data)
                elif isinstance(data, dict) and "data" in data:
                    return pd.DataFrame(data["data"])
                return pd.DataFrame([data])
            else:
                # Assume CSV
                from io import StringIO

                return pd.read_csv(StringIO(response.text))

        except Exception:
            return pd.DataFrame()
