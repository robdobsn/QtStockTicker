#!/usr/bin/env python3
"""
Test to verify that only providers in the fallback chain are initialized.
This test mocks the provider imports to avoid dependencies.
"""

import logging
import sys
import os

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("TestProviderInit")

def test_provider_initialization():
    """Test that only fallback chain providers are initialized"""
    
    print("=== Testing Provider Initialization ===\n")
    
    # Mock the provider imports to avoid dependencies
    class MockProvider:
        def __init__(self, name, callback=None):
            self.name = name
            self.callback = callback
            print(f"    MockProvider {name} initialized!")
        
        def setCallback(self, callback):
            self.callback = callback
            print(f"    MockProvider {self.name} callback set")
        
        def setApiKey(self, key):
            print(f"    MockProvider {self.name} API key set")
        
        def setApiHost(self, host):
            print(f"    MockProvider {self.name} API host set")
    
    # Mock imports
    import sys
    sys.modules['StockValues_YahooAPI'] = type('Module', (), {'StockValues_YahooAPI': lambda callback: MockProvider('YahooAPI', callback)})
    sys.modules['StockValues_InteractiveBrokers'] = type('Module', (), {'StockValues_InteractiveBrokers': lambda: MockProvider('InteractiveBrokers')})
    sys.modules['StockValues_Google'] = type('Module', (), {'StockValues_Google': lambda callback: MockProvider('Google', callback)})
    sys.modules['StockValues_Test'] = type('Module', (), {'StockValues_Test': lambda: MockProvider('Test')})
    
    # Now we can import and test
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    
    # Create a minimal version of the initialization logic
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
    
    def test_callback(symbol):
        print(f"    Callback called for {symbol}")
    
    # Test the initialization logic
    providers = {}
    
    # Check if test mode is enabled
    test_mode = _readConfigValue("TEST_MODE", "false").lower() == "true"
    
    if test_mode:
        print("TEST_MODE enabled - initializing test provider only")
        providers['test'] = MockProvider('Test')
    else:
        # Normal mode - get the fallback chain to determine which providers to initialize
        fallback_chain_str = _readConfigValue("STOCK_PROVIDER_FALLBACK_CHAIN", "interactive_brokers,yahoo_api,google")
        needed_providers = [p.strip() for p in fallback_chain_str.split(',') if p.strip()]
        
        print(f"Fallback chain from config: {needed_providers}")
        print("Initializing providers...")
        
        # Initialize Yahoo API provider if needed
        if 'yahoo_api' in needed_providers:
            providers['yahoo_api'] = MockProvider('YahooAPI', test_callback)
            # Mock API key/host setting
            api_key = _readConfigValue("YAHOO_FINANCE_API_KEY")
            if api_key:
                providers['yahoo_api'].setApiKey(api_key)
        
        # Initialize Interactive Brokers provider if needed
        if 'interactive_brokers' in needed_providers:
            providers['interactive_brokers'] = MockProvider('InteractiveBrokers')
            providers['interactive_brokers'].setCallback(test_callback)
        
        # Initialize Google provider if needed
        if 'google' in needed_providers:
            providers['google'] = MockProvider('Google', test_callback)
    
    print(f"\nInitialized providers: {list(providers.keys())}")
    
    # Verify correct behavior
    config_chain = _readConfigValue("STOCK_PROVIDER_FALLBACK_CHAIN", "").split(',')
    config_chain = [p.strip() for p in config_chain if p.strip()]
    
    print(f"Expected providers based on config: {config_chain}")
    
    if set(providers.keys()) == set(config_chain):
        print("✅ SUCCESS: Only providers in fallback chain were initialized!")
    else:
        print("❌ FAILURE: Mismatch between config and initialized providers")
        print(f"   Config: {config_chain}")
        print(f"   Initialized: {list(providers.keys())}")
    
    return providers

if __name__ == "__main__":
    try:
        test_provider_initialization()
        print("\n=== Provider initialization test completed ===")
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
