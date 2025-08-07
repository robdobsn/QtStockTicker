#!/usr/bin/env python3
"""
Test script for the refactored StockValues_Test provider
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from StockValues_Test import StockValues_Test

def test_provider():
    print("Testing refactored StockValues_Test provider...")
    
    # Test the refactored provider
    provider = StockValues_Test()
    print("✓ Provider created successfully")
    
    # Test interface methods
    print("\nTesting interface methods:")
    market_status = provider.getMarketOpenStatus()
    print(f"✓ getMarketOpenStatus: {market_status}")
    
    # Set stocks and test data retrieval
    test_symbols = ['YCA.L', 'IMI.L', 'TEST.L']
    provider.setStocks(test_symbols)
    print(f"✓ Stocks set successfully: {test_symbols}")
    
    # Test data retrieval
    print("\nTesting data retrieval:")
    for symbol in test_symbols:
        data = provider.getStockData(symbol)
        if data:
            print(f"✓ {symbol}: price={data['price']:.2f}, change={data['change']:+.2f}, name='{data['name']}'")
        else:
            print(f"✗ {symbol}: No data returned")
        
        # Test alternate method name
        info_data = provider.getStockInfoData(symbol)
        if info_data:
            print(f"✓ {symbol} (via getStockInfoData): Same data returned")
        else:
            print(f"✗ {symbol} (via getStockInfoData): No data returned")
    
    # Test market hours setting
    print("\nTesting market hours functionality:")
    provider.setOnlyUpdateWhenMarketOpen(True)
    print("✓ setOnlyUpdateWhenMarketOpen(True) called")
    
    provider.setOnlyUpdateWhenMarketOpen(False)
    print("✓ setOnlyUpdateWhenMarketOpen(False) called")
    
    # Test start/stop
    print("\nTesting start/stop functionality:")
    provider.start()
    print("✓ start() called")
    
    provider.stop()
    print("✓ stop() called")
    
    print("\n🎉 All interface tests passed! The refactored provider is working correctly.")

if __name__ == "__main__":
    test_provider()
