#!/usr/bin/env python3

import logging
import sys
import os
import time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
from StockProviderManager import StockProviderManager

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def test_integration():
    print("=== Testing Yahoo API Integration with StockProviderManager ===")
    
    # Create provider manager with dummy callback
    def dummy_callback(symbol, provider, data):
        pass
    
    manager = StockProviderManager(dummy_callback)
    
    print(f"Initialized providers: {list(manager.providers.keys())}")
    print(f"Fallback chain: {manager.unified_fallback_chain}")
    
    # Test symbols
    test_symbols = ['AAPL', 'MSFT']
    
    print(f"\nTesting symbols: {test_symbols}")
    print("-" * 60)
    
    # Get quotes for each symbol
    for symbol in test_symbols:
        try:
            provider_name, quote_data = manager.get_quote_for_symbol(symbol)
            
            if quote_data and quote_data.get('price', 0) > 0:
                print(f"✅ {symbol}: ${quote_data['price']:.2f} (change: {quote_data.get('change', 0):.2f}) via {provider_name}")
            else:
                print(f"❌ {symbol}: Failed to get data via {provider_name}")
                
        except Exception as e:
            print(f"❌ {symbol}: Error - {e}")
    
    print("\n=== Integration Test Complete ===")

if __name__ == "__main__":
    test_integration()
