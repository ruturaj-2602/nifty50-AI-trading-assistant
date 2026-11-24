"""
NIFTY Intraday Options Scalper Engine.
Rules:
1. Maximum trade duration: strictly <= 15 minutes (Time-based theta cutoff).
2. Targets quick momentum bursts (0.8 - 1.2 ATR) with tight stops (0.6 - 0.8 ATR).
3. Accounts for 0.5% slippage, flat brokerage (₹40 round-trip), STT, GST, and exchange fees.
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np

from config import MARKET, STRATEGY, RISK
from core.options_pricer import BlackScholesEngine
from core.risk_manager import RiskManager
from core.indicators import add_all_indicators

@dataclass
class ScalpTrade:
    trade_id: int
    entry_date: str
    entry_time: str
    exit_time: str
    contract: str
    option_type: str
    strike: int
    lots: int
    quantity: int
    spot_entry: float
    spot_exit: float
    entry_premium: float
    exit_premium: float
    gross_pnl: float
    total_charges: float
    net_pnl: float
    pnl_pct: float
    exit_reason: str
    duration_mins: int

class NiftyScalperEngine:
    def __init__(
        self,
        initial_capital: float = 100000.0,
        max_holding_mins: int = 15,
        sl_atr_mult: float = 0.75,
        tp_atr_mult: float = 1.25,
        max_daily_trades: int = 8,
        iv: float = 0.14
    ):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.max_holding_mins = max_holding_mins
        self.sl_atr_mult = sl_atr_mult
        self.tp_atr_mult = tp_atr_mult
        self.max_daily_trades = max_daily_trades
        self.iv = iv
        
        self.bs_engine = BlackScholesEngine(risk_free_rate=0.068)
        self.risk_manager = RiskManager(capital=initial_capital)
        self.trades: List[ScalpTrade] = []
        self.equity_curve: List[Dict[str, Any]] = []

    def run(self, df: pd.DataFrame, interval_mins: int = 1) -> pd.DataFrame:
        """
        Runs bar-by-bar scalping backtest with strict <= 15 minute holding limit.
        """
        df_ind = add_all_indicators(df)
        
        # Microstructure Scalper Triggers:
        # Fast EMA 9 > 21 + VWAP confirmation + RSI momentum + Candle Body Expansion
        df_ind['EMA_Fast'] = df_ind['Close'].ewm(span=5, adjust=False).mean()
        df_ind['EMA_Slow'] = df_ind['Close'].ewm(span=13, adjust=False).mean()
        df_ind['RSI_Fast'] = df_ind['RSI'].rolling(5).mean()
        
        max_holding_bars = max(int(self.max_holding_mins // interval_mins), 1)
        
        current_trade = None
        trade_id = 1
        daily_trades_count = 0
        current_day = None
        
        timestamps = df_ind.index
        dates = df_ind.index.date
        times = df_ind.index.strftime("%H:%M")
        
        for idx in range(len(df_ind)):
            row = df_ind.iloc[idx]
            dt = timestamps[idx]
            curr_date = dates[idx]
            curr_time = times[idx]
            
            # Reset daily trade limits
            if curr_date != current_day:
                current_day = curr_date
                daily_trades_count = 0
                self.equity_curve.append({
                    "date": curr_date.strftime("%Y-%m-%d"),
                    "capital": round(self.capital, 2)
                })
                
            # 1. Manage Active Scalp
            if current_trade is not None:
                current_trade['bars_held'] += 1
                duration_mins = current_trade['bars_held'] * interval_mins
                
                spot_high = row['High']
                spot_low = row['Low']
                spot_close = row['Close']
                
                exit_triggered = False
                exit_reason = ""
                spot_exit = spot_close
                is_ce = (current_trade['option_type'] == "CE")
                
                # A. Stop Loss Check
                if is_ce and spot_low <= current_trade['spot_sl']:
                    exit_triggered = True
                    exit_reason = "STOP_LOSS"
                    spot_exit = current_trade['spot_sl']
                elif (not is_ce) and spot_high >= current_trade['spot_sl']:
                    exit_triggered = True
                    exit_reason = "STOP_LOSS"
                    spot_exit = current_trade['spot_sl']
                    
                # B. Take Profit Target Check
                elif is_ce and spot_high >= current_trade['spot_target']:
                    exit_triggered = True
                    exit_reason = "TARGET_HIT"
                    spot_exit = current_trade['spot_target']
                elif (not is_ce) and spot_low <= current_trade['spot_target']:
                    exit_triggered = True
                    exit_reason = "TARGET_HIT"
                    spot_exit = current_trade['spot_target']
                    
                # C. Time-Stop Check (Duration >= 15 mins)
                elif duration_mins >= self.max_holding_mins:
                    exit_triggered = True
                    exit_reason = f"TIME_OUT_{self.max_holding_mins}M"
                    spot_exit = spot_close
                    
                # D. End of Day Square-Off (15:15 IST)
                elif curr_time >= "15:15":
                    exit_triggered = True
                    exit_reason = "EOD_SQUARE_OFF"
                    spot_exit = spot_close
                    
                if exit_triggered:
                    # Estimate exit option premium via Black-Scholes
                    days_to_thursday = (3 - dt.weekday()) % 7
                    dte = max(days_to_thursday + (17.5 - dt.hour) / 24.0, 0.05)
                    
                    exit_greeks = self.bs_engine.calculate_greeks(
                        spot=spot_exit,
                        strike=current_trade['strike'],
                        dte_days=dte,
                        iv=self.iv,
                        option_type=current_trade['option_type']
                    )
                    exit_prem = max(round(exit_greeks.price, 2), 0.5)
                    
                    gross_pnl = (exit_prem - current_trade['entry_premium']) * current_trade['quantity']
                    charges = self.risk_manager.calculate_costs(
                        buy_price=current_trade['entry_premium'],
                        sell_price=exit_prem,
                        quantity=current_trade['quantity']
                    )['total_costs']
                    
                    net_pnl = gross_pnl - charges
                    self.capital += net_pnl
                    
                    self.trades.append(ScalpTrade(
                        trade_id=trade_id,
                        entry_date=current_trade['entry_date'],
                        entry_time=current_trade['entry_time'],
                        exit_time=curr_time,
                        contract=current_trade['contract'],
                        option_type=current_trade['option_type'],
                        strike=current_trade['strike'],
                        lots=current_trade['lots'],
                        quantity=current_trade['quantity'],
                        spot_entry=current_trade['spot_entry'],
                        spot_exit=round(spot_exit, 2),
                        entry_premium=current_trade['entry_premium'],
                        exit_premium=exit_prem,
                        gross_pnl=round(gross_pnl, 2),
                        total_charges=round(charges, 2),
                        net_pnl=round(net_pnl, 2),
                        pnl_pct=round((net_pnl / current_trade['capital_committed']) * 100, 2),
                        exit_reason=exit_reason,
                        duration_mins=duration_mins
                    ))
                    
                    trade_id += 1
                    current_trade = None
                    
            # 2. Check for New Scalp Trigger
            if current_trade is None:
                if curr_time < "09:20" or curr_time > "14:45":
                    continue
                if daily_trades_count >= self.max_daily_trades:
                    continue
                    
                spot_close = row['Close']
                atr = max(row['ATR'], 10.0)
                vwap = row['VWAP']
                ema_fast = row['EMA_Fast']
                ema_slow = row['EMA_Slow']
                rsi = row['RSI']
                
                signal = None
                # Bullish Momentum Scalp: EMA 5 > 13 & Price > VWAP & RSI > 54
                if spot_close > vwap and ema_fast > ema_slow and rsi > 54:
                    signal = "BUY_CE"
                # Bearish Momentum Scalp: EMA 5 < 13 & Price < VWAP & RSI < 46
                elif spot_close < vwap and ema_fast < ema_slow and rsi < 46:
                    signal = "BUY_PE"
                    
                if signal:
                    option_type = "CE" if signal == "BUY_CE" else "PE"
                    strike = self.bs_engine.select_strike(spot_close, option_type, selection_mode="ATM", strike_gap=50)
                    
                    # Quick Scalp SL & TP
                    sl_pts = round(max(atr * self.sl_atr_mult, 15.0), 1)
                    tp_pts = round(sl_pts * (self.tp_atr_mult / self.sl_atr_mult), 1)
                    
                    spot_sl = spot_close - sl_pts if option_type == "CE" else spot_close + sl_pts
                    spot_tp = spot_close + tp_pts if option_type == "CE" else spot_close - tp_pts
                    
                    days_to_thursday = (3 - dt.weekday()) % 7
                    dte = max(days_to_thursday + (17.5 - dt.hour) / 24.0, 0.05)
                    
                    opt_levels = self.bs_engine.map_spot_to_option_levels(
                        spot_entry=spot_close,
                        spot_sl=spot_sl,
                        spot_target=spot_tp,
                        strike=strike,
                        option_type=option_type,
                        dte_days=dte,
                        iv=self.iv
                    )
                    
                    entry_prem = opt_levels['entry_premium']
                    risk_per_share = opt_levels['risk_per_share']
                    
                    # Scalper position size
                    lots = max(1, min(4, int(1500 // (risk_per_share * MARKET.lot_size))))
                    qty = lots * MARKET.lot_size
                    cap_comm = qty * entry_prem
                    
                    if cap_comm <= self.capital * 0.70:
                        current_trade = {
                            "entry_date": curr_date.strftime("%Y-%m-%d"),
                            "entry_time": curr_time,
                            "contract": f"NIFTY {strike} {option_type}",
                            "option_type": option_type,
                            "strike": strike,
                            "lots": lots,
                            "quantity": qty,
                            "capital_committed": cap_comm,
                            "spot_entry": round(spot_close, 2),
                            "spot_sl": round(spot_sl, 2),
                            "spot_target": round(spot_tp, 2),
                            "entry_premium": entry_prem,
                            "bars_held": 0
                        }
                        daily_trades_count += 1
                        
        self.equity_curve.append({
            "date": dates[-1].strftime("%Y-%m-%d"),
            "capital": round(self.capital, 2)
        })
        
        return pd.DataFrame([t.__dict__ for t in self.trades])
