# QtStockTicker — Technical Overview

## Architecture

QtStockTicker is a PySide6 (Qt 6) desktop application that displays real-time stock prices in tabular form. The architecture separates data fetching, aggregation, and presentation into distinct layers:

```
┌──────────────────────────────────────────────────────┐
│  Stock Data Providers (background threads)           │
│  Yahoo API · Interactive Brokers                    │
└────────────────────┬─────────────────────────────────┘
                     │ symbolDataChanged() callbacks
                     ▼
┌──────────────────────────────────────────────────────┐
│  StockProviderManager (central data hub)             │
│  Fallback chain · symbol routing · change tracking   │
└────────────────────┬─────────────────────────────────┘
                     │ getStockData() / getMapOfStocksChanged…()
                     ▼
┌──────────────────────────────────────────────────────┐
│  RStockTicker  (QMainWindow, main thread)            │
│  2-second QTimer drives updateStockValues()          │
└────────────────────┬─────────────────────────────────┘
                     │ updateTable()
                     ▼
┌──────────────────────────────────────────────────────┐
│  StockTable × 6   (QTableWidget subclass)            │
│  3 watch-list tables · 3 portfolio tables            │
└──────────────────────────────────────────────────────┘
```

## Source Layout

All Python source files live under `src/`:

| File | Role |
|---|---|
| `StockTicker.py` | Main window, UI setup, update timer loop |
| `StockTable.py` | QTableWidget subclass — rendering, colour coding, flash animations |
| `StockProviderManager.py` | Provider orchestration, fallback chain, change tracking |
| `StockValues_YahooAPI.py` | Yahoo Finance provider (RapidAPI HTTP) |
| `StockValues_InteractiveBrokers.py` | Interactive Brokers provider (socket API) |
| `StockValues_IB_*.py` | IB helper modules (market data client, wrapper, price getter) |
| `StockValues_Test.py` | Test provider with simulated data |
| `StockHolding.py` | Data model for a single stock position |
| `StockHoldings.py` | Collection of holdings; load/save stock list JSON |
| `StockSymbolList.py` | Symbol reference list for the stock picker dialog |
| `ExchangeRates.py` | Currency conversion via fixer.io (disabled by default) |
| `ExDivDates.py` | Dividend scraping via Selenium/headless Chrome |
| `LocalConfig.py` | Persistent local UI preferences (JSON) |
| `HostedConfigFile.py` | Remote config sync (HTTP, FTP, S3) |
| `PickStockDialog.py` | Dialog for searching/selecting stock symbols |
| `StockSettingsDialog.py` | Dialog for editing portfolio holdings |
| `ResourcePath.py` | Helper for resolving bundled resource paths |

## Threading Model

| Thread | What it does | Frequency |
|---|---|---|
| **Main (UI)** | QTimer fires `updateStockValues()` | Every 2 seconds |
| **Yahoo API** | HTTP requests to RapidAPI in batches of ≤10 symbols | ~1 s sleep between batches |
| **Interactive Brokers** | Socket streaming via IB API | Continuous |
| **ExDivDates** | Selenium scrape of dividend info | Once daily (configurable hour) |
| **Exchange Rates** | fixer.io API call | Every 10 hours (disabled by default) |

All provider threads write into their own cache and invoke a `symbolDataChanged()` callback that feeds into `StockProviderManager`.

## Data Flow

### 1. Provider Fetch

Each provider runs a background thread that fetches prices for its assigned symbols. When new data arrives, the provider calls `symbolDataChanged(symbol, data)`, which routes through to `StockProviderManager._providerSymbolChanged()`.

### 2. Central Aggregation

`StockProviderManager` stores all stock data in a shared `stockData` dict keyed by symbol. It also maintains a `_symbolsChangedSinceUIUpdate` set that records which symbols have received new data since the last UI refresh.

### 3. UI Update Cycle

Every 2 seconds the main-thread QTimer fires `RStockTicker.updateStockValues()`:

1. Check whether any symbols have changed (`checkAndSetUIUpdateDataChange()`).
2. If nothing changed, the cycle exits early (~70 % of cycles).
3. Retrieve the changed-symbol map and full stock data snapshot.
4. Enrich data with ex-dividend information (`ExDivDates.addToStockInfo()`).
5. Iterate over all 6 `StockTable` instances, calling `updateTable()` with the stock data and the set of changed symbols.

### 4. Table Rendering

`StockTable._updateTableInner()` processes each row:

- If the symbol has not changed and cached computed values exist, the cached tuple is reused.
- Otherwise it recalculates holdings value, profit, cost, etc. and stores the result in `uiRowDef['_cache']`.
- Cell text is only written when the formatted value has actually changed, avoiding unnecessary Qt paint calls.
- Colour coding applies green/red based on positive/negative values.
- Changed cells trigger a brief flash animation (400 ms fade) managed by a separate `QTimer`.
- `resizeColumnsToContents()` is called only for the first few updates after a table is populated, then throttled to avoid repeated layout recalculation.

## Provider Fallback System

The fallback chain is configured in `privatesettings/config.ini`:

```ini
STOCK_PROVIDER_FALLBACK_CHAIN=yahoo_api,interactive_brokers
```

Only providers listed in the chain are initialised. Symbols can optionally specify a preferred provider via the `stock_provider` field in the stock list JSON; otherwise they follow the chain order. When a provider fails to return valid data (null/zero price or non-zero `failCount`), the symbol is automatically reassigned to the next provider in the chain.

## UI Structure

The main window contains two `QSplitter` widgets (watch list and portfolio), each split into three `StockTable` instances. Stocks are distributed evenly across tables.

- **Watch tables** — 9 columns: Symbol, Name, Price, Change, Change %, Volume, Ex-Div Date, Dividend, Payment Date.
- **Portfolio tables** — 12 columns: adds Holding, Value, and Profit.

A totals row at the bottom of each portfolio table shows aggregated value, profit, and counts.

## Configuration

| File | Purpose |
|---|---|
| `privatesettings/config.ini` | API keys, provider fallback chain, test mode flag |
| `privatesettings/stockTickerConfig.json` | Remote config locations (HTTP/FTP/S3 endpoints for stock list sync) |
| `stocklist.json` | Stock portfolio data (symbols, holdings, costs, dividend info) |

## Building & Packaging

The app is packaged into a standalone Windows executable using PyInstaller:

```
uv venv --python 3.12
.venv\Scripts\activate
uv pip install -r requirements.txt
uv run pyinstaller StockTicker.spec --noconfirm
```

The output lands in `dist/StockTicker/`. The `_internal/` folder alongside the exe is required at runtime.

## Profiling

Run with the `--profile` flag to enable performance instrumentation:

```
python src/StockTicker.py --profile
```

This activates:
- `tracemalloc` memory tracking with periodic snapshots.
- Per-cycle and per-table timing of `updateStockValues()`.
- Diagnostic output to the log showing milliseconds per table and overall cycle time.
