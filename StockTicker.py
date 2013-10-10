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
    portfolioTableColDefs = []
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
            { 'lblIdx':0, 'colLbl':"Sym", 'colValName':"sym", 'dataType':'str', 'fmtStr':'', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'left', 'fontSize':'large', 'colourCode':'PosNeg', 'colourByCol':'change' },
            { 'lblIdx':1, 'colLbl':"Name", 'colValName':"name", 'dataType':'str', 'fmtStr':'', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'left', 'fontSize':'small' },
            { 'lblIdx':2, 'colLbl':"Holding", 'colValName':"hld", 'dataType':'float', 'fmtStr':'{:0.0f}', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            { 'lblIdx':3, 'colLbl':"Last", 'colValName':"price", 'dataType':'float', 'fmtStr':'{:0.2f}', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right', 'colourCode':'FlashPosNeg', 'colourBy':'change' },
            { 'lblIdx':4, 'colLbl':"Change%", 'colValName':"chg_percent", 'dataType':'str', 'fmtStr':'{:0.2f}', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            { 'lblIdx':5, 'colLbl':"Value", 'colValName':"totalvalue", 'dataType':'float', 'fmtStr':'{:0.2f}', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            { 'lblIdx':6, 'colLbl':"Profit", 'colValName':"profit", 'dataType':'float', 'fmtStr':'{:0.2f}', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right', 'colourCode':'PosNeg' },
            { 'lblIdx':7, 'colLbl':"Volume", 'colValName':"volume", 'dataType':'float', 'fmtStr':'{:0,.0f}', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            { 'lblIdx':8, 'colLbl':"ExDiv", 'colValName':"exDivDate", 'dataType':'str', 'fmtStr':'', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            { 'lblIdx':9, 'colLbl':"Amount", 'colValName':"exDivAmount", 'dataType':'float', 'fmtStr':'{:0.2f}', 'prfxStr':self.currencySign, 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right', 'onlyIfValid':'exDivDate' },
            { 'lblIdx':10, 'colLbl':"PayDate", 'colValName':"paymentDate", 'dataType':'str', 'fmtStr':'', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
            ]
        self.initUI()

        
    def initUI(self):

        grid = QtWidgets.QGridLayout()
        
        self.portfolioTable = StockTable()
        self.portfolioTable.initTable(self.portfolioTableColDefs, self.currencySign)
        self.portfolioTable.populateTable(self.stockHoldings)

        # Edit action
        editAction = QtWidgets.QAction(QtGui.QIcon('edit.png'), '&Edit', self)        
        editAction.setStatusTip('Edit shares')
        editAction.triggered.connect(self.editStocksList)

        # Exit action
        exitAction = QtWidgets.QAction(QtGui.QIcon('exit.png'), '&Exit', self)        
        exitAction.setStatusTip('Exit application')
        exitAction.triggered.connect(self.quitApp)
        
        grid.addWidget(self.portfolioTable.stocksTable, 0, 0)
        
#        self.setLayout(grid)
        gridWidget = QtWidgets.QWidget()
        gridWidget.setLayout(grid)
        gridWidget.addAction(editAction)
        gridWidget.addAction(exitAction)
        gridWidget.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        self.setCentralWidget(gridWidget)
#        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
        
        self.setWindowTitle('Stock Ticker')
        self.show()
        
    def quitApp(self):
        QtWidgets.qApp.closeAllWindows()
        
    def editStocksList(self):
        editWindow = StockSettingsDialog()
        editWindow.setContext(self.stockHoldings, self.portfolioTableColDefs, self.stockSymbolList)
        editWindow.initUI()
        rslt = editWindow.exec()
        #print ("Edit stocks", rslt)
        if rslt != QtWidgets.QDialog.Accepted:
            return
#        for it in self.stockHoldings.getSortedStockHolding():
#            print(it)
#        for it in editWindow.updatedStockHoldings:
#            print (it)
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
            self.portfolioTable.clearDataFlash()
            self.populatePortfolioTable()
            self.stocksListChanged = False
        self.stocksViewLock.release()

        self.portfolioTable.updateTable(self.stockValues, self.exDivDates)
        optSize = self.portfolioTable.getOptimumTableSize()
        self.setMinimumWidth(optSize[0]+20)
        self.setMinimumHeight(optSize[1]+20)
        
def main():
    app = QtWidgets.QApplication(sys.argv)
    stockTicker = RStockTicker()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
