from PyQt5 import QtGui, QtWidgets, QtCore
from PyQt5.QtCore import QTime

'''
Created on 10 Oct 2013

@author: rob dobson
'''

class StockTable():
    
    uiColDefs = []
    uiRowDefs = []
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
    dataFlashTimerStarted = False
    dataFlashTimer = QTime();
    dataFlashTimeMs = 400;
    currencySign = ""
 
    def initTable(self, colDefs, currencySign, bTotalsRow, normalFont, smallFont, largeFont):
        self.uiColDefs = colDefs
        self.currencySign = currencySign
        self.bTotalsRow = bTotalsRow
        self.normalFont = normalFont
        self.smallFont = smallFont
        self.largeFont = largeFont
        
        # Table for stocks
        self.stocksTable = QtWidgets.QTableWidget()
        self.stocksTable.setColumnCount(len(self.uiColDefs))
        self.stocksTable.setShowGrid(False)
        self.stocksTable.setFocusPolicy(QtCore.Qt.NoFocus)
        self.stocksTable.verticalHeader().setVisible(False)
#        self.stocksTable.setSortingEnabled(True)
#        self.stocksTable.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        colIdx = 0
        for colDef in self.uiColDefs:
            hdrItem = QtWidgets.QTableWidgetItem(colDef['colLbl'])
            if 'align' in colDef and colDef['align'] == 'right':
                hdrItem.setTextAlignment(QtCore.Qt.AlignRight)
            else:
                hdrItem.setTextAlignment(QtCore.Qt.AlignLeft)
            hdrItem.setFont(self.normalFont)
            self.stocksTable.setHorizontalHeaderItem(colIdx, hdrItem)
            colIdx += 1
        palette = QtGui.QPalette()
        palette.setBrush(QtGui.QPalette.Base, self.brushBackground)
        self.stocksTable.setPalette(palette)

        
    def populateTable(self, stockHolding):
        
        # Stock items table
        self.uiRowDefs = []
        totalRowsInTable = len(stockHolding) + (1 if self.bTotalsRow else 0) 
        self.stocksTable.setRowCount(totalRowsInTable)
        rowIdx = 0
        for stk in stockHolding:
            self.stocksTable.setRowHeight(rowIdx,20)
            colIdx = 0
            for colDef in self.uiColDefs:
                if colDef['colValName'] == 'profit':
                    self.totalProfitCol = colIdx
                elif colDef['colValName'] == 'totalvalue':
                    self.totalValueCol = colIdx
                if 'fontSize' in colDef and colDef['fontSize'] == 'large':
                    font1 = self.largeFont
                elif 'fontSize' in colDef and colDef['fontSize'] == 'small':
                    font1 = self.smallFont
                else:
                    font1 = self.normalFont
                it1 = self.makeTableItem("", self.brushText, QtCore.Qt.AlignRight if ('align' in colDef and colDef['align'] == 'right') else QtCore.Qt.AlignLeft, font1)
                self.stocksTable.setItem(rowIdx, colIdx, it1)
                colIdx += 1
            rowDef = { 'sym':stk['symbol'], 'hld':stk['holding'], 'cost':stk['cost'] }
            self.uiRowDefs.append(rowDef)
            rowIdx += 1
        self.totalsRow = rowIdx

        if self.bTotalsRow:
            # fill totals row of table with empty cells
            colIdx = 0
            for colDef in self.uiColDefs:
                it1 = self.makeTableItem("", self.brushText, QtCore.Qt.AlignLeft, self.normalFont)
                self.stocksTable.setItem(self.totalsRow, colIdx, it1)
                colIdx += 1
            #Totals
            itTotLabel = self.makeTableItem("Totals", self.brushTotals, QtCore.Qt.AlignLeft, self.normalFont)
            self.stocksTable.setItem(self.totalsRow, min(self.totalProfitCol, self.totalValueCol)-1, itTotLabel)
            itTotProfitVal = self.makeTableItem("", self.brushTotals, QtCore.Qt.AlignRight, self.normalFont)
            self.stocksTable.setItem(self.totalsRow, self.totalProfitCol, itTotProfitVal)
            itTotalVal = self.makeTableItem("", self.brushTotals, QtCore.Qt.AlignRight, self.normalFont)
            self.stocksTable.setItem(self.totalsRow, self.totalValueCol, itTotalVal)

    def makeTableItem(self, txt, foreGnd, align, font):
        it1 = QtWidgets.QTableWidgetItem(txt)
        it1.setForeground(foreGnd)
        it1.setTextAlignment(align)
        it1.setFont(font)
        it1.setFlags(it1.flags() ^ (QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable))
        return it1
    
    def getOptimumTableSize(self):
        w = self.stocksTable.verticalHeader().width() + 4
        for i in range(self.stocksTable.columnCount()):
            w += self.stocksTable.columnWidth(i)
        h = self.stocksTable.horizontalHeader().height() + 4
        for i in range(self.stocksTable.rowCount()):
            h += self.stocksTable.rowHeight(i)
        return (w,h)
    
    def clearDataFlash(self):
        self.dataFlashTimerStarted = False
    
    def updateDataFlash(self, table, colDefs, rowDefs, dataFlashTimerStarted, dataFlashTimer):
        if dataFlashTimerStarted:
            if dataFlashTimer.elapsed() > self.dataFlashTimeMs:
                dataFlashTimerStarted = False
                for rowIdx in range(len(rowDefs)):
                    for colIdx in range(len(colDefs)):
                        uiCell = table.item(rowIdx, colIdx)
                        colDef = colDefs[colIdx]
                        if 'colourCode' in colDef:
                            if colDef['colourCode'] == 'FlashPosNeg':
                                uiCell.setBackground(self.brushNeutral)
                

    def updateTable(self, stockValues, exDivDates):
        
        # Flash any changed data
        self.updateDataFlash(self.stocksTable, self.uiColDefs, self.uiRowDefs, self.dataFlashTimerStarted, self.dataFlashTimer)
        
        # Update stock table values
        rowIdx = 0
        totalVal = 0
        totalProfit = 0
        for uiRowDef in self.uiRowDefs:
            stkValues = stockValues.getStockData(uiRowDef["sym"])
            if stkValues != None:
                exDivDates.addToStockInfo(uiRowDef["sym"], stkValues)
                colIdx=0
                for colDef in self.uiColDefs:
                    valChanged = False
                    uiCell = self.stocksTable.item(rowIdx, colIdx)
                    if not "price" in stkValues:
                        break;
                    stkVal = 0 if (not "price" in stkValues) else float(stkValues["price"])
                    curVal = float(stkVal) * uiRowDef["hld"] / 100.0
                    colValStr = stkValues[colDef['colValName']] if (colDef['colValName'] in stkValues) else "0"
                    if colDef['colValName'] == 'sym':
                        colStr = uiRowDef['sym']
                    elif colDef['colValName'] == 'hld':
                        colStr = '{:2,.0f}'.format(uiRowDef['hld']) if (uiRowDef['hld'] != 0) else "" 
                    elif colDef['colValName'] == 'cost':
                        colStr = (self.currencySign + '{:2,.1f}'.format(uiRowDef['cost'])) if (uiRowDef['hld'] != 0) else ""
                        colValStr = str(uiRowDef['cost'])
                    elif colDef['colValName'] == 'profit':
                        profitVal = curVal - ((uiRowDef['cost'] * uiRowDef["hld"]) / 100.0)
                        colStr = (self.currencySign + '{:2,.2f}'.format(profitVal))  if (uiRowDef['hld'] != 0) else ""
                        totalProfit += profitVal
                        colValStr = str(profitVal) if (uiRowDef['hld'] != 0) else ""
                    elif colDef['colValName'] == 'totalvalue':
                        colStr = (self.currencySign + '{:2,.2f}'.format(curVal)) if (uiRowDef['hld'] != 0) else ""
                        colValStr = str(curVal) if (uiRowDef['hld'] != 0) else ""
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
        # Handle totals if required
        if self.bTotalsRow:
            self.stocksTable.item(self.totalsRow, self.totalProfitCol).setText(self.currencySign + '{:2,.2f}'.format(totalProfit))
            self.stocksTable.item(self.totalsRow, self.totalValueCol).setText(self.currencySign + '{:2,.2f}'.format(totalVal))
        # Resize the table to fit the contents
        self.stocksTable.resizeColumnsToContents()

