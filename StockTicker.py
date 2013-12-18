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
        self.exDivDates.run()
        self.updateTimer = QTimer(self)
        self.updateTimer.timeout.connect(self.updateStockValues)
        self.updateTimer.start(1000)
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
        numWatchTables = 2
        self.watchTables = []
        for tabIdx in range(numWatchTables):
            newTab = StockTable()
            newTab.initTable(self.watchTableColDefs, self.currencySign, False, QtGui.QFont('SansSerif', 9), QtGui.QFont('SansSerif', 8), QtGui.QFont('SansSerif', 9, QtGui.QFont.Bold))
            self.watchTables.append(newTab)

#        self.watchTable = StockTable()
#        self.watchTable.initTable(self.watchTableColDefs, self.currencySign, False, QtGui.QFont('SansSerif', 9), QtGui.QFont('SansSerif', 8), QtGui.QFont('SansSerif', 11, QtGui.QFont.Bold))
#        self.watchTable.populateTable(watchStocks)

        # Table for portfolio stocks
        self.portfolioTable = StockTable()
        self.portfolioTable.initTable(self.portfolioTableColDefs, self.currencySign, True, QtGui.QFont('SansSerif', 11), QtGui.QFont('SansSerif', 9), QtGui.QFont('SansSerif', 13, QtGui.QFont.Bold))

        # Populate tables
        self.populateTablesWithStocks()
        
        # Add tables to grid
        for tabIdx in range(len(self.watchTables)):
            self.gridLayout.addWidget(self.watchTables[tabIdx].stocksTable, 0, tabIdx)
        self.gridLayout.addWidget(self.portfolioTable.stocksTable, 1, 0, 1, len(self.watchTables))
        
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
        numWatchStocksPerTable = int(len(watchStocks)/len(self.watchTables))
        for tabIdx in range(len(self.watchTables)):
            self.watchTables[tabIdx].populateTable(watchStocks[tabIdx*numWatchStocksPerTable:((tabIdx+1)*numWatchStocksPerTable)])
        # Portfolio table
        portfolioStocks = [item for item in fullStockList if item['holding'] != 0]                
        self.portfolioTable.populateTable(portfolioStocks)

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
            self.stocksListChanged = False
        self.stocksViewLock.release()

        for table in self.watchTables:
            table.updateTable(self.stockValues, self.exDivDates)
        self.portfolioTable.updateTable(self.stockValues, self.exDivDates)
                
        # Handle window size updates
        watchWidth = 0
        watchHeight = 0
        for table in self.watchTables:
            optSizeWatch = table.getOptimumTableSize()
            watchWidth += optSizeWatch[0] + 20
            watchHeight = max(watchHeight, optSizeWatch[1])
        watchHeight = watchHeight + 10
        optSizePortfolio = self.portfolioTable.getOptimumTableSize()
        portfolioWidth = optSizePortfolio[0] + 20
        portfolioHeight = optSizePortfolio[1] + 10
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
