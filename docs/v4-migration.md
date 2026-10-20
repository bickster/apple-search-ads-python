# Migrating to 4.0 (Apple Ads Platform API v1)

Apple shuts down Campaign Management API v5 on **January 26, 2027**. 4.0 moves every call
to the Apple Ads Platform API v1 (`https://api.ads.apple.com/v1`). 3.x stops working on
that date.

**Short version:** method signatures and return shapes are unchanged, and existing v5 API
keys keep working. Upgrade and check three things:

1. **Totals now include Search Ads Basic spend.** See [Basic accounts](#search-ads-basic-accounts).
   Pass `include_basic=False` to reproduce 3.x numbers exactly.
2. **Code that reaches into internals breaks.** `BASE_URL`, `_make_request`, v5 request
   bodies and v5 URL paths are all different now (see [Internals](#internals)).
3. **Impression share's create/poll flow is gone.** `get_impression_share_data()` still
   works; the two lower-level methods raise `NotImplementedError`.

## Verification

All of this was checked live on 2026-10-19 by running 3.2.0 (v5) and 4.0 (v1) against the
same account for 2026-10-12 → 2026-10-18 and comparing every output cell by cell and field
by field.

| Surface | Result (with `include_basic=False`) |
|---|---|
| `get_daily_spend_by_app` | identical: 35/35 rows (spend, impressions, taps, installs), $8,441.0927 |
| `get_daily_spend_with_dates` | identical: 7/7 rows |
| `get_campaign_report` (9 accounts) | identical except `adam_id`, which 3.x left `None` and 4.0 fills in |
| `get_adgroup_report`, `get_keyword_report` (3 campaigns) | identical row counts and values; keyword `avg_cpm` now populated (v5 omitted it) |
| `get_search_term_report`, `get_adgroup_search_term_report` | identical |
| `get_all_organizations` | 9/9 accounts, every v5 field identical |
| `get_campaigns` | 143 campaigns: every field identical except the [unmapped fields](#unmapped-and-changed-fields) |
| `get_adgroups` | 71 ad groups: identical except `targetingDimensions`, `servingStateReasons` |
| `get_keywords` | 1,538 keywords: every field identical |
| `get_app_details` | 15/15 apps: every field identical |
| Integration suite (live) | 17/17 passed |

With the default `include_basic=True`, the week totals $8,613.2386: the same 35 rows plus
$172.1459 from the Basic account, which touches 14 rows across 2 apps (1134998522 and
1319686013). No 3.x row is lost.

Not verified live: `update_keyword_bid`. It is a write, so it is covered only by unit
tests against Apple's documented `PUT /keywords/{id}`.

## Search Ads Basic accounts

v5's `/acls` never listed Search Ads Basic (automated) accounts, so **3.x totals silently
excluded their spend**. For Bickster that was 2.0% of the 2026-10-12 week ($172.15 on top of
$8,441.09), and one app (1319686013) showed no ad spend at all.

v1 lists them. In 4.0:

- `get_all_organizations()` includes them, and so does every `fetch_all_orgs=True` total
  (`get_daily_spend*`). Each org dict carries `productFeatures`, where
  `APPSTORE_APP_AUTOMATED` marks a Basic account.
- `include_basic=False` drops them everywhere and reproduces 3.x numbers exactly.
- `get_all_campaigns()` skips them, because v1 returns **403** to campaign queries on
  Basic accounts. Their spend still comes through the report-based methods.
  Calling `get_campaigns(org_id=<basic account>)` directly raises that 403.
- `get_daily_spend_by_app` now takes the app from report metadata (`promotedObjectId`)
  instead of looking up each campaign. 3.x's lookup would have dropped Basic spend,
  since those campaigns can't be listed.
- **Time zones:** reports use each account's own zone (ORTZ). Bickster's Basic account
  is on UTC; its advanced accounts are on America/New_York. Per-day totals across both
  therefore add up days with different boundaries.

## Unmapped and changed fields

Returned objects are Apple's v1 dicts with the v5 field names added. An added name never
overwrites a v1 key, except the vocabulary collisions listed below.

**Added v5 names** (each mapping matches v5 on every live object compared):

| Object | v5 field | Source in v1 |
|---|---|---|
| org | `orgId`, `orgName`, `displayName` | ACL `adAccount.id`, `adAccount.name` |
| org | `currency`, `paymentModel`, `timeZone` | `GET /ad-accounts/{id}` (one call per account, cached per client) |
| org | `roleNames`, `parentOrgId` | ACL `roles`; `adAccount.orgId`, or `None` for the parent account itself |
| campaign | `adamId` | `promotedObjectId`, as an int |
| campaign | `orgId` | `adAccountId` |
| campaign | `supplySources` | `targeting.supplyPlacement.include`, with `APPSTORE_PRODUCT_PAGES` → `APPSTORE_PRODUCT_PAGES_BROWSE` |
| campaign | `adChannelType` | `SEARCH` when the placement is `APPSTORE_SEARCH_RESULTS`, otherwise `DISPLAY` (143/143) |
| campaign | `countriesOrRegions` | `targeting.countryOrRegion.include`, sorted |
| campaign | `dailyBudgetAmount` | `dailyBudget.value` |
| campaign | `biddingStrategy` | `bidStrategy.bidStrategyType` |
| campaign | `targetCpa` | `bidStrategy.bid` when the type is `MAX_CONVERSIONS` |
| campaign | `sapinLawResponse` | the `CAMPAIGN_SAPIN_LAW` entry of `regulationResponses` |
| campaign, ad group | `servingStatus` | `systemStatus` |
| ad group | `defaultBidAmount` | `bidStrategy.bid` |
| ad group | `cpaGoal` | `cpaCap.value` |
| keyword | `bidAmount` | `bid` |
| app | `adamId` | `id`, as an int |
| app | `isPreOrder` | `isPreorder`, as the string `"true"`/`"false"` (as v5 sent it) |

**Same key, v5 value restored:**

| Object | Field | v1 value | 4.0 returns |
|---|---|---|---|
| keyword | `status` | `ENABLED` | `ACTIVE` (`PAUSED` unchanged) |
| ad group | `pricingModel` | `CPT` | `CPC` |
| campaign | `displayStatus` | `ON_HOLD` / `LIMITED` on paused campaigns | `PAUSED` whenever `status` is `PAUSED` (131/131) |

**Not mapped** (v1 has no equivalent; neither known consumer reads them):
- campaign: `budgetAmount`, `budgetOrders`, `locInvoiceDetails`, `countryOrRegionServingStateReasons`
- ad group: `targetingDimensions` (v1 has `targeting`, in a different shape)

**v1 vocabulary:** `servingStateReasons` on campaigns and ad groups now uses v1's reason
codes, e.g. `AD_GROUPS_NOT_RUNNING` instead of `NO_AVAILABLE_AD_GROUPS`, and
`PAUSED_BY_USER` instead of `AD_GROUP_PAUSED_BY_USER`.

## Reports

- **Idle days:** v1 represents an idle day as a date-only entry. 4.0 expands each one
  into the explicit zero row v5 sent (all 798 such rows in the verification week were
  all-zero in v5). A *partly* missing entry still raises `MissingMetricError`.
- **Search-term low-volume rows:** v1 dropped v5's `other` flag. A null `searchTermText`
  marks the same rows (14/14 matched), so `is_low_volume` and `"(Low volume terms)"`
  behave as before.
- **Metric names:** `avgCPT`/`avgCPM` became `cpt`/`cpm`. The `avg_cpt`/`avg_cpm` columns
  are unchanged.
- **`*_raw` methods** return v1 rows (`metadata`, `totalMetrics`, `granularMetrics`), not
  v5 rows (`granularity`, `metrics`). Code that parses raw rows itself must be updated.
- **Time zone default:** `None` means the API default, ORTZ (each account's zone). This
  matched v5's behavior: daily rows matched 35/35 under ORTZ and 0/35 under UTC. Earlier
  READMEs said the default was UTC; that was wrong.
- **Lookback:** Apple's docs say DAILY reports must start within the last 90 days. That
  wasn't enforced on 2026-10-19 (a 140-day-old request succeeded), but it may be later.

## Impression share

v1 replaces v5's queued custom reports with a synchronous query.

- `get_impression_share_data()` keeps its signature. `name`, `poll_interval` and
  `max_wait` are ignored. `time_zone` must be `None` or `"UTC"`. `granularity="WEEKLY"`
  means v1's Sunday–Saturday weeks. When `adam_ids` is omitted, it uses every app
  promoted by the current org's campaigns, because v1 requires at least one.
- Output keeps the v5 column names (`date`, `adamId`, `searchPopularity`) alongside v1's
  (`day`, `promotedObjectId`, `searchPopularity1to5`).
- `create_impression_share_report()` and `get_impression_share_report()` raise
  `NotImplementedError`.

## Internals

Anything private changed:

- `BASE_URL` is `https://api.ads.apple.com/v1`.
- The `X-AP-Context` header is `adAccountId=…` instead of `orgId=…`.
- Responses use `result` instead of `data`.
- Pagination is `{offset, pageSize, totalCount}` instead of `{startIndex, itemsPerPage, totalResults}`.
- Report URLs are `/reports/apps/{campaigns,adgroups,keywords,searchterms}/query` with a
  `campaignId` filter, instead of `/reports/campaigns/{id}/…`.
- Request bodies use `timeRange`, `filters` and `sorting` instead of `startTime`/`endTime`/`selector`.

Callers that post v5 bodies through `_make_request` (for example, a hand-built search-term
request) must move to the public method or to the v1 request shape.

## Auth

v1 uses the same token endpoint (`appleid.apple.com/auth/oauth2/token`) and scope
(`searchadsorg`) as v5. Existing v5 API keys (client id, team id, key id, EC private key)
work unchanged; this was verified against the live API.
