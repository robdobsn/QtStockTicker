# -*- coding: utf-8 -*-

import os
import sys
import threading
import logging
import requests
import datetime
import time
import tracemalloc
import argparse

from PySide6 import QtGui, QtWidgets, QtCore
from PySide6.QtCore import QTimer, Qt
from StockHoldings import StockHoldings
from StockSettingsDialog import StockSettingsDialog
from StockSymbolList import StockSymbolList
from ExDivDates import ExDivDates
from StockTable import StockTable
# Decimal no longer used - float is sufficient for stock prices
from ExchangeRates import ExchangeRates
from YahooCalendarEvents import YahooCalendarEvents
from LocalConfig import LocalConfig
from HostedConfigFile import HostedConfigFile
from ResourcePath import getResourcePath
from StockProviderManager import StockProviderManager

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

    def __init__(self, profiling=False):
        # Superclass
        super(RStockTicker, self).__init__()
        # Profiling
        self.profiling = profiling
        self._updateTimings = []
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

        # Stock values getter - use provider manager with intelligent fallback
        self.stockValues = StockProviderManager(self.symbolDataChanged, self.localConfigFile)
        logger.info("Using StockProviderManager with intelligent fallback")

        self.stockValues.setStocks(heldStockSymbols)
        self.stockValues.start()

        # Ex-dividend dates getter
        self.exDivDates = ExDivDates(self.exchangeRates)
        # self.exDivDates.run()

        # Yahoo calendar events (ex-div + earnings dates) — daily refresh
        yahoo_api_key = self._readConfigValue("YAHOO_FINANCE_API_KEY")
        yahoo_api_host = self._readConfigValue("YAHOO_API_HOST", "yahoo-finance15.p.rapidapi.com")
        self.yahooCalendarEvents = None
        if yahoo_api_key:
            self.yahooCalendarEvents = YahooCalendarEvents(yahoo_api_key, yahoo_api_host)
            self.yahooCalendarEvents.setSymbols([s if isinstance(s, str) else s.get('symbol','') for s in heldStockSymbols])
            self.yahooCalendarEvents.run()
            logger.info("YahooCalendarEvents started")
        else:
            logger.warning("YAHOO_FINANCE_API_KEY not set — YahooCalendarEvents disabled")

        # Update for the display
        self.updateTimer = QTimer(self)
        self.updateTimer.timeout.connect(self.updateStockValues)
        self.updateTimer.start(2000)

        # Profiling: periodic tracemalloc snapshots
        if self.profiling:
            self._profilingStartTime = time.perf_counter()
            self._snapshotIntervals = [60, 300, 1800]  # seconds: 1m, 5m, 30m
            self._nextSnapshotIdx = 0
            self._dumpTracemalloc("startup")
            self._profilingTimer = QTimer(self)
            self._profilingTimer.timeout.connect(self._checkProfilingSnapshot)
            self._profilingTimer.start(10000)  # check every 10s
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
            { 'colLbl':"Earnings", 'colValName':"earningsDate", 'dataType':'str', 'fmtStr':'', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
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
            { 'colLbl':"Earnings", 'colValName':"earningsDate", 'dataType':'str', 'fmtStr':'', 'prfxStr':'', 'pstfxStr':'', 'anchor':"e", 'sticky':"EW", 'align':'right' },
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

        # Add main splitter - this is the correct way for QMainWindow
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

    def _readConfigValue(self, key, default=""):
        """Read a value from privatesettings/config.ini"""
        try:
            with open("privatesettings/config.ini", "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if line.startswith(key + "="):
                        return line.split("=", 1)[1].strip()
        except Exception as e:
            logger.debug(f"Could not read {key} from config.ini: {e}")
        return default
        
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
        if self.yahooCalendarEvents:
            self.yahooCalendarEvents.setSymbols([s if isinstance(s, str) else s.get('symbol','') for s in heldStockSymbols])
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
        if self.yahooCalendarEvents:
            self.yahooCalendarEvents.stop()
        self.updateTimer.stop()
        self.exchangeRates.stop()
        event.accept()
        
    def updateStockValues(self):
        t0 = time.perf_counter() if self.profiling else None

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
            if len(changedStockDict) == 0:
                # logger.debug(f"No Update Required {changedStockDict}")
                return
            # else:
            #     logger.debug(f"Doing update {changedStockDict}")

        # Update the tables
        if self.profiling:
            t_tables_start = time.perf_counter()
            watch_times = []
            folio_times = []

        for i, table in enumerate(self.watchTables):
            t_tab = time.perf_counter() if self.profiling else None
            table.updateTable(self.stockValues, self.exDivDates, changedStockDict, [0.0, 0.0, 0, 0], self.yahooCalendarEvents)
            if self.profiling:
                watch_times.append((time.perf_counter() - t_tab) * 1000)

        tableTotals = [0.0, 0.0, 0, 0]
        for i, table in enumerate(self.portfolioTables):
            t_tab = time.perf_counter() if self.profiling else None
            tableTotals = table.updateTable(self.stockValues, self.exDivDates, changedStockDict, tableTotals, self.yahooCalendarEvents)
            table.SetTotals(tableTotals)
            if self.profiling:
                folio_times.append((time.perf_counter() - t_tab) * 1000)

        if self.profiling:
            t_end = time.perf_counter()
            tables_ms = (t_end - t_tables_start) * 1000
            elapsed_ms = (t_end - t0) * 1000
            watch_str = '+'.join(f'{t:.0f}' for t in watch_times)
            folio_str = '+'.join(f'{t:.0f}' for t in folio_times)
            pre_tables_ms = (t_tables_start - t0) * 1000
            if tables_ms > 50:
                logger.info(f"PROFILING: tables total={tables_ms:.0f}ms  watch=[{watch_str}]ms  folio=[{folio_str}]ms  pre={pre_tables_ms:.0f}ms  cycle={elapsed_ms:.0f}ms")

        # Profiling: log update cycle duration
        if self.profiling and t0 is not None:
            self._updateTimings.append(elapsed_ms)
            if elapsed_ms > 50:
                logger.warning(f"PROFILING: updateStockValues took {elapsed_ms:.1f}ms")
            # Log summary every 30 cycles (~60s)
            if len(self._updateTimings) >= 30:
                avg = sum(self._updateTimings) / len(self._updateTimings)
                peak = max(self._updateTimings)
                logger.info(f"PROFILING: updateStockValues last 30 cycles — avg={avg:.1f}ms, peak={peak:.1f}ms")
                self._updateTimings.clear()

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

    def symbolDataChanged(self, symbol):
        """Callback for when stock data changes"""
        pass

    def _dumpTracemalloc(self, label):
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics('lineno')
        current, peak = tracemalloc.get_traced_memory()
        logger.info(f"PROFILING: tracemalloc [{label}] current={current/1024:.0f}KB peak={peak/1024:.0f}KB")
        logger.info(f"PROFILING: tracemalloc [{label}] top 15 allocations:")
        for stat in top_stats[:15]:
            logger.info(f"  {stat}")

    def _checkProfilingSnapshot(self):
        if self._nextSnapshotIdx >= len(self._snapshotIntervals):
            self._profilingTimer.stop()
            return
        elapsed = time.perf_counter() - self._profilingStartTime
        target = self._snapshotIntervals[self._nextSnapshotIdx]
        if elapsed >= target:
            label = f"{target}s"
            self._dumpTracemalloc(label)
            self._nextSnapshotIdx += 1

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

    # Parse arguments
    parser = argparse.ArgumentParser(description='Stock Ticker')
    parser.add_argument('--profile', action='store_true', help='Enable Phase 1 profiling (tracemalloc + update cycle timing)')
    args, remaining = parser.parse_known_args()

    # Start tracemalloc before any allocations if profiling
    if args.profile:
        tracemalloc.start()
        logger.info("PROFILING: tracemalloc started")

    # Start the app
    logger.debug(f"StockTicker: Starting")
    app = QtWidgets.QApplication(remaining)
    app.setWindowIcon(QtGui.QIcon(getResourcePath('StockTickerIcon.ico')))
    stockTicker = RStockTicker(profiling=args.profile)
    curExitCode = app.exec()
    sys.exit(curExitCode)

if __name__ == '__main__':
    main()
