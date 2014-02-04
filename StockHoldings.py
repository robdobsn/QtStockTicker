import json

'''
Created on 01 Oct 2013

@author: rob dobson
'''

class StockHoldings:

    stockreader = None
    stockHolding = {}

    # def readFromJsonFile(self, fName):
    #     with open(fName, 'r') as jsonFile:
    #         jsonData = json.load(jsonFile)
    #         self.setupFromJsonData(jsonData)
            
    def setupFromConfigData(self, configData):
        if configData != None:
            if 'StockInfo' in configData:
                self.stockHolding = configData['StockInfo']
                for stock in self.stockHolding:
                    if not "exDivDate" in stock:
                        stock["exDivDate"] = ""
                    if not "exDivAmount" in stock:
                        stock["exDivAmount"] = 0
                    if not "paymentDate" in stock:
                        stock["paymentDate"] = ""

    def getStockSymbols(self):
        return [dct['symbol'] for dct in self.stockHolding]
    
    def numStocks(self):
        return len(self.stockHolding)
    
    def getStockHolding(self, bSorted):
        if not bSorted:
            return self.stockHolding
        return sorted(self.stockHolding, key=lambda k: k['symbol'])
    
    def setHoldings(self, newHoldings):
        self.stockHolding = newHoldings
        
    def getConfigData(self):
        stockData = { "StockInfo": self.stockHolding}
        return stockData
    