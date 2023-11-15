import os
from re import sub
import logging
from decimal import Decimal
from PySide6 import QtGui, QtWidgets, QtCore
from PySide6.QtCore import QElapsedTimer

from LocalConfig import LocalConfig
from StockHolding import StockHolding

'''
Created on 10 Oct 2013

@author: rob dobson
'''

# Logging
logger = logging.getLogger("StockTickerLogger")

class StockTable(QtWidgets.QTableWidget):

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
    totalsRow = -1
    totalProfitCol = 0
    totalValueCol = 0
    totalCommentCol = 0
    dataFlashTimerStarted = False
    dataFlashTimer = QElapsedTimer()
    dataFlashTimeMs = 400
    currencySign = ""
    fontsInUse = {}

    def initTable(self, parent: object, colDefs: list[dict[str,str]], currencySign: str, bTotalsRow: bool, tableId: str, localConfigFile: LocalConfig):
        self.uiColDefs = colDefs
        self.currencySign = currencySign
        self.bTotalsRow = bTotalsRow
        self.tableId = tableId
        self.localConfigFile = localConfigFile
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)

        # Table for stocks
        self.setColumnCount(len(self.uiColDefs))
        self.setShowGrid(False)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setMinimumSectionSize(2)
        colIdx = 0
        for colDef in self.uiColDefs:
            hdrItem = QtWidgets.QTableWidgetItem(colDef['colLbl'])
            if 'align' in colDef and colDef['align'] == 'right':
                hdrItem.setTextAlignment(QtCore.Qt.AlignRight)
            else:
                hdrItem.setTextAlignment(QtCore.Qt.AlignLeft)
            self.setHorizontalHeaderItem(colIdx, hdrItem)
            colIdx += 1
        palette = QtGui.QPalette()
        palette.setBrush(QtGui.QPalette.Base, self.brushBackground)
        self.setPalette(palette)

    def getDefaultFont(self, height: int, tableFontId: str):
        fontSize = 6
        weight = 50
        if height > 15:
            fontSize = 7
        if height > 22:
            fontSize = 8
        if height > 30:
            fontSize = 9
        if height > 40:
            fontSize = 10
        if tableFontId == 'large':
            fontSize += 1
        elif tableFontId == "totals":
            fontSize += 1
            weight = 75
        tmpFont = QtGui.QFont("Arial", fontSize, weight, False)
        return tmpFont.toString()

    def updateTableFonts(self):
        # Get full viewport size
        table_size = self.viewport().size()
        gw = 0  # Grid line width
        rows = self.rowCount() or 1
        cols = self.columnCount() or 1
        colWidth = (table_size.width() - (gw * (cols - 1))) / cols
        rowHeight = (table_size.height() -  (gw * (rows - 1))) / rows
        if rowHeight < 5:
            rowHeight = 5
        # logger.debug(f"numRows {rows} numCols {cols} tableWidth {table_size.width()} tableHeight {table_size.height()} colWidth {colWidth} rowHeight {rowHeight}")
        for row in range(self.rowCount()):
            self.setRowHeight(row, int(rowHeight))
            for col in range(self.columnCount()):
                if 'fontSize' in self.uiColDefs[col] and self.uiColDefs[col]['fontSize'] == 'large':
                    tableFontId = "large"
                elif row == self.totalsRow:
                    tableFontId = "totals"
                else:
                    tableFontId = "normal"
                fontStr = self.localConfigFile.getItem("table_"+self.tableId+"_"+tableFontId, self.getDefaultFont(int(rowHeight), tableFontId))
                fontToUse = QtGui.QFont()
                fontToUse.fromString(fontStr)
                self.item(row, col).setFont(fontToUse)
                self.fontsInUse[tableFontId] = fontStr

    def resizeTableCells(self):
        self.updateTableFonts()

    def getFontStr(self, tableFontId: str):
        if tableFontId in self.fontsInUse:
            return self.fontsInUse[tableFontId]
        return ""

    def setFontStr(self, tableFontId: str, newFontStr: str):
        self.localConfigFile.setItem("table_"+self.tableId+"_"+tableFontId, newFontStr)
        self.updateTableFonts()

    def populateTable(self, stockHolding: list[StockHolding]):
        
        # Stock items table
        self.uiRowDefs = []
        totalRowsInTable = len(stockHolding) + (1 if self.bTotalsRow else 0)
        self.setRowCount(totalRowsInTable)
        rowIdx = 0
        for stk in stockHolding:
            self.setRowHeight(rowIdx,15)
            colIdx = 0
            for colDef in self.uiColDefs:
                if colDef['colValName'] == 'profit':
                    self.totalProfitCol = colIdx
                elif colDef['colValName'] == 'totalvalue':
                    self.totalValueCol = colIdx
                elif colDef['colValName'] == 'volume':
                    self.totalCommentCol = colIdx
                it1 = self.makeTableItem("", self.brushText, QtCore.Qt.AlignRight if ('align' in colDef and colDef['align'] == 'right') else QtCore.Qt.AlignLeft)
                self.setItem(rowIdx, colIdx, it1)
                colIdx += 1
            rowDef = { 'sym':stk['symbol'], 'hld':stk['holding'], 'cost':stk['cost'] }
            self.uiRowDefs.append(rowDef)
            rowIdx += 1
        self.totalsRow = rowIdx

        if self.bTotalsRow:
            # fill totals row of table with empty cells
            colIdx = 0
            for colDef in self.uiColDefs:
                it1 = self.makeTableItem("", self.brushText, QtCore.Qt.AlignLeft)
                self.setItem(self.totalsRow, colIdx, it1)
                colIdx += 1
            #Totals
            itTotLabel = self.makeTableItem("Totals", self.brushTotals, QtCore.Qt.AlignLeft)
            self.setItem(self.totalsRow, min(self.totalProfitCol, self.totalValueCol)-1, itTotLabel)
            itTotProfitVal = self.makeTableItem("", self.brushTotals, QtCore.Qt.AlignRight)
            self.setItem(self.totalsRow, self.totalProfitCol, itTotProfitVal)
            itTotalVal = self.makeTableItem("", self.brushTotals, QtCore.Qt.AlignRight)
            self.setItem(self.totalsRow, self.totalValueCol, itTotalVal)
            itTotalComment = self.makeTableItem("", self.brushTotals, QtCore.Qt.AlignRight)
            self.setItem(self.totalsRow, self.totalCommentCol, itTotalComment)

    def makeTableItem(self, txt, foreGnd, align):
        it1 = QtWidgets.QTableWidgetItem(txt)
        it1.setForeground(foreGnd)
        it1.setTextAlignment(align)
        it1.setFlags(it1.flags() ^ (QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEditable))
        return it1
    
    def getOptimumTableSize(self):
        w = self.verticalHeader().width() + 4
        for i in range(self.columnCount()):
            w += self.columnWidth(i)
        h = self.horizontalHeader().height() + 4
        for i in range(self.rowCount()):
            h += self.rowHeight(i)
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

    def updateFlash(self):
        # Flash any changed data
        self.updateDataFlash(self, self.uiColDefs, self.uiRowDefs, self.dataFlashTimerStarted, self.dataFlashTimer)

    def updateTable(self, stockValues, exDivDates, changedStockDict, tableTotals):
        # Update stock table values
        totalVal = self.ToDecimal("0.00")
        totalProfit = self.ToDecimal("0.00")
        rowsWithTotalValue = 0
        debugTotals = []
        # Iterate rows
        for rowIdx in range(len(self.uiRowDefs)):
            uiRowDef = self.uiRowDefs[rowIdx]
            symbolName = uiRowDef['sym']
            stkValues = stockValues.getStockData(symbolName)
            if stkValues is not None:
                exDivDates.addToStockInfo(symbolName, stkValues)
                if not "price" in stkValues:
                    continue
                # Get information on stock
                stkHolding = self.ToDecimal(uiRowDef["hld"])
                stkPricePence = self.ToDecimal(stkValues["price"])
                stkCurValue = (stkPricePence * stkHolding) / self.ToDecimal("100")
                stkCostPerSharePence = self.ToDecimal(uiRowDef['cost'])
                stkOrigCost = (stkCostPerSharePence * stkHolding) / self.ToDecimal("100")
                stkCurProfit = stkCurValue - stkOrigCost
                # Make calculations
                totalProfit += stkCurProfit
                totalVal += stkCurValue
                rowsWithTotalValue += 1
                # Check if anything has changed with this stock
                if changedStockDict is None or symbolName in changedStockDict:
                    # Iterate columns to fill table
                    for colIdx in range(len(self.uiColDefs)):
                        colDef = self.uiColDefs[colIdx]
                        colValName = colDef['colValName']
                        uiCell = self.item(rowIdx, colIdx)
                        cellNewText = ""
                        cellValue = self.ToDecimal(0)
                        if colDef['dataType'] == 'decimal':
                            if colValName == 'hld':
                                cellValue = stkHolding
                            elif colValName == 'cost':
                                cellValue = stkCostPerSharePence
                            elif colValName == 'profit':
                                cellValue = stkCurProfit
                            elif colValName == 'totalvalue':
                                cellValue = stkCurValue
                                debugTotals.append((rowIdx, cellValue, totalVal))  # debug
                            else:
                                if colValName in stkValues:
                                    cellValue = self.ToDecimal(stkValues[colValName])
                            # Format the value
                            cellNewText += colDef['fmtStr'].format(cellValue) if ('fmtStr' in colDef and colDef['fmtStr'] != "") else "{0:.0f}".format(cellValue)
                        else: # must be string
                            if colValName == 'sym':
                                cellNewText = symbolName
                            else:
                                cellNewText = str(stkValues[colDef['colValName']]) if (colDef['colValName'] in stkValues) else ""
                        txtPrefix = colDef['prfxStr'] if 'prfxStr' in colDef else ""
                        txtSuffix = colDef['pstfxStr'] if ('pstfxStr' in colDef) else ""
                        cellNewText = txtPrefix + cellNewText + txtSuffix
                        # Check for changes
                        valChanged = (uiCell.text() != cellNewText)
                        # Handle colour coding
                        if 'colourCode' in colDef:
                            if colDef['colourCode'] == 'PosNeg' or colDef['colourCode'] == 'PosBad' or ((colDef['colourCode'] == 'FlashPosNeg') and valChanged):
                                colourByVal = cellValue
                                if 'colourBy' in colDef:
                                    if colDef['colourBy'] == 'change':
                                        curCellVal = 0
                                        try:
                                            curCellVal = self.ToDecimal(float(uiCell.text()))
                                        except:
                                            curCellVal = 0
                                        colourByVal = colourByVal - curCellVal
                                    elif colDef['colourBy'] == 'exDivFromHoldings':
                                        colourByVal = -1
                                elif 'colourByCol' in colDef:
                                    colToColourBy = colDef['colourByCol']
                                    if colToColourBy in stkValues:
                                        colourByVal = stkValues[colToColourBy]
                                valToColourBy = 0
                                try:
                                    valToColourBy = float(colourByVal)
                                except:
                                    valToColourBy = 0
                                if valToColourBy > 0:
                                    if 'colourCode' in colDef and colDef['colourCode'] == 'PosBad':
                                        uiCell.setBackground(self.brushRed)
                                    else:
                                        uiCell.setBackground(self.brushGreen)
                                elif valToColourBy < 0:
                                    if 'colourCode' in colDef and colDef['colourCode'] == 'PosBad':
                                        uiCell.setBackground(self.brushGreen)
                                    else:
                                        uiCell.setBackground(self.brushRed)
                                else:
                                    uiCell.setBackground(self.brushNeutral)
                            if (colDef['colourCode'] == 'FlashPosNeg') and valChanged:
                                self.dataFlashTimerStarted = True
                                self.dataFlashTimer.start()
                        # Handle display validity
                        bShowValue = True
                        if 'onlyIfValid' in colDef:
                            bShowValue = False
                            if colDef['onlyIfValid'] in stkValues:
                                if stkValues[colDef['onlyIfValid']] != "":
                                    bShowValue = True
                        if bShowValue:
                            uiCell.setText(cellNewText)
            else: # stkValues is None
                symbolName = uiRowDef['sym']
                for colIdx in range(len(self.uiColDefs)):
                    colDef = self.uiColDefs[colIdx]
                    if colDef['colValName'] == "sym":
                        uiCell = self.item(rowIdx, colIdx)
                        uiCell.setText(symbolName)
                        break

        # Resize the table to fit the contents
        self.resizeColumnsToContents()
