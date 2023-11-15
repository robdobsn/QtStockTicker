import threading
import datetime
import pytz
import time
import copy
from ibapi.wrapper import EWrapper
from ibapi.client import EClient
from ibapi import contract
from StockValues_Google import StockValues_Google
import logging

'''
Created on 11th November 2017

@author: rob dobson
'''

logger = logging.getLogger("StockTickerLogger")

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

    def __init__(self, ipaddress, portid, clientid, symbolChangedCallback):

        self.DEBUG_IB_TICK_VALUES = False

        self._REQ_ID_PRICE_BASE = 10000000
        self._REQ_ID_DETAILS_BASE = 200000
        self._nextReqId = 1
        self._mapPriceReqIdToStockInfo = {}
        self._mapSymbolToPriceReqId = {}
        self._mapDetailsReqIdToPriceReqId = {}
        self._IB_SymbolMappings = {
            "INDEXSP:.INX": { "symbol": "SPX", "exchange": "CBOE", "currency":"USD", "secType":"IND" },
            "INDEXDJX:.DJI": {"symbol": "INDU", "exchange": "NYSE", "currency": "USD", "secType": "IND"},
            # "INDEXFTSE:UKX": {"symbol": "TICK-LSE", "exchange": "LSE", "currency": "GBP", "secType": "IND"},
            "AV-B.L": {"symbol": "AV.B", "exchange": "LSE", "currency": "GBP", "secType": "STK"},
        }
        self.setTickCodes()
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
                    logger.warn(f"StockValues: IB ERROR reqId {reqId} Symbol not matched {sym} errorMsg {errorString}")
                    self._mapPriceReqIdToStockInfo.pop(reqId)
                    if sym in self._mapSymbolToPriceReqId:
                        self._mapSymbolToPriceReqId.pop(sym)
                    # Add to list of symbols to get from google
                    self._stockValuesFromGoogle.addStock(sym)
                else:
                    logger.warn(f"StockValues: IB unknown symbol reqId {reqId} errorMsg {errorString}")
        else:
            if reqId == -1:
                logger.warn(f"StockValues: IB ERROR msgCode {errorCode} msgStr {errorString}")
            else:
                logger.warn(f"StockValues: IB ERROR reqId {reqId} msgCode {errorCode} msgStr {errorString}")

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
        if self.DEBUG_IB_TICK_VALUES and tickType in self.tickCodes:
            logger.debug(f"tick {self.tickCodes.get(tickType)[1]} ... PRICE {price} ATTRIB {attrib}")
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
                    logger.warn(f"StockValues: Unhandled tickPrice {tickType} price {price}")
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
        if self.DEBUG_IB_TICK_VALUES and tickType in self.tickCodes:
            logger.debug(f"tick {self.tickCodes.get(tickType)[1]} ... SIZE {size}")
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
                    logger.warn(f"StockValues: Unhandled tickSize {tickType} size {size}")
                if symbolDataChanged:
                    nowInUk = datetime.datetime.now(pytz.timezone('GB'))
                    stockInfo["time"] = nowInUk
        # Callback if data has changed
        if symbolDataChanged is not None:
            self._symbolChangedCallback(symbolDataChanged)

    def tickString(self, reqId:int, tickType:int, value:str):
        if self.DEBUG_IB_TICK_VALUES and tickType in self.tickCodes:
            logger.debug(f"tick {self.tickCodes.get(tickType)[1]} ... VALUE {value}")
        # if tickType == 32: # ask_exch
        #     pass
        # elif tickType == 33: # bid_exch
        #     pass
        # elif tickType == 45: # last_timestamp
        #     pass
        # elif tickType == 84: # last_exch
        #     logger.debug(f"last_exch str {value}")
        # else:
        #     logger.warn(f"StockValues: Unhandled tickString {tickType} str {value}")

    def tickGeneric(self, reqId:int, tickType:int, value:float):
        if self.DEBUG_IB_TICK_VALUES and tickType in self.tickCodes:
            logger.debug(f"tick {self.tickCodes.get(tickType)[1]} ... VALUE {value}")
        # logger.warn(f"StockValues: Unhandled tickGeneric {tickType} float {value}")

    def tickEFP(self, reqId:int, tickType:int, basisPoints:float,
                formattedBasisPoints:str, totalDividends:float,
                holdDays:int, futureLastTradeDate:str, dividendImpact:float,
                dividendsToLastTradeDate:float):
        logger.info(f"StockValues: Unhandled tickEFP {tickType} basisPoints {basisPoints} formattedBasisPoints {formattedBasisPoints} totalDividends {totalDividends} holdDays {holdDays} futureLastTradeDate {futureLastTradeDate} dividendImpact {dividendImpact} dividendsToLastTradeDate {dividendsToLastTradeDate}")

    def tickSnapshotEnd(self, reqId:int):
        logger.info(f"StockValues: Unhandled tickSnapshotEnd {reqId}")

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

    def setTickCodes(self):
        self.tickCodes = {
            0: ["bid_size", "Bid Size", "Number of contracts or lots offered at the bid price.", "IBApi.EWrapper.tickSize", "-"],
            1: ["bid_price", "Bid Price", "Highest priced bid for the contract.", "IBApi.EWrapper.tickPrice", "-"],
            2: ["ask_price", "Ask Price", "Lowest price offer on the contract.", "IBApi.EWrapper.tickPrice", "-"],
            3: ["ask_size", "Ask Size", "Number of contracts or lots offered at the ask price.", "IBApi.EWrapper.tickSize", "-"],
            4: ["price", "Last Price", "Last price at which the contract traded (does not include some trades in RTVolume).", "IBApi.EWrapper.tickPrice", "-"],
            5: ["last_size", "Last Size", "Number of contracts or lots traded at the last price.", "IBApi.EWrapper.tickSize", "-"],
            6: ["high", "High", "High price for the day.", "IBApi.EWrapper.tickPrice", "-"],
            7: ["low", "Low", "Low price for the day.", "IBApi.EWrapper.tickPrice", "-"],
            8: ["volume", "Volume", "Trading volume for the day for the selected contract (US Stocks: multiplier 100).", "IBApi.EWrapper.tickSize", "-"],
            9: ["close", "Close Price", "The last available closing price for the previous day. For US Equities, we use corporate action processing to get the closing price, so the close price is adjusted to reflect forward and reverse splits and cash and stock dividends.", "IBApi.EWrapper.tickPrice", "-"],
            10: ["bid_option_comp", "Bid Option Computation", "Computed Greeks and implied volatility based on the underlying stock price and the option bid price. See Option Greeks", "IBApi.EWrapper.tickOptionComputation", "-"],
            11: ["ask_option_comp", "Ask Option Computation", "Computed Greeks and implied volatility based on the underlying stock price and the option ask price. See Option Greeks", "IBApi.EWrapper.tickOptionComputation", "-"],
            12: ["last_option_comp", "Last Option Computation", "Computed Greeks and implied volatility based on the underlying stock price and the option last traded price. See Option Greeks", "IBApi.EWrapper.tickOptionComputation", "-"],
            13: ["model_option_comp", "Model Option Computation", "Computed Greeks and implied volatility based on the underlying stock price and the option model price. Correspond to greeks shown in TWS. See Option Greeks", "IBApi.EWrapper.tickOptionComputation", "-"],
            14: ["open", "Open Tick", "Current session's opening price. Before open will refer to previous day. The official opening price requires a market data subscription to the native exchange of the instrument.", "IBApi.EWrapper.tickPrice", "-"],
            15: ["low_13wk", "Low 13 Weeks", "Lowest price for the last 13 weeks. For stocks only.", "IBApi.EWrapper.tickPrice", "165"],
            16: ["high_13wk", "High 13 Weeks", "Highest price for the last 13 weeks. For stocks only.", "IBApi.EWrapper.tickPrice", "165"],
            17: ["low_26wk", "Low 26 Weeks", "Lowest price for the last 26 weeks. For stocks only.", "IBApi.EWrapper.tickPrice", "165"],
            18: ["high_26wk", "High 26 Weeks", "Highest price for the last 26 weeks. For stocks only.", "IBApi.EWrapper.tickPrice", "165"],
            19: ["low_52wk", "Low 52 Weeks", "Lowest price for the last 52 weeks. For stocks only.", "IBApi.EWrapper.tickPrice", "165"],
            20: ["high_52wk", "High 52 Weeks", "Highest price for the last 52 weeks. For stocks only.", "IBApi.EWrapper.tickPrice", "165"],
            21: ["avg_volume", "Average Volume", "The average daily trading volume over 90 days. Multiplier of 100. For stocks only.", "IBApi.EWrapper.tickSize", "165"],
            22: ["open_interest", "Open Interest", "(Deprecated, not currently in use) Total number of options that are not closed.", "IBApi.EWrapper.tickSize", "-"],
            23: ["option_hist_vol", "Option Historical Volatility", "The 30-day historical volatility (currently for stocks).", "IBApi.EWrapper.tickGeneric", "104"],
            24: ["option_imp_vol", "Option Implied Volatility", "A prediction of how volatile an underlying will be in the future. The IB 30-day volatility is the at-market volatility estimated for a maturity thirty calendar days forward of the current trading day, and is based on option prices from two consecutive expiration months.", "IBApi.EWrapper.tickGeneric", "106"],
            25: ["option_bid_exch", "Option Bid Exchange", "Not Used.", "IBApi.EWrapper.tickString", "-"],
            26: ["option_ask_exch", "Option Ask Exchange", "Not Used.", "IBApi.EWrapper.tickString", "-"],
            27: ["option_call_open_int", "Option Call Open Interest", "Call option open interest.", "IBApi.EWrapper.tickSize", "101"],
            28: ["option_put_open_int", "Option Put Open Interest", "Put option open interest.", "IBApi.EWrapper.tickSize", "101"],
            29: ["option_call_volume", "Option Call Volume", "Call option volume for the trading day.", "IBApi.EWrapper.tickSize", "100"],
            30: ["option_put_volume", "Option Put Volume", "Put option volume for the trading day.", "IBApi.EWrapper.tickSize", "100"],
            31: ["index_future_premium", "Index Future Premium", "The number of points that the index is over the cash index.", "IBApi.EWrapper.tickGeneric", "162"],
            32: ["bid_exch", "Bid Exchange", "For stock and options, identifies the exchange(s) posting the bid price. See Component Exchanges", "IBApi.EWrapper.tickString", "-"],
            33: ["ask_exch", "Ask Exchange", "For stock and options, identifies the exchange(s) posting the ask price. See Component Exchanges", "IBApi.EWrapper.tickString", "-"],
            34: ["auction_volume", "Auction Volume", "The number of shares that would trade if no new orders were received and the auction were held now.", "IBApi.EWrapper.tickSize", "225"],
            35: ["auction_price", "Auction Price", "The price at which the auction would occur if no new orders were received and the auction were held now- the indicative price for the auction. Typically received after Auction imbalance (tick type 36)", "IBApi.EWrapper.tickPrice", "225"],
            36: ["auction_imbalance", "Auction Imbalance", "The number of unmatched shares for the next auction; returns how many more shares are on one side of the auction than the other. Typically received after Auction Volume", "IBApi.EWrapper.tickSize", "225"],
            37: ["mark_price", "Mark Price", "The mark price is equal to the midpoint of the best bid and ask prices. It is calculated by TWS/IBKR and is not tradable.", "IBApi.EWrapper.tickPrice", "232"],
            38: ["bid_efp_computation", "Bid EFP Computation", "The computed implied exchange for a stock or index future price. Used in conjunction with the EFP (Exchange for Physical) field.", "IBApi.EWrapper.tickEFP", "-"],
            39: ["ask_efp_computation", "Ask EFP Computation", "The computed implied exchange for a stock or index future price. Used in conjunction with the EFP (Exchange for Physical) field.", "IBApi.EWrapper.tickEFP", "-"],
            40: ["last_efp_computation", "Last EFP Computation", "The computed implied exchange for a stock or index future price. Used in conjunction with the EFP (Exchange for Physical) field.", "IBApi.EWrapper.tickEFP", "-"],
            41: ["open_efp_computation", "Open EFP Computation", "The computed implied exchange for a stock or index future price. Used in conjunction with the EFP (Exchange for Physical) field.", "IBApi.EWrapper.tickEFP", "-"],
            42: ["high_efp_computation", "High EFP Computation", "The computed implied exchange for a stock or index future price. Used in conjunction with the EFP (Exchange for Physical) field.", "IBApi.EWrapper.tickEFP", "-"],
            43: ["low_efp_computation", "Low EFP Computation", "The computed implied exchange for a stock or index future price. Used in conjunction with the EFP (Exchange for Physical) field.", "IBApi.EWrapper.tickEFP", "-"],
            44: ["close_efp_computation", "Close EFP Computation", "The computed implied exchange for a stock or index future price. Used in conjunction with the EFP (Exchange for Physical) field.", "IBApi.EWrapper.tickEFP", "-"],
            45: ["last_timestamp", "Last Timestamp", "The time of the last trade. For US stocks, a millisecond timestamp is used. For non-US stocks, an IB system time timestamp is used.", "IBApi.EWrapper.tickString", "-"],
            46: ["shortable", "Shortable", "Indicates if the contract can currently be shorted. The availability of shortable shares is indicative only and is not guaranteed. For more information on shortable shares, see the Shortable Shares Availability section of the TWS Users' Guide.", "IBApi.EWrapper.tickString", "236"],
            47: ["fundamental_ratios", "Fundamental Ratios", "Fundamental ratios.", "IBApi.EWrapper.tickString", "-"],
            48: ["rt_volume", "RTVolume", "Real-time volume for the day for the selected contract (US Stocks: multiplier 100).", "IBApi.EWrapper.tickSize", "233"],
            49: ["halted", "Halted", "Indicates if the contract is halted", "IBApi.EWrapper.tickString", "-"],
            50: ["bid_yield", "Bid Yield", "Implied yield of the bond if it is purchased at the current bid", "IBApi.EWrapper.tickString", "-"],
            51: ["ask_yield", "Ask Yield", "Implied yield of the bond if it is purchased at the current ask", "IBApi.EWrapper.tickString", "-"],
            52: ["last_yield", "Last Yield", "Implied yield of the bond if it is purchased at the last price", "IBApi.EWrapper.tickString", "-"],
            53: ["cust_option_computation", "Cust Option Computation", "Custom option computation.", "IBApi.EWrapper.tickOptionComputation", "-"],
            54: ["trade_count", "Trade Count", "Trade count for the day", "IBApi.EWrapper.tickGeneric", "293"],
            55: ["trade_rate", "Trade Count Per Minute", "Trade rate per minute", "IBApi.EWrapper.tickGeneric", "294"],
            56: ["volume_rate", "Volume Per Minute", "Volume per minute", "IBApi.EWrapper.tickGeneric", "295"],
            57: ["last_rth_trade", "Last RTH Trade", "Last Regular Trading Hours trade price.", "IBApi.EWrapper.tickPrice", "318"],
            58: ["rt_historical_vol", "Realtime Historical Volatility", "30-day real time historical volatility", "IBApi.EWrapper.tickGeneric", "411"],
            59: ["ib_dividends", "IB Dividends", "Contract's dividends. See IB Dividends", "IBApi.EWrapper.tickGeneric", "456"],
            60: ["bond_factor_multiplier", "Bond Factor Multiplier", "The bond factor is a number that indicates the ratio of the current bond principal to the original principal", "IBApi.EWrapper.tickGeneric", "460"],
            61: ["regulatory_imbalance", "Regulatory Imbalance", "The imbalance that is used to determine which at-the-open or at-the-close orders can be entered following the publishing of the regulatory imbalance", "IBApi.EWrapper.tickSize", "225"],
            62: ["news_tick", "News Tick", "Contract's news feed", "IBApi.EWrapper.tickString", "292"],
            63: ["short_term_volume_3min", "Short Term Volume 3 min", "The past three minutes volume. Interpolation may be applied. For stocks only.", "IBApi.EWrapper.tickSize", "595"],
            64: ["short_term_volume_5min", "Short Term Volume 5 min", "The past five minutes volume. Interpolation may be applied. For stocks only.", "IBApi.EWrapper.tickSize", "595"],
            65: ["short_term_volume_10min", "Short Term Volume 10 min", "The past ten minutes volume. Interpolation may be applied. For stocks only.", "IBApi.EWrapper.tickSize", "595"],
            66: ["delayed_bid", "Delayed Bid", "Delayed bid price", "IBApi.EWrapper.tickPrice", "-"],
            67: ["delayed_ask", "Delayed Ask", "Delayed ask price", "IBApi.EWrapper.tickPrice", "-"],
            68: ["delayed_last", "Delayed Last", "Delayed last price", "IBApi.EWrapper.tickPrice", "-"],
            69: ["delayed_bid_size", "Delayed Bid Size", "Delayed bid size", "IBApi.EWrapper.tickSize", "-"],
            70: ["delayed_ask_size", "Delayed Ask Size", "Delayed ask size", "IBApi.EWrapper.tickSize", "-"],
            71: ["delayed_last_size", "Delayed Last Size", "Delayed last size", "IBApi.EWrapper.tickSize", "-"],
            72: ["delayed_high", "Delayed High", "Delayed high price of the day", "IBApi.EWrapper.tickPrice", "-"],
            73: ["delayed_low", "Delayed Low", "Delayed low price of the day", "IBApi.EWrapper.tickPrice", "-"],
            74: ["delayed_volume", "Delayed Volume", "Delayed traded volume of the day", "IBApi.EWrapper.tickSize", "-"],
            75: ["delayed_close", "Delayed Close", "Delayed close price", "IBApi.EWrapper.tickPrice", "-"],
            76: ["delayed_open", "Delayed Open", "Delayed open price", "IBApi.EWrapper.tickPrice", "-"],
            77: ["rt_trd_volume", "RT Trd Volume", "Real-time traded volume for the day for the selected contract (US Stocks: multiplier 100).", "IBApi.EWrapper.tickSize", "-"],
            78: ["creditman_mark_price", "Creditman Mark Price", "Creditman mark price", "IBApi.EWrapper.tickPrice", "-"],
            79: ["creditman_slow_mark_price", "Creditman Slow Mark Price", "Creditman slow mark price", "IBApi.EWrapper.tickPrice", "-"],
            80: ["delayed_bid_opt_comp", "Delayed Bid Option Computation", "Delayed bid option computation", "IBApi.EWrapper.tickOptionComputation", "-"],
            81: ["delayed_ask_opt_comp", "Delayed Ask Option Computation", "Delayed ask option computation", "IBApi.EWrapper.tickOptionComputation", "-"],
            82: ["delayed_last_opt_comp", "Delayed Last Option Computation", "Delayed last option computation", "IBApi.EWrapper.tickOptionComputation", "-"],
            83: ["delayed_model_opt_comp", "Delayed Model Option Computation", "Delayed model option computation", "IBApi.EWrapper.tickOptionComputation", "-"],
            84: ["last_exchange", "Last Exchange", "Exchange where last trade was executed", "IBApi.EWrapper.tickString", "-"],
            85: ["last_reg_time", "Last Regulatory Time", "Timestamp (in Unix ms time) of last trade returned with regulatory snapshot", "IBApi.EWrapper.tickString", "-"],
            86: ["futures_open_interest", "Futures Open Interest", "Total number of outstanding futures contracts (TWS v965+). *HSI open interest requested with generic tick 101", "IBApi.EWrapper.tickSize", "588"],
            87: ["avg_option_volume", "Average Option Volume", "Average volume of the corresponding option contracts(TWS Build 970+ is required)", "IBApi.EWrapper.tickSize", "105"],
            88: ["delayed_last_timestamp", "Delayed Last Timestamp", "Delayed time of the last trade (in UNIX time) (TWS Build 970+ is required)", "IBApi.EWrapper.tickString", "-"],
            89: ["shortable_shares", "Shortable Shares", "Number of shares available to short (TWS Build 974+ is required)", "IBApi.EWrapper.tickSize", "236"],
            92: ["etf_nav_close", "ETF Nav Close", "Today's closing price of ETF's Net Asset Value (NAV). Calculation is based on prices of ETF's underlying securities.", "IBApi.EWrapper.tickPrice", "578"],
            93: ["etf_nav_prior_close", "ETF Nav Prior Close", "Yesterday's closing price of ETF's Net Asset Value (NAV). Calculation is based on prices of ETF's underlying securities.", "IBApi.EWrapper.tickPrice", "578"],
            94: ["etf_nav_bid", "ETF Nav Bid", "The bid price of ETF's Net Asset Value (NAV). Calculation is based on prices of ETF's underlying securities.", "IBApi.EWrapper.tickPrice", "576"],
            95: ["etf_nav_ask", "ETF Nav Ask", "The ask price of ETF's Net Asset Value (NAV). Calculation is based on prices of ETF's underlying securities.", "IBApi.EWrapper.tickPrice", "576"],
            96: ["etf_nav_last", "ETF Nav Last", "The last price of Net Asset Value (NAV). For ETFs: Calculation is based on prices of ETF's underlying securities. For NextShares: Value is provided by NASDAQ", "IBApi.EWrapper.tickPrice", "577"],
            97: ["etf_nav_frozen_last", "ETF Nav Frozen Last", "ETF Nav Last for Frozen data", "IBApi.EWrapper.tickPrice", "623"],
            98: ["etf_nav_high", "ETF Nav High", "The high price of ETF's Net Asset Value (NAV)", "IBApi.EWrapper.tickPrice", "614"],
            99: ["etf_nav_low", "ETF Nav Low", "The low price of ETF's Net Asset Value (NAV)", "IBApi.EWrapper.tickPrice", "614"],
            101: ["est_ipo_midpoint", "Estimated IPO - Midpoint", "Midpoint is calculated based on IPO price range", "IBApi.EWrapper.tickGeneric", "586"],
            102: ["final_ipo_price", "Final IPO Price", "Final price for IPO", "IBApi.EWrapper.tickGeneric", "586"],
        }

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

