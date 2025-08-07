"""
Interactive Brokers Market Data Client
Separated from the main StockValues_InteractiveBrokers implementation
"""

import logging
from ibapi.client import EClient

logger = logging.getLogger("StockTickerLogger")

class StockValues_IB_MarketDataClient(EClient):
    """
    The client method
    We don't override native methods, but instead call them from our own wrappers
    """
    def __init__(self, wrapper):
        ## Set up with a wrapper inside
        EClient.__init__(self, wrapper)
