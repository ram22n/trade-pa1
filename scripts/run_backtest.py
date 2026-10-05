import pandas as pd
import yfinance as yf
from features.indicators import add_indicators
from advisors.rules import rules_strategy

tickers = ["AAPL", "MSFT", "NVDA", "SPY", "QQQ"]

for ticker in tickers:
    df = yf.download(ticker, period="5d", interval="1m")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    df = add_indicators(df)
    df['signal'] = df.apply(rules_strategy, axis=1)
    buys = df[df['signal'] == 'BUY']
    sells = df[df['signal'] == 'SELL']
    print(f"{ticker}: {len(buys)} BUYs, {len(sells)} SELLs in last 5 days")