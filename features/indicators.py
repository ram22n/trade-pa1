# features/indicators.py
# Indicator calculations parameterized by a versioned strategy configuration.
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


def add_indicators(df: pd.DataFrame, settings: dict) -> pd.DataFrame:
    """
    Return a copy of df with the following columns added:
      - ema_fast
      - ema_slow
      - ema_50 (trend EMA; retained name for CSV compatibility)
      - rsi
      - vwap     (cumulative VWAP over the provided window)
      - atr
      - vol_ma20 (volume average; retained name for CSV compatibility)
      - bb_mid, bb_upper, bb_lower

    Expects columns: ["Open","High","Low","Close","Volume"].
    """
    df = df.copy()

    # Ensure numeric types
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # --- EMAs ---
    df["ema_fast"] = df["Close"].ewm(span=settings["ema_fast"], adjust=False).mean()
    df["ema_slow"] = df["Close"].ewm(span=settings["ema_slow"], adjust=False).mean()
    df["ema_50"] = df["Close"].ewm(span=settings["ema_trend"], adjust=False).mean()

    # --- RSI ---
    df["rsi"] = _rsi(df["Close"], period=settings["rsi_period"])

    # --- VWAP (cumulative over the slice) ---
    # Using Close*Volume for consistency with V1 logic.
    pv_cum = (df["Close"] * df["Volume"]).cumsum()
    vol_cum = df["Volume"].replace(0, pd.NA).cumsum()
    df["vwap"] = (pv_cum / vol_cum).astype(float)

    # --- ATR ---
    df["atr"] = _atr(df, period=settings["atr_period"])

    # --- Volume moving average ---
    df["vol_ma20"] = df["Volume"].rolling(
        window=settings["volume_ma_period"], min_periods=1
    ).mean()

    # --- Bollinger Bands (20, 2σ) ---
    bb_period = settings["bollinger_period"]
    bb_width = settings["bollinger_std_dev"]
    mid = df["Close"].rolling(window=bb_period, min_periods=1).mean()
    std = df["Close"].rolling(window=bb_period, min_periods=1).std(ddof=0)
    df["bb_mid"]   = mid
    df["bb_upper"] = mid + bb_width * std
    df["bb_lower"] = mid - bb_width * std

    return df
