# Dividend Data Handling

This document describes how ex-dividend dates, dividend amounts, payment dates, and earnings dates are fetched, stored, merged, and displayed in the QtStockTicker application. It is intended as a reference for replicating this functionality in another project.

---

## Overview

Dividend-related data comes from three sources, merged with a priority system:

1. **Manual holdings data** — user-entered via the settings dialog and persisted in `stocklist.json`
2. **ExDivDates web scraper** — scrapes `dividenddata.co.uk` using Selenium (currently disabled)
3. **YahooCalendarEvents API** — fetches from Yahoo Finance via RapidAPI (active, requires API key)

Lower-priority sources never overwrite values already set by higher-priority ones.

---

## Data Fields

| Field | Type | Format | Sources | Displayed |
|---|---|---|---|---|
| `exDivDate` | str | `YYYY-MM-DD` | Holdings, Scraper, API | Yes — "ExDiv" column |
| `exDivAmount` | float | 4 decimal places | Holdings, Scraper | Yes — "Amount" column (with currency prefix) |
| `paymentDate` | str | `YYYY-MM-DD` | Holdings, Scraper, API | Yes — "PayDate" column |
| `earningsDate` | str | `YYYY-MM-DD` | API only | Yes — "Earnings" column |
| `isEarningsDateEstimate` | bool | — | API only | No (metadata) |
| `earningsEstimate` | float | — | API only | No (stored for future use) |
| `exDivDataFromHoldings` | bool | — | Internal flag | No (used for colour-coding) |

---

## Data Model

### StockHolding (src/StockHolding.py)

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class StockHolding:
    symbol: str
    holding: float
    cost: float
    exDivDate: str              # "YYYY-MM-DD" or ""
    exDivAmount: float          # per-share amount in base currency, or 0
    paymentDate: str            # "YYYY-MM-DD" or ""
    stock_provider: Optional[str] = None
```

### JSON Storage (stocklist.json)

```json
{
    "StockInfo": [
        {
            "symbol": "DLAR.L",
            "holding": 100.0,
            "cost": 350.0,
            "exDivDate": "2026-03-15",
            "exDivAmount": 0.1234,
            "paymentDate": "2026-04-01"
        }
    ]
}
```

On load, `StockHoldings.loadFromStocksDataFileContents()` ensures missing dividend fields default to `""` / `0`.

---

## Source 1: YahooCalendarEvents (src/YahooCalendarEvents.py)

This is the primary active data source for dividend and earnings dates.

### API Details

- **Provider**: Yahoo Finance via RapidAPI
- **Endpoint**: `GET https://{host}/api/v1/markets/stock/modules`
- **Default host**: `yahoo-finance15.p.rapidapi.com`
- **Parameters**:
  - `ticker` — stock symbol (e.g. `AAPL`, `SHEL.L`)
  - `module` — always `"calendar-events"`
- **Headers**:
  ```
  X-RapidAPI-Key: <your_api_key>
  X-RapidAPI-Host: yahoo-finance15.p.rapidapi.com
  ```

### Configuration

Requires two config values (read from `config.ini`):

```ini
YAHOO_FINANCE_API_KEY=your_rapidapi_key_here
YAHOO_API_HOST=yahoo-finance15.p.rapidapi.com   # optional, defaults to this
```

### API Response Parsing

The response JSON has this structure (relevant fields):

```json
{
    "body": {
        "exDividendDate": { "raw": 1770595200, "fmt": "2026-02-09" },
        "dividendDate":   { "raw": 1772323200, "fmt": "2026-03-01" },
        "earnings": {
            "earningsDate": [
                { "raw": 1774742400, "fmt": "2026-03-26" }
            ],
            "isEarningsDateEstimate": true,
            "earningsAverage": { "raw": 2.35, "fmt": "2.35" }
        }
    }
}
```

Parsing logic (from `_fetch_one()`):

```python
def _fetch_one(self, symbol: str) -> dict | None:
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
        result["exDivDate"] = ex_div["fmt"]           # e.g. "2026-02-09"

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

    # EPS consensus for future use
    avg = earnings.get("earningsAverage", {})
    if isinstance(avg, dict) and "raw" in avg:
        result["earningsEstimate"] = avg["raw"]

    return result
```

### Merging into Stock Info

`addToStockInfo()` only writes fields that are not already set, so manual/scraper data takes precedence:

