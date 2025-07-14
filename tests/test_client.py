"""
Unit tests for Apple Search Ads Client.
"""

import pytest
from unittest.mock import Mock, patch, mock_open
import pandas as pd
from datetime import datetime, timedelta

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
            "private_key_content": "-----BEGIN PRIVATE KEY-----\ntest_key\n-----END PRIVATE KEY-----"
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
    
    @patch.dict('os.environ', {
        'APPLE_SEARCH_ADS_CLIENT_ID': 'env_client_id',
        'APPLE_SEARCH_ADS_TEAM_ID': 'env_team_id',
        'APPLE_SEARCH_ADS_KEY_ID': 'env_key_id',
        'APPLE_SEARCH_ADS_PRIVATE_KEY_PATH': '/path/to/key.p8'
    })
    @patch('builtins.open', mock_open(read_data='test_key_content'))
    def test_client_initialization_with_env_vars(self):
        """Test client initialization with environment variables."""
        client = AppleSearchAdsClient()
        assert client.client_id == "env_client_id"
        assert client.team_id == "env_team_id"
        assert client.key_id == "env_key_id"
        assert client.private_key_path == "/path/to/key.p8"
    
    def test_client_initialization_missing_credentials(self):
        """Test client initialization with missing credentials."""
        with pytest.raises(ValueError) as exc_info:
            AppleSearchAdsClient(client_id="test")
        assert "Missing required credentials" in str(exc_info.value)
    
    def test_client_initialization_missing_private_key(self):
        """Test client initialization with missing private key."""
        with pytest.raises(ValueError) as exc_info:
            AppleSearchAdsClient(
                client_id="test",
                team_id="test",
                key_id="test"
            )
        assert "Missing private key" in str(exc_info.value)
    
    @patch('jwt.encode')
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
    
    @patch('requests.post')
    def test_get_access_token(self, mock_post, client):
        """Test access token retrieval."""
        mock_response = Mock()
        mock_response.json.return_value = {"access_token": "test_access_token"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        with patch.object(client, '_generate_client_secret', return_value='test_secret'):
            token = client._get_access_token()
        
        assert token == "test_access_token"
        assert client._token == "test_access_token"
        mock_post.assert_called_once_with(
            "https://appleid.apple.com/auth/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": "test_client_id",
                "client_secret": "test_secret",
                "scope": "searchadsorg"
            }
        )
    
    def test_get_headers_without_org(self, client):
        """Test header generation without organization context."""
        with patch.object(client, '_get_access_token', return_value='test_token'):
            headers = client._get_headers(include_org_context=False)
        
        assert headers == {
            "Authorization": "Bearer test_token",
            "Content-Type": "application/json"
        }
    
    def test_get_headers_with_org(self, client):
        """Test header generation with organization context."""
        client.org_id = "12345"
        with patch.object(client, '_get_access_token', return_value='test_token'):
            headers = client._get_headers(include_org_context=True)
        
        assert headers == {
            "Authorization": "Bearer test_token",
            "Content-Type": "application/json",
            "X-AP-Context": "orgId=12345"
        }
    
    @patch('requests.request')
    def test_make_request(self, mock_request, client):
        """Test making API requests."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": "test"}
        mock_response.raise_for_status = Mock()
        mock_request.return_value = mock_response
        
        with patch.object(client, '_get_headers', return_value={'test': 'header'}):
            result = client._make_request("https://test.url", method="GET")
        
        assert result == {"data": "test"}
        mock_request.assert_called_once_with(
            method="GET",
            url="https://test.url",
            headers={'test': 'header'},
            json=None,
            params=None
        )
    
    @patch.object(AppleSearchAdsClient, '_make_request')
    def test_get_all_organizations(self, mock_make_request, client):
        """Test fetching all organizations."""
        mock_make_request.return_value = {
            "data": [
                {"orgId": "123", "orgName": "Test Org 1"},
                {"orgId": "456", "orgName": "Test Org 2"}
            ]
        }
        
        orgs = client.get_all_organizations()
        
        assert len(orgs) == 2
        assert orgs[0]["orgId"] == "123"
        assert orgs[1]["orgName"] == "Test Org 2"
        mock_make_request.assert_called_once_with(
            f"{client.BASE_URL}/acls",
            include_org_context=False
        )
    
    @patch.object(AppleSearchAdsClient, '_make_request')
    def test_get_campaigns(self, mock_make_request, client):
        """Test fetching campaigns."""
        client.org_id = "123"
        mock_make_request.return_value = {
            "data": [
                {"id": "1", "name": "Campaign 1", "status": "ENABLED"},
                {"id": "2", "name": "Campaign 2", "status": "PAUSED"}
            ]
        }
        
        campaigns = client.get_campaigns()
        
        assert len(campaigns) == 2
        assert campaigns[0]["fetched_org_id"] == "123"
        assert campaigns[1]["name"] == "Campaign 2"
    
    @patch.object(AppleSearchAdsClient, '_make_request')
    def test_get_campaign_report(self, mock_make_request, client):
        """Test fetching campaign report."""
        client.org_id = "123"
        mock_make_request.return_value = {
            "data": {
                "reportingDataResponse": {
                    "row": [{
                        "metadata": {
                            "campaignId": "1",
                            "campaignName": "Test Campaign",
                            "adamId": "123456"
                        },
                        "granularity": [{
                            "date": "2024-01-01",
                            "impressions": 1000,
                            "taps": 50,
                            "totalInstalls": 10,
                            "localSpend": {"amount": 100.0, "currency": "USD"}
                        }]
                    }]
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
    
    @patch.object(AppleSearchAdsClient, 'get_campaign_report')
    def test_get_daily_spend(self, mock_get_report, client):
        """Test getting daily spend."""
        mock_df = pd.DataFrame({
            'date': ['2024-01-01', '2024-01-01', '2024-01-02'],
            'spend': [100.0, 50.0, 75.0],
            'impressions': [1000, 500, 750],
            'taps': [50, 25, 40],
            'installs': [10, 5, 8]
        })
        mock_get_report.return_value = mock_df
        
        result = client.get_daily_spend(days=7)
        
        assert len(result) == 2  # Two unique dates
        assert result.iloc[0]['spend'] == 150.0  # 100 + 50
        assert result.iloc[1]['spend'] == 75.0
        assert 'clicks' in result.columns  # taps renamed to clicks
    
    @patch.object(AppleSearchAdsClient, 'get_campaigns_with_details')
    @patch.object(AppleSearchAdsClient, 'get_campaign_report')
    def test_get_daily_spend_by_app(self, mock_get_report, mock_get_campaigns, client):
        """Test getting daily spend by app."""
        # Mock campaigns with app IDs
        mock_get_campaigns.return_value = [
            {"id": "1", "adamId": "123456"},
            {"id": "2", "adamId": "789012"}
        ]
        
        # Mock campaign report
        mock_df = pd.DataFrame({
            'date': ['2024-01-01', '2024-01-01', '2024-01-02'],
            'campaign_id': ['1', '2', '1'],
            'spend': [100.0, 50.0, 75.0],
            'impressions': [1000, 500, 750],
            'taps': [50, 25, 40],
            'installs': [10, 5, 8]
        })
        mock_get_report.return_value = mock_df
        
        start_date = datetime(2024, 1, 1)
        end_date = datetime(2024, 1, 2)
        
        result = client.get_daily_spend_by_app(start_date, end_date)
        
        assert len(result) == 3  # 3 date-app combinations
        assert '123456' in result['app_id'].values
        assert '789012' in result['app_id'].values
        assert 'clicks' in result.columns  # taps renamed to clicks
        assert 'campaigns' in result.columns  # campaign count