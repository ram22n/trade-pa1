import os
import time
import math
import datetime as dt
import csv

import pytz
import pandas as pd
from dotenv import load_dotenv
from alpaca_trade_api import REST

from features.indicators import add_indicators
from logging_utils import TradeLogger

# --- Config ---
TICKERS = [
    "SPY", "QQQ", "DIA", "IWM",
    "XLK", "XLF", "XLV", "XLI", "XLP", "XLU", "XLE", "XLY",
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "JPM", "COST",
]
LOOKBACK_MINUTES = 390
RISK_PER_TRADE   = 0.003   # 0.3% equity risked per entry
ATR_MULT         = 2.5     # stop = entry - ATR_MULT * ATR
MAX_ALLOC        = 0.03    # max 3% equity in one ticker
SESSION_START    = dt.time(9, 35)
CUT_OFF_ENTRIES  = dt.time(15, 15)  # stop opening new positions
CLOSE_ALL_BY     = dt.time(15, 45)  # stop new entries + close everything
ET               = pytz.timezone("US/Eastern")
POLL_SEC         = 0.7
SLEEP_FALLBACK   = 15
MAX_OPEN_POSITIONS = 5
EMA_FAST_LEN     = 12
EMA_SLOW_LEN     = 26
BUY_RSI_MIN      = 55
SELL_RSI_MAX     = 75
VWAP_SELL_MULT   = 0.995
MIN_PRICE        = 20.0
MIN_ATR_PCT      = 0.0005
MAX_ATR_PCT      = 0.01
TECH_TICKERS     = {"QQQ", "XLK", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META"}

VERSION = "v2"
load_dotenv()
API_KEY    = os.getenv("ALPACA_KEY")
API_SECRET = os.getenv("ALPACA_SECRET")
BASE_URL   = os.getenv("ALPACA_BASE_URL")

RUN_ID      = dt.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
LOG_DIR     = os.path.join("reports", "V2_runs", RUN_ID)
LATEST_DIR  = os.path.join("reports", "V2_runs", "latest")
os.makedirs(LOG_DIR,    exist_ok=True)
os.makedirs(LATEST_DIR, exist_ok=True)
LOG_PATH    = os.path.join(LOG_DIR,    f"trades_{RUN_ID}.csv")
LATEST_PATH = os.path.join(LATEST_DIR, "trades_latest.csv")
DECISION_PATH = os.path.join(LOG_DIR, f"decisions_{RUN_ID}.csv")
REVIEW_PATH = os.path.join(LOG_DIR, f"daily_review_{RUN_ID}.md")

DECISION_HEADERS = [
    "ts_utc", "bar_ts", "run_id", "symbol", "decision", "signal",
    "price", "ema_fast", "ema_slow", "ema_50", "rsi", "vwap", "atr",
    "atr_pct", "volume", "vol_ma20", "market_ok", "spy_ok", "qqq_ok",
    "entry_allowed", "open_positions", "position_qty", "stop", "order_qty",
    "reason",
]


def session_start_iso() -> str:
    today_et = dt.datetime.now(ET).date()
    start_et = ET.localize(dt.datetime.combine(today_et, dt.time(9, 30)))
    return start_et.astimezone(dt.timezone.utc).isoformat()


def fetch_bars(api: REST, symbol: str, n: int = LOOKBACK_MINUTES) -> pd.DataFrame | None:
    try:
        bars = api.get_bars(symbol, "1Min", start=session_start_iso(), limit=n, feed="iex").df
    except Exception as e:
        print(f"  {symbol}: bar fetch error - {e}")
        return None
    if bars is None or bars.empty:
        return None
    if "symbol" in bars.columns:
        bars = bars[bars["symbol"] == symbol]
    try:
        bars = bars.tz_convert(None)
    except Exception:
        pass
    bars = bars.rename(columns={"open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"})
    cols = ["Open", "High", "Low", "Close", "Volume"]
    return bars[cols] if all(c in bars.columns for c in cols) else None


def prepare_live_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = add_indicators(df)
    df["ema_fast"] = df["Close"].ewm(span=EMA_FAST_LEN, adjust=False).mean()
    df["ema_slow"] = df["Close"].ewm(span=EMA_SLOW_LEN, adjust=False).mean()
    df["prev_close"] = df["Close"].shift(1)
    return df


def live_rules_strategy(row):
    if (
        row["ema_fast"] > row["ema_slow"]
        and row["rsi"] >= BUY_RSI_MIN
        and row["Close"] > row["ema_50"]
        and row["Volume"] > row["vol_ma20"]
    ):
        return "BUY"
    if (
        row["ema_fast"] < row["ema_slow"]
        or (row["rsi"] > SELL_RSI_MAX and row["Close"] < row["prev_close"])
        or row["Close"] < row["vwap"] * VWAP_SELL_MULT
    ):
        return "SELL"
    return "HOLD"


def is_market_healthy(rows: dict[str, pd.Series]) -> tuple[bool, bool, bool]:
    spy = rows.get("SPY")
    qqq = rows.get("QQQ")
    spy_ok = bool(
        spy is not None
        and spy["ema_fast"] > spy["ema_slow"]
        and spy["Close"] > spy["ema_50"]
        and spy["rsi"] >= 50
    )
    qqq_ok = bool(
        qqq is not None
        and qqq["ema_fast"] > qqq["ema_slow"]
        and qqq["Close"] > qqq["ema_50"]
        and qqq["rsi"] >= 50
    )
    return spy_ok, qqq_ok, spy_ok or qqq_ok


def entry_market_ok(symbol: str, spy_ok: bool, qqq_ok: bool) -> bool:
    if symbol in TECH_TICKERS:
        return spy_ok and qqq_ok
    return spy_ok


def get_equity(api: REST) -> float:
    return float(api.get_account().equity)


def append_csv(path: str, headers: list[str], row: dict):
    new_file = not os.path.exists(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        if new_file:
            writer.writeheader()
        writer.writerow({h: row.get(h, "") for h in headers})


def log_decision(row: dict):
    append_csv(DECISION_PATH, DECISION_HEADERS, row)


def write_daily_review():
    lines = [
        f"# Daily Review {RUN_ID}",
        "",
        f"- Generated UTC: {dt.datetime.now(dt.timezone.utc).isoformat()}",
        f"- Trade log: {LOG_PATH}",
        f"- Decision journal: {DECISION_PATH}",
        "",
    ]

    if os.path.exists(LOG_PATH):
        fills = pd.read_csv(LOG_PATH)
        if not fills.empty:
            filled = fills[fills["status"].astype(str).str.lower() == "filled"].copy()
            buys = int((filled["side"].astype(str).str.upper() == "BUY").sum())
            sells = int((filled["side"].astype(str).str.upper() == "SELL").sum())
            pnl = pd.to_numeric(filled.get("realized_pnl", pd.Series(dtype=float)), errors="coerce").fillna(0)
            lines += [
                "## Fills",
                "",
                f"- Filled buys: {buys}",
                f"- Filled sells: {sells}",
                f"- Realized P&L from logged sells: ${pnl.sum():.2f}",
                "",
            ]
            if "symbol" in filled.columns:
                by_symbol = (
                    filled.assign(realized_pnl_num=pnl)
                    .groupby("symbol")["realized_pnl_num"]
                    .sum()
                    .sort_values(ascending=False)
                )
                lines += ["## P&L By Symbol", ""]
                for sym, value in by_symbol.items():
                    lines.append(f"- {sym}: ${value:.2f}")
                lines.append("")
        else:
            lines += ["## Fills", "", "- No fills recorded.", ""]
    else:
        lines += ["## Fills", "", "- Trade log was not created.", ""]

    if os.path.exists(DECISION_PATH):
        decisions = pd.read_csv(DECISION_PATH)
        if not decisions.empty:
            lines += [
                "## Decision Counts",
                "",
            ]
            for decision, count in decisions["decision"].value_counts().items():
                lines.append(f"- {decision}: {int(count)}")
            lines.append("")

            lines += ["## Top Decision Reasons", ""]
            for reason, count in decisions["reason"].value_counts().head(12).items():
                lines.append(f"- {int(count)}x {reason}")
            lines.append("")
    else:
        lines += ["## Decisions", "", "- Decision journal was not created.", ""]

    lines += [
        "## Review Questions",
        "",
        "- Which symbols repeatedly triggered BUY but failed quickly?",
        "- Which SELL reason caused the largest losses?",
        "- Did the volume filter block many trades or only weak ones?",
        "- Did the market filter keep the bot out during broad market weakness?",
        "- Were stops too tight or too wide compared with normal ATR?",
        "",
    ]

    with open(REVIEW_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Daily review written to {REVIEW_PATH}")


def poll_fill(api: REST, client_id: str, log_run: TradeLogger, log_latest: TradeLogger, reason: str = ""):
    started = time.monotonic()
    next_status_report = 60
    while True:
        o = api.get_order_by_client_order_id(client_id)
        if o.status in ("filled", "canceled", "rejected", "expired"):
            log_run.log_fill(o, reason=reason)
            log_latest.log_fill(o, reason=reason)
            return o
        elapsed = time.monotonic() - started
        if elapsed >= next_status_report:
            print(f"  Waiting on order {client_id}: status={o.status} filled={o.filled_qty or 0}")
            next_status_report += 60
        time.sleep(POLL_SEC)


def submit_buy(api, sym, qty, reason, log_run, log_latest):
    cid = f"{VERSION}-{RUN_ID}-{sym}-BUY-{int(time.time()*1000)}"
    api.submit_order(symbol=sym, side="buy", type="market",
                     time_in_force="day", qty=qty, client_order_id=cid)
    return poll_fill(api, cid, log_run, log_latest, reason)


def submit_sell(api, sym, qty, reason, log_run, log_latest):
    cid = f"{VERSION}-{RUN_ID}-{sym}-SELL-{int(time.time()*1000)}"
    api.submit_order(symbol=sym, side="sell", type="market",
                     time_in_force="day", qty=qty, client_order_id=cid)
    return poll_fill(api, cid, log_run, log_latest, reason)


def init_state_from_alpaca(api: REST, tickers: list, loggers: list[TradeLogger] | None = None) -> dict:
    """Seed in-memory position state from live Alpaca positions at startup."""
    state = {sym: {"qty": 0, "entry_px": None, "stop": None} for sym in tickers}
    try:
        for pos in api.list_positions():
            sym = pos.symbol
            if sym in state:
                qty = int(float(pos.qty))
                entry_px = float(pos.avg_entry_price)
                # Can't recover the original ATR stop; set a conservative 2% trailing stop
                stop = entry_px * 0.98
                state[sym] = {"qty": qty, "entry_px": entry_px, "stop": stop}
                for logger in loggers or []:
                    logger.seed_position(sym, qty, entry_px)
                print(f"  Existing position: {sym} qty={qty} entry={entry_px:.2f} stop={stop:.2f} (2% fallback)")
    except Exception as e:
        print(f"  Could not load existing positions: {e}")
    return state


def close_all(api, state, log_run, log_latest):
    live_qty = {}
    try:
        for pos in api.list_positions():
            if pos.symbol in state:
                live_qty[pos.symbol] = int(float(pos.qty))
    except Exception as e:
        print(f"  Could not refresh live positions before close-all: {e}")

    for sym, pos in list(state.items()):
        qty = abs(live_qty.get(sym, pos["qty"]))
        if qty > 0:
            print(f"  Closing {sym} qty={qty}")
            try:
                submit_sell(api, sym, qty, "SESSION_END", log_run, log_latest)
            except Exception as e:
                print(f"  Failed to close {sym}: {e}")
        state[sym] = {"qty": 0, "entry_px": None, "stop": None}


def main():
    api        = REST(API_KEY, API_SECRET, base_url=BASE_URL)
    log_run    = TradeLogger(LOG_PATH,    version=VERSION, run_id=RUN_ID)
    log_latest = TradeLogger(LATEST_PATH, version=VERSION, run_id=RUN_ID)

    print(f"=== Live Trading  run_id={RUN_ID} ===")
    print(f"Tickers : {TICKERS}")
    print(f"Session : {SESSION_START} - {CLOSE_ALL_BY} ET (no new entries after {CUT_OFF_ENTRIES})")
    print(f"Risk    : {RISK_PER_TRADE*100:.1f}% equity/trade  ATRx{ATR_MULT} stop  max {MAX_ALLOC*100:.0f}% alloc")
    print(f"Filters : EMA{EMA_FAST_LEN}>{EMA_SLOW_LEN}, RSI>={BUY_RSI_MIN}, Close>EMA50, Volume>VolMA20, market trend on")
    print(f"Logs    : {LOG_PATH}")
    print(f"Notes   : {DECISION_PATH}")

    state = init_state_from_alpaca(api, TICKERS, loggers=[log_run, log_latest])
    review_written = False

    try:
        while True:
            try:
                clock = api.get_clock()
                if not clock.is_open:
                    print("Market closed - sleeping 60s")
                    time.sleep(60)
                    continue

                now_et = dt.datetime.now(ET).time()

                # End-of-session: close everything and idle
                if now_et >= CLOSE_ALL_BY:
                    print(f"[{now_et}] Session end - closing all positions")
                    close_all(api, state, log_run, log_latest)
                    if not review_written:
                        write_daily_review()
                        review_written = True
                    time.sleep(60)
                    continue

                equity = get_equity(api)
                prepared = {}
                last_rows = {}

                for sym in TICKERS:
                    df = fetch_bars(api, sym, LOOKBACK_MINUTES)
                    if df is None or len(df) < 60:
                        print(f"  {sym}: not enough bars, skipping")
                        continue
                    df = prepare_live_indicators(df)
                    prepared[sym] = df
                    last_rows[sym] = df.iloc[-1]

                spy_ok, qqq_ok, broad_market_ok = is_market_healthy(last_rows)
                open_positions = sum(1 for p in state.values() if p["qty"] > 0)
                entry_allowed = SESSION_START <= now_et < CUT_OFF_ENTRIES

                for sym in TICKERS:
                    df = prepared.get(sym)
                    if df is None:
                        continue

                    last = last_rows[sym]
                    px   = float(last["Close"])
                    atr  = float(last["atr"])
                    rsi  = float(last["rsi"])
                    emaf = float(last["ema_fast"])
                    emas = float(last["ema_slow"])
                    ema50 = float(last["ema_50"])
                    vwap = float(last["vwap"])
                    vol = float(last["Volume"])
                    vol_ma20 = float(last["vol_ma20"])
                    atr_pct = atr / px if px > 0 else math.nan
                    ts   = df.index[-1].strftime("%H:%M")
                    sig  = live_rules_strategy(last)
                    pos  = state[sym]
                    market_ok = entry_market_ok(sym, spy_ok, qqq_ok)
                    decision = "HOLD"
                    order_qty = ""
                    reason = ""

                    if math.isnan(atr) or atr <= 0:
                        reason = "invalid_atr"
                        log_decision({
                            "ts_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                            "bar_ts": str(df.index[-1]),
                            "run_id": RUN_ID,
                            "symbol": sym,
                            "decision": "SKIP",
                            "signal": sig,
                            "price": px,
                            "atr": atr,
                            "reason": reason,
                        })
                        continue

                    if pos["qty"] > 0 and pos["stop"] is not None:
                        trailing_stop = px - ATR_MULT * atr
                        if trailing_stop > pos["stop"]:
                            pos["stop"] = trailing_stop

                    # --- Stop-loss (checked before signal, same as backtest) ---
                    if pos["qty"] > 0 and pos["stop"] is not None and px <= pos["stop"]:
                        reason = f"STOP hit px={px:.2f} stop={pos['stop']:.2f}"
                        print(f"[{ts}] STOP  {sym}: {reason}")
                        o = submit_sell(api, sym, pos["qty"], reason, log_run, log_latest)
                        decision = "SELL"
                        order_qty = pos["qty"]
                        filled_qty = int(float(o.filled_qty or 0))
                        remaining_qty = max(0, pos["qty"] - filled_qty)
                        if remaining_qty > 0:
                            state[sym] = {"qty": remaining_qty, "entry_px": pos["entry_px"], "stop": pos["stop"]}
                        else:
                            state[sym] = {"qty": 0, "entry_px": None, "stop": None}
                            open_positions = max(0, open_positions - 1)

                    # --- Entry ---
                    elif sig == "BUY" and pos["qty"] == 0:
                        if not entry_allowed:
                            reason = "entry_blocked_time_window"
                            print(f"[{ts}] HOLD  {sym}: BUY blocked after cutoff/before start")
                        elif open_positions >= MAX_OPEN_POSITIONS:
                            reason = "entry_blocked_max_open_positions"
                            print(f"[{ts}] HOLD  {sym}: BUY blocked max open positions")
                        elif not broad_market_ok or not market_ok:
                            reason = f"entry_blocked_market_filter spy_ok={spy_ok} qqq_ok={qqq_ok}"
                            print(f"[{ts}] HOLD  {sym}: BUY blocked by market filter")
                        elif px < MIN_PRICE:
                            reason = f"entry_blocked_price_below_{MIN_PRICE:g}"
                            print(f"[{ts}] HOLD  {sym}: BUY blocked price={px:.2f}")
                        elif atr_pct < MIN_ATR_PCT:
                            reason = f"entry_blocked_atr_pct_too_low {atr_pct:.5f}"
                            print(f"[{ts}] HOLD  {sym}: BUY blocked low ATR%={atr_pct:.5f}")
                        elif atr_pct > MAX_ATR_PCT:
                            reason = f"entry_blocked_atr_pct_too_high {atr_pct:.5f}"
                            print(f"[{ts}] HOLD  {sym}: BUY blocked high ATR%={atr_pct:.5f}")
                        else:
                            stop_gap         = ATR_MULT * atr
                            risk_shares      = (equity * RISK_PER_TRADE) / stop_gap
                            max_alloc_shares = (equity * MAX_ALLOC) / px
                            qty              = int(min(risk_shares, max_alloc_shares))
                            order_qty = qty
                            if qty <= 0 or qty * px > equity:
                                reason = f"entry_blocked_invalid_qty qty={qty}"
                                print(f"  {sym}: BUY signal but qty={qty} invalid, skipping")
                            else:
                                reason = (
                                    f"BUY ema{EMA_FAST_LEN}>{EMA_SLOW_LEN} rsi={rsi:.1f} "
                                    f"vol>{vol_ma20:.0f} atr={atr:.3f} stop={px-stop_gap:.2f}"
                                )
                                print(f"[{ts}] BUY   {sym}: qty={qty} px={px:.2f} stop={px-stop_gap:.2f}")
                                o = submit_buy(api, sym, qty, reason, log_run, log_latest)
                                decision = "BUY"
                                filled_qty = int(float(o.filled_qty or 0))
                                if filled_qty > 0:
                                    fill_px = float(o.filled_avg_price)
                                    state[sym] = {"qty": filled_qty, "entry_px": fill_px, "stop": fill_px - stop_gap}
                                    open_positions += 1

                    # --- Exit ---
                    elif sig == "SELL" and pos["qty"] > 0:
                        reason = (
                            f"SELL_SIGNAL rsi={rsi:.1f} ema{EMA_FAST_LEN}<{EMA_SLOW_LEN}={emaf<emas} "
                            f"hotWeak={rsi>SELL_RSI_MAX and px<float(last['prev_close'])} belowVWAP={px<vwap*VWAP_SELL_MULT}"
                        )
                        print(f"[{ts}] SELL  {sym}: qty={pos['qty']} px={px:.2f}")
                        o = submit_sell(api, sym, pos["qty"], reason, log_run, log_latest)
                        decision = "SELL"
                        order_qty = pos["qty"]
                        filled_qty = int(float(o.filled_qty or 0))
                        remaining_qty = max(0, pos["qty"] - filled_qty)
                        if remaining_qty > 0:
                            state[sym] = {"qty": remaining_qty, "entry_px": pos["entry_px"], "stop": pos["stop"]}
                        else:
                            state[sym] = {"qty": 0, "entry_px": None, "stop": None}
                            open_positions = max(0, open_positions - 1)

                    # --- Hold ---
                    else:
                        reason = (
                            f"no_action signal={sig} market_ok={market_ok} "
                            f"ema_ok={emaf>emas} rsi_ok={rsi>=BUY_RSI_MIN} "
                            f"close_gt_ema50={px>ema50} volume_ok={vol>vol_ma20}"
                        )
                        held = f" (in pos qty={pos['qty']} stop={pos['stop']:.2f})" if pos["qty"] > 0 else ""
                        print(f"[{ts}] HOLD  {sym}: px={px:.2f} rsi={rsi:.1f} ema{EMA_FAST_LEN}>{EMA_SLOW_LEN}={emaf>emas} aboveVWAP={px>=vwap}{held}")

                    log_decision({
                        "ts_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                        "bar_ts": str(df.index[-1]),
                        "run_id": RUN_ID,
                        "symbol": sym,
                        "decision": decision,
                        "signal": sig,
                        "price": round(px, 4),
                        "ema_fast": round(emaf, 4),
                        "ema_slow": round(emas, 4),
                        "ema_50": round(ema50, 4),
                        "rsi": round(rsi, 4),
                        "vwap": round(vwap, 4),
                        "atr": round(atr, 4),
                        "atr_pct": round(atr_pct, 6),
                        "volume": round(vol, 2),
                        "vol_ma20": round(vol_ma20, 2),
                        "market_ok": market_ok,
                        "spy_ok": spy_ok,
                        "qqq_ok": qqq_ok,
                        "entry_allowed": entry_allowed,
                        "open_positions": open_positions,
                        "position_qty": state[sym]["qty"],
                        "stop": state[sym]["stop"] or "",
                        "order_qty": order_qty,
                        "reason": reason,
                    })

                # Sleep to the next minute boundary
                now_utc  = dt.datetime.now(dt.timezone.utc)
                sleep_s  = 60 - now_utc.second
                time.sleep(max(5, min(60, sleep_s)))

            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(SLEEP_FALLBACK)

    except KeyboardInterrupt:
        print("\nCtrl+C - closing all open positions before exit...")
        close_all(api, state, log_run, log_latest)
        if not review_written:
            write_daily_review()
            review_written = True
    finally:
        log_run.close()
        log_latest.close()
        print("Done.")


if __name__ == "__main__":
    main()