```python
def addToStockInfo(self, symbol: str, stkInfoDict: dict):
    with self._lock:
        cal = self._data.get(symbol)
    if cal is None:
        return

    # Only fill if not already present
    if cal.get("exDivDate") and not stkInfoDict.get("exDivDate"):
        stkInfoDict["exDivDate"] = cal["exDivDate"]
    if cal.get("paymentDate") and not stkInfoDict.get("paymentDate"):
        stkInfoDict["paymentDate"] = cal["paymentDate"]
    if cal.get("dividendRate") is not None and not stkInfoDict.get("exDivAmount"):
        stkInfoDict["exDivAmount"] = cal["dividendRate"]

    # Earnings are always set (no other source provides them)
    if cal.get("earningsDate"):
        stkInfoDict["earningsDate"] = cal["earningsDate"]
    if cal.get("isEarningsDateEstimate") is not None:
        stkInfoDict["isEarningsDateEstimate"] = cal["isEarningsDateEstimate"]
```

### Threading & Scheduling

- Runs as a daemon thread, fetching once per day at a configurable hour (default: 5 AM)
- Sleeps in 1-second increments (60 iterations) so `stop()` is responsive
- 0.5-second delay between symbol requests to respect RapidAPI rate limits
- Thread-safe access to `_data` dict via `threading.Lock`

---

## Source 2: ExDivDates Web Scraper (src/ExDivDates.py)

> **Note**: This scraper is currently disabled in `StockTicker.py` (line 116 is commented out). It targets UK LSE stocks via `dividenddata.co.uk`.

### How It Works

1. Uses Selenium with headless Chrome to load `http://www.dividenddata.co.uk`
2. Parses the HTML table using BeautifulSoup (`html5lib` parser)
3. Extracts columns: EPIC, Name, Market, SharePrice, Amount, Impact, Declared, ExDivDate, PaymentDate
4. Converts currencies to GBP using exchange rates
5. Converts short dates (`DD-MMM`) to `YYYY-MM-DD`
6. Appends `.L` suffix for FTSE stocks

### Currency Conversion

The scraper handles multiple currency symbols found in the dividend amount column:

```python
conversionRatesSymbols = {
    "C$": {"iso": "CAD", "def": 1.6},
    "$":  {"iso": "USD", "def": 1.3},
    "€":  {"iso": "EUR", "def": 1.1},
    "R":  {"iso": "ZAR", "def": 18.9},
    "p":  {"iso": "",    "def": 100},     # pence → pounds
    "£":  {"iso": "GBP", "def": 1.0},
}
```

### Date Conversion

Short dates like `15-Mar` are converted to full dates with year-rollover logic:

```python
def convertFromShortDate(self, val):
    newVal = arrow.get(val, "DD-MMM")
    newVal = newVal.replace(year=arrow.now().year)
    if newVal < arrow.now():
        newVal = newVal.shift(years=+1)
    return newVal.format("YYYY-MM-DD")
```

### Merging into Stock Info

Same pattern as YahooCalendarEvents — directly copies `exDivDate`, `exDivAmount`, `paymentDate` into the stock info dict. This scraper runs before Yahoo, so its values take precedence.

```python
def addToStockInfo(self, symbol, stkInfoDict):
    itemsToAdd = ['exDivDate', 'exDivAmount', 'paymentDate']
    self.lock.acquire()
    if symbol in self.stocksExDivInfo:
        for iti in itemsToAdd:
            if iti in self.stocksExDivInfo[symbol]:
                stkInfoDict[iti] = self.stocksExDivInfo[symbol][iti]
    self.lock.release()
```

### Loading from Holdings

The scraper also accepts pre-existing dividend data from user holdings, which takes highest priority:

```python
def setFromStockHoldings(self, stockHoldings):
    for stock in stockHoldings:
        sym = stock['symbol']
        if stock['exDivDate'] == "" or stock['exDivAmount'] == 0 or stock['paymentDate'] == "":
            continue
        exDivOnly[sym] = {
            'symbol': sym,
            'exDivDate': stock['exDivDate'],
            'exDivAmount': stock['exDivAmount'],
            'paymentDate': stock['paymentDate']
        }
    # Mark these as from holdings
    for stock in exDivOnly.values():
        newDict = {'exDivDataFromHoldings': True}
        for item in itemsToAdd:
            if item in stock:
                newDict[item] = stock[item]
        self.stocksExDivInfo[stock["symbol"]] = newDict
```

---

## Data Flow

