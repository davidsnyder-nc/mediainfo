#!/usr/bin/env python3
"""Debug script to test Plex API calls and understand data retrieval issues"""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import urljoin

def test_plex_api():
    # Your configuration
    plex_url = "http://localhost:32400"  # Update this if different
    plex_token = "iwn81nkfedl029j8tk24nh6vv"
    
    session = requests.Session()
    headers = {'X-Plex-Token': plex_token}
    
    print("=== Testing Plex API ===")
    
    # Test 1: Basic connection
    try:
        url = urljoin(plex_url, '/identity')
        response = session.get(url, headers=headers, timeout=30)
        print(f"Identity test: {response.status_code}")
        if response.status_code == 200:
            print("✓ Basic connection successful")
        else:
            print(f"✗ Connection failed: {response.text}")
            return
    except Exception as e:
        print(f"✗ Connection error: {e}")
        return
    
    # Test 2: Get libraries
    try:
        url = urljoin(plex_url, '/library/sections')
        response = session.get(url, headers=headers, timeout=30)
        print(f"\nLibraries test: {response.status_code}")
        
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            print("✓ Libraries found:")
            
            for library in root.findall('.//Directory'):
                lib_key = library.get('key')
                lib_title = library.get('title')
                lib_type = library.get('type')
                print(f"  - Library {lib_key}: {lib_title} (type: {lib_type})")
                
                # Test recent content for movie/show libraries
                if lib_type in ['movie', 'show']:
                    print(f"    Testing recent content for {lib_title}...")
                    recent_url = urljoin(plex_url, f'/library/sections/{lib_key}/recentlyAdded')
                    recent_response = session.get(recent_url, headers=headers, timeout=30)
                    
                    if recent_response.status_code == 200:
                        recent_root = ET.fromstring(recent_response.content)
                        items = recent_root.findall('.//Video')
                        print(f"    Found {len(items)} recently added items")
                        
                        # Show details of first few items
                        today = datetime.now().date()
                        yesterday = today - timedelta(days=1)
                        recent_count = 0
                        
                        for i, item in enumerate(items[:5]):  # Show first 5 items
                            title = item.get('title', 'Unknown')
                            year = item.get('year', 'Unknown')
                            added_at = item.get('addedAt')
                            
                            if added_at:
                                added_date = datetime.fromtimestamp(int(added_at)).date()
                                print(f"      {i+1}. {title} ({year}) - Added: {added_date}")
                                
                                if added_date >= yesterday:
                                    recent_count += 1
                            else:
                                print(f"      {i+1}. {title} ({year}) - Added: No timestamp")
                        
                        print(f"    Items added since yesterday: {recent_count}")
                    else:
                        print(f"    ✗ Failed to get recent content: {recent_response.status_code}")
        else:
            print(f"✗ Failed to get libraries: {response.text}")
    
    except Exception as e:
        print(f"✗ Library error: {e}")

if __name__ == '__main__':
    test_plex_api()