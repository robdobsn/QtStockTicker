"""
Interactive Brokers Stock Provider
Refactored to remove internal fallback logic and use external IB classes
"""

import threading
import datetime
import pytz
import time
import copy
import logging
from StockValues_IB_PriceGetter import StockValues_IB_PriceGetter

logger = logging.getLogger("StockTickerLogger")

class StockValues_InteractiveBrokers:
    """
    Interactive Brokers stock data provider.
    Refactored to remove internal fallback mechanisms - fallback logic is now handled by StockProviderManager.
    """
    
    bOnlyUpdateWhileMarketOpen = False
    
    def __init__(self, callback=None):
        self.openhour = 8
        self.openmin = 0
        self.closehour = 16
        self.closemin = 30
        self.tradingdow = 0, 1, 2, 3, 4
        
        # Initialize the IB price getter
        self._priceGetter = StockValues_IB_PriceGetter("127.0.0.1", 4001, 10, self.symbolDataChanged)
        
        # State tracking for provider interface compatibility
        self._dictOfStocksChangedSinceUIUpdate = {}
        self._lockOnStockChangeList = threading.Lock()
        self._symbolChangedCallback = callback
        
        logger.info("StockValues_InteractiveBrokers initialized")

    def setStocks(self, stockList):
        """Set list of symbols to monitor"""
        logger.info(f"StockValues_InteractiveBrokers setStocks: {len(stockList)} symbols: {stockList}")
        self._priceGetter.setStocks(stockList)

    def setCallback(self, callback):
        """Set the callback function to be called when stock data changes"""
        self._symbolChangedCallback = callback
        logger.debug(f"StockValues_InteractiveBrokers callback set to {callback}")

    def symbolDataChanged(self, symbol):
        """Called when a symbol's data changes"""
        with self._lockOnStockChangeList:
            self._dictOfStocksChangedSinceUIUpdate[symbol] = True
        
        # Call the callback if one has been set (for StockProviderManager)
        if self._symbolChangedCallback:
            logger.debug(f"StockValues_InteractiveBrokers symbolDataChanged calling callback for {symbol}")
            self._symbolChangedCallback(symbol)

    def getMapOfStocksChangedSinceUIUpdated(self):
        """Get symbols that have changed since last UI update"""
        changedStockDict = {}
        with self._lockOnStockChangeList:
            changedStockDict = copy.copy(self._dictOfStocksChangedSinceUIUpdate)
            self._dictOfStocksChangedSinceUIUpdate = {}
        return changedStockDict

    def getStockData(self, symbol):
        """Get current stock data for a symbol (primary method used by StockProviderManager)"""
        return self._priceGetter.getStockInfoData(symbol)

    def getStockInfoData(self, symbol):
        """Get current stock data for a symbol (alternative method name for compatibility)"""
        return self.getStockData(symbol)

    def setOnlyUpdateWhenMarketOpen(self, onlyWhenOpen):
        """Set whether to only update when market is open"""
        self.bOnlyUpdateWhileMarketOpen = onlyWhenOpen
        logger.debug(f"StockValues_InteractiveBrokers setOnlyUpdateWhenMarketOpen: {onlyWhenOpen}")

    def getMarketOpenStatus(self):
        """Get market open/closed status"""
        try:
            nowInUk = datetime.datetime.now(pytz.timezone('GB'))
            open_time = nowInUk.replace(hour=self.openhour, minute=self.openmin, second=0)
            close_time = nowInUk.replace(hour=self.closehour, minute=self.closemin, second=0)
            open_day = nowInUk.weekday() in self.tradingdow
            marketOpen = (nowInUk > open_time) and (nowInUk < close_time) and open_day
            return "Market Open" if marketOpen else "Market Closed"
        except Exception as e:
            logger.error(f"StockValues_InteractiveBrokers getMarketOpenStatus error: {e}")
            return "Market Status Unknown"

    def start(self):
        """Start the provider (alias for run())"""
        self.run()

    def run(self):
        """Start the provider - IB price getter starts automatically in constructor"""
        logger.info("StockValues_InteractiveBrokers started")

    def stop(self):
        """Stop the provider"""
        self._priceGetter.stop()
        logger.info("StockValues_InteractiveBrokers stopped")

