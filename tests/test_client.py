"""
Unit tests for Apple Search Ads Client.
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, patch, mock_open
import pandas as pd
from datetime import datetime
import time
import requests

from apple_search_ads import AppleSearchAdsClient


def test_module_version_matches_installed_metadata():
    """__version__ must track the installed dist version, never a hardcoded string."""
    import importlib.metadata

    import apple_search_ads

    assert apple_search_ads.__version__ == importlib.metadata.version("apple-search-ads-client")


def modern_day_metrics(**overrides):
    """A complete v1 day row satisfying strict (v3) parsing."""
    metrics = {
        "impressions": 0,
        "taps": 0,
        "totalInstalls": 0,
        "totalNewDownloads": 0,
        "totalRedownloads": 0,
        "tapInstalls": 0,
        "viewInstalls": 0,
        "tapNewDownloads": 0,
        "tapRedownloads": 0,
        "viewNewDownloads": 0,
        "viewRedownloads": 0,
        "localSpend": {"amount": "0", "currency": "USD"},
    }
    metrics.update(overrides)
    return metrics


def report_response(rows, total=None):
    """A v1 report response page."""
    return {
        "result": {"rows": rows},
        "pagination": {
            "offset": 0,
            "pageSize": 1000,
            "totalCount": len(rows) if total is None else total,
        },
    }


def query_response(objects):
    """A v1 `/…/query` response page."""
    return {
        "result": objects,
        "pagination": {"offset": 0, "pageSize": 1000, "totalCount": len(objects)},
    }


def acl_response(*accounts):
    """A v1 ACL response; accounts are (id, name, parent orgId) tuples."""
    return {
        "result": {
            "acls": [
                {
                    "adAccount": {"id": acct_id, "name": name, "orgId": parent},
                    "roles": ["API Campaign Manager"],
                }
                for acct_id, name, parent in accounts
            ]
        }
    }


def ad_account_response(currency="USD", features=("APPSTORE_APP_MANUAL",), timezone="UTC"):
    return {
        "result": {
            "currency": currency,
            "paymentModel": "PAYG",
            "timezone": timezone,
            "productFeatures": list(features),
        }
    }


def v1_campaign(campaign_id, name, placements, **overrides):
    campaign = {
        "id": campaign_id,
        "name": name,
        "status": "ENABLED",
        "targeting": {"supplyPlacement": {"include": placements}},
    }
    campaign.update(overrides)
    return campaign


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
            timeout=30.0,
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
        """Test header generation with ad account context."""
        client.org_id = "12345"
        with patch.object(client, "_get_access_token", return_value="test_token"):
            headers = client._get_headers(include_org_context=True)

        assert headers == {
            "Authorization": "Bearer test_token",
            "Content-Type": "application/json",
            "X-AP-Context": "adAccountId=12345",
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
            method="GET",
            url="https://test.url",
            headers={"test": "header"},
            json=None,
            params=None,
            timeout=30.0,
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

    @patch.object(AppleSearchAdsClient, "_retry_sleep")
    @patch("requests.request")
    def test_make_request_rate_limit_error(self, mock_request, mock_sleep, client):
        """A persistent 429 still raises once the retry budget is spent."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "429 Too Many Requests", response=mock_response
        )
        mock_request.return_value = mock_response

        with patch.object(client, "_get_headers", return_value={"test": "header"}):
            with pytest.raises(requests.exceptions.HTTPError):
                client._make_request("https://test.url")

        assert mock_request.call_count == 3  # initial + 2 retries, then raises

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

    @patch("requests.request")
    def test_make_request_passes_default_timeout(self, mock_request, client):
        """Every API request carries the default 30s timeout instead of blocking forever."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": "test"}
        mock_request.return_value = mock_response

        with patch.object(client, "_get_headers", return_value={}):
            client._make_request("https://test.url")

        assert mock_request.call_args.kwargs["timeout"] == 30.0

    @patch("requests.request")
    def test_make_request_passes_custom_timeout(self, mock_request, mock_credentials):
        """A timeout given at construction is passed through to requests."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": "test"}
        mock_request.return_value = mock_response

        client = AppleSearchAdsClient(**mock_credentials, timeout=5.0)
        with patch.object(client, "_get_headers", return_value={}):
            client._make_request("https://test.url")

        assert mock_request.call_args.kwargs["timeout"] == 5.0

    @patch("requests.request")
    def test_make_request_timeout_none_disables(self, mock_request, mock_credentials):
        """timeout=None restores the old block-forever behavior explicitly."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": "test"}
        mock_request.return_value = mock_response

        client = AppleSearchAdsClient(**mock_credentials, timeout=None)
        with patch.object(client, "_get_headers", return_value={}):
            client._make_request("https://test.url")

        assert mock_request.call_args.kwargs["timeout"] is None

    @patch("requests.post")
    def test_token_fetch_passes_timeout(self, mock_post, client):
        """The OAuth token request also carries the timeout."""
        mock_response = Mock()
        mock_response.json.return_value = {"access_token": "tok"}
        mock_post.return_value = mock_response

        with patch.object(client, "_generate_client_secret", return_value="secret"):
            client._get_access_token()

        assert mock_post.call_args.kwargs["timeout"] == 30.0

    @patch.object(AppleSearchAdsClient, "_retry_sleep")
    @patch("requests.request")
    def test_retries_connect_timeout_then_succeeds(self, mock_request, mock_sleep, client):
        """A transient ConnectTimeout is retried and the call succeeds."""
        ok = Mock()
        ok.json.return_value = {"data": "test"}
        mock_request.side_effect = [requests.exceptions.ConnectTimeout("boom"), ok]

        with patch.object(client, "_get_headers", return_value={}):
            result = client._make_request("https://test.url")

        assert result == {"data": "test"}
        assert mock_request.call_count == 2
        mock_sleep.assert_called_once_with(1.0)

    @patch.object(AppleSearchAdsClient, "_retry_sleep")
    @patch("requests.request")
    def test_retries_502_then_succeeds(self, mock_request, mock_sleep, client):
        """A transient 502 is retried."""
        bad = Mock(status_code=502)
        bad.raise_for_status.side_effect = requests.exceptions.HTTPError(response=bad)
        ok = Mock()
        ok.json.return_value = {"data": "test"}
        mock_request.side_effect = [bad, ok]

        with patch.object(client, "_get_headers", return_value={}):
            result = client._make_request("https://test.url")

        assert result == {"data": "test"}
        assert mock_request.call_count == 2

    @patch.object(AppleSearchAdsClient, "_retry_sleep")
    @patch("requests.request")
    def test_retries_429_then_succeeds(self, mock_request, mock_sleep, client):
        """A server-side 429 is retried (the client-side throttle can't prevent these)."""
        bad = Mock(status_code=429)
        bad.raise_for_status.side_effect = requests.exceptions.HTTPError(response=bad)
        ok = Mock()
        ok.json.return_value = {"data": "test"}
        mock_request.side_effect = [bad, ok]

        with patch.object(client, "_get_headers", return_value={}):
            result = client._make_request("https://test.url")

        assert result == {"data": "test"}
        assert mock_request.call_count == 2

    @patch.object(AppleSearchAdsClient, "_retry_sleep")
    @patch("requests.request")
    def test_does_not_retry_404(self, mock_request, mock_sleep, client):
        """Non-transient HTTP errors fail fast — retrying a 404 just delays the truth."""
        bad = Mock(status_code=404)
        bad.raise_for_status.side_effect = requests.exceptions.HTTPError(response=bad)
        mock_request.return_value = bad

        with patch.object(client, "_get_headers", return_value={}):
            with pytest.raises(requests.exceptions.HTTPError):
                client._make_request("https://test.url")

        assert mock_request.call_count == 1
        mock_sleep.assert_not_called()

    @patch.object(AppleSearchAdsClient, "_retry_sleep")
    @patch("requests.request")
    def test_retry_budget_exhausted_raises_with_capped_backoff(
        self, mock_request, mock_sleep, client
    ):
        """Default budget is 2 retries (3 attempts total); backoff is 1s then capped at 2s."""
        mock_request.side_effect = requests.exceptions.ConnectTimeout("down")

        with patch.object(client, "_get_headers", return_value={}):
            with pytest.raises(requests.exceptions.ConnectTimeout):
                client._make_request("https://test.url")

        assert mock_request.call_count == 3
        assert [c.args[0] for c in mock_sleep.call_args_list] == [1.0, 2.0]

    @patch.object(AppleSearchAdsClient, "_retry_sleep")
    @patch("requests.request")
    def test_retries_zero_disables_retry(self, mock_request, mock_sleep, mock_credentials):
        """retries=0 restores fail-fast on the first transient error."""
        mock_request.side_effect = requests.exceptions.ConnectTimeout("down")

        client = AppleSearchAdsClient(**mock_credentials, retries=0)
        with patch.object(client, "_get_headers", return_value={}):
            with pytest.raises(requests.exceptions.ConnectTimeout):
                client._make_request("https://test.url")

        assert mock_request.call_count == 1
        mock_sleep.assert_not_called()

    def test_default_retries_is_two(self, client):
        assert client.retries == 2

    @patch.object(AppleSearchAdsClient, "_retry_sleep")
    @patch("requests.request")
    def test_retry_budget_is_shared_across_report_pages(self, mock_request, mock_sleep, client):
        """One paged fetch gets ONE retry budget, not a fresh budget per page —
        a systemically-down Apple must not multiply retries by page count."""
        client.org_id = "123"

        def page_response(rows_start, rows_count, total):
            resp = Mock()
            resp.json.return_value = {
                "result": {
                    "rows": [{"metadata": {"id": rows_start + i}} for i in range(rows_count)]
                },
                "pagination": {"offset": rows_start, "pageSize": 1000, "totalCount": total},
            }
            return resp

        # Page 1 consumes both retries, then succeeds; page 2's first transient
        # failure finds an empty budget and must raise immediately.
        mock_request.side_effect = [
            requests.exceptions.ConnectTimeout("blip"),
            requests.exceptions.ConnectTimeout("blip"),
            page_response(0, 1000, 1500),
            requests.exceptions.ConnectTimeout("blip"),
        ]

        with patch.object(client, "_get_headers", return_value={}):
            with pytest.raises(requests.exceptions.ConnectTimeout):
                client.get_campaign_report_raw("2024-01-01", "2024-01-31")

        assert mock_request.call_count == 4

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_all_organizations(self, mock_make_request, client):
        """ACL plus one ad-account lookup per account, returned in the v5 shape."""
        mock_make_request.side_effect = [
            acl_response((123, "Test Org 1", 123), (456, "Test Org 2", 123)),
            ad_account_response(),
            ad_account_response(currency="EUR"),
        ]

        orgs = client.get_all_organizations()

        assert len(orgs) == 2
        assert orgs[0]["orgId"] == 123
        assert orgs[1]["orgName"] == "Test Org 2"
        assert orgs[1]["currency"] == "EUR"
        assert mock_make_request.call_args_list[0] == (
            (f"{client.BASE_URL}/acls",),
            {"include_org_context": False},
        )
        assert mock_make_request.call_args_list[2].args == (f"{client.BASE_URL}/ad-accounts/456",)

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_all_organizations_empty_response(self, mock_make_request, client):
        """Test fetching organizations with empty response."""
        mock_make_request.return_value = {}

        orgs = client.get_all_organizations()

        assert orgs == []

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_app_details(self, mock_make_request, client):
        """Test fetching app details."""
        client.org_id = "test_org_id"
        mock_make_request.return_value = {
            "result": {
                "id": "284815942",
                "appName": "Trip Trek",
                "artistName": "Trip Trek",
                "primaryLanguage": "en-US",
                "primaryGenre": ">Mobile Software Applications>Utilities",
                "secondaryGenre": ">Mobile Software Applications>Reference",
                "deviceClasses": ["IPHONE", "IPAD"],
                "iconPictureUrl": "https://example.com/icon.png",
                "isPreorder": False,
                "availableStorefronts": ["US"],
            }
        }

        details = client.get_app_details("284815942")

        assert details["adamId"] == 284815942
        assert details["isPreOrder"] == "false"
        assert details["appName"] == "Trip Trek"
        assert details["artistName"] == "Trip Trek"
        assert details["primaryLanguage"] == "en-US"
        assert "IPHONE" in details["deviceClasses"]
        assert "US" in details["availableStorefronts"]
        mock_make_request.assert_called_once_with(f"{client.BASE_URL}/apps/284815942", method="GET")

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_app_details_empty_response(self, mock_make_request, client):
        """Test fetching app details with empty response."""
        client.org_id = "test_org_id"
        mock_make_request.return_value = {}

        details = client.get_app_details("999999999")

        assert details == {}

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
        mock_make_request.return_value = acl_response()

        with pytest.raises(ValueError) as exc_info:
            client._get_org_id()

        assert "No organization found" in str(exc_info.value)

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_org_id_success(self, mock_make_request, client):
        """Test successful _get_org_id call."""
        # Clear org_id to force fetch
        client.org_id = None

        mock_make_request.return_value = acl_response((789, "Test Org", 789))

        org_id = client._get_org_id()

        assert org_id == "789"
        assert client.org_id == "789"

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_campaigns(self, mock_make_request, client):
        """Test fetching campaigns."""
        client.org_id = "123"
        mock_make_request.return_value = query_response(
            [
                {"id": 1, "name": "Campaign 1", "status": "ENABLED"},
                {"id": 2, "name": "Campaign 2", "status": "PAUSED"},
            ]
        )

        campaigns = client.get_campaigns()

        assert len(campaigns) == 2
        assert campaigns[0]["fetched_org_id"] == "123"
        assert campaigns[1]["name"] == "Campaign 2"
        assert mock_make_request.call_args.args == (f"{client.BASE_URL}/campaigns/query",)
        assert mock_make_request.call_args.kwargs["method"] == "POST"

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_campaigns_with_supply_sources(self, mock_make_request, client):
        """Campaigns carry v5 supplySources derived from v1 targeting.supplyPlacement."""
        client.org_id = "123"
        mock_make_request.return_value = query_response(
            [
                v1_campaign(1, "Search Campaign", ["APPSTORE_SEARCH_RESULTS"]),
                v1_campaign(2, "Today Tab Campaign", ["APPSTORE_TODAY_TAB"]),
            ]
        )

        campaigns = client.get_campaigns()

        assert len(campaigns) == 2
        assert campaigns[0]["supplySources"] == ["APPSTORE_SEARCH_RESULTS"]
        assert campaigns[1]["supplySources"] == ["APPSTORE_TODAY_TAB"]

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_campaigns_filter_by_supply_source(self, mock_make_request, client):
        """Test filtering campaigns by supply_source."""
        client.org_id = "123"
        mock_make_request.return_value = query_response(
            [
                v1_campaign(1, "Search Campaign", ["APPSTORE_SEARCH_RESULTS"]),
                v1_campaign(2, "Today Tab Campaign", ["APPSTORE_TODAY_TAB"]),
                v1_campaign(3, "Search Tab Campaign", ["APPSTORE_SEARCH_TAB"]),
            ]
        )

        # Filter for search results campaigns only
        campaigns = client.get_campaigns(supply_source="APPSTORE_SEARCH_RESULTS")

        assert len(campaigns) == 1
        assert campaigns[0]["name"] == "Search Campaign"

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_campaigns_filter_uses_v5_product_pages_name(self, mock_make_request, client):
        """v1 renamed APPSTORE_PRODUCT_PAGES_BROWSE; the v5 filter value must still match."""
        client.org_id = "123"
        mock_make_request.return_value = query_response(
            [v1_campaign(4, "YMAL Campaign", ["APPSTORE_PRODUCT_PAGES"])]
        )

        campaigns = client.get_campaigns(supply_source="APPSTORE_PRODUCT_PAGES_BROWSE")

        assert [c["name"] for c in campaigns] == ["YMAL Campaign"]

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_campaigns_filter_no_match(self, mock_make_request, client):
        """Test filtering campaigns when no campaigns match the supply_source."""
        client.org_id = "123"
        mock_make_request.return_value = query_response(
            [v1_campaign(1, "Search Campaign", ["APPSTORE_SEARCH_RESULTS"])]
        )

        campaigns = client.get_campaigns(supply_source="APPSTORE_TODAY_TAB")

        assert len(campaigns) == 0

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_adgroups(self, mock_make_request, client):
        """Test fetching ad groups for a campaign."""
        client.org_id = "123"
        mock_make_request.return_value = query_response(
            [
                {"id": 1, "name": "Ad Group 1", "status": "ENABLED"},
                {"id": 2, "name": "Ad Group 2", "status": "PAUSED"},
            ]
        )

        adgroups = client.get_adgroups("campaign123")

        assert len(adgroups) == 2
        assert adgroups[0]["name"] == "Ad Group 1"
        assert adgroups[1]["status"] == "PAUSED"
        call_args = mock_make_request.call_args
        assert call_args.args == (f"{client.BASE_URL}/adgroups/query",)
        assert call_args.kwargs["json_data"]["filters"] == [
            {"field": "campaignId", "operator": "EQUALS", "value": "campaign123"}
        ]

    @patch.object(AppleSearchAdsClient, "_get_org_id")
    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_adgroups_no_org_id(self, mock_make_request, mock_get_org_id, client):
        """Test fetching ad groups when org_id is not set."""
        client.org_id = None
        mock_make_request.return_value = query_response([])

        adgroups = client.get_adgroups("campaign123")

        mock_get_org_id.assert_called_once()
        assert adgroups == []

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_keywords(self, mock_make_request, client):
        """Test fetching keywords for a campaign."""
        client.org_id = "123"
        mock_make_request.return_value = query_response(
            [
                {
                    "id": 542370642,
                    "adGroupId": 427916203,
                    "text": "targeting keyword example 1",
                    "status": "PAUSED",
                    "matchType": "BROAD",
                    "bid": {"amount": "100", "currency": "USD"},
                    "modificationTime": "2024-04-08T21:03:02.216",
                    "deleted": False,
                },
                {
                    "id": 542370643,
                    "adGroupId": 427916203,
                    "text": "targeting keyword example 2",
                    "status": "ENABLED",
                    "matchType": "EXACT",
                    "bid": {"amount": "50", "currency": "USD"},
                    "modificationTime": "2024-04-08T17:53:10.899",
                    "deleted": False,
                },
            ]
        )

        keywords = client.get_keywords("campaign123")

        assert len(keywords) == 2
        assert keywords[0]["text"] == "targeting keyword example 1"
        assert keywords[0]["status"] == "PAUSED"
        assert keywords[0]["matchType"] == "BROAD"
        assert keywords[0]["bidAmount"] == {"amount": "100", "currency": "USD"}
        assert keywords[1]["status"] == "ACTIVE"
        assert keywords[1]["matchType"] == "EXACT"
        mock_make_request.assert_called_once()
        call_args = mock_make_request.call_args
        assert call_args[0][0] == f"{client.BASE_URL}/keywords/query"
        assert call_args[1]["method"] == "POST"
        filters = call_args[1]["json_data"]["filters"]
        assert {"field": "campaignId", "operator": "EQUALS", "value": "campaign123"} in filters
        # Should filter out deleted by default
        assert {"field": "deleted", "operator": "EQUALS", "value": "false"} in filters

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_keywords_with_adgroup_filter(self, mock_make_request, client):
        """Test fetching keywords filtered by ad group."""
        client.org_id = "123"
        mock_make_request.return_value = query_response([])

        client.get_keywords("campaign123", adgroup_id="adgroup456")

        filters = mock_make_request.call_args[1]["json_data"]["filters"]
        assert {"field": "adGroupId", "operator": "EQUALS", "value": "adgroup456"} in filters

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_keywords_include_deleted(self, mock_make_request, client):
        """Test fetching keywords including deleted ones."""
        client.org_id = "123"
        mock_make_request.return_value = query_response([])

        client.get_keywords("campaign123", include_deleted=True)

        call_args = mock_make_request.call_args
        json_data = call_args[1]["json_data"]
        # Should not have conditions when include_deleted=True and no adgroup filter
        assert "conditions" not in json_data or len(json_data.get("conditions", [])) == 0

    @patch.object(AppleSearchAdsClient, "_get_org_id")
    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_keywords_no_org_id(self, mock_make_request, mock_get_org_id, client):
        """Test fetching keywords when org_id is not set."""
        client.org_id = None
        mock_make_request.return_value = query_response([])

        client.get_keywords("campaign123")

        mock_get_org_id.assert_called_once()

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_update_keyword_bid_success(self, mock_make_request, client):
        """PUT /keywords/{id} with a bid body; returns the v5-compat keyword."""
        client.org_id = "123"
        mock_make_request.return_value = {
            "result": {
                "id": 542370642,
                "adGroupId": 427916203,
                "text": "targeting keyword example",
                "status": "ENABLED",
                "matchType": "BROAD",
                "bid": {"amount": "1.50", "currency": "USD"},
                "modificationTime": "2024-04-08T21:03:02.216",
                "deleted": False,
            }
        }

        result = client.update_keyword_bid(
            campaign_id="campaign123",
            adgroup_id="adgroup456",
            keyword_id="keyword789",
            bid_amount=1.50,
            currency="USD",
        )

        assert result["id"] == 542370642
        assert result["status"] == "ACTIVE"
        assert result["bidAmount"]["amount"] == "1.50"
        assert result["bidAmount"]["currency"] == "USD"
        mock_make_request.assert_called_once()
        call_args = mock_make_request.call_args
        assert call_args[0][0] == f"{client.BASE_URL}/keywords/keyword789"
        assert call_args[1]["method"] == "PUT"
        assert call_args[1]["json_data"] == {"bid": {"amount": "1.5", "currency": "USD"}}

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_update_keyword_bid_string_amount(self, mock_make_request, client):
        """Test keyword bid update with string bid amount."""
        client.org_id = "123"
        mock_make_request.return_value = {
            "result": {"id": 123, "bid": {"amount": "2.00", "currency": "EUR"}}
        }

        result = client.update_keyword_bid(
            campaign_id="c1",
            adgroup_id="ag1",
            keyword_id="kw1",
            bid_amount="2.00",
            currency="EUR",
        )

        assert result["bidAmount"]["amount"] == "2.00"
        call_args = mock_make_request.call_args
        assert call_args[1]["json_data"]["bid"]["amount"] == "2.0"

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_update_keyword_bid_currency_normalization(self, mock_make_request, client):
        """Test currency is normalized to uppercase."""
        client.org_id = "123"
        mock_make_request.return_value = {"result": {"id": 123}}

        client.update_keyword_bid(
            campaign_id="c1",
            adgroup_id="ag1",
            keyword_id="kw1",
            bid_amount=1.0,
            currency="usd",
        )

        call_args = mock_make_request.call_args
        assert call_args[1]["json_data"]["bid"]["currency"] == "USD"

    def test_update_keyword_bid_negative_amount(self, client):
        """Test that negative bid amount raises ValueError."""
        client.org_id = "123"

        with pytest.raises(ValueError) as exc_info:
            client.update_keyword_bid(
                campaign_id="c1",
                adgroup_id="ag1",
                keyword_id="kw1",
                bid_amount=-1.50,
                currency="USD",
            )

        assert "must be positive" in str(exc_info.value)

    def test_update_keyword_bid_zero_amount(self, client):
        """Test that zero bid amount raises ValueError."""
        client.org_id = "123"

        with pytest.raises(ValueError) as exc_info:
            client.update_keyword_bid(
                campaign_id="c1",
                adgroup_id="ag1",
                keyword_id="kw1",
                bid_amount=0,
                currency="USD",
            )

        assert "must be positive" in str(exc_info.value)

    def test_update_keyword_bid_invalid_amount(self, client):
        """Test that non-numeric bid amount raises ValueError."""
        client.org_id = "123"

        with pytest.raises(ValueError) as exc_info:
            client.update_keyword_bid(
                campaign_id="c1",
                adgroup_id="ag1",
                keyword_id="kw1",
                bid_amount="invalid",
                currency="USD",
            )

        assert "Invalid bid_amount" in str(exc_info.value)

    def test_update_keyword_bid_invalid_currency_length(self, client):
        """Test that currency with wrong length raises ValueError."""
        client.org_id = "123"

        with pytest.raises(ValueError) as exc_info:
            client.update_keyword_bid(
                campaign_id="c1",
                adgroup_id="ag1",
                keyword_id="kw1",
                bid_amount=1.50,
                currency="US",
            )

        assert "Invalid currency" in str(exc_info.value)

    def test_update_keyword_bid_invalid_currency_format(self, client):
        """Test that currency with non-alpha characters raises ValueError."""
        client.org_id = "123"

        with pytest.raises(ValueError) as exc_info:
            client.update_keyword_bid(
                campaign_id="c1",
                adgroup_id="ag1",
                keyword_id="kw1",
                bid_amount=1.50,
                currency="US1",
            )

        assert "Invalid currency" in str(exc_info.value)

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_update_keyword_bid_empty_response(self, mock_make_request, client):
        """Test keyword bid update with empty response."""
        client.org_id = "123"
        mock_make_request.return_value = {}

        result = client.update_keyword_bid(
            campaign_id="c1",
            adgroup_id="ag1",
            keyword_id="kw1",
            bid_amount=1.50,
            currency="USD",
        )

        assert result == {}

    @patch.object(AppleSearchAdsClient, "_get_org_id")
    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_update_keyword_bid_no_org_id(self, mock_make_request, mock_get_org_id, client):
        """Test keyword bid update when org_id is not set."""
        client.org_id = None
        mock_make_request.return_value = {"result": {"id": 123}}

        client.update_keyword_bid(
            campaign_id="c1",
            adgroup_id="ag1",
            keyword_id="kw1",
            bid_amount=1.50,
            currency="USD",
        )

        mock_get_org_id.assert_called_once()

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_update_keyword_bid_http_error(self, mock_make_request, client):
        """Test keyword bid update with HTTP error."""
        client.org_id = "123"
        mock_make_request.side_effect = requests.exceptions.HTTPError("404 Not Found")

        with pytest.raises(requests.exceptions.HTTPError):
            client.update_keyword_bid(
                campaign_id="c1",
                adgroup_id="ag1",
                keyword_id="kw1",
                bid_amount=1.50,
                currency="USD",
            )

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
        mock_make_request.return_value = report_response(
            [
                {
                    "metadata": {
                        "id": 1,
                        "name": "Test Campaign",
                        "status": "ENABLED",
                        "promotedObject": {"name": "Test App"},
                        "promotedObjectId": "123456",
                    },
                    "granularMetrics": [
                        modern_day_metrics(
                            date="2024-01-01",
                            impressions=1000,
                            taps=50,
                            totalInstalls=10,
                            totalNewDownloads=6,
                            totalRedownloads=4,
                            latOnInstalls=8,
                            latOffInstalls=2,
                            localSpend={"amount": "100.00", "currency": "USD"},
                            cpm={"amount": "5.00", "currency": "USD"},
                        )
                    ],
                }
            ]
        )

        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 7)

        df = client.get_campaign_report(start_date, end_date)

        assert not df.empty
        assert len(df) == 1
        assert df.iloc[0]["campaign_name"] == "Test Campaign"
        assert df.iloc[0]["app_name"] == "Test App"
        assert df.iloc[0]["spend"] == Decimal("100.00")
        assert df.iloc[0]["adam_id"] == 123456
        # Verify new metrics fields
        assert df.iloc[0]["new_downloads"] == 6
        assert df.iloc[0]["redownloads"] == 4
        assert df.iloc[0]["lat_on_installs"] == 8
        assert df.iloc[0]["lat_off_installs"] == 2
        assert df.iloc[0]["avg_cpm"] == Decimal("5.00")
        assert mock_make_request.call_args.args == (
            f"{client.BASE_URL}/reports/apps/campaigns/query",
        )
        time_range = mock_make_request.call_args.kwargs["json_data"]["timeRange"]
        assert time_range == {"start": "2024-01-01", "end": "2024-01-07", "granularity": "DAILY"}

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
    @patch.object(AppleSearchAdsClient, "get_campaign_report")
    def test_get_daily_spend_by_app(self, mock_get_report, mock_get_orgs, client):
        """Spend is attributed by the report's adam_id; no campaign lookup is needed."""
        mock_get_orgs.return_value = [{"orgId": "123", "orgName": "Test Org"}]

        mock_df = pd.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-01", "2024-01-02"],
                "campaign_id": [1, 2, 1],
                "adam_id": [123456, 789012, 123456],
                "spend": [100.0, 50.0, 75.0],
                "impressions": [1000, 500, 750],
                "taps": [50, 25, 40],
                "installs": [10, 5, 8],
            }
        )
        mock_get_report.return_value = mock_df

        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 2)

        with patch.object(client, "get_campaigns_with_details") as mock_details:
            result = client.get_daily_spend_by_app(start_date, end_date)

        mock_details.assert_not_called()
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
        mock_make_request.return_value = report_response(
            [
                {
                    "metadata": {"id": 1},
                    "granularMetrics": [
                        modern_day_metrics(
                            date="2024-01-01",
                            impressions=100,
                            taps=10,
                            totalInstalls=1,
                            localSpend={"amount": "10.00", "currency": "USD"},
                        )
                    ],
                }
            ]
        )

        # Test with string dates
        df = client.get_campaign_report("2024-01-01", "2024-01-07")

        assert not df.empty
        assert len(df) == 1

    @patch.object(AppleSearchAdsClient, "_get_org_id")
    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_campaign_report_no_org_id(self, mock_make_request, mock_get_org_id, client):
        """Test campaign report when org_id needs to be fetched."""
        client.org_id = None
        mock_make_request.return_value = report_response([])

        df = client.get_campaign_report(datetime(2024, 1, 1), datetime(2024, 1, 7))

        mock_get_org_id.assert_called_once()
        assert df.empty

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_campaigns_with_org_id_param_and_finally(self, mock_make_request, client):
        """Test get_campaigns with org_id parameter and finally block."""
        client.org_id = "original_org"
        mock_make_request.return_value = query_response([{"id": 1, "name": "Campaign"}])

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
        mock_make_request.return_value = query_response([])

        campaigns = client.get_campaigns(org_id=None)

        mock_get_org_id.assert_called_once()
        assert campaigns == []

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_campaign_report_empty_rows(self, mock_make_request, client):
        """Test campaign report with empty rows."""
        client.org_id = "123"
        mock_make_request.return_value = report_response([])

        df = client.get_campaign_report(datetime(2024, 1, 1), datetime(2024, 1, 7))

        assert df.empty

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_campaign_report_with_null_nested_fields(self, mock_make_request, client):
        """Test campaign report handles None nested fields with strict=False (v2 zero-fill)."""
        client.org_id = "123"
        client.strict = False
        mock_make_request.return_value = report_response(
            [
                {
                    "metadata": {"id": 1, "name": "Test Campaign"},
                    "granularMetrics": [
                        {
                            "date": "2024-01-01",
                            "impressions": 100,
                            "taps": 10,
                            "totalInstalls": 2,
                            "localSpend": None,
                            "totalAvgCPI": None,
                            "cpt": None,
                        }
                    ],
                }
            ]
        )

        df = client.get_campaign_report("2024-01-01", "2024-01-07")

        assert not df.empty
        assert len(df) == 1
        assert df.iloc[0]["spend"] == 0
        assert df.iloc[0]["avg_cpa"] == 0
        assert df.iloc[0]["avg_cpt"] == 0
        assert df.iloc[0]["currency"] == "USD"

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
    @patch.object(AppleSearchAdsClient, "get_campaign_report")
    def test_get_daily_spend_by_app_no_app_mapping(self, mock_report, mock_orgs, client):
        """Report rows without a promoted app (adam_id None) are not attributed."""
        mock_orgs.return_value = [{"orgId": "123"}]
        mock_report.return_value = pd.DataFrame(
            {
                "campaign_id": [1, 2],
                "adam_id": [None, None],
                "date": ["2024-01-01", "2024-01-01"],
                "spend": [100.0, 50.0],
            }
        )

        result = client.get_daily_spend_by_app(datetime(2024, 1, 1), datetime(2024, 1, 2))

        assert result.empty

    @patch.object(AppleSearchAdsClient, "get_campaign_report")
    def test_get_daily_spend_by_app_single_org(self, mock_report, client):
        """Test get_daily_spend_by_app with fetch_all_orgs=False."""
        client.org_id = "123"
        mock_report.return_value = pd.DataFrame(
            {
                "campaign_id": [1],
                "adam_id": [999],
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
    @patch.object(AppleSearchAdsClient, "get_campaign_report")
    def test_get_daily_spend_by_app_with_exception(self, mock_report, mock_orgs, client):
        """Test get_daily_spend_by_app with exception during report fetching."""
        mock_orgs.return_value = [{"orgId": "123"}, {"orgId": "456"}]

        # First org succeeds, second fails
        mock_report.side_effect = [
            pd.DataFrame(
                {
                    "campaign_id": [1],
                    "adam_id": [999],
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
    @patch.object(AppleSearchAdsClient, "get_campaign_report")
    def test_get_daily_spend_by_app_string_dates(self, mock_report, mock_orgs, client):
        """Test get_daily_spend_by_app with string dates in filtering."""
        mock_orgs.return_value = [{"orgId": "123"}]
        client.org_id = "123"

        # Return data outside the date range to test filtering
        mock_report.return_value = pd.DataFrame(
            {
                "campaign_id": [1, 1, 1],
                "adam_id": [999, 999, 999],
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

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_adgroup_report(self, mock_make_request, client):
        """Test fetching ad group report."""
        client.org_id = "123"
        mock_make_request.return_value = report_response(
            [
                {
                    "metadata": {
                        "id": "ag1",
                        "campaignId": 123,
                        "name": "Test Ad Group",
                        "status": "ENABLED",
                    },
                    "granularMetrics": [
                        modern_day_metrics(
                            date="2024-01-01",
                            impressions=500,
                            taps=25,
                            totalInstalls=5,
                            localSpend={"amount": "50.00", "currency": "USD"},
                        )
                    ],
                }
            ]
        )

        df = client.get_adgroup_report("campaign123", "2024-01-01", "2024-01-07")

        assert not df.empty
        assert len(df) == 1
        assert df.iloc[0]["adgroup_name"] == "Test Ad Group"
        assert df.iloc[0]["adgroup_id"] == "ag1"
        assert df.iloc[0]["adgroup_status"] == "ENABLED"
        assert df.iloc[0]["campaign_id"] == "campaign123"
        assert df.iloc[0]["spend"] == Decimal("50.00")
        call = mock_make_request.call_args
        assert call.args == (f"{client.BASE_URL}/reports/apps/adgroups/query",)
        assert call.kwargs["json_data"]["filters"] == [
            {"field": "campaignId", "operator": "EQUALS", "value": "campaign123"}
        ]

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_adgroup_report_empty(self, mock_make_request, client):
        """Test ad group report with empty response."""
        client.org_id = "123"
        mock_make_request.return_value = report_response([])

        df = client.get_adgroup_report("campaign123", "2024-01-01", "2024-01-07")

        assert df.empty

    @patch.object(AppleSearchAdsClient, "_get_org_id")
    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_adgroup_report_no_org_id(self, mock_make_request, mock_get_org_id, client):
        """Test ad group report when org_id needs to be fetched."""
        client.org_id = None
        mock_make_request.return_value = report_response([])

        df = client.get_adgroup_report("campaign123", "2024-01-01", "2024-01-07")

        mock_get_org_id.assert_called_once()
        assert df.empty

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_keyword_report(self, mock_make_request, client):
        """Test fetching keyword report."""
        client.org_id = "123"
        mock_make_request.return_value = report_response(
            [
                {
                    "metadata": {
                        "id": "kw1",
                        "text": "test keyword",
                        "status": "ENABLED",
                        "matchType": "EXACT",
                        "adGroupId": "ag1",
                        "bid": {"amount": "1.50", "currency": "USD"},
                    },
                    "granularMetrics": [
                        modern_day_metrics(
                            date="2024-01-01",
                            impressions=100,
                            taps=10,
                            totalInstalls=2,
                            localSpend={"amount": "15.00", "currency": "USD"},
                        )
                    ],
                }
            ]
        )

        df = client.get_keyword_report("campaign123", "2024-01-01", "2024-01-07")

        assert not df.empty
        assert len(df) == 1
        assert df.iloc[0]["keyword"] == "test keyword"
        assert df.iloc[0]["keyword_id"] == "kw1"
        assert df.iloc[0]["keyword_status"] == "ACTIVE"
        assert df.iloc[0]["match_type"] == "EXACT"
        assert df.iloc[0]["bid_amount"] == 1.50
        assert df.iloc[0]["campaign_id"] == "campaign123"
        assert df.iloc[0]["adgroup_id"] == "ag1"
        assert df.iloc[0]["spend"] == Decimal("15.00")
        assert mock_make_request.call_args.args == (
            f"{client.BASE_URL}/reports/apps/keywords/query",
        )

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_keyword_report_idle_day_is_zero_row(self, mock_make_request, client):
        """A date-only granular entry yields v5's explicit zero row, not an error or a gap."""
        client.org_id = "123"
        mock_make_request.return_value = report_response(
            [
                {
                    "metadata": {"id": "kw1", "text": "kw", "status": "ENABLED"},
                    "totalMetrics": modern_day_metrics(
                        impressions=100, localSpend={"amount": "15.00", "currency": "USD"}
                    ),
                    "granularMetrics": [
                        modern_day_metrics(
                            date="2024-01-01",
                            impressions=100,
                            localSpend={"amount": "15.00", "currency": "USD"},
                        ),
                        {"date": "2024-01-02"},
                    ],
                }
            ]
        )

        df = client.get_keyword_report("campaign123", "2024-01-01", "2024-01-02")

        assert list(df["date"]) == ["2024-01-01", "2024-01-02"]
        idle = df.iloc[1]
        assert idle["spend"] == Decimal("0")
        assert idle["impressions"] == 0
        assert idle["currency"] == "USD"
        assert idle["ttr"] is None

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_keyword_report_no_bid_amount(self, mock_make_request, client):
        """Test keyword report when bid is missing."""
        client.org_id = "123"
        mock_make_request.return_value = report_response(
            [
                {
                    "metadata": {
                        "id": "kw1",
                        "text": "no bid keyword",
                        "status": "ENABLED",
                        "matchType": "EXACT",
                        "adGroupId": "ag1",
                    },
                    "granularMetrics": [
                        modern_day_metrics(
                            date="2024-01-01",
                            impressions=100,
                            taps=10,
                            totalInstalls=2,
                            localSpend={"amount": "15.00", "currency": "USD"},
                        )
                    ],
                }
            ]
        )

        df = client.get_keyword_report("campaign123", "2024-01-01", "2024-01-07")

        assert not df.empty
        assert df.iloc[0]["bid_amount"] == 0

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_keyword_report_empty(self, mock_make_request, client):
        """Test keyword report with empty response."""
        client.org_id = "123"
        mock_make_request.return_value = report_response([])

        df = client.get_keyword_report("campaign123", "2024-01-01", "2024-01-07")

        assert df.empty

    @patch.object(AppleSearchAdsClient, "_get_org_id")
    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_keyword_report_no_org_id(self, mock_make_request, mock_get_org_id, client):
        """Test keyword report when org_id needs to be fetched."""
        client.org_id = None
        mock_make_request.return_value = report_response([])

        df = client.get_keyword_report("campaign123", "2024-01-01", "2024-01-07")

        mock_get_org_id.assert_called_once()
        assert df.empty

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_search_term_report(self, mock_make_request, client):
        """Search term rows carry only totalMetrics; dated by the report start."""
        client.org_id = "123"
        mock_make_request.return_value = report_response(
            [
                {
                    "metadata": {
                        "keyword": {"id": "kw1", "text": "test keyword", "matchType": "EXACT"},
                        "searchTermText": "actual search term",
                        "searchTermSource": "TARGETED",
                        "adGroupId": "ag1",
                    },
                    "totalMetrics": modern_day_metrics(
                        impressions=100,
                        taps=10,
                        totalInstalls=2,
                        localSpend={"amount": "15.00", "currency": "USD"},
                    ),
                },
                {
                    "metadata": {
                        "keyword": {"id": "kw1", "text": "test keyword", "matchType": "EXACT"},
                        "searchTermText": None,
                        "searchTermSource": "TARGETED",
                        "adGroupId": "ag1",
                    },
                    "totalMetrics": modern_day_metrics(impressions=3),
                },
            ]
        )

        df = client.get_search_term_report("campaign123", "2024-01-01", "2024-01-07")

        assert not df.empty
        assert len(df) == 2
        assert df.iloc[0]["date"] == "2024-01-01"
        assert df.iloc[0]["search_term"] == "actual search term"
        assert df.iloc[0]["search_term_source"] == "TARGETED"
        assert df.iloc[0]["keyword"] == "test keyword"
        assert df.iloc[0]["keyword_id"] == "kw1"
        assert df.iloc[0]["match_type"] == "EXACT"
        assert df.iloc[0]["campaign_id"] == "campaign123"
        assert df.iloc[0]["adgroup_id"] == "ag1"
        assert df.iloc[0]["spend"] == Decimal("15.00")
        assert not df.iloc[0]["is_low_volume"]
        assert df.iloc[1]["is_low_volume"]
        assert df.iloc[1]["search_term"] == "(Low volume terms)"
        call = mock_make_request.call_args
        assert call.args == (f"{client.BASE_URL}/reports/apps/searchterms/query",)
        assert call.kwargs["json_data"]["timeRange"]["timeZone"] == "ORTZ"

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_search_term_report_empty(self, mock_make_request, client):
        """Test search term report with empty response."""
        client.org_id = "123"
        mock_make_request.return_value = report_response([])

        df = client.get_search_term_report("campaign123", "2024-01-01", "2024-01-07")

        assert df.empty

    @patch.object(AppleSearchAdsClient, "_get_org_id")
    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_search_term_report_no_org_id(self, mock_make_request, mock_get_org_id, client):
        """Test search term report when org_id needs to be fetched."""
        client.org_id = None
        mock_make_request.return_value = report_response([])

        df = client.get_search_term_report("campaign123", "2024-01-01", "2024-01-07")

        mock_get_org_id.assert_called_once()
        assert df.empty

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_adgroup_search_term_report(self, mock_make_request, client):
        """Test fetching ad group search term report."""
        client.org_id = "123"
        mock_make_request.return_value = report_response(
            [
                {
                    "metadata": {
                        "keyword": {"id": "kw1", "text": "test keyword", "matchType": "BROAD"},
                        "searchTermText": "adgroup search term",
                        "searchTermSource": "AUTO",
                        "adGroupId": "ag1",
                    },
                    "totalMetrics": modern_day_metrics(
                        impressions=50,
                        taps=5,
                        totalInstalls=1,
                        localSpend={"amount": "10.00", "currency": "USD"},
                    ),
                }
            ]
        )

        df = client.get_adgroup_search_term_report(
            "campaign123", "adgroup456", "2024-01-01", "2024-01-07"
        )

        assert not df.empty
        assert len(df) == 1
        assert df.iloc[0]["search_term"] == "adgroup search term"
        assert df.iloc[0]["search_term_source"] == "AUTO"
        assert df.iloc[0]["adgroup_id"] == "ag1"
        assert df.iloc[0]["spend"] == Decimal("10.00")
        filters = mock_make_request.call_args.kwargs["json_data"]["filters"]
        assert {"field": "adGroupId", "operator": "EQUALS", "value": "adgroup456"} in filters

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_adgroup_search_term_report_empty(self, mock_make_request, client):
        """Test ad group search term report with empty response."""
        client.org_id = "123"
        mock_make_request.return_value = report_response([])

        df = client.get_adgroup_search_term_report(
            "campaign123", "adgroup456", "2024-01-01", "2024-01-07"
        )

        assert df.empty

    @patch.object(AppleSearchAdsClient, "_get_org_id")
    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_adgroup_search_term_report_no_org_id(
        self, mock_make_request, mock_get_org_id, client
    ):
        """Test ad group search term report when org_id needs to be fetched."""
        client.org_id = None
        mock_make_request.return_value = report_response([])

        df = client.get_adgroup_search_term_report(
            "campaign123", "adgroup456", "2024-01-01", "2024-01-07"
        )

        mock_get_org_id.assert_called_once()
        assert df.empty

    def test_create_impression_share_report_removed(self, client):
        """v1 has no queued custom reports; the v5 method fails loudly."""
        client.org_id = "123"
        with pytest.raises(NotImplementedError, match="get_impression_share_data"):
            client.create_impression_share_report(
                name="test_report", start_date="2024-01-20", end_date="2024-01-29"
            )

    def test_get_impression_share_report_removed(self, client):
        client.org_id = "123"
        with pytest.raises(NotImplementedError):
            client.get_impression_share_report(7615231)

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_impression_share_data(self, mock_make_request, client):
        """A synchronous query; v5 column names are added alongside v1's."""
        client.org_id = "123"
        mock_make_request.return_value = {
            "result": {
                "rows": [
                    {
                        "day": "2024-01-01",
                        "rank": 3,
                        "appName": "Test App",
                        "searchTerm": "test keyword",
                        "countryOrRegion": "US",
                        "promotedObjectId": 123,
                        "searchPopularity1to5": 3,
                        "lowImpressionShare": 0.1,
                        "highImpressionShare": 0.3,
                    }
                ]
            },
            "pagination": {"offset": 0, "pageSize": 1000, "totalCount": 1},
        }

        df = client.get_impression_share_data(
            name="test",
            start_date="2024-01-01",
            end_date="2024-01-07",
            countries=["US"],
            adam_ids=["123"],
            granularity="WEEKLY",
        )

        assert len(df) == 1
        row = df.iloc[0]
        assert row["adamId"] == 123
        assert row["searchPopularity"] == 3
        assert row["date"] == "2024-01-01"
        assert row["lowImpressionShare"] == 0.1
        call = mock_make_request.call_args
        assert call.args == (f"{client.BASE_URL}/insights/apps/impression-share/query",)
        body = call.kwargs["json_data"]
        assert body["filters"] == [
            {"field": "promotedObjectId", "operator": "IN", "value": ["123"]},
            {"field": "countryOrRegion", "operator": "IN", "value": ["US"]},
        ]
        assert body["timeRange"]["granularity"] == "WEEKLY_SUN_SAT"

    @patch.object(AppleSearchAdsClient, "_make_request")
    @patch.object(AppleSearchAdsClient, "get_campaigns")
    def test_get_impression_share_data_defaults_to_promoted_apps(
        self, mock_get_campaigns, mock_make_request, client
    ):
        """v1 requires an app filter; without adam_ids every promoted app is used."""
        client.org_id = "123"
        mock_get_campaigns.return_value = [{"adamId": 2}, {"adamId": 1}, {"adamId": 2}, {}]
        mock_make_request.return_value = {"result": {"rows": []}}

        client.get_impression_share_data(name="t", start_date="2024-01-01", end_date="2024-01-07")

        filters = mock_make_request.call_args.kwargs["json_data"]["filters"]
        assert filters[0]["value"] == ["1", "2"]

    def test_get_impression_share_data_rejects_non_utc(self, client):
        client.org_id = "123"
        with pytest.raises(ValueError, match="UTC"):
            client.get_impression_share_data(
                name="t", start_date="2024-01-01", end_date="2024-01-07", time_zone="ORTZ"
            )

    @patch.object(AppleSearchAdsClient, "_make_request")
    @patch.object(AppleSearchAdsClient, "get_campaigns")
    def test_get_impression_share_data_no_promoted_apps(
        self, mock_get_campaigns, mock_make_request, client
    ):
        """No apps to query -> empty DataFrame without calling the API."""
        client.org_id = "123"
        mock_get_campaigns.return_value = []

        df = client.get_impression_share_data(
            name="test", start_date="2024-01-01", end_date="2024-01-07"
        )

        assert df.empty
        mock_make_request.assert_not_called()


class TestV5Compat:
    """4.0 adds v5 field names to v1 objects so 3.x callers keep working.
    Each mapping mirrors one verified against live v5 objects on 2026-10-19."""

    @pytest.fixture
    def client(self):
        return AppleSearchAdsClient(
            client_id="test_client_id",
            team_id="test_team_id",
            key_id="test_key_id",
            private_key_content="test_key",
            org_id="123",
        )

    def test_campaign_core_aliases(self, client):
        campaign = client._compat_campaign(
            v1_campaign(
                7,
                "C",
                ["APPSTORE_SEARCH_RESULTS"],
                promotedObjectId="6760951765",
                adAccountId=29120,
                dailyBudget={"value": {"amount": "50", "currency": "USD"}},
                bidStrategy={"bidStrategyType": "MANUAL_CPT", "bid": {"amount": "1"}},
                systemStatus="RUNNING",
                systemStatusReasons=[],
            )
        )

        assert campaign["adamId"] == 6760951765
        assert campaign["orgId"] == 29120
        assert campaign["dailyBudgetAmount"] == {"amount": "50", "currency": "USD"}
        assert campaign["biddingStrategy"] == "MANUAL_CPT"
        assert campaign["servingStatus"] == "RUNNING"
        assert campaign["servingStateReasons"] is None
        assert campaign["targetCpa"] is None

    @pytest.mark.parametrize(
        "placements, channel",
        [
            (["APPSTORE_SEARCH_RESULTS"], "SEARCH"),
            (["APPSTORE_SEARCH_TAB"], "DISPLAY"),
            (["APPSTORE_TODAY_TAB"], "DISPLAY"),
            (["APPSTORE_PRODUCT_PAGES"], "DISPLAY"),
        ],
    )
    def test_campaign_ad_channel_type(self, client, placements, channel):
        campaign = client._compat_campaign(v1_campaign(1, "C", placements))
        assert campaign["adChannelType"] == channel

    def test_campaign_supply_source_uses_v5_product_pages_name(self, client):
        campaign = client._compat_campaign(v1_campaign(1, "C", ["APPSTORE_PRODUCT_PAGES"]))
        assert campaign["supplySources"] == ["APPSTORE_PRODUCT_PAGES_BROWSE"]

    def test_campaign_countries_sorted_like_v5(self, client):
        campaign = client._compat_campaign(
            v1_campaign(1, "C", [], targeting={"countryOrRegion": {"include": ["US", "DE", "AT"]}})
        )
        assert campaign["countriesOrRegions"] == ["AT", "DE", "US"]

    def test_campaign_target_cpa_only_for_max_conversions(self, client):
        bid = {"amount": "2.5", "currency": "USD"}
        max_conv = client._compat_campaign(
            v1_campaign(1, "C", [], bidStrategy={"bidStrategyType": "MAX_CONVERSIONS", "bid": bid})
        )
        manual = client._compat_campaign(
            v1_campaign(2, "C", [], bidStrategy={"bidStrategyType": "MANUAL_CPT", "bid": bid})
        )
        assert max_conv["targetCpa"] == bid
        assert manual["targetCpa"] is None

    def test_campaign_sapin_law_response(self, client):
        campaign = client._compat_campaign(
            v1_campaign(
                1,
                "C",
                [],
                regulationResponses=[
                    {"regulationType": "OTHER", "responseValue": "X"},
                    {
                        "regulationType": "CAMPAIGN_SAPIN_LAW",
                        "responseValue": "NOT_FRENCH_BUSINESS",
                    },
                ],
            )
        )
        assert campaign["sapinLawResponse"] == "NOT_FRENCH_BUSINESS"
        assert client._compat_campaign(v1_campaign(2, "C", []))["sapinLawResponse"] is None

    def test_paused_campaign_display_status_is_v5_paused(self, client):
        paused = client._compat_campaign(
            v1_campaign(1, "C", [], status="PAUSED", displayStatus="ON_HOLD")
        )
        enabled = client._compat_campaign(
            v1_campaign(2, "C", [], status="ENABLED", displayStatus="ON_HOLD")
        )
        assert paused["displayStatus"] == "PAUSED"
        assert enabled["displayStatus"] == "ON_HOLD"

    def test_aliases_never_clobber_v1_keys(self, client):
        campaign = client._compat_campaign(
            v1_campaign(1, "C", ["APPSTORE_TODAY_TAB"], adamId=42, adChannelType="SEARCH")
        )
        assert campaign["adamId"] == 42
        assert campaign["adChannelType"] == "SEARCH"

    def test_adgroup_aliases(self, client):
        adgroup = client._compat_adgroup(
            {
                "id": 1,
                "adAccountId": 29120,
                "pricingModel": "CPT",
                "bidStrategy": {"bidStrategyType": "MANUAL_CPT", "bid": {"amount": "1"}},
                "cpaCap": {"value": {"amount": "2", "currency": "USD"}},
                "systemStatus": "RUNNING",
            }
        )
        assert adgroup["pricingModel"] == "CPC"
        assert adgroup["cpaGoal"] == {"amount": "2", "currency": "USD"}
        assert adgroup["defaultBidAmount"] == {"amount": "1"}
        assert adgroup["orgId"] == 29120
        assert adgroup["servingStatus"] == "RUNNING"

    def test_adgroup_without_cpa_cap(self, client):
        adgroup = client._compat_adgroup({"id": 1, "pricingModel": "CPM"})
        assert adgroup["cpaGoal"] is None
        assert adgroup["pricingModel"] == "CPM"

    def test_keyword_aliases(self, client):
        enabled = client._compat_keyword({"status": "ENABLED", "bid": {"amount": "2"}})
        paused = client._compat_keyword({"status": "PAUSED"})
        assert enabled["status"] == "ACTIVE"
        assert enabled["bidAmount"] == {"amount": "2"}
        assert paused["status"] == "PAUSED"

    def test_app_aliases(self, client):
        assert client._compat_app({"id": "6760951765", "isPreorder": True}) == {
            "id": "6760951765",
            "isPreorder": True,
            "adamId": 6760951765,
            "isPreOrder": "true",
        }
        assert client._compat_app({"id": "1", "isPreorder": False})["isPreOrder"] == "false"
        assert client._compat_app({"id": "1"})["isPreOrder"] is None

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_all_organizations_v5_shape(self, mock_make_request, client):
        mock_make_request.side_effect = [
            acl_response((29120, "Bickster LLC", 29120), (555, "Sub Org", 29120)),
            ad_account_response(timezone="America/New_York"),
            ad_account_response(),
        ]

        parent, child = client.get_all_organizations()

        assert parent == {
            "orgId": 29120,
            "orgName": "Bickster LLC",
            "displayName": "Bickster LLC",
            "currency": "USD",
            "paymentModel": "PAYG",
            "roleNames": ["API Campaign Manager"],
            "parentOrgId": None,
            "timeZone": "America/New_York",
            "productFeatures": ["APPSTORE_APP_MANUAL"],
        }
        assert child["parentOrgId"] == 29120
        # Ad account lookups are scoped to the account being looked up, then restored.
        assert client.org_id == "123"

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_include_basic_false_drops_automated_accounts(self, mock_make_request, client):
        client.include_basic = False
        mock_make_request.side_effect = [
            acl_response((1, "Advanced", 1), (2, "Search Ads Basic", 1)),
            ad_account_response(),
            ad_account_response(features=("APPSTORE_APP_AUTOMATED",)),
        ]

        orgs = client.get_all_organizations()

        assert [o["orgName"] for o in orgs] == ["Advanced"]

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_basic_accounts_included_by_default(self, mock_make_request, client):
        mock_make_request.side_effect = [
            acl_response((1, "Advanced", 1), (2, "Search Ads Basic", 1)),
            ad_account_response(),
            ad_account_response(features=("APPSTORE_APP_AUTOMATED",)),
        ]

        orgs = client.get_all_organizations()

        assert [o["orgName"] for o in orgs] == ["Advanced", "Search Ads Basic"]

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_ad_account_details_cached_per_client(self, mock_make_request, client):
        mock_make_request.side_effect = [
            acl_response((1, "A", 1)),
            ad_account_response(),
            acl_response((1, "A", 1)),
        ]

        client.get_all_organizations()
        client.get_all_organizations()

        urls = [call.args[0] for call in mock_make_request.call_args_list]
        assert urls == [
            f"{client.BASE_URL}/acls",
            f"{client.BASE_URL}/ad-accounts/1",
            f"{client.BASE_URL}/acls",
        ]

    @patch.object(AppleSearchAdsClient, "get_all_organizations")
    @patch.object(AppleSearchAdsClient, "get_campaigns")
    def test_get_all_campaigns_skips_basic_accounts(self, mock_get_campaigns, mock_orgs, client):
        """v1 answers campaign queries on Basic accounts with 403; never ask."""
        mock_orgs.return_value = [
            {"orgId": 1, "orgName": "Advanced", "productFeatures": ["APPSTORE_APP_MANUAL"]},
            {"orgId": 2, "orgName": "Basic", "productFeatures": ["APPSTORE_APP_AUTOMATED"]},
        ]
        mock_get_campaigns.return_value = [{"id": 10}]

        campaigns = client.get_all_campaigns()

        assert len(campaigns) == 1
        mock_get_campaigns.assert_called_once_with(org_id="1", supply_source=None)

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_daily_spend_by_app_includes_basic_account_spend(self, mock_make_request, client):
        """Spend from a Basic account is attributed by promotedObjectId, end to end."""

        def campaign_report(campaign_id, adam_id, amount):
            return report_response(
                [
                    {
                        "metadata": {"id": campaign_id, "promotedObjectId": adam_id},
                        "granularMetrics": [
                            modern_day_metrics(
                                date="2026-10-12",
                                impressions=10,
                                taps=2,
                                totalInstalls=1,
                                localSpend={"amount": amount, "currency": "USD"},
                            )
                        ],
                    }
                ]
            )

        mock_make_request.side_effect = [
            acl_response((1, "Advanced", 1), (2, "Search Ads Basic", 1)),
            ad_account_response(),
            ad_account_response(features=("APPSTORE_APP_AUTOMATED",)),
            campaign_report(11, "1134998522", "100.50"),
            campaign_report(22, "1134998522", "10.25"),
        ]

        result = client.get_daily_spend_by_app("2026-10-12", "2026-10-12")

        assert len(result) == 1
        row = result.iloc[0]
        assert row["app_id"] == "1134998522"
        assert row["spend"] == Decimal("110.75")
        assert row["campaigns"] == 2
        contexts = [
            call.kwargs.get("json_data") is not None for call in mock_make_request.call_args_list
        ]
        assert contexts == [False, False, False, True, True]
