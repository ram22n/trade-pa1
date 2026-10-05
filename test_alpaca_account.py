# test_alpaca_account.py
import os
from dotenv import load_dotenv
from alpaca_trade_api import REST

load_dotenv()

api = REST(
    os.getenv("ALPACA_KEY"),
    os.getenv("ALPACA_SECRET"),
    base_url=os.getenv("ALPACA_BASE_URL"),
)

# Check account (confirms keys work)
acct = api.get_account()
print("Account status:", acct.status)

# Check market clock (works without market data subscription)
clock = api.get_clock()
print("Market is open?" , clock.is_open)