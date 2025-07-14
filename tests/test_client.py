"""
Unit tests for Apple Search Ads Client.
"""

import pytest
from unittest.mock import Mock, patch, mock_open
import pandas as pd
from datetime import datetime
import time
import requests

from apple_search_ads import AppleSearchAdsClient


class TestAppleSearchAdsClient:
    """Test cases for AppleSearchAdsClient."""

    @pytest.fixture
    def mock_credentials(self):
        """Mock credentials for testing."""
        return {
            "client_id": "test_client_id",
            "team_id": "test_team_id",
            "key_id": "test_key_id",
            "private_key_content": "-----BEGIN PRIVATE KEY-----\ntest_key\n-----END PRIVATE KEY-----",
        }

    @pytest.fixture
    def client(self, mock_credentials):
        """Create a client instance with mock credentials."""
        return AppleSearchAdsClient(**mock_credentials)

    def test_client_initialization_with_params(self, mock_credentials):
        """Test client initialization with parameters."""
        client = AppleSearchAdsClient(**mock_credentials)
        assert client.client_id == "test_client_id"
        assert client.team_id == "test_team_id"
        assert client.key_id == "test_key_id"
        assert client.private_key_content == mock_credentials["private_key_content"]

    @patch.dict(
        "os.environ",
        {
            "APPLE_SEARCH_ADS_CLIENT_ID": "env_client_id",
            "APPLE_SEARCH_ADS_TEAM_ID": "env_team_id",
            "APPLE_SEARCH_ADS_KEY_ID": "env_key_id",
            "APPLE_SEARCH_ADS_PRIVATE_KEY_PATH": "/path/to/key.p8",
        },
    )
    @patch("builtins.open", mock_open(read_data="test_key_content"))
    def test_client_initialization_with_env_vars(self):
        """Test client initialization with environment variables."""
        client = AppleSearchAdsClient()
        assert client.client_id == "env_client_id"
        assert client.team_id == "env_team_id"
        assert client.key_id == "env_key_id"
        assert client.private_key_path == "/path/to/key.p8"

    @patch.dict("os.environ", {}, clear=True)
    def test_client_initialization_missing_credentials(self):
        """Test client initialization with missing credentials."""
        with pytest.raises(ValueError) as exc_info:
            AppleSearchAdsClient(client_id="test")
        assert "Missing required credentials" in str(exc_info.value)

    @patch.dict("os.environ", {}, clear=True)
    def test_client_initialization_missing_private_key(self):
        """Test client initialization with missing private key."""
        with pytest.raises(ValueError) as exc_info:
            AppleSearchAdsClient(client_id="test", team_id="test", key_id="test")
        assert "Missing private key" in str(exc_info.value)

    def test_client_initialization_with_private_key_path(self):
        """Test client initialization with private key path."""
        mock_file_content = (
            "-----BEGIN PRIVATE KEY-----\ntest_key_from_file\n-----END PRIVATE KEY-----"
        )
        with patch("builtins.open", mock_open(read_data=mock_file_content)) as mock_file:
            with patch("os.path.exists", return_value=True):
                client = AppleSearchAdsClient(
                    client_id="test",
                    team_id="test",
                    key_id="test",
                    private_key_path="/path/to/key.p8",
                )
                assert client.private_key_path == "/path/to/key.p8"
                assert client.private_key_content is None  # Not loaded yet

                # Test that private key is loaded when needed
                loaded_key = client._load_private_key()
                assert loaded_key == mock_file_content
                mock_file.assert_called_once_with("/path/to/key.p8", "r")

    def test_client_initialization_with_missing_private_key_file(self):
        """Test client initialization when private key file doesn't exist."""
        with patch("os.path.exists", return_value=False):
            client = AppleSearchAdsClient(
                client_id="test",
                team_id="test",
                key_id="test",
                private_key_path="/nonexistent/path/key.p8",
            )

            # Private key file error happens when loading, not during init
            with pytest.raises(FileNotFoundError) as exc_info:
                client._load_private_key()

            assert "Private key file not found" in str(exc_info.value)

    def test_load_private_key_no_path_provided(self):
        """Test _load_private_key when private_key_path is None."""
        client = AppleSearchAdsClient(
            client_id="test", team_id="test", key_id="test", private_key_content="test_key_content"
        )

        # Manually set both to None to trigger the missing line
        client.private_key_content = None
        client.private_key_path = None

        with pytest.raises(ValueError) as exc_info:
            client._load_private_key()

        assert "No private key path provided" in str(exc_info.value)

    @patch("jwt.encode")
    def test_generate_client_secret(self, mock_jwt_encode, client):
        """Test JWT client secret generation."""
        mock_jwt_encode.return_value = "test_jwt_token"

        secret = client._generate_client_secret()

        assert secret == "test_jwt_token"
        mock_jwt_encode.assert_called_once()

        # Check JWT payload
        call_args = mock_jwt_encode.call_args
        payload = call_args[0][0]
        assert payload["sub"] == "test_client_id"
        assert payload["iss"] == "test_team_id"
        assert payload["aud"] == "https://appleid.apple.com"

    @patch("requests.post")
    def test_get_access_token(self, mock_post, client):
        """Test access token retrieval."""
        mock_response = Mock()
        mock_response.json.return_value = {"access_token": "test_access_token"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        with patch.object(client, "_generate_client_secret", return_value="test_secret"):
            token = client._get_access_token()

        assert token == "test_access_token"
        assert client._token == "test_access_token"
        mock_post.assert_called_once_with(
            "https://appleid.apple.com/auth/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": "test_client_id",
                "client_secret": "test_secret",
                "scope": "searchadsorg",
            },
        )

    @patch("requests.post")
    def test_get_access_token_none_returned(self, mock_post, client):
        """Test access token retrieval when None is returned."""
        mock_response = Mock()
        mock_response.json.return_value = {"access_token": None}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        with patch.object(client, "_generate_client_secret", return_value="test_secret"):
            with pytest.raises(ValueError) as exc_info:
                client._get_access_token()

        assert "Failed to obtain access token" in str(exc_info.value)

    def test_get_access_token_cached(self, client):
        """Test that cached token is returned when still valid."""
        # Set up a cached token
        client._token = "cached_token"
        # Use time.time() for consistency with the code
        client._token_expiry = time.time() + 1800  # 30 minutes from now

        # Get token should return cached token without making API call
        with patch("requests.post") as mock_post:
            token = client._get_access_token()

            assert token == "cached_token"
            mock_post.assert_not_called()

    def test_get_headers_without_org(self, client):
        """Test header generation without organization context."""
        with patch.object(client, "_get_access_token", return_value="test_token"):
            headers = client._get_headers(include_org_context=False)

        assert headers == {"Authorization": "Bearer test_token", "Content-Type": "application/json"}

    def test_get_headers_with_org(self, client):
        """Test header generation with organization context."""
        client.org_id = "12345"
        with patch.object(client, "_get_access_token", return_value="test_token"):
            headers = client._get_headers(include_org_context=True)

        assert headers == {
            "Authorization": "Bearer test_token",
            "Content-Type": "application/json",
            "X-AP-Context": "orgId=12345",
        }

    @patch("requests.request")
    def test_make_request(self, mock_request, client):
        """Test making API requests."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": "test"}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response

        with patch.object(client, "_get_headers", return_value={"test": "header"}):
            result = client._make_request("https://test.url", method="GET")

        assert result == {"data": "test"}
        mock_request.assert_called_once_with(
            method="GET", url="https://test.url", headers={"test": "header"}, json=None, params=None
        )

    @patch("requests.request")
    def test_make_request_http_error(self, mock_request, client):
        """Test API request with HTTP error."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
        mock_request.return_value = mock_response

        with patch.object(client, "_get_headers", return_value={"test": "header"}):
            with pytest.raises(requests.exceptions.HTTPError):
                client._make_request("https://test.url")

    @patch("requests.request")
    def test_make_request_rate_limit_error(self, mock_request, client):
        """Test API request with rate limit error (429)."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "429 Too Many Requests"
        )
        mock_request.return_value = mock_response

        with patch.object(client, "_get_headers", return_value={"test": "header"}):
            with pytest.raises(requests.exceptions.HTTPError):
                client._make_request("https://test.url")

    @patch("requests.request")
    def test_make_request_server_error(self, mock_request, client):
        """Test API request with server error (500)."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "500 Internal Server Error"
        )
        mock_request.return_value = mock_response

        with patch.object(client, "_get_headers", return_value={"test": "header"}):
            with pytest.raises(requests.exceptions.HTTPError):
                client._make_request("https://test.url")

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_all_organizations(self, mock_make_request, client):
        """Test fetching all organizations."""
        mock_make_request.return_value = {
            "data": [
                {"orgId": "123", "orgName": "Test Org 1"},
                {"orgId": "456", "orgName": "Test Org 2"},
            ]
        }

        orgs = client.get_all_organizations()

        assert len(orgs) == 2
        assert orgs[0]["orgId"] == "123"
        assert orgs[1]["orgName"] == "Test Org 2"
        mock_make_request.assert_called_once_with(
            f"{client.BASE_URL}/acls", include_org_context=False
        )

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_all_organizations_empty_response(self, mock_make_request, client):
        """Test fetching organizations with empty response."""
        mock_make_request.return_value = {}

        orgs = client.get_all_organizations()

        assert orgs == []

    def test_get_org_id_already_set(self, client):
        """Test _get_org_id when org_id is already set."""
        client.org_id = "existing_org_id"

        # Should return without making any API calls
        client._get_org_id()

        assert client.org_id == "existing_org_id"

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_org_id_no_organizations(self, mock_make_request, client):
        """Test _get_org_id when no organizations are found."""
        # Clear org_id to force fetch
        client.org_id = None

        # Mock empty response
        mock_make_request.return_value = {"data": []}

        with pytest.raises(ValueError) as exc_info:
            client._get_org_id()

        assert "No organization found" in str(exc_info.value)

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_org_id_success(self, mock_make_request, client):
        """Test successful _get_org_id call."""
        # Clear org_id to force fetch
        client.org_id = None

        # Mock response with organization
        mock_make_request.return_value = {"data": [{"orgId": "789", "orgName": "Test Org"}]}

        org_id = client._get_org_id()

        assert org_id == "789"
        assert client.org_id == "789"

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_campaigns(self, mock_make_request, client):
        """Test fetching campaigns."""
        client.org_id = "123"
        mock_make_request.return_value = {
            "data": [
                {"id": "1", "name": "Campaign 1", "status": "ENABLED"},
                {"id": "2", "name": "Campaign 2", "status": "PAUSED"},
            ]
        }

        campaigns = client.get_campaigns()

        assert len(campaigns) == 2
        assert campaigns[0]["fetched_org_id"] == "123"
        assert campaigns[1]["name"] == "Campaign 2"

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_adgroups(self, mock_make_request, client):
        """Test fetching ad groups for a campaign."""
        client.org_id = "123"
        mock_make_request.return_value = {
            "data": [
                {"id": "1", "name": "Ad Group 1", "status": "ENABLED"},
                {"id": "2", "name": "Ad Group 2", "status": "PAUSED"},
            ]
        }

        adgroups = client.get_adgroups("campaign123")

        assert len(adgroups) == 2
        assert adgroups[0]["name"] == "Ad Group 1"
        assert adgroups[1]["status"] == "PAUSED"
        mock_make_request.assert_called_once_with(
            f"{client.BASE_URL}/campaigns/campaign123/adgroups", params={"limit": 1000}
        )

    @patch.object(AppleSearchAdsClient, "_get_org_id")
    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_adgroups_no_org_id(self, mock_make_request, mock_get_org_id, client):
        """Test fetching ad groups when org_id is not set."""
        client.org_id = None
        mock_make_request.return_value = {"data": []}

        adgroups = client.get_adgroups("campaign123")

        mock_get_org_id.assert_called_once()
        assert adgroups == []

    @patch.object(AppleSearchAdsClient, "get_all_organizations")
    @patch.object(AppleSearchAdsClient, "get_campaigns")
    def test_get_all_campaigns(self, mock_get_campaigns, mock_get_orgs, client):
        """Test fetching campaigns from all organizations."""
        # Mock organizations
        mock_get_orgs.return_value = [
            {"orgId": "123", "orgName": "Org 1"},
            {"orgId": "456", "orgName": "Org 2"},
        ]

        # Mock campaigns for each org
        mock_get_campaigns.side_effect = [
            [{"id": "1", "name": "Campaign 1", "fetched_org_id": "123"}],
            [{"id": "2", "name": "Campaign 2", "fetched_org_id": "456"}],
        ]

        campaigns = client.get_all_campaigns()

        assert len(campaigns) == 2
        assert campaigns[0]["name"] == "Campaign 1"
        assert campaigns[1]["name"] == "Campaign 2"
        assert mock_get_campaigns.call_count == 2

    @patch.object(AppleSearchAdsClient, "get_all_organizations")
    @patch.object(AppleSearchAdsClient, "get_campaigns")
    def test_get_all_campaigns_with_error(self, mock_get_campaigns, mock_get_orgs, client):
        """Test get_all_campaigns error handling."""
        # Mock organizations
        mock_get_orgs.return_value = [
            {"orgId": "123", "orgName": "Org 1"},
            {"orgId": "456", "orgName": "Org 2"},
        ]

        # First org succeeds, second org fails
        mock_get_campaigns.side_effect = [
            [{"id": "1", "name": "Campaign 1"}],
            Exception("API Error"),
        ]

        campaigns = client.get_all_campaigns()

        # Should still return campaigns from successful org
        assert len(campaigns) == 1
        assert campaigns[0]["name"] == "Campaign 1"

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_campaign_report(self, mock_make_request, client):
        """Test fetching campaign report."""
        client.org_id = "123"
        mock_make_request.return_value = {
            "data": {
                "reportingDataResponse": {
                    "row": [
                        {
                            "metadata": {
                                "campaignId": "1",
                                "campaignName": "Test Campaign",
                                "adamId": "123456",
                            },
                            "granularity": [
                                {
                                    "date": "2024-01-01",
                                    "impressions": 1000,
                                    "taps": 50,
                                    "totalInstalls": 10,
                                    "localSpend": {"amount": 100.0, "currency": "USD"},
                                }
                            ],
                        }
                    ]
                }
            }
        }

        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 7)

        df = client.get_campaign_report(start_date, end_date)

        assert not df.empty
        assert len(df) == 1
        assert df.iloc[0]["campaign_name"] == "Test Campaign"
        assert df.iloc[0]["spend"] == 100.0
        assert df.iloc[0]["adam_id"] == "123456"

    @patch.object(AppleSearchAdsClient, "get_all_organizations")
    @patch.object(AppleSearchAdsClient, "get_campaign_report")
    def test_get_daily_spend(self, mock_get_report, mock_get_orgs, client):
        """Test getting daily spend."""
        # Mock organizations
        mock_get_orgs.return_value = [{"orgId": "123", "orgName": "Test Org"}]

        mock_df = pd.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-01", "2024-01-02"],
                "spend": [100.0, 50.0, 75.0],
                "impressions": [1000, 500, 750],
                "taps": [50, 25, 40],
                "installs": [10, 5, 8],
            }
        )
        mock_get_report.return_value = mock_df

        result = client.get_daily_spend(days=7)

        assert len(result) == 2  # Two unique dates
        assert result.iloc[0]["spend"] == 150.0  # 100 + 50
        assert result.iloc[1]["spend"] == 75.0
        assert "taps" in result.columns

    @patch.object(AppleSearchAdsClient, "get_all_organizations")
    @patch.object(AppleSearchAdsClient, "get_campaigns_with_details")
    @patch.object(AppleSearchAdsClient, "get_campaign_report")
    def test_get_daily_spend_by_app(
        self, mock_get_report, mock_get_campaigns, mock_get_orgs, client
    ):
        """Test getting daily spend by app."""
        # Mock organizations
        mock_get_orgs.return_value = [{"orgId": "123", "orgName": "Test Org"}]

        # Mock campaigns with app IDs
        mock_get_campaigns.return_value = [
            {"id": "1", "adamId": "123456"},
            {"id": "2", "adamId": "789012"},
        ]

        # Mock campaign report
        mock_df = pd.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-01", "2024-01-02"],
                "campaign_id": ["1", "2", "1"],
                "spend": [100.0, 50.0, 75.0],
                "impressions": [1000, 500, 750],
                "taps": [50, 25, 40],
                "installs": [10, 5, 8],
            }
        )
        mock_get_report.return_value = mock_df

        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 2)

        result = client.get_daily_spend_by_app(start_date, end_date)

        assert len(result) == 3  # 3 date-app combinations
        assert "123456" in result["app_id"].values
        assert "789012" in result["app_id"].values
        assert "taps" in result.columns
        assert "campaigns" in result.columns  # campaign count

    @patch.object(AppleSearchAdsClient, "get_all_campaigns")
    def test_get_campaigns_with_details_all_orgs(self, mock_get_all_campaigns, client):
        """Test get_campaigns_with_details with fetch_all_orgs=True."""
        mock_campaigns = [
            {"id": "1", "name": "Campaign 1", "adamId": "123456"},
            {"id": "2", "name": "Campaign 2", "adamId": "789012"},
        ]
        mock_get_all_campaigns.return_value = mock_campaigns

        campaigns = client.get_campaigns_with_details(fetch_all_orgs=True)

        assert campaigns == mock_campaigns
        mock_get_all_campaigns.assert_called_once()

    @patch.object(AppleSearchAdsClient, "_get_org_id")
    @patch.object(AppleSearchAdsClient, "get_campaigns")
    def test_get_campaigns_with_details_single_org(
        self, mock_get_campaigns, mock_get_org_id, client
    ):
        """Test get_campaigns_with_details with fetch_all_orgs=False."""
        client.org_id = None
        mock_campaigns = [{"id": "1", "name": "Campaign 1"}]
        mock_get_campaigns.return_value = mock_campaigns

        campaigns = client.get_campaigns_with_details(fetch_all_orgs=False)

        assert campaigns == mock_campaigns
        mock_get_org_id.assert_called_once()
        mock_get_campaigns.assert_called_once()

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_campaign_report_with_string_dates(self, mock_make_request, client):
        """Test campaign report with string date inputs."""
        client.org_id = "123"
        mock_make_request.return_value = {
            "data": {
                "reportingDataResponse": {
                    "row": [
                        {
                            "metadata": {"campaignId": "1"},
                            "granularity": [
                                {
                                    "date": "2024-01-01",
                                    "impressions": 100,
                                    "taps": 10,
                                    "totalInstalls": 1,
                                    "localSpend": {"amount": 10.0, "currency": "USD"},
                                }
                            ],
                        }
                    ]
                }
            }
        }

        # Test with string dates
        df = client.get_campaign_report("2024-01-01", "2024-01-07")

        assert not df.empty
        assert len(df) == 1

    @patch.object(AppleSearchAdsClient, "_get_org_id")
    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_campaign_report_no_org_id(self, mock_make_request, mock_get_org_id, client):
        """Test campaign report when org_id needs to be fetched."""
        client.org_id = None
        mock_make_request.return_value = {"data": {"reportingDataResponse": {"row": []}}}

        df = client.get_campaign_report(datetime(2024, 1, 1), datetime(2024, 1, 7))

        mock_get_org_id.assert_called_once()
        assert df.empty

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_campaigns_with_org_id_param_and_finally(self, mock_make_request, client):
        """Test get_campaigns with org_id parameter and finally block."""
        client.org_id = "original_org"
        mock_make_request.return_value = {"data": [{"id": "1", "name": "Campaign"}]}

        # Call with specific org_id
        campaigns = client.get_campaigns(org_id="specific_org")

        # Should restore original org_id via finally block
        assert client.org_id == "original_org"
        assert len(campaigns) == 1
        assert campaigns[0]["fetched_org_id"] == "specific_org"

    @patch.object(AppleSearchAdsClient, "_get_org_id")
    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_campaigns_no_org_id(self, mock_make_request, mock_get_org_id, client):
        """Test get_campaigns when both org_id param and self.org_id are None."""
        client.org_id = None
        mock_make_request.return_value = {"data": []}

        campaigns = client.get_campaigns(org_id=None)

        mock_get_org_id.assert_called_once()
        assert campaigns == []

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_campaign_report_legacy_format(self, mock_make_request, client):
        """Test campaign report with legacy 'rows' response format."""
        client.org_id = "123"
        mock_make_request.return_value = {
            "data": {
                "rows": [
                    {
                        "metadata": {
                            "campaignId": "1",
                            "campaignName": "Legacy Campaign",
                            "adamId": "999888",
                        },
                        "granularity": [
                            {
                                "date": "2024-01-01",
                                "impressions": 200,
                                "taps": 20,
                                "totalInstalls": 2,
                                "localSpend": {"amount": 20.0, "currency": "USD"},
                            }
                        ],
                    }
                ]
            }
        }

        df = client.get_campaign_report(datetime(2024, 1, 1), datetime(2024, 1, 7))

        assert not df.empty
        assert len(df) == 1
        assert df.iloc[0]["campaign_name"] == "Legacy Campaign"
        assert df.iloc[0]["adam_id"] == "999888"

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_campaign_report_legacy_metrics_format(self, mock_make_request, client):
        """Test campaign report with legacy 'metrics' format without granularity."""
        client.org_id = "123"
        mock_make_request.return_value = {
            "data": {
                "rows": [
                    {
                        "metadata": {
                            "date": "2024-01-01",
                            "campaignId": "1",
                            "campaignName": "Legacy Campaign",
                        },
                        "metrics": {
                            "impressions": 300,
                            "taps": 30,
                            "totalInstalls": 3,
                            "localSpend": {"amount": 30.0, "currency": "USD"},
                        },
                    }
                ]
            }
        }

        df = client.get_campaign_report(datetime(2024, 1, 1), datetime(2024, 1, 7))

        assert not df.empty
        assert len(df) == 1
        assert df.iloc[0]["campaign_name"] == "Legacy Campaign"
        assert df.iloc[0]["spend"] == 30.0

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_campaign_report_empty_rows(self, mock_make_request, client):
        """Test campaign report with empty rows."""
        client.org_id = "123"
        mock_make_request.return_value = {"data": {"reportingDataResponse": {"row": []}}}

        df = client.get_campaign_report(datetime(2024, 1, 1), datetime(2024, 1, 7))

        assert df.empty

    @patch.object(AppleSearchAdsClient, "get_all_organizations")
    @patch.object(AppleSearchAdsClient, "get_campaign_report")
    def test_get_daily_spend_empty_campaign_data(self, mock_get_report, mock_get_orgs, client):
        """Test get_daily_spend with empty campaign data."""
        mock_get_orgs.return_value = [{"orgId": "123"}]
        mock_get_report.return_value = pd.DataFrame()  # Empty DataFrame

        result = client.get_daily_spend(days=7)

        assert result.empty

    @patch.object(AppleSearchAdsClient, "get_campaigns")
    def test_get_daily_spend_single_org(self, mock_get_campaigns, client):
        """Test get_daily_spend with fetch_all_orgs=False."""
        client.org_id = "123"

        with patch.object(client, "get_campaign_report") as mock_report:
            mock_report.return_value = pd.DataFrame(
                {
                    "date": ["2024-01-01"],
                    "spend": [100.0],
                    "impressions": [1000],
                    "taps": [50],
                    "installs": [5],
                }
            )

            result = client.get_daily_spend(days=7, fetch_all_orgs=False)

            assert len(result) == 1
            assert result.iloc[0]["spend"] == 100.0

    @patch.object(AppleSearchAdsClient, "get_all_organizations")
    @patch.object(AppleSearchAdsClient, "get_campaign_report")
    def test_get_daily_spend_with_exception(self, mock_get_report, mock_get_orgs, client):
        """Test get_daily_spend with exception during report fetching."""
        mock_get_orgs.return_value = [{"orgId": "123"}, {"orgId": "456"}]
        mock_get_report.side_effect = [
            pd.DataFrame(
                {
                    "date": ["2024-01-01"],
                    "spend": [50.0],
                    "impressions": [500],
                    "taps": [10],
                    "installs": [2],
                }
            ),
            Exception("API Error"),
        ]

        result = client.get_daily_spend(days=7)

        # Should still return data from successful org
        assert len(result) == 1
        assert result.iloc[0]["spend"] == 50.0

    @patch.object(AppleSearchAdsClient, "get_all_organizations")
    @patch.object(AppleSearchAdsClient, "get_campaigns_with_details")
    @patch.object(AppleSearchAdsClient, "get_campaign_report")
    def test_get_daily_spend_by_app_empty_campaign_data(
        self, mock_report, mock_campaigns, mock_orgs, client
    ):
        """Test get_daily_spend_by_app with empty campaign data."""
        mock_orgs.return_value = [{"orgId": "123"}]
        mock_campaigns.return_value = []
        mock_report.return_value = pd.DataFrame()

        result = client.get_daily_spend_by_app(datetime(2024, 1, 1), datetime(2024, 1, 2))

        assert result.empty

    @patch.object(AppleSearchAdsClient, "get_all_organizations")
    @patch.object(AppleSearchAdsClient, "get_campaigns_with_details")
    @patch.object(AppleSearchAdsClient, "get_campaign_report")
    def test_get_daily_spend_by_app_no_app_mapping(
        self, mock_report, mock_campaigns, mock_orgs, client
    ):
        """Test get_daily_spend_by_app when no apps are mapped."""
        # Mock organizations
        mock_orgs.return_value = [{"orgId": "123"}]

        # Campaigns without adamId
        mock_campaigns.return_value = [
            {"id": "1", "name": "Campaign 1"},
            {"id": "2", "name": "Campaign 2"},
        ]
        mock_report.return_value = pd.DataFrame(
            {
                "campaign_id": ["1", "2"],
                "date": ["2024-01-01", "2024-01-01"],
                "spend": [100.0, 50.0],
            }
        )

        result = client.get_daily_spend_by_app(datetime(2024, 1, 1), datetime(2024, 1, 2))

        assert result.empty

    @patch.object(AppleSearchAdsClient, "get_campaigns_with_details")
    @patch.object(AppleSearchAdsClient, "get_campaign_report")
    def test_get_daily_spend_by_app_single_org(self, mock_report, mock_campaigns, client):
        """Test get_daily_spend_by_app with fetch_all_orgs=False."""
        client.org_id = "123"
        mock_campaigns.return_value = [{"id": "1", "adamId": "999"}]
        mock_report.return_value = pd.DataFrame(
            {
                "campaign_id": ["1"],
                "date": ["2024-01-01"],
                "spend": [100.0],
                "impressions": [1000],
                "taps": [10],
                "installs": [2],
            }
        )

        result = client.get_daily_spend_by_app(
            datetime(2024, 1, 1), datetime(2024, 1, 2), fetch_all_orgs=False
        )

        assert len(result) == 1
        assert result.iloc[0]["app_id"] == "999"

    @patch.object(AppleSearchAdsClient, "get_all_organizations")
    @patch.object(AppleSearchAdsClient, "get_campaigns_with_details")
    @patch.object(AppleSearchAdsClient, "get_campaign_report")
    def test_get_daily_spend_by_app_with_exception(
        self, mock_report, mock_campaigns, mock_orgs, client
    ):
        """Test get_daily_spend_by_app with exception during report fetching."""
        mock_orgs.return_value = [{"orgId": "123"}, {"orgId": "456"}]
        mock_campaigns.return_value = [{"id": "1", "adamId": "999"}]

        # First org succeeds, second fails
        mock_report.side_effect = [
            pd.DataFrame(
                {
                    "campaign_id": ["1"],
                    "date": ["2024-01-01"],
                    "spend": [50.0],
                    "impressions": [500],
                    "taps": [5],
                    "installs": [1],
                }
            ),
            Exception("API Error"),
        ]

        result = client.get_daily_spend_by_app(datetime(2024, 1, 1), datetime(2024, 1, 2))

        # Should still return data from successful org
        assert len(result) == 1
        assert result.iloc[0]["spend"] == 50.0

    @patch.object(AppleSearchAdsClient, "get_all_organizations")
    @patch.object(AppleSearchAdsClient, "get_campaigns_with_details")
    @patch.object(AppleSearchAdsClient, "get_campaign_report")
    def test_get_daily_spend_by_app_string_dates(
        self, mock_report, mock_campaigns, mock_orgs, client
    ):
        """Test get_daily_spend_by_app with string dates in filtering."""
        # Mock organizations
        mock_orgs.return_value = [{"orgId": "123"}]

        client.org_id = "123"
        mock_campaigns.return_value = [{"id": "1", "adamId": "999"}]

        # Return data outside the date range to test filtering
        mock_report.return_value = pd.DataFrame(
            {
                "campaign_id": ["1", "1", "1"],
                "date": ["2023-12-31", "2024-01-01", "2024-01-03"],
                "spend": [10.0, 20.0, 30.0],
                "impressions": [100, 200, 300],
                "taps": [1, 2, 3],
                "installs": [0, 1, 1],
            }
        )

        result = client.get_daily_spend_by_app("2024-01-01", "2024-01-02")

        # Should only include data within date range
        assert len(result) == 1
        assert result.iloc[0]["date"] == "2024-01-01"
        assert result.iloc[0]["spend"] == 20.0
