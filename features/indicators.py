# features/indicators.py
# V2 indicators: EMA9/21/50, RSI14, VWAP, ATR14, VolMA20, Bollinger(20,2)
# Input df must have columns: ["Open","High","Low","Close","Volume"]

from __future__ import annotations
import pandas as pd
import numpy as np


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    Wilder-style RSI using exponential smoothing.
    """
    close = pd.to_numeric(close, errors="coerce")
    delta = close.diff()

    gains = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)

    avg_gain = gains.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1/period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.bfill()


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average True Range (ATR) with Wilder smoothing.
    """
    high = pd.to_numeric(df["High"], errors="coerce")
    low = pd.to_numeric(df["Low"], errors="coerce")
    close = pd.to_numeric(df["Close"], errors="coerce")

    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    return atr


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a copy of df with the following columns added:
      - ema_fast (EMA 9)
      - ema_slow (EMA 21)
      - ema_50   (EMA 50)
      - rsi      (RSI 14)
      - vwap     (cumulative VWAP over the provided window)
      - atr      (ATR 14)
      - vol_ma20 (20-bar average volume)
      - bb_mid, bb_upper, bb_lower (Bollinger Bands 20, 2σ)

    Expects columns: ["Open","High","Low","Close","Volume"].
    """
    df = df.copy()

    # Ensure numeric types
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # --- EMAs ---
    df["ema_fast"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["ema_slow"] = df["Close"].ewm(span=21, adjust=False).mean()
    df["ema_50"]   = df["Close"].ewm(span=50, adjust=False).mean()

    # --- RSI ---
    df["rsi"] = _rsi(df["Close"], period=14)

    # --- VWAP (cumulative over the slice) ---
    # Using Close*Volume for consistency with V1 logic.
    pv_cum = (df["Close"] * df["Volume"]).cumsum()
    vol_cum = df["Volume"].replace(0, pd.NA).cumsum()
    df["vwap"] = (pv_cum / vol_cum).astype(float)

    # --- ATR ---
    df["atr"] = _atr(df, period=14)

    # --- Volume moving average ---
    df["vol_ma20"] = df["Volume"].rolling(window=20, min_periods=1).mean()

    # --- Bollinger Bands (20, 2σ) ---
    mid = df["Close"].rolling(window=20, min_periods=1).mean()
    std = df["Close"].rolling(window=20, min_periods=1).std(ddof=0)
    df["bb_mid"]   = mid
    df["bb_upper"] = mid + 2 * std
    df["bb_lower"] = mid - 2 * std

    return df
