# QtStockTicker
by Rob Dobson 2013, updated 2024

## Build

To build an executable:

1) Setup a virtual environment (venv)
2) Activate the venv
3) pip install -r requirements.txt
4) pyinstaller StockTicker.spec --noconfirm

The exe is in the dist folder and the _internal folder is also required to be copied to the required distribution folder

## Configuration File

This should be in the folder privatesettings of the distribution and is a file named stockTickerConfig.json

'''
{
	"FileVersion": 0,
	"ConfigLocations":
	[
	  {
	    "hostURLForGet": "<<url-for-online-or-offline-stocklist>>", "filePathForGet": "/Config/stocklist.json", "getUsing": "local",
        "hostURLForPut": "<<url-for-online-or-offline-stocklist>>", "filePathForPut": "/Config/stocklist.json", "putUsing": "local",
        "userName": "", "passWord" : "", "sourceName": "server"
	  }
	]
}
'''

The ConfigLocations section of this file is a list of configured "backup" locations for the stock list. This can be on a HTTP server for instance.

## Further information

more info at http://robdobson.com/2013/10/a-qt-stock-ticker/

![ScreenShot](https://raw.github.com/robdobsn/QtStockTicker/master/screenshots/latest.png)

## Stock Provider API Fallback System

## Overview

The StockProviderManager uses a unified fallback chain system that automatically handles provider selection, initialization, and failover. Only providers specified in the fallback chain are initialized, making the system efficient and reducing unnecessary resource usage.

## Configuration

The system is configured via the `config.ini` file in the `privatesettings` folder:

```ini
# Single unified fallback chain for all scenarios
STOCK_PROVIDER_FALLBACK_CHAIN=yahoo_api,google

# Test Mode - Use test provider only
TEST_MODE=false

# Yahoo Finance API Configuration (required for yahoo_api provider)
YAHOO_FINANCE_API_KEY=your_rapidapi_key_here
YAHOO_API_HOST=yahoo-finance15.p.rapidapi.com
```

## How It Works

### 1. Provider Initialization

Only providers listed in the fallback chain are initialized:
- If `TEST_MODE=true`, only the test provider is initialized
- Otherwise, providers are initialized in the order specified in `STOCK_PROVIDER_FALLBACK_CHAIN`
- Missing API keys or configuration will cause provider initialization to fail (logged as errors)

### 2. Stock Assignment

**Stock records without preferred provider:**
```json
{
  "symbol": "MSFT", 
  "holding": 50,
  "cost": 300.0
}
```
**Fallback order:** First provider in chain → Second provider → etc.

**Stock records with preferred provider:**
```json
{
  "symbol": "AAPL",
  "holding": 100,
  "cost": 150.0,
  "stock_provider": "yahoo_api"
}
```
**Fallback order:** `yahoo_api` → remaining providers in chain (excluding yahoo_api to avoid duplicates)

### 3. Automatic Failover

When a provider fails to return valid data for a symbol:
1. The system automatically tries the next provider in the fallback chain
2. Symbol assignment is updated to the new provider
3. Failure and recovery are logged for debugging

### 4. Data Validation

Stock data is validated before being accepted:
- Must contain a valid price (not null, not zero)
- Must have `failCount` of 0 or missing
- Invalid data triggers automatic fallover to the next provider

## Provider Types

### Available Providers
- **`yahoo_api`** - Yahoo Finance via RapidAPI (requires API key)
- **`google`** - Google Finance API 
- **`interactive_brokers`** - Interactive Brokers API
- **`test`** - Test provider with simulated data

### Provider Status
Current implementation prioritizes:
1. **Yahoo API** - Primary data source with comprehensive symbol coverage
2. **Google** - Fallback for symbols not available via Yahoo API
3. **Interactive Brokers** - Available but requires additional setup

## Configuration Examples

### Production Configuration (Yahoo Primary)
```ini
# Yahoo API first, Google as fallback
STOCK_PROVIDER_FALLBACK_CHAIN=yahoo_api,google
TEST_MODE=false
YAHOO_FINANCE_API_KEY=your_rapidapi_key_here
YAHOO_API_HOST=yahoo-finance15.p.rapidapi.com
```

### Development/Testing Configuration
```ini
# Test mode with simulated data
TEST_MODE=true
STOCK_PROVIDER_FALLBACK_CHAIN=test
```

### Multi-Provider Configuration
```ini
# All providers with Interactive Brokers primary
STOCK_PROVIDER_FALLBACK_CHAIN=interactive_brokers,yahoo_api,google
TEST_MODE=false
```

## Stock Record Format

The system supports the JSON format used in `stocklist.json`:

```json
{
  "StockInfo": [
    {
      "symbol": "ABBV",
      "holding": 0.0,
      "cost": 0.0,
      "stock_provider": "yahoo_api",
      "exDivDate": "",
      "exDivAmount": 0.0,
      "paymentDate": ""
    },
    {
      "symbol": "MSFT", 
      "holding": 50.0,
      "cost": 300.0,
      "exDivDate": "",
      "exDivAmount": 0.0,
      "paymentDate": ""
    }
  ]
}
```

**Key Features:**
- `stock_provider` field is optional
- Supports both US stocks (e.g., `ABBV`, `MSFT`) and UK stocks (e.g., `BARC.L`, `BP.L`)
- Holdings and cost tracking for portfolio management
- Dividend information tracking

## Debugging and Logging

### Debug Output Example
```
DEBUG StockProviderManager _providerSymbolChanged: Getting data from provider yahoo_api for ABBV
DEBUG StockProviderManager _isValidStockData: failCount = 0
DEBUG StockProviderManager _isValidStockData: price = 195.715
DEBUG StockProviderManager _isValidStockData: Data is valid
DEBUG StockTicker symbolDataChanged: symbolDataChanged called for symbol: ABBV
```

### Common Log Messages
- **Provider initialization:** `"Yahoo API provider initialized successfully"`
- **Symbol assignment:** `"Assigned symbol ABBV to provider yahoo_api"`
- **Data validation:** `"Got valid data for ABBV, updating cache"`
- **Failover:** `"No valid data from yahoo_api for SYMBOL, trying fallback"`

### Troubleshooting

**No data appearing in UI:**
1. Check provider initialization logs for errors
2. Verify API keys are correctly set in `config.ini`
3. Confirm symbols exist in the data source
4. Review data validation logs for failed stock data

**Provider not being used:**
1. Verify provider is listed in `STOCK_PROVIDER_FALLBACK_CHAIN`
2. Check initialization logs for provider setup errors
3. Confirm required configuration (API keys, etc.) is present

## Symbol Support

### Current Coverage
- **US Stocks:** ABBV, GWW, PG, NKE, CAT, MSFT, AAPL, etc.
- **UK Stocks:** ITV.L, BEZ.L, BARC.L, BP.L, GSK.L, etc.
- **ETFs:** VUSA.L, VUKE.L, VWRL.L, etc.

### Symbol Format
- US stocks: Standard ticker (e.g., `AAPL`, `MSFT`)
- UK stocks: Ticker with `.L` suffix (e.g., `BP.L`, `BARC.L`)
- Other markets: Follow Yahoo Finance symbol conventions

## Migration Notes

**From Previous Versions:**
- Provider-specific fallback chains are no longer used
- All configuration is now centralized in `STOCK_PROVIDER_FALLBACK_CHAIN`
- System only initializes needed providers, improving startup time
- Automatic failover is more robust with better error handling