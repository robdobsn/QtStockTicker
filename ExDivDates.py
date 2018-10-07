from selenium import webdriver
import time
import arrow
from datetime import datetime
from bs4 import BeautifulSoup
import threading
from selenium.webdriver.chrome.options import Options  
from selenium.webdriver.common.keys import Keys
import os
import sys

'''
Created on 13 Sep 2013
Updated 12 Nov 2017

@author: rob dobson
'''

class ExDivDates():
    hourToRunAt = 4
    bRunAlready = False
    bFirstRunDone = False

    conversionRatesSymbols = {
        "C$": {"iso":"CAD","def":1.6},
        "$":  {"iso":"USD","def":1.3},
        "€":  {"iso":"EUR","def":1.1},
        "R":  {"iso":"ZAR","def":18.9},
        "p":  {"iso":"","def":100},
        "£":  {"iso":"GBP","def":1.0}
    }

    def __init__(self, exchangeRates):
        self._exchangeRates = exchangeRates
        self.running = False
        self.stocksExDivInfo = {}
        self.lock = threading.Lock()
        self.runHeadless = True
        
    def run(self):
        self.running = True
        self.t = threading.Thread(target=self.do_thread_scrape)
        self.t.start()

    def stop(self):
        self.running = False
        
    def setTimeToRunAt(self, hourToRunAt):
        self.hourToRunAt = hourToRunAt

    def addToStockInfo(self, symbol, stkInfoDict):
        itemsToAdd = ['exDivDate','exDivAmount','paymentDate']
        self.lock.acquire()
        if symbol in self.stocksExDivInfo:
            for iti in itemsToAdd:
                if iti in self.stocksExDivInfo[symbol]:
                    stkInfoDict[iti] = self.stocksExDivInfo[symbol][iti]
        self.lock.release()

    def setFromStockHoldings(self, stockHoldings):
        itemsToAdd = ['exDivDate','exDivAmount','paymentDate']
        exDivOnly = {}
        for stock in stockHoldings:
            sym = stock['symbol']
            if stock['exDivDate'] == "" or stock['exDivAmount'] == 0 or stock['paymentDate'] == "":
                continue
            if sym in exDivOnly:
                if 'exDivDate' in exDivOnly[sym]:
                    if exDivOnly[sym]['exDivDate'] != "":
                        continue
            exDivOnly[sym] = { 'symbol':sym, 'exDivDate':stock['exDivDate'], 'exDivAmount':stock['exDivAmount'], 'paymentDate':stock['paymentDate'] }
        for stock in exDivOnly.values():
            if "symbol" in stock:
                newDict = { 'exDivDataFromHoldings': True }
                for item in itemsToAdd:
                    if item in stock:
                        newDict[item] = stock[item]
                self.stocksExDivInfo[stock["symbol"]] = newDict

    def convertFromPence(self, val):
        newVal = None
        try:
            for sym, exRateInfo in self.conversionRatesSymbols.items():
                if sym in val:
                    val = val.replace(sym, "")
                    newVal = float(val)
                    exchgRate = self._exchangeRates.getExVsGBPByIso(exRateInfo["iso"])
                    if exchgRate is not None:
                        newVal /= exchgRate
                    else:
                        newVal /= exRateInfo["def"]
                    break
            if newVal is None:
                newVal = float(val)
        except:
            newVal = None
        return newVal

    def convertFromShortDate(self, val):
        newVal = ""
        try:
            newVal = arrow.get(val, "DD-MMM")
            newVal = newVal.replace(year=arrow.now().year)
            if newVal < arrow.now():
                newVal = newVal.shift(years=+1)
            newVal = newVal.format("YYYY-MM-DD")
        except:
            newVal = ""
        return newVal

    def extractDataFromPage(self, pageText):

        # parse and extract ex dividend table
        soup = BeautifulSoup(pageText, "html5lib")
        exDivTable = soup.select("body section table tbody tr")
        # print(exDivTable)

        # Extract rows and columns from table
        exDivInfo = {}
        attrNames = ["exDivEPIC", "exDivName", "exDivMarket", "exDivSharePrice", "exDivAmount", "exDivImpact",
                     "exDivDeclared", "exDivDate", "paymentDate"]
        exDivTableLine = 0
        for exDivRow in exDivTable:
            exDivValid = True
            exDivItems = {"exDivTableLine": exDivTableLine}
            exDivTableLine += 1
            exDivCells = exDivRow.select("td")
            for elIdx in range(len(exDivCells)):
                if elIdx >= len(attrNames):
                    break
                attrName = attrNames[elIdx]
                val = exDivCells[elIdx].getText().strip()
                # Convert currency fields
                if attrName == "exDivSharePrice" or attrName == "exDivAmount":
                    val = self.convertFromPence(val)
                if val is None and attrName == "exDivAmount":
                    exDivValid = False
                    break
                # Convert time fields
                if attrName == "paymentDate" or attrName == "exDivDate" or attrName == "exDivDeclared":
                    val = self.convertFromShortDate(val)
                if val == "" and (attrName == "exDivDate" or attrName == "paymentDate"):
                    exDivValid = False
                    break
                exDivItems[attrName] = val
            if exDivValid and "exDivEPIC" in exDivItems:
                if not exDivItems["exDivEPIC"] in exDivInfo:
                    exDivInfo[exDivItems["exDivEPIC"]] = exDivItems
                else:
                    print("Got 2 or more dividend lines, returning only earliest for", exDivItems["exDivEPIC"])
            else:
                print("Skipping", exDivItems)

        # for sym, vals in exDivInfo.items():
        #     print(vals)

        print("ExDivDates: Processed", len(exDivTable), "rows, got", len(exDivInfo), "symbols")
        return exDivInfo

    def do_thread_scrape(self):
        while(self.running):
            
            # Check if it is time to run
            bRunNow = False
            hourNow = datetime.now().hour
            if self.bFirstRunDone:
                testHour = hourNow
                if testHour < self.hourToRunAt:
                    testHour = hourNow + 24
                if testHour >= self.hourToRunAt and testHour < self.hourToRunAt + 1:
                    if not self.bRunAlready:
                        bRunNow = True
                else:
                    self.bRunAlready = False
            else:
                bRunNow = True
                    
            if bRunNow:
                pageURL = "http://www.dividenddata.co.uk"
                print("ExDivDates:", datetime.now().strftime("%Y-%m-%d %H:%M"), ", URL", pageURL)
                self.bFirstRunDone = True
                self.bRunAlready = True
                
                if self.runHeadless:
                    print(os.path.abspath("chromedriver"))
                    print(sys.path)
                    chrome_options = Options()  
                    chrome_options.add_argument("--headless")
                    chrome_options.add_argument("--no-sandbox")
                    chrome_options.add_argument("--disable-extensions")
                    browser = webdriver.Chrome(chrome_options=chrome_options)
                else:
                    browser = webdriver.Firefox() # Get local session of firefox
    
                browser.get(pageURL) # Load page

                exDivInfoDict = self.extractDataFromPage(browser.page_source)

                # Close the browser now we're done
                browser.close()

                # Put found stocks into the dictionary of current data
                for sym, vals in exDivInfoDict.items():
                    ySymbol = sym
                    if "exDivMarket" in vals:
                        market = vals["exDivMarket"]
                        if market.startswith("FTSE"):
                            ySymbol = sym + "L" if sym.endswith(".") else sym + ".L"
                    self.lock.acquire()
                    self.stocksExDivInfo[ySymbol] = vals
                    self.lock.release()

            for i in range(60):
                if not self.running:
                    break
                time.sleep(1)

if __name__ == '__main__':
    ## Test code
    ss = ExDivDates()
    ss.run()
