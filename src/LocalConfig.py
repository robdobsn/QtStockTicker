import json
import logging

logger = logging.getLogger("StockTickerLogger")

class LocalConfig:
    _config = {}
    _configFileName = None

    def __init__(self, configFileName):
        self._configFileName = configFileName
        try:
            with open(configFileName, "r") as cf:
                self._config = json.loads(cf.read())
        except Exception as excp:
            logger.warn(f"LocalConfig: failed to load config from {configFileName}: {excp}")

    def getItem(self, itemName, defaultVal):
        if itemName in self._config:
            return self._config[itemName]
        return defaultVal

    def setItem(self, itemName, itemVal):
        self._config[itemName] = itemVal
        if self._configFileName is not None:
            with open(self._configFileName, "w") as cf:
                try:
                    strToWrite = json.dumps(self._config)
                    cf.write(strToWrite)
                except Exception as excp:
                    logger.warn(f"LocalConfig: write failed: {excp}")
