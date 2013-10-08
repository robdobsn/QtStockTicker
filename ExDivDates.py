from selenium import webdriver
import time
from bs4 import BeautifulSoup
import threading
import json
from datetime import datetime

'''
Created on 13 Sep 2013

@author: rob dobson
'''

class ExDivDates():
    hourToRunAt = 4;
    bRunAlready = False;
    bFirstRunDone = False;

    def __init__(self):
        self.running = False
        self.stocksExDivInfo = {}
        self.lock = threading.Lock()
        self.runHeadless = False 
        
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

    def do_thread_scrape(self):
        while(self.running):
            
            # Check if it is time to run
            bRunNow = False;
            hourNow = datetime.now().hour;
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
                print("Running ExDivData at", hourNow)
                self.bFirstRunDone = True
                self.bRunAlready = True
                
                exDivInfoList = []
                
                urlbase = "http://www.exdividenddate.co.uk"
                pageURL = urlbase
                if self.runHeadless:
                    dc = webdriver.DesiredCapabilities.HTMLUNIT
                    browser = webdriver.Remote(desired_capabilities=dc)
                else:
                    browser = webdriver.Firefox() # Get local session of firefox
    
                browser.get(pageURL) # Load page
                
                maxPagerNumber = 0
                curPagerNumber = 1
                while (True):
                    
                    colNames = ['symbol','name','index','exDivDate','exDivAmount','paymentDate']
                    
                    # Get page and parse
                    html = browser.page_source
                    soup = BeautifulSoup(html, "lxml")
                    rows = soup.findAll('tr', {'class' : 'exdividenditem' }) + soup.findAll('tr', {'class':'exdividendalternatingitem'})
                    
                    # Extract stocks table info
                    for row in rows:
                        colIdx = 0
                        stockExDivInfo = {}
                        for cell in row.findAll(text=True):
                            cell = cell.strip()
                            if cell == "":
                                continue
                            if colIdx < len(colNames):
                                if colNames[colIdx] == "symbol":
                                    cell = cell + ".L" if (cell[-1] != ".") else cell + "L"
                                stockExDivInfo[colNames[colIdx]] = cell
                            colIdx += 1
#                    print(stockExDivInfo)
                        exDivInfoList.append(stockExDivInfo)
                        
                    # Find maximum pager number
                    pagerRow = soup.find('tr', {'id' : 'ctl00_ContentPlaceHolder1_lvExDividendDate_Tr1' })
                    for txt in pagerRow.findAll(text=True):
                        txt = txt.strip()
                        if txt == "":
                            continue
                        if maxPagerNumber < int(txt):
                            maxPagerNumber = int(txt)
                    
                    # Find the pager and go to next page if applicable
                    curPagerNumber += 1
                    if curPagerNumber > maxPagerNumber:
                        break
                    browser.find_element_by_xpath("//a[contains(.,'" + str(curPagerNumber) + "')]").click();
                    time.sleep(3)
    
                # Close the browser now we're done    
                browser.close()
                
                # Put found stocks into the dictionary of current data
                for stk in exDivInfoList:
                    self.lock.acquire()
                    self.stocksExDivInfo[stk['symbol']] = stk
                    self.lock.release()
                
                # Append to exdivinfo file
                with open("exdivinfo.json", "at") as exDivFile:
                    jsonStr = json.dumps(exDivInfoList, indent=4) + ","
                    exDivFile.write(jsonStr)
    
                print("Found", len(exDivInfoList), "ExDivInfoLines")
#                sortit = sorted(exDivInfoList, key=lambda k: k['name'])
#                for stk in sortit:
#                    print(stk)
                               
            time.sleep(60)

if __name__ == '__main__':
    ## Test code
    ss = ExDivDates()
    ss.run()
