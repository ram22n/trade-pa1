# scripts/run_backtest_pnl.py
import math
import numpy as np
import pandas as pd
import yfinance as yf
from features.indicators import add_indicators
from advisors.rules import rules_strategy

TICKERS = ["AAPL","MSFT","NVDA","SPY","QQQ"]

# Risk settings (simple)
RISK_PER_TRADE = 0.003     # 0.3% of equity risked each entry
ATR_MULT = 2.0             # stop = entry - ATR_MULT*ATR
MAX_ALLOC = 0.30           # never allocate more than 30% of equity to one ticker
HALF_SPREAD = 0.00015      # 1.5 bps each side (slippage proxy)

def run_one(ticker: str):
    df = yf.download(ticker, period="5d", interval="1m", auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    df = add_indicators(df)
    df["signal"] = df.apply(rules_strategy, axis=1)

    cash = 1.0           # start with $1 normalized equity
    shares = 0
    entry = None
    stop  = None
    equity_curve = []

    for ts, row in df.iterrows():
        px   = float(row["Close"])
        atr  = float(row["atr"]) if not np.isnan(row["atr"]) else None
        sig  = row["signal"]

        # mark-to-market equity at bar open/close
        equity = cash + (shares * px)
        equity_curve.append(equity)

        # Skip until indicators exist
        if atr is None or math.isnan(atr):
            continue

        # Check stop first (intrabar at close)
        if shares > 0 and stop is not None and px <= stop:
            # exit at stop price (simplify to close)
            cash += shares * px * (1 - HALF_SPREAD)
            shares = 0
            entry = stop = None
            continue

        # Signals
        if sig == "BUY" and shares == 0:
            # dollars we can risk & allocate
            equity = cash  # flat
            risk_dollars = equity * RISK_PER_TRADE
            stop_gap = ATR_MULT * atr
            if stop_gap <= 0:
                continue

            # shares sized by risk and capped by allocation
            max_shares_alloc = (equity * MAX_ALLOC) / px
            risk_shares = risk_dollars / stop_gap
            qty = int(max(0, min(risk_shares, max_shares_alloc)))
            if qty > 0:
                # pay spread on entry
                cost = qty * px * (1 + HALF_SPREAD)
                if cost <= cash:
                    cash -= cost
                    shares = qty
                    entry = px
                    stop = entry - stop_gap

        elif sig == "SELL" and shares > 0:
            # exit position
            cash += shares * px * (1 - HALF_SPREAD)
            shares = 0
            entry = stop = None

    # finalize
    final_equity = cash + shares * float(df["Close"].iloc[-1])
    equity_s = pd.Series(equity_curve)
    ret_total = float(final_equity - 1.0)
    rtn = equity_s.pct_change().fillna(0.0).values
    mu = rtn.mean() * 390 * 252
    sigma = rtn.std(ddof=1) * np.sqrt(390 * 252)
    sharpe = mu / sigma if sigma > 0 else 0.0
    mdd = float((equity_s / equity_s.cummax() - 1).min())

    print(f"{ticker}: return={ret_total:.2%}, sharpe={sharpe:.2f}, maxDD={mdd:.2%}")
    return {"ticker":ticker, "ret":ret_total, "sharpe":sharpe, "mdd":mdd}

def main():
    _ = [run_one(t) for t in TICKERS]

if __name__ == "__main__":
    main()
