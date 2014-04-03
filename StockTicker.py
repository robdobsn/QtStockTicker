# -*- coding: utf-8 -*-

import sys
import threading

from PyQt5 import QtGui, QtWidgets, QtCore
from PyQt5.QtCore import QTimer

from StockHoldings import StockHoldings
from StockValues import StockValues
from StockSettingsDialog import StockSettingsDialog
from StockSymbolList import StockSymbolList
from HostedConfigFile import HostedConfigFile
from ExDivDates import ExDivDates
from StockTable import StockTable
from decimal import Decimal

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
    
    def __init__(self):
        super(RStockTicker, self).__init__()
        self.hostedConfigFile = HostedConfigFile()
        self.hostedConfigFile.initFromFile('privatesettings/stockTickerConfig.json')
        self.stockHoldings = StockHoldings()
        #self.stockreader.readFromShareScopeCSV("robstkexpt.csv")
        configData = self.hostedConfigFile.getConfigDataFromLocation()
        self.stockHoldings.setupFromConfigData(configData)
        heldStockSymbols = self.stockHoldings.getStockSymbols()
        self.stockValues = StockValues()
        self.stockValues.setStocks(heldStockSymbols)
        self.stockValues.run()
        self.exDivDates = ExDivDates()
#        self.exDivDates.run()
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
            { 'colLbl':"Change", 'colValName':"change", 'dataType':'str', 'fmtStr':'', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            { 'colLbl':"Change%", 'colValName':"chg_percent", 'dataType':'str', 'fmtStr':'', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            { 'colLbl':"Value", 'colValName':"totalvalue", 'dataType':'decimal', 'fmtStr':'{:0,.2f}', 'prfxStr':'£', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            { 'colLbl':"Profit", 'colValName':"profit", 'dataType':'decimal', 'fmtStr':'{:0,.2f}', 'prfxStr':'£', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right', 'colourCode':'PosNeg' },
            { 'colLbl':"Volume", 'colValName':"volume", 'dataType':'decimal', 'fmtStr':'{:0,.0f}', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            { 'colLbl':"ExDiv", 'colValName':"exDivDate", 'dataType':'str', 'fmtStr':'', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            { 'colLbl':"Amount", 'colValName':"exDivAmount", 'dataType':'decimal', 'fmtStr':'{:0.2f}', 'prfxStr':self.currencySign, 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right', 'onlyIfValid':'exDivDate' },
            { 'colLbl':"PayDate", 'colValName':"paymentDate", 'dataType':'str', 'fmtStr':'', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            ]
        self.watchTableColDefs = [
            { 'colLbl':"Sym", 'colValName':"sym", 'dataType':'str', 'fmtStr':'', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'left', 'fontSize':'large', 'colourCode':'PosNeg', 'colourByCol':'change' },
            { 'colLbl':"Name", 'colValName':"name", 'dataType':'str', 'fmtStr':'', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'left', 'fontSize':'small' },
            { 'colLbl':"Last", 'colValName':"price", 'dataType':'decimal', 'fmtStr':'{:0.2f}', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right', 'colourCode':'FlashPosNeg', 'colourBy':'change' },
            { 'colLbl':"Change", 'colValName':"change", 'dataType':'str', 'fmtStr':'', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            { 'colLbl':"Change%", 'colValName':"chg_percent", 'dataType':'str', 'fmtStr':'{:0.2f}', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            { 'colLbl':"Volume", 'colValName':"volume", 'dataType':'decimal', 'fmtStr':'{:0,.0f}', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            { 'colLbl':"ExDiv", 'colValName':"exDivDate", 'dataType':'str', 'fmtStr':'', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            { 'colLbl':"Amount", 'colValName':"exDivAmount", 'dataType':'decimal', 'fmtStr':'{:0.2f}', 'prfxStr':self.currencySign, 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right', 'onlyIfValid':'exDivDate' },
            { 'colLbl':"PayDate", 'colValName':"paymentDate", 'dataType':'str', 'fmtStr':'', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            ]
        self.initUI()

        
    def initUI(self):

        # Grid layout for the tables
        self.gridLayout = QtWidgets.QGridLayout()

        # Table(s) to handle watch list
        numWatchTables = 3
        self.watchTables = []
        for tabIdx in range(numWatchTables):
            newTab = StockTable()
            newTab.initTable(self.watchTableColDefs, self.currencySign, False, QtGui.QFont('SansSerif', 9), QtGui.QFont('SansSerif', 8), QtGui.QFont('SansSerif', 9, QtGui.QFont.Bold))
            self.watchTables.append(newTab)

#        self.watchTable = StockTable()
#        self.watchTable.initTable(self.watchTableColDefs, self.currencySign, False, QtGui.QFont('SansSerif', 9), QtGui.QFont('SansSerif', 8), QtGui.QFont('SansSerif', 11, QtGui.QFont.Bold))
#        self.watchTable.populateTable(watchStocks)

        # Table(s) for portfolio stocks
        numPortfolioTables = 2
        self.portfolioTables = []
        for tabIdx in range(numPortfolioTables):
            newTab = StockTable()
            newTab.initTable(self.portfolioTableColDefs, self.currencySign, tabIdx==numPortfolioTables-1, QtGui.QFont('SansSerif', 10), QtGui.QFont('SansSerif', 8), QtGui.QFont('SansSerif', 11, QtGui.QFont.Bold))
            self.portfolioTables.append(newTab)

        # Populate tables
        self.populateTablesWithStocks()
        self.exDivDates.setFromStockHoldings(self.stockHoldings.getStockHolding(False))

        # Span for watch tables and portfolio tables
        watchTabColSpan = numPortfolioTables
        portfolioTabColSpan = numWatchTables

        # Add tables to grid
        for tabIdx in range(len(self.watchTables)):
            self.gridLayout.addWidget(self.watchTables[tabIdx].stocksTable, 0, tabIdx*watchTabColSpan, 1, watchTabColSpan)
        for tabIdx in range(len(self.portfolioTables)):
            self.gridLayout.addWidget(self.portfolioTables[tabIdx].stocksTable, 1, tabIdx*portfolioTabColSpan, 1, portfolioTabColSpan)
        
        # Edit action
        editAction = QtWidgets.QAction(QtGui.QIcon('edit.png'), '&Edit', self)        
        editAction.setStatusTip('Edit shares')
        editAction.triggered.connect(self.editStocksList)

        # Exit action
        exitAction = QtWidgets.QAction(QtGui.QIcon('exit.png'), '&Exit', self)        
        exitAction.setStatusTip('Exit application')
        exitAction.triggered.connect(self.quitApp)

        # GridWidget that holds everything        
        gridWidget = QtWidgets.QWidget()
        gridWidget.setLayout(self.gridLayout)
        gridWidget.addAction(editAction)
        gridWidget.addAction(exitAction)
        gridWidget.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        self.setCentralWidget(gridWidget)
#        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
        
        self.setWindowTitle('Stock Ticker')
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
        print('Stopping')
        self.stockValues.stop()
        self.exDivDates.stop()
        self.updateTimer.stop()
        event.accept()
        
    def updateStockValues(self):
        # Check if stocks information has changed
        self.stocksViewLock.acquire()
        if self.stocksListChanged:
            print ("Stock list changed")
            self.populateTablesWithStocks()
            self.exDivDates.setFromStockHoldings(self.stockHoldings.getStockHolding(False))
            self.stocksListChanged = False
        self.stocksViewLock.release()

        for table in self.watchTables:
            table.updateTable(self.stockValues, self.exDivDates, [Decimal("0"),Decimal("0"),0,0])
        tableTotals = [Decimal("0"),Decimal("0"),0,0]
        for table in self.portfolioTables:
            tableTotals = table.updateTable(self.stockValues, self.exDivDates, tableTotals)
            table.SetTotals(tableTotals)

        # Handle window size updates
        watchWidth = 0
        watchHeight = 0
        portfolioWidth = 0
        portfolioHeight = 0
        for table in self.watchTables:
            optSizeWatch = table.getOptimumTableSize()
            watchWidth += optSizeWatch[0] + 20
            watchHeight = max(watchHeight, optSizeWatch[1])
        watchHeight += 10
        for table in self.portfolioTables:
            optSizePortfolio = table.getOptimumTableSize()
            portfolioWidth += optSizePortfolio[0] + 20
            portfolioHeight = max(portfolioHeight, optSizePortfolio[1])
        portfolioWidth += 20
        portfolioHeight += 10
        self.gridLayout.setRowStretch(0, watchHeight)
        self.gridLayout.setRowStretch(1, portfolioHeight)
        self.setMinimumWidth(max(watchWidth, portfolioWidth))
        self.setMinimumHeight(watchHeight+portfolioHeight)
        
def main():
    app = QtWidgets.QApplication(sys.argv)
    stockTicker = RStockTicker()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
