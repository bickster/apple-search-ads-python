#!/usr/bin/env python3
"""
Per-app spend tracking example for Apple Search Ads Python Client.

This example shows how to track advertising spend by individual apps.
"""

import os
from datetime import datetime, timedelta
import pandas as pd
from apple_search_ads import AppleSearchAdsClient


def main():
    # Initialize the client
    client = AppleSearchAdsClient(
        client_id=os.environ.get('APPLE_SEARCH_ADS_CLIENT_ID'),
        team_id=os.environ.get('APPLE_SEARCH_ADS_TEAM_ID'),
        key_id=os.environ.get('APPLE_SEARCH_ADS_KEY_ID'),
        private_key_path=os.environ.get('APPLE_SEARCH_ADS_PRIVATE_KEY_PATH')
    )
    
    # Define date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    print(f"Analyzing per-app spend from {start_date.date()} to {end_date.date()}")
    print("=" * 60)
    
    # Get per-app spend data
    print("\nFetching per-app spend data...")
    app_spend_df = client.get_daily_spend_by_app(
        start_date=start_date,
        end_date=end_date,
        fetch_all_orgs=True  # Fetch from all organizations
    )
    
    if app_spend_df.empty:
        print("No spend data found for the specified period")
        return
    
    # Aggregate by app
    print("\n📊 SPEND BY APP (Last 30 days)")
    print("-" * 60)
    
    app_summary = app_spend_df.groupby('app_id').agg({
        'spend': 'sum',
        'impressions': 'sum',
        'clicks': 'sum',
        'installs': 'sum',
        'campaigns': 'max'
    }).round(2)
    
    # Calculate metrics
    app_summary['CPI'] = (app_summary['spend'] / app_summary['installs']).round(2)
    app_summary['CTR'] = ((app_summary['clicks'] / app_summary['impressions']) * 100).round(2)
    app_summary['CVR'] = ((app_summary['installs'] / app_summary['clicks']) * 100).round(2)
    
    # Sort by spend descending
    app_summary = app_summary.sort_values('spend', ascending=False)
    
    # Display results
    for app_id, row in app_summary.iterrows():
        print(f"\nApp ID: {app_id}")
        print(f"  Total Spend: ${row['spend']:,.2f}")
        print(f"  Installs: {row['installs']:,}")
        print(f"  CPI: ${row['CPI']}")
        print(f"  CTR: {row['CTR']}%")
        print(f"  CVR: {row['CVR']}%")
        print(f"  Active Campaigns: {int(row['campaigns'])}")
    
    # Daily trend for top app
    print("\n📈 DAILY TREND (Top spending app)")
    print("-" * 60)
    
    top_app = app_summary.index[0]
    top_app_data = app_spend_df[app_spend_df['app_id'] == top_app].copy()
    
    # Show last 7 days
    recent_data = top_app_data.tail(7)
    
    print(f"\nApp ID: {top_app}")
    print("\nDate         Spend      Installs   CPI")
    print("-" * 40)
    
    for _, row in recent_data.iterrows():
        cpi = row['spend'] / row['installs'] if row['installs'] > 0 else 0
        print(f"{row['date']}   ${row['spend']:7.2f}   {int(row['installs']):8}   ${cpi:6.2f}")
    
    # Summary statistics
    print("\n📊 OVERALL SUMMARY")
    print("-" * 60)
    
    total_spend = app_spend_df['spend'].sum()
    total_installs = app_spend_df['installs'].sum()
    total_clicks = app_spend_df['clicks'].sum()
    total_impressions = app_spend_df['impressions'].sum()
    unique_apps = app_spend_df['app_id'].nunique()
    
    print(f"Total Apps: {unique_apps}")
    print(f"Total Spend: ${total_spend:,.2f}")
    print(f"Total Installs: {total_installs:,}")
    print(f"Overall CPI: ${(total_spend / total_installs):.2f}" if total_installs > 0 else "Overall CPI: N/A")
    print(f"Overall CTR: {(total_clicks / total_impressions * 100):.2f}%" if total_impressions > 0 else "Overall CTR: N/A")
    print(f"Overall CVR: {(total_installs / total_clicks * 100):.2f}%" if total_clicks > 0 else "Overall CVR: N/A")
    
    # Export to CSV
    output_file = "app_spend_summary.csv"
    app_summary.to_csv(output_file)
    print(f"\n💾 Summary exported to {output_file}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()