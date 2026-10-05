def rules_strategy(row, settings: dict):
    buy = row["ema_fast"] > row["ema_slow"] and row["rsi"] >= settings["buy_rsi_min"]
    if settings["require_close_above_ema_trend"]:
        buy = buy and row["Close"] > row["ema_50"]
    if settings["require_volume_above_average"]:
        buy = buy and row["Volume"] > row["vol_ma20"]

    if buy:
        return "BUY"

    overbought = row["rsi"] > settings["sell_rsi_max"]
    if settings["overbought_sell_requires_weakening"]:
        overbought = overbought and row["Close"] < row["prev_close"]

    if (
        row["ema_fast"] < row["ema_slow"]
        or overbought
        or row["Close"] < row["vwap"] * settings["vwap_sell_multiplier"]
    ):
        return "SELL"
    return "HOLD"
