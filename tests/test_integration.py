"""
Integration tests for Apple Search Ads API.

These tests make real API calls and require valid credentials.
They are skipped unless the required environment variables are set.

Required environment variables:
- APPLE_SEARCH_ADS_CLIENT_ID
- APPLE_SEARCH_ADS_TEAM_ID
- APPLE_SEARCH_ADS_KEY_ID
- APPLE_SEARCH_ADS_PRIVATE_KEY_PATH or APPLE_SEARCH_ADS_PRIVATE_KEY

Optional:
- APPLE_SEARCH_ADS_ORG_ID (will use first available org if not set)
"""

import os
import pytest
import time
from datetime import datetime, timedelta

# Load environment variables from .env file
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from apple_search_ads import AppleSearchAdsClient


# Skip all tests in this file if credentials are not available
pytestmark = pytest.mark.skipif(
    not all(
        [
            os.environ.get("APPLE_SEARCH_ADS_CLIENT_ID"),
            os.environ.get("APPLE_SEARCH_ADS_TEAM_ID"),
            os.environ.get("APPLE_SEARCH_ADS_KEY_ID"),
            any(
                [
                    os.environ.get("APPLE_SEARCH_ADS_PRIVATE_KEY_PATH"),
                    os.environ.get("APPLE_SEARCH_ADS_PRIVATE_KEY"),
                ]
            ),
        ]
    ),
    reason="Integration tests require Apple Search Ads credentials",
)


