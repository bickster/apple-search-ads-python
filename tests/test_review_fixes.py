"""
Regression tests for the 4.0.1 fixes from the independent review of 4.0.0.

- One failing ad-account lookup must not fail every all-accounts total.
- The default account must not be a Basic (automated) account.
- app_id must never come out as "1134998522.0".
- Impression share adamId is an int, as in v5; WEEKLY must start on a Sunday.
- A single-day report row without granularMetrics is dated, not dropped.
"""

from unittest.mock import Mock, patch

import pandas as pd
import pytest
import requests

from apple_search_ads import AppleSearchAdsClient

BASIC = ["APPSTORE_APP_AUTOMATED"]
ADVANCED = ["APPSTORE_APP_MANUAL"]


def make_client(**kwargs):
    return AppleSearchAdsClient(
        client_id="test_client_id",
        team_id="test_team_id",
        key_id="test_key_id",
        private_key_content="test_key",
        **kwargs,
    )


def acl_response(*accounts):
    return {
        "result": {
            "acls": [
                {"adAccount": {"id": i, "name": f"acct {i}", "orgId": 1}, "roles": ["r"]}
                for i in accounts
            ]
        }
    }


def fake_api(acls, details):
    """_make_request stand-in: details maps account id -> features list or an exception."""

    def handler(url, *args, **kwargs):
        if url.endswith("/acls"):
            return acls
        account_id = int(url.rsplit("/", 1)[1])
        found = details[account_id]
        if isinstance(found, Exception):
            raise found
        return {"result": {"currency": "USD", "productFeatures": found}}

    return handler


def http_error(status):
    return requests.exceptions.HTTPError(response=Mock(status_code=status))


class TestAdAccountLookupFailure:
    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_failed_lookup_keeps_the_account(self, mock_make_request):
        mock_make_request.side_effect = fake_api(
            acl_response(1, 2), {1: http_error(403), 2: ADVANCED}
        )

        orgs = make_client().get_all_organizations()

        assert [o["orgId"] for o in orgs] == [1, 2]
        assert orgs[0]["currency"] is None
        assert orgs[1]["currency"] == "USD"

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_failed_lookup_is_retried_on_the_next_call(self, mock_make_request):
        client = make_client()
        mock_make_request.side_effect = fake_api(acl_response(1), {1: http_error(503)})
        assert client.get_all_organizations()[0]["currency"] is None

        mock_make_request.side_effect = fake_api(acl_response(1), {1: ADVANCED})
        assert client.get_all_organizations()[0]["currency"] == "USD"

    @patch.object(AppleSearchAdsClient, "get_campaign_report")
    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_all_accounts_total_survives_one_bad_account(self, mock_make_request, mock_report):
        mock_make_request.side_effect = fake_api(
            acl_response(1, 2), {1: http_error(403), 2: ADVANCED}
        )
        mock_report.return_value = pd.DataFrame(
            [{"date": "2026-10-18", "spend": 1, "impressions": 1, "taps": 1, "installs": 1}]
        )

        df = make_client().get_daily_spend_with_dates("2026-10-18", "2026-10-18")

        assert mock_report.call_count == 2
        assert df["spend"].tolist() == [2]


class TestDefaultAccount:
    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_default_account_skips_basic(self, mock_make_request):
        mock_make_request.side_effect = fake_api(acl_response(7, 8), {7: BASIC, 8: ADVANCED})
        client = make_client()

        assert client._get_org_id() == "8"
        assert client.org_id == "8"

    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_default_account_falls_back_when_all_are_basic(self, mock_make_request):
        mock_make_request.side_effect = fake_api(acl_response(7), {7: BASIC})

        assert make_client()._get_org_id() == "7"


class TestAppIdFormat:
    @patch.object(AppleSearchAdsClient, "_fetch_campaign_reports_from_orgs")
    def test_app_id_is_never_a_float_string(self, mock_fetch):
        """A row without an app makes the adam_id column float64."""
        mock_fetch.return_value = [
            pd.DataFrame(
                [
                    {"date": "2026-10-18", "campaign_id": 1, "adam_id": 1134998522},
                    {"date": "2026-10-18", "campaign_id": 2, "adam_id": None},
                ]
            ).assign(spend=1, impressions=1, taps=1, installs=1)
        ]

        df = make_client(org_id="1").get_daily_spend_by_app("2026-10-18", "2026-10-18")

        assert df["app_id"].tolist() == ["1134998522"]


class TestImpressionShareFixes:
    @patch.object(AppleSearchAdsClient, "_make_request")
    def test_adam_id_is_an_int_like_v5(self, mock_make_request):
        mock_make_request.return_value = {
            "result": {"rows": [{"day": "2026-10-18", "promotedObjectId": "6760951765"}]},
            "pagination": {"offset": 0, "pageSize": 1000, "totalCount": 1},
        }

        df = make_client(org_id="1").get_impression_share_data(
            "unused", "2026-10-18", "2026-10-18", adam_ids=["6760951765"]
        )

        assert df["adamId"].tolist() == [6760951765]

    def test_weekly_must_start_on_a_sunday(self):
        with pytest.raises(ValueError, match="Sunday"):
            make_client(org_id="1").get_impression_share_data(
                "unused", "2026-10-13", "2026-10-19", granularity="WEEKLY", adam_ids=["1"]
            )


def total_only_row():
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
    metrics["localSpend"] = {"amount": "5.00", "currency": "USD"}
    return {"metadata": {"id": 1, "promotedObjectId": "1"}, "totalMetrics": metrics}


class TestSingleDayDate:
    @patch.object(AppleSearchAdsClient, "get_campaign_report_raw")
    def test_single_day_total_only_row_gets_the_requested_date(self, mock_raw):
        mock_raw.return_value = [total_only_row()]

        df = make_client(org_id="1").get_campaign_report("2026-10-18", "2026-10-18")

        assert df["date"].tolist() == ["2026-10-18"]

    @patch.object(AppleSearchAdsClient, "get_campaign_report_raw")
    def test_multi_day_total_only_row_is_not_given_a_guessed_date(self, mock_raw):
        mock_raw.return_value = [total_only_row()]

        df = make_client(org_id="1").get_campaign_report("2026-10-12", "2026-10-18")

        assert df["date"].tolist() == [None]
