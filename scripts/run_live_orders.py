# run_live_orders.py
import os, time, datetime as dt
from alpaca_trade_api import REST
from dotenv import load_dotenv

from configs.loader import load_config
from logging_utils import TradeLogger

CONFIG = load_config("live_v2.yml")
TICKERS = CONFIG["symbols"]
NOTIONAL_PER_TRADE = CONFIG["execution"]["demo_notional_per_trade"]
POLL_SEC = CONFIG["execution"]["order_poll_seconds"]

# ------------- Setup (env) --------------
load_dotenv()
API_KEY = os.getenv("ALPACA_KEY")
API_SECRET = os.getenv("ALPACA_SECRET")
BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

VERSION = CONFIG["version"]
RUN_ID = dt.datetime.utcnow().strftime("%Y%m%d-%H%M%S")

# Per-run file (separate CSV each test)
LOG_DIR = os.path.join("reports", "V2_runs", RUN_ID)
os.makedirs(LOG_DIR, exist_ok=True)
LOG_PATH = os.path.join(LOG_DIR, f"trades_{RUN_ID}.csv")

# (Optional) also keep a rolling "latest" file for quick lookups
LATEST_DIR = os.path.join("reports", "V2_runs", "latest")
os.makedirs(LATEST_DIR, exist_ok=True)
LATEST_PATH = os.path.join(LATEST_DIR, "trades_latest.csv")

rest = REST(API_KEY, API_SECRET, BASE_URL)
log_run = TradeLogger(LOG_PATH, version=VERSION, run_id=RUN_ID)
log_latest = TradeLogger(LATEST_PATH, version=VERSION, run_id=RUN_ID)

def _poll_to_terminal(client_order_id: str):
    while True:
        o = rest.get_order_by_client_order_id(client_order_id)
        if o.status in ("filled","canceled","rejected","expired","partially_filled"):
            # log to per-run and to latest
            log_run.log_fill(o)
            log_latest.log_fill(o)
            return o
        time.sleep(POLL_SEC)

def submit_buy(symbol: str, reason: str = ""):
    client_id = f"{VERSION}-{RUN_ID}-{symbol}-BUY-{int(time.time()*1000)}"
    order = rest.submit_order(
        symbol=symbol,
        side="buy",
        type="market",
        time_in_force="day",
        notional=NOTIONAL_PER_TRADE,
        client_order_id=client_id,
    )
    # stamp the "reason" by logging after poll
    o = _poll_to_terminal(client_id)
    # rewrite last line with reason (simple re-log is fine)
    o.reason = reason  # attach for logger display
    log_run.log_fill(o, reason=reason)
    log_latest.log_fill(o, reason=reason)
    return o

def submit_close(symbol: str, reason: str = "CLOSE_POSITION"):
    # Close explicit qty = current position size
    try:
        pos = rest.get_position(symbol)
        qty = abs(int(float(pos.qty)))
    except Exception:
        return None
    if qty <= 0:
        return None

    client_id = f"{VERSION}-{RUN_ID}-{symbol}-SELL-{int(time.time()*1000)}"
    order = rest.submit_order(
        symbol=symbol,
        side="sell",
        type="market",
        time_in_force="day",
        qty=qty,
        client_order_id=client_id,
    )
    o = _poll_to_terminal(client_id)
    o.reason = reason
    log_run.log_fill(o, reason=reason)
    log_latest.log_fill(o, reason=reason)
    return o

# ---------------- Example loop ----------------
# This is a skeleton; plug in your V2 signals where indicated.
if __name__ == "__main__":
    try:
        for sym in TICKERS:
            # --- your V2 entry condition here ---
            # Replace this placeholder with a real strategy reason.
            reason_str = "V2-signal"  # replace with your real reason string
            submit_buy(sym, reason=reason_str)
            time.sleep(1.5)  # placeholder delay
            submit_close(sym)  # close for demo; your logic will decide when
    finally:
        log_run.close()
        log_latest.close()
