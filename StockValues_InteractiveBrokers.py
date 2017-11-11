import threading
import datetime
import pytz
import time
import copy
import re
from ibapi.wrapper import EWrapper
from ibapi.client import EClient
from ibapi import contract, ticktype
from StockValues_Google import StockValues_Google

'''
Created on 11th November 2017

@author: rob dobson
'''

class MarketDataWrapper(EWrapper):
    """
    The wrapper deals with the action coming back from the IB gateway or TWS instance
    We override methods in EWrapper that will get called when this action happens
    """

    def __init__(self):
        pass

class MarketDataClient(EClient):
    """
    The client method
    We don't override native methods, but instead call them from our own wrappers
    """
    def __init__(self, wrapper):
        ## Set up with a wrapper inside
        EClient.__init__(self, wrapper)

class PriceGetter(MarketDataWrapper, MarketDataClient):
    _REQ_ID_PRICE_BASE = 10000000
    _REQ_ID_DETAILS_BASE = 200000
    _nextReqId = 1
    _mapPriceReqIdToStockInfo = {}
    _mapSymbolToPriceReqId = {}
    _mapDetailsReqIdToPriceReqId = {}
    _IB_SymbolMappings = {
        "^GSPC": { "symbol": "SPX", "exchange": "CBOE", "currency":"USD", "secType":"IND" },
        "^NYA": {"symbol": "INDU", "exchange": "NYSE", "currency": "USD", "secType": "IND"},
        "^FTSE": {"symbol": "TICK-LSE", "exchange": "LSE", "currency": "GBP", "secType": "IND"},
        "AV-B.L": {"symbol": "AV.B", "exchange": "LSE", "currency": "GBP", "secType": "STK"},
    }

    def __init__(self, ipaddress, portid, clientid, symbolChangedCallback):
        self._symbolChangedCallback = symbolChangedCallback
        # Initialise both base classes
        MarketDataWrapper.__init__(self)
        MarketDataClient.__init__(self, wrapper=self)
        # Connect using the passed params
        self.connect(ipaddress, portid, clientid)
        # Start a thread which runs the run() function inside EClient in the IB API
        self.getterThread = threading.Thread(target = self.run)
        self.getterThread.start()
        setattr(self, "_thread", self.getterThread)
        # A thread for adding the market requests
        self.requestAddStockList = []
        self.requestRemoveStockList = []
        self.requestStockListChanged = False
        self.requestListLock = threading.Lock()
        self.requestThreadRunning = True
        self.requestThread = threading.Thread(target = self.requestMarketData)
        self.requestThread.start()
        # A lock for the dictionary used to access symbol values
        self.mapsLock = threading.Lock()
        # Start the google getter too
        self._stockValuesFromGoogle = StockValues_Google(self.symbolChangedCallback)

    def error(self, reqId:int, errorCode:int, errorString:str):
        if errorCode == 200: # security not found
            self.mapsLock.acquire()
            if reqId in self._mapPriceReqIdToStockInfo:
                sym = self._mapPriceReqIdToStockInfo[reqId]["ySymbol"]
                print("StockValues: Symbol not matched", sym, "errorMsg", errorString)
                self._mapPriceReqIdToStockInfo.pop(reqId)
                if sym in self._mapSymbolToPriceReqId:
                    self._mapSymbolToPriceReqId.pop(sym)
                # Add to list of symbols to get from google
                self._stockValuesFromGoogle.addStock(sym)
            else:
                print("StockValues: Unknown symbol not found")
            self.mapsLock.release()
        else:
            print("StockValues: IB ERR reqId", reqId, "errorCode", errorCode, "errorStr", errorString)

    def stop(self):
        # Setting this flag avoids calling disconnect() twice (which throws an error)
        self._stockValuesFromGoogle.stop()
        self.done = True
        self.requestThreadRunning = False

    def setStocks(self, stockList):
        with self.requestListLock:
            self.requestAddStockList = []
            with self.mapsLock:
                for sym in stockList:
                    if sym not in self._mapSymbolToPriceReqId:
                        self.requestAddStockList.append(sym)
                for sym, reqId in self._mapSymbolToPriceReqId.items():
                    if sym not in stockList:
                        self.requestRemoveStockList.append(sym)
            if len(self.requestAddStockList) > 0 or len(self.requestRemoveStockList) > 0:
                self.requestStockListChanged = True

    def clear(self):
        # Stop getting each symbol from the market data feed
        for reqId, stockItem in self._mapPriceReqIdToStockInfo.items():
            self.cancelMktData(reqId)
        # Lock here as we're changing the mappings
        self.mapsLock.acquire()
        # Clear maps
        self._mapSymbolToPriceReqId.clear()
        self._mapPriceReqIdToStockInfo.clear()
        self._mapDetailsReqIdToPriceReqId.clear()
        # Release lock
        self.mapsLock.release()
        # Set reqId back
        self._nextReqId = 1

    def addYSymbol(self, ySymbol):
        # Check if this stock is already being acquired
        if ySymbol in self._mapSymbolToPriceReqId:
            return
        # Get the contract (stockInfo) in the form needed for interactiveBrokers API
        stockInfo = self.makeStockInfo(ySymbol)
        # Ticker Id is used to communicate with the API - called reqId in the API
        curPriceReqId = self._REQ_ID_PRICE_BASE + self._nextReqId
        stockInfo["priceReqId"] = curPriceReqId
        # Info used by the IB API
        contractInfo = self.getContractInfo(stockInfo)
        stockInfo["contractInfo"] = contractInfo
        # Add to the lookups for the symbol and tickId
        self.mapsLock.acquire()
        self._mapSymbolToPriceReqId[ySymbol] = curPriceReqId
        self._mapPriceReqIdToStockInfo[curPriceReqId] = stockInfo
        self.mapsLock.release()
        # Start the API getting this symbol
        self.reqMktData(curPriceReqId, contractInfo, "", False, False, [])
        # No reuse of tickIds currently
        self._nextReqId += 1

    def removeSymbol(self, ySymbol):
        # Check we have the symbol
        if ySymbol in self._mapSymbolToPriceReqId:
            # Remove from maps
            tickId = self._mapSymbolToPriceReqId[ySymbol]
            self.mapsLock.acquire()
            self._mapSymbolToPriceReqId.pop(ySymbol, None)
            self._mapPriceReqIdToStockInfo.pop(tickId, None)
            self.mapsLock.release()
            # Stop the API getting this symbol
            self.cancelMktData(tickId)

    def makeStockInfo(self, ySymbol):
        nowInUk = datetime.datetime.now(pytz.timezone('GB'))
        # Base record
        stkInfo = {"ySymbol": ySymbol, "symbol": ySymbol, "name": "", "exchange": "SMART",
                    "currency": "USD", "secType": "STK", "includeExpired": False,
                    "failCount": 0, "time": nowInUk}
        if ySymbol in self._IB_SymbolMappings:
            for key, val in self._IB_SymbolMappings[ySymbol].items():
                stkInfo[key] = val
        else:
            # Split YSymbol apart to find underlying exchange and symbol
            # Attempt to handle Yahoo style ticker symbols
            dotPos = ySymbol.rfind(".")
            if dotPos > 0:
                if ySymbol[dotPos+1:] == "L":
                    stkInfo["exchange"] = "LSE"
                    stkInfo["currency"] = "GBP"
                    symb = ySymbol[:dotPos]
                    if len(symb) == 2:
                        symb += "."
                    stkInfo["symbol"] = symb
            else:
                atPos = ySymbol.rfind("@")
                if atPos > 0:
                    stkInfo["primaryExchange"] = ySymbol[atPos+1:]
                    symb = ySymbol[:atPos]
                    if len(symb) == 2:
                        symb += "."
                    stkInfo["symbol"] = symb
        return stkInfo

    def getContractInfo(self, stockInfo):
        c = contract.Contract()
        c.conId = 0
        c.symbol = stockInfo["symbol"]
        c.exchange = stockInfo["exchange"]
        c.currency = stockInfo["currency"]
        c.secType = stockInfo["secType"]
        if "primaryExchange" in stockInfo:
            c.primaryExchange = stockInfo["primaryExchange"]
        c.includeExpired = stockInfo["includeExpired"]
        return c

    def requestMarketData(self):
        while self.requestThreadRunning:
            # Check if there is new data
            if self.requestStockListChanged:
                self.requestStockListChanged = False
                # Add new stocks
                stockList = []
                with self.requestListLock:
                    for stk in self.requestAddStockList:
                        stockList.append(stk)
                # Go through adding stocks
                for stk in stockList:
                    self.addYSymbol(stk)
                # Remove unwanted stocks
                stockList = []
                with self.requestListLock:
                    for stk in self.requestRemoveStockList:
                        stockList.append(stk)
                # Go through adding stocks
                for stk in stockList:
                    self.removeSymbol(stk)
            time.sleep(1)

    def marketDataCallback(self, reqId, tickType, price, attrib):
        pass

    def tickPrice(self, reqId, tickType:ticktype.TickType, price:float, attrib):
        # Acquire lock on maps
        symbolDataChanged = None
        self.mapsLock.acquire()
        if reqId in self._mapPriceReqIdToStockInfo:
            stockInfo = self._mapPriceReqIdToStockInfo[reqId]
            if tickType == 4: # last
                if "price" not in stockInfo or stockInfo["price"] is None or stockInfo["price"] != price:
                    stockInfo["price"] = price
                    symbolDataChanged = stockInfo["ySymbol"]
                    if "open" in stockInfo and stockInfo["open"] is not None:
                        stockInfo["change"] = price - stockInfo["open"]
                        if price != 0:
                            stockInfo["chg_percent"] = 100 * (price - stockInfo["open"]) / price
            elif ticktype == 14: # open
                if "open" not in stockInfo or stockInfo["open"] is None or stockInfo["open"] != price:
                    stockInfo["open"] = price
                    symbolDataChanged = stockInfo["ySymbol"]
            elif ticktype == 8: # volume
                if "volume" not in stockInfo or stockInfo["volume"] is None or stockInfo["volume"] != price:
                    stockInfo["volume"] = price
                    symbolDataChanged = stockInfo["ySymbol"]
            elif tickType == 9: # close
                if "close" not in stockInfo or stockInfo["close"] is None or stockInfo["close"] != price:
                    stockInfo["close"] = price
                    stockInfo["price"] = price
                    symbolDataChanged = stockInfo["ySymbol"]
            # else:
            #     print("Received tickType", tickType, "price", price)
            if symbolDataChanged:
                nowInUk = datetime.datetime.now(pytz.timezone('GB'))
                stockInfo["time"] = nowInUk
            # Check if detailed info (long name of stock etc) already requested
            if "detailsReqId" not in stockInfo:
                # Request contract details for this symbol
                detailsReqId = self._REQ_ID_DETAILS_BASE + self._nextReqId
                self.reqContractDetails(detailsReqId, stockInfo["contractInfo"])
                self._mapDetailsReqIdToPriceReqId[detailsReqId] = stockInfo["priceReqId"]
                stockInfo["detailsReqId"] = detailsReqId
                self._nextReqId += 1
        # Release the lock on the map
        self.mapsLock.release()
        # Callback if data has changed
        if symbolDataChanged is not None:
            self._symbolChangedCallback(symbolDataChanged)

    def contractDetails(self, reqId:int, contractDetails):
        self.mapsLock.acquire()
        if reqId in self._mapDetailsReqIdToPriceReqId:
            priceReqId = self._mapDetailsReqIdToPriceReqId[reqId]
            if priceReqId in self._mapPriceReqIdToStockInfo:
                stockInfo = self._mapPriceReqIdToStockInfo[priceReqId]
                stockInfo["name"] = contractDetails.longName
                self._symbolChangedCallback(stockInfo["ySymbol"])
        self.mapsLock.release()

    def contractDetailsEnd(self, reqId:int):
        pass

    def getStockInfoData(self, ySymbol):
        if ySymbol not in self._mapSymbolToPriceReqId:
            return self._stockValuesFromGoogle.getStockInfoData(ySymbol)
        reqId = self._mapSymbolToPriceReqId[ySymbol]
        self.mapsLock.acquire()
        dat = copy.copy(self._mapPriceReqIdToStockInfo[reqId])
        self.mapsLock.release()
        return dat

    def symbolChangedCallback(self, symbol):
        self._symbolChangedCallback(symbol)

