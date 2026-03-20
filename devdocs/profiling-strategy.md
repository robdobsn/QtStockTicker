# Performance Profiling Strategy — QtStockTicker

## Overview

This document outlines a strategy for identifying CPU and memory bottlenecks in the QtStockTicker application. The app is a PySide6 GUI with multiple background threads fetching stock data from Yahoo Finance, Interactive Brokers, and Google Finance, with a 2-second UI refresh cycle driving 6 table widgets.

---

## Architecture Summary (Profiling-Relevant)

| Component | Threading Model | Key Concern |
|-----------|----------------|-------------|
| Main UI loop (`StockTicker.py`) | QTimer every 2s on main thread | CPU time iterating 6 tables |
| `StockTable.updateTable()` | Main thread (Qt requirement) | Cell-by-cell rendering: setText, setBackground, setFont, Decimal math |
| Yahoo provider (`StockValues_YahooAPI.py`) | Dedicated background thread | Network I/O, lock contention on `self.lock` |
| IB provider (`StockValues_InteractiveBrokers.py`) | 2 background threads (event loop + request thread) | Persistent TCP, callback latency, lock contention |
| Google provider (`StockValues_Google.py`) | Dedicated background thread | Web scraping overhead |
| `HostedConfigFile.py` | Synchronous on startup | Blocks UI while fetching from FTP/HTTP/S3 |
| `ExDivDates.py` | Separate thread with Selenium | Headless Chrome startup/memory |
| `StockSymbolList.py` | Called on-demand | BeautifulSoup HTML parsing |

---

## Recommended Profiling Tools

### 1. py-spy (CPU — Zero Code Changes)

**Best for**: Getting an initial picture of where CPU time is spent without modifying any code.

```bash
pip install py-spy
# Run the app and attach:
py-spy top --pid <PID>
# Or record a flame graph:
py-spy record -o profile.svg --pid <PID>
# Or launch directly:
py-spy record -o profile.svg -- python StockTicker.py
```

**What to look for**: Which functions dominate the flame graph — expect `updateTable`, Qt paint events, and network I/O to be prominent.

### 2. cProfile (CPU — Targeted Sections)

**Best for**: Measuring specific code paths like the update cycle or startup.

```python
import cProfile
import pstats

# Wrap the update cycle:
profiler = cProfile.Profile()
profiler.enable()
self.updateStockValues()  # the 2s timer callback
profiler.disable()

stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(30)
```

Alternatively, run the whole app under cProfile to get totals:
```bash
python -m cProfile -s cumulative StockTicker.py 2>&1 | head -60
```

### 3. tracemalloc (Memory — Built-in)

**Best for**: Finding memory allocations and leaks without external dependencies.

```python
import tracemalloc
tracemalloc.start()

# ... after running for a while ...
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')
for stat in top_stats[:20]:
    print(stat)
```

Insert this at startup in `StockTicker.py` and periodically dump stats (e.g. every 60 seconds via QTimer) to see if memory grows over time.

### 4. memory_profiler (Memory — Line-Level)

**Best for**: Pinpointing exact lines that allocate the most memory.

```bash
pip install memory_profiler
```

Decorate suspect functions:
```python
from memory_profiler import profile

@profile
def updateTable(self, stockValues, exDivDates, changedStockDict, tableTotals):
    ...
```

Then run: `python -m memory_profiler StockTicker.py`

### 5. objgraph (Memory Leaks)

**Best for**: Finding reference cycles or objects that grow unboundedly.

```bash
pip install objgraph
```

```python
import objgraph
# Periodically call:
objgraph.show_growth(limit=10)  # shows which object types are increasing
```

---

## Profiling Plan — Ordered by Priority

### Phase 1: Baseline Measurement

**Goal**: Establish current CPU and memory usage patterns.

1. **Launch with py-spy** and let the app run for 5+ minutes during market hours. Capture a flame graph SVG.
2. **Record baseline memory** using `tracemalloc` snapshots at startup, 1 minute, 5 minutes, and 30 minutes. Check for steady growth.
3. **Log the update cycle time** by adding simple timing around the `updateStockValues()` method in `StockTicker.py`:
   ```python
   import time
   t0 = time.perf_counter()
   # ... existing update logic ...
   elapsed = time.perf_counter() - t0
   if elapsed > 0.05:  # log if > 50ms
       logger.warning(f"updateStockValues took {elapsed*1000:.1f}ms")
   ```

### Phase 2: Isolate UI vs Network

**Goal**: Determine whether the bottleneck is UI rendering or data fetching.

1. **Run with test provider** (`TEST_MODE=true` in config.ini) to eliminate all network I/O. Re-capture flame graph. If CPU drops significantly, the problem is network/provider-side.
2. **Run with real providers but comment out table updates** (return early from `updateTable`). If CPU drops, the problem is UI rendering.
3. **Measure lock contention**: Add timing around lock acquisitions in `StockProviderManager.py` and provider classes:
   ```python
   t0 = time.perf_counter()
   self.lock.acquire()
   wait_ms = (time.perf_counter() - t0) * 1000
   if wait_ms > 5:
       logger.warning(f"Lock wait: {wait_ms:.1f}ms")
   ```

