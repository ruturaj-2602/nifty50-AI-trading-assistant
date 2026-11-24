"""
Angel One SmartAPI Historical Data Fetcher.
Fetches authentic NIFTY 50 intraday 5-minute candles directly from Angel One servers.
"""
import os
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
from brokers.angelone_adapter import AngelOneBroker

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data_cache")

def fetch_angel_historical_data(
    days: int = 60,
    interval: str = "FIVE_MINUTE",
    symbol_token: str = "99926000",
    exchange: str = "NSE",
    force_refresh: bool = False
) -> pd.DataFrame:
    """
    Fetches real historical candles directly from Angel One SmartAPI.
    Caches to parquet to avoid redundant API calls.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_file = os.path.join(CACHE_DIR, f"nifty_angel_{interval}_{days}d.csv")

    if not force_refresh and os.path.exists(cache_file):
        try:
            df = pd.read_csv(cache_file, index_col=0, parse_dates=True)
            if not df.empty:
                if not isinstance(df.index, pd.DatetimeIndex):
                    df.index = pd.to_datetime(df.index)
                if df.index.tz is None:
                    df.index = df.index.tz_localize("Asia/Kolkata")
                else:
                    df.index = df.index.tz_convert("Asia/Kolkata")
                print(f"[AngelData] Loaded {len(df):,} candles from local Angel One cache.")
                return df
        except Exception:
            pass

    print(f"[AngelData] Connecting to Angel One SmartAPI to download {days} days of historical 5m candles...")
    broker = AngelOneBroker()
    if not broker.connect():
        raise ConnectionError("Failed to authenticate with Angel One SmartAPI.")

    all_candles = []
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    # Angel One allows up to 30 days per chunk for intraday intervals
    chunk_size = timedelta(days=25)
    curr_start = start_date

    while curr_start < end_date:
        curr_end = min(curr_start + chunk_size, end_date)
        from_str = curr_start.strftime("%Y-%m-%d 09:15")
        to_str = curr_end.strftime("%Y-%m-%d 15:30")

        params = {
            "exchange": exchange,
            "symboltoken": symbol_token,
            "interval": interval,
            "fromdate": from_str,
            "todate": to_str
        }

        try:
            res = broker.smart_api.getCandleData(params)
            if res.get("status") and "data" in res and res["data"]:
                data = res["data"]
                print(f"[AngelData] Fetched {len(data)} candles from {from_str} to {to_str}")
                all_candles.extend(data)
            else:
                msg = res.get("message", "No data returned")
                print(f"[AngelData] Chunk notice ({from_str} to {to_str}): {msg}")
        except Exception as e:
            print(f"[AngelData] Error fetching chunk: {e}")

        curr_start = curr_end + timedelta(minutes=1)

    if not all_candles:
        raise ValueError("No historical candles retrieved from Angel One SmartAPI.")

    # Convert to DataFrame
    # Columns in SmartAPI getCandleData: [timestamp, open, high, low, close, volume]
    df = pd.DataFrame(all_candles, columns=["Timestamp", "Open", "High", "Low", "Close", "Volume"])
    df["Timestamp"] = pd.to_datetime(df["Timestamp"])
    df.set_index("Timestamp", inplace=True)
    df.sort_index(inplace=True)
    
    # Remove duplicates if any from overlapping chunks
    df = df[~df.index.duplicated(keep="first")]

    # Localize or convert timezone to Asia/Kolkata
    if df.index.tz is None:
        df.index = df.index.tz_localize("Asia/Kolkata")
    else:
        df.index = df.index.tz_convert("Asia/Kolkata")

    # Filter trading hours: 09:15 to 15:30
    time_str = df.index.strftime("%H:%M")
    df = df[(time_str >= "09:15") & (time_str <= "15:30")].copy()

    # Cast to float
    for col in ["Open", "High", "Low", "Close"]:
        df[col] = df[col].astype(float)
    df["Volume"] = df["Volume"].astype(int)

    # Cache locally
    df.to_csv(cache_file)
    print(f"[AngelData] Successfully saved {len(df):,} Angel One candles to cache.")
    return df
