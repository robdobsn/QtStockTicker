import json
import logging

from StockHolding import StockHolding, StocksDataFileContents

'''
Created on 01 Oct 2013

@author: rob dobson
'''

logger = logging.getLogger("StockTickerLogger")

class StockHoldings:

    def __init__(self):
        self.stockHoldingsList: list[StockHolding] = []

    # def readFromJsonFile(self, fName):
    #     with open(fName, 'r') as jsonFile:
    #         jsonData = json.load(jsonFile)
    #         self.setupFromJsonData(jsonData)
            
    def loadFromStocksDataFileContents(self, configData: StocksDataFileContents | None) -> None:
        if configData != None:
            if 'StockInfo' in configData:
                self.stockHoldingsList = configData['StockInfo']
                for stock in self.stockHoldingsList:
                    if not "exDivDate" in stock:
                        stock["exDivDate"] = ""
                    if not "exDivAmount" in stock:
                        stock["exDivAmount"] = 0
                    if not "paymentDate" in stock:
                        stock["paymentDate"] = ""

    def getStockSymbols(self) -> list[str]:
        return [dct['symbol'] for dct in self.stockHoldingsList]
    
    def numStocks(self) -> int:
        return len(self.stockHoldingsList)
    
    def getStockHoldings(self, bSorted: bool) -> list[StockHolding]:
        if not bSorted:
            return self.stockHoldingsList
        return sorted(self.stockHoldingsList, key=lambda k: k['symbol'])
    
    def setHoldings(self, newHoldings):
        self.stockHoldingsList = newHoldings
        
    def getConfigData(self):
        stockData = { "StockInfo": self.stockHoldingsList}
        return stockData
    