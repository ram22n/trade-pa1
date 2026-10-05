import os
import time
import datetime as dt

import pandas as pd
from dotenv import load_dotenv
from alpaca_trade_api import REST

from advisors.rules import rules_strategy
from configs.loader import load_config
from features.indicators import add_indicators

CONFIG = load_config("live_v2.yml")
TICKERS = CONFIG["symbols"]
LOOKBACK_MINUTES = CONFIG["data"]["lookback_bars"]
SLEEP_FALLBACK = CONFIG["execution"]["error_sleep_seconds"]

# --- Setup ---
load_dotenv()
API_KEY = os.getenv("ALPACA_KEY")
API_SECRET = os.getenv("ALPACA_SECRET")
BASE_URL = os.getenv("ALPACA_BASE_URL")

def fetch_last_n_minutes(api: REST, symbol: str, n: int = LOOKBACK_MINUTES) -> pd.DataFrame | None:
    bars = api.get_bars(
        symbol,
        CONFIG["data"]["interval"],
        limit=n,
        feed=CONFIG["data"]["feed"],
    ).df
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
                if df is None or len(df) < CONFIG["data"]["minimum_bars"]:
                    print(f"{sym}: not enough data yet")
                    continue

                df = add_indicators(df, CONFIG["indicators"])
                df["prev_close"] = df["Close"].shift(1)
                last = df.iloc[-1]
                sig = rules_strategy(last, CONFIG["signal"])

                px = float(last["Close"])
                rsi = float(last["rsi"])
                emaf = float(last["ema_fast"])
                emas = float(last["ema_slow"])
                vwap = float(last["vwap"])
                ts = df.index[-1].strftime("%H:%M:%S")

                print(
                    f"[{ts}] {sym}: {sig} — px={px:.2f}, rsi={rsi:.1f}, "
                    f"ema{CONFIG['indicators']['ema_fast']}>"
                    f"ema{CONFIG['indicators']['ema_slow']}? {emaf>emas}, "
                    f"above vwap? {px>=vwap}"
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
