#!/usr/bin/env python3
"""
Verify Apple Search Ads credentials are working correctly.
"""

import os
import sys

# Try to load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("Loaded credentials from .env file")
except ImportError:
    print("Note: python-dotenv not installed. Using environment variables only.")
    print("Install with: pip install python-dotenv")

# Add src to path to import the client
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from apple_search_ads import AppleSearchAdsClient

def verify_credentials():
    """Test that credentials work by attempting to authenticate and fetch organizations."""
    print("Apple Search Ads Credential Verification")
    print("=" * 50)
    
    # Check environment variables
    required_vars = [
        'APPLE_SEARCH_ADS_CLIENT_ID',
        'APPLE_SEARCH_ADS_TEAM_ID',
        'APPLE_SEARCH_ADS_KEY_ID',
        'APPLE_SEARCH_ADS_PRIVATE_KEY_PATH'
    ]
    
    print("\n1. Checking environment variables:")
    all_present = True
    for var in required_vars:
        value = os.environ.get(var)
        if value:
            print(f"   ✓ {var}: {value[:20]}...")
        else:
            print(f"   ✗ {var}: NOT SET")
            all_present = False
    
    if not all_present:
        print("\n❌ Missing required environment variables!")
        return False
    
    # Check private key file
    print("\n2. Checking private key file:")
    key_path = os.environ.get('APPLE_SEARCH_ADS_PRIVATE_KEY_PATH')
    if os.path.exists(key_path):
        print(f"   ✓ Private key exists at: {key_path}")
        with open(key_path, 'r') as f:
            content = f.read()
            if 'BEGIN PRIVATE KEY' in content or 'BEGIN EC PRIVATE KEY' in content or 'BEGIN RSA PRIVATE KEY' in content:
                print("   ✓ File appears to be a valid private key")
            else:
                print("   ✗ File doesn't appear to be a valid private key")
                return False
    else:
        print(f"   ✗ Private key not found at: {key_path}")
        return False
    
    # Try to create client and authenticate
    print("\n3. Testing authentication:")
    try:
        client = AppleSearchAdsClient()
        print("   ✓ Client created successfully")
        
        # Try to get access token
        token = client._get_access_token()
        print(f"   ✓ Access token obtained: {token[:20]}...")
        
        # Try to fetch organizations
        print("\n4. Fetching organizations:")
        orgs = client.get_all_organizations()
        
        if orgs:
            print(f"   ✓ Found {len(orgs)} organization(s):")
            for org in orgs:
                print(f"      - {org['orgName']} (ID: {org['orgId']})")
                if 'currency' in org:
                    print(f"        Currency: {org['currency']}")
                if 'paymentModel' in org:
                    print(f"        Payment Model: {org['paymentModel']}")
        else:
            print("   ⚠️  No organizations found (this might be normal for new accounts)")
        
        print("\n✅ Credentials verified successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Error during authentication: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    success = verify_credentials()
    sys.exit(0 if success else 1)