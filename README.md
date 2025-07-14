# Apple Search Ads Python Client

A Python client library for Apple Search Ads API v5, providing a simple and intuitive interface for managing and reporting on Apple Search Ads campaigns.

## Features

- 🔐 OAuth2 authentication with JWT
- 📊 Campaign performance reporting
- 🏢 Multi-organization support
- 💰 Spend tracking by app
- ⚡ Built-in rate limiting
- 🐼 Pandas DataFrames for easy data manipulation
- 🔄 Automatic token refresh
- 🎯 Type hints for better IDE support
- ✅ 100% test coverage

## Installation

```bash
pip install apple-search-ads-client
```

## Quick Start

```python
from apple_search_ads import AppleSearchAdsClient

# Initialize the client
client = AppleSearchAdsClient(
    client_id="your_client_id",
    team_id="your_team_id",
    key_id="your_key_id",
    private_key_path="/path/to/private_key.p8"
)

# Get all campaigns
campaigns = client.get_campaigns()

# Get daily spend for the last 30 days
spend_df = client.get_daily_spend(days=30)
print(spend_df)
```

## Authentication

### Prerequisites

1. An Apple Search Ads account with API access
2. API credentials from the Apple Search Ads UI:
   - Client ID
   - Team ID
   - Key ID
   - Private key file (.p8)

### Setting up credentials

You can provide credentials in three ways:

#### 1. Direct parameters (recommended)

```python
client = AppleSearchAdsClient(
    client_id="your_client_id",
    team_id="your_team_id",
    key_id="your_key_id",
    private_key_path="/path/to/private_key.p8"
)
```

#### 2. Environment variables

```bash
export APPLE_SEARCH_ADS_CLIENT_ID="your_client_id"
export APPLE_SEARCH_ADS_TEAM_ID="your_team_id"
export APPLE_SEARCH_ADS_KEY_ID="your_key_id"
export APPLE_SEARCH_ADS_PRIVATE_KEY_PATH="/path/to/private_key.p8"
```

```python
client = AppleSearchAdsClient()  # Will use environment variables
```

#### 3. Private key content

```python
# Useful for environments where file access is limited
with open("private_key.p8", "r") as f:
    private_key_content = f.read()

client = AppleSearchAdsClient(
    client_id="your_client_id",
    team_id="your_team_id",
    key_id="your_key_id",
    private_key_content=private_key_content
)
```

## Usage Examples

### Get all organizations

```python
# List all organizations you have access to
orgs = client.get_all_organizations()
for org in orgs:
    print(f"{org['orgName']} - {org['orgId']}")
```

### Get campaign performance report

```python
from datetime import datetime, timedelta

# Get campaign performance for the last 7 days
end_date = datetime.now()
start_date = end_date - timedelta(days=7)

report_df = client.get_campaign_report(
    start_date=start_date,
    end_date=end_date,
    granularity="DAILY"  # Options: DAILY, WEEKLY, MONTHLY
)

# Display key metrics
print(report_df[['date', 'campaign_name', 'spend', 'installs', 'taps']])
```

### Track spend by app

```python
# Get daily spend grouped by app
app_spend_df = client.get_daily_spend_by_app(
    start_date="2024-01-01",
    end_date="2024-01-31",
    fetch_all_orgs=True  # Fetch from all organizations
)

# Group by app and sum
app_totals = app_spend_df.groupby('app_id').agg({
    'spend': 'sum',
    'installs': 'sum',
    'impressions': 'sum'
}).round(2)

print(app_totals)
```

### Get campaigns from all organizations

```python
# Fetch campaigns across all organizations
all_campaigns = client.get_all_campaigns()

# Filter active campaigns
active_campaigns = [c for c in all_campaigns if c['status'] == 'ENABLED']

print(f"Found {len(active_campaigns)} active campaigns across all orgs")
```

### Working with specific organization

