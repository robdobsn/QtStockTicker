import threading
import time
import datetime
import logging
import requests

logger = logging.getLogger("StockTickerLogger")


class YahooCalendarEvents:
    """Fetches ex-dividend dates and earnings calendar data from the Yahoo Finance API.

    Runs a background thread that refreshes data once per day (at a configurable
    hour). Each symbol requires its own API call to the ``calendar-events`` module.

    The fetched data is merged into the per-symbol stock-info dict via
    ``addToStockInfo()``, following the same pattern as ``ExDivDates``.
    """

    def __init__(self, api_key: str, api_host: str = "yahoo-finance15.p.rapidapi.com",
                 hour_to_run: int = 5):
        self._api_key = api_key
        self._api_host = api_host
        self._base_url = f"https://{api_host}"
        self._headers = {
            "X-RapidAPI-Key": api_key,
            "X-RapidAPI-Host": api_host,
        }
        self._hour_to_run = hour_to_run
        self._symbols: list[str] = []
        self._data: dict[str, dict] = {}   # symbol -> calendar info
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._first_run_done = False
        self._ran_today = False

    # ------------------------------------------------------------------
    # Public interface (same shape as ExDivDates)
    # ------------------------------------------------------------------

    def setSymbols(self, symbols: list[str]):
        """Update the list of symbols to fetch calendar data for."""
        with self._lock:
            self._symbols = list(symbols)

    def run(self):
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def addToStockInfo(self, symbol: str, stkInfoDict: dict):
        """Merge calendar-event fields into the stock-info dict used by StockTable.

        Fields written:
          exDivDate, exDivAmount (always 0 — API doesn't give per-share amount),
          paymentDate, earningsDate, isEarningsDateEstimate
        Existing values from other sources (ExDivDates scraper, holdings JSON)
        are *not* overwritten so the scraper/manual data takes precedence.
        """
        with self._lock:
            cal = self._data.get(symbol)
        if cal is None:
            return

        # Ex-dividend date — only fill if not already present
        if cal.get("exDivDate") and not stkInfoDict.get("exDivDate"):
            stkInfoDict["exDivDate"] = cal["exDivDate"]
        # Payment date
        if cal.get("paymentDate") and not stkInfoDict.get("paymentDate"):
            stkInfoDict["paymentDate"] = cal["paymentDate"]
        # Dividend amount from the quote (annual rate) — only if not already set
        if cal.get("dividendRate") is not None and not stkInfoDict.get("exDivAmount"):
            stkInfoDict["exDivAmount"] = cal["dividendRate"]

        # Earnings date — new field
        if cal.get("earningsDate"):
            stkInfoDict["earningsDate"] = cal["earningsDate"]
        if cal.get("isEarningsDateEstimate") is not None:
            stkInfoDict["isEarningsDateEstimate"] = cal["isEarningsDateEstimate"]

    # ------------------------------------------------------------------
    # Background worker
    # ------------------------------------------------------------------

    def _worker(self):
        while self._running:
            now = datetime.datetime.now()

            should_run = False
            if not self._first_run_done:
                should_run = True
            else:
                # Run once in the target hour
                if now.hour == self._hour_to_run and not self._ran_today:
                    should_run = True
                elif now.hour != self._hour_to_run:
                    self._ran_today = False

            if should_run:
                self._fetch_all()
                self._first_run_done = True
                self._ran_today = True

            # Sleep in short increments so stop() is responsive
            for _ in range(60):
                if not self._running:
                    return
                time.sleep(1)

    def _fetch_all(self):
        with self._lock:
            symbols = list(self._symbols)
        if not symbols:
            return

        logger.info(f"YahooCalendarEvents: fetching calendar data for {len(symbols)} symbols")
        fetched = 0
        failed = 0

        for symbol in symbols:
            if not self._running:
                break
            try:
                cal = self._fetch_one(symbol)
                if cal:
                    with self._lock:
                        self._data[symbol] = cal
                    fetched += 1
                else:
                    failed += 1
            except Exception as e:
                logger.debug(f"YahooCalendarEvents: error fetching {symbol}: {e}")
                failed += 1
            # Small delay between requests to respect rate limits
            time.sleep(0.5)

        logger.info(f"YahooCalendarEvents: done — {fetched} ok, {failed} failed out of {len(symbols)}")

    def _fetch_one(self, symbol: str) -> dict | None:
        """Fetch calendar-events module for a single symbol.

        Returns a flat dict with the fields we care about, or None on failure.
        """
        url = f"{self._base_url}/api/v1/markets/stock/modules"
        params = {"ticker": symbol, "module": "calendar-events"}

        resp = requests.get(url, headers=self._headers, params=params, timeout=15)
        resp.raise_for_status()
        body = resp.json().get("body", {})
        if not body:
            return None

        result: dict = {}

        # Ex-dividend date
        ex_div = body.get("exDividendDate")
        if isinstance(ex_div, dict) and "fmt" in ex_div:
            result["exDivDate"] = ex_div["fmt"]            # e.g. "2026-02-09"

        # Dividend payment date
        div_date = body.get("dividendDate")
        if isinstance(div_date, dict) and "fmt" in div_date:
            result["paymentDate"] = div_date["fmt"]

        # Earnings
        earnings = body.get("earnings", {})
        dates = earnings.get("earningsDate", [])
        if dates:
            result["earningsDate"] = dates[0].get("fmt", "")
        result["isEarningsDateEstimate"] = earnings.get("isEarningsDateEstimate")

        # Store the EPS consensus for potential future use
        avg = earnings.get("earningsAverage", {})
        if isinstance(avg, dict) and "raw" in avg:
            result["earningsEstimate"] = avg["raw"]

        # We also want the dividend rate from the quote (not in calendar-events).
        # We'll leave dividendRate as None here; StockTicker can supplement it
        # from the quote response that StockValues_YahooAPI already fetches.
        result["dividendRate"] = None

        return result
