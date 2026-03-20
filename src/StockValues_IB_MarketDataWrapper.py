"""
Interactive Brokers Market Data Wrapper
Separated from the main StockValues_InteractiveBrokers implementation
"""

import threading
import datetime
import pytz
import time
import logging
from ibapi.wrapper import EWrapper

logger = logging.getLogger("StockTickerLogger")

class StockValues_IB_MarketDataWrapper(EWrapper):
    """
    The wrapper deals with the action coming back from the IB gateway or TWS instance
    We override methods in EWrapper that will get called when this action happens
    """

    def __init__(self):
        pass
