"""
AI Options Analyst Engine.
Produces institutional-grade trade advisories, confluence breakdowns,
Greeks analysis, and risk-managed execution parameters for NIFTY traders.
"""
from typing import Dict, Any, Optional
from datetime import datetime
from core.options_pricer import BlackScholesEngine
from config import STRATEGY, RISK, MARKET

class AIAnalyst:
    def __init__(self):
        self.bs_engine = BlackScholesEngine(risk_free_rate=STRATEGY.risk_free_rate)

    def analyze_setup(
        self,
        current_candle: dict,
        ml_prediction: dict,
        iv: float = 0.11,
        dte_days: float = 1.2,
        broker = None
    ) -> Optional[Dict[str, Any]]:
        """
        Synthesizes technical indicators, options Greeks, and ML predictions
        into a complete, actionable trading advisory.
        """
        signal = ml_prediction.get("signal", "HOLD")
        confidence = ml_prediction.get("confidence", 0.0)
        
        if signal not in ("BUY_CE", "BUY_PE"):
            return None
            
        spot_close = current_candle['Close']
        atr = current_candle['ATR']
        vwap = current_candle['VWAP']
        rsi = current_candle['RSI']
        adx = current_candle['ADX']
        supertrend = current_candle['SuperTrend']
        st_dir = current_candle['SuperTrend_Dir']
        
        # Determine Strike and Option Type
        option_type = "CE" if signal == "BUY_CE" else "PE"
        strike = self.bs_engine.select_strike(
            spot=spot_close,
            option_type=option_type,
            selection_mode=STRATEGY.strike_selection,
            strike_gap=MARKET.strike_gap
        )
        
        # Dynamic ATR-based Stop Loss & Target in Spot Points
        sl_points = round(max(atr * 1.2, 25.0), 1)  # Minimum 25 points SL on Nifty
        target_points = round(sl_points * STRATEGY.min_risk_reward, 1)
        
        if option_type == "CE":
            spot_sl = spot_close - sl_points
            spot_target = spot_close + target_points
            spot_target_2 = spot_close + (target_points * 1.4)
        else:
            spot_sl = spot_close + sl_points
            spot_target = spot_close - target_points
            spot_target_2 = spot_close - (target_points * 1.4)
            
        # Map to Option Premium Levels via Black-Scholes
        opt_levels = self.bs_engine.map_spot_to_option_levels(
            spot_entry=spot_close,
            spot_sl=spot_sl,
            spot_target=spot_target,
            strike=strike,
            option_type=option_type,
            dte_days=dte_days,
            iv=iv
        )
        
        entry_prem = opt_levels['entry_premium']
        sl_prem = opt_levels['sl_premium']
        target_prem = opt_levels['target_premium']
        
        # Second target option premium
        opt_levels_t2 = self.bs_engine.map_spot_to_option_levels(
            spot_entry=spot_close,
            spot_sl=spot_sl,
            spot_target=spot_target_2,
            strike=strike,
            option_type=option_type,
            dte_days=dte_days,
            iv=iv
        )
        
        # Check for Real Exchange Quote from Angel One
        from core.option_resolver import RESOLVER
        real_symbol, real_token, real_ltp = RESOLVER.get_real_option_quote(strike, option_type, broker=broker)
        
        delta = abs(opt_levels['delta'])
        contract_name = real_symbol if real_symbol else f"NIFTY {strike} {option_type}"
        
        if real_ltp > 0:
            # LIVE REAL-TIME EXCHANGE QUOTES
            entry_prem = round(real_ltp, 1)
            sl_prem = round(max(real_ltp - (sl_points * delta), 2.0), 1)
            target_prem = round(real_ltp + (target_points * delta), 1)
            target_prem_2 = round(real_ltp + (target_points * 1.4 * delta), 1)
            is_live_quote = True
        else:
            entry_prem = opt_levels['entry_premium']
            sl_prem = opt_levels['sl_premium']
            target_prem = opt_levels['target_premium']
            target_prem_2 = opt_levels_t2['target_premium']
            is_live_quote = False
        
        risk_per_share = max(entry_prem - sl_prem, 2.0)
        gain_per_share = max(target_prem - entry_prem, 3.0)
        
        risk_per_lot = risk_per_share * MARKET.lot_size
        gain_per_lot = gain_per_share * MARKET.lot_size
        gain_per_lot_2 = max(target_prem_2 - entry_prem, 0) * MARKET.lot_size
        
        # Technical Confluence Analysis
        confluences = []
        if option_type == "CE":
            if spot_close > vwap:
                confluences.append("Bullish: Trading above Intraday VWAP")
            if st_dir == 1:
                confluences.append(f"Bullish: SuperTrend Support @ {supertrend:.1f}")
            if rsi > 55:
                confluences.append(f"Bullish: RSI Momentum Expanding ({rsi:.1f})")
            if adx > 22:
                confluences.append(f"Trend Strength: ADX Strong ({adx:.1f})")
            if current_candle.get('orb_pos', 0) > 0:
                confluences.append("Breakout: Holding above 15-min Opening Range High")
        else:
            if spot_close < vwap:
                confluences.append("Bearish: Trading below Intraday VWAP")
            if st_dir == -1:
                confluences.append(f"Bearish: SuperTrend Resistance @ {supertrend:.1f}")
            if rsi < 45:
                confluences.append(f"Bearish: RSI Momentum Declining ({rsi:.1f})")
            if adx > 22:
                confluences.append(f"Trend Strength: ADX Strong ({adx:.1f})")
            if current_candle.get('orb_pos', 0) < 0:
                confluences.append("Breakdown: Holding below 15-min Opening Range Low")
                
        time_str = current_candle.get('time_str', 'N/A')
        
        return {
            "timestamp": time_str,
            "signal": signal,
            "action": "BUY OPTION",
            "contract": contract_name,
            "symbol_token": real_token or "0",
            "is_live_quote": is_live_quote,
            "strike": strike,
            "option_type": option_type,
            "spot_price": round(spot_close, 2),
            "spot_sl": round(spot_sl, 2),
            "spot_target": round(spot_target, 2),
            "spot_target_2": round(spot_target_2, 2),
            "entry_premium": entry_prem,
            "sl_premium": sl_prem,
            "target_premium": target_prem,
            "target_premium_2": target_prem_2,
            "risk_per_share": round(risk_per_share, 2),
            "gain_per_share": round(gain_per_share, 2),
            "risk_reward_ratio": f"1:{opt_levels['risk_reward_ratio']}",
            "lot_size": MARKET.lot_size,
            "risk_per_lot": round(risk_per_lot, 2),
            "gain_per_lot": round(gain_per_lot, 2),
            "gain_per_lot_2": round(gain_per_lot_2, 2),
            "delta": opt_levels['delta'],
            "theta_daily": opt_levels['theta'],
            "ai_confidence": f"{confidence * 100:.1f}%",
            "confluences": confluences,
            "management_plan": [
                f"Entry: Buy at ₹{entry_prem:.1f} (Option) / {spot_close:.1f} (Spot)",
                f"Stop Loss: Hard Stop at ₹{sl_prem:.1f} (Max loss ₹{risk_per_lot:.0f}/lot)",
                f"Target 1: Book 50% lots at ₹{target_prem:.1f} (+₹{gain_per_lot:.0f}/lot)",
                f"Target 2: Trail remaining lots to ₹{target_prem_2:.1f} (+₹{gain_per_lot_2:.0f}/lot)",
                f"Trailing Rule: Move Stop Loss to Cost (₹{entry_prem:.1f}) once Target 1 is hit",
                "Mandatory Exit: Close all open intraday positions before 15:15 IST"
            ]
        }

