import threading
import datetime
import pytz
import time
import copy
from urllib.request import Request, urlopen
import logging

'''
Created on 24 Sep 2013

@author: rob dobson
'''

logger = logging.getLogger("StockTickerLogger")

class StockValues_Yahoo:
    bOnlyUpdateWhileMarketOpen = False
    
    def __init__(self):
        self.tickerlist = []
        self.pendingTickerList = None
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
        
    def setStocks(self, stockList):
        curList = []
        for sym in stockList:
            curList.append(sym)
        self.listUpdateLock.acquire()
        self.pendingTickerlist = curList
        self.listUpdateLock.release()

    def checkAndSetUIUpdateDataChange(self):
        tmpDataChange = self.dataUpdatedSinceLastUIUpdate
        self.dataUpdatedSinceLastUIUpdate = False
        return tmpDataChange

    def getStockData(self, sym):
        self.lock.acquire()
        dat = None
        if sym in self.stockData:
            dat = copy.copy(self.stockData[sym])
        self.lock.release()
        return dat
    
    def setOnlyUpdateWhenMarketOpen(self, onlyWhenOpen):
        self.bOnlyUpdateWhileMarketOpen = onlyWhenOpen
        
    def run(self):
        self.running = True
        self.t = threading.Thread(target=self.stockUpdateThread)
        self.t.start()        

    def stop(self):
        self.running = False
        
    def stockUpdateThread(self):
        firstpass = True
        nextStockIdx = 0
        maxStocksPerPass = 50
        while self.running:

            # Sleep for a bit
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
            except:
                logger.debug(f"stockUpdateThread get_quote failed for {nextStockIdx}")
                self.status = "failed for " + str(nextStockIdx)
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
                                break
                        self.stockData[ticker] = values
                        self.stockData[ticker]['failCount'] = 0
                        self.stockData[ticker]['time'] = nowInUk
                finally:
                    self.lock.release()

            if nextStockIdx + maxStocksPerPass >= len(self.tickerlist):
                nextStockIdx = 0
                firstpass = False
            else:
                nextStockIdx += maxStocksPerPass
            delayTime = 0 if firstpass else (9 if marketOpen else 600)
            for delayCount in range(delayTime):
                if not self.running:
                    break
                time.sleep(1)

    def get_quotes(self, symbols):
        """
        Get all available quote data for the given ticker symbols.

        Returns a dictionary.
        """
        symbolList = ""
        for symbol in symbols:
            if symbolList != "":
                symbolList += ","
            symbolList+=symbol
        lines = self._request(symbolList, 'sl1c1vp2n').split('\n')
        quotes = {}
        for symIdx in range(len(lines)):
            values = lines[symIdx].strip().split(',')
            ticker = self.stripQuotes(values[0])
            quotes[ticker] = dict(
                        price=values[1],
                        change=values[2],
                        volume=values[3],
                        chg_percent=self.stripQuotes(values[4]),
                        name=self.stripQuotes(values[5]),
                    )
        return quotes

    def stripQuotes(self, inStr):
        if inStr.startswith('"') and inStr.endswith('"'):
            inStr = inStr[1:-1]
        return inStr
    
    # Borrowed from ystockquote
    def _request(self, symbol, stat):
        url = 'http://finance.yahoo.com/d/quotes.csv?s=%s&f=%s' % (symbol, stat)
        req = Request(url)
        resp = urlopen(req)
        readVal = resp.read()
        return str(readVal.decode('utf-8').strip())
