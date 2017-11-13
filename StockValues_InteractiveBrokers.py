import threading
import datetime
import pytz
import time
import copy
import re
from ibapi.wrapper import EWrapper
from ibapi.client import EClient
from ibapi import contract
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
        "INDEXSP:.INX": { "symbol": "SPX", "exchange": "CBOE", "currency":"USD", "secType":"IND" },
        "INDEXDJX:.DJI": {"symbol": "INDU", "exchange": "NYSE", "currency": "USD", "secType": "IND"},
        # "INDEXFTSE:UKX": {"symbol": "TICK-LSE", "exchange": "LSE", "currency": "GBP", "secType": "IND"},
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
        if errorCode == 200 or errorCode == 504: # security not found OR not connected
            with self.mapsLock:
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
        else:
            if reqId == -1:
                print("StockValues: IB INFO msgCode", errorCode, "msgStr", errorString)
            else:
                print("StockValues: IB INFO reqId", reqId, "msgCode", errorCode, "msgStr", errorString)

    def stop(self):
        # Setting this flag avoids calling disconnect() twice (which throws an error)
        self._stockValuesFromGoogle.stop()
        self.done = True
        self.requestThreadRunning = False

    def setStocks(self, stockList):
        # Send full list to google getter (for slow rate updates - e.g. when market closed)
        self._stockValuesFromGoogle.setAllStocks(stockList)
        # Record list to be got
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

    def setValInStockDict(self, sym, elemName, val, stockDict):
        if elemName not in stockDict or stockDict[elemName] is None or stockDict[elemName] != val:
            stockDict[elemName] = val
            return sym
        return None

    def setChangeInStockDict(self, sym, stockDict):
        if "close" in stockDict and stockDict["close"] is not None and "price" in stockDict and stockDict["price"] is not None:
            last = stockDict["price"]
            stockDict["change"] = priceChange = last - stockDict["close"]
            if last != 0:
                stockDict["chg_percent"] = 100 * (priceChange) / last

    def tickPrice(self, reqId, tickType:int, price:float, attrib):
        # Acquire lock on maps
        symbolDataChanged = None
        with self.mapsLock:
            if reqId in self._mapPriceReqIdToStockInfo:
                stockInfo = self._mapPriceReqIdToStockInfo[reqId]
                sym = stockInfo["ySymbol"]
                if tickType == 1:  # bid_price
                    # Not this does not set symbolDataChanged
                    self.setValInStockDict(sym, "bid_price", price, stockInfo)
                elif tickType == 2:  # ask_price
                    # Not this does not set symbolDataChanged
                    self.setValInStockDict(sym, "ask_price", price, stockInfo)
                elif tickType == 4: # last
                    symbolDataChanged = self.setValInStockDict(sym, "price", price, stockInfo)
                    if symbolDataChanged:
                        self.setChangeInStockDict(sym, stockInfo)
                elif tickType == 6:  # high
                    symbolDataChanged = self.setValInStockDict(sym, "high", price, stockInfo)
                elif tickType == 7:  # low
                    symbolDataChanged = self.setValInStockDict(sym, "low", price, stockInfo)
                elif tickType == 9: # close
                    symbolDataChanged = self.setValInStockDict(sym, "close", price, stockInfo)
                    if "price" not in stockInfo or stockInfo["price"] is None:
                        self.setValInStockDict(sym, "price", price, stockInfo)
                    if symbolDataChanged:
                        self.setChangeInStockDict(sym, stockInfo)
                elif tickType == 14:  # open
                    symbolDataChanged = self.setValInStockDict(sym, "open", price, stockInfo)
                    if "price" not in stockInfo or stockInfo["price"] is None:
                        self.setValInStockDict(sym, "price", price, stockInfo)
                else:
                    print("StockValues: Unhandled tickPrice", tickType, "price", price)
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
        # Callback if data has changed
        if symbolDataChanged is not None:
            self._symbolChangedCallback(symbolDataChanged)

    def tickSize(self, reqId:int, tickType:int, size:int):
        # Acquire lock on maps
        symbolDataChanged = None
        with self.mapsLock:
            if reqId in self._mapPriceReqIdToStockInfo:
                stockInfo = self._mapPriceReqIdToStockInfo[reqId]
                sym = stockInfo["ySymbol"]
                if tickType == 0:  # bid_size
                    self.setValInStockDict(sym, "bid_size", size, stockInfo)
                elif tickType == 3:  # ask_size
                    self.setValInStockDict(sym, "ask_size", size, stockInfo)
                elif tickType == 5:  # last_size
                    self.setValInStockDict(sym, "last_size", size, stockInfo)
                elif tickType == 8:  # volume
                    symbolDataChanged = self.setValInStockDict(sym, "volume", size, stockInfo)
                else:
                    print("StockValues: Unhandled tickSize", tickType, "size", size)
                if symbolDataChanged:
                    nowInUk = datetime.datetime.now(pytz.timezone('GB'))
                    stockInfo["time"] = nowInUk
        # Callback if data has changed
        if symbolDataChanged is not None:
            self._symbolChangedCallback(symbolDataChanged)

    def tickString(self, reqId:int, tickType:int, value:str):
        if tickType == 32: # ask_exch
            pass
        elif tickType == 33: # bid_exch
            pass
        elif tickType == 45: # last_timestamp
            pass
        elif tickType == 84: # last_exch
            pass
        else:
            print("StockValues: Unhandled tickString", tickType, "str", value)

    def tickGeneric(self, reqId:int, tickType:int, value:float):
        print("StockValues: Unhandled tickGeneric", tickType, "float", value)

    def tickEFP(self, reqId:int, tickType:int, basisPoints:float,
                formattedBasisPoints:str, totalDividends:float,
                holdDays:int, futureLastTradeDate:str, dividendImpact:float,
                dividendsToLastTradeDate:float):
        print("StockValues: Unhandled tickEFP", tickType, "basisPoints", basisPoints,
                "formattedBasisPoints", formattedBasisPoints, "totalDividends", totalDividends,
                "holdDays", holdDays, "futureLastTradeDate", futureLastTradeDate,
                "dividendImpact", dividendImpact, "dividendsToLastTradeDate", dividendsToLastTradeDate)

    def tickSnapshotEnd(self, reqId:int):
        print("StockValues: Unhandled tickSnapshotEnd", reqId)

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
        stockInfo = self._stockValuesFromGoogle.getStockInfoData(ySymbol)
        if stockInfo is None:
            stockInfo = {}
        reqId = self._mapSymbolToPriceReqId[ySymbol]
        with self.mapsLock:
            for k,v in self._mapPriceReqIdToStockInfo[reqId].items():
                if k != "price" or v != 0:
                    stockInfo[k] = v
        return stockInfo

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

