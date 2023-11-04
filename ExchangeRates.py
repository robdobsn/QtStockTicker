import logging
import threading
import time
import copy
import requests

'''
Created on 11 Nov 2017

@author: rob dobson
'''

logger = logging.getLogger(__name__)

class ExchangeRates:
    def __init__(self):
        self.running = False
        self.exchgRateData = {}
        self.lock = threading.Lock()

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
                url = 'https://api.fixer.io/latest?base=GBP'
                logger.debug(f"ExchangeRates: Requesting {url}")
                r = requests.get(url)
                exRtData = r.json()
                with self.lock:
                    self.exchgRateData = exRtData
                logger.debug(f"ExchangeRates: got {exRtData}")
            except:
                logger.warn("ExchangeRates: get failed")

            # Wait for next time
            delayTime = 3600
            for delayCount in range(delayTime):
                if not self.running:
                    break
                time.sleep(1)

