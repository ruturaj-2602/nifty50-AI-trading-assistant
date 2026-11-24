"""
Technical Indicators Engine for NIFTY Intraday Trading.
Optimized for high performance, zero look-ahead bias, and NumPy 2.x / Pandas 3.x compatibility.
"""
import numpy as np
import pandas as pd
from typing import Tuple

def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """
    Calculate Intraday Anchored VWAP (resets each trading session).
    If Volume is zero (standard for Spot Index like NIFTY 50),
    uses session cumulative intraday TWAP (Time-Weighted Average Price).
    """
    df = df.copy()
    if 'Date' not in df.columns:
        if isinstance(df.index, pd.DatetimeIndex):
            df['Date'] = df.index.date
        else:
            df['Date'] = pd.to_datetime(df.index).date
    
    typical_price = (df['High'] + df['Low'] + df['Close']) / 3.0
    
    if df['Volume'].sum() == 0:
        twap = typical_price.groupby(df['Date']).expanding().mean()
        if isinstance(twap.index, pd.MultiIndex):
            twap.index = df.index
        return twap
        
    tp_vol = typical_price * df['Volume']
    cum_tp_vol = tp_vol.groupby(df['Date']).cumsum()
    cum_vol = df['Volume'].groupby(df['Date']).cumsum()
    
    cum_vol = cum_vol.replace(0, np.nan)
    vwap = cum_tp_vol / cum_vol
    return vwap.ffill().bfill()

def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Average True Range (Wilder's Smoothing)."""
    high = df['High'].values
    low = df['Low'].values
    close_prev = df['Close'].shift(1).bfill().values
    
    tr1 = high - low
    tr2 = np.abs(high - close_prev)
    tr3 = np.abs(low - close_prev)
    
    tr = np.maximum(tr1, np.maximum(tr2, tr3))
    tr_series = pd.Series(tr, index=df.index)
    atr = tr_series.ewm(alpha=1.0 / period, adjust=False).mean()
    return atr

def calculate_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 2.5) -> Tuple[pd.Series, pd.Series]:
    """
    SuperTrend indicator: returns (supertrend_value, direction).
    direction: 1 for Bullish (Green), -1 for Bearish (Red).
    Guarantees mutable NumPy 2.x writable arrays.
    """
    n = len(df)
    if n == 0:
        return pd.Series(dtype=float), pd.Series(dtype=int)
        
    hl2 = ((df['High'] + df['Low']) / 2.0).to_numpy(dtype=float, copy=True)
    atr = calculate_atr(df, period).to_numpy(dtype=float, copy=True)
    
    basic_ub = hl2 + (multiplier * atr)
    basic_lb = hl2 - (multiplier * atr)
    
    closes = df['Close'].to_numpy(dtype=float, copy=True)
    f_ubs = np.zeros(n, dtype=float)
    f_lbs = np.zeros(n, dtype=float)
    trends = np.ones(n, dtype=int)
    st_vals = np.zeros(n, dtype=float)
    
    f_ubs[0] = basic_ub[0]
    f_lbs[0] = basic_lb[0]
    st_vals[0] = f_lbs[0]
    
    for i in range(1, n):
        # Final Upper Band
        if basic_ub[i] < f_ubs[i-1] or closes[i-1] > f_ubs[i-1]:
            f_ubs[i] = basic_ub[i]
        else:
            f_ubs[i] = f_ubs[i-1]
            
        # Final Lower Band
        if basic_lb[i] > f_lbs[i-1] or closes[i-1] < f_lbs[i-1]:
            f_lbs[i] = basic_lb[i]
        else:
            f_lbs[i] = f_lbs[i-1]
            
        # Trend
        if trends[i-1] == 1:
            if closes[i] < f_lbs[i]:
                trends[i] = -1
                st_vals[i] = f_ubs[i]
            else:
                trends[i] = 1
                st_vals[i] = f_lbs[i]
        else:
            if closes[i] > f_ubs[i]:
                trends[i] = 1
                st_vals[i] = f_lbs[i]
            else:
                trends[i] = -1
                st_vals[i] = f_ubs[i]
                
    return pd.Series(st_vals, index=df.index), pd.Series(trends, index=df.index)

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)