### Phase 3: Deep-Dive into Suspects

Based on the architecture, these are the most likely bottleneck areas to investigate:

#### A. Table Rendering (`StockTable.updateTable`)

- 6 tables × N rows × M columns = many cells updated every 2 seconds
- Each cell: `item()` lookup, `setText()`, `setBackground()`, `setFont()`, Decimal conversions
- **Profile with cProfile** targeting just this method
- **Check**: Are all 6 tables being fully re-rendered even when only a few values changed? The `changedStockDict` parameter exists but verify it's actually used to skip unchanged cells.
- **Check**: Flash animation (`dataFlashTimeMs = 400`) may trigger additional paint events

#### B. Provider Thread CPU Usage

- Yahoo thread sleeps 1s between checks then processes up to 10 symbols per pass
- IB runs a persistent event loop that may spin or busy-wait
- **Profile each thread separately** using py-spy's `--threads` flag:
  ```bash
  py-spy record -o profile.svg --threads -- python StockTicker.py
  ```

#### C. Startup Blocking

- `HostedConfigFile` tries FTP, HTTP, S3, and local file sequentially — all synchronous
- A failed FTP/HTTP connection could hang for the timeout duration
- **Measure**: Time from process start to first `updateStockValues()` call

#### D. Memory: Qt Widget Objects

- 6 `QTableWidget` instances with potentially hundreds of `QTableWidgetItem` objects
- Items created via `setItem()` — check if old items are properly disposed or accumulate
- **Measure with objgraph**: Track `QTableWidgetItem` instance count over time

#### E. Memory: Stock Data Caches

- Each provider maintains its own `stockData` dict
- `StockProviderManager` maintains a merged cache
- **Check**: Are old/removed symbols cleaned up from caches?

### Phase 4: Targeted Improvements (after profiling confirms)

Only implement these if profiling data supports them:

| Suspected Issue | Likely Fix |
|----------------|-----------|
| Full table re-render every 2s | Only update cells in `changedStockDict`; skip unchanged rows entirely |
| Decimal arithmetic per cell per cycle | Cache formatted strings; only recompute on value change |
| Font recalculation on every render | Cache font objects; only recalculate on resize events |
| QBrush/color creation per cell | Already static — verify they're not recreated |
| Lock contention between providers and UI | Use `threading.RLock` or reduce critical section scope |
| Provider thread busy-waiting | Verify sleep/wait behaviour; use `threading.Event` instead of polling |
| Startup FTP/HTTP blocking | Move `HostedConfigFile` fetching to a background thread |
| Selenium for ex-div dates | Consider lightweight HTTP scraping or API if possible |
| Growing memory over time | Ensure old symbol data is cleaned up on removal; check for reference cycles |

---

## Test Configurations

Use these configurations to isolate variables during profiling:

| Config | Purpose | Settings |
|--------|---------|----------|
| **UI-only** | Profile rendering without network | `TEST_MODE=true` in config.ini |
| **Minimal stocks** | Reduce data volume | Use a stocklist.json with 2-3 symbols |
| **Maximum stocks** | Stress test | Load 50+ symbols to see scaling |
| **Single provider** | Isolate provider overhead | Set `STOCK_PROVIDER_FALLBACK_CHAIN=yahoo_api` (or `interactive_brokers`, or `google`) |
| **Fast timer** | Stress UI rendering | Temporarily change timer interval from 2000ms to 200ms |
| **Market closed** | Profile idle behaviour | Run outside market hours; verify CPU drops to near-zero |

---

## Key Metrics to Track

| Metric | Tool | Acceptable | Concerning |
|--------|------|-----------|------------|
| `updateStockValues()` duration | perf_counter | < 50ms | > 200ms |
| Per-table `updateTable()` duration | cProfile | < 10ms | > 50ms |
| Resident memory (steady state) | Task Manager / tracemalloc | < 150MB | > 300MB |
| Memory growth over 1 hour | tracemalloc snapshots | < 5MB/hr | > 20MB/hr |
| Provider lock hold time | Instrumented logging | < 5ms | > 50ms |
| Startup to first render | perf_counter | < 5s | > 15s |
| CPU at idle (market closed) | Task Manager / py-spy | < 1% | > 5% |

---

## Quick-Start Checklist

1. [ ] Install py-spy: `pip install py-spy`
2. [ ] Run `py-spy record -o profile.svg -- python StockTicker.py` for 5 minutes
3. [ ] Open `profile.svg` in browser — identify top functions
4. [ ] Add `tracemalloc` to startup, dump stats every 60s
5. [ ] Compare flame graphs: TEST_MODE vs real providers
6. [ ] Profile `updateTable()` with cProfile for cell-level breakdown
7. [ ] Check memory growth with `objgraph.show_growth()` over 30 minutes
8. [ ] Document findings and prioritise fixes by measured impact
