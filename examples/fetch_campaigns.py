#!/usr/bin/env python3
"""
Campaign fetching example for Apple Search Ads Python Client.

This example demonstrates how to fetch and analyze campaign data.
"""

import os
from datetime import datetime, timedelta
from apple_search_ads import AppleSearchAdsClient


def main():
    # Initialize client with explicit credentials
    client = AppleSearchAdsClient(
        client_id=os.environ.get('APPLE_SEARCH_ADS_CLIENT_ID'),
        team_id=os.environ.get('APPLE_SEARCH_ADS_TEAM_ID'),
        key_id=os.environ.get('APPLE_SEARCH_ADS_KEY_ID'),
        private_key_path=os.environ.get('APPLE_SEARCH_ADS_PRIVATE_KEY_PATH')
    )
    
    print("🔍 Fetching Apple Search Ads Campaigns")
    print("=" * 60)
    
    # Get campaigns from all organizations
    print("\nFetching campaigns from all organizations...")
    all_campaigns = client.get_all_campaigns()
    
    print(f"\nFound {len(all_campaigns)} total campaigns")
    
    # Analyze campaigns by status
    status_counts = {}
    for campaign in all_campaigns:
        status = campaign.get('status', 'UNKNOWN')
        status_counts[status] = status_counts.get(status, 0) + 1
    
    print("\n📊 Campaigns by Status:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")
    
    # Show active campaigns
    active_campaigns = [c for c in all_campaigns if c.get('status') == 'ENABLED']
    
    if active_campaigns:
        print(f"\n✅ Active Campaigns ({len(active_campaigns)} total):")
        print("-" * 60)
        
        # Group by organization
        campaigns_by_org = {}
        for campaign in active_campaigns:
            org_name = campaign.get('org_name', 'Unknown Org')
            if org_name not in campaigns_by_org:
                campaigns_by_org[org_name] = []
            campaigns_by_org[org_name].append(campaign)
        
        for org_name, campaigns in campaigns_by_org.items():
            print(f"\n{org_name} ({len(campaigns)} campaigns):")
            
            for campaign in campaigns[:5]:  # Show first 5 per org
                adam_id = campaign.get('adamId', 'N/A')
                print(f"  - {campaign.get('name', 'Unnamed')} (App ID: {adam_id})")
            
            if len(campaigns) > 5:
                print(f"  ... and {len(campaigns) - 5} more")
    
    # Get campaign performance for active campaigns
    if active_campaigns:
        print("\n📈 Fetching performance data for active campaigns...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=7)
        
        try:
            report_df = client.get_campaign_report(
                start_date=start_date,
                end_date=end_date,
                granularity="DAILY"
            )
            
            if not report_df.empty:
                # Top campaigns by spend
                top_campaigns = report_df.groupby('campaign_name')['spend'].sum().sort_values(ascending=False).head(10)
                
                print("\n💰 Top 10 Campaigns by Spend (Last 7 days):")
                print("-" * 60)
                
                for campaign_name, spend in top_campaigns.items():
                    print(f"  {campaign_name}: ${spend:,.2f}")
                
                # Performance summary
                total_spend = report_df['spend'].sum()
                total_installs = report_df['installs'].sum()
                total_impressions = report_df['impressions'].sum()
                
                print(f"\n📊 Overall Performance (Last 7 days):")
                print(f"  Total Spend: ${total_spend:,.2f}")
                print(f"  Total Installs: {total_installs:,}")
                print(f"  Total Impressions: {total_impressions:,}")
                
                if total_installs > 0:
                    print(f"  Average CPI: ${(total_spend / total_installs):.2f}")
            else:
                print("No performance data available for the last 7 days")
                
        except Exception as e:
            print(f"Error fetching performance data: {e}")
    
    # Show campaigns with details
    print("\n🔍 Campaign Details Sample:")
    print("-" * 60)
    
    # Get campaigns with full details
    campaigns_with_details = client.get_campaigns_with_details(fetch_all_orgs=True)
    
    # Show first 3 campaigns with full details
    for i, campaign in enumerate(campaigns_with_details[:3]):
        print(f"\nCampaign {i+1}:")
        print(f"  Name: {campaign.get('name', 'N/A')}")
        print(f"  ID: {campaign.get('id', 'N/A')}")
        print(f"  Status: {campaign.get('status', 'N/A')}")
        print(f"  Adam ID (App): {campaign.get('adamId', 'N/A')}")
        print(f"  Budget: {campaign.get('budgetAmount', {}).get('amount', 'N/A')}")
        print(f"  Daily Budget: {campaign.get('dailyBudgetAmount', {}).get('amount', 'N/A')}")
        print(f"  Organization: {campaign.get('org_name', 'N/A')}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()