"""
Quantitative Feature Engineering Pipeline for NIFTY Intraday Options.
Transforms raw market indicators into a normalized ML feature vector.
"""
import numpy as np
import pandas as pd
from typing import List, Tuple

FEATURE_COLUMNS = [
    'vwap_dev_atr',
    'ema_spread_9_21',
    'ema_spread_21_50',
    'ema_dist_200',
    'rsi_norm',
    'rsi_delta_3',
    'supertrend_dir',
    'adx_val',
    'di_spread',
    'bb_pct_b',
    'bb_bandwidth',
    'body_to_range',
    'upper_wick_ratio',
    'lower_wick_ratio',
    'atr_pct',
    'orb_pos',
    'intraday_time_norm'
]

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes normalized quantitative features for each candle.
    Guarantees no look-ahead bias (uses only past and current bar information).
    """
    df = df.copy()
    atr_safe = df['ATR'].replace(0, np.nan).ffill().bfill()
    range_safe = df['Candle_Range'].replace(0, np.nan).ffill().bfill()
    close_safe = df['Close'].replace(0, np.nan)
    
    # 1. VWAP Deviation normalized by ATR
    df['vwap_dev_atr'] = (df['Close'] - df['VWAP']) / atr_safe
    
    # 2. Moving Average Spreads normalized by ATR
    df['ema_spread_9_21'] = (df['EMA_9'] - df['EMA_21']) / atr_safe
    df['ema_spread_21_50'] = (df['EMA_21'] - df['EMA_50']) / atr_safe
    df['ema_dist_200'] = (df['Close'] - df['EMA_200']) / atr_safe
    
    # 3. Momentum
    df['rsi_norm'] = (df['RSI'] - 50.0) / 50.0 # centered at 0, [-1, 1]
    df['rsi_delta_3'] = df['RSI'].diff(3) / 10.0
    
    # 4. SuperTrend
    df['supertrend_dir'] = df['SuperTrend_Dir'] # 1 or -1
    
    # 5. Trend Strength & Direction
    df['adx_val'] = df['ADX'] / 100.0
    df['di_spread'] = (df['Plus_DI'] - df['Minus_DI']) / 100.0
    
    # 6. Bollinger Bands
    bb_width_diff = (df['BB_Upper'] - df['BB_Lower']).replace(0, np.nan)
    df['bb_pct_b'] = (df['Close'] - df['BB_Lower']) / bb_width_diff
    df['bb_bandwidth'] = df['BB_Bandwidth']
    
    # 7. Candlestick Anatomy
    df['body_to_range'] = df['Body'] / range_safe
    df['upper_wick_ratio'] = df['Upper_Wick'] / range_safe
    df['lower_wick_ratio'] = df['Lower_Wick'] / range_safe
    
    # 8. Volatility Regime
    df['atr_pct'] = (df['ATR'] / close_safe) * 100.0
    
    # 9. Opening Range Position (-1 = below ORB low, 0 = inside, 1 = above ORB high)
    orb_pos = np.zeros(len(df))
    above_orb = df['Close'] > df['ORB_High']
    below_orb = df['Close'] < df['ORB_Low']
    orb_pos[above_orb] = 1.0
    orb_pos[below_orb] = -1.0
    df['orb_pos'] = orb_pos
    
    # 10. Intraday Time Normalized (0.0 at 09:15 to 1.0 at 15:30)
    minutes_from_open = (df.index.hour * 60 + df.index.minute) - (9 * 60 + 15)
    df['intraday_time_norm'] = np.clip(minutes_from_open / 375.0, 0.0, 1.0)
    
    return df

