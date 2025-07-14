# Integration Testing Guide

This guide covers how to run integration tests that make real API calls to Apple Search Ads.

## Overview

Integration tests verify that the client works correctly with the actual Apple Search Ads API. Unlike unit tests that use mocks, integration tests:

- Make real HTTP requests
- Test actual authentication flow
- Verify API response parsing
- Validate rate limiting
- Ensure multi-organization support works

## Prerequisites

1. **Apple Search Ads Account**
   - Active account with API access enabled
   - At least one organization
   - Ideally some campaigns with data (for report tests)

2. **API Credentials**
   - Client ID
   - Team ID  
   - Key ID
   - Private key (EC or RSA format in .pem file)

3. **Test Isolation** (Recommended)
   - Use a separate test account if possible
   - Or use read-only API credentials
   - Never use production credentials with write access

## Local Setup

### 1. Install Development Dependencies

```bash
pip install -e ".[dev]"
```

### 2. Configure Credentials

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` and add your credentials:

```bash
# Required credentials
APPLE_SEARCH_ADS_CLIENT_ID=your_client_id
APPLE_SEARCH_ADS_TEAM_ID=your_team_id
APPLE_SEARCH_ADS_KEY_ID=your_key_id
APPLE_SEARCH_ADS_PRIVATE_KEY_PATH=/path/to/private_key.pem

# Optional: specific org for testing
APPLE_SEARCH_ADS_ORG_ID=123456789
```

**Note**: The integration tests now use the standard environment variable names (without `_TEST_` prefix).

### 3. Load Environment Variables

```bash
# Using python-dotenv (recommended)
pip install python-dotenv

# Or export manually
export $(cat .env | xargs)
```

## Running Integration Tests

### Run All Integration Tests

```bash
pytest tests/test_integration.py -v
```

### Run Specific Test

```bash
pytest tests/test_integration.py::TestAppleSearchAdsIntegration::test_authentication_flow -v
```

### Run with Debug Output

```bash
pytest tests/test_integration.py -vv --log-cli-level=DEBUG
```

### Skip Slow Tests

```bash
pytest tests/test_integration.py -v -m "not slow"
```

## Test Coverage

The integration test suite covers:

### 1. **Authentication** (`test_authentication_flow`)
- JWT generation with real private key
- Token exchange with Apple's OAuth endpoint
- Token expiry handling

### 2. **Token Caching** (`test_token_caching`)
- Verifies token reuse
- Reduces unnecessary API calls

### 3. **Organizations** (`test_get_organizations`, `test_set_organization`)
- Fetching organization list
- Setting organization context
- Organization data structure

### 4. **Campaigns** (`test_get_campaigns`)
- Fetching campaign list
- Campaign data structure
- Empty campaign handling


### 5. **Ad Groups** (`test_get_adgroups`)
- Fetching ad groups for a campaign
- Ad group data structure
- Campaign relationship validation

### 6. **Reports** (`test_campaign_report_recent_data`)
- Fetching performance data
- DataFrame generation
- Data type validation

### 7. **Multi-Org Support** (`test_multi_organization_access`)
- Switching between organizations
- Isolated data per org

### 8. **Error Handling** (`test_error_handling_invalid_org`)
- Invalid organization handling
- API error responses

### 9. **Spend Analytics** (`test_daily_spend_functionality`, `test_spend_by_app_functionality`)
- Daily spend aggregation
- Per-app spend tracking
- Data aggregation accuracy

## CI/CD Integration

### GitHub Actions

The repository includes a workflow that runs integration tests:

- **Schedule**: Daily at 2 AM UTC
- **Triggers**: Manual dispatch, releases
- **Python versions**: 3.8 and 3.12
- **Notifications**: Creates issue on failure

### Setting up Secrets

In your GitHub repository settings:

1. Go to Settings → Secrets and variables → Actions
2. Add the following secrets:
   - `APPLE_TEST_CLIENT_ID`
   - `APPLE_TEST_TEAM_ID`
   - `APPLE_TEST_KEY_ID`
   - `APPLE_TEST_PRIVATE_KEY` (entire key file content)
   - `APPLE_TEST_ORG_ID` (optional)

### Manual Trigger

Run integration tests manually:

1. Go to Actions tab
2. Select "Integration Tests" workflow
3. Click "Run workflow"
4. Optionally enable debug logging

## Best Practices

### 1. **Test Data Management**
- Use recent dates for reports (API may not have old data)
- Account for time zones (use UTC when possible)
- Handle empty responses gracefully

### 2. **Rate Limiting**
- Tests respect the 1 request/second limit
- Don't run integration tests in parallel
- Use `@pytest.mark.slow` for time-consuming tests

### 3. **Error Handling**
- Expect and handle API maintenance windows
- Account for network issues
- Use proper assertions for optional data

### 4. **Security**
- Never commit credentials
- Use separate test account
- Rotate test credentials regularly
- Use read-only access when possible

### 5. **Test Isolation**
- Tests shouldn't depend on specific data
- Clean up any created resources
- Use unique identifiers where needed

## Troubleshooting

### Tests Skip with "requires credentials"

Ensure all required environment variables are set:

```python
import os
required = [
    'APPLE_SEARCH_ADS_CLIENT_ID',
    'APPLE_SEARCH_ADS_TEAM_ID', 
    'APPLE_SEARCH_ADS_KEY_ID'
]
for var in required:
    print(f"{var}: {'✓' if os.environ.get(var) else '✗'}")
```

### Authentication Failures

1. Verify credentials are correct
2. Check private key format (should include headers)
3. Ensure key hasn't expired
4. Verify team has API access enabled

### Empty Data

1. Check if account has campaigns
2. Use recent date ranges
3. Verify organization has data
4. Account for time zone differences

### Rate Limit Errors

1. Don't run tests in parallel
2. Check for other processes using API
3. Wait between test runs
4. Use the built-in rate limiting

## Example Test Run

```bash
$ pytest tests/test_integration.py -v

========================== test session starts ==========================
platform darwin -- Python 3.9.6, pytest-8.3.5
collected 11 items

tests/test_integration.py::TestAppleSearchAdsIntegration::test_authentication_flow PASSED
tests/test_integration.py::TestAppleSearchAdsIntegration::test_token_caching PASSED
tests/test_integration.py::TestAppleSearchAdsIntegration::test_get_organizations PASSED
tests/test_integration.py::TestAppleSearchAdsIntegration::test_set_organization PASSED
tests/test_integration.py::TestAppleSearchAdsIntegration::test_get_campaigns PASSED
tests/test_integration.py::TestAppleSearchAdsIntegration::test_get_adgroups PASSED
tests/test_integration.py::TestAppleSearchAdsIntegration::test_campaign_report_recent_data PASSED
tests/test_integration.py::TestAppleSearchAdsIntegration::test_multi_organization_access PASSED
tests/test_integration.py::TestAppleSearchAdsIntegration::test_error_handling_invalid_org PASSED
tests/test_integration.py::TestAppleSearchAdsIntegration::test_daily_spend_functionality PASSED
tests/test_integration.py::TestAppleSearchAdsIntegration::test_spend_by_app_functionality PASSED

========================== 11 passed in 27.15s ==========================
```

## Next Steps

1. **Monitor Results**: Check GitHub Actions for scheduled test runs
2. **Add Custom Tests**: Extend the suite for your specific use cases
3. **Performance Testing**: Add benchmarks for large datasets
4. **Stress Testing**: Test behavior under high load