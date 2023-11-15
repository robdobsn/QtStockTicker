from dataclasses import dataclass

@dataclass
class StockHolding:
    symbol: str
    holding: float
    cost: float
    exDivDate: str
    exDivAmount: float
    paymentDate: str

@dataclass
class StocksDataFileContents:
    StockInfo: list[StockHolding]
