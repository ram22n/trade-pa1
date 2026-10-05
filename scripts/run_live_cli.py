import os
import time
import datetime as dt

import pandas as pd
from dotenv import load_dotenv
from alpaca_trade_api import REST

from features.indicators import add_indicators
from advisors.rules import rules_strategy

# --- Config ---
TICKERS = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"]
LOOKBACK_MINUTES = 120     # how many recent 1-min bars to compute indicators on
SLEEP_FALLBACK = 15        # seconds to sleep on errors

# --- Setup ---
load_dotenv()
API_KEY = os.getenv("ALPACA_KEY")
API_SECRET = os.getenv("ALPACA_SECRET")
BASE_URL = os.getenv("ALPACA_BASE_URL")

def fetch_last_n_minutes(api: REST, symbol: str, n: int = LOOKBACK_MINUTES) -> pd.DataFrame | None:
    bars = api.get_bars(symbol, "1Min", limit=n, feed="iex").df
    if bars is None or bars.empty:
        return None

    if "symbol" in bars.columns:
        bars = bars[bars["symbol"] == symbol]

    try:
        bars = bars.tz_convert(None)
    except Exception:
        pass

    bars = bars.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    })

    cols = ["Open", "High", "Low", "Close", "Volume"]
    return bars[cols] if all(c in bars.columns for c in cols) else None

def main():
    api = REST(API_KEY, API_SECRET, base_url=BASE_URL)
    print("Starting live CLI. Ctrl+C to stop.")

    while True:
        try:
            clock = api.get_clock()
            if not clock.is_open:
                print("Market closed. Sleeping 60s...")
                time.sleep(60)
                continue

            for sym in TICKERS:
                df = fetch_last_n_minutes(api, sym, LOOKBACK_MINUTES)
                if df is None or len(df) < 30:
                    print(f"{sym}: not enough data yet")
                    continue

                df = add_indicators(df)
                last = df.iloc[-1]
                sig = rules_strategy(last)

                px = float(last["Close"])
                rsi = float(last["rsi"])
                emaf = float(last["ema_fast"])
                emas = float(last["ema_slow"])
                vwap = float(last["vwap"])
                ts = df.index[-1].strftime("%H:%M:%S")

                print(
                    f"[{ts}] {sym}: {sig} — px={px:.2f}, rsi={rsi:.1f}, "
                    f"ema9>ema21? {emaf>emas}, above vwap? {px>=vwap}"
                )

            now = dt.datetime.now(dt.timezone.utc)
            sleep_s = 60 - now.second
            time.sleep(max(5, min(60, sleep_s)))

        except KeyboardInterrupt:
            print("Exiting.")
            break
        except Exception as e:
            print("Error:", e)
            time.sleep(SLEEP_FALLBACK)

if __name__ == "__main__":
    main()
