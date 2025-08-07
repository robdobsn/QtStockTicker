#!/usr/bin/env python3

import logging
import os
from StockValues_YahooAPI import StockValues_YahooAPI

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

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

# Test UK stocks
test_symbols = ['LLOY.L', 'BT-A.L', 'BARC.L']  # UK stocks

# Create provider instance
provider = StockValues_YahooAPI()

# Configure API credentials
api_key = _readConfigValue("YAHOO_FINANCE_API_KEY", "")
api_host = _readConfigValue("YAHOO_API_HOST", "yahoo-finance15.p.rapidapi.com")

provider.setApiKey(api_key)
provider.setApiHost(api_host)

print(f"Testing Yahoo API provider with UK symbols: {test_symbols}")
print("-" * 60)

# Test get_quotes method
try:
    quotes = provider.get_quotes(test_symbols)
    
    print(f"Received quotes for {len(quotes)} symbols:")
    for symbol, data in quotes.items():
        print(f"  {symbol}: price=${data.get('price', 'N/A')}, change={data.get('change', 'N/A')}, volume={data.get('volume', 'N/A')}")
        if data.get('failCount', 0) > 0:
            print(f"    WARNING: Failed to get data for {symbol}")
    
except Exception as e:
    print(f"Error testing Yahoo API: {e}")
    import traceback
    traceback.print_exc()
