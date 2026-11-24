"""
Options Pricing and Greeks Engine using Black-Scholes-Merton.
Provides realistic option premium estimation, Greeks, strike selection,
and spot-to-option SL/Target mapping for NIFTY 50 weekly/monthly options.
"""
import math
from dataclasses import dataclass
from typing import Literal, Tuple
from scipy.stats import norm
import numpy as np

@dataclass
class OptionGreeks:
    price: float
    delta: float
    gamma: float
    theta: float      # Daily theta decay
    vega: float       # Change per 1% change in IV
    intrinsic_value: float
    time_value: float

class BlackScholesEngine:
    def __init__(self, risk_free_rate: float = 0.068):
        self.r = risk_free_rate

    def calculate_greeks(
        self,
        spot: float,
        strike: float,
        dte_days: float, # Days to expiry (can be fractional, e.g. 0.5 = intraday afternoon)
        iv: float,       # Implied Volatility (e.g., 0.14 = 14%)
        option_type: Literal["CE", "PE"]
    ) -> OptionGreeks:
        """Calculate Black-Scholes premium and Greeks."""
        # Minimum time to expiry to avoid numerical division by zero
        t = max(dte_days / 365.0, 0.0001)
        sigma = max(iv, 0.01)
        
        d1 = (math.log(spot / strike) + (self.r + 0.5 * sigma ** 2) * t) / (sigma * math.sqrt(t))
        d2 = d1 - sigma * math.sqrt(t)
        
        pdf_d1 = norm.pdf(d1)
        
        if option_type == "CE":
            price = spot * norm.cdf(d1) - strike * math.exp(-self.r * t) * norm.cdf(d2)
            delta = norm.cdf(d1)
            intrinsic = max(0.0, spot - strike)
            # Theta per day (divide by 365)
            theta = (-(spot * pdf_d1 * sigma) / (2 * math.sqrt(t)) - self.r * strike * math.exp(-self.r * t) * norm.cdf(d2)) / 365.0
        else:
            price = strike * math.exp(-self.r * t) * norm.cdf(-d2) - spot * norm.cdf(-d1)
            delta = norm.cdf(d1) - 1.0
            intrinsic = max(0.0, strike - spot)
            theta = (-(spot * pdf_d1 * sigma) / (2 * math.sqrt(t)) + self.r * strike * math.exp(-self.r * t) * norm.cdf(-d2)) / 365.0
            
        gamma = pdf_d1 / (spot * sigma * math.sqrt(t))
        vega = (spot * math.sqrt(t) * pdf_d1) / 100.0  # Per 1% IV change
        time_value = max(0.0, price - intrinsic)
        
        return OptionGreeks(
            price=max(price, 0.5), # minimum tick price
            delta=delta,
            gamma=gamma,
            theta=theta,
            vega=vega,
            intrinsic_value=intrinsic,
            time_value=time_value
        )

    def select_strike(
        self,
        spot: float,
        option_type: Literal["CE", "PE"],
        selection_mode: Literal["ATM", "ITM_1", "OTM_1"] = "ATM",
        strike_gap: int = 50
    ) -> int:
        """Select strike price according to mode (ATM, ITM_1, OTM_1)."""
        atm_strike = int(round(spot / strike_gap) * strike_gap)
        
        if selection_mode == "ATM":
            return atm_strike
        elif selection_mode == "ITM_1":
            return atm_strike - strike_gap if option_type == "CE" else atm_strike + strike_gap
        elif selection_mode == "OTM_1":
            return atm_strike + strike_gap if option_type == "CE" else atm_strike - strike_gap
        return atm_strike

    def map_spot_to_option_levels(
        self,
        spot_entry: float,
        spot_sl: float,
        spot_target: float,
        strike: int,
        option_type: Literal["CE", "PE"],
        dte_days: float = 3.0,
        iv: float = 0.14
    ) -> dict:
        """
        Maps underlying NIFTY spot entry, SL, and Target directly to option premium prices
        using 2nd-order Taylor expansion (Delta + 0.5 * Gamma * dS^2) and exact BS repricing.
        """
        entry_greeks = self.calculate_greeks(spot_entry, strike, dte_days, iv, option_type)
        entry_premium = entry_greeks.price
        
        # Exact BS calculation at SL and Target spot levels
        sl_greeks = self.calculate_greeks(spot_sl, strike, dte_days, iv, option_type)
        target_greeks = self.calculate_greeks(spot_target, strike, dte_days, iv, option_type)
        
        sl_premium = max(sl_greeks.price, 0.5)
        target_premium = target_greeks.price
        
        # Calculate premium risk and reward
        risk_per_share = max(entry_premium - sl_premium, 1.0)
        reward_per_share = max(target_premium - entry_premium, 1.0)
        
        rr_ratio = reward_per_share / risk_per_share
        
        return {
            "strike": strike,
            "option_type": option_type,
            "contract_name": f"NIFTY {strike} {option_type}",
            "spot_entry": round(spot_entry, 2),
            "spot_sl": round(spot_sl, 2),
            "spot_target": round(spot_target, 2),
            "entry_premium": round(entry_premium, 2),
            "sl_premium": round(sl_premium, 2),
            "target_premium": round(target_premium, 2),
            "risk_per_share": round(risk_per_share, 2),
            "reward_per_share": round(reward_per_share, 2),
            "risk_reward_ratio": round(rr_ratio, 2),
            "delta": round(entry_greeks.delta, 3),
            "theta": round(entry_greeks.theta, 2),
            "iv_pct": round(iv * 100, 1),
            "dte_days": round(dte_days, 1)
        }

