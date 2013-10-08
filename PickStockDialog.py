from PyQt5 import QtGui, QtWidgets, QtCore
from PyQt5.QtWidgets import QTableWidget

'''
Created on 04 Oct 2013

@author: rob dobson
'''

class PickStockDialog(QtWidgets.QDialog):
    selResult = ""
    
    def __init__(self):
        super(PickStockDialog, self).__init__()
        self.setModal(True)

    def setContext(self, curstock, stockSymbolList):
        self.curstock = curstock
        self.stockSymbolList = stockSymbolList
        
    def initUI(self):

        dialogFont = QtGui.QFont('SansSerif', 11)
        grid = QtWidgets.QHBoxLayout(self)
        self.selResult = ""

        # Table for stocks
        colDefs = ["Symbol", "Name"]
        self.table = QtWidgets.QTableWidget()
        self.table.setRowCount(self.stockSymbolList.getNumStocks())
        self.table.setColumnCount(len(colDefs))
        self.table.setSelectionMode(QTableWidget.SingleSelection);
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)
#        self.table.setFocusPolicy(QtCore.Qt.NoFocus)
        self.table.horizontalHeader().setStretchLastSection(True)
#        self.table.horizontalHeader().setVisible(False)

        # Table headings
        colIdx = 0
        for colDef in colDefs:
            hdrItem = QtWidgets.QTableWidgetItem(colDef)
            hdrItem.setFont(dialogFont)
            self.table.setHorizontalHeaderItem(colIdx, hdrItem)
            colIdx += 1

        # Table items
        rowIdx = 0
        for stk in self.stockSymbolList.getStockList():
            #self.table.setRowHeight(rowIdx,20)
            # print (stk[0], stk[1])
            it1 = QtWidgets.QTableWidgetItem(stk[1])
            it1.setFlags(it1.flags() ^ QtCore.Qt.ItemIsEditable)
            it1.setFont(dialogFont)
            self.table.setItem(rowIdx, 0, it1)
            it2 = QtWidgets.QTableWidgetItem(stk[0])
            it2.setFlags(it2.flags() ^ QtCore.Qt.ItemIsEditable)
            it2.setFont(dialogFont)
            self.table.setItem(rowIdx, 1, it2)
            rowIdx += 1
        self.table.setSizePolicy(QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding))

        # Move to the currently used stock if it exists
        for rowIdx in range(self.table.rowCount()):
            if (self.table.item(rowIdx, 0).text() == self.curstock):
                self.table.selectRow(rowIdx)
                self.table.scrollToItem(self.table.item(rowIdx,0))
                break
            
        self.table.clicked.connect(self.stockSelected)
        grid.addWidget(self.table,1)
        
        self.setLayout(grid)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool)
        self.setWindowTitle('Pick Stock')
        self.setMinimumWidth(400)
        
    def stockSelected(self):
        if len(self.table.selectedItems()) <= 0:
            return
        self.selResult = self.table.selectedItems()[0].text()
        self.setResult(QtWidgets.QDialog.Rejected)
        self.close()
        