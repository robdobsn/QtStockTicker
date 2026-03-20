#!/usr/bin/env python3

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

# Test the Yahoo Finance API configuration
def test_yahoo_api():
    api_key = _readConfigValue("YAHOO_FINANCE_API_KEY")
    api_host = _readConfigValue("YAHOO_API_HOST", "yahoo-finance15.p.rapidapi.com")
    
    if not api_key:
        print("Error: YAHOO_FINANCE_API_KEY not found in privatesettings/config.ini")
        return False
    
    headers = {
        'X-RapidAPI-Key': api_key,
        'X-RapidAPI-Host': api_host
    }
    
    # Test with a simple US symbol first
    symbol = "AAPL"
    
    print(f"Testing Yahoo Finance API with symbol: {symbol}")
    print(f"API Host: {api_host}")
    print(f"Headers: {headers}")
    
    # Try different endpoints
    endpoints = [
        f"https://{api_host}/v8/finance/chart/{symbol}",
        f"https://{api_host}/v7/finance/quote",
        f"https://{api_host}/v6/finance/quote",
    ]
    
    for endpoint in endpoints:
        try:
            print(f"\nTrying endpoint: {endpoint}")
            
            if "quote" in endpoint and not "chart" in endpoint:
                # This endpoint might need parameters
                params = {'symbols': symbol}
                response = requests.get(endpoint, headers=headers, params=params, timeout=10)
            else:
                response = requests.get(endpoint, headers=headers, timeout=10)
            
            print(f"Status Code: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"SUCCESS! Response data:")
                print(json.dumps(data, indent=2)[:1000] + "..." if len(str(data)) > 1000 else json.dumps(data, indent=2))
                return True
            else:
                print(f"Error Response: {response.text[:200]}")
                
        except Exception as e:
            print(f"Exception: {e}")
    
    return False

if __name__ == "__main__":
    success = test_yahoo_api()
    if not success:
        print("\nAll endpoints failed. You may need to:")
        print("1. Check your RapidAPI subscription status")
        print("2. Verify the API key is correct")
        print("3. Check the API host/endpoint URLs")
        print("4. Review RapidAPI documentation for correct endpoints")
