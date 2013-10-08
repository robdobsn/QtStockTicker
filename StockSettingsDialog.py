from PyQt5 import QtGui, QtWidgets, QtCore
from PyQt5.QtWidgets import QTableWidget
from PickStockDialog import PickStockDialog

'''
Created on 04 Oct 2013

@author: rob dobson
'''

class StockSettingsDialog(QtWidgets.QDialog):
    updatedStockHoldings = []
    
    def __init__(self):
        super(StockSettingsDialog, self).__init__()
        self.setModal(True)

    def setContext(self, stockHoldings, uiColDefs, stockSymbolList):
        self.stockHoldings = stockHoldings
        self.uiColDefs = uiColDefs
        self.stockSymbolList = stockSymbolList
        
    def initUI(self):

        dialogFont = QtGui.QFont('SansSerif', 11)
        self.setFont(dialogFont)
        vLayout = QtWidgets.QVBoxLayout(self)
        hLayout1 = QtWidgets.QHBoxLayout()
        
        # Table for stocks
        self.colHeadStrs = ["Symbol", "", "Holding", "Cost \xA3", ""]
        self.colDefs = ["symbol", "", "holding", "cost", ""]
        self.colIsFloat = [False,False,True,True,False]
        self.table = QtWidgets.QTableWidget()
        self.table.setRowCount(self.stockHoldings.numStocks())
        self.table.setColumnCount(len(self.colHeadStrs))
        self.table.setSelectionMode(QTableWidget.SingleSelection);
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
#        self.table.setShowGrid(False)
#        self.table.setFocusPolicy(QtCore.Qt.NoFocus)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        #self.table.horizontalHeader()
        self.table.setFont(dialogFont)

#        self.table.setSortingEnabled(True)

        # Table headings
        colIdx = 0
        for colDef in self.colHeadStrs:
            hdrItem = QtWidgets.QTableWidgetItem(colDef)
            self.table.setHorizontalHeaderItem(colIdx, hdrItem)
            colIdx += 1

        # Table items
        rowIdx = 0
        stockHolding = self.stockHoldings.getStockHolding(False)
        for stk in stockHolding:
            self.createRowContent(self.table, rowIdx, stk[self.colDefs[0]], "{:.0f}".format(stk[self.colDefs[2]]), "{:.2f}".format(stk[self.colDefs[3]]))
            rowIdx += 1
#        butWidth = ic2.availableSizes(mode=QtGui.QIcon.Normal, state=QtGui.QIcon.Off)[0].width()
        self.table.setColumnWidth(1,20)
        self.table.setColumnWidth(4,20)
        self.table.setSizePolicy(QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding))
        if self.table.rowCount() > 0:
            self.table.selectRow(0)
#        self.table.resizeRowsToContents()

        hLayout1.addWidget(self.table)
        vLayoutButtons = QtWidgets.QVBoxLayout()
        
        pxa1 = QtGui.QPixmap('Add.png')
        ica1 = QtGui.QIcon(pxa1)
        bta1 = QtWidgets.QPushButton(ica1, "", self)
        bta1.setIconSize(QtCore.QSize(32,32))
        #bta1.setFlat(True)
        bta1.clicked.connect(self.addRowToStocks)
        vLayoutButtons.addWidget(bta1)

        pxa2 = QtGui.QPixmap('Up_Arrow.png')
        ica2 = QtGui.QIcon(pxa2)
        bta2 = QtWidgets.QPushButton(ica2, "", self)
        bta2.setIconSize(QtCore.QSize(32,32))
        #bta1.setFlat(True)
        bta2.clicked.connect(self.moveStockUp)
        vLayoutButtons.addWidget(bta2)

        pxa3 = QtGui.QPixmap('Down_Arrow.png')
        ica3 = QtGui.QIcon(pxa3)
        bta3 = QtWidgets.QPushButton(ica3, "", self)
        bta3.setIconSize(QtCore.QSize(32,32))
        #bta1.setFlat(True)
        bta3.clicked.connect(self.moveStockDown)
        vLayoutButtons.addWidget(bta3)

        hLayout1.addLayout(vLayoutButtons)
        vLayout.addLayout(hLayout1)
        
