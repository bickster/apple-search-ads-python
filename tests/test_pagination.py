"""
Tests for automatic report pagination (v3.0.0).

Covers the paged fetch loop used by all report methods and get_keywords:
- multi-page accumulation with correct offsets
- no spurious extra requests
- empty results
- termination on lack of progress (raises instead of spinning)
- truncation backstop for non-paged fetches
"""

import pytest
from unittest.mock import patch

from apple_search_ads import AppleSearchAdsClient
from apple_search_ads.exceptions import PaginationError


def report_page(rows, total, start, items):
    """Build a report response page with top-level pagination."""
    return {
        "data": {"reportingDataResponse": {"row": rows}},
        "pagination": {"totalResults": total, "startIndex": start, "itemsPerPage": items},
        "error": None,
    }


def report_rows(count, start=0):
    """Build `count` distinct raw report rows."""
    return [{"metadata": {"campaignId": str(start + i)}} for i in range(count)]


class TestReportPagination:
    """Pagination behavior of the internal report fetch."""

    @pytest.fixture
    def client(self):
        return AppleSearchAdsClient(
            client_id="test_client_id",
            team_id="test_team_id",
            key_id="test_key_id",
            private_key_content="test_key",
            org_id="123456",
        )

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_pages_across_multiple_requests(self, mock_make_request, client):
        """totalResults=2500, limit=1000 -> 3 requests at offsets 0/1000/2000, 2500 rows."""
        mock_make_request.side_effect = [
            report_page(report_rows(1000, 0), 2500, 0, 1000),
            report_page(report_rows(1000, 1000), 2500, 1000, 1000),
            report_page(report_rows(500, 2000), 2500, 2000, 500),
        ]

        rows = client.get_campaign_report_raw("2024-01-01", "2024-01-31")

        assert len(rows) == 2500
        assert mock_make_request.call_count == 3
        offsets = [
            call.kwargs["json_data"]["selector"]["pagination"]["offset"]
            for call in mock_make_request.call_args_list
        ]
        assert offsets == [0, 1000, 2000]

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_single_full_page_issues_one_request(self, mock_make_request, client):
        """totalResults=1000, limit=1000 -> exactly 1 request, no spurious second page."""
        mock_make_request.side_effect = [
            report_page(report_rows(1000), 1000, 0, 1000),
        ]

        rows = client.get_campaign_report_raw("2024-01-01", "2024-01-31")

        assert len(rows) == 1000
        assert mock_make_request.call_count == 1

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_empty_result_is_not_an_error(self, mock_make_request, client):
        """totalResults=0 -> 1 request, empty result, no error."""
        mock_make_request.side_effect = [
            report_page([], 0, 0, 0),
        ]

        rows = client.get_campaign_report_raw("2024-01-01", "2024-01-31")

        assert rows == []
        assert mock_make_request.call_count == 1

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_zero_items_per_page_mid_loop_raises(self, mock_make_request, client):
        """A page reporting itemsPerPage=0 mid-loop raises instead of spinning forever."""
        mock_make_request.side_effect = [
            report_page(report_rows(1000), 2500, 0, 1000),
            report_page([], 2500, 1000, 0),
        ]

        with pytest.raises(PaginationError):
            client.get_campaign_report_raw("2024-01-01", "2024-01-31")

        assert mock_make_request.call_count == 2

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_non_paged_short_result_raises_instead_of_truncating(self, mock_make_request, client):
        """A single-page fetch that would silently truncate raises instead."""
        mock_make_request.side_effect = [
            report_page(report_rows(1000), 2500, 0, 1000),
        ]

        with pytest.raises(PaginationError):
            client._fetch_report_rows(
                f"{client.BASE_URL}/reports/campaigns",
                "2024-01-01",
                "2024-01-31",
                paginate=False,
            )

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_build_report_request_emits_offset_and_limit(self, mock_make_request, client):
        """_build_report_request emits both offset and limit in selector.pagination."""
        from datetime import datetime

        request = client._build_report_request(
            datetime(2024, 1, 1), datetime(2024, 1, 31), offset=1000, limit=500
        )

        assert request["selector"]["pagination"] == {"offset": 1000, "limit": 500}

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_dataframe_report_accumulates_all_pages(self, mock_make_request, client):
        """get_campaign_report (DataFrame path) returns rows from every page."""

        def granularity_row(campaign_id):
            return {
                "metadata": {
                    "campaignId": campaign_id,
                    "campaignName": f"Campaign {campaign_id}",
                    "campaignStatus": "ENABLED",
                    "app": {"appName": "Test App", "adamId": "123456789"},
                },
                "granularity": [
                    {
                        "date": "2024-01-01",
                        "impressions": 100,
                        "taps": 10,
                        "totalInstalls": 5,
                        "totalNewDownloads": 3,
                        "totalRedownloads": 2,
                        "latOnInstalls": 4,
                        "latOffInstalls": 1,
                        "tapInstalls": 4,
                        "viewInstalls": 1,
                        "tapNewDownloads": 2,
                        "tapRedownloads": 2,
                        "viewNewDownloads": 1,
                        "viewRedownloads": 0,
                        "localSpend": {"amount": "10.00", "currency": "USD"},
                        "totalAvgCPI": {"amount": "2.00", "currency": "USD"},
                        "avgCPT": {"amount": "1.00", "currency": "USD"},
                        "avgCPM": {"amount": "100.00", "currency": "USD"},
                        "ttr": 0.1,
                        "totalInstallRate": 0.5,
                        "tapInstallRate": 0.4,
                    }
                ],
            }

        mock_make_request.side_effect = [
            report_page([granularity_row("1"), granularity_row("2")], 3, 0, 2),
            report_page([granularity_row("3")], 3, 2, 1),
        ]

        df = client.get_campaign_report("2024-01-01", "2024-01-31")

        assert len(df) == 3
        assert sorted(df["campaign_id"]) == ["1", "2", "3"]
        assert mock_make_request.call_count == 2


class TestKeywordListPagination:
    """get_keywords pages past Apple's 1000-row limit."""

    @pytest.fixture
    def client(self):
        return AppleSearchAdsClient(
            client_id="test_client_id",
            team_id="test_team_id",
            key_id="test_key_id",
            private_key_content="test_key",
            org_id="123456",
        )

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_keywords_pages_past_1000(self, mock_make_request, client):
        """1327 keywords -> 2 requests, all keywords returned."""

        def keyword_page(count, start, total):
            return {
                "data": [
                    {"id": str(start + i), "text": f"kw{start + i}", "adGroupId": "42"}
                    for i in range(count)
                ],
                "pagination": {
                    "totalResults": total,
                    "startIndex": start,
                    "itemsPerPage": count,
                },
            }

        mock_make_request.side_effect = [
            keyword_page(1000, 0, 1327),
            keyword_page(327, 1000, 1327),
        ]

        keywords = client.get_keywords("1001")

        assert len(keywords) == 1327
        assert mock_make_request.call_count == 2
        offsets = [
            call.kwargs["json_data"]["pagination"]["offset"]
            for call in mock_make_request.call_args_list
        ]
        assert offsets == [0, 1000]

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_get_keywords_single_page(self, mock_make_request, client):
        """Fewer keywords than the limit -> exactly 1 request."""
        mock_make_request.side_effect = [
            {
                "data": [{"id": "1", "text": "kw", "adGroupId": "42"}],
                "pagination": {"totalResults": 1, "startIndex": 0, "itemsPerPage": 1},
            },
        ]

        keywords = client.get_keywords("1001")

        assert len(keywords) == 1
        assert mock_make_request.call_count == 1
