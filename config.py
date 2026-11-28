"""
Configuration parameters for NIFTY Intraday Options Trading AI Bot & Analyst.
Configured specifically for NSE NIFTY 50 Index Options.
"""
import os
from dataclasses import dataclass
from typing import Literal

def load_dotenv(env_path: str = ".env"):
    """Loads key-value pairs from .env into os.environ."""
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()

load_dotenv()

@dataclass
class BrokerConfig:
    mode: str = os.getenv("TRADING_MODE", "PAPER")  # "PAPER" or "ANGEL_ONE"
    angel_api_key: str = os.getenv("ANGEL_API_KEY", "")
    angel_client_code: str = os.getenv("ANGEL_CLIENT_CODE", "")
    angel_pin: str = os.getenv("ANGEL_PIN", "")
    angel_totp_key: str = os.getenv("ANGEL_TOTP_KEY", "")

@dataclass
class MarketConfig:
    symbol: str = "^NSEI"               # Yahoo Finance Nifty 50 ticker
    index_name: str = "NIFTY 50"
    lot_size: int = 65                  # NIFTY standard lot size: 65 Qty
    strike_gap: int = 50                # Strike difference (e.g., 24000, 24050, 24100)
    market_open_time: str = "09:15"     # IST
    entry_start_time: str = "09:20"     # Avoid first 5 minutes opening volatility
    entry_cutoff_time: str = "14:45"    # No new entries after 14:45 IST
    square_off_time: str = "15:15"      # Mandatory intraday square-off time
    market_close_time: str = "15:30"    # IST

@dataclass
class StrategyConfig:
    # Timeframe
    primary_timeframe: str = "5m"       # 5-minute candles are optimal for intraday NIFTY
    secondary_timeframe: str = "15m"    # Multi-timeframe trend confirmation
    
    # Technical Indicators
    ema_fast: int = 9
    ema_medium: int = 21
    ema_slow: int = 50
    ema_trend: int = 200
    rsi_period: int = 14
    rsi_overbought: float = 68.0
    rsi_oversold: float = 32.0
    atr_period: int = 14
    supertrend_period: int = 10
    supertrend_multiplier: float = 2.5
    adx_period: int = 14
    adx_threshold: float = 20.0        # Trend strength threshold
    bb_period: int = 20
    bb_std: float = 2.0
    orb_minutes: int = 15              # Opening range breakout duration

    # Machine Learning Signals
    ml_confidence_threshold: float = 0.70  # High-conviction threshold (~3.9 trades/day, 1.55 PF)
    min_risk_reward: float = 1.35          # Target 1.35 R:R for higher win rate
    
    # Options specifics
    strike_selection: Literal["ATM", "ITM_1", "OTM_1"] = "ITM_1" # ITM_1 has higher delta & lower theta decay
    default_iv: float = 0.11               # 11% India VIX realistic current market proxy
    risk_free_rate: float = 0.068          # RBI 91-day T-bill yield (~6.8%)
    slippage_pct: float = 0.005            # 0.5% slippage on option premium
    brokerage_per_order: float = 20.0      # ₹20 flat discount brokerage (Zerodha/Groww/Angel)
    stt_rate: float = 0.000625             # 0.0625% on option sale turn-over
    exchange_charges: float = 0.0005       # NSE transaction + SEBI + Stamp duty ~0.05%
    gst_rate: float = 0.18                 # 18% GST on brokerage + exchange charges

@dataclass
class RiskConfig:
    capital: float = 15000.0               # ₹15,000 user specified capital
    fixed_lots: int = 1                    # Strict 1 lot (25 shares) trading
    max_capital_per_trade: float = 12000.0 # Max capital committed per trade
    max_trades_per_day: int = 2            # 2 quality trades per day to avoid overtrading
    max_daily_loss: float = 1500.0         # Circuit breaker for day (10% of capital)
    target_risk_per_trade: float = 800.0   # Max risk per trade (~32 pts on 1 lot)
    trailing_sl_trigger_r: float = 1.0     # Move to breakeven when profit reaches 1R
    trailing_sl_step_r: float = 0.5        # Trail SL further by 0.5R for every 1R advance

MARKET = MarketConfig()
STRATEGY = StrategyConfig()
RISK = RiskConfig()
BROKER = BrokerConfig()
