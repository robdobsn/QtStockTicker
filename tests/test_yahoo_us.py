#!/usr/bin/env python3

import sys
import os
import logging

# Add the current directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from StockValues_YahooAPI import StockValues_YahooAPI
from LocalConfig import LocalConfig

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_yahoo_api():
    """Test Yahoo API with US symbols that should work"""
    
    # Load config
    config = LocalConfig("privatesettings")
    
    # US symbols that should work with Yahoo API
    test_symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
    
    # Create Yahoo API provider
    yahoo_provider = StockValues_YahooAPI(config)
    
    # Test callback to capture results
    def test_callback(symbol, data):
        if data and "failCount" not in data:
            print(f"✅ {symbol}: ${data.get('price', 'N/A')} ({data.get('change', 'N/A')}%)")
        else:
            print(f"❌ {symbol}: Failed to get data")
    
    # Set the callback
    yahoo_provider.setCallback(test_callback)
    
    # Add test symbols
    for symbol in test_symbols:
        yahoo_provider.addStock(symbol)
        print(f"Added symbol: {symbol}")
    
    # Start the provider
    yahoo_provider.start()
    print("Started Yahoo API provider")
    
    # Get quotes
    print("\nRequesting quotes...")
    yahoo_provider.requestQuotes()
    
    # Wait a bit for results
    import time
    print("Waiting for results...")
    time.sleep(5)
    
    # Stop the provider
    yahoo_provider.stop()
    print("Stopped Yahoo API provider")

if __name__ == "__main__":
    test_yahoo_api()
