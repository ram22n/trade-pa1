# dashboard_streamlit.py
# Live dashboard for V2 runs
import os
import pandas as pd
import numpy as np
import streamlit as st
import matplotlib.pyplot as plt
from streamlit_autorefresh import st_autorefresh

from datetime import datetime

# -------- Config --------
CSV_PATH = os.path.join("reports", "V2_runs", "latest", "trades_latest.csv")
TZ = "America/Los_Angeles"
REFRESH_SEC = 2  # auto refresh every 2 seconds

st.set_page_config(page_title="V2 Live Trades", layout="wide")
st_autorefresh(interval=REFRESH_SEC * 1000, limit=None, key="refresh")

@st.cache_data(ttl=1.0)
def load_csv(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    if "ts_utc" in df.columns:
        df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
        df["ts_local"] = df["ts_utc"].dt.tz_convert(TZ)
    for col in ["filled_qty","filled_avg_price","realized_pnl"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

def build_cycles(df: pd.DataFrame):
    df = df.sort_values("ts_utc").copy()
    lots = {}
    cycles = []
    for _, r in df.iterrows():
        sym = str(r["symbol"])
        side = str(r["side"]).upper()
        if str(r.get("status","")).lower() != "filled":
            continue
        qty = float(r.get("filled_qty") or 0)
        px = float(r.get("filled_avg_price") or 0)
        ts = r["ts_utc"]
        if sym not in lots: lots[sym] = []
        if side == "BUY" and qty>0 and px>0:
            lots[sym].append({"qty":qty,"price":px,"time":ts})
        elif side == "SELL" and qty>0 and px>0:
            to_sell = qty; realized=0; entry_val=0; entry_qty=0; first_time=None
            while to_sell>1e-9 and lots[sym]:
                lot = lots[sym][0]; take = min(to_sell, lot["qty"])
                realized += (px - lot["price"])*take
                entry_val += lot["price"]*take; entry_qty += take
                if first_time is None: first_time=lot["time"]
                lot["qty"] -= take; to_sell -= take
                if lot["qty"]<=1e-9: lots[sym].pop(0)
            if entry_qty>0:
                cycles.append({
                    "symbol":sym,
                    "buy_time":first_time,
                    "sell_time":ts,
                    "qty_closed":round(entry_qty,6),
                    "avg_entry":round(entry_val/entry_qty,4),
                    "exit_price":round(px,4),
                    "pnl":round(realized,2)
                })
    closed = pd.DataFrame(cycles)
    if not closed.empty:
        closed["buy_time_local"]=pd.to_datetime(closed["buy_time"],utc=True).dt.tz_convert(TZ)
        closed["sell_time_local"]=pd.to_datetime(closed["sell_time"],utc=True).dt.tz_convert(TZ)
        closed["hold_min"]=(closed["sell_time_local"]-closed["buy_time_local"]).dt.total_seconds()/60
    return closed

st.title("📊 V2 Live Trades Dashboard")
st.caption("Watching latest trades CSV and updating every 2 seconds.")

if not os.path.exists(CSV_PATH):
    st.warning("CSV not found yet. Start your trading script first.")
    st.stop()

df = load_csv(CSV_PATH)
if df.empty:
    st.info("No fills yet… waiting for trades.")
    st.stop()

closed = build_cycles(df)

# KPIs
colA,colB,colC,colD = st.columns(4)
net_pnl = float(closed["pnl"].sum()) if not closed.empty else 0
wins = int((closed["pnl"]>0).sum()) if not closed.empty else 0
losses = int((closed["pnl"]<0).sum()) if not closed.empty else 0
trades = len(closed)
win_rate = (wins/trades*100) if trades else 0
colA.metric("Net P&L", f"${net_pnl:,.2f}")
colB.metric("Closed Cycles", str(trades))
colC.metric("Win Rate", f"{win_rate:.1f}%")
colD.metric("W/L", f"{wins}/{losses}")

# Equity curve
if not closed.empty:
    st.subheader("Equity Curve")
    eq = closed.sort_values("sell_time")["pnl"].cumsum()
    fig = plt.figure(); plt.plot(eq.values); plt.xlabel("Closed trade #"); plt.ylabel("Cumulative P&L"); st.pyplot(fig)

# Per symbol
if not closed.empty:
    st.subheader("P&L by Symbol")
    st.dataframe(closed.groupby("symbol")["pnl"].sum().sort_values(ascending=False).reset_index())

# Raw fills
st.subheader("Recent fills")
show = df.sort_values("ts_utc").tail(50)
st.dataframe(show[["ts_local","symbol","side","status","filled_qty","filled_avg_price","realized_pnl","reason"]])
