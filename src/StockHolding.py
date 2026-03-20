from dataclasses import dataclass
from typing import Optional

@dataclass
class StockHolding:
    symbol: str
    holding: float
    cost: float
    exDivDate: str
    exDivAmount: float
    paymentDate: str
    stock_provider: Optional[str] = None  # Optional field for specifying preferred provider

@dataclass
class StocksDataFileContents:
    StockInfo: list[StockHolding]
