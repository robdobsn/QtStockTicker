#!/usr/bin/env python3
"""
Test script to demonstrate the new unified fallback chain system.

This script shows how the StockProviderManager now handles:
1. Unified fallback chain configuration (no more provider-specific chains)
2. stock_provider field in stock records
3. Proper fallback when preferred providers fail

Usage: python test_unified_fallback.py
"""

import logging
import sys
import os
import time

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from StockProviderManager import StockProviderManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("TestUnifiedFallback")

def test_callback(symbol):
    """Callback function for when stock data changes"""
    logger.info(f"Stock data changed for symbol: {symbol}")

def test_unified_fallback_system():
    """Test the new unified fallback chain system"""
    
    print("=== Testing Unified Fallback Chain System ===\n")
    
    # Create StockProviderManager instance
    logger.info("Creating StockProviderManager...")
    manager = StockProviderManager(test_callback)
    
    # Test 1: Mixed stock list with both string symbols and dict symbols with stock_provider
    print("Test 1: Mixed stock list (some with preferred providers, some without)")
    
    mixed_stock_list = [
        # Regular string symbols (will use unified fallback chain)
        "AAPL",
        "MSFT",
        
        # Dictionary symbols with preferred providers
        {"symbol": "GOOGL", "stock_provider": "yahoo_api"},
        {"symbol": "TSLA", "stock_provider": "interactive_brokers"},
        {"symbol": "AMZN", "stock_provider": "google"},
        
        # Dictionary symbol without stock_provider (will use unified fallback chain)
        {"symbol": "NVDA", "holding": 100, "cost": 500},
        
        # Dictionary symbol with empty stock_provider (will use unified fallback chain)
        {"symbol": "META", "stock_provider": "", "holding": 50, "cost": 300},
    ]
    
    print(f"Setting stocks: {mixed_stock_list}")
    manager.setStocks(mixed_stock_list)
    
    print("\nProvider assignments:")
    for symbol in ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN", "NVDA", "META"]:
        provider = manager.symbol_to_provider.get(symbol, "Not assigned")
        fallback_index = manager.symbol_to_fallback_index.get(symbol, "N/A")
        preferred = manager.symbol_preferred_provider.get(symbol, "None")
        print(f"  {symbol}: provider={provider}, fallback_index={fallback_index}, preferred={preferred}")
    
    print(f"\nUnified fallback chain: {manager.unified_fallback_chain}")
    
    # Test 2: Demonstrate fallback when a provider fails
    print("\n" + "="*50)
    print("Test 2: Simulating provider failure and fallback")
    
    # Simulate a failure for GOOGL (which should be on yahoo_api)
    test_symbol = "GOOGL"
    if test_symbol in manager.symbol_to_provider:
        current_provider = manager.symbol_to_provider[test_symbol]
        print(f"\n{test_symbol} is currently on provider: {current_provider}")
        
        # Get fallback chain for this symbol
        preferred = manager.symbol_preferred_provider.get(test_symbol)
        fallback_chain = manager._getFallbackChainForSymbol(test_symbol, preferred)
        print(f"Fallback chain for {test_symbol}: {fallback_chain}")
        
        # Simulate failure and trigger fallback
        print(f"Simulating failure for {test_symbol} on {current_provider}...")
        manager._tryFallbackProvider(test_symbol)
        
        new_provider = manager.symbol_to_provider.get(test_symbol, "Not assigned")
        new_index = manager.symbol_to_fallback_index.get(test_symbol, "N/A")
        print(f"After fallback: {test_symbol} moved to provider={new_provider}, fallback_index={new_index}")
    
    # Test 3: Show configuration
    print("\n" + "="*50)
    print("Test 3: Configuration details")
    
    print(f"Available providers: {list(manager.providers.keys())}")
    print(f"Unified fallback chain: {manager.unified_fallback_chain}")
    print(f"Test mode: {manager._readConfigValue('TEST_MODE', 'false')}")
    
    # Test 4: Test with different stock list formats
    print("\n" + "="*50)
    print("Test 4: Different stock list formats")
    
    # Just strings
    string_list = ["SPY", "QQQ", "VTI"]
    print(f"\nString list: {string_list}")
    manager.setStocks(string_list)
    
    # Just dicts with stock_provider
    dict_list = [
        {"symbol": "BRK-A", "stock_provider": "interactive_brokers"},
        {"symbol": "BRK-B", "stock_provider": "yahoo_api"},
    ]
    print(f"\nDict list with providers: {dict_list}")
    manager.setStocks(dict_list)
    
    # Mixed realistic format
    realistic_list = [
        {"symbol": "AAPL", "holding": 100, "cost": 150.0, "stock_provider": "yahoo_api"},
        {"symbol": "MSFT", "holding": 50, "cost": 300.0},  # No provider specified
        {"symbol": "GOOGL", "holding": 25, "cost": 2000.0, "stock_provider": "interactive_brokers"},
    ]
    print(f"\nRealistic mixed format: {realistic_list}")
    manager.setStocks(realistic_list)
    
    print("\nFinal provider assignments:")
    for item in realistic_list:
        symbol = item["symbol"]
        provider = manager.symbol_to_provider.get(symbol, "Not assigned")
        preferred = manager.symbol_preferred_provider.get(symbol, "None")
        print(f"  {symbol}: provider={provider}, preferred={preferred}")

if __name__ == "__main__":
    try:
        test_unified_fallback_system()
        print("\n=== Test completed successfully! ===")
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
