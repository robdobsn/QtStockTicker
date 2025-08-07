#!/usr/bin/env python3
"""
Test script to verify if stock symbols work with Yahoo API and whether fallback to Google is needed.
"""

import logging
import sys
import os

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("TestStockSymbols")

def test_yahoo_api_symbols():
    """Test some problematic symbols with Yahoo API directly"""
    print("=== Testing Yahoo API Symbol Accessibility ===\n")
    
    # Add the current directory to path to import our modules
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    
    try:
        from StockValues_YahooAPI import StockValues_YahooAPI
        
        # Test symbols that were failing in the logs
        test_symbols = ['DLAR.L', 'FRES.L', 'ANTO.L', 'BP.L', 'LLOY.L', 'AAPL', 'MSFT', 'GOOGL']
        
        # Create Yahoo API instance
        yahoo_api = StockValues_YahooAPI()
        
        # Set API credentials from config
        def _readConfigValue(key, default=""):
            """Read value from config.ini"""
            try:
                with open("privatesettings/config.ini", "r") as f:
                    for line in f:
                        line = line.strip()
                        # Skip comments and empty lines
                        if not line or line.startswith('#'):
                            continue
                        # Check for exact key match
                        if line.startswith(key + "="):
                            return line.split("=", 1)[1].strip()
            except Exception as e:
                logger.debug(f"Could not read {key} from config.ini: {e}")
            return default
        
        api_key = _readConfigValue("YAHOO_FINANCE_API_KEY", "")
        api_host = _readConfigValue("YAHOO_API_HOST", "yahoo-finance15.p.rapidapi.com")
        
        if not api_key:
            print("❌ ERROR: No Yahoo Finance API key found in config")
            return
        
        yahoo_api.setApiKey(api_key)
        yahoo_api.setApiHost(api_host)
        
        print(f"Testing {len(test_symbols)} symbols with Yahoo Finance API:")
        print(f"API Host: {api_host}")
        print(f"API Key: {'*' * (len(api_key)-4) + api_key[-4:] if len(api_key) > 4 else 'SET'}")
        print()
        
        for symbol in test_symbols:
            try:
                print(f"Testing {symbol}... ", end='')
                quotes = yahoo_api.get_quotes([symbol])
                
                if symbol in quotes:
                    quote = quotes[symbol]
                    if quote.get('failCount', 0) > 0:
                        print(f"❌ FAILED (marked as failed)")
                    elif quote.get('price', 0) > 0:
                        print(f"✅ SUCCESS (price: {quote['price']})")
                    else:
                        print(f"⚠️  NO DATA (price: {quote.get('price', 'N/A')})")
                else:
                    print(f"❌ NOT FOUND")
                    
            except Exception as e:
                print(f"❌ ERROR: {e}")
        
        print("\n=== Summary ===")
        print("If many UK stocks (.L suffix) are failing, this indicates Yahoo API")
        print("may not have good coverage for London Stock Exchange symbols.")
        print("The fallback to Google should help with this.")
        
    except ImportError as e:
        print(f"❌ Failed to import required modules: {e}")
        print("Make sure you're running from the correct directory")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_yahoo_api_symbols()
