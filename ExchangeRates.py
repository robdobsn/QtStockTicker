import logging
import threading
import time
import copy
import requests

'''
Created on 11 Nov 2017

@author: rob dobson
'''

ENABLE_EXCHANGE_RATES = False

logger = logging.getLogger("StockTickerLogger")

class ExchangeRates:
    def __init__(self):
        self.running = False
        self.exchgRateData = {}
        self.lock = threading.Lock()
        self.FIXER_IO_API_KEY = ""

    def getExRateDataBaseGBP(self):
        dat = None
        with self.lock:
            if self.exchgRateData is not None and "rates" in self.exchgRateData:
                dat = copy.copy(self.exchgRateData["rates"])
        return dat

    def getExVsGBPByIso(self, isoCode):
        dat = None
        with self.lock:
            if self.exchgRateData is not None and "rates" in self.exchgRateData and isoCode in self.exchgRateData["rates"]:
                dat = self.exchgRateData["rates"][isoCode]
        return dat

    def start(self):
        # Read the FIXER_IO_API_KEY from a config.ini file
        self.FIXER_IO_API_KEY = ""
        try:
            with open("config.ini", "r") as f:
                for line in f:
                    if "FIXER_IO_API_KEY" in line:
                        self.FIXER_IO_API_KEY = line.split("=")[1].strip()
                        break
        except:
            logger.error("ExchangeRates: Failed to read FIXER_IO_API_KEY from config.ini")
        # Start the thread
        if ENABLE_EXCHANGE_RATES:
            self.running = True
            self.t = threading.Thread(target=self.exRateUpdateThread)
            self.t.start()

    def stop(self):
        self.running = False

    def exRateUpdateThread(self):
        firstpass = True
        while self.running:
            # Get the exchange rates
            try:
                url = 'http://data.fixer.io/api/latest?base=GBP&access_key=' + self.FIXER_IO_API_KEY
                logger.debug(f"ExchangeRates: Requesting {url}")
                r = requests.get(url)
                exRtData = r.json()
                with self.lock:
                    self.exchgRateData = exRtData
                logger.debug(f"ExchangeRates: got {exRtData}")
            except:
                logger.warn("ExchangeRates: get failed")

            # Wait for next time
            delayTime = 36000
            for delayCount in range(delayTime):
                if not self.running:
                    break
                time.sleep(1)

