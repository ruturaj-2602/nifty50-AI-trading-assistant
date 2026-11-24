"""
Data Fetcher for NIFTY 50 Historical and Live Intraday Data.
Fetches data from Yahoo Finance (^NSEI) with local caching.
"""
import os
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from typing import Optional

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data_cache")

def get_nifty_intraday_data(
    period: str = "60d",
    interval: str = "5m",
    force_refresh: bool = False
) -> pd.DataFrame:
    """
    Fetches NIFTY 50 intraday data (^NSEI).
    Yahoo Finance provides up to 60 days of 5m intraday data.
    Saves to parquet cache to avoid repetitive network requests.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_file = os.path.join(CACHE_DIR, f"nifty_{interval}_{period}.parquet")
    
    if not force_refresh and os.path.exists(cache_file):
        try:
            df = pd.read_parquet(cache_file)
            if not df.empty:
                return df
        except Exception:
            pass
            
    try:
        ticker = yf.Ticker("^NSEI")
        df = ticker.history(period=period, interval=interval)
        
        if df.empty:
            raise ValueError("Empty data returned from Yahoo Finance")
            
        # Standardize columns
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
        
        # Convert index to Indian Standard Time (IST) if localized or naive
        if df.index.tz is not None:
            df.index = df.index.tz_convert("Asia/Kolkata")
        else:
            df.index = df.index.tz_localize("Asia/Kolkata")
            
        # Filter for NSE trading hours 09:15 to 15:30
        df['time_str'] = df.index.strftime("%H:%M")
        df = df[(df['time_str'] >= "09:15") & (df['time_str'] <= "15:30")].copy()
        df.drop(columns=['time_str'], inplace=True)
        
        # Drop zero-volume or invalid rows if any
        df = df[df['Close'] > 0]
        
        # Save cache
        df.to_parquet(cache_file)
        return df
    except Exception as e:
        print(f"Warning: Could not fetch live Yahoo Finance data ({e}). Using synthetic generator.")
        from data.synthetic import generate_realistic_nifty_intraday
        return generate_realistic_nifty_intraday(days=60, interval_mins=5)

