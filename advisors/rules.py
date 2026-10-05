# advisors/rules.py  (TEMP easier BUY for testing)
def rules_strategy(row):
    # Easier BUY: trend up and RSI >= 50 (removed VWAP filter)
    if row['ema_fast'] > row['ema_slow'] and row['rsi'] >= 50:
        return "BUY"
    # SELL when trend down OR very overbought OR below VWAP by 0.5%
    elif row['ema_fast'] < row['ema_slow'] or row['rsi'] > 75 or row['Close'] < row['vwap'] * 0.995:
        return "SELL"
    else:
        return "HOLD"