```
                    ┌──────────────────────┐
                    │   User Holdings      │
                    │  (stocklist.json)     │
                    └──────────┬───────────┘
                               │ setFromStockHoldings()
                               ▼
┌──────────────┐    ┌──────────────────────┐    ┌─────────────────────┐
│ dividenddata │    │    ExDivDates         │    │ YahooCalendarEvents │
│   .co.uk     │───▶│  stocksExDivInfo{}   │    │    _data{}          │
│ (Selenium)   │    └──────────┬───────────┘    └──────────┬──────────┘
└──────────────┘               │                           │
                               │ addToStockInfo()          │ addToStockInfo()
                               │ (runs first)              │ (fills gaps only)
                               ▼                           ▼
                    ┌──────────────────────────────────────────────┐
                    │            stkValues dict (per symbol)       │
                    │  { exDivDate, exDivAmount, paymentDate,     │
                    │    earningsDate, isEarningsDateEstimate }    │
                    └──────────────────────┬──────────────────────┘
                                           │
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │          StockTable.updateTable()            │
                    │  Renders columns using uiColDefs             │
                    └─────────────────────────────────────────────┘
```

### Merge Order in StockTable._updateTableInner()

For each row/symbol:
1. `exDivDates.addToStockInfo(symbolName, stkValues)` — writes scraper data (overwrites)
2. `yahooCalendarEvents.addToStockInfo(symbolName, stkValues)` — fills only empty fields

Since ExDivDates also holds user-entered data (loaded via `setFromStockHoldings()`), the effective priority is:

**Manual holdings > ExDivDates scraper > YahooCalendarEvents API**

---

## UI Display

### Table Column Definitions

Dividend columns are defined in the column-def lists in `StockTicker.py`:

```python
# Portfolio view
{ 'colLbl': "ExDiv",    'colValName': "exDivDate",   'dataType': 'str',     'colourBy': 'exDivFromHoldings' },
{ 'colLbl': "Amount",   'colValName': "exDivAmount",  'dataType': 'decimal', 'fmtStr': '{:0.4f}', 'prfxStr': self.currencySign, 'onlyIfValid': 'exDivDate' },
{ 'colLbl': "PayDate",  'colValName': "paymentDate",  'dataType': 'str' },
{ 'colLbl': "Earnings", 'colValName': "earningsDate", 'dataType': 'str' },
```

Key display behaviours:
- **Amount** is only shown if `exDivDate` is present (`onlyIfValid` check)
- **Amount** is formatted to 4 decimal places with a currency prefix (`£`)
- **ExDiv** column is colour-coded based on `exDivFromHoldings` flag (marks manual data vs scraped)

### Settings Dialog

Users can edit dividend fields directly in the settings dialog (`StockSettingsDialog.py`):

```python
colHeadStrs = ["Symbol", "", "Holding", "Cost/Share (p)", "ExDivDate", "ExDivAmount", "PaymentDate", ""]
colDefs     = ["symbol", "", "holding", "cost",            "exDivDate", "exDivAmount", "paymentDate", ""]
```

---

## Initialization Sequence (StockTicker.py)

```python
# 1. Create ExDivDates (currently disabled)
self.exDivDates = ExDivDates(self.exchangeRates)
# self.exDivDates.run()   # <-- disabled

# 2. Create YahooCalendarEvents if API key is configured
yahoo_api_key = self._readConfigValue("YAHOO_FINANCE_API_KEY")
yahoo_api_host = self._readConfigValue("YAHOO_API_HOST", "yahoo-finance15.p.rapidapi.com")
self.yahooCalendarEvents = None
if yahoo_api_key:
    self.yahooCalendarEvents = YahooCalendarEvents(yahoo_api_key, yahoo_api_host)
    self.yahooCalendarEvents.setSymbols([
        s if isinstance(s, str) else s.get('symbol', '')
        for s in heldStockSymbols
    ])
    self.yahooCalendarEvents.run()
```

---

## Replication Guide

To replicate this in another project, you need:

### 1. Yahoo Finance Calendar Events Fetcher

**Dependencies**: `requests`

**Minimal implementation**:

