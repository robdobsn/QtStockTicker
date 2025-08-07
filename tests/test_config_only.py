#!/usr/bin/env python3
"""
Simple test script to demonstrate the new unified fallback chain configuration loading.

This script tests only the configuration and fallback chain logic without 
importing the actual provider modules (which have external dependencies).
"""

import logging
import sys
import os

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("TestUnifiedConfig")

def test_fallback_chain_config():
    """Test the unified fallback chain configuration loading"""
    
    print("=== Testing Unified Fallback Chain Configuration ===\n")
    
    # Mock a minimal StockProviderManager to test configuration
    class MockStockProviderManager:
        def __init__(self):
            self.unified_fallback_chain = []
            self.provider_order = []
            self._loadFallbackConfig()
        
        def _loadFallbackConfig(self):
            """Load fallback configuration from config.ini"""
            
            # Check if test mode is enabled
            test_mode = self._readConfigValue("TEST_MODE", "false").lower() == "true"
            
            if test_mode:
                logger.info("TEST_MODE enabled - using test provider chain only")
                self.unified_fallback_chain = ['test']
                self.provider_order = ['test']
                return
            
            # Normal mode - load unified fallback configuration
            fallback_chain_str = self._readConfigValue("STOCK_PROVIDER_FALLBACK_CHAIN", "interactive_brokers,yahoo_api,google")
            self.unified_fallback_chain = [p.strip() for p in fallback_chain_str.split(',') if p.strip()]
            
            # Use the unified fallback chain as the default provider order
            self.provider_order = self.unified_fallback_chain.copy()
            
            logger.info(f"Unified fallback chain: {self.unified_fallback_chain}")
            logger.info(f"Default provider order: {self.provider_order}")
        
        def _readConfigValue(self, key, default=""):
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
        
        def _getFallbackChainForSymbol(self, symbol, preferred_provider):
            """Get the fallback chain for a symbol"""
            if preferred_provider and preferred_provider in ['interactive_brokers', 'yahoo_api', 'google', 'test']:
                # Start with preferred provider, then continue with the rest of the unified chain
                # excluding the preferred provider to avoid duplicates
                chain = [preferred_provider]
                for provider in self.unified_fallback_chain:
                    if provider != preferred_provider:
                        chain.append(provider)
                return chain
            else:
                # Use the unified fallback chain as-is
                return self.unified_fallback_chain.copy()
    
    # Create mock manager instance
    manager = MockStockProviderManager()
    
    print("Configuration loaded:")
    print(f"  Unified fallback chain: {manager.unified_fallback_chain}")
    print(f"  Provider order: {manager.provider_order}")
    
    # Test fallback chain generation for different scenarios
    print("\nTesting fallback chain generation:")
    
    test_cases = [
        ("AAPL", None),  # No preferred provider
        ("MSFT", ""),  # Empty preferred provider  
        ("GOOGL", "yahoo_api"),  # Preferred provider specified
        ("TSLA", "interactive_brokers"),  # Different preferred provider
        ("NVDA", "invalid_provider"),  # Invalid preferred provider
    ]
    
    for symbol, preferred in test_cases:
        chain = manager._getFallbackChainForSymbol(symbol, preferred)
        print(f"  {symbol} (preferred: {preferred or 'None'}): {chain}")
    
    # Test configuration reading
    print(f"\nConfiguration values:")
    print(f"  TEST_MODE: {manager._readConfigValue('TEST_MODE', 'false')}")
    print(f"  STOCK_PROVIDER_FALLBACK_CHAIN: {manager._readConfigValue('STOCK_PROVIDER_FALLBACK_CHAIN', 'default')}")
    
    return True

if __name__ == "__main__":
    try:
        test_fallback_chain_config()
        print("\n=== Configuration test completed successfully! ===")
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
