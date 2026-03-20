import logging
import threading
import time
from StockValues_YahooAPI import StockValues_YahooAPI
from StockValues_InteractiveBrokers import StockValues_InteractiveBrokers
from StockValues_Google import StockValues_Google
from StockValues_Test import StockValues_Test

logger = logging.getLogger("StockTickerLogger")

class StockProviderManager:
    """
    Manages multiple stock data providers with intelligent fallback logic.
    Handles symbol routing and failover between Yahoo API, Interactive Brokers, and Google.
    """
    
    def __init__(self, symbolChangedCallback, config_manager=None):
        self.symbolChangedCallback = symbolChangedCallback
        self.config_manager = config_manager
        self.lock = threading.Lock()
        
        # Provider instances
        self.providers = {}
        self.provider_order = []
        self.unified_fallback_chain = []
        
        # Symbol tracking - which provider is handling which symbol
        self.symbol_to_provider = {}  # symbol -> provider_name
        self.symbol_to_fallback_index = {}  # symbol -> current fallback index
        self.symbol_preferred_provider = {}  # symbol -> preferred provider from stock record
        
        # Stock data cache
        self.stockData = {}
        self.dataUpdatedSinceLastUIUpdate = False
        
        # Market hours
        self.openhour = 8
        self.openmin = 0
        self.closehour = 16
        self.closemin = 30
        self.tradingdow = 0, 1, 2, 3, 4
        self.bOnlyUpdateWhileMarketOpen = True
        
        self.running = False
        
        # Initialize providers and fallback chains
        self._initializeProviders()
        self._loadFallbackConfig()
    
    def _initializeProviders(self):
        """Initialize only the stock data providers that are needed based on fallback chain"""
        
        # Check if test mode is enabled
        test_mode = self._readConfigValue("TEST_MODE", "false").lower() == "true"
        
        if test_mode:
            logger.info("TEST_MODE enabled - using test provider only")
            try:
                self.providers['test'] = StockValues_Test()
                self.providers['test'].setCallback(self._providerSymbolChanged)
                logger.info("Test provider initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Test provider: {e}")
            return
        
        # Normal mode - get the fallback chain to determine which providers to initialize
        fallback_chain_str = self._readConfigValue("STOCK_PROVIDER_FALLBACK_CHAIN", "interactive_brokers,yahoo_api,google")
        needed_providers = [p.strip() for p in fallback_chain_str.split(',') if p.strip()]
        
        logger.info(f"Initializing only providers in fallback chain: {needed_providers}")
        
        # Initialize Yahoo API provider if needed
        if 'yahoo_api' in needed_providers:
            try:
                self.providers['yahoo_api'] = StockValues_YahooAPI(self._providerSymbolChanged)
                # Set API key and host if available
                api_key = self._readConfigValue("YAHOO_FINANCE_API_KEY")
                api_host = self._readConfigValue("YAHOO_API_HOST", "yahoo-finance15.p.rapidapi.com")
                if api_key:
                    self.providers['yahoo_api'].setApiKey(api_key)
                if api_host:
                    self.providers['yahoo_api'].setApiHost(api_host)
                logger.info("Yahoo API provider initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Yahoo API provider: {e}")
        
        # Initialize Interactive Brokers provider if needed
        if 'interactive_brokers' in needed_providers:
            try:
                self.providers['interactive_brokers'] = StockValues_InteractiveBrokers()
                # Set the callback using the new setCallback method
                def safe_callback(symbol, stock_data=None):
                    try:
                        logger.debug(f"StockProviderManager safe_callback called with symbol={symbol}, stock_data={type(stock_data)}")
                        self._providerSymbolChanged(symbol, stock_data)
                    except Exception as e:
                        logger.error(f"Error in StockProviderManager callback: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                
                self.providers['interactive_brokers'].setCallback(safe_callback)
                logger.info("Interactive Brokers provider initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Interactive Brokers provider: {e}")
        
        # Initialize Google provider if needed
        if 'google' in needed_providers:
            try:
                self.providers['google'] = StockValues_Google(self._providerSymbolChanged)
                logger.info("Google provider initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Google provider: {e}")
    
    def _loadFallbackConfig(self):
        """Load fallback configuration from config.ini"""
        
        # Check if test mode is enabled
        test_mode = self._readConfigValue("TEST_MODE", "false").lower() == "true"
        
        if test_mode:
            logger.info("TEST_MODE enabled - using test provider chain only")
            self.provider_order = ['test']
            self.unified_fallback_chain = ['test']
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
        if not self.config_manager:
            # Still try to read directly if no config_manager
            pass
        
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
    
    def setStocks(self, stockList):
        """
        Set the list of stocks to monitor.
        stockList can be either:
        1. List of symbol strings: ['AAPL', 'MSFT', 'GOOGL']
        2. List of stock dictionaries: [{'symbol': 'AAPL', 'stock_provider': 'yahoo_api'}, ...]
        """
        with self.lock:
            # Clear previous assignments
            self.symbol_to_provider.clear()
            self.symbol_to_fallback_index.clear()
            self.symbol_preferred_provider.clear()
            
            # Check if test mode is enabled
            test_mode = self._readConfigValue("TEST_MODE", "false").lower() == "true"
            
            if test_mode and 'test' in self.providers:
                # In test mode, assign all symbols to test provider
                symbols = self._extractSymbols(stockList)
                logger.info(f"TEST_MODE: Setting {len(symbols)} stocks on test provider")
                self.providers['test'].setStocks(symbols)
                for symbol in symbols:
                    self.symbol_to_provider[symbol] = 'test'
                    self.symbol_to_fallback_index[symbol] = 0
            else:
                # Normal mode - assign symbols based on stock_provider field and fallback chain
                self._assignSymbolsToProviders(stockList)
    
    def _extractSymbols(self, stockList):
        """Extract symbol strings from stock list (handles both string list and dict list)"""
        symbols = []
        for item in stockList:
            if isinstance(item, str):
                symbols.append(item)
            elif isinstance(item, dict) and 'symbol' in item:
                symbols.append(item['symbol'])
        return symbols
    
    def _assignSymbolsToProviders(self, stockList):
        """Assign symbols to providers based on stock_provider field and fallback chain"""
        provider_symbols = {}  # provider_name -> list of symbols
        
        for item in stockList:
            # Extract symbol and preferred provider
            if isinstance(item, str):
                symbol = item
                preferred_provider = None
            elif isinstance(item, dict) and 'symbol' in item:
                symbol = item['symbol']
                preferred_provider = item.get('stock_provider', '').strip()
                if not preferred_provider:
                    preferred_provider = None
            else:
                logger.warn(f"Invalid stock item format: {item}")
                continue
            
            # Store preferred provider if specified
            if preferred_provider:
                self.symbol_preferred_provider[symbol] = preferred_provider
                logger.debug(f"Symbol {symbol} has preferred provider: {preferred_provider}")
            
            # Determine the fallback chain for this symbol
            fallback_chain = self._getFallbackChainForSymbol(symbol, preferred_provider)
            
            # Try to assign to the first available provider in the chain
            assigned = False
            for provider_name in fallback_chain:
                if provider_name in self.providers:
                    try:
                        # Add to provider's symbol list
                        if provider_name not in provider_symbols:
                            provider_symbols[provider_name] = []
                        provider_symbols[provider_name].append(symbol)
                        
                        # Track assignment
                        self.symbol_to_provider[symbol] = provider_name
                        self.symbol_to_fallback_index[symbol] = fallback_chain.index(provider_name)
                        
                        logger.debug(f"Assigned symbol {symbol} to provider {provider_name} (index {self.symbol_to_fallback_index[symbol]} in chain {fallback_chain})")
                        assigned = True
                        break
                    except Exception as e:
                        logger.warn(f"Failed to assign {symbol} to {provider_name}: {e}")
                        continue
            
            if not assigned:
                logger.error(f"Could not assign symbol {symbol} to any provider")
        
        # Now call setStocks once per provider with their assigned symbols
        for provider_name, symbols in provider_symbols.items():
            try:
                provider = self.providers[provider_name]
                logger.info(f"Setting {len(symbols)} symbols on provider {provider_name}: {symbols}")
                if hasattr(provider, 'setStocks'):
                    provider.setStocks(symbols)
                else:
                    # Fallback for providers that don't have setStocks
                    for symbol in symbols:
                        if hasattr(provider, 'addStock'):
                            provider.addStock(symbol)
            except Exception as e:
                logger.error(f"Failed to set stocks on provider {provider_name}: {e}")
    
    def _getFallbackChainForSymbol(self, symbol, preferred_provider):
        """Get the fallback chain for a symbol"""
        if preferred_provider and preferred_provider in self.providers:
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
    
    def _providerSymbolChanged(self, symbol, stock_data=None):
        """Called when a provider reports data change for a symbol"""
        logger.debug(f"_providerSymbolChanged called for symbol: {symbol}")
        
        # If stock data was passed directly, use it
        if stock_data is not None:
            logger.debug(f"_providerSymbolChanged: Using provided stock data for {symbol}")
            symbol_data = stock_data
        else:
            # Fall back to retrieving data from provider (for backwards compatibility)
            logger.debug(f"_providerSymbolChanged: Retrieving data from provider for {symbol}")
            current_provider = self.symbol_to_provider.get(symbol)
            if not current_provider:
                logger.warn(f"_providerSymbolChanged: No provider assigned for symbol {symbol}")
                return
            
            logger.debug(f"_providerSymbolChanged: Getting data from provider {current_provider} for {symbol}")
            provider = self.providers[current_provider]
            symbol_data = None
            
            # Get data from the provider
            try:
                if hasattr(provider, 'getStockData'):
                    logger.debug(f"_providerSymbolChanged: Calling getStockData for {symbol}")
                    symbol_data = provider.getStockData(symbol)
                    logger.debug(f"_providerSymbolChanged: getStockData returned: {symbol_data}")
                elif hasattr(provider, 'getStockInfoData'):
                    logger.debug(f"_providerSymbolChanged: Calling getStockInfoData for {symbol}")
                    symbol_data = provider.getStockInfoData(symbol)
                    logger.debug(f"_providerSymbolChanged: getStockInfoData returned: {symbol_data}")
                else:
                    logger.warn(f"_providerSymbolChanged: Provider {current_provider} has no getStockData or getStockInfoData method")
                    return
            except Exception as e:
                logger.warn(f"Error getting data for {symbol} from {current_provider}: {e}")
                logger.debug(f"Exception details:", exc_info=True)
                return
        
        # Check if we got valid data
        logger.debug(f"_providerSymbolChanged: Checking if data is valid for {symbol}")
        logger.debug(f"_providerSymbolChanged: Data type: {type(symbol_data)}, Data: {symbol_data}")
        
        if symbol_data and self._isValidStockData(symbol_data):
            logger.debug(f"_providerSymbolChanged: Got valid data for {symbol}, updating cache")
            # Update our cache and notify the main application
            with self.lock:
                self.stockData[symbol] = symbol_data
                self.dataUpdatedSinceLastUIUpdate = True
            
            logger.debug(f"_providerSymbolChanged: Calling symbolChangedCallback for {symbol}")
            # Notify the main application
            self.symbolChangedCallback(symbol)
        else:
            # Provider failed to get data, try fallback
            logger.info(f"No valid data from {current_provider} for {symbol}, trying fallback")
            logger.debug(f"Validation failure: data={symbol_data}, valid={self._isValidStockData(symbol_data) if symbol_data else 'None'}")
            self._tryFallbackProvider(symbol)
    
    def _isValidStockData(self, data):
        """Check if stock data is valid"""
        logger.debug(f"_isValidStockData: Validating data: {data}")
        
        if not data:
            logger.debug("_isValidStockData: Data is None or empty")
            return False
        
        # Check for explicit failure markers
        fail_count = data.get('failCount', 0)
        logger.debug(f"_isValidStockData: failCount = {fail_count}")
        if fail_count > 0:
            logger.debug("_isValidStockData: Data has failCount > 0")
            return False
        
        # Check for essential fields
        price = data.get('price')
        logger.debug(f"_isValidStockData: price = {price}")
        if price is None or price == 0:
            logger.debug("_isValidStockData: Price is None or 0")
            return False
        
        logger.debug("_isValidStockData: Data is valid")
        # Additional validation can be added here
        return True
    
    def _tryFallbackProvider(self, symbol):
        """Try the next provider in the fallback chain for a symbol"""
        current_provider = self.symbol_to_provider.get(symbol)
        if not current_provider:
            return
        
        # Get the fallback chain for this symbol 
        preferred_provider = self.symbol_preferred_provider.get(symbol)
        fallback_chain = self._getFallbackChainForSymbol(symbol, preferred_provider)
        
        current_index = self.symbol_to_fallback_index.get(symbol, 0)
        next_index = current_index + 1
        
        # Try the next provider in the fallback chain
        if next_index < len(fallback_chain):
            next_provider = fallback_chain[next_index]
            logger.info(f"Trying fallback provider {next_provider} for symbol {symbol} (index {next_index} in chain {fallback_chain})")
            
            if next_provider in self.providers:
                try:
                    # Add to new provider - don't worry about removing from old one
                    # as the StockValues providers can handle overlapping symbols
                    new_provider = self.providers[next_provider]
                    if hasattr(new_provider, 'addStock'):
                        new_provider.addStock(symbol)
                    elif hasattr(new_provider, 'setStocks'):
                        # For providers that need the full list, we'd need to handle this differently
                        # For now, just assign and let the provider handle it
                        pass
                    
                    # Update tracking
                    self.symbol_to_provider[symbol] = next_provider
                    self.symbol_to_fallback_index[symbol] = next_index
                    logger.info(f"Successfully moved symbol {symbol} from {current_provider} to fallback {next_provider} (index {next_index} in chain {fallback_chain})")
                    
                except Exception as e:
                    logger.error(f"Failed to move {symbol} to fallback provider {next_provider}: {e}")
                    # Try the next fallback
                    self.symbol_to_fallback_index[symbol] = next_index
                    self._tryFallbackProvider(symbol)
            else:
                logger.error(f"Fallback provider {next_provider} not available for {symbol}")
                # Try the next fallback
                self.symbol_to_fallback_index[symbol] = next_index
                self._tryFallbackProvider(symbol)
        else:
            logger.error(f"Exhausted all fallback providers for symbol {symbol} (tried chain: {fallback_chain})")
    
    def getStockData(self, symbol):
        """Get stock data for a symbol"""
        with self.lock:
            data = self.stockData.get(symbol)
            logger.debug(f"getStockData called for {symbol}, returning: {data is not None}")
            if data is None:
                logger.debug(f"getStockData: No data found for {symbol}. Available symbols: {list(self.stockData.keys())}")
            return data
    
    def getStockInfoData(self, symbol):
        """Get stock info data for a symbol - alias for getStockData for compatibility"""
        return self.getStockData(symbol)
    
    def checkAndSetUIUpdateDataChange(self):
        """Check if data has changed since last UI update"""
        with self.lock:
            changed = self.dataUpdatedSinceLastUIUpdate
            self.dataUpdatedSinceLastUIUpdate = False
            return changed
    
    def getMapOfStocksChangedSinceUIUpdated(self):
        """Get map of stocks that have changed since last UI update"""
        logger.debug(f"getMapOfStocksChangedSinceUIUpdated called, dataUpdated={self.dataUpdatedSinceLastUIUpdate}")
        # For compatibility with existing StockTicker.py interface
        if self.dataUpdatedSinceLastUIUpdate:
            # Return all symbols that have data
            changed_stocks = {}
            with self.lock:
                for symbol in self.stockData:
                    changed_stocks[symbol] = True
                self.dataUpdatedSinceLastUIUpdate = False
            logger.debug(f"getMapOfStocksChangedSinceUIUpdated returning {len(changed_stocks)} changed stocks")
            return changed_stocks
        logger.debug("getMapOfStocksChangedSinceUIUpdated returning empty dict")
        return {}
    
    def setOnlyUpdateWhenMarketOpen(self, onlyWhenOpen):
        """Set whether to only update when market is open"""
        self.bOnlyUpdateWhileMarketOpen = onlyWhenOpen
        for provider in self.providers.values():
            if hasattr(provider, 'setOnlyUpdateWhenMarketOpen'):
                provider.setOnlyUpdateWhenMarketOpen(onlyWhenOpen)
    
    def start(self):
        """Start all providers"""
        self.running = True
        for provider_name, provider in self.providers.items():
            try:
                if hasattr(provider, 'start'):
                    provider.start()
                elif hasattr(provider, 'run'):
                    provider.run()
                logger.debug(f"Started provider: {provider_name}")
            except Exception as e:
                logger.error(f"Failed to start provider {provider_name}: {e}")
    
    def run(self):
        """Start all providers - alias for start() for compatibility"""
        self.start()
    
    def stop(self):
        """Stop all providers"""
        self.running = False
        for provider_name, provider in self.providers.items():
            try:
                if hasattr(provider, 'stop'):
                    provider.stop()
                logger.debug(f"Stopped provider: {provider_name}")
            except Exception as e:
                logger.error(f"Failed to stop provider {provider_name}: {e}")
    
    def getMarketOpenStatus(self):
        """Get market open status from the primary provider"""
        if not self.provider_order:
            return "No providers available"
        
        primary_provider_name = self.provider_order[0]
        if primary_provider_name in self.providers:
            provider = self.providers[primary_provider_name]
            if hasattr(provider, 'getMarketOpenStatus'):
                return provider.getMarketOpenStatus()
            elif hasattr(provider, 'status'):
                return getattr(provider, 'status', "Unknown")
        
        return "Market status unavailable"
    
    def getProviderStatus(self):
        """Get status of all providers"""
        status = {}
        for provider_name, provider in self.providers.items():
            try:
                if hasattr(provider, 'status'):
                    status[provider_name] = provider.status
                else:
                    status[provider_name] = "Running" if self.running else "Stopped"
            except:
                status[provider_name] = "Unknown"
        
        return status