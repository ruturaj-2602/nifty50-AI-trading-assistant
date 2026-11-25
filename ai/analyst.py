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
        
        # Calculate initial Greeks to get Option Delta for spot <-> premium mapping
        entry_greeks = self.bs_engine.calculate_greeks(spot_close, strike, dte_days, iv, option_type)
        delta = max(abs(entry_greeks.delta), 0.35)

        # Dynamic ATR-based Stop Loss in Spot Points (absorbs normal 5m candle wicks)
        sl_points = round(max(atr * 1.2, 25.0), 1)
        sl_opt_pts = round(sl_points * delta, 1)

        # Confidence-driven Option Premium Targets (in option points):
        # - Standard confidence (< 78%): T1 = 16 to 24 pts, T2 = 26 to 30 pts (lock profit before reversal)
        # - Full confidence (>= 78%): T1 = 22 to 24 pts (trail SL to cost), T2 = 50 pts runner
        if confidence >= 0.78:
            target1_opt_pts = 24.0 if confidence >= 0.85 else 22.0
            target2_opt_pts = 50.0
        else:
            conf_span = max(0.78 - STRATEGY.ml_confidence_threshold, 0.01)
            conf_factor = min(max((confidence - STRATEGY.ml_confidence_threshold) / conf_span, 0.0), 1.0)
            target1_opt_pts = round(16.0 + conf_factor * 8.0, 1)   # Strictly 16.0 - 24.0 pts
            target2_opt_pts = round(26.0 + conf_factor * 4.0, 1)   # Strictly 26.0 - 30.0 pts

        # Convert Option Point targets into NIFTY Spot Points via Delta
        target_points = round(target1_opt_pts / delta, 1)
        target_points_2 = round(target2_opt_pts / delta, 1)

        if option_type == "CE":
            spot_sl = spot_close - sl_points
            spot_target = spot_close + target_points
            spot_target_2 = spot_close + target_points_2
        else:
            spot_sl = spot_close + sl_points
            spot_target = spot_close - target_points
            spot_target_2 = spot_close - target_points_2

        # Check for Real Exchange Quote from Angel One
        from core.option_resolver import RESOLVER
        real_symbol, real_token, real_ltp = RESOLVER.get_real_option_quote(strike, option_type, broker=broker)

        contract_name = real_symbol if real_symbol else f"NIFTY {strike} {option_type}"

        if real_ltp > 0:
            # LIVE REAL-TIME EXCHANGE QUOTES
            entry_prem = round(real_ltp, 1)
            is_live_quote = True
        else:
            entry_prem = round(entry_greeks.price, 1)
            is_live_quote = False

        sl_prem = round(max(entry_prem - sl_opt_pts, 2.0), 1)
        target_prem = round(entry_prem + target1_opt_pts, 1)
        target_prem_2 = round(entry_prem + target2_opt_pts, 1)

        risk_per_share = max(entry_prem - sl_prem, 2.0)
        gain_per_share = max(target_prem - entry_prem, 3.0)
        rr_ratio = round(gain_per_share / risk_per_share, 2)

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
            "risk_reward_ratio": f"1:{rr_ratio}",
            "lot_size": MARKET.lot_size,
            "risk_per_lot": round(risk_per_lot, 2),
            "gain_per_lot": round(gain_per_lot, 2),
            "gain_per_lot_2": round(gain_per_lot_2, 2),
            "delta": round(entry_greeks.delta, 3),
            "theta_daily": round(entry_greeks.theta, 2),
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

