# -*- coding: utf-8 -*-

import os
import sys
import threading
import logging
import requests
import datetime
import time

from PySide6 import QtGui, QtWidgets, QtCore
from PySide6.QtCore import QTimer, Qt
from StockHoldings import StockHoldings
from StockValues_InteractiveBrokers import StockValues_InteractiveBrokers
from StockSettingsDialog import StockSettingsDialog
from StockSymbolList import StockSymbolList
from ExDivDates import ExDivDates
from StockTable import StockTable
from decimal import Decimal
from ExchangeRates import ExchangeRates
from LocalConfig import LocalConfig
from HostedConfigFile import HostedConfigFile
from ResourcePath import getResourcePath

'''
Created on 4 Sep 2013

@author: rob dobson
'''

# Logging
logger = logging.getLogger("StockTickerLogger")
basedir = os.path.dirname(__file__)
logger.setLevel(logging.DEBUG)

# Taskbar icon control
try:
    from ctypes import windll  # Only exists on Windows.
    myappid = 'robdobson.stockticker.main.version' # arbitrary string
    windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except ImportError:
    pass

# Send to message board
SEND_TO_MESSAGE_BOARD = False

class RStockTicker(QtWidgets.QMainWindow):

    def __init__(self):
        # Superclass
        super(RStockTicker, self).__init__()
        # Init
        self.currencySign = "\xA3"
        self.stocksViewLock = threading.Lock()
        self.stocksListChanged = False
        self.windowTitle = ""
        self.MARKET_OPEN_CHECK_TICKS = 60
        self.ticksBeforeMarketOpenCheck = self.MARKET_OPEN_CHECK_TICKS
        self.numWatchTables = 3
        self.numFolioTables = 3
        self.stockHoldings = StockHoldings()

        # Local config
        self.localConfigFile = LocalConfig("localConfig.json")

        # Hosted config
        self.hostedConfigFile = HostedConfigFile()
        self.hostedConfigFile.initFromFile('privatesettings/stockTickerConfig.json')
        #self.stockreader.readFromShareScopeCSV("robstkexpt.csv")
        stocksDataFileContents = self.hostedConfigFile.getConfigDataFromLocation()

        # Load stocks from file
        self.stockHoldings.loadFromStocksDataFileContents(stocksDataFileContents)
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
        # self.exDivDates.run()

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
        fontAction = QtGui.QAction(QtGui.QIcon(getResourcePath('font.png')), '&' + title, self)
        fontAction.setStatusTip(title)
        fontAction.triggered.connect(lambda: self.changeFont(connectParam1, connectParam2))
        return fontAction

    def initUI(self):

        # Edit menu action
        editAction = QtGui.QAction(QtGui.QIcon(getResourcePath('edit.png')), '&Edit', self)
        editAction.setStatusTip('Edit shares')
        editAction.triggered.connect(self.editStocksList)

        # Exit menu action
        exitAction = QtGui.QAction(QtGui.QIcon(getResourcePath('exit.png')), '&Exit', self)
        exitAction.setStatusTip('Exit application')
        exitAction.triggered.connect(self.quitApp)

        # Table(s) to handle watch list
        self.watchTableSplitter = QtWidgets.QSplitter()
        self.watchTables: list[StockTable] = []
        for tabIdx in range(self.numWatchTables):
            newTab = StockTable()
            newTab.initTable(self, self.watchTableColDefs, self.currencySign, False, "watch", self.localConfigFile)
            # Add menu actions
            newTab.addAction(editAction)
            newTab.addAction(self.getFontAction("Normal Font", "watch", "normal"))
            newTab.addAction(self.getFontAction("Large Font", "watch", "large"))
            newTab.addAction(exitAction)
            newTab.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
            # Add to list of tables
            self.watchTables.append(newTab)
            self.watchTableSplitter.addWidget(newTab)

        # Table(s) for portfolio stocks
        self.portfolioTableSplitter = QtWidgets.QSplitter()
        self.portfolioTables: list[StockTable] = []
        for tabIdx in range(self.numFolioTables):
            newTab = StockTable()
            newTab.initTable(self, self.portfolioTableColDefs, self.currencySign, tabIdx==self.numFolioTables-1, "folio", self.localConfigFile)
            # Add menu actions
            newTab.addAction(editAction)
            newTab.addAction(self.getFontAction("Normal Font", "folio", "normal"))
            newTab.addAction(self.getFontAction("Large Font", "folio", "large"))
            newTab.addAction(self.getFontAction("Totals Font", "folio", "totals"))
            newTab.addAction(exitAction)
            newTab.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
            # Add to list of tables
            self.portfolioTables.append(newTab)
            self.portfolioTableSplitter.addWidget(newTab)

        # Populate tables
        self.populateTablesWithStocks()
        self.exDivDates.setFromStockHoldings(self.stockHoldings.getStockHoldings(False))

        # Layout for the tables
        self.mainSplitter = QtWidgets.QSplitter(Qt.Vertical)
        self.mainSplitter.addWidget(self.watchTableSplitter)
        self.mainSplitter.addWidget(self.portfolioTableSplitter)
        self.mainSplitter.splitterMoved.connect(self.splitterMoved)

        # Layout for whole page
        self.layout = QtWidgets.QHBoxLayout(self)
        self.layout.addWidget(self.mainSplitter)
        self.setLayout(self.layout)

        # Add main splitter
        self.setCentralWidget(self.mainSplitter)

        # Window title
        self.windowTitle = 'Stock Ticker'
        self.setWindowTitle(self.windowTitle)
        self.resize(1280,800)
        self.show()

    def populateTablesWithStocks(self):
        fullStockList = self.stockHoldings.getStockHoldings(False)
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
        if self.hostedConfigFile is not None:
            self.hostedConfigFile.configFileUpdate(configData)

    def changeFont(self, tableName, tableFont):
        logger.debug(f"changeFont {tableName} {tableFont}")
        if tableName == "watch":
            curFontStr = self.watchTables[0].getFontStr(tableFont)
        else:
            curFontStr = self.portfolioTables[0].getFontStr(tableFont)
        curQFont = QtGui.QFont()
        curQFont.fromString(curFontStr)
        valid, font = QtWidgets.QFontDialog.getFont(curQFont)
        if valid and font is not None:
            fontStr = font.toString()
            if tableName == "watch":
                for tab in self.watchTables:
                    tab.setFontStr(tableFont, fontStr)
            else:
                for tab in self.portfolioTables:
                    tab.setFontStr(tableFont, fontStr)

    def closeEvent(self, event):
        logger.debug(f"closeEvent {event}")
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
            logger.debug(f"updateStockValues stock list changed")
            self.populateTablesWithStocks()
            self.exDivDates.setFromStockHoldings(self.stockHoldings.getStockHoldings(False))
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
                # logger.debug(f"No Update Required {changedStockDict}")
                return
            # else:
            #     logger.debug(f"Doing update {changedStockDict}")

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
                logger.debug("StockTicker: Failed to send stock data to LED Panel")

    def resizeEvent(self, event):
        # logger.debug(f"resizeEvent {event.size().width()} {event.size().height()}")
        for table in self.watchTables:
            table.resizeTableCells()

    def splitterMoved(self, pos, index):
        # logger.debug(f"splitterResizedOrMoved")
        for table in self.watchTables:
            table.resizeTableCells()

def main():
    # Create logs folder if it doesn't exist
    try:
        if not os.path.exists("logs"):
            os.makedirs("logs")
    except:
        pass
    # Log to file in logs folder with name based on data and time uniquely
    logFileName = "logs/StockTicker_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".log"
    # Logging to file and console with format including time, level and module
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(module)s %(funcName)s %(message)s')
    # Logging to file
    fh = logging.FileHandler(logFileName)
    fh.setFormatter(formatter)
    fh.setLevel(logging.DEBUG)
    logging.getLogger('').addHandler(fh)

    # Logging to console
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    ch.setLevel(logging.DEBUG)
    logging.getLogger('').addHandler(ch)

    # Start the app
    logger.debug(f"StockTicker: Starting")
    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(QtGui.QIcon(getResourcePath('StockTickerIcon.ico')))
    stockTicker = RStockTicker()
    curExitCode = app.exec()
    sys.exit(curExitCode)

if __name__ == '__main__':
    main()