def calculate_bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0):
    """Bollinger Bands: Middle, Upper, Lower, Bandwidth."""
    middle = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = middle + (std_dev * std)
    lower = middle - (std_dev * std)
    bandwidth = (upper - lower) / middle.replace(0, np.nan)
    return upper.bfill(), middle.bfill(), lower.bfill(), bandwidth.fillna(0.0)

def calculate_adx(df: pd.DataFrame, period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Average Directional Index (+DI, -DI, ADX)."""
    high = df['High'].values
    low = df['Low'].values
    
    up_move = np.diff(high, prepend=high[0])
    down_move = -np.diff(low, prepend=low[0])
    
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    
    atr = calculate_atr(df, period).replace(0, np.nan)
    
    plus_di = 100.0 * pd.Series(plus_dm, index=df.index).ewm(alpha=1.0 / period, adjust=False).mean() / atr
    minus_di = 100.0 * pd.Series(minus_dm, index=df.index).ewm(alpha=1.0 / period, adjust=False).mean() / atr
    
    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1.0 / period, adjust=False).mean()
    return plus_di.fillna(0), minus_di.fillna(0), adx.fillna(0)

def calculate_orb(df: pd.DataFrame, orb_minutes: int = 15) -> Tuple[pd.Series, pd.Series]:
    """
    Opening Range Breakout: returns (orb_high, orb_low) for each session.
    """
    df = df.copy()
    if 'Date' not in df.columns:
        if isinstance(df.index, pd.DatetimeIndex):
            df['Date'] = df.index.date
        else:
            df['Date'] = pd.to_datetime(df.index).date
        
    orb_high = pd.Series(np.nan, index=df.index)
    orb_low = pd.Series(np.nan, index=df.index)
    
    grouped = df.groupby(df['Date'])
    for date, group in grouped:
        first_time = group.index[0]
        orb_cutoff = first_time + pd.Timedelta(minutes=orb_minutes)
        orb_window = group[group.index <= orb_cutoff]
        if not orb_window.empty:
            h = orb_window['High'].max()
            l = orb_window['Low'].min()
            orb_high.loc[group.index] = h
            orb_low.loc[group.index] = l
            
    return orb_high.ffill().bfill(), orb_low.ffill().bfill()

def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Enrich intraday DataFrame with all technical indicators."""
    df = df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    if df.index.tz is not None:
        try:
            df.index = df.index.tz_convert("Asia/Kolkata")
        except Exception:
            pass
    
    # Moving Averages
    df['EMA_9'] = calculate_ema(df['Close'], 9)
    df['EMA_21'] = calculate_ema(df['Close'], 21)
    df['EMA_50'] = calculate_ema(df['Close'], 50)
    df['EMA_200'] = calculate_ema(df['Close'], 200)
    
    # VWAP
    df['VWAP'] = calculate_vwap(df)
    df['VWAP_Dev'] = (df['Close'] - df['VWAP']) / df['Close']
    
    # Volatility & Momentum
    df['ATR'] = calculate_atr(df, 14)
    df['RSI'] = calculate_rsi(df['Close'], 14)
    df['RSI_SMA'] = df['RSI'].rolling(7).mean()
    
    # SuperTrend
    st_val, st_trend = calculate_supertrend(df, period=10, multiplier=2.5)
    df['SuperTrend'] = st_val
    df['SuperTrend_Dir'] = st_trend
    
    # Bollinger Bands
    bb_u, bb_m, bb_l, bb_w = calculate_bollinger_bands(df['Close'], 20, 2.0)
    df['BB_Upper'] = bb_u
    df['BB_Middle'] = bb_m
    df['BB_Lower'] = bb_l
    df['BB_Bandwidth'] = bb_w
    
    # ADX
    plus_di, minus_di, adx = calculate_adx(df, 14)
    df['Plus_DI'] = plus_di
    df['Minus_DI'] = minus_di
    df['ADX'] = adx
    
    # Opening Range Breakout
    orb_h, orb_l = calculate_orb(df, 15)
    df['ORB_High'] = orb_h
    df['ORB_Low'] = orb_l
    
    # Candle Anatomy
    df['Body'] = (df['Close'] - df['Open']).abs()
    df['Upper_Wick'] = df['High'] - df[['Open', 'Close']].max(axis=1)
    df['Lower_Wick'] = df[['Open', 'Close']].min(axis=1) - df['Low']
    df['Candle_Range'] = df['High'] - df['Low']
    
    return df
