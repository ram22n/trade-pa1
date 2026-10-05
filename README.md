# Trade PA1

An experimental intraday paper-trading project built with Python and the Alpaca API. The system downloads one-minute market bars, calculates technical indicators, evaluates trading rules, sizes positions, submits paper orders, and records trade decisions for later review.

## Important Warning

This project can submit market orders through Alpaca. Keep `ALPACA_BASE_URL` pointed at the paper-trading endpoint while developing and testing. Review the code and account state before starting the live-order script.

## Project Flow

```text
market data -> indicators -> signal -> risk checks -> order -> reports
```

Key files:

- `scripts/run_live.py`: current paper-trading program.
- `features/indicators.py`: EMA, RSI, VWAP, ATR, volume average, and Bollinger calculations.
- `logging_utils.py`: fill logging and FIFO realized P&L tracking.
- `scripts/run_backtest_pnl.py`: historical P&L simulation using the older backup strategy.
- `dashboard_streamlit.py`: Streamlit trade dashboard.

## Setup

Requires Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Add your Alpaca paper credentials to `.env`:

```env
ALPACA_KEY=your_key_here
ALPACA_SECRET=your_secret_here
ALPACA_BASE_URL=https://paper-api.alpaca.markets
```

## Useful Commands

```bash
# Verify Alpaca connectivity
python test_alpaca_account.py

# Run the backup P&L backtest
python scripts/run_backtest_pnl.py

# Run the scanner without placing orders
python scripts/run_live_cli.py

# Start the Streamlit dashboard
streamlit run dashboard_streamlit.py
```

The live-order program is intentionally not listed as a routine command. Read and verify `scripts/run_live.py` before running it.

## Private Files

The repository excludes credentials, virtual environments, generated reports, CSV files, logs, and personal documents through `.gitignore`.
