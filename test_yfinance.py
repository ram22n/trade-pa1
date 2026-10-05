# test_yfinance.py
import yfinance as yf

# Last 5 days of 1-minute AAPL bars
# Works best during/near market hours
df = yf.download("AAPL", period="5d", interval="1m")
print(df.head())
print("Rows:", len(df))