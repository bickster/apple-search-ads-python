# Spec — `apple-search-ads-client` v3.0.0 (breaking)

**For:** this repo (`apple-search-ads-client`, currently **v2.7.1**)
**From:** the `bickster-hq` engineering session · **Date:** 2026-08-03
**Consumer driving this:** `bickster_os` ASA Pass 2 — full recon at
`~/Projects/bickster-hq/docs/AppleSearchAdsPass2/recon.md` (cross-repo; read it for the why, not required
to execute this spec)

> **Operator ruling: Path B.** `bickster_os` will consume this SDK **wholesale** rather than porting its
> auth seam. That requires the two defects below to be fixed at source. **Breaking the donor project
> (`~/Documents/apple-search-ads-save`) is explicitly accepted** — Chris will fix it afterwards. Do not
> contort the API to preserve donor compatibility.

> **No deadline.** ASA Pass 2 in `bickster_os` is deliberately **gated** on this release — the operator's
> call, 2026-08-03. There is no schedule pressure, so prefer the correct fix over the fast one. Nothing
> downstream ships until 3.0.0 is on PyPI.

Everything in this spec was verified against the live Apple API and the v2.7.1 source on 2026-08-03.
Line numbers refer to **this repo's** `src/apple_search_ads/client.py` at v2.7.1.

---

## Why (one paragraph)

`bickster_os` lands money that must reconcile to Apple **to the cent**, and its pipeline asserts that
required Apple fields are *present* before constructing a row. The SDK today silently substitutes `0` for
any missing metric and silently truncates any report over 1000 rows. Both are invisible failures: they
produce plausible numbers, not errors. At campaign grain (190 rows) neither has bitten. ASA Pass 2 moves to
keyword and search-term grain (22,034 keywords today, 2 campaigns already over the 1000 limit), where both
will bite immediately and quietly.

---

## Change 1 — Real pagination (currently absent everywhere)

### The defect

`_build_report_request` (**:203**) hardcodes `"pagination": {"limit": 1000}` with **no offset**, and there is
**no offset loop anywhere in the file**. `get_keywords` (**:381**) hardcodes `{"offset": 0, "limit": 1000}`.
Any report or keyword list exceeding 1000 rows is **silently truncated**.

`_extract_rows_from_response` (**:214-223**) returns only the rows and **discards the pagination block**, so
callers cannot even detect truncation.

**Already breaking in production data:** `Fitbit to Apple Health Sync - US - REDBOX -` has **1,327**
keywords and `SMO` has **1,012**. Eight more campaigns are ≥500 and rising.

### Verified response shape (live, 2026-07-31)

`pagination` is a **top-level sibling of `data`**, not nested inside it:

```json
{
  "data": { "reportingDataResponse": { "row": [ ... ] } },
  "pagination": { "totalResults": 21, "startIndex": 0, "itemsPerPage": 5 },
  "error": null
}
```

`selector.pagination.offset` is honored — requesting `{"offset": 3, "limit": 2}` returns
`{"totalResults": 21, "startIndex": 3, "itemsPerPage": 2}`.

### Required behavior

