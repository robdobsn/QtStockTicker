import threading
import datetime
import pytz
import time
import copy
import requests
import logging

logger = logging.getLogger("StockTickerLogger")

class StockValues_YahooAPI:
    bOnlyUpdateWhileMarketOpen = False
    
    def __init__(self, callback=None):
        self.tickerlist = []
        self.pendingTickerlist = None
        self.running = False
        self.openhour = 8
        self.openmin = 0
        self.closehour = 16
        self.closemin = 30
        self.tradingdow = 0, 1, 2, 3, 4
        self.dataUpdatedSinceLastUIUpdate = False
        self.stockData = {}
        self.lock = threading.Lock()
        self.status = ""
        self.listUpdateLock = threading.Lock()
        self._symbolChangedCallback = callback
        
        # State tracking for provider interface compatibility
        self._dictOfStocksChangedSinceUIUpdate = {}
        self._lockOnStockChangeList = threading.Lock()
        
        logger.info("StockValues_YahooAPI initialized")
        
        # Yahoo Finance API configuration
        self.api_key = ""  # Set from config
        self.api_host = "yahoo-finance15.p.rapidapi.com"  # From config
        self.base_url = "https://yahoo-finance15.p.rapidapi.com"
        self.headers = {
            'X-RapidAPI-Key': self.api_key,
            'X-RapidAPI-Host': self.api_host
        }
        
    def setApiKey(self, api_key):
        self.api_key = api_key
        self.headers['X-RapidAPI-Key'] = api_key
        
    def setApiHost(self, api_host):
        self.api_host = api_host
        self.base_url = f"https://{api_host}"
        self.headers['X-RapidAPI-Host'] = api_host
        self.base_url = f"https://{api_host}"
        
    def setStocks(self, stockList):
        """Set list of symbols to monitor"""
        logger.info(f"StockValues_YahooAPI setStocks: {len(stockList)} symbols: {stockList}")
        curList = []
        for sym in stockList:
            curList.append(sym)
        self.listUpdateLock.acquire()
        self.pendingTickerlist = curList
        self.listUpdateLock.release()

    def setCallback(self, callback):
        """Set the callback function to be called when stock data changes"""
        self._symbolChangedCallback = callback
        logger.debug(f"StockValues_YahooAPI callback set to {callback}")

    def symbolDataChanged(self, symbol):
        """Called when a symbol's data changes"""
        with self._lockOnStockChangeList:
            self._dictOfStocksChangedSinceUIUpdate[symbol] = True
        
        # Call the callback if one has been set (for StockProviderManager)
        if self._symbolChangedCallback:
            logger.debug(f"StockValues_YahooAPI symbolDataChanged calling callback for {symbol}")
            self._symbolChangedCallback(symbol)

    def getMapOfStocksChangedSinceUIUpdated(self):
        """Get symbols that have changed since last UI update"""
        changedStockDict = {}
        with self._lockOnStockChangeList:
            changedStockDict = copy.copy(self._dictOfStocksChangedSinceUIUpdate)
            self._dictOfStocksChangedSinceUIUpdate = {}
        return changedStockDict

    def checkAndSetUIUpdateDataChange(self):
        tmpDataChange = self.dataUpdatedSinceLastUIUpdate
        self.dataUpdatedSinceLastUIUpdate = False
        return tmpDataChange
        
    def getStockData(self, sym):
        """Get current stock data for a symbol (primary method used by StockProviderManager)"""
        self.lock.acquire()
        dat = None
        if sym in self.stockData:
            dat = copy.copy(self.stockData[sym])
        self.lock.release()
        return dat

    def getStockInfoData(self, symbol):
        """Get current stock data for a symbol (alternative method name for compatibility)"""
        return self.getStockData(symbol)
    
    def setOnlyUpdateWhenMarketOpen(self, onlyWhenOpen):
        """Set whether to only update when market is open"""
        self.bOnlyUpdateWhileMarketOpen = onlyWhenOpen
        logger.debug(f"StockValues_YahooAPI setOnlyUpdateWhenMarketOpen: {onlyWhenOpen}")
        
    def start(self):
        """Start the provider (alias for run())"""
        self.run()
        
    def run(self):
        """Start the provider"""
        logger.info("StockValues_YahooAPI started")
        self.running = True
        self.t = threading.Thread(target=self.stockUpdateThread)
        self.t.start()        

    def stop(self):
        """Stop the provider"""
        self.running = False
        logger.info("StockValues_YahooAPI stopped")
        
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
            logger.error(f"StockValues_YahooAPI getMarketOpenStatus error: {e}")
            return "Market Status Unknown"

    def stockUpdateThread(self):
        firstpass = True
        nextStockIdx = 0
        maxStocksPerPass = 10  # Smaller batches for API rate limits
        
        while self.running:
            time.sleep(1)

            # Check if the stock list has been updated
            updateNeeded = False
            self.listUpdateLock.acquire()
            if self.pendingTickerlist != None:
                self.tickerlist = self.pendingTickerlist
                self.pendingTickerlist = None
                self.dataUpdatedSinceLastUIUpdate = True
                updateNeeded = True
            self.listUpdateLock.release()

            # Check market status
            nowInUk = datetime.datetime.now(pytz.timezone('GB'))
            open_time = nowInUk.replace(hour=self.openhour, minute=self.openmin, second=0)
            close_time = nowInUk.replace(hour=self.closehour, minute=self.closemin, second=0)
            open_day = False
            for day in self.tradingdow:
                if (day == nowInUk.weekday()):
                    open_day = True
            forceUpdate = firstpass
            marketOpen = (nowInUk > open_time) and (nowInUk < close_time) and open_day
            if not self.bOnlyUpdateWhileMarketOpen or marketOpen:
                forceUpdate = True
            self.status = "Market Open" if marketOpen else "Market Closed"
            updateNeeded = updateNeeded or forceUpdate
            if not updateNeeded:
                continue

            # Check list isn't empty
            if len(self.tickerlist) <= 0:
                continue

            # Update the list
            stocks = self.tickerlist[nextStockIdx:nextStockIdx+maxStocksPerPass]
            if len(stocks) <= 0:
                continue

            stkdataValid = False
            try:
                stkdata = self.get_quotes(stocks)
                stkdataValid = True
            except Exception as e:
                logger.debug(f"Yahoo API get_quote failed for {stocks}: {e}")
                self.status = "failed for " + str(stocks[0])

            if stkdataValid:
                try:
                    # Store the data and track changes
                    changed_symbols = []
                    
                    self.lock.acquire()
                    for ticker, values in stkdata.items():
                        # Store the data first
                        old_data = self.stockData.get(ticker, {})
                        self.stockData[ticker] = values
                        self.stockData[ticker]['failCount'] = 0
                        self.stockData[ticker]['time'] = nowInUk
                        logger.debug(f"Updated {ticker}: {self.stockData[ticker]}")
                        
                        # Check if data has changed
                        data_changed = False
                        for k, v in values.items():
                            if k not in old_data or old_data[k] != v:
                                data_changed = True
                                break
                        
                        if data_changed:
                            self.dataUpdatedSinceLastUIUpdate = True
                            changed_symbols.append(ticker)
                            
                    self.lock.release()
                    
                    # Call callbacks AFTER releasing the lock to avoid deadlock
                    for ticker in changed_symbols:
                        self.symbolDataChanged(ticker)
                        
                except Exception as e:
                    logger.error(f"Error in stockUpdateThread: {e}")
                    if hasattr(self, 'lock') and self.lock.locked():
                        self.lock.release()

            # Move to next batch
            if nextStockIdx + maxStocksPerPass >= len(self.tickerlist):
                nextStockIdx = 0
                firstpass = False
            else:
                nextStockIdx += maxStocksPerPass
            
            # Delay between requests to respect rate limits
            delayTime = 5 if firstpass else (30 if marketOpen else 300)
            for delayCount in range(delayTime):
                if not self.running:
                    break
                time.sleep(1)

    def get_quotes(self, symbols):
        """
        Get real-time quotes using the correct Yahoo Finance API endpoint
        """
        quotes = {}
        
        try:
            # Use the correct API endpoint for multiple symbols
            url = f"{self.base_url}/api/v1/markets/stock/quotes"
            
            # Join symbols with comma for batch request
            ticker_param = ','.join(symbols)
            params = {'ticker': ticker_param}
            
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Parse the new API response format
            if 'body' in data and isinstance(data['body'], list):
                for item in data['body']:
                    symbol = item.get('symbol', '')
                    if symbol:
                        # Map new API response to expected format
                        quotes[symbol] = {
                            'sym': symbol,
                            'name': item.get('longName', item.get('shortName', symbol)),
                            'price': item.get('regularMarketPrice', 0),
                            'change': item.get('regularMarketChange', 0),
                            'chg_percent': item.get('regularMarketChangePercent', 0),
                            'volume': item.get('regularMarketVolume', 0),
                            'open': item.get('regularMarketOpen', 0),
                            'high': item.get('regularMarketDayHigh', 0),
                            'low': item.get('regularMarketDayLow', 0),
                            'close': item.get('regularMarketPreviousClose', 0),
                        }
                        logger.debug(f"Successfully got quote for {symbol}: price={quotes[symbol]['price']}")
            else:
                logger.warn(f"Unexpected API response format: {data}")
                
        except Exception as e:
            logger.warn(f"Failed to get quotes for {symbols}: {e}")
            
        # For any symbols that weren't returned, mark as failed
        for symbol in symbols:
            if symbol not in quotes:
                quotes[symbol] = {
                    'sym': symbol,
                    'name': symbol,
                    'price': 0,
                    'change': 0,
                    'chg_percent': 0,
                    'volume': 0,
                    'failCount': 1
                }
                logger.warn(f"No data received for symbol {symbol}")
        
        return quotes

    def search_stocks(self, query):
        """
        Search for stocks using Yahoo Finance API
        """
        try:
            url = f"{self.base_url}/v1/search"
            params = {'query': query}
            
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Stock search failed for '{query}': {e}")
            return None

    def get_historical_data(self, symbol, period='1mo'):
        """
        Get historical data for a symbol
        """
        try:
            url = f"{self.base_url}/v1/stock/history"
            params = {
                'symbol': symbol,
                'period': period
            }
            
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Historical data failed for {symbol}: {e}")
            return None