import os
from dotenv import load_dotenv
from alpaca_trade_api import REST

load_dotenv()
api = REST(os.getenv("ALPACA_KEY"), os.getenv("ALPACA_SECRET"), base_url=os.getenv("ALPACA_BASE_URL"))
o = api.submit_order(symbol="AAPL", notional=10, side="buy", type="market", time_in_force="day")
print("Submitted test BUY order for ~$10:", o.symbol)
