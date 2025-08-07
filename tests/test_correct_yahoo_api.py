#!/usr/bin/env python3
"""
Test the correct Yahoo Finance API endpoints based on the working curl example.
"""

import requests
import json
import os

def _readConfigValue(key, default=""):
    """Read value from config.ini"""
    config_file = os.path.join("..", "privatesettings", "config.ini")
    if not os.path.exists(config_file):
        config_file = os.path.join("privatesettings", "config.ini")
    
    try:
        with open(config_file, "r") as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                # Check for exact key match
                if line.startswith(key + "="):
                    return line.split("=", 1)[1].strip()
    except Exception as e:
        print(f"Could not read {key} from config.ini: {e}")
    return default

def test_correct_endpoints():
    """Test the correct Yahoo Finance API endpoints"""
    
    api_key = _readConfigValue("YAHOO_FINANCE_API_KEY")
    api_host = _readConfigValue("YAHOO_API_HOST", "yahoo-finance15.p.rapidapi.com")
    
    if not api_key:
        print("Error: YAHOO_FINANCE_API_KEY not found in privatesettings/config.ini")
        return False
    
    headers = {
        'X-RapidAPI-Key': api_key,
        'X-RapidAPI-Host': api_host
    }
    
    print("=== Testing Correct Yahoo Finance API Endpoints ===\n")
    
    # Test different v1 API endpoints that might exist
    test_endpoints = [
        f"https://{api_host}/api/v1/markets/insider-trades",  # Known working
        f"https://{api_host}/api/v1/markets/quote",
        f"https://{api_host}/api/v1/markets/quotes", 
        f"https://{api_host}/api/v1/markets/stock",
        f"https://{api_host}/api/v1/markets/stocks",
        f"https://{api_host}/api/v1/quote",
        f"https://{api_host}/api/v1/quotes",
        f"https://{api_host}/api/v1/stock",
        f"https://{api_host}/api/v1/stocks",
    ]
    
    # Test with and without symbol parameter
    symbols_to_test = ["AAPL", "MSFT", "BP.L"]
    
    for endpoint in test_endpoints:
        print(f"Testing: {endpoint}")
        
        # Try without parameters first
        try:
            response = requests.get(endpoint, headers=headers, timeout=10)
            print(f"  No params - Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"  ✅ SUCCESS - Got data")
                if isinstance(data, dict):
                    print(f"  Keys: {list(data.keys())[:5]}")
                elif isinstance(data, list) and len(data) > 0:
                    print(f"  List with {len(data)} items")
                    if isinstance(data[0], dict):
                        print(f"  First item keys: {list(data[0].keys())[:5]}")
            elif response.status_code == 400:
                print(f"  ⚠️  Needs parameters - {response.text[:100]}")
            else:
                print(f"  ❌ Failed - {response.text[:100]}")
                
        except Exception as e:
            print(f"  ❌ Error: {e}")
        
        # Try with symbol parameter
        for symbol in symbols_to_test:
            try:
                # Try different parameter names
                param_variants = [
                    {'symbol': symbol},
                    {'symbols': symbol},
                    {'ticker': symbol},
                    {'q': symbol},
                    {'query': symbol}
                ]
                
                for params in param_variants:
                    response = requests.get(endpoint, headers=headers, params=params, timeout=5)
                    if response.status_code == 200:
                        data = response.json()
                        print(f"  ✅ SUCCESS with {symbol} using params {params}")
                        print(f"     Data preview: {str(data)[:200]}")
                        break
                    elif response.status_code != 404 and response.status_code != 400:
                        print(f"  Status {response.status_code} with {symbol} using {params}")
                        
            except Exception as e:
                pass  # Don't spam errors for parameter tests
        
        print()
    
    print("=== Summary ===")
    print("Look for endpoints that return 200 status codes to find working API calls.")

if __name__ == "__main__":
    test_correct_endpoints()
