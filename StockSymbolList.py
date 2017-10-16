import csv
import requests
from bs4 import BeautifulSoup
import re

'''
Created on 28 Sep 2013

@author: rob dobson
'''

class StockSymbolList():
        
    def getStocksFromCSV(self):
        self.stockList = []
        with open('ukstocks.csv', 'r') as csvfile:
            stkReader = csv.reader(csvfile)
            for row in stkReader:
                self.stockList.append(row[0:2])
        self.stockList = sorted(self.stockList)

    def getStocksFromWeb(self):
        self.stockList = []
        r = None
        for getStocksAttempt in range(3):
            try:
                r = requests.get('http://www.lse.co.uk/index-constituents.asp?index=idx:asx')
                break
            except Exception as excp:
                print("Faield to get FTSE list from LSE, attempt", getStocksAttempt)
        if r is None:
            return
        soup = BeautifulSoup(r.text, "html.parser")
        for x in soup.find_all('a', attrs={'class':"linkTabs"}):
            #print (x.text)
            mtch = re.match("(.+?)\((.+?)\)", x.text)
            if (mtch != None and mtch.lastindex == 2):
                #print (mtch.group(1), mtch.group(2))
                # Append .L to make it work with Yahoo
                coName = mtch.group(1)
                symb = mtch.group(2) + ".L" if (mtch.group(2)[-1]!='.') else mtch.group(2) + "L" 
                self.stockList.append([coName,symb])
            else:
                print("Failed Match", x.text)
        
    def getNumStocks(self):
        return len(self.stockList)
    
    def getStockList(self):
        return self.stockList