#        self.CrossCheckValues()
        # return totals
        tableTotals[0] += totalVal
        tableTotals[1] += totalProfit
        tableTotals[2] += rowsWithTotalValue
        tableTotals[3] += len(self.uiRowDefs)
        return tableTotals

    def SetTotals(self, tableTotals):
        # Handle totals if required
        if self.bTotalsRow:
            self.item(self.totalsRow, self.totalProfitCol).setText(self.currencySign + '{:2,.2f}'.format(tableTotals[1]))
            self.item(self.totalsRow, self.totalValueCol).setText(self.currencySign + '{:2,.2f}'.format(tableTotals[0]))
            if tableTotals[2] == tableTotals[3]:
                uiCell = self.item(self.totalsRow, self.totalCommentCol)
                uiCell.setText("")
                uiCell.setBackground(self.brushNeutral)
            else:
                uiCell = self.item(self.totalsRow, self.totalCommentCol)
                uiCell.setText("Missing Values")
                uiCell.setBackground(self.brushRed)

    def ToDecimal(self, value):
        try:
            if type(value) is str:
                mult = 1
                if "M" in value:
                    value = value.replace("M","")
                    mult = 1000000
                outVal = Decimal(value.replace(",", "")) * mult
            else:
                outVal = Decimal(value)
            return outVal
        except:
            return Decimal("0")

    def CrossCheckValues(self):

        # Cross-check values
        if self.bTotalsRow:
            sum = 0
            chkValues = []
            rowIdx = 0
            for uiRowDef in self.uiRowDefs:
                colIdx=0
                valueText = ""
                symText = ""
                for colDef in self.uiColDefs:
                    uiCell = self.item(rowIdx, colIdx)
                    if colDef['colValName'] == 'totalvalue':
                        valueText = uiCell.text()
                    elif colDef['colValName'] == 'sym':
                        symText = uiCell.text()
                    colIdx += 1
                val = self.ToDecimal(sub(r'[^\d\-.]', '', valueText))
                sum += val
                chkValues.append((symText, valueText, val, sum))
                rowIdx += 1

            sumFromTab = self.item(self.totalsRow, self.totalValueCol).text()
            sumCheck = self.ToDecimal(sub(r'[^\d\-.]', '', sumFromTab))
            sumDiff = abs(sumCheck - sum)
            if sumDiff > 1:
                pubFolder = os.path.expanduser('~Public\Documents')
                f = open(pubFolder + "\\qtstktickdebug.txt", 'w+')
                f.write("VALUES DON'T ADD UP" + " ColTotal = " + str(sum) + " != TotCell = " + str(sumCheck) + " sumFromTab " + sumFromTab + "\n")
                for elIdx in range(len(chkValues)):
                    for li in chkValues[elIdx]:
                        f.write(str(li) + "\t")
                    f.write("\n")
                f.write("\n")
                f.close()
                self.item(self.totalsRow, self.totalValueCol).setBackground(self.brushRed)
            else:
                self.item(self.totalsRow, self.totalValueCol).setBackground(self.brushNeutral)