class TestAppleSearchAdsIntegration:
    """Integration tests that make real API calls."""

    @pytest.fixture(scope="function")
    def client(self):
        """Create a real client with credentials."""
        # Use standard environment variables
        client = AppleSearchAdsClient(
            client_id=os.environ.get("APPLE_SEARCH_ADS_CLIENT_ID"),
            team_id=os.environ.get("APPLE_SEARCH_ADS_TEAM_ID"),
            key_id=os.environ.get("APPLE_SEARCH_ADS_KEY_ID"),
            private_key_path=os.environ.get("APPLE_SEARCH_ADS_PRIVATE_KEY_PATH"),
            private_key_content=os.environ.get("APPLE_SEARCH_ADS_PRIVATE_KEY"),
            org_id=os.environ.get("APPLE_SEARCH_ADS_ORG_ID"),
        )

        # If no org_id provided, get the first available one
        if not client.org_id:
            orgs = client.get_all_organizations()
            if orgs:
                client.org_id = str(orgs[0]["orgId"])

        return client

    def test_authentication_flow(self, client):
        """Test real JWT generation and token exchange."""
        # Clear any cached token
        client._token = None
        client._token_expiry = None

        # Get a fresh token
        token = client._get_access_token()

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 50  # Real tokens are long
        assert client._token == token
        assert client._token_expiry > time.time()

    def test_token_caching(self, client):
        """Test that token caching works in real scenarios."""
        # Get initial token
        token1 = client._get_access_token()
        expiry1 = client._token_expiry

        # Get token again - should be cached
        token2 = client._get_access_token()
        expiry2 = client._token_expiry

        assert token1 == token2
        assert expiry1 == expiry2

    def test_get_organizations(self, client):
        """Test fetching real organizations."""
        orgs = client.get_all_organizations()

        assert isinstance(orgs, list)
        assert len(orgs) > 0

        # Check organization structure
        org = orgs[0]
        assert "orgId" in org
        assert "orgName" in org
        assert "currency" in org
        assert "paymentModel" in org

        # Verify org_id is a string of digits
        assert isinstance(org["orgId"], (str, int))
        assert str(org["orgId"]).isdigit()

    def test_set_organization(self, client):
        """Test organization context is properly set."""
        orgs = client.get_all_organizations()

        if len(orgs) > 0:
            # Test that client can be created with specific org_id
            org_id = str(orgs[0]["orgId"])
            new_client = AppleSearchAdsClient(
                client_id=os.environ.get("APPLE_SEARCH_ADS_CLIENT_ID"),
                team_id=os.environ.get("APPLE_SEARCH_ADS_TEAM_ID"),
                key_id=os.environ.get("APPLE_SEARCH_ADS_KEY_ID"),
                private_key_path=os.environ.get("APPLE_SEARCH_ADS_PRIVATE_KEY_PATH"),
                org_id=org_id,
            )
            assert new_client.org_id == org_id

    @pytest.mark.slow
    def test_get_campaigns(self, client):
        """Test fetching real campaigns."""
        # Ensure we have an org set
        if not client.org_id:
            orgs = client.get_all_organizations()
            if orgs:
                client.org_id = str(orgs[0]["orgId"])

        campaigns = client.get_campaigns()

        assert isinstance(campaigns, list)
        # Note: Account might have no campaigns

        if len(campaigns) > 0:
            campaign = campaigns[0]
            assert "id" in campaign
            assert "name" in campaign
            assert "status" in campaign
            assert "adamId" in campaign

    @pytest.mark.slow
    def test_get_adgroups(self, client):
        """Test fetching ad groups for a campaign."""
        # Ensure we have an org set
        if not client.org_id:
            orgs = client.get_all_organizations()
            if orgs:
                client.org_id = str(orgs[0]["orgId"])

        # Get campaigns first
        campaigns = client.get_campaigns()

        if campaigns:
            # Use the first campaign
            campaign_id = str(campaigns[0]["id"])
            campaign_name = campaigns[0]["name"]
            print(f"Testing ad groups for campaign: {campaign_name} (ID: {campaign_id})")

            adgroups = client.get_adgroups(campaign_id)

            assert isinstance(adgroups, list)
            print(f"Found {len(adgroups)} ad groups")

            if len(adgroups) > 0:
                adgroup = adgroups[0]
                assert "id" in adgroup
                assert "name" in adgroup
                assert "campaignId" in adgroup
                assert str(adgroup["campaignId"]) == campaign_id
        else:
            pytest.skip("No campaigns available for testing ad groups")

    @pytest.mark.slow
    def test_campaign_report_recent_data(self, client):
        """Test fetching campaign report for recent dates."""
        # Use recent dates to ensure data availability
        end_date = datetime.now() - timedelta(days=2)  # Account for timezone
        start_date = end_date - timedelta(days=7)

        df = client.get_campaign_report(start_date, end_date)

        # DataFrame might be empty if no campaigns or no data
        assert df is not None

        if not df.empty:
            # Check expected columns (note: API returns 'taps' not 'clicks')
            expected_columns = [
                "date",
                "campaign_id",
                "campaign_name",
                "spend",
                "impressions",
                "taps",
                "installs",
            ]
            for col in expected_columns:
                assert col in df.columns

            # Verify data types
            assert df["spend"].dtype == "float64"
            assert df["impressions"].dtype in ["int64", "float64"]

    @pytest.mark.slow
    def test_multi_organization_access(self, client):
        """Test accessing data from multiple organizations."""
        orgs = client.get_all_organizations()

        if len(orgs) > 1:
            # Test switching between organizations
            org1_id = str(orgs[0]["orgId"])
            org2_id = str(orgs[1]["orgId"])

            # Create client for first org
            client1 = AppleSearchAdsClient(
                client_id=os.environ.get("APPLE_SEARCH_ADS_CLIENT_ID"),
                team_id=os.environ.get("APPLE_SEARCH_ADS_TEAM_ID"),
                key_id=os.environ.get("APPLE_SEARCH_ADS_KEY_ID"),
                private_key_path=os.environ.get("APPLE_SEARCH_ADS_PRIVATE_KEY_PATH"),
                org_id=org1_id,
            )
            campaigns1 = client1.get_campaigns()

            # Create client for second org
            client2 = AppleSearchAdsClient(
                client_id=os.environ.get("APPLE_SEARCH_ADS_CLIENT_ID"),
                team_id=os.environ.get("APPLE_SEARCH_ADS_TEAM_ID"),
                key_id=os.environ.get("APPLE_SEARCH_ADS_KEY_ID"),
                private_key_path=os.environ.get("APPLE_SEARCH_ADS_PRIVATE_KEY_PATH"),
                org_id=org2_id,
            )
            campaigns2 = client2.get_campaigns()

            # Just verify we can access different orgs
            assert isinstance(campaigns1, list)
            assert isinstance(campaigns2, list)

    @pytest.mark.slow
    def test_error_handling_invalid_org(self, client):
        """Test error handling with invalid organization ID."""
        # Set an invalid org ID
        client.org_id = "999999999999"  # Unlikely to be valid

        # This should raise an error or return empty data
        try:
            campaigns = client.get_campaigns()
            # If no error, should return empty list
            assert campaigns == []
        except Exception as e:
            # Should be a proper API error
            assert "org" in str(e).lower() or "403" in str(e)

    @pytest.mark.slow
    def test_daily_spend_functionality(self, client):
        """Test daily spend aggregation with real data."""
        # Ensure we have an org set
        if not client.org_id:
            orgs = client.get_all_organizations()
            if orgs:
                client.org_id = str(orgs[0]["orgId"])

        # Only test if we have campaigns
        campaigns = client.get_campaigns()

        if campaigns:
            # Get spend for last 7 days
            df = client.get_daily_spend(days=7, fetch_all_orgs=False)

            assert df is not None

            if not df.empty:
                # Check aggregation columns
                assert "date" in df.columns
                assert "spend" in df.columns
                assert "taps" in df.columns

                # Verify it's actually aggregated by date
                assert len(df["date"].unique()) == len(df)

    @pytest.mark.slow
    def test_spend_by_app_functionality(self, client):
        """Test spend by app aggregation with real data."""
        # Ensure we have an org set
        if not client.org_id:
            orgs = client.get_all_organizations()
            if orgs:
                client.org_id = str(orgs[0]["orgId"])

        # Only test if we have campaigns
        campaigns = client.get_campaigns()

        if campaigns:
            end_date = datetime.now() - timedelta(days=2)
            start_date = end_date - timedelta(days=7)

            df = client.get_daily_spend_by_app(start_date, end_date, fetch_all_orgs=False)

            assert df is not None

            if not df.empty:
                # Check expected columns
                assert "date" in df.columns
                assert "app_id" in df.columns
                assert "spend" in df.columns
                assert "campaigns" in df.columns

                # Verify it's grouped by date and app
                grouped = df.groupby(["date", "app_id"]).size()
                assert len(grouped) == len(df)