1. `_build_report_request` takes `offset: int = 0` and emits `{"offset": offset, "limit": limit}`, with
   `limit` a parameter (default 1000, Apple's max).
2. Add an internal paged fetch used by **every** report method and by `get_keywords`:
   loop `offset += itemsPerPage` while `startIndex + itemsPerPage < totalResults`, accumulating rows.
3. **Terminate on lack of progress, not just the counter.** If a page returns `itemsPerPage == 0` or no new
   rows, stop and raise rather than loop forever — a server-side quirk must not become an infinite loop.
4. Surface pagination to callers: `_extract_rows_from_response` should either return the pagination block
   alongside rows or gain a sibling accessor. Callers must be able to assert completeness.
5. **Guard against silent truncation as a backstop**: if a caller opts out of paging, and
   `len(rows) < totalResults`, raise — never return a short result quietly.
6. Apply the same treatment to `get_keywords` (**:381**).

⚠️ **Interaction with `returnRecordsWithNoMetrics: False`:** rows are filtered server-side *before*
pagination, so `totalResults` reflects the filtered count. Verify this holds — if `totalResults` ever counts
pre-filter rows, the loop's termination condition is wrong. Add a test pinning the observed behavior.

---

## Change 2 — Stop zero-filling metrics (the dangerous one)

### The defect

`_parse_metrics` (**:225-273**) resolves **every** metric with a `0` default:

```python
"impressions": day_data.get("impressions", 0),
"spend":       float((day_data.get("localSpend") or {}).get("amount", 0)),
```

If Apple renames, drops, or fails to return a field, the row lands **`0`** instead of raising. Downstream
validation cannot catch it because `0` is a structurally valid value. This is the single highest-risk
behavior in the SDK.

### ⚠️ The latent bug that makes it worse

The `is_legacy` branches map **different Apple keys to the same output name**:

| Output field | `is_legacy=True` reads | `is_legacy=False` reads |
|---|---|---|
| `installs` | `installs` | **`totalInstalls`** |
| `new_downloads` | `newDownloads` | **`totalNewDownloads`** |
| `redownloads` | `redownloads` | **`totalRedownloads`** |
| `avg_cpa` | `avgCPA` | **`totalAvgCPI`** |
| `conversion_rate` | `conversionRate` | **`totalInstallRate`** |

`is_legacy` is inferred purely from whether `"granularity"` is present in the row (**:592-599**). **If that
inference is ever wrong, those five fields silently become `0` for every row** — a full-column data loss
that reports as success. Combined with the `0` defaults, there is no way to detect it.

### Required behavior — three field classes, three treatments

Metrics are **not** homogeneous. Treating them uniformly is what created this bug.

| Class | Fields | Required behavior |
|---|---|---|
| **Base facts** | `impressions`, `taps`, `installs`, `new_downloads`, `redownloads`, `lat_on_installs`, `lat_off_installs`, `tap_installs`, `view_installs`, `tap_new_downloads`, `tap_redownloads`, `view_new_downloads`, `view_redownloads`, **`localSpend`** | **Must be present.** Raise a typed error naming the missing key. Never default. |
| **Ratios** | `ttr`, `conversion_rate`, `tap_install_rate` | **Legitimately absent** on 0-denominator days. Return **`None`**, never `0` — `0` is a real, different value and conflating them corrupts averages. |
| **Money** | `localSpend`, `avg_cpa`, `avg_cpt`, `avg_cpm` | Return **`Decimal`** built from the **original JSON string** (`Decimal(str(amount))`). Never `float(...)`. Absent *ratio-derived* money (`avg_cpa`/`avg_cpt`/`avg_cpm`) → `None`; absent `localSpend` → raise (base fact). |

Add a typed exception, e.g. `MissingMetricError(field, available_keys)` in `exceptions.py`, and include the
keys that *were* present — that turns a future Apple rename into a one-line diagnosis.

### API surface

- **`strict: bool = True`** on the client (or per-report-method). Strict raises per the table above.
  `strict=False` restores v2 zero-fill **solely as a migration aid for the donor project**. Default **must**
  be strict — a correctness default that must be opted into is not a fix.
- **Add a raw-entry accessor.** The public `get_*_report` methods return `pd.DataFrame`; `Decimal` columns
  degrade to `object` dtype, and `bickster_os` wants unparsed entries for its own Pydantic validation
  anyway. Add either `as_dataframe: bool = True` or `get_*_report_raw()` returning
  `List[Dict[str, Any]]` with money left as the original strings. **`bickster_os` will consume the raw
  path** — treat it as a first-class API, not an escape hatch.

### Not in scope for this change

Do **not** alter the entity methods (`get_all_organizations`, `get_campaigns`, `get_all_campaigns`,
`get_adgroups`, `get_keywords`, `get_app_details`). They already return raw `List[Dict[str, Any]]` with no
metric coercion and are safe as-is — `get_keywords` needs *only* the pagination fix from Change 1.

---

## Change 3 — Housekeeping (small, do while you're here)

- **`timeZone` already works.** `_build_report_request` accepts `time_zone` (**:195**, applied at **:210-211**) and
  `get_campaign_report` exposes it (**:560**). The donor's `_get_report_with_timezone` workaround
  (`collector.py:129-223`, comment at `:136-141` claiming "the library doesn't expose timezone parameter")
  is **stale** and should simply be deleted when the donor is fixed. Nothing to change in the SDK — noted so
  nobody re-derives the workaround.
- Consider documenting in the README that `returnRecordsWithNoMetrics: False` is set by default
  (**:206**), since it means "no row" ≠ "keyword does not exist."

---

## Testing requirements

The repo has `tests/test_client.py`, `tests/test_integration.py`, `conftest.py`, and `TESTING.md` — follow
the existing conventions.

**Write these test-first.** Each must be watched failing before implementation.

**Pagination**
1. `totalResults=2500, limit=1000` → 3 requests issued, 2500 rows returned, offsets `0/1000/2000`.
2. `totalResults=1000, limit=1000` → exactly 1 request (no spurious second page).
3. `totalResults=0` → 1 request, empty result, no error.
4. Page returns `itemsPerPage=0` mid-loop → raises, does **not** spin.
5. Non-paged call whose `len(rows) < totalResults` → raises rather than truncating.
6. `get_keywords` pages past 1000.

**Strict parsing**
7. Missing `impressions` → `MissingMetricError` naming `impressions` (not a `0` row).
8. Missing `localSpend` → raises (base fact, not a ratio).
9. Missing `ttr` → `None`, **not** `0`, and does **not** raise.
10. `localSpend.amount == "1265.20"` → `Decimal("1265.20")`, and `type(...) is Decimal`.
11. **Regression for the `is_legacy` hazard:** a non-legacy row carrying `totalInstalls` parsed with
    `is_legacy=True` must **raise**, not silently yield `installs=0`. This is the test that would have
    caught the whole class of bug.
12. `strict=False` reproduces v2.7.1 behavior exactly (zero-fill), so the donor has a working stopgap.

**No network in unit tests** — fixture the JSON response shapes above.

---

## Release

- **Version `3.0.0`** — both changes are breaking (strict default; `Decimal` instead of `float`;
  `None` instead of `0` for ratios).
- `CHANGELOG.md`: lead with the migration note — *"metrics now raise instead of defaulting to 0; money is
  `Decimal`; ratios are `None` when absent; reports now page automatically."*
- Repo has `release.sh` / `build_and_upload.sh` / `RELEASE_GUIDE.md` — follow those.
- **Coordinate the bump.** `bickster-hq:pyproject.toml:13` currently pins `apple-search-ads-client==2.7.1`.
  It is a **phantom dependency today** (declared, never imported — the auth seam is ported at
  `bickster-hq:os/asa_sync/connectors/apple_search_ads.py`). Under Path B that changes: `bickster_os` will import it for
  real. Do not bump the pin in `bickster-hq` until 3.0.0 is on PyPI **and** the ASA Pass 2 branch is ready
  to consume it — a premature bump breaks nothing today but will mask which change caused a later failure.
- The donor (`apple-search-ads-save`) **will break** on upgrade. Accepted. Its stopgap is `strict=False`;
  its real fix is deleting the stale timezone workaround and adopting the public report methods.

---

## Acceptance criteria

1. A report with >1000 rows returns **all** rows, verified against a live `totalResults`.
2. A response missing a base-fact key **raises**, naming the key; no `0` is ever substituted in strict mode.
3. `spend` is a `Decimal` carrying the exact digits Apple sent — `Decimal("1265.20")`, not `1265.2000...`.
4. An absent ratio is `None`; a genuine zero ratio is `0`. The two are distinguishable.
5. Test 11 (the `is_legacy` regression) passes and was watched failing first.
6. `strict=False` is byte-compatible with v2.7.1 output.
7. Existing test suite green; lint/type checks per repo config clean.

## Open question for the implementing session

Should `strict=False` also disable pagination-completeness enforcement? **Recommend no** — silent
truncation is a *different* failure from a missing field, and the donor benefits from correct pagination
regardless. Keep the flag scoped to parsing only.
