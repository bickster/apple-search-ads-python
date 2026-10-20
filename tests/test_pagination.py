"""
Tests for automatic report pagination (v3.0.0; v1 page shape since 4.0.0).

Covers the paged fetch loop used by all report methods and the object queries:
- multi-page accumulation with correct offsets
- no spurious extra requests
- empty results
- termination on lack of progress (raises instead of spinning)
- truncation backstop for non-paged fetches
- pages without totalCount (query endpoints) end on a short page
"""

import pytest
from unittest.mock import patch

from apple_search_ads import AppleSearchAdsClient
from apple_search_ads.exceptions import PaginationError


def report_page(rows, total, offset, page_size=1000):
    """Build a v1 report response page with top-level pagination."""
    return {
        "result": {"rows": rows},
        "pagination": {"offset": offset, "pageSize": page_size, "totalCount": total},
    }


def report_rows(count, start=0):
    """Build `count` distinct raw report rows."""
    return [{"metadata": {"id": start + i}} for i in range(count)]


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
        """totalCount=2500, pageSize=1000 -> 3 requests at offsets 0/1000/2000, 2500 rows."""
        mock_make_request.side_effect = [
            report_page(report_rows(1000, 0), 2500, 0),
            report_page(report_rows(1000, 1000), 2500, 1000),
            report_page(report_rows(500, 2000), 2500, 2000),
        ]

        rows = client.get_campaign_report_raw("2024-01-01", "2024-01-31")

        assert len(rows) == 2500
        assert mock_make_request.call_count == 3
        offsets = [
            call.kwargs["json_data"]["pagination"]["offset"]
            for call in mock_make_request.call_args_list
        ]
        assert offsets == [0, 1000, 2000]

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_single_full_page_issues_one_request(self, mock_make_request, client):
        """totalCount=1000, pageSize=1000 -> exactly 1 request, no spurious second page."""
        mock_make_request.side_effect = [
            report_page(report_rows(1000), 1000, 0),
        ]

        rows = client.get_campaign_report_raw("2024-01-01", "2024-01-31")

        assert len(rows) == 1000
        assert mock_make_request.call_count == 1

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_empty_result_is_not_an_error(self, mock_make_request, client):
        """totalCount=0 -> 1 request, empty result, no error."""
        mock_make_request.side_effect = [
            report_page([], 0, 0),
        ]

        rows = client.get_campaign_report_raw("2024-01-01", "2024-01-31")

        assert rows == []
        assert mock_make_request.call_count == 1

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_empty_page_mid_loop_raises(self, mock_make_request, client):
        """An empty page before totalCount is reached raises instead of spinning forever."""
        mock_make_request.side_effect = [
            report_page(report_rows(1000), 2500, 0),
            report_page([], 2500, 1000),
        ]

        with pytest.raises(PaginationError):
            client.get_campaign_report_raw("2024-01-01", "2024-01-31")

        assert mock_make_request.call_count == 2

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_non_paged_short_result_raises_instead_of_truncating(self, mock_make_request, client):
        """A single-page fetch that would silently truncate raises instead."""
        mock_make_request.side_effect = [
            report_page(report_rows(1000), 2500, 0),
        ]

        with pytest.raises(PaginationError):
            client._fetch_report_rows(
                f"{client.BASE_URL}/reports/apps/campaigns/query",
                "2024-01-01",
                "2024-01-31",
                paginate=False,
            )

    def test_build_report_request_emits_offset_and_page_size(self, client):
        """_build_report_request emits offset and pageSize in pagination."""
        from datetime import datetime

        request = client._build_report_request(
            datetime(2024, 1, 1), datetime(2024, 1, 31), offset=1000, limit=500
        )

        assert request["pagination"] == {"offset": 1000, "pageSize": 500}

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_dataframe_report_accumulates_all_pages(self, mock_make_request, client):
        """get_campaign_report (DataFrame path) returns rows from every page."""

        def granular_row(campaign_id):
            return {
                "metadata": {
                    "id": campaign_id,
                    "name": f"Campaign {campaign_id}",
                    "status": "ENABLED",
                    "promotedObject": {"name": "Test App"},
                    "promotedObjectId": "123456789",
                },
                "granularMetrics": [
                    {
                        "date": "2024-01-01",
                        "impressions": 100,
                        "taps": 10,
                        "totalInstalls": 5,
                        "totalNewDownloads": 3,
                        "totalRedownloads": 2,
                        "tapInstalls": 4,
                        "viewInstalls": 1,
                        "tapNewDownloads": 2,
                        "tapRedownloads": 2,
                        "viewNewDownloads": 1,
                        "viewRedownloads": 0,
                        "localSpend": {"amount": "10.00", "currency": "USD"},
                        "totalAvgCPI": {"amount": "2.00", "currency": "USD"},
                        "cpt": {"amount": "1.00", "currency": "USD"},
                        "cpm": {"amount": "100.00", "currency": "USD"},
                        "ttr": 0.1,
                        "totalInstallRate": 0.5,
                        "tapInstallRate": 0.4,
                    }
                ],
            }

        mock_make_request.side_effect = [
            report_page([granular_row("1"), granular_row("2")], 3, 0, page_size=2),
            report_page([granular_row("3")], 3, 2, page_size=2),
        ]

        df = client.get_campaign_report("2024-01-01", "2024-01-31")

        assert len(df) == 3
        assert sorted(df["campaign_id"]) == ["1", "2", "3"]
        assert mock_make_request.call_count == 2


def keyword_page(count, start, total=None):
    """Build a v1 query response page; total=None omits totalCount."""
    pagination = {"offset": start, "pageSize": 1000}
    if total is not None:
        pagination["totalCount"] = total
    return {
        "result": [
            {"id": start + i, "text": f"kw{start + i}", "adGroupId": 42} for i in range(count)
        ],
        "pagination": pagination,
    }


class TestKeywordListPagination:
    """get_keywords pages past one 1000-row page."""

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
        mock_make_request.side_effect = [keyword_page(1, 0, 1)]

        keywords = client.get_keywords("1001")

        assert len(keywords) == 1
        assert mock_make_request.call_count == 1

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_queries_ask_for_total_count(self, mock_make_request, client):
        """v1 query endpoints omit totalCount unless fetchTotalCount is sent."""
        mock_make_request.side_effect = [keyword_page(1, 0, 1)]

        client.get_keywords("1001")

        assert (
            mock_make_request.call_args.kwargs["json_data"]["pagination"]["fetchTotalCount"] is True
        )

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_short_page_without_total_count_ends_the_fetch(self, mock_make_request, client):
        mock_make_request.side_effect = [keyword_page(5, 0)]

        keywords = client.get_keywords("1001")

        assert len(keywords) == 5
        assert mock_make_request.call_count == 1

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_empty_page_after_full_page_without_total_count_ends_cleanly(
        self, mock_make_request, client
    ):
        """Without totalCount an exact multiple of the page size ends on an
        empty page; that is completion, not a stalled fetch."""
        mock_make_request.side_effect = [keyword_page(1000, 0), keyword_page(0, 1000)]

        keywords = client.get_keywords("1001")

        assert len(keywords) == 1000
        assert mock_make_request.call_count == 2