```python
import requests

def fetch_dividend_calendar(symbol: str, api_key: str,
                            host: str = "yahoo-finance15.p.rapidapi.com") -> dict:
    """Fetch ex-dividend and earnings dates for a single symbol."""
    url = f"https://{host}/api/v1/markets/stock/modules"
    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": host,
    }
    params = {"ticker": symbol, "module": "calendar-events"}

    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    body = resp.json().get("body", {})

    result = {}

    ex_div = body.get("exDividendDate")
    if isinstance(ex_div, dict) and "fmt" in ex_div:
        result["exDivDate"] = ex_div["fmt"]

    div_date = body.get("dividendDate")
    if isinstance(div_date, dict) and "fmt" in div_date:
        result["paymentDate"] = div_date["fmt"]

    earnings = body.get("earnings", {})
    dates = earnings.get("earningsDate", [])
    if dates:
        result["earningsDate"] = dates[0].get("fmt", "")
    result["isEarningsDateEstimate"] = earnings.get("isEarningsDateEstimate")

    return result
```

### 2. Background Refresh Thread

Run once per day with rate limiting between symbols:

```python
import threading, time, datetime

class DividendFetcher:
    def __init__(self, api_key, symbols, hour_to_run=5):
        self._api_key = api_key
        self._symbols = symbols
        self._hour_to_run = hour_to_run
        self._data = {}
        self._lock = threading.Lock()
        self._running = False

    def run(self):
        self._running = True
        t = threading.Thread(target=self._worker, daemon=True)
        t.start()

    def stop(self):
        self._running = False

    def get_data(self, symbol):
        with self._lock:
            return self._data.get(symbol)

    def _worker(self):
        first_run = True
        ran_today = False
        while self._running:
            now = datetime.datetime.now()
            should_run = first_run or (now.hour == self._hour_to_run and not ran_today)
            if now.hour != self._hour_to_run:
                ran_today = False

            if should_run:
                for sym in self._symbols:
                    if not self._running:
                        break
                    try:
                        cal = fetch_dividend_calendar(sym, self._api_key)
                        with self._lock:
                            self._data[sym] = cal
                    except Exception:
                        pass
                    time.sleep(0.5)  # rate limit
                first_run = False
                ran_today = True

            for _ in range(60):
                if not self._running:
                    return
                time.sleep(1)
```

### 3. Data Merge Pattern

When building the display dict for each stock, merge sources in priority order:

```python
def merge_dividend_data(stkValues: dict, holdings_data: dict, api_data: dict):
    """Merge dividend data from multiple sources. Earlier sources take priority."""
    # Holdings data first (highest priority)
    for field in ('exDivDate', 'exDivAmount', 'paymentDate'):
        val = holdings_data.get(field)
        if val and val != "" and val != 0:
            stkValues[field] = val

    # API data fills gaps only
    if api_data:
        if api_data.get("exDivDate") and not stkValues.get("exDivDate"):
            stkValues["exDivDate"] = api_data["exDivDate"]
        if api_data.get("paymentDate") and not stkValues.get("paymentDate"):
            stkValues["paymentDate"] = api_data["paymentDate"]
        if api_data.get("earningsDate"):
            stkValues["earningsDate"] = api_data["earningsDate"]
```

### 4. RapidAPI Setup

1. Sign up at [rapidapi.com](https://rapidapi.com)
2. Subscribe to the **Yahoo Finance** API (look for `yahoo-finance15`)
3. Get your API key from the RapidAPI dashboard
4. Store it in your config as `YAHOO_FINANCE_API_KEY`

---

## Limitations & Notes

- **No per-share dividend amount from Yahoo API** — the `calendar-events` module only provides dates, not the per-share dividend amount. The `dividendRate` field in the quote response is an annual rate, not per-event.
- **Daily refresh only** — data is fetched once per day, not real-time.
- **ExDivDates scraper is UK-focused** — targets LSE stocks with appended `.L` suffixes.
- **ExDivDates scraper is currently disabled** — requires Selenium + Chrome WebDriver.
- **Rate limiting** — 0.5s delay between API requests. Adjust based on your RapidAPI plan tier.
- **Dates are strings** — stored as `YYYY-MM-DD` strings, not datetime objects.

---

## Source Files Reference

| File | Role |
|---|---|
| `src/YahooCalendarEvents.py` | Yahoo Finance API fetcher (active) |
| `src/ExDivDates.py` | dividenddata.co.uk scraper (disabled) |
| `src/StockHolding.py` | Data model with dividend fields |
| `src/StockHoldings.py` | Holdings list management, JSON load/save |
| `src/StockTicker.py` | Initialization, column definitions |
| `src/StockTable.py` | Table rendering, data merge orchestration |
| `src/StockSettingsDialog.py` | User editing of dividend fields |
| `src/ExchangeRates.py` | Currency conversion (used by ExDivDates) |
