"""
Event-Driven Intraday Options Backtesting Engine.
Simulates real-world execution with option Greeks, slippage,
transaction taxes (STT/GST/Exchange/SEBI), trailing SL, and 15:15 square-off.
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np

from config import MARKET, STRATEGY, RISK
from core.options_pricer import BlackScholesEngine
from core.risk_manager import RiskManager
from core.indicators import add_all_indicators
from ai.features import engineer_features
from ai.model import IntradaySignalClassifier

@dataclass
class TradeRecord:
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
    holding_bars: int

class BacktestEngine:
    def __init__(
        self,
        initial_capital: float = RISK.capital,
        confidence_threshold: float = STRATEGY.ml_confidence_threshold,
        iv: float = STRATEGY.default_iv
    ):
        self.initial_capital = initial_capital
        self.risk_manager = RiskManager(capital=initial_capital)
        self.bs_engine = BlackScholesEngine(risk_free_rate=STRATEGY.risk_free_rate)
        self.classifier = IntradaySignalClassifier(confidence_threshold=confidence_threshold)
        self.iv = iv
        
        self.trades: List[TradeRecord] = []
        self.equity_curve: List[Dict[str, Any]] = []

    def run(self, df: pd.DataFrame, train_ratio: float = 0.5) -> pd.DataFrame:
        """
        Runs out-of-sample backtest.
        Trains AI classifier on first `train_ratio` (e.g. 50%), then runs
        live-simulation backtest strictly on the remaining unseen test set.
        """
        print("[Backtester] Preparing indicators and ML feature pipeline...")
        df_ind = add_all_indicators(df)
        df_feat = engineer_features(df_ind).dropna()
        
        total_rows = len(df_feat)
        train_size = int(total_rows * train_ratio)
        
        train_df = df_feat.iloc[:train_size].copy()
        test_df = df_feat.iloc[train_size:].copy()
        
        print(f"[Backtester] Training AI Model on {len(train_df)} historical candles...")
        self.classifier.train(train_df)
        
        print(f"[Backtester] Executing walk-forward out-of-sample backtest on {len(test_df)} candles...")
        
        current_trade = None
        trade_id_counter = 1
        
        dates = test_df.index.date
        times = test_df.index.strftime("%H:%M")
        
        for idx in range(len(test_df)):
            row = test_df.iloc[idx]
            curr_date = dates[idx]
            curr_time = times[idx]
            curr_dt = test_df.index[idx]
            
            # Reset daily limits on new day
            self.risk_manager.reset_daily_metrics_if_new_day(curr_date)
            
            # Record daily equity snapshot at start of day
            if idx == 0 or dates[idx] != dates[idx - 1]:
                self.equity_curve.append({
                    "date": curr_date.strftime("%Y-%m-%d"),
                    "capital": round(self.risk_manager.current_capital, 2)
                })
            
            # 1. Manage Active Trade if any
            if current_trade is not None:
                spot_high = row['High']
                spot_low = row['Low']
                spot_close = row['Close']
                
                current_trade['bars_held'] += 1
                
                # Expiry DTE estimation: Thursday is expiry (weekday == 3)
                days_to_thursday = (3 - curr_dt.weekday()) % 7
                dte = max(days_to_thursday + (17.5 - curr_dt.hour) / 24.0, 0.1)
                
                # Check Spot SL / Target triggers
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
                    
                # B. Target 2 Check (Full target hit)
                elif is_ce and spot_high >= current_trade['spot_target_2']:
                    exit_triggered = True
                    exit_reason = "TARGET_2_HIT"
                    spot_exit = current_trade['spot_target_2']
                elif (not is_ce) and spot_low <= current_trade['spot_target_2']:
                    exit_triggered = True
                    exit_reason = "TARGET_2_HIT"
                    spot_exit = current_trade['spot_target_2']
                    
                # C. Target 1 Reached: Trail SL to Breakeven
                elif not current_trade.get('sl_trailed', False):
                    if is_ce and spot_high >= current_trade['spot_target']:
                        current_trade['spot_sl'] = current_trade['spot_entry'] # Trail SL to cost
                        current_trade['sl_trailed'] = True
                    elif (not is_ce) and spot_low <= current_trade['spot_target']:
                        current_trade['spot_sl'] = current_trade['spot_entry']
                        current_trade['sl_trailed'] = True
                        
                # D. Mandatory Square-off at 15:15 IST
                if not exit_triggered and curr_time >= MARKET.square_off_time:
                    exit_triggered = True
                    exit_reason = "INTRADAY_SQUARE_OFF"
                    spot_exit = spot_close
                    
                # Execute Trade Exit
                if exit_triggered:
                    exit_greeks = self.bs_engine.calculate_greeks(
                        spot=spot_exit,
                        strike=current_trade['strike'],
                        dte_days=dte,
                        iv=self.iv,
                        option_type=current_trade['option_type']
                    )
                    exit_prem = max(round(exit_greeks.price, 2), 0.5)
                    
                    gross_pnl = (exit_prem - current_trade['entry_premium']) * current_trade['quantity']
                    charges_dict = self.risk_manager.calculate_costs(
                        buy_price=current_trade['entry_premium'],
                        sell_price=exit_prem,
                        quantity=current_trade['quantity']
                    )
                    total_charges = charges_dict['total_costs']
                    net_pnl = gross_pnl - total_charges
                    pnl_pct = (net_pnl / current_trade['capital_committed']) * 100.0
                    
                    # Update Risk Manager Capital
                    self.risk_manager.update_capital(net_pnl)
                    
                    self.trades.append(TradeRecord(
                        trade_id=trade_id_counter,
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
                        total_charges=round(total_charges, 2),
                        net_pnl=round(net_pnl, 2),
                        pnl_pct=round(pnl_pct, 2),
                        exit_reason=exit_reason,
                        holding_bars=current_trade['bars_held']
                    ))
                    
                    trade_id_counter += 1
                    current_trade = None
                    
            # 2. Check for New Entry if no active trade
            if current_trade is None:
                # Time filter: Entry only between 09:20 and 14:45
                if curr_time < MARKET.entry_start_time or curr_time > MARKET.entry_cutoff_time:
                    continue
                # Skip lunch hour dead zone (11:30 - 13:15 IST)
                if "11:30" <= curr_time <= "13:15":
                    continue
                    
                spot_close = row['Close']
                atr = row['ATR']
                vwap = row['VWAP']
                supertrend_dir = row['SuperTrend_Dir']
                rsi = row['RSI']
                adx = row.get('ADX', 22.0)
                
                # Evaluate ML setup
                ml_pred = self.classifier.predict(row)
                bull_prob = ml_pred['bull_prob']
                bear_prob = ml_pred['bear_prob']
                
                signal = None
                if spot_close >= vwap and supertrend_dir == 1 and bull_prob >= self.classifier.confidence_threshold and adx >= 18 and rsi >= 50:
                    signal = "BUY_CE"
                elif spot_close <= vwap and supertrend_dir == -1 and bear_prob >= self.classifier.confidence_threshold and adx >= 18 and rsi <= 50:
                    signal = "BUY_PE"
                
                if signal in ("BUY_CE", "BUY_PE"):
                        
                    option_type = "CE" if signal == "BUY_CE" else "PE"
                    strike = self.bs_engine.select_strike(
                        spot=spot_close,
                        option_type=option_type,
                        selection_mode=STRATEGY.strike_selection,
                        strike_gap=MARKET.strike_gap
                    )
                    
                    # Dynamic ATR Stop Loss & Target
                    sl_pts = round(max(atr * 1.2, 25.0), 1)
                    tp_pts = round(sl_pts * STRATEGY.min_risk_reward, 1)
                    
                    if option_type == "CE":
                        spot_sl = spot_close - sl_pts
                        spot_tp1 = spot_close + tp_pts
                        spot_tp2 = spot_close + (tp_pts * 1.4)
                    else:
                        spot_sl = spot_close + sl_pts
                        spot_tp1 = spot_close - tp_pts
                        spot_tp2 = spot_close - (tp_pts * 1.4)
                        
                    # DTE calculation
                    days_to_thursday = (3 - curr_dt.weekday()) % 7
                    dte = max(days_to_thursday + (17.5 - curr_dt.hour) / 24.0, 0.1)
                    
                    opt_levels = self.bs_engine.map_spot_to_option_levels(
                        spot_entry=spot_close,
                        spot_sl=spot_sl,
                        spot_target=spot_tp1,
                        strike=strike,
                        option_type=option_type,
                        dte_days=dte,
                        iv=self.iv
                    )
                    
                    entry_prem = opt_levels['entry_premium']
                    risk_per_share = opt_levels['risk_per_share']
                    
                    # Risk management position sizing
                    pos_res = self.risk_manager.calculate_position_size(
                        entry_premium=entry_prem,
                        risk_per_share=risk_per_share
                    )
                    
                    if pos_res.is_valid and pos_res.lots >= 1:
                        current_trade = {
                            "entry_date": curr_date.strftime("%Y-%m-%d"),
                            "entry_time": curr_time,
                            "contract": f"NIFTY {strike} {option_type}",
                            "option_type": option_type,
                            "strike": strike,
                            "lots": pos_res.lots,
                            "quantity": pos_res.quantity,
                            "capital_committed": pos_res.capital_required,
                            "spot_entry": round(spot_close, 2),
                            "spot_sl": round(spot_sl, 2),
                            "spot_target": round(spot_tp1, 2),
                            "spot_target_2": round(spot_tp2, 2),
                            "entry_premium": entry_prem,
                            "bars_held": 0,
                            "sl_trailed": False
                        }

        # Final equity point
        self.equity_curve.append({
            "date": dates[-1].strftime("%Y-%m-%d"),
            "capital": round(self.risk_manager.current_capital, 2)
        })
        
        # Convert trades to DataFrame
        trade_dicts = [t.__dict__ for t in self.trades]
        return pd.DataFrame(trade_dicts)
