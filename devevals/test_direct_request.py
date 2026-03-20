#!/usr/bin/env python3

import requests
import os

def _readConfigValue(key, default_value=""):
    """Read configuration value from config.ini"""
    config_file = os.path.join("privatesettings", "config.ini")
    try:
        with open(config_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#') or not line:
                    continue
                if '=' in line:
                    k, v = line.split('=', 1)
                    if k.strip() == key:
                        return v.strip()
    except FileNotFoundError:
        pass
    return default_value

# Get configuration
api_key = _readConfigValue("YAHOO_FINANCE_API_KEY", "")
api_host = _readConfigValue("YAHOO_API_HOST", "yahoo-finance15.p.rapidapi.com")

print(f"API Key: {api_key[:20]}... (truncated)")
print(f"API Host: {api_host}")

# Test single symbol request using requests directly
symbols = ['AAPL']
url = f"https://{api_host}/api/v1/markets/stock/quotes"

headers = {
    'X-RapidAPI-Key': api_key,
    'X-RapidAPI-Host': api_host
}

params = {
    'ticker': ','.join(symbols)
}

print(f"URL: {url}")
print(f"Params: {params}")
print(f"Headers: {headers}")
print("-" * 60)

try:
    response = requests.get(url, headers=headers, params=params)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text[:500]}...")
    
    if response.status_code == 200:
        data = response.json()
        print("JSON parsing successful")
        print(f"Meta: {data.get('meta', {})}")
        print(f"Body length: {len(data.get('body', []))}")
    else:
        print(f"Error: {response.text}")
        
except Exception as e:
    print(f"Exception: {e}")
    import traceback
    traceback.print_exc()
