#!/usr/bin/env python3

import logging
import os
import time
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

# Create provider instance and configure it
provider = StockValues_YahooAPI()
api_key = _readConfigValue("YAHOO_FINANCE_API_KEY", "")
api_host = _readConfigValue("YAHOO_API_HOST", "yahoo-finance15.p.rapidapi.com")
provider.setApiKey(api_key)
provider.setApiHost(api_host)

# Set some test symbols 
test_symbols = ['FRES.L', 'ANTO.L']
provider.setStocks(test_symbols)

# Start the provider
provider.start()

print("Waiting for data to be fetched...")
time.sleep(10)  # Wait for data to be fetched

# Test getStockData method
for symbol in test_symbols:
    print(f"\nTesting getStockData for {symbol}:")
    data = provider.getStockData(symbol)
    print(f"  Result: {data}")
    
    if data:
        print(f"  Valid: {data.get('price', 0) > 0}")
        print(f"  FailCount: {data.get('failCount', 0)}")
        
# Test the validation function from StockProviderManager
def _isValidStockData(data):
    """Check if stock data is valid"""
    if not data:
        return False
    
    # Check for explicit failure markers
    if data.get('failCount', 0) > 0:
        return False
    
    # Check for essential fields
    price = data.get('price')
    if price is None or price == 0:
        return False
    
    # Additional validation can be added here
    return True

for symbol in test_symbols:
    data = provider.getStockData(symbol)
    if data:
        is_valid = _isValidStockData(data)
        print(f"{symbol} validation: {is_valid}")
        if not is_valid:
            print(f"  Fail reason - price: {data.get('price')}, failCount: {data.get('failCount')}")

# Stop the provider
provider.stop()
