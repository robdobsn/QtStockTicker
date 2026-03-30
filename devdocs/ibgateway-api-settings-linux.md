# IB Gateway API Settings

## General

- [x] Read-Only API
- [x] TotalQuantity field may be used to transmit monetary value for BUY orders for mutual funds
- [x] Download open orders on connection
- [x] Include virtual FX positions when sending portfolio
- [x] Prepare DailyPnL when downloading positions
- [x] Send status updates for Volatility orders with "Continuous Update" flag
- Encode API messages, instrument names: **ASCII 7 (Python, Java, ...)**
- Socket port: **4001**
- [x] Use negative numbers to bind automatic orders
- [x] Create API message log file
- [ ] Include market data in API log file
- [x] Expose entire trading schedule to API
- [ ] Split Insured Deposit from Cash Balance
- [ ] Send zero positions for today's opening positions only
- [x] Use Account Groups with Allocation Methods
- Logging Level: **Error**
- Master API client ID: *(blank)*
- Timeout to send bulk data to API: **30**
- Component Exch. Separator: *(blank)*
- [x] Show Forex data in 1/10 pips
   - [x] Allow Forex trading in 1/10 pips
- [ ] Round Account values to nearest whole number
- [ ] Send market data in lots for US stocks for dual-mode API clients
- [ ] Show advanced order reject in UI always
- [ ] Reject messages above maximum allowed message rate vs applying pacing
- [x] Maintain connection upon receiving incorrectly formatted fields
- [ ] Compatibility Mode: Send ISLAND for US Stocks trading on NASDAQ
- Send instrument-specific attributes for dual-mode API client in: **instrument timezone**
- [x] Send Forex market data in compatibility mode in integer units
- Split historical data into parts with size of (in MB): **16**
- [x] Automatically report Netting Event Contract trades

## Orders

- Option exercise requests are: **editable until cutoff time (varies by clearing house)**
- [x] Allow connections from localhost only

## Trusted IPs

- 192.168.86.247
- 127.0.0.0/16
- 172.29.0.0/16
