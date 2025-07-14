# Testing Documentation

This document provides comprehensive information about the testing infrastructure for the Apple Search Ads Python Client.

## Table of Contents

1. [Testing Improvements](#testing-improvements)
2. [Running Tests](#running-tests)
3. [Understanding Coverage Reports](#understanding-coverage-reports)
4. [Test Structure and Organization](#test-structure-and-organization)
5. [Guidelines for Adding New Tests](#guidelines-for-adding-new-tests)

## Testing Improvements

The Apple Search Ads Python Client includes a robust testing suite with the following improvements:

### 100% Code Coverage
- All production code is covered by unit tests
- Both happy path and error scenarios are tested
- Edge cases and boundary conditions are thoroughly tested

### Comprehensive Test Suite
- **Authentication Testing**: Tests for JWT token generation, OAuth2 flow, and credential handling
- **API Request Testing**: Mock-based tests for all API endpoints
- **Error Handling**: Tests for all custom exceptions and error scenarios
- **Data Processing**: Tests for DataFrame generation and data transformations
- **Environment Variable Support**: Tests for configuration via environment variables

### Testing Infrastructure
- **pytest**: Modern testing framework with powerful fixtures and parametrization
- **pytest-cov**: Coverage reporting integrated into test runs
- **pytest-mock**: Advanced mocking capabilities
- **Fixtures**: Reusable test data and mock objects defined in `conftest.py`

### CI/CD Integration
- Tests run automatically on GitHub Actions for Python 3.8-3.12
- Coverage reports are generated for every test run
- Tests must pass before merging pull requests

## Running Tests

### Prerequisites

Install the development dependencies:

```bash
pip install -r requirements-dev.txt
```

Or install the package with dev extras:

```bash
pip install -e ".[dev]"
```

### Running All Tests

Run all tests with coverage report:

```bash
pytest tests -v --cov=apple_search_ads --cov-report=html --cov-report=term-missing
```

### Running Specific Tests

Run a specific test file:

```bash
pytest tests/test_client.py -v
```

Run a specific test class:

```bash
pytest tests/test_client.py::TestAppleSearchAdsClient -v
```

Run a specific test method:

```bash
pytest tests/test_client.py::TestAppleSearchAdsClient::test_client_initialization_with_params -v
```

### Running Tests with Different Options

Run tests without coverage:

```bash
pytest tests -v
```

Run tests with minimal output:

```bash
pytest tests -q
```

Run tests and stop on first failure:

```bash
pytest tests -x
```

Run tests with print statements visible:

```bash
pytest tests -s
```

### Running Tests in Parallel

Install pytest-xdist for parallel execution:

```bash
pip install pytest-xdist
pytest tests -n auto  # Uses all available CPU cores
```

## Understanding Coverage Reports

### Terminal Coverage Report

When you run tests with `--cov-report=term-missing`, you'll see output like:

```
---------- coverage: platform darwin, python 3.11.0-final-0 ----------
Name                            Stmts   Miss  Cover   Missing
-------------------------------------------------------------
src/apple_search_ads/__init__.py     5      0   100%
src/apple_search_ads/client.py     245      0   100%
src/apple_search_ads/exceptions.py   6      0   100%
-------------------------------------------------------------
TOTAL                              256      0   100%
```

- **Stmts**: Number of executable statements
- **Miss**: Number of statements not covered by tests
- **Cover**: Percentage of code covered
- **Missing**: Line numbers of uncovered code

### HTML Coverage Report

The HTML report is generated in the `htmlcov/` directory:

```bash
# Generate HTML report
pytest tests --cov=apple_search_ads --cov-report=html

# Open the report (macOS)
open htmlcov/index.html

# Open the report (Linux)
xdg-open htmlcov/index.html

# Open the report (Windows)
start htmlcov/index.html
```

The HTML report provides:
- **Overview**: Summary of coverage for all files
- **File Details**: Click on any file to see line-by-line coverage
- **Color Coding**:
  - Green: Covered lines
  - Red: Uncovered lines
  - Yellow: Partially covered branches

### Coverage Configuration

Coverage is configured in `pyproject.toml`:

```toml
[tool.coverage.run]
source = ["src/apple_search_ads"]
omit = ["*/tests/*", "*/test_*.py"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise AssertionError",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]
```

## Test Structure and Organization

### Directory Structure

```
tests/
├── __init__.py          # Makes tests a package
├── conftest.py          # Shared fixtures and configuration
├── test_client.py       # Tests for AppleSearchAdsClient
└── test_exceptions.py   # Tests for exception classes
```

### Test Files

#### `conftest.py`
Contains shared fixtures used across test files:
- `mock_response`: Creates mock HTTP response objects
- `sample_org_data`: Sample organization API response data
- `sample_campaign_data`: Sample campaign API response data
- `sample_report_data`: Sample report API response data

#### `test_client.py`
Tests for the main client class, organized into logical groups:
- **Initialization Tests**: Client creation with various credential sources
- **Authentication Tests**: JWT generation and token management
- **API Request Tests**: HTTP request handling and error scenarios
- **Organization Tests**: Multi-org support and org ID management
- **Campaign Tests**: Campaign fetching and filtering
- **Report Tests**: Performance data and DataFrame generation
- **Integration Tests**: End-to-end scenarios with multiple API calls

#### `test_exceptions.py`
Tests for all custom exception classes:
- Exception instantiation
- Error message handling
- Inheritance hierarchy verification

### Test Patterns

#### Mocking External Dependencies

```python
@patch('requests.post')
def test_get_access_token(self, mock_post, client):
    """Test access token retrieval."""
    mock_response = Mock()
    mock_response.json.return_value = {"access_token": "test_token"}
    mock_post.return_value = mock_response
    
    token = client._get_access_token()
    assert token == "test_token"
```

#### Testing Error Scenarios

```python
def test_client_initialization_missing_credentials(self):
    """Test client initialization with missing credentials."""
    with pytest.raises(ValueError) as exc_info:
        AppleSearchAdsClient(client_id="test")
    assert "Missing required credentials" in str(exc_info.value)
```

#### Using Fixtures

```python
def test_api_call(self, client, sample_campaign_data):
    """Test API call with fixture data."""
    with patch.object(client, '_make_request') as mock_request:
        mock_request.return_value = sample_campaign_data
        campaigns = client.get_campaigns()
        assert len(campaigns) == 2
```

## Guidelines for Adding New Tests

### 1. Follow Existing Patterns

- Use the same test class structure as existing tests
- Follow naming conventions: `test_<feature>_<scenario>`
- Group related tests in the same test class

### 2. Write Descriptive Test Names

```python
# Good
def test_get_campaigns_with_org_id_parameter(self):
    """Test fetching campaigns with specific org_id parameter."""

# Bad
def test_campaigns(self):
    """Test campaigns."""
```

### 3. Use Fixtures for Common Data

Create fixtures in `conftest.py` for data used across multiple tests:

```python
@pytest.fixture
def sample_new_feature_data():
    """Sample data for new feature."""
    return {
        "data": {
            "id": "123",
            "name": "Test Feature"
        }
    }
```

### 4. Test Both Success and Failure Cases

For each new feature, test:
- Happy path (normal operation)
- Error conditions (invalid input, API errors)
- Edge cases (empty data, None values)
- Boundary conditions (limits, timeouts)

### 5. Mock External Dependencies

Never make real API calls in tests:

```python
@patch.object(AppleSearchAdsClient, '_make_request')
def test_new_api_endpoint(self, mock_request, client):
    """Test new API endpoint."""
    mock_request.return_value = {"data": "response"}
    result = client.new_endpoint()
    mock_request.assert_called_once_with(
        expected_url,
        method="GET"
    )
```

### 6. Test Data Transformations

If your feature processes data:

```python
def test_data_transformation(self, client):
    """Test that data is transformed correctly."""
    input_data = {...}
    expected_output = {...}
    
    result = client.transform_data(input_data)
    assert result == expected_output
```

### 7. Use Parametrized Tests

For testing multiple scenarios with similar logic:

```python
@pytest.mark.parametrize("status,expected", [
    ("ENABLED", True),
    ("PAUSED", False),
    ("DELETED", False),
])
def test_campaign_is_active(self, status, expected):
    """Test campaign active status logic."""
    campaign = {"status": status}
    assert is_active(campaign) == expected
```

### 8. Document Complex Test Logic

Add comments for non-obvious test setup:

```python
def test_token_refresh_on_expiry(self, client):
    """Test that token is refreshed when expired."""
    # Set token to expire in 1 second
    client._token_expiry = time.time() + 1
    client._token = "old_token"
    
    # Wait for token to expire
    time.sleep(2)
    
    # Next request should trigger refresh
    with patch.object(client, '_generate_client_secret'):
        client._get_access_token()
```

### 9. Maintain Test Independence

Each test should be independent and not rely on others:

```python
class TestFeature:
    def setup_method(self):
        """Reset state before each test."""
        self.client = AppleSearchAdsClient(...)
    
    def teardown_method(self):
        """Clean up after each test."""
        # Clean up any test artifacts
```

### 10. Update Coverage

After adding new code, ensure it's covered:

```bash
# Run tests and check coverage
pytest tests --cov=apple_search_ads --cov-report=term-missing

# Look for any uncovered lines in your new code
# Add tests to cover any missing lines
```

### Example: Adding a Test for a New Method

Let's say you've added a new method `get_ad_groups()` to the client:

```python
class TestAppleSearchAdsClient:
    @patch.object(AppleSearchAdsClient, '_make_request')
    def test_get_ad_groups(self, mock_request, client):
        """Test fetching ad groups."""
        # Arrange
        expected_data = {
            "data": [
                {"id": "1", "name": "Ad Group 1", "campaignId": "100"},
                {"id": "2", "name": "Ad Group 2", "campaignId": "100"}
            ]
        }
        mock_request.return_value = expected_data
        
        # Act
        ad_groups = client.get_ad_groups(campaign_id="100")
        
        # Assert
        assert len(ad_groups) == 2
        assert ad_groups[0]["name"] == "Ad Group 1"
        mock_request.assert_called_once_with(
            f"{client.BASE_URL}/campaigns/100/adgroups",
            params={"limit": 1000}
        )
    
    def test_get_ad_groups_empty_response(self, client):
        """Test get_ad_groups with empty response."""
        with patch.object(client, '_make_request') as mock_request:
            mock_request.return_value = {"data": []}
            ad_groups = client.get_ad_groups(campaign_id="100")
            assert ad_groups == []
    
    def test_get_ad_groups_invalid_campaign_id(self, client):
        """Test get_ad_groups with invalid campaign ID."""
        with pytest.raises(ValueError) as exc_info:
            client.get_ad_groups(campaign_id=None)
        assert "campaign_id is required" in str(exc_info.value)
```

## Continuous Integration

Tests are automatically run on GitHub Actions for:
- Every push to the main branch
- Every pull request
- Multiple Python versions (3.8, 3.9, 3.10, 3.11, 3.12)
- Multiple operating systems (Ubuntu, macOS, Windows)

The CI configuration is in `.github/workflows/tests.yml`.

## Best Practices Summary

1. **Write tests first** (TDD) when adding new features
2. **Keep tests fast** by using mocks instead of real API calls
3. **Test one thing** per test method
4. **Use descriptive names** that explain what is being tested
5. **Follow AAA pattern**: Arrange, Act, Assert
6. **Don't test implementation details**, test behavior
7. **Keep test data minimal** but realistic
8. **Update tests** when changing existing functionality
9. **Review test output** to ensure tests are meaningful
10. **Maintain high coverage** but focus on quality over quantity

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure you've installed the package in development mode:
   ```bash
   pip install -e .
   ```

2. **Coverage Not Working**: Install pytest-cov:
   ```bash
   pip install pytest-cov
   ```

3. **Tests Hanging**: Check for missing mocks that might be making real API calls

4. **Flaky Tests**: Look for time-dependent code or race conditions

### Getting Help

- Check existing tests for examples
- Review pytest documentation: https://docs.pytest.org/
- Review coverage.py documentation: https://coverage.readthedocs.io/
- Open an issue on GitHub for test-related questions