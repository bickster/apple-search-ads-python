"""
Tests for strict metric parsing (v3.0.0).

Field classes get distinct treatment:
- Base facts (impressions, taps, installs, ..., localSpend): must be present, raise otherwise.
- Ratios (ttr, conversion_rate, tap_install_rate): absent -> None, never 0.
- Money (spend, avg_cpa, avg_cpt, avg_cpm): Decimal from the original JSON string;
  absent ratio-derived money -> None; absent localSpend -> raise.

strict=False restores v2.7.1 zero-fill behavior exactly (donor migration aid).
"""

from decimal import Decimal

import pytest

from apple_search_ads import AppleSearchAdsClient
from apple_search_ads.exceptions import MissingMetricError


def full_modern_row(**overrides):
    """A complete non-legacy day row with every base fact present."""
    row = {
        "impressions": 10000,
        "taps": 500,
        "totalInstalls": 50,
        "totalNewDownloads": 30,
        "totalRedownloads": 20,
        "latOnInstalls": 40,
        "latOffInstalls": 10,
        "tapInstalls": 45,
        "viewInstalls": 5,
        "tapNewDownloads": 28,
        "tapRedownloads": 17,
        "viewNewDownloads": 2,
        "viewRedownloads": 3,
        "localSpend": {"amount": "1265.20", "currency": "USD"},
        "totalAvgCPI": {"amount": "2.00", "currency": "USD"},
        "avgCPT": {"amount": "0.20", "currency": "USD"},
        "avgCPM": {"amount": "10.00", "currency": "USD"},
        "ttr": 0.05,
        "totalInstallRate": 0.1,
        "tapInstallRate": 0.09,
    }
    row.update(overrides)
    return row


def full_legacy_row(**overrides):
    """A complete legacy day row with every base fact present."""
    row = {
        "impressions": 10000,
        "taps": 500,
        "installs": 50,
        "newDownloads": 30,
        "redownloads": 20,
        "latOnInstalls": 40,
        "latOffInstalls": 10,
        "tapInstalls": 45,
        "viewInstalls": 5,
        "tapNewDownloads": 28,
        "tapRedownloads": 17,
        "viewNewDownloads": 2,
        "viewRedownloads": 3,
        "localSpend": {"amount": "1265.20", "currency": "USD"},
        "avgCPA": {"amount": "2.00", "currency": "USD"},
        "avgCPT": {"amount": "0.20", "currency": "USD"},
        "avgCPM": {"amount": "10.00", "currency": "USD"},
        "ttr": 0.05,
        "conversionRate": 0.1,
        "tapInstallRate": 0.09,
    }
    row.update(overrides)
    return row


def make_client(strict=True):
    return AppleSearchAdsClient(
        client_id="test_client_id",
        team_id="test_team_id",
        key_id="test_key_id",
        private_key_content="test_key",
        org_id="123456",
        strict=strict,
    )


class TestStrictBaseFacts:
    """Base facts must be present — missing keys raise, never default to 0."""

    def test_missing_impressions_raises_naming_the_field(self):
        client = make_client()
        row = full_modern_row()
        del row["impressions"]

        with pytest.raises(MissingMetricError) as exc_info:
            client._parse_metrics(row, is_legacy=False)

        assert exc_info.value.field == "impressions"
        assert "impressions" in str(exc_info.value)

    def test_missing_metric_error_reports_available_keys(self):
        client = make_client()
        row = full_modern_row()
        del row["taps"]

        with pytest.raises(MissingMetricError) as exc_info:
            client._parse_metrics(row, is_legacy=False)

        assert "impressions" in exc_info.value.available_keys

    def test_missing_local_spend_raises(self):
        """localSpend is a base fact, not a ratio — absence raises."""
        client = make_client()
        row = full_modern_row()
        del row["localSpend"]

        with pytest.raises(MissingMetricError) as exc_info:
            client._parse_metrics(row, is_legacy=False)

        assert exc_info.value.field == "localSpend"

    def test_missing_lat_installs_is_none_not_error(self):
        """The live API no longer returns LAT metrics (verified 2026-08-03):
        absent lat_on/lat_off installs are None — not an error, and never 0."""
        client = make_client()
        row = full_modern_row()
        del row["latOnInstalls"]
        del row["latOffInstalls"]

        metrics = client._parse_metrics(row, is_legacy=False)

        assert metrics["lat_on_installs"] is None
        assert metrics["lat_off_installs"] is None

    def test_present_lat_installs_keep_their_value(self):
        client = make_client()
        metrics = client._parse_metrics(full_modern_row(), is_legacy=False)
        assert metrics["lat_on_installs"] == 40
        assert metrics["lat_off_installs"] == 10

    def test_complete_row_parses_without_error(self):
        client = make_client()
        metrics = client._parse_metrics(full_modern_row(), is_legacy=False)
        assert metrics["impressions"] == 10000
        assert metrics["installs"] == 50

    def test_legacy_row_with_modern_keys_raises(self):
        """Regression for the is_legacy hazard: a non-legacy row (totalInstalls)
        parsed with is_legacy=True must raise, not silently yield installs=0."""
        client = make_client()
        row = full_modern_row()  # carries totalInstalls, not installs

        with pytest.raises(MissingMetricError):
            client._parse_metrics(row, is_legacy=True)

    def test_modern_row_with_legacy_keys_raises(self):
        """The inverse inference error must also raise."""
        client = make_client()
        row = full_legacy_row()  # carries installs, not totalInstalls

        with pytest.raises(MissingMetricError):
            client._parse_metrics(row, is_legacy=False)


