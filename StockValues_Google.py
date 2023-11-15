import threading
import datetime
import pytz
import time
import copy
from urllib.request import Request, urlopen
import json
from bs4 import BeautifulSoup
import requests
import logging

'''
Created on 11 Nov 2017

@author: rob dobson
'''

logger = logging.getLogger("StockTickerLogger")

class StockValues_Google:
    bOnlyUpdateWhileMarketOpen = True
    bUpdateFullListWhenMarketClosed = True
    pendingTickerlist = None
    fullTickerList = []

    def __init__(self, symbolChangedCallback):
        self._symbolChangedCallback = symbolChangedCallback
        self.highFreqSymList = []
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
        self.start()

    def addStock(self, symbol):
        logger.debug(f"StockValues_Google: Adding symbol {symbol} to be got from Google")
        self.listUpdateLock.acquire()
        curList = []
        for sym in self.highFreqSymList:
            curList.append(sym)
        if self.pendingTickerlist is not None:
            for sym in self.pendingTickerlist:
                if sym not in curList:
                    curList.append(sym)
        if symbol not in curList:
            curList.append(symbol)
        self.pendingTickerlist = curList
        self.listUpdateLock.release()

    def setAllStocks(self, stockList):
        curList = []
        for sym in stockList:
            curList.append(sym)
        self.listUpdateLock.acquire()
        self.fullTickerList = curList
        self.listUpdateLock.release()

    def checkAndSetUIUpdateDataChange(self):
        tmpDataChange = self.dataUpdatedSinceLastUIUpdate
        self.dataUpdatedSinceLastUIUpdate = False
        return tmpDataChange

    def getStockInfoData(self, sym):
        self.lock.acquire()
        dat = None
        if sym in self.stockData:
            dat = copy.copy(self.stockData[sym])
        self.lock.release()
        return dat
    
    def setOnlyUpdateWhenMarketOpen(self, onlyWhenOpen):
        self.bOnlyUpdateWhileMarketOpen = onlyWhenOpen
        
    def start(self):
        self.running = True
        self.t = threading.Thread(target=self.stockUpdateThread)
        self.t.start()        

    def stop(self):
        self.running = False
        
    def stockUpdateThread(self):
        firstpass = True
        nextStockIdx = 0
        maxStocksPerPass = 1
        for delayCount in range(20):
            if not self.running:
                break
            time.sleep(1)

        while self.running:
            # Check if the stock list has been updated
            updateNeeded = False
            self.listUpdateLock.acquire()
            if self.pendingTickerlist is not None:
                self.highFreqSymList = self.pendingTickerlist
                self.pendingTickerlist = None
                self.dataUpdatedSinceLastUIUpdate = True
                updateNeeded = True
            self.listUpdateLock.release()

            # Check if the market opening times are important
            nowInUk = datetime.datetime.now(pytz.timezone('GB'))
            open_time = nowInUk.replace( hour=self.openhour, minute=self.openmin, second=0 )
            close_time = nowInUk.replace( hour=self.closehour, minute=self.closemin, second=0 )
            open_day = False
            for day in self.tradingdow:
                if ( day == nowInUk.weekday() ):
                    open_day = True
            forceUpdate = firstpass
            marketOpen = (nowInUk > open_time) and (nowInUk < close_time) and open_day
            if not self.bOnlyUpdateWhileMarketOpen or marketOpen:
                forceUpdate = True
            self.status = "Market Open" if marketOpen else "Market Closed"
            updateNeeded = updateNeeded or forceUpdate or self.bUpdateFullListWhenMarketClosed
            if not updateNeeded:
                continue
            updateUsingFullList = self.bUpdateFullListWhenMarketClosed and not marketOpen and len(self.fullTickerList) > 0

            # Check list isn't empty
            if len(self.highFreqSymList) <= 0 and (not updateUsingFullList):
                continue

            # Update the list
            if updateUsingFullList:
                stocks = self.fullTickerList[nextStockIdx:nextStockIdx + maxStocksPerPass]
            else:
                stocks = self.highFreqSymList[nextStockIdx:nextStockIdx + maxStocksPerPass]
            if len(stocks) <= 0:
                continue

            stkdataValid = False
            try:
                stkdata = self.get_quotes(stocks)
                stkdataValid = True
            except:
                logger.debug(f"get_quote failed for {stocks[0]}")
                self.status = "failed for " + str(stocks[0])
                # self.lock.acquire()
                # if not ticker in self.stockData:
                #     self.stockData[ticker] = {}
                #     self.stockData[ticker]['failCount'] = 1
                # else:
                #     self.stockData[ticker]['failCount'] += 1
                # self.lock.release()

            if stkdataValid:
                try:
                    self.lock.acquire()
                    for ticker,values in stkdata.items():
                        for k,v in values.items():
                            if not (ticker in self.stockData and k in self.stockData[ticker] and self.stockData[ticker][k] == v):
                                self.dataUpdatedSinceLastUIUpdate = True
                                self._symbolChangedCallback(ticker)
                                break
                        self.stockData[ticker] = values
                        self.stockData[ticker]['failCount'] = 0
                        self.stockData[ticker]['time'] = nowInUk
                        logger.debug(f"stockUpdateThread {self.stockData[ticker]}")
                finally:
                    self.lock.release()

            if nextStockIdx + maxStocksPerPass >= (len(self.fullTickerList) if updateUsingFullList else len(self.highFreqSymList)):
                nextStockIdx = 0
                firstpass = False
            else:
                nextStockIdx += maxStocksPerPass
            delayTime = 10 if firstpass else 120
            for delayCount in range(delayTime):
                if not self.running:
                    break
                time.sleep(1)

    def get_quotes(self, symbols):
        """
        Get all available quote data for the given ticker symbols.
        Returns a dictionary.
        """
        tryAlternateList = []
        quotes = {}
        for symbol in symbols:
            try:
                stockInfoJson = self.requestFromGoogle(symbol)
                stkData = json.loads(stockInfoJson)
                if len(stkData) > 0:
                    stkFirst = stkData[0]
                    quotes[symbol] = dict( name=stkFirst["name"] )
                    if "l" in stkFirst:
                        quotes[symbol]["price"] = stkFirst["l"]
                    if "c" in stkFirst:
                        quotes[symbol]["change"] = stkFirst["c"]
                    if "vo" in stkFirst:
                        quotes[symbol]["volume"] = stkFirst["vo"]
                    if "cp" in stkFirst:
                        quotes[symbol]["chg_percent"] = stkFirst["cp"]
            except:
                logger.debug(f"StockValues_Google: failed to get quote for {symbol}")
                tryAlternateList.append(symbol)
        # Now try an alternate source
        for symbol in tryAlternateList:
            try:
                dotPos = symbol.find(".")
                if dotPos >= 0:
                    sym = symbol[:dotPos]
                    exchange = symbol[dotPos+1:]
                    if exchange == "L":
                        exchange = "LSE"
                    stockInfo = self.requestFromAlternate(sym, exchange)
                    quotes[symbol] = stockInfo
            except:
                logger.debug(f"Couldn't get quote for {symbol} from alternate source")
        return quotes

    # def stripQuotes(self, inStr):
    #     if inStr.startswith('"') and inStr.endswith('"'):
    #         inStr = inStr[1:-1]
    #     return inStr
    
    def requestFromGoogle(self, symbol):
        url = 'https://finance.google.com/finance?output=json&q=' + symbol
        logger.debug(f"StockValues_Google: Requesting {url}")
        req = Request(url)
        resp = urlopen(req)
        readVal = resp.read()
        jsonStr = str(readVal.decode('utf-8').strip())
        # Check if it starts with // and remove if so
        slashslashPos = jsonStr.find("//")
        if slashslashPos >= 0 and slashslashPos < 10:
            jsonStr = jsonStr[slashslashPos+2:].strip()
        if jsonStr.find("{") == 0:
            jsonStr = "[" + jsonStr + "]"
        return jsonStr

    def requestFromAlternate(self, symbol, exchange):

        url = 'http://eoddata.com/stockquote/' + exchange + "/" + symbol + ".htm"
        logger.debug(f"StockValues_Google: Requesting {url}")
        req = requests.get(url)
        # Get page and parse
        soup = BeautifulSoup(req.text, "html5lib")
        stockInfo = {}
        nameTable = soup.select("#ctl00_cph1_qp1_div1 div.rc_bg_bl table tr td")
        if len(nameTable) > 2:
            stockInfo["name"] = nameTable[1].getText().strip()

        perfTable = soup.select("#ctl00_cph1_qp1_div1 div.cb table tr td b")
        # Extract stocks table info

        attrNames = ["price", "change", "open", "high", "ask", "volume", "chg_percent", "prev", "low", "bid",
                     "open_int"]
        for elIdx in range(len(perfTable)):
            if elIdx >= len(attrNames):
                break
            stockInfo[attrNames[elIdx]] = perfTable[elIdx].getText().strip()
        return stockInfo
