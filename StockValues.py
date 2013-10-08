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
        while ( self.running ):
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
            if updateNeeded:
                firstpass = False
                for stock in self.tickerlist:
                    ticker = stock
#                    print ("querying for ", ticker)
                    try:
                        stkdata = self.get_quote( ticker )
                    except:
                        print ("get_quote failed for " + ticker)
                        self.status = "failed for " + ticker
                        stkdata={}
                    stkdata['time'] = now
                    self.lock.acquire()
                    self.stockData[ticker] = stkdata
                    self.lock.release()
#                    print (ticker + " = " + stkdata["price"])
            else:
                self.status = "Market Closed"
#                    print "Markets closed"
            time.sleep(1)
            # Check if the stock list has been updated
            self.listUpdateLock.acquire()
            if self.pendingTickerlist != None:
                self.tickerlist = self.pendingTickerlist
                self.pendingTickerlist = None
            self.listUpdateLock.release()

            
    def get_quote(self, symbol):
        """
        Get all available quote data for the given ticker symbol.
    
        Returns a dictionary.
        """
        values = self._request(symbol, 'l1c1va2xj1b4j4dyekjm3m4rr5p5p6s7abghp2opqr1n').split(',')
        return dict(
            price=values[0],
            change=values[1],
            volume=values[2],
            avg_daily_volume=values[3],
            stock_exchange=values[4],
            market_cap=values[5],
            book_value=values[6],
            ebitda=values[7],
            dividend_per_share=values[8],
            dividend_yield=values[9],
            earnings_per_share=values[10],
            fifty_two_week_high=values[11],
            fifty_two_week_low=values[12],
            fifty_day_moving_avg=values[13],
            two_hundred_day_moving_avg=values[14],
            price_earnings_ratio=values[15],
            price_earnings_growth_ratio=values[16],
            price_sales_ratio=values[17],
            price_book_ratio=values[18],
            short_ratio=values[19],
            ask=values[20],
            bid=values[21],
            day_low=values[22],
            day_high=values[23],
            chg_percent=self.stripQuotes(values[24]),
            open_val=values[25],
            prev_close=values[26],
            ex_div_date=self.stripQuotes(values[27]),
            div_pay_date=values[28],
            name=self.stripQuotes(values[29]),
        )

    def stripQuotes(self, inStr):
        if inStr.startswith('"') and inStr.endswith('"'):
            inStr = inStr[1:-1]
        return inStr
    
    # Borrowed from ystockquote
    def _request(self, symbol, stat):
        url = 'http://finance.yahoo.com/d/quotes.csv?s=%s&f=%s' % (symbol, stat)
        req = Request(url)
        resp = urlopen(req)
        return str(resp.read().decode('utf-8').strip())
