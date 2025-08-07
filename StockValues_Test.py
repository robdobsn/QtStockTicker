"""
Test Stock Provider for QtStockTicker
Returns predictable, changing stock values for testing UI updates
"""

import threading
import time
import logging
import copy
import datetime
import pytz
from typing import Dict, Optional, Callable

logger = logging.getLogger("StockTickerLogger")

class StockValues_Test:
    """Test stock provider that returns predictable, changing values"""
    
    bOnlyUpdateWhileMarketOpen = False
    
    def __init__(self, callback=None):
        self.openhour = 8
        self.openmin = 0
        self.closehour = 16
        self.closemin = 30
        self.tradingdow = 0, 1, 2, 3, 4
        
        # Test data - each symbol has a base price and gets cyclic variations
        self._test_data = {
            'YCA.L': {'base': 511.5, 'current': 511.5, 'cycle': 0, 'name': 'Yodel Holdings'},
            'IMI.L': {'base': 2450.0, 'current': 2450.0, 'cycle': 0, 'name': 'IMI PLC'},
            'IDHC.L': {'base': 85.2, 'current': 85.2, 'cycle': 0, 'name': 'Intermediate Capital Group'},
            'INVP.L': {'base': 1234.5, 'current': 1234.5, 'cycle': 0, 'name': 'Investec PLC'},
            'REC.L': {'base': 156.8, 'current': 156.8, 'cycle': 0, 'name': 'Reckitt Benckiser'},
            'SEPL.L': {'base': 890.0, 'current': 890.0, 'cycle': 0, 'name': 'SE PLC'},
            'STCM.L': {'base': 445.6, 'current': 445.6, 'cycle': 0, 'name': 'St. Modwen Properties'},
            'TPFG.L': {'base': 678.9, 'current': 678.9, 'cycle': 0, 'name': 'TPG Inc'},
            'AAF.L': {'base': 123.4, 'current': 123.4, 'cycle': 0, 'name': 'Abrdn Asian Focus'},
            'ATYM.L': {'base': 567.8, 'current': 567.8, 'cycle': 0, 'name': 'Autonomy Capital'},
            'BP.L': {'base': 434.2, 'current': 434.2, 'cycle': 0, 'name': 'BP PLC'},
            'CNA.L': {'base': 789.1, 'current': 789.1, 'cycle': 0, 'name': 'China Airlines'},
            'FDM.L': {'base': 345.7, 'current': 345.7, 'cycle': 0, 'name': 'FDM Group'},
            'TUNE.L': {'base': 234.5, 'current': 234.5, 'cycle': 0, 'name': 'Tune Group'},
            'HILS.L': {'base': 678.2, 'current': 678.2, 'cycle': 0, 'name': 'Hill & Smith'},
            'LIO.L': {'base': 456.8, 'current': 456.8, 'cycle': 0, 'name': 'Liontrust Asset Management'},
            'NWG.L': {'base': 345.6, 'current': 345.6, 'cycle': 0, 'name': 'NatWest Group'},
            'RE.L': {'base': 567.3, 'current': 567.3, 'cycle': 0, 'name': 'Renewable Energy'},
            'RWA.L': {'base': 789.4, 'current': 789.4, 'cycle': 0, 'name': 'RWA Holdings'},
            'SOM.L': {'base': 234.7, 'current': 234.7, 'cycle': 0, 'name': 'SOM Capital'},
            'SYS1.L': {'base': 456.9, 'current': 456.9, 'cycle': 0, 'name': 'System1 Group'},
            'TLW.L': {'base': 678.5, 'current': 678.5, 'cycle': 0, 'name': 'Tullow Oil'},
            'VTU.L': {'base': 890.3, 'current': 890.3, 'cycle': 0, 'name': 'Venture Life Group'},
            'WOSG.L': {'base': 123.8, 'current': 123.8, 'cycle': 0, 'name': 'Worldwide Software'},
        }
        
        # Variation patterns (percentage changes applied cyclically)
        self._variations = [0.0, 0.5, 1.0, 0.8, 0.2, -0.3, -0.8, -1.2, -0.5, 0.3]
        
        self._dictOfStocksChangedSinceUIUpdate = {}
        self._lockOnStockChangeList = threading.Lock()
        self._symbolChangedCallback: Optional[Callable] = callback
        self._running = False
        self._update_thread = None
        self._stock_list = []
        
        logger.info("StockValues_Test initialized with test data for UI testing")
    
    def setStocks(self, stockList):
        """Set list of symbols to provide test data for"""
        self._stock_list = stockList
        logger.info(f"StockValues_Test setStocks: {len(stockList)} symbols: {stockList}")
        
        # Initialize any missing symbols with default data
        for symbol in stockList:
            if symbol not in self._test_data:
                # Create deterministic but varied test data
                base_price = 100.0 + (hash(symbol) % 500)
                self._test_data[symbol] = {
                    'base': base_price,
                    'current': base_price,
                    'cycle': 0,
                    'name': f'Test Company {symbol}'
                }
                logger.debug(f"StockValues_Test: Added test data for {symbol} with base price {base_price}")
        
        # Start the update loop if not already running
        if not self._running:
            self.run()
    
    def setCallback(self, callback):
        """Set the callback function to be called when stock data changes"""
        self._symbolChangedCallback = callback
        logger.debug(f"StockValues_Test callback set to {callback}")
    
    def symbolDataChanged(self, symbol):
        """Called when a symbol's data changes"""
        with self._lockOnStockChangeList:
            self._dictOfStocksChangedSinceUIUpdate[symbol] = True
        
        # Call the callback if one has been set (for StockProviderManager)
        if self._symbolChangedCallback:
            logger.debug(f"StockValues_Test symbolDataChanged calling callback for {symbol}")
            self._symbolChangedCallback(symbol)
    
    def getMapOfStocksChangedSinceUIUpdated(self):
        """Get symbols that have changed since last UI update"""
        changedStockDict = {}
        with self._lockOnStockChangeList:
            changedStockDict = copy.copy(self._dictOfStocksChangedSinceUIUpdate)
            self._dictOfStocksChangedSinceUIUpdate = {}
        return changedStockDict
    
    def getStockData(self, symbol):
        """Get current test data for a symbol (primary method used by StockProviderManager)"""
        if symbol in self._test_data:
            data = self._test_data[symbol]
            change = data['current'] - data['base']
            percent_change = (change / data['base']) * 100 if data['base'] > 0 else 0
            
            result = {
                'symbol': symbol,
                'name': data['name'],
                'price': data['current'],
                'change': change,
                'chg_percent': percent_change,
                'volume': 1000000 + (hash(symbol) % 500000),  # Mock volume with some variation
                'last_update': time.time(),
                'failCount': 0
            }
            logger.debug(f"StockValues_Test getStockData for {symbol}: price={data['current']:.2f}, change={change:+.2f}")
            return result
        else:
            logger.warning(f"StockValues_Test getStockData: No test data for {symbol}")
            return None
    
    def getStockInfoData(self, symbol):
        """Get current test data for a symbol (alternative method name for compatibility)"""
        return self.getStockData(symbol)
    
    def setOnlyUpdateWhenMarketOpen(self, onlyWhenOpen):
        """Set whether to only update when market is open"""
        self.bOnlyUpdateWhileMarketOpen = onlyWhenOpen
        logger.debug(f"StockValues_Test setOnlyUpdateWhenMarketOpen: {onlyWhenOpen}")
    
    def getMarketOpenStatus(self):
        """Get market open/closed status for testing"""
        try:
            nowInUk = datetime.datetime.now(pytz.timezone('GB'))
            open_time = nowInUk.replace(hour=self.openhour, minute=self.openmin, second=0)
            close_time = nowInUk.replace(hour=self.closehour, minute=self.closemin, second=0)
            open_day = nowInUk.weekday() in self.tradingdow
            marketOpen = (nowInUk > open_time) and (nowInUk < close_time) and open_day
            return "Market Open (Test Mode)" if marketOpen else "Market Closed (Test Mode)"
        except Exception as e:
            logger.error(f"StockValues_Test getMarketOpenStatus error: {e}")
            return "Market Status Unknown (Test Mode)"
    
    def start(self):
        """Start the test provider (alias for run())"""
        self.run()
    
    def run(self):
        """Start the test provider - begins cycling through price variations"""
        if not self._running:
            self._running = True
            self._update_thread = threading.Thread(target=self._update_loop, daemon=True)
            self._update_thread.start()
            logger.info("StockValues_Test started - price variations will cycle every 3 seconds")
    
    def stop(self):
        """Stop the test provider"""
        self._running = False
        if self._update_thread:
            self._update_thread.join(timeout=1.0)
        logger.info("StockValues_Test stopped")
    
    def _update_loop(self):
        """Update loop that cycles through price variations"""
        while self._running:
            try:
                # Only update if we should (market hours check if enabled)
                should_update = True
                if self.bOnlyUpdateWhileMarketOpen:
                    market_status = self.getMarketOpenStatus()
                    should_update = "Open" in market_status
                
                if should_update:
                    # Update all symbols with their next variation
                    symbols_updated = 0
                    for symbol in self._stock_list:
                        if symbol in self._test_data:
                            data = self._test_data[symbol]
                            variation_idx = data['cycle'] % len(self._variations)
                            variation_pct = self._variations[variation_idx]
                            
                            # Apply variation to base price
                            new_price = data['base'] * (1 + variation_pct / 100)
                            data['current'] = round(new_price, 2)
                            data['cycle'] += 1
                            
                            # Notify of change
                            self.symbolDataChanged(symbol)
                            symbols_updated += 1
                            
                            logger.debug(f"StockValues_Test: Updated {symbol} to {data['current']:.2f} (variation: {variation_pct:+.1f}%)")
                    
                    if symbols_updated > 0:
                        logger.info(f"StockValues_Test: Updated {symbols_updated} symbols in test cycle")
                else:
                    logger.debug("StockValues_Test: Skipping update (market closed)")
                
                # Wait 3 seconds before next update cycle
                time.sleep(3.0)
                
            except Exception as e:
                logger.error(f"StockValues_Test update loop error: {e}")
                import traceback
                logger.error(traceback.format_exc())
                time.sleep(1.0)
        
        logger.debug("StockValues_Test update loop finished")
