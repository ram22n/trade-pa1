import pandas as pd
import yfinance as yf
from advisors.rules import rules_strategy
from configs.loader import load_config
from features.indicators import add_indicators

CONFIG = load_config("backup_v1.yml")
tickers = CONFIG["symbols"]

for ticker in tickers:
    df = yf.download(
        ticker,
        period=CONFIG["data"]["period"],
        interval=CONFIG["data"]["interval"],
    )
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    df = add_indicators(df, CONFIG["indicators"])
    df['signal'] = df.apply(lambda row: rules_strategy(row, CONFIG["signal"]), axis=1)
    buys = df[df['signal'] == 'BUY']
    sells = df[df['signal'] == 'SELL']
    print(f"{ticker}: {len(buys)} BUYs, {len(sells)} SELLs in {CONFIG['data']['period']}")
