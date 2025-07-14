"""
Pytest configuration and fixtures for Apple Search Ads tests.
"""

import pytest
from unittest.mock import Mock


@pytest.fixture
def mock_response():
    """Create a mock response object."""
    response = Mock()
    response.status_code = 200
    response.raise_for_status = Mock()
    return response


@pytest.fixture
def sample_org_data():
    """Sample organization data."""
    return {
        "data": [
            {
                "orgId": "123456",
                "orgName": "Test Organization",
                "currency": "USD",
                "paymentModel": "PAYG",
                "roleNames": ["API Account Manager"],
            }
        ]
    }


@pytest.fixture
def sample_campaign_data():
    """Sample campaign data."""
    return {
        "data": [
            {
                "id": "1001",
                "name": "App Campaign 1",
                "adamId": "123456789",
                "status": "ENABLED",
                "budgetAmount": {"amount": "1000.00", "currency": "USD"},
                "dailyBudgetAmount": {"amount": "50.00", "currency": "USD"},
            },
            {
                "id": "1002",
                "name": "App Campaign 2",
                "adamId": "987654321",
                "status": "PAUSED",
                "budgetAmount": {"amount": "500.00", "currency": "USD"},
                "dailyBudgetAmount": {"amount": "25.00", "currency": "USD"},
            },
        ]
    }


@pytest.fixture
def sample_report_data():
    """Sample campaign report data."""
    return {
        "data": {
            "reportingDataResponse": {
                "row": [
                    {
                        "metadata": {
                            "campaignId": "1001",
                            "campaignName": "App Campaign 1",
                            "campaignStatus": "ENABLED",
                            "app": {"appName": "Test App", "adamId": "123456789"},
                        },
                        "granularity": [
                            {
                                "date": "2024-01-01",
                                "impressions": 10000,
                                "taps": 500,
                                "totalInstalls": 50,
                                "localSpend": {"amount": "100.00", "currency": "USD"},
                                "totalAvgCPI": {"amount": "2.00", "currency": "USD"},
                                "avgCPT": {"amount": "0.20", "currency": "USD"},
                                "ttr": 0.05,
                                "totalInstallRate": 0.1,
                            },
                            {
                                "date": "2024-01-02",
                                "impressions": 12000,
                                "taps": 600,
                                "totalInstalls": 60,
                                "localSpend": {"amount": "120.00", "currency": "USD"},
                                "totalAvgCPI": {"amount": "2.00", "currency": "USD"},
                                "avgCPT": {"amount": "0.20", "currency": "USD"},
                                "ttr": 0.05,
                                "totalInstallRate": 0.1,
                            },
                        ],
                    }
                ]
            }
        }
    }
