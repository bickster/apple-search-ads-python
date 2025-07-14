#!/usr/bin/env python3
"""
Basic usage example for Apple Search Ads Python Client.

This example demonstrates basic authentication and API calls.
"""

import os
from datetime import datetime, timedelta
from apple_search_ads import AppleSearchAdsClient


def main():
    # Initialize the client using environment variables
    # Make sure to set these environment variables:
    # - APPLE_SEARCH_ADS_CLIENT_ID
    # - APPLE_SEARCH_ADS_TEAM_ID
    # - APPLE_SEARCH_ADS_KEY_ID
    # - APPLE_SEARCH_ADS_PRIVATE_KEY_PATH
    
    client = AppleSearchAdsClient()
    
    # Get all organizations
    print("Fetching organizations...")
    organizations = client.get_all_organizations()
    
    print(f"\nFound {len(organizations)} organizations:")
    for org in organizations:
        print(f"  - {org['orgName']} (ID: {org['orgId']})")
    
    # Get campaigns from the first organization
    if organizations:
        print(f"\nFetching campaigns...")
        campaigns = client.get_campaigns()
        
        print(f"\nFound {len(campaigns)} campaigns:")
        for campaign in campaigns[:5]:  # Show first 5
            print(f"  - {campaign.get('name', 'N/A')} (ID: {campaign['id']}, Status: {campaign.get('status', 'N/A')})")
        
        if len(campaigns) > 5:
            print(f"  ... and {len(campaigns) - 5} more")
    
    # Get daily spend for the last 7 days
    print("\nFetching daily spend for the last 7 days...")
    daily_spend = client.get_daily_spend(days=7)
    
    if not daily_spend.empty:
        print("\nDaily spend summary:")
        print(daily_spend[['date', 'spend', 'installs', 'clicks']].to_string(index=False))
        
        total_spend = daily_spend['spend'].sum()
        total_installs = daily_spend['installs'].sum()
        
        print(f"\nTotal spend: ${total_spend:,.2f}")
        print(f"Total installs: {total_installs:,}")
        
        if total_installs > 0:
            avg_cpi = total_spend / total_installs
            print(f"Average CPI: ${avg_cpi:.2f}")
    else:
        print("No spend data found for the last 7 days")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()