#        symLookup = QtWidgets.QPushButton(ic2, "Symbol Lookup", self)
#        grid.addWidget(symLookup, 1,1)
        
        hLayout2 = QtWidgets.QHBoxLayout()
        
        okButton = QtWidgets.QPushButton()
        okButton.setDefault(True)
        okButton.setText("OK")
        #okButton.setFlat(True)
        okButton.clicked.connect(self.validateDataOnOk)
        hLayout2.addWidget(okButton)
        
        cancelButton = QtWidgets.QPushButton()
        cancelButton.setText("Cancel")        
        #cancelButton.setFlat(True)
        cancelButton.clicked.connect(self.reject)
        hLayout2.addWidget(cancelButton)

        vLayout.addLayout(hLayout2)

        self.setLayout(vLayout)
        self.setWindowTitle('Edit stocks')
        self.setMinimumWidth(500)
        
        self.table.setFocus()
        #self.show()

    def createRowContent(self, table, rowIdx, symbolStr, holdingStr, costStr):
        #self.table.setRowHeight(rowIdx,20)
        #print (stk['symbol'], stk['holding'], stk['cost'])
        it1 = QtWidgets.QTableWidgetItem(symbolStr)
        table.setItem(rowIdx, 0, it1)
        ic2 = QtGui.QIcon('edit.png')
        bt2 = QtWidgets.QPushButton(ic2, "", self.table)
        bt2.setFlat(True)
        bt2.clicked.connect(self.pickStockClick)
        table.setCellWidget(rowIdx, 1, bt2)
        it3 = QtWidgets.QTableWidgetItem(holdingStr)
        it3.setTextAlignment(QtCore.Qt.AlignRight)
        table.setItem(rowIdx, 2, it3)
        it4 = QtWidgets.QTableWidgetItem(costStr)
        it4.setTextAlignment(QtCore.Qt.AlignRight)
        table.setItem(rowIdx, 3, it4)
        ic5 = QtGui.QIcon('exit.png')
        bt5 = QtWidgets.QPushButton(ic5, "", self.table)
        bt5.setFlat(True)
        bt5.clicked.connect(self.deleteStockClick)
        table.setCellWidget(rowIdx, 4, bt5)

    def pickStockClick(self, arg1):
#        print (type(arg1))
#        self.table.selectRow(3)
#        for iti in self.table.selectedItems():
#            print("Selected ", iti.text())
        curRowIdx = self.table.currentRow()
        if curRowIdx < 0:
            return
        if curRowIdx >= self.table.rowCount():
            return
        selectedSymbol = self.table.item(curRowIdx,0).text()
        picker = PickStockDialog()
        picker.setContext(selectedSymbol, self.stockSymbolList)
        picker.initUI()
        picker.exec()
        self.table.selectRow(curRowIdx)
        self.table.setFocus(True)
        if picker.selResult != "":
            self.table.item(curRowIdx,0).setText(picker.selResult)

    def deleteStockClick(self):
        curRowIdx = self.table.currentRow()
        if curRowIdx < 0:
            return
        if curRowIdx >= self.table.rowCount():
            return
        self.table.removeRow(curRowIdx)

    def addRowToStocks(self):
        curRowIdx = self.table.currentRow()
        if curRowIdx < 0:
            curRowIdx = 0
        self.table.insertRow(curRowIdx)
        self.createRowContent(self.table, curRowIdx, "","0","0.00")
        self.table.selectRow(curRowIdx)
        
    def takeRowContent(self, rowIdx):
        rowContent = []
        for colIdx in range(self.table.columnCount()):
            rowContent.append(self.table.takeItem(rowIdx, colIdx))
        return rowContent
    
    def setRowContent(self, rowIdx, rowContent):
        for colIdx in range(self.table.columnCount()):
            self.table.setItem(rowIdx, colIdx, rowContent[colIdx])
        
    def moveStockUp(self):
        if len(self.table.selectedItems()) <= 0:
            return
        curRowIdx = self.table.currentRow()
        if curRowIdx <= 0:
            return
        if curRowIdx >= self.table.rowCount():
            return
        row1 = self.takeRowContent(curRowIdx-1)
        row2 = self.takeRowContent(curRowIdx)
        self.setRowContent(curRowIdx-1, row2)
        self.setRowContent(curRowIdx, row1)
        self.table.selectRow(curRowIdx-1)
        
    def moveStockDown(self):
        if len(self.table.selectedItems()) <= 0:
            return
        curRowIdx = self.table.currentRow()
        if curRowIdx >= self.table.rowCount()-1:
            return
        row1 = self.takeRowContent(curRowIdx)
        row2 = self.takeRowContent(curRowIdx+1)
        self.setRowContent(curRowIdx, row2)
        self.setRowContent(curRowIdx+1, row1)
        self.table.selectRow(curRowIdx+1)
        
    def validateDataOnOk(self):
        self.updatedStockHoldings = []
        for rowIdx in range(self.table.rowCount()):
            newRow = {}
            for colIdx in range(len(self.colDefs)):
                if self.colDefs[colIdx] != "":
                    colText = self.table.item(rowIdx, colIdx).text()
                    colVal = 0
                    if self.colIsFloat[colIdx]:
                        try:
                            colVal = float(colText)
                        except:
                            colVal = 0
                        newRow[self.colDefs[colIdx]] = colVal
                    else:
                        newRow[self.colDefs[colIdx]] = colText
            self.updatedStockHoldings.append(newRow)
        self.accept()
        
        