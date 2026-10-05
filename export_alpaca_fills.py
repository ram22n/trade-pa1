import os
import pandas as pd
from dotenv import load_dotenv
from alpaca_trade_api.rest import REST, TimeFrame
from datetime import datetime, timedelta

# Load keys from .env
load_dotenv()
API_KEY = os.getenv("ALPACA_KEY")
API_SECRET = os.getenv("ALPACA_SECRET")
BASE_URL = "https://paper-api.alpaca.markets"  # Change if live

api = REST(API_KEY, API_SECRET, base_url=BASE_URL)

# Date range: yesterday to today
end_time = datetime.now()
start_time = end_time - timedelta(days=1)

# Get raw fills (activities)
fills = api.get_activities(
    activity_types="FILL",
    after=start_time.isoformat() + "Z",
    until=end_time.isoformat() + "Z"
)

# Convert to DataFrame
df = pd.DataFrame([f._raw for f in fills])

# Ensure reports folder exists
reports_dir = os.path.join(os.path.dirname(__file__), "reports")
os.makedirs(reports_dir, exist_ok=True)

# Save file
out_path = os.path.join(reports_dir, f"alpaca_fills_{end_time.strftime('%Y%m%d_%H%M%S')}.csv")
df.to_csv(out_path, index=False)

print(f"Exported {len(df)} fills to {out_path}")
