import threading
import datetime
import time
import copy
from urllib.request import Request, urlopen

'''
Created on 24 Sep 2013

@author: rob dobson
'''

class StockValues:
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
        self.stockData = {}
        self.lock = threading.Lock()
        self.status = ""
        self.listUpdateLock = threading.Lock()
        
    def setStocks(self, stockList):
        yahooList = []
        for sym in stockList:
            yahooList.append(sym)
        self.listUpdateLock.acquire()
        self.pendingTickerlist = yahooList
        self.listUpdateLock.release()

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
        self.t = threading.Thread(target=self.do_thread_loop)
        self.t.start()        

    def stop(self):
        self.running = False
        
    def do_thread_loop(self):
        firstpass = True
        nextStockIdx = 0
        maxStocksPerPass = 50
        while self.running:

            # Sleep for a bit
            time.sleep(10)

            # Check if the stock list has been updated
            self.listUpdateLock.acquire()
            if self.pendingTickerlist != None:
                self.tickerlist = self.pendingTickerlist
                self.pendingTickerlist = None
            self.listUpdateLock.release()

            # Check if the market opening times are important
            now = datetime.datetime.now()
            open_time = now.replace( hour=self.openhour, minute=self.openmin, second=0 )
            close_time = now.replace( hour=self.closehour, minute=self.closemin, second=0 )
            open_day = False
            for day in self.tradingdow:
                if ( day == datetime.datetime.today().weekday() ):
                    open_day = True
            updateNeeded = True
            if self.bOnlyUpdateWhileMarketOpen:
                if not( firstpass or (( now > open_time) and ( now < close_time ) and open_day)):
                    updateNeeded = False
            if not updateNeeded:
                self.status = "Market Closed"
                continue

            # Check list isn't empty
            if len(self.tickerlist) <= 0:
                continue

            # Update the list
            firstpass = False
            stocks = self.tickerlist[nextStockIdx:nextStockIdx+maxStocksPerPass]
            if len(stocks) <= 0:
                continue

            stkdataValid = False
            try:
                stkdata = self.get_quotes(stocks)
                stkdataValid = True
            except:
                print ("get_quote failed for " + str(nextStockIdx))
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
                        self.stockData[ticker] = values
                        self.stockData[ticker]['failCount'] = 0
                        self.stockData[ticker]['time'] = now
                finally:
                    self.lock.release()

            if nextStockIdx + maxStocksPerPass >= len(self.tickerlist):
                nextStockIdx = 0
            else:
                nextStockIdx += maxStocksPerPass

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
#        if len(symbols) != len(lines):
#            print("Problem - returned values don't match symbols - numSym " + str(len(symbolList)) + ", str(numVals)" + len(lines))
#            return {}
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
        #print ("Requesting " + url)
        req = Request(url)
        resp = urlopen(req)
        readVal = resp.read()
        return str(readVal.decode('utf-8').strip())
