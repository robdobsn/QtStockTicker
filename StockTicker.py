# -*- coding: utf-8 -*-

import sys
import threading

from PyQt5 import QtGui, QtWidgets, QtCore
from PyQt5.QtCore import QTimer

from StockHoldings import StockHoldings
from StockValues_InteractiveBrokers import StockValues_InteractiveBrokers
from StockSettingsDialog import StockSettingsDialog
from StockSymbolList import StockSymbolList
from HostedConfigFile import HostedConfigFile
from ExDivDates import ExDivDates
from StockTable import StockTable
from decimal import Decimal
from ExchangeRates import ExchangeRates
from LocalConfig import LocalConfig

import requests
SEND_TO_MESSAGE_BOARD = False

'''
Created on 4 Sep 2013

@author: rob dobson
'''

class RStockTicker(QtWidgets.QMainWindow):

    stockHoldings = None
    updateTimer = None
    currencySign = "\xA3"
    stocksViewLock = threading.Lock()
    stocksListChanged = False
    windowTitle = ""
    MARKET_OPEN_CHECK_TICKS = 60
    ticksBeforeMarketOpenCheck = MARKET_OPEN_CHECK_TICKS

    def __init__(self):
        super(RStockTicker, self).__init__()
        # Local config
        self.localConfigFile = LocalConfig("localConfig.json")
        # Hosted config
        self.hostedConfigFile = HostedConfigFile()
        self.hostedConfigFile.initFromFile('privatesettings/stockTickerConfig.json')
        self.stockHoldings = StockHoldings()
        #self.stockreader.readFromShareScopeCSV("robstkexpt.csv")
        configData = self.hostedConfigFile.getConfigDataFromLocation()
        self.stockHoldings.setupFromConfigData(configData)
        heldStockSymbols = self.stockHoldings.getStockSymbols()
        # Exchange rate getter
        self.exchangeRates = ExchangeRates()
        self.exchangeRates.start()
        # Stock values getter
        self.stockValues = StockValues_InteractiveBrokers()
        self.stockValues.setStocks(heldStockSymbols)
        self.stockValues.run()
        # Ex-dividend dates getter
        self.exDivDates = ExDivDates(self.exchangeRates)
        self.exDivDates.run()
        # Update for the display
        self.updateTimer = QTimer(self)
        self.updateTimer.timeout.connect(self.updateStockValues)
        self.updateTimer.start(2000)
        self.stockSymbolList = StockSymbolList()
