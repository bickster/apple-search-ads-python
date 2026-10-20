"""
Tests for group_by on search term reports (4.1.0).

v5's search term reports accepted groupBy (callers used countryOrRegion to get one
row per search term per country); 4.0 dropped the option. group_by restores it.
"""

from unittest.mock import patch

import pytest

from apple_search_ads import AppleSearchAdsClient


@pytest.fixture
def client():
    return AppleSearchAdsClient(
        client_id="test_client_id",
        team_id="test_team_id",
        key_id="test_key_id",
        private_key_content="test_key",
        org_id="123456",
    )


def search_term_row(country):
    metrics = {
        key: 1
        for key in (
            "impressions",
            "taps",
            "totalInstalls",
            "totalNewDownloads",
            "totalRedownloads",
            "tapInstalls",
            "viewInstalls",
            "tapNewDownloads",
            "tapRedownloads",
            "viewNewDownloads",
            "viewRedownloads",
        )
    }
    metrics["localSpend"] = {"amount": "2.50", "currency": "USD"}
    return {
        "metadata": {
            "adGroupId": 7,
            "searchTermText": "bible chat",
            "searchTermSource": "TARGETED",
            "keyword": {"id": 9, "text": "bible chat", "matchType": "EXACT"},
            "countryOrRegion": country,
        },
        "totalMetrics": metrics,
    }


def page(rows):
    return {
        "result": {"rows": rows},
        "pagination": {"offset": 0, "pageSize": 1000, "totalCount": len(rows)},
    }


class TestSearchTermGroupBy:
    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_group_by_is_sent_and_country_is_parsed(self, mock_make_request, client):
        mock_make_request.return_value = page([search_term_row("US"), search_term_row("GB")])

        df = client.get_search_term_report(
            "1001", "2026-10-12", "2026-10-18", group_by=["countryOrRegion"]
        )

        body = mock_make_request.call_args.kwargs["json_data"]
        assert body["groupBy"] == ["countryOrRegion"]
        assert body["timeRange"]["timeZone"] == "ORTZ"
        assert df["country_or_region"].tolist() == ["US", "GB"]

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_adgroup_variant_sends_group_by(self, mock_make_request, client):
        mock_make_request.return_value = page([search_term_row("CA")])

        df = client.get_adgroup_search_term_report(
            "1001", "7", "2026-10-12", "2026-10-18", group_by=["countryOrRegion"]
        )

        body = mock_make_request.call_args.kwargs["json_data"]
        assert body["groupBy"] == ["countryOrRegion"]
        assert {"field": "adGroupId", "operator": "EQUALS", "value": "7"} in body["filters"]
        assert df["country_or_region"].tolist() == ["CA"]

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_no_group_by_sends_none(self, mock_make_request, client):
        """Omitting group_by keeps the 4.0 request exactly as it was."""
        mock_make_request.return_value = page([])

        client.get_search_term_report("1001", "2026-10-12", "2026-10-18")

        assert "groupBy" not in mock_make_request.call_args.kwargs["json_data"]
