#!/usr/bin/env python3
"""
Connect to IB Gateway, subscribe to one liquid symbol, print every tick type and errors.

Same env as the app: IB_HOST, IB_PORT, IB_CLIENT_ID (defaults 127.0.0.1:4001).

Usage (repo root):
  uv run python devevals/ib_market_data_probe.py
  IB_PROBE_SYMBOL=VOD IB_PROBE_EXCHANGE=LSE IB_PROBE_CURRENCY=GBP uv run python devevals/ib_market_data_probe.py

Optional:
  IB_PROBE_SECONDS=20   # how long to collect (default 15)
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from collections import Counter
from typing import Any

from ibapi.client import EClient
from ibapi.contract import Contract
from ibapi.wrapper import EWrapper

# Match StockValues_IB_PriceGetter / ib_connect_test — not failures.
_IB_INFO_STATUS_CODES = frozenset({2104, 2106, 2107, 2119, 2158})


def _tick_name(t: int) -> str:
    names = {
        1: "BID",
        2: "ASK",
        4: "LAST",
        6: "HIGH",
        7: "LOW",
        9: "CLOSE",
        14: "OPEN",
        66: "DELAYED_BID",
        67: "DELAYED_ASK",
        68: "DELAYED_LAST",
        72: "DELAYED_HIGH",
        73: "DELAYED_LOW",
        74: "DELAYED_VOLUME",
        75: "DELAYED_CLOSE",
        76: "DELAYED_OPEN",
    }
    return names.get(t, f"TYPE_{t}")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    for name in ("ibapi", "ibapi.client", "ibapi.connection", "ibapi.decoder"):
        logging.getLogger(name).setLevel(logging.WARNING)

    host = os.environ.get("IB_HOST", "127.0.0.1")
    port = int(os.environ.get("IB_PORT", "4001"))
    client_id = int(os.environ.get("IB_CLIENT_ID", "99"))
    symbol = os.environ.get("IB_PROBE_SYMBOL", "MSFT")
    exchange = os.environ.get("IB_PROBE_EXCHANGE", "SMART")
    currency = os.environ.get("IB_PROBE_CURRENCY", "USD")
    seconds = float(os.environ.get("IB_PROBE_SECONDS", "15"))

    tick_prices: list[tuple[int, float]] = []
    tick_sizes: list[tuple[int, int]] = []
    errors: list[tuple[int, int, str]] = []
    mdt: list[tuple[int, int]] = []
    counters: Counter[str] = Counter()

    class App(EWrapper, EClient):
        def __init__(self) -> None:
            EClient.__init__(self, self)
            self._api_ready = threading.Event()

        def nextValidId(self, orderId: int) -> None:
            self._api_ready.set()

        def error(self, reqId: int, errorCode: int, errorString: str) -> None:
            errors.append((reqId, errorCode, errorString))
            if errorCode in _IB_INFO_STATUS_CODES:
                counters["info_status"] += 1
                return
            counters[f"err_{errorCode}"] += 1
            EWrapper.error(self, reqId, errorCode, errorString)

        def tickPrice(self, reqId: int, tickType: int, price: float, attrib: Any) -> None:
            tick_prices.append((tickType, price))
            counters[f"tickPrice_{tickType}_{_tick_name(tickType)}"] += 1

        def tickSize(self, reqId: int, tickType: int, size: int) -> None:
            tick_sizes.append((tickType, size))
            counters[f"tickSize_{tickType}"] += 1

        def marketDataType(self, reqId: int, marketDataType: int) -> None:
            # 1=Live, 2=Frozen, 3=Delayed, 4=Delayed frozen
            mdt.append((reqId, marketDataType))
            counters[f"marketDataType_{marketDataType}"] += 1

    app = App()
    c = Contract()
    c.symbol = symbol
    c.secType = "STK"
    c.exchange = exchange
    c.currency = currency

    print(
        f"Probe: connect {host}:{port} clientId={client_id}  "
        f"contract {symbol} {exchange} {currency}  collect {seconds}s",
        flush=True,
    )
    app.connect(host, port, client_id)
    if not app.isConnected():
        print("FAIL: not connected", file=sys.stderr)
        return 1

    t = threading.Thread(target=app.run, daemon=True)
    t.start()
    if not app._api_ready.wait(timeout=15):
        print("FAIL: timeout waiting for nextValidId (session not ready)", file=sys.stderr)
        app.disconnect()
        return 1
    req_id = 10001
    app.reqMktData(req_id, c, "", False, False, [])
    print(f"reqMktData reqId={req_id} sent", flush=True)

    time.sleep(seconds)
    app.cancelMktData(req_id)
    app.disconnect()
    time.sleep(0.3)

    print("\n--- Summary ---", flush=True)
    print(f"marketDataType events: {mdt}", flush=True)
    print(f"tickPrice samples (tickType, price) last 20: {tick_prices[-20:]}", flush=True)
    print(f"tickSize samples last 10: {tick_sizes[-10:]}", flush=True)
    print(f"non-info errors: {[(e[1], e[2]) for e in errors if e[1] not in _IB_INFO_STATUS_CODES]}", flush=True)
    print("\nCounters (top):", flush=True)
    for k, v in counters.most_common(40):
        print(f"  {k}: {v}", flush=True)

    # Diagnosis for QtStockTicker (tickPrice handler + _isValidStockData needs non-zero price)
    types_seen = {t for t, _ in tick_prices}
    has_last = 4 in types_seen
    has_close = 9 in types_seen
    has_delayed = 68 in types_seen
    print("\n--- QtStockTicker hint ---", flush=True)
    if not tick_prices:
        print("No tickPrice received — check symbol/exchange, market data entitlements, or error 200 above.", flush=True)
    elif has_delayed and not has_last:
        print(
            "Only DELAYED_LAST (68) or other delayed types — StockValues_IB_PriceGetter must handle "
            "tick types 66–76. Without them, 'price' never sets and UI stays empty.",
            flush=True,
        )
    elif has_last or has_delayed:
        print("Received LAST (4) or DELAYED_LAST (68) — app maps these to 'price'.", flush=True)
    elif has_close and not has_last:
        print(
            "Session looks like outside regular trading: you got CLOSE (9) but no LAST (4). "
            "BID/ASK -1 is normal when there is no quote. "
            "QtStockTicker maps tick type 9 into 'close' and copies it to 'price' when last is absent — "
            "quotes should still validate if nothing else clears the row (e.g. error 200).",
            flush=True,
        )
    else:
        print(
            f"Tick price types seen: {sorted(types_seen)} — if 'price' stays empty in the app, "
            "check StockValues_IB_PriceGetter.tickPrice for those types.",
            flush=True,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
