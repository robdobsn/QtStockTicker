# -*- coding: utf-8 -*-

import sys
from PyQt5 import QtGui, QtWidgets, QtCore
from PyQt5.QtCore import QTimer, QTime

from StockHoldings import StockHoldings
from StockValues import StockValues
from StockSettingsDialog import StockSettingsDialog
from StockSymbolList import StockSymbolList
from HostedConfigFile import HostedConfigFile
from ExDivDates import ExDivDates
import threading

'''
Created on 4 Sep 2013

@author: rob dobson
'''

class RStockTicker(QtWidgets.QMainWindow):

    stockHoldings = None
    uiColDefs = []
    uiRowDefs = []
    updateTimer = None
    brushRed = QtGui.QBrush(QtGui.QColor(200, 0, 0))
    brushRed.setStyle(QtCore.Qt.SolidPattern)
    brushGreen = QtGui.QBrush(QtGui.QColor(0, 150, 0))
    brushGreen.setStyle(QtCore.Qt.SolidPattern)
    brushText = QtGui.QBrush(QtGui.QColor(255, 255, 255))
    brushText.setStyle(QtCore.Qt.SolidPattern)
    brushTotals = QtGui.QBrush(QtGui.QColor(255, 255, 0))
    brushTotals.setStyle(QtCore.Qt.SolidPattern)
    gradient = QtGui.QLinearGradient(0, 0, 250, 0)
    gradient.setColorAt(0.0, QtGui.QColor(120, 120, 120))
    gradient.setColorAt(1.0, QtGui.QColor(0, 0, 0))
    brushBackground = QtGui.QBrush(gradient)
    brushNeutral = QtGui.QBrush(QtGui.QColor(0, 0, 0, 0))
    totalsRow = 0
    totalProfitCol = 0
    totalValueCol = 0
    currencySign = "\xA3"
    dataFlashTimerStarted = False
    dataFlashTimer = QTime();
    dataFlashTimeMs = 400;
    stocksViewLock = threading.Lock()
    stocksListChanged = False
    
    def __init__(self):
        super(RStockTicker, self).__init__()
        self.hostedConfigFile = HostedConfigFile()
        self.hostedConfigFile.initFromFile('stockTickerConfig.json')
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
        self.uiColDefs = [
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

        # Table for stocks
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(len(self.uiColDefs))
        self.table.setShowGrid(False)
        self.table.setFocusPolicy(QtCore.Qt.NoFocus)
        self.table.verticalHeader().setVisible(False)
#        self.table.setSortingEnabled(True)
#        self.table.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        colIdx = 0
        for colDef in self.uiColDefs:
            hdrItem = QtWidgets.QTableWidgetItem(colDef['colLbl'])
            if 'align' in colDef and colDef['align'] == 'right':
                hdrItem.setTextAlignment(QtCore.Qt.AlignRight)
            else:
                hdrItem.setTextAlignment(QtCore.Qt.AlignLeft)
            hdrItem.setFont(QtGui.QFont('SansSerif', 11))
            self.table.setHorizontalHeaderItem(colIdx, hdrItem)
            colIdx += 1
        palette = QtGui.QPalette()
        palette.setBrush(QtGui.QPalette.Base, self.brushBackground)
        self.table.setPalette(palette)

        self.populateStocksTable()

        # Edit action
        editAction = QtWidgets.QAction(QtGui.QIcon('edit.png'), '&Edit', self)        
        editAction.setStatusTip('Edit shares')
        editAction.triggered.connect(self.editStocksList)

        # Exit action
        exitAction = QtWidgets.QAction(QtGui.QIcon('exit.png'), '&Exit', self)        
        exitAction.setStatusTip('Exit application')
        exitAction.triggered.connect(self.quitApp)
        
        self.table.addAction(editAction)
        self.table.addAction(exitAction)
        self.table.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        grid.addWidget(self.table, 0, 0)
#        self.setLayout(grid)
        gridWidget = QtWidgets.QWidget()
        gridWidget.setLayout(grid)
        self.setCentralWidget(gridWidget)
#        self.setWindowFlags(QtCore.Qt.FramelessWindowHint)
        
        self.setWindowTitle('Stock Ticker')
        self.show()

    def populateStocksTable(self):
        # Stock items view in table
        self.uiRowDefs = []
        self.table.setRowCount(self.stockHoldings.numStocks() + 1)
        rowIdx = 0
        stockHolding = self.stockHoldings.getStockHolding(False)
        for stk in stockHolding:
            self.table.setRowHeight(rowIdx,20)
            colIdx = 0
            for colDef in self.uiColDefs:
                if colDef['colValName'] == 'profit':
                    self.totalProfitCol = colIdx
                elif colDef['colValName'] == 'totalvalue':
                    self.totalValueCol = colIdx
                if 'fontSize' in colDef and colDef['fontSize'] == 'large':
                    font1 = QtGui.QFont('SansSerif', 13, QtGui.QFont.Bold)
                elif 'fontSize' in colDef and colDef['fontSize'] == 'small':
                    font1 = QtGui.QFont('SansSerif', 9)
                else:
                    font1 = QtGui.QFont('SansSerif', 11)
                it1 = self.tableItem("", self.brushText, QtCore.Qt.AlignRight if ('align' in colDef and colDef['align'] == 'right') else QtCore.Qt.AlignLeft, font1)
                self.table.setItem(rowIdx, colIdx, it1)
                colIdx += 1
            rowDef = { 'sym':stk['symbol'], 'hld':stk['holding'], 'cost':stk['cost'] }
#            print(stk['symbol'], stk['holding'],stk['cost'])
            self.uiRowDefs.append(rowDef)
#            print (stk['symbol'])
            rowIdx += 1
        self.totalsRow = rowIdx

        # fill remainder of table with empty cells
        colIdx = 0
        for colDef in self.uiColDefs:
            it1 = self.tableItem("", self.brushText, QtCore.Qt.AlignLeft, QtGui.QFont('SansSerif', 11))
            self.table.setItem(self.totalsRow, colIdx, it1)
            colIdx += 1
            
        # Totals
        itTotLabel = self.tableItem("Totals", self.brushTotals, QtCore.Qt.AlignLeft, QtGui.QFont('SansSerif', 11))
        self.table.setItem(self.totalsRow, min(self.totalProfitCol, self.totalValueCol)-1, itTotLabel)
        itTotProfitVal = self.tableItem("", self.brushTotals, QtCore.Qt.AlignRight, QtGui.QFont('SansSerif', 11))
        self.table.setItem(self.totalsRow, self.totalProfitCol, itTotProfitVal)
        itTotalVal = self.tableItem("", self.brushTotals, QtCore.Qt.AlignRight, QtGui.QFont('SansSerif', 11))
        self.table.setItem(self.totalsRow, self.totalValueCol, itTotalVal)

    def tableItem(self, txt, foreGnd, align, font):
        it1 = QtWidgets.QTableWidgetItem(txt)
        it1.setForeground(foreGnd)
        it1.setTextAlignment(align)
        it1.setFont(font)
        it1.setFlags(it1.flags() ^ (QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable))
        return it1
        
    def quitApp(self):
        QtWidgets.qApp.closeAllWindows()
        
    def editStocksList(self):
        editWindow = StockSettingsDialog()
        editWindow.setContext(self.stockHoldings, self.uiColDefs, self.stockSymbolList)
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

    def optTableSize(self):
        w = self.table.verticalHeader().width() + 4
        for i in range(self.table.columnCount()):
#            w += self.table.horizontalHeaderItem(i).sizeHint().width()
            w += self.table.columnWidth(i)
        h = self.table.horizontalHeader().height() + 4
#        self.table.item(0,0).height() * self.table.rowCount()
        for i in range(self.table.rowCount()):
            h += self.table.rowHeight(i)
        return (w,h)
        
    def updateDataFlash(self):
        if self.dataFlashTimerStarted:
            if self.dataFlashTimer.elapsed() > self.dataFlashTimeMs:
                self.dataFlashTimerStarted = False
                for rowIdx in range(len(self.uiRowDefs)):
                    for colIdx in range(len(self.uiColDefs)):
                        uiCell = self.table.item(rowIdx, colIdx)
                        colDef = self.uiColDefs[colIdx]
                        if 'colourCode' in colDef:
                            if colDef['colourCode'] == 'FlashPosNeg':
                                uiCell.setBackground(self.brushNeutral)
                    
    def updateStockValues(self):
        # Flash any changed data
        self.updateDataFlash()
        
        # Check if stocks information has changed
        self.stocksViewLock.acquire()
        if self.stocksListChanged:
            print ("Stock list changed")
            self.dataFlashTimerStarted = False
            self.populateStocksTable()
            self.stocksListChanged = False
        self.stocksViewLock.release()

        # Update stock table values
        rowIdx = 0
        totalVal = 0
        totalProfit = 0
        for uiRowDef in self.uiRowDefs:
            stkValues = self.stockValues.getStockData(uiRowDef["sym"])
            if stkValues != None:
                self.exDivDates.addToStockInfo(uiRowDef["sym"], stkValues)
                colIdx=0
                for colDef in self.uiColDefs:
                    valChanged = False
                    uiCell = self.table.item(rowIdx, colIdx)
                    if not "price" in stkValues:
                        break;
                    stkVal = 0 if (not "price" in stkValues) else float(stkValues["price"])
                    curVal = float(stkVal) * uiRowDef["hld"] / 100.0
                    colValStr = stkValues[colDef['colValName']] if (colDef['colValName'] in stkValues) else "0"
                    if colDef['colValName'] == 'sym':
                        colStr = uiRowDef['sym']
                    elif colDef['colValName'] == 'hld':
                        colStr = '{:2,.0f}'.format(uiRowDef['hld'])
                    elif colDef['colValName'] == 'cost':
                        colStr = self.currencySign + '{:2,.2f}'.format(uiRowDef['cost'])
                        colValStr = str(uiRowDef['cost'])
                    elif colDef['colValName'] == 'profit':
                        profitVal = curVal - uiRowDef['cost']
                        colStr = self.currencySign + '{:2,.2f}'.format(profitVal)
                        totalProfit += profitVal
                        colValStr = str(profitVal)
                    elif colDef['colValName'] == 'totalvalue':
                        colStr = self.currencySign + '{:2,.2f}'.format(curVal)
                        colValStr = str(curVal)
                        totalVal += curVal
                    elif colDef['dataType'] == 'str':
                        colStr = "" if (not colDef['colValName'] in stkValues) else stkValues[colDef['colValName']]
                    elif colDef['dataType'] == 'float':
                        try:
                            colStr = colDef['prfxStr'] if 'prfxStr' in colDef else ""
                            colStr += colDef['fmtStr'].format(float(colValStr)) if ('fmtStr' in colDef and colDef['fmtStr'] != "") else colValStr 
                            colStr += colDef['pstfxStr'] if ('pstfxStr' in colDef) else ""
                        except:
                            colStr = colValStr
#                            print (colDef['colValName'], uiCell.text(), colStr, valChanged, colDef)
                    valChanged = (uiCell.text() != colStr)
                    if 'colourCode' in colDef:
                        if colDef['colourCode'] == 'PosNeg' or ((colDef['colourCode'] == 'FlashPosNeg') and valChanged):
#                            print ("Price", valChanged, colDef['colourCode'], colValStr, uiCell.text())
                            colourByVal = colValStr
                            if 'colourBy' in colDef:
                                if colDef['colourBy'] == 'change':
                                    curCellVal = 0
                                    try:
                                        curCellVal = float(uiCell.text())
                                    except:
                                        curCellVal = 0
                                    colourByVal = float(colValStr) - curCellVal
                            elif 'colourByCol' in colDef:
                                colToColourBy = colDef['colourByCol']
                                colourByVal = stkValues[colToColourBy]
#                            if colDef['colValName'] == 'price':
#                                print ("Price..", colourByVal, float(colValStr), curCellVal)
                            valToColourBy = 0
                            try:
                                valToColourBy = float(colourByVal)
                            except:
                                valToColourBy = 0
                            if valToColourBy > 0:
                                uiCell.setBackground(self.brushGreen)
                            elif valToColourBy < 0:
                                uiCell.setBackground(self.brushRed)
                            else:
                                uiCell.setBackground(self.brushNeutral)
                        if (colDef['colourCode'] == 'FlashPosNeg') and valChanged:
                            self.dataFlashTimerStarted = True
                            self.dataFlashTimer.start()
                    bShowValue = True
                    if 'onlyIfValid' in colDef:
                        bShowValue = False
                        if colDef['onlyIfValid'] in stkValues:
                            if stkValues[colDef['onlyIfValid']] != "":
                                bShowValue = True
                    if bShowValue:
                        uiCell.setText(colStr)
                    colIdx += 1
            rowIdx += 1
        self.table.item(self.totalsRow, self.totalProfitCol).setText(self.currencySign + '{:2,.2f}'.format(totalProfit))
        self.table.item(self.totalsRow, self.totalValueCol).setText(self.currencySign + '{:2,.2f}'.format(totalVal))
        self.table.resizeColumnsToContents()
        optSize = self.optTableSize()
        self.setMinimumWidth(optSize[0]+20)
        self.setMinimumHeight(optSize[1])
        
def main():
    app = QtWidgets.QApplication(sys.argv)
    stockTicker = RStockTicker()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
