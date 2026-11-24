"""
Synthetic Realistic NIFTY Intraday Market Generator.
Models:
1. Overnight gap up/down distribution (mean 0, std 0.4%)
2. Intraday U-shaped volatility curve (NSE microstructure)
3. Trend persistence & mean-reversion regimes
4. 75 five-minute bars per day (09:15 to 15:30 IST)
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, time

def generate_realistic_nifty_intraday(
    days: int = 90,
    interval_mins: int = 5,
    start_price: float = 24200.0,
    seed: int = 42
) -> pd.DataFrame:
    """
    Generates statistically accurate intraday NIFTY 50 candles.
    """
    np.random.seed(seed)
    
    # 375 trading minutes per day / 5 mins = 75 bars/day
    bars_per_day = 375 // interval_mins
    
    # Intraday volatility curve (U-shaped: high at open & close, low during 12:00-13:30)
    # Normalized weights across the 75 bars
    t = np.linspace(-1, 1, bars_per_day)
    vol_u_curve = 0.7 + 0.6 * (t ** 2)
    vol_u_curve = vol_u_curve / vol_u_curve.mean() # scale factor
    
    base_bar_vol = 0.00085 # ~0.085% per 5-min bar (~14% annualized volatility)
    
    # Generate business days
    current_date = datetime.now().date() - timedelta(days=int(days * 1.5))
    trade_dates = []
    while len(trade_dates) < days:
        if current_date.weekday() < 5: # Monday to Friday
            trade_dates.append(current_date)
        current_date += timedelta(days=1)
        
    all_timestamps = []
    all_opens = []
    all_highs = []
    all_lows = []
    all_closes = []
    all_volumes = []
    
    last_close = start_price
    
    for d in trade_dates:
        # 1. Overnight gap
        gap_return = np.random.normal(0.0002, 0.0045) # ~0.45% gap std
        day_open = last_close * (1.0 + gap_return)
        
        # Determine day regime: 0 = Bull Trend, 1 = Bear Trend, 2 = Rangebound Chop
        regime = np.random.choice([0, 1, 2], p=[0.35, 0.35, 0.30])
        drift = 0.00015 if regime == 0 else (-0.00015 if regime == 1 else 0.0)
        
        bar_open = day_open
        
        session_start = datetime.combine(d, time(9, 15))
        
        for bar_idx in range(bars_per_day):
            bar_time = session_start + timedelta(minutes=bar_idx * interval_mins)
            all_timestamps.append(bar_time)
            
            # Volatility multiplier for this specific time of day
            bar_vol = base_bar_vol * vol_u_curve[bar_idx]
            if regime == 2:
                bar_vol *= 0.75 # lower vol in rangebound
                
            # Random return
            ret = np.random.normal(drift, bar_vol)
            bar_close = bar_open * (1.0 + ret)
            
            # Intra-bar high and low
            intra_vol = abs(np.random.normal(0, bar_vol * 0.8))
            bar_high = max(bar_open, bar_close) + bar_open * intra_vol
            bar_low = min(bar_open, bar_close) - bar_open * intra_vol
            
            # Volume profile (higher at open and close)
            base_vol = int(np.random.normal(180000, 30000))
            bar_volume = max(int(base_vol * vol_u_curve[bar_idx]), 5000)
            
            all_opens.append(round(bar_open, 2))
            all_highs.append(round(bar_high, 2))
            all_lows.append(round(bar_low, 2))
            all_closes.append(round(bar_close, 2))
            all_volumes.append(bar_volume)
            
            bar_open = bar_close
            
        last_close = bar_close
        
    df = pd.DataFrame({
        'Open': all_opens,
        'High': all_highs,
        'Low': all_lows,
        'Close': all_closes,
        'Volume': all_volumes
    }, index=pd.DatetimeIndex(all_timestamps, tz="Asia/Kolkata"))
    
    return df