class TestStrictRatios:
    """Ratios are legitimately absent on 0-denominator days -> None, never 0."""

    def test_missing_ttr_is_none_not_zero(self):
        client = make_client()
        row = full_modern_row()
        del row["ttr"]

        metrics = client._parse_metrics(row, is_legacy=False)

        assert metrics["ttr"] is None

    def test_missing_conversion_rate_is_none(self):
        client = make_client()
        row = full_modern_row()
        del row["totalInstallRate"]

        metrics = client._parse_metrics(row, is_legacy=False)

        assert metrics["conversion_rate"] is None

    def test_zero_ratio_is_distinguishable_from_absent(self):
        """A genuine zero ratio stays 0; an absent one is None."""
        client = make_client()
        metrics = client._parse_metrics(full_modern_row(ttr=0), is_legacy=False)
        assert metrics["ttr"] == 0
        assert metrics["ttr"] is not None


class TestStrictMoney:
    """Money is Decimal built from the original JSON string, never float."""

    def test_spend_is_exact_decimal(self):
        client = make_client()
        metrics = client._parse_metrics(full_modern_row(), is_legacy=False)

        assert type(metrics["spend"]) is Decimal
        assert metrics["spend"] == Decimal("1265.20")

    def test_avg_money_is_decimal(self):
        client = make_client()
        metrics = client._parse_metrics(full_modern_row(), is_legacy=False)

        assert type(metrics["avg_cpa"]) is Decimal
        assert metrics["avg_cpa"] == Decimal("2.00")
        assert type(metrics["avg_cpt"]) is Decimal
        assert type(metrics["avg_cpm"]) is Decimal

    def test_absent_ratio_derived_money_is_none(self):
        """avg_cpa/avg_cpt/avg_cpm are ratio-derived — absent -> None, not 0."""
        client = make_client()
        row = full_modern_row()
        del row["totalAvgCPI"]
        del row["avgCPT"]

        metrics = client._parse_metrics(row, is_legacy=False)

        assert metrics["avg_cpa"] is None
        assert metrics["avg_cpt"] is None

    def test_currency_comes_from_local_spend(self):
        client = make_client()
        row = full_modern_row(localSpend={"amount": "5.00", "currency": "EUR"})
        metrics = client._parse_metrics(row, is_legacy=False)
        assert metrics["currency"] == "EUR"


class TestNonStrictCompatibility:
    """strict=False reproduces v2.7.1 zero-fill behavior exactly."""

    def test_sparse_row_zero_fills_like_v2(self):
        client = make_client(strict=False)
        sparse = {
            "impressions": 100,
            "localSpend": {"amount": "10.50", "currency": "USD"},
        }

        metrics = client._parse_metrics(sparse, is_legacy=False)

        assert metrics == {
            "impressions": 100,
            "taps": 0,
            "installs": 0,
            "new_downloads": 0,
            "redownloads": 0,
            "lat_on_installs": 0,
            "lat_off_installs": 0,
            "tap_installs": 0,
            "view_installs": 0,
            "tap_new_downloads": 0,
            "tap_redownloads": 0,
            "view_new_downloads": 0,
            "view_redownloads": 0,
            "spend": 10.5,
            "currency": "USD",
            "avg_cpa": 0.0,
            "avg_cpt": 0.0,
            "avg_cpm": 0.0,
            "ttr": 0,
            "conversion_rate": 0,
            "tap_install_rate": 0,
        }
        assert type(metrics["spend"]) is float

    def test_sparse_legacy_row_zero_fills_like_v2(self):
        client = make_client(strict=False)
        metrics = client._parse_metrics({}, is_legacy=True)

        assert metrics["installs"] == 0
        assert metrics["spend"] == 0.0
        assert metrics["ttr"] == 0

    def test_derived_metrics_work_with_decimal_spend(self):
        """The DataFrame convenience path must not choke on Decimal spend columns."""
        import pandas as pd

        client = make_client()
        df = pd.DataFrame(
            {
                "spend": [Decimal("10.00"), Decimal("20.00")],
                "installs": [4, 0],
                "taps": [10, 5],
                "impressions": [100, 50],
            }
        )

        result = client._add_derived_metrics(df)

        assert result["cpi"].tolist() == [2.5, 0]
        assert result["ctr"].tolist() == [10.0, 10.0]

    def test_strict_is_the_default(self):
        client = AppleSearchAdsClient(
            client_id="test_client_id",
            team_id="test_team_id",
            key_id="test_key_id",
            private_key_content="test_key",
        )
        assert client.strict is True
