# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Environment

Python 3.12 virtualenv at `.venv/`. Activate with `source .venv/Scripts/activate` (Windows) or the equivalent on Mac. Credentials are loaded from `.env` via `python-dotenv`:

```
ALPACA_KEY=...
ALPACA_SECRET=...
ALPACA_BASE_URL=https://paper-api.alpaca.markets   # or live URL
```

## Common Commands

```bash
# Verify Alpaca connectivity
python test_alpaca_account.py

# Verify yfinance data fetch
python test_yfinance.py

# Signal-count backtest (no P&L simulation)
python -m scripts.run_backtest

# Full equity-curve backtest with ATR-based position sizing
python -m scripts.run_backtest_pnl

# Live signal scanner (prints BUY/SELL/HOLD each minute, no orders)
python -m scripts.run_live_cli

# Live order execution skeleton (submits Alpaca market orders)
python -m scripts.run_live_orders

# Streamlit dashboard (reads reports/V2_runs/latest/trades_latest.csv)
streamlit run dashboard_streamlit.py

# Export yesterday's Alpaca fills to reports/
python export_alpaca_fills.py
```

## Architecture

The pipeline is: **data source → indicators → signal → action**.

### Signal Pipeline

1. **`features/indicators.py`** — `add_indicators(df)` takes an OHLCV DataFrame and returns it with EMA9/21/50, RSI14, VWAP, ATR14, 20-bar volume MA, and Bollinger Bands (20, 2σ) appended. This is the sole indicator layer; all scripts call this function.

2. **`advisors/rules.py`** — `rules_strategy(row)` applies the trading logic to a single bar: returns `"BUY"` (EMA9 > EMA21 and RSI ≥ 50), `"SELL"` (EMA9 < EMA21 or RSI > 75 or price 0.5% below VWAP), or `"HOLD"`. This is currently marked as a test-friendly relaxed version (VWAP filter removed from BUY condition).

3. **`configs/live_v2.yml` and `configs/backup_v1.yml`** — Versioned settings loaded by the Python scripts. `live_v2.yml` controls the current live bot, scanner, and dashboard. `backup_v1.yml` preserves the older backtest strategy.

### Execution Layer

- **`scripts/run_live_cli.py`** — Market hours loop. Fetches the last 120 1-min bars from Alpaca (`iex` feed), runs the indicator + signal pipeline, and prints the signal with key indicator values. No orders are placed. Sleeps until the next minute boundary.

- **`scripts/run_live_orders.py`** — Order execution skeleton around `alpaca_trade_api.REST`. `submit_buy` sends a notional market order ($2000 default) and polls until terminal status. `submit_close` reads the current position qty and sends a market sell. Both log fills via `TradeLogger`. The `__main__` loop is a placeholder; real entry/exit logic should replace it.

- **`logging_utils.py`** — `TradeLogger` writes Alpaca fill data to CSV with FIFO realized P&L tracking across a session. Two loggers are used in parallel: one per run-ID file (`reports/V2_runs/<run_id>/`) and one rolling latest file (`reports/V2_runs/latest/`).

### Backtesting

- **`scripts/run_backtest.py`** — Counts BUY/SELL bars per ticker over the last 5 days (1-min yfinance data). Quick signal sanity check only.

- **`scripts/run_backtest_pnl.py`** — Bar-by-bar equity simulation: risk-sized entries (0.3% equity per trade, ATR × 2.0 stop), 30% max allocation per ticker, 1.5 bps half-spread slippage. Reports total return, annualized Sharpe, and max drawdown per ticker.

### Dashboard

- **`dashboard_streamlit.py`** — Auto-refreshes every 2 seconds, reads the latest CSV, reconstructs buy/sell cycles with FIFO matching, and shows net P&L, win rate, equity curve, per-symbol breakdown, and recent fills.

### Stub Directories

`backtest/`, `data/`, `exec/`, `policy/`, `webapi/` are empty — placeholders for future modularization.