class StockValues_InteractiveBrokers:
    bOnlyUpdateWhileMarketOpen = False
    
    def __init__(self):
        self.openhour = 8
        self.openmin = 0
        self.closehour = 16
        self.closemin = 30
        self.tradingdow = 0, 1, 2, 3, 4
        self._priceGetter = PriceGetter("127.0.0.1", 4001, 10, self.symbolDataChanged)
        self._dictOfStocksChangedSinceUIUpdate = {}
        self._lockOnStockChangeList = threading.Lock()
        
    def setStocks(self, stockList):
        # Set list of symbols got by the API
        self._priceGetter.setStocks(stockList)

    def symbolDataChanged(self, symbol):
        with self._lockOnStockChangeList:
            self._dictOfStocksChangedSinceUIUpdate[symbol] = True
            # print("UpdateTo", symbol, "len", len(self._dictOfStocksChangedSinceUIUpdate))

    def getMapOfStocksChangedSinceUIUpdated(self):
        changedStockDict = {}
        with self._lockOnStockChangeList:
            changedStockDict = copy.copy(self._dictOfStocksChangedSinceUIUpdate)
            self._dictOfStocksChangedSinceUIUpdate = {}
        return changedStockDict

    def getStockData(self, sym):
        return self._priceGetter.getStockInfoData(sym)

    def setOnlyUpdateWhenMarketOpen(self, onlyWhenOpen):
        self.bOnlyUpdateWhileMarketOpen = onlyWhenOpen
        
    def run(self):
        pass

    def stop(self):
        self._priceGetter.stop()

    def getMarketOpenStatus(self):
        nowInUk = datetime.datetime.now(pytz.timezone('GB'))
        open_time = nowInUk.replace( hour=self.openhour, minute=self.openmin, second=0 )
        close_time = nowInUk.replace( hour=self.closehour, minute=self.closemin, second=0 )
        open_day = False
        for day in self.tradingdow:
            if ( day == nowInUk.weekday() ):
                open_day = True
        marketOpen = (nowInUk > open_time) and (nowInUk < close_time) and open_day
        return "Market Open" if marketOpen else "Market Closed"