```python
# Get campaigns for a specific org
org_id = "123456"
campaigns = client.get_campaigns(org_id=org_id)

# The client will use this org for subsequent requests
```

### Working with ad groups

```python
# Get ad groups for a campaign
campaign_id = "1234567890"
adgroups = client.get_adgroups(campaign_id)

for adgroup in adgroups:
    print(f"Ad Group: {adgroup['name']} (Status: {adgroup['status']})")
```

## API Reference

### Client initialization

```python
AppleSearchAdsClient(
    client_id: Optional[str] = None,
    team_id: Optional[str] = None,
    key_id: Optional[str] = None,
    private_key_path: Optional[str] = None,
    private_key_content: Optional[str] = None,
    org_id: Optional[str] = None
)
```

### Methods

#### Organizations

- `get_all_organizations()` - Get all organizations
- `get_campaigns(org_id: Optional[str] = None)` - Get campaigns for an organization
- `get_all_campaigns()` - Get campaigns from all organizations

#### Reporting

- `get_campaign_report(start_date, end_date, granularity="DAILY")` - Get campaign performance report
- `get_daily_spend(days=30, fetch_all_orgs=True)` - Get daily spend for the last N days
- `get_daily_spend_with_dates(start_date, end_date, fetch_all_orgs=True)` - Get daily spend for date range
- `get_daily_spend_by_app(start_date, end_date, fetch_all_orgs=True)` - Get spend grouped by app

#### Campaign Management

- `get_campaigns_with_details(fetch_all_orgs=True)` - Get campaigns with app details
- `get_adgroups(campaign_id)` - Get ad groups for a specific campaign

## DataFrame Output

All reporting methods return pandas DataFrames for easy data manipulation:

```python
# Example: Calculate weekly totals
daily_spend = client.get_daily_spend(days=30)
daily_spend['week'] = pd.to_datetime(daily_spend['date']).dt.isocalendar().week
weekly_totals = daily_spend.groupby('week')['spend'].sum()
```

## Rate Limiting

The client includes built-in rate limiting to respect Apple's API limits (10 requests per second). You don't need to implement any additional rate limiting.

## Error Handling

```python
from apple_search_ads.exceptions import (
    AuthenticationError,
    RateLimitError,
    OrganizationNotFoundError
)

try:
    campaigns = client.get_campaigns()
except AuthenticationError as e:
    print(f"Authentication failed: {e}")
except RateLimitError as e:
    print(f"Rate limit exceeded: {e}")
except Exception as e:
    print(f"An error occurred: {e}")
```

## Best Practices

1. **Reuse client instances**: Create one client and reuse it for multiple requests
2. **Use date ranges wisely**: Large date ranges may result in slower responses
3. **Cache organization IDs**: If working with specific orgs frequently, cache their IDs
4. **Monitor rate limits**: Although built-in rate limiting is included, be mindful of your usage
5. **Use DataFrame operations**: Leverage pandas for data aggregation and analysis

## Requirements

- Python 3.8 or higher
- See `requirements.txt` for package dependencies

## Testing

This project maintains **100% test coverage**. The test suite includes:

- Unit tests with mocked API responses
- Exception handling tests
- Edge case coverage
- Legacy API format compatibility tests
- Comprehensive integration tests

### Running Tests

```bash
# Run all tests with coverage report
pytest tests -v --cov=apple_search_ads --cov-report=term-missing

# Run tests in parallel for faster execution
pytest tests -n auto

# Generate HTML coverage report
pytest tests --cov=apple_search_ads --cov-report=html

# Run integration tests (requires credentials)
pytest tests/test_integration.py -v
```

For detailed testing documentation, see [TESTING.md](TESTING.md).

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- 🐛 Issues: [GitHub Issues](https://github.com/bickster/apple-search-ads-python/issues)
- 📖 Documentation: [Read the Docs](https://apple-search-ads-python.readthedocs.io/)

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a list of changes.

## Acknowledgments

- Apple for providing the Search Ads API
- The Python community for excellent libraries used in this project