#        self.stockSymbolList.getStocksFromCSV()
        self.stockSymbolList.getStocksFromWeb()
        self.portfolioTableColDefs = [
            { 'colLbl':"Sym", 'colValName':"sym", 'dataType':'str', 'fmtStr':'', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'left', 'fontSize':'large', 'colourCode':'PosNeg', 'colourByCol':'change' },
            { 'colLbl':"Name", 'colValName':"name", 'dataType':'str', 'fmtStr':'', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'left', 'fontSize':'small', 'colourCode':'PosBad', 'colourByCol':'failCount' },
            { 'colLbl':"Holding", 'colValName':"hld", 'dataType':'decimal', 'fmtStr':'{:0,.0f}', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            { 'colLbl':"Last", 'colValName':"price", 'dataType':'decimal', 'fmtStr':'{:0.2f}', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right', 'colourCode':'FlashPosNeg', 'colourBy':'change' },
            { 'colLbl':"Change", 'colValName':"change", 'dataType':'decimal', 'fmtStr':'{:0.2f}', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            { 'colLbl':"Change%", 'colValName':"chg_percent", 'dataType':'decimal', 'fmtStr':'{:0.2f}', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            { 'colLbl':"Value", 'colValName':"totalvalue", 'dataType':'decimal', 'fmtStr':'{:0,.2f}', 'prfxStr':'£', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            { 'colLbl':"Profit", 'colValName':"profit", 'dataType':'decimal', 'fmtStr':'{:0,.2f}', 'prfxStr':'£', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right', 'colourCode':'PosNeg' },
            { 'colLbl':"Volume", 'colValName':"volume", 'dataType':'decimal', 'fmtStr':'{:0,.0f}', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            { 'colLbl':"ExDiv", 'colValName':"exDivDate", 'dataType':'str', 'fmtStr':'', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right', 'colourBy':'exDivFromHoldings' },
            { 'colLbl':"Amount", 'colValName':"exDivAmount", 'dataType':'decimal', 'fmtStr':'{:0.4f}', 'prfxStr':self.currencySign, 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right', 'onlyIfValid':'exDivDate' },
            { 'colLbl':"PayDate", 'colValName':"paymentDate", 'dataType':'str', 'fmtStr':'', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            ]
        self.watchTableColDefs = [
            { 'colLbl':"Sym", 'colValName':"sym", 'dataType':'str', 'fmtStr':'', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'left', 'fontSize':'large', 'colourCode':'PosNeg', 'colourByCol':'change' },
            { 'colLbl':"Name", 'colValName':"name", 'dataType':'str', 'fmtStr':'', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'left', 'fontSize':'small' },
            { 'colLbl':"Last", 'colValName':"price", 'dataType':'decimal', 'fmtStr':'{:0.2f}', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right', 'colourCode':'FlashPosNeg', 'colourBy':'change' },
            { 'colLbl':"Change", 'colValName':"change", 'dataType':'decimal', 'fmtStr':'{:0.2f}', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            { 'colLbl':"Change%", 'colValName':"chg_percent", 'dataType':'decimal', 'fmtStr':'{:0.2f}', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            { 'colLbl':"Volume", 'colValName':"volume", 'dataType':'decimal', 'fmtStr':'{:0,.0f}', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            { 'colLbl':"ExDiv", 'colValName':"exDivDate", 'dataType':'str', 'fmtStr':'', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right', 'colourBy':'exDivFromHoldings' },
            { 'colLbl':"Amount", 'colValName':"exDivAmount", 'dataType':'decimal', 'fmtStr':'{:0.4f}', 'prfxStr':self.currencySign, 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right', 'onlyIfValid':'exDivDate' },
            { 'colLbl':"PayDate", 'colValName':"paymentDate", 'dataType':'str', 'fmtStr':'', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            ]
        self.initUI()

    def getFontAction(self, title, connectParam1, connectParam2):
        fontAction = QtWidgets.QAction(QtGui.QIcon('font.png'), '&' + title, self)
        fontAction.setStatusTip(title)
        fontAction.triggered.connect(lambda: self.changeFont(connectParam1, connectParam2))
        return fontAction

    def initUI(self):

        # Grid layout for the tables
        self.gridLayout = QtWidgets.QGridLayout()

        # Edit action
        editAction = QtWidgets.QAction(QtGui.QIcon('edit.png'), '&Edit', self)
        editAction.setStatusTip('Edit shares')
        editAction.triggered.connect(self.editStocksList)

        # Exit action
        exitAction = QtWidgets.QAction(QtGui.QIcon('exit.png'), '&Exit', self)
        exitAction.setStatusTip('Exit application')
        exitAction.triggered.connect(self.quitApp)

        # Table(s) to handle watch list
        numWatchTables = 3
        self.watchTables = []
        for tabIdx in range(numWatchTables):
            newTab = StockTable()
            newTab.initTable(self, self.watchTableColDefs, self.currencySign, False, "watch", self.localConfigFile)
            # Add actions
            newTab.addAction(editAction)
            newTab.addAction(self.getFontAction("Normal Font", "watch", "normal"))
            newTab.addAction(self.getFontAction("Large Font", "watch", "large"))
            newTab.addAction(exitAction)
            newTab.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
            # Add to list of tables
            self.watchTables.append(newTab)

#        self.watchTable.initTable(self.watchTableColDefs, self.currencySign, False, QtGui.QFont('SansSerif', 9), QtGui.QFont('SansSerif', 8), QtGui.QFont('SansSerif', 11, QtGui.QFont.Bold))
#        self.watchTable.populateTable(watchStocks)

        # Table(s) for portfolio stocks
        numPortfolioTables = 2
        self.portfolioTables = []
        for tabIdx in range(numPortfolioTables):
            newTab = StockTable()
            self.portfolioTables.append(newTab)

        # Populate tables
        self.populateTablesWithStocks()
        self.exDivDates.setFromStockHoldings(self.stockHoldings.getStockHolding(False))

        # Span for watch tables and portfolio tables
        watchTabColSpan = numPortfolioTables
        portfolioTabColSpan = numWatchTables

        # Add tables to grid
        for tabIdx in range(len(self.watchTables)):
            self.gridLayout.addWidget(self.watchTables[tabIdx], 0, tabIdx*watchTabColSpan, 1, watchTabColSpan)
        for tabIdx in range(len(self.portfolioTables)):
            self.gridLayout.addWidget(self.portfolioTables[tabIdx], 1, tabIdx*portfolioTabColSpan, 1, portfolioTabColSpan)

        # GridWidget that holds everything        
        gridWidget = QtWidgets.QWidget()
        gridWidget.setLayout(self.gridLayout)

        self.setCentralWidget(gridWidget)
#        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)

        self.windowTitle = 'Stock Ticker'
        self.setWindowTitle(self.windowTitle)
        self.resize(1280,800)
        self.show()
        
    def populateTablesWithStocks(self):
        fullStockList = self.stockHoldings.getStockHolding(False)
        # Watch tables
        watchStocks = [item for item in fullStockList if item['holding'] == 0]
        numWatchStocksPerTable = int((len(watchStocks)+len(self.watchTables)-1)/len(self.watchTables))
        for tabIdx in range(len(self.watchTables)):
            self.watchTables[tabIdx].populateTable(watchStocks[tabIdx*numWatchStocksPerTable:((tabIdx+1)*numWatchStocksPerTable)])
        # Portfolio table
        portfolioStocks = [item for item in fullStockList if item['holding'] != 0]
        numPortfolioStocksPerTable = int((len(portfolioStocks)+len(self.portfolioTables)-1)/len(self.portfolioTables))
        for tabIdx in range(len(self.portfolioTables)):
            self.portfolioTables[tabIdx].populateTable(portfolioStocks[tabIdx*numPortfolioStocksPerTable:((tabIdx+1)*numPortfolioStocksPerTable)])

    def quitApp(self):
        QtWidgets.qApp.closeAllWindows()
        
    def editStocksList(self):
        editWindow = StockSettingsDialog()
        editWindow.setContext(self.stockHoldings, self.portfolioTableColDefs, self.stockSymbolList)
        editWindow.initUI()
        rslt = editWindow.exec()
        if rslt != QtWidgets.QDialog.Accepted:
            return
        # Store the new stock values
        self.stockHoldings.setHoldings(editWindow.updatedStockHoldings)
        heldStockSymbols = self.stockHoldings.getStockSymbols()
        self.stockValues.setStocks(heldStockSymbols)
        self.stocksViewLock.acquire()
        self.stocksListChanged = True
        self.stocksViewLock.release()
        configData = self.stockHoldings.getConfigData()
        self.hostedConfigFile.configFileUpdate(configData)
    def closeEvent(self, event):
        print('StockTicker: Stopping')
        self.stockValues.stop()
        self.exDivDates.stop()
        self.updateTimer.stop()
        self.exchangeRates.stop()
        event.accept()
        
    def updateStockValues(self):
        # Check if stocks information has changed
        forceTableUpdate = False
        self.stocksViewLock.acquire()
        if self.stocksListChanged:
            print ("StockTicker: Stock list changed")
            self.populateTablesWithStocks()
            self.exDivDates.setFromStockHoldings(self.stockHoldings.getStockHolding(False))
            self.stocksListChanged = False
            forceTableUpdate = True
        self.stocksViewLock.release()

        # Update the window title every now and again with market open status
        if (self.ticksBeforeMarketOpenCheck == 0):
            stat = self.stockValues.getMarketOpenStatus()
            if stat != "":
                newWindowTitle = 'Stock Ticker - ' + stat
                if self.windowTitle != newWindowTitle:
                    self.windowTitle = newWindowTitle
                    self.setWindowTitle(self.windowTitle)
            self.ticksBeforeMarketOpenCheck = self.MARKET_OPEN_CHECK_TICKS
        else:
            self.ticksBeforeMarketOpenCheck -= 1

        # Update data flash
        for table in self.watchTables:
            table.updateFlash()
        for table in self.portfolioTables:
            table.updateFlash()

        # Get list of stocks updated since last UI update
        changedStockDict = None
        if not forceTableUpdate:
            changedStockDict = self.stockValues.getMapOfStocksChangedSinceUIUpdated()
            if (changedStockDict) == 0:
                # print("No Update Required")
                return
            # else:
            #     print("Doing update")

        # Update the tables
        for table in self.watchTables:
            table.updateTable(self.stockValues, self.exDivDates, changedStockDict, [Decimal("0"),Decimal("0"),0,0])
        tableTotals = [Decimal("0"),Decimal("0"),0,0]
        for table in self.portfolioTables:
            tableTotals = table.updateTable(self.stockValues, self.exDivDates, changedStockDict, tableTotals)
            table.SetTotals(tableTotals)

        if SEND_TO_MESSAGE_BOARD:
            try:
                stkValues = self.stockValues.getStockData("^FTSE")
                url = 'http://192.168.0.229/text?<1>' + stkValues['name'] + ": " + stkValues['price'] + "  " + stkValues['change'] + " (" + stkValues['chg_percent'] + ")"
                r = requests.get(url)
            except:
                print ("StockTicker: Failed to send stock data to LED Panel")

        # Handle window size updates
        # watchWidth = 0
        # watchHeight = 0
        # portfolioWidth = 0
        # portfolioHeight = 0
        # for table in self.watchTables:
        #     optSizeWatch = table.getOptimumTableSize()
        #     watchWidth += optSizeWatch[0] + 20
        #     watchHeight = max(watchHeight, optSizeWatch[1])
        # watchHeight += 10
        # for table in self.portfolioTables:
        #     optSizePortfolio = table.getOptimumTableSize()
        #     portfolioWidth += optSizePortfolio[0] + 20
        #     portfolioHeight = max(portfolioHeight, optSizePortfolio[1])
        # portfolioWidth += 20
        # portfolioHeight += 10
        # self.gridLayout.setRowStretch(0, watchHeight)
        # self.gridLayout.setRowStretch(1, portfolioHeight)
#        self.setMinimumWidth(max(watchWidth, portfolioWidth))
#        self.setMinimumHeight(watchHeight+portfolioHeight)
        
def main():
    app = QtWidgets.QApplication(sys.argv)
    stockTicker = RStockTicker()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
