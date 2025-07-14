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

    def get_campaigns(self, org_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all campaigns for a specific organization or the default one.

        Args:
            org_id: Optional organization ID. If not provided, uses the default org.

        Returns:
            List of campaign dictionaries.
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

            return campaigns
        finally:
            # Restore original org_id if we changed it
            if original_org_id is not None:
                self.org_id = original_org_id

    def get_all_campaigns(self) -> List[Dict[str, Any]]:
        """
        Get campaigns from all organizations.

        Returns:
            List of all campaigns across all organizations.
        """
        all_campaigns = []
        organizations = self.get_all_organizations()

        for org in organizations:
            org_id = str(org["orgId"])
            org_name = org.get("orgName", "Unknown")

            try:
                campaigns = self.get_campaigns(org_id=org_id)

                # Add organization info to each campaign
                for campaign in campaigns:
                    campaign["org_name"] = org_name
                    campaign["parent_org_id"] = org.get("parentOrgId")

                all_campaigns.extend(campaigns)
            except Exception as e:
                print(f"Error fetching campaigns from {org_name}: {e}")

        return all_campaigns

    def get_campaign_report(
        self,
        start_date: Union[datetime, str],
        end_date: Union[datetime, str],
        granularity: str = "DAILY",
    ) -> pd.DataFrame:
        """
        Get campaign performance report.

        Args:
            start_date: Start date for the report (datetime or YYYY-MM-DD string)
            end_date: End date for the report (datetime or YYYY-MM-DD string)
            granularity: DAILY, WEEKLY, or MONTHLY

        Returns:
            DataFrame with campaign performance metrics.
        """
        # Ensure we have org_id for the context header
        if not self.org_id:
            self._get_org_id()

        # Convert string dates to datetime if needed
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, "%Y-%m-%d")

        url = f"{self.BASE_URL}/reports/campaigns"

        # Apple Search Ads API uses date-only format
        request_data = {
            "startTime": start_date.strftime("%Y-%m-%d"),
            "endTime": end_date.strftime("%Y-%m-%d"),
            "granularity": granularity,
            "selector": {
                "orderBy": [{"field": "localSpend", "sortOrder": "DESCENDING"}],
                "pagination": {"limit": 1000},
            },
            "returnRowTotals": True,
            "returnRecordsWithNoMetrics": False,
        }

        response = self._make_request(url, method="POST", json_data=request_data)

        # Handle different response structures
        rows = []
        if response and "data" in response:
            if (
                "reportingDataResponse" in response["data"]
                and "row" in response["data"]["reportingDataResponse"]
            ):
                # New response structure
                rows = response["data"]["reportingDataResponse"]["row"]
            elif "rows" in response["data"]:
                # Old response structure
                rows = response["data"]["rows"]

        if rows:
            # Extract data into a flat structure
            data = []
            for row in rows:
                metadata = row.get("metadata", {})

                # For the new structure, we need to process granularity data
                if "granularity" in row:
                    # New structure: iterate through each day in granularity
                    for day_data in row["granularity"]:
                        data.append(
                            {
                                "date": day_data.get("date"),
                                "campaign_id": metadata.get("campaignId"),
                                "campaign_name": metadata.get("campaignName"),
                                "campaign_status": metadata.get("campaignStatus"),
                                "app_name": (
                                    metadata.get("app", {}).get("appName")
                                    if "app" in metadata
                                    else metadata.get("appName")
                                ),
                                "adam_id": metadata.get("adamId"),
                                "impressions": day_data.get("impressions", 0),
                                "taps": day_data.get("taps", 0),
                                "installs": day_data.get("totalInstalls", 0),
                                "spend": float(day_data.get("localSpend", {}).get("amount", 0)),
                                "currency": day_data.get("localSpend", {}).get("currency", "USD"),
                                "avg_cpa": float(day_data.get("totalAvgCPI", {}).get("amount", 0)),
                                "avg_cpt": float(day_data.get("avgCPT", {}).get("amount", 0)),
                                "ttr": day_data.get("ttr", 0),
                                "conversion_rate": day_data.get("totalInstallRate", 0),
                            }
                        )
                else:
                    # Old structure
                    metrics = row.get("metrics", {})

                    data.append(
                        {
                            "date": metadata.get("date"),
                            "campaign_id": metadata.get("campaignId"),
                            "campaign_name": metadata.get("campaignName"),
                            "campaign_status": metadata.get("campaignStatus"),
                            "app_name": metadata.get("appName"),
                            "adam_id": metadata.get("adamId"),
                            "impressions": metrics.get("impressions", 0),
                            "taps": metrics.get("taps", 0),
                            "installs": metrics.get("installs", 0),
                            "spend": float(metrics.get("localSpend", {}).get("amount", 0)),
                            "currency": metrics.get("localSpend", {}).get("currency", "USD"),
                            "avg_cpa": float(metrics.get("avgCPA", {}).get("amount", 0)),
                            "avg_cpt": float(metrics.get("avgCPT", {}).get("amount", 0)),
                            "ttr": metrics.get("ttr", 0),
                            "conversion_rate": metrics.get("conversionRate", 0),
                        }
                    )

            return pd.DataFrame(data)

        return pd.DataFrame()

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
        # First, get campaign-to-app mapping
        campaigns = self.get_campaigns_with_details(fetch_all_orgs=fetch_all_orgs)
        campaign_to_app = {str(c["id"]): str(c.get("adamId")) for c in campaigns if c.get("adamId")}

        # Get campaign reports from all organizations
        all_campaign_data = []

        if fetch_all_orgs:
            organizations = self.get_all_organizations()

            for org in organizations:
                org_id = str(org["orgId"])
                org_name = org.get("orgName", "Unknown")

                # Set org context
                current_org_id = self.org_id
                self.org_id = org_id

                try:
                    # Get campaign report for this org
                    org_campaign_df = self.get_campaign_report(start_date, end_date)
                    if not org_campaign_df.empty:
                        # Add org info to the dataframe
                        org_campaign_df["org_id"] = org_id
                        org_campaign_df["org_name"] = org_name
                        all_campaign_data.append(org_campaign_df)
                except Exception:
                    pass
                finally:
                    # Restore original org_id
                    self.org_id = current_org_id
        else:
            # Just get from default org
            campaign_df = self.get_campaign_report(start_date, end_date)
            if not campaign_df.empty:
                all_campaign_data.append(campaign_df)

        if not all_campaign_data:
            return pd.DataFrame()

        # Combine all campaign data
        campaign_df = pd.concat(all_campaign_data, ignore_index=True)

        # Convert campaign_id to string for mapping
        campaign_df["campaign_id"] = campaign_df["campaign_id"].astype(str)

        # Map campaigns to apps
        campaign_df["app_id"] = campaign_df["campaign_id"].map(campaign_to_app)

        # Filter out campaigns without app mapping
        app_df = campaign_df[campaign_df["app_id"].notna()].copy()

        if app_df.empty:
            return pd.DataFrame()

        # Aggregate by date and app
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

        # Rename columns to match standard format
        aggregated.rename(columns={"campaign_id": "campaigns"}, inplace=True)

        # Add derived metrics
        aggregated["cpi"] = aggregated.apply(
            lambda x: x["spend"] / x["installs"] if x["installs"] > 0 else 0, axis=1
        ).round(2)

        aggregated["ctr"] = aggregated.apply(
            lambda x: (x["taps"] / x["impressions"] * 100) if x["impressions"] > 0 else 0, axis=1
        ).round(2)

        aggregated["cvr"] = aggregated.apply(
            lambda x: (x["installs"] / x["taps"] * 100) if x["taps"] > 0 else 0, axis=1
        ).round(2)

        # Sort by date and app
        aggregated.sort_values(["date", "app_id"], inplace=True)

        # Filter to ensure we only return data within the requested date range
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, "%Y-%m-%d")
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, "%Y-%m-%d")

        aggregated["date_dt"] = pd.to_datetime(aggregated["date"])
        start_date_only = start_date.date() if hasattr(start_date, "date") else start_date
        end_date_only = end_date.date() if hasattr(end_date, "date") else end_date

        aggregated = aggregated[
            (aggregated["date_dt"].dt.date >= start_date_only)
            & (aggregated["date_dt"].dt.date <= end_date_only)
        ].copy()

        # Drop the temporary datetime column
        aggregated.drop("date_dt", axis=1, inplace=True)

        return aggregated
