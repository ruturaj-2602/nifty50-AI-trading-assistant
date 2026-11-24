"""
Institutional Risk and Money Management Engine for NIFTY Options.
Enforces position sizing, daily drawdowns, slippage, and Indian statutory taxes/charges.
"""
from dataclasses import dataclass
from typing import Dict, Any, Tuple
from config import RISK, STRATEGY, MARKET

@dataclass
class PositionSizeResult:
    lots: int
    quantity: int
    capital_required: float
    max_risk_amount: float
    is_valid: bool
    rejection_reason: str = ""

class RiskManager:
    def __init__(self, capital: float = RISK.capital):
        self.initial_capital = capital
        self.current_capital = capital
        self.daily_pnl = 0.0
        self.daily_trade_count = 0
        self.current_date = None

    def reset_daily_metrics_if_new_day(self, trade_date):
        """Resets daily circuit breakers on a new trading session."""
        if self.current_date != trade_date:
            self.current_date = trade_date
            self.daily_pnl = 0.0
            self.daily_trade_count = 0

    def can_take_trade(self) -> Tuple[bool, str]:
        """Check if daily circuit breakers or trade limits are breached."""
        if self.daily_trade_count >= RISK.max_trades_per_day:
            return False, f"Max daily trade limit ({RISK.max_trades_per_day}) reached."
        if self.daily_pnl <= -abs(RISK.max_daily_loss):
            return False, f"Daily max loss circuit breaker (-₹{abs(RISK.max_daily_loss)}) hit. Trading halted for day."
        min_allowed_capital = max(3000.0, self.initial_capital * 0.25)
        if self.current_capital < min_allowed_capital:
            return False, f"Insufficient capital remaining (< ₹{min_allowed_capital:,.0f})."
        return True, "Approved"

    def calculate_position_size(
        self,
        entry_premium: float,
        risk_per_share: float
    ) -> PositionSizeResult:
        """
        Calculates position size in NIFTY lots based on strict risk-per-trade budgeting.
        Supports single-lot trading for accounts from ₹15,000 upwards.
        """
        can_trade, reason = self.can_take_trade()
        if not can_trade:
            return PositionSizeResult(0, 0, 0.0, 0.0, False, reason)

        one_lot_capital = entry_premium * MARKET.lot_size
        if one_lot_capital > self.current_capital:
            return PositionSizeResult(0, 0, 0.0, 0.0, False, f"Required margin (₹{one_lot_capital:,.0f}) exceeds available capital (₹{self.current_capital:,.0f})")

        # If single lot mode or small account
        if getattr(RISK, 'fixed_lots', 0) == 1 or self.current_capital <= 30000:
            lots = 1
        else:
            max_shares_by_risk = RISK.target_risk_per_trade / max(risk_per_share, 1.0)
            max_shares_by_capital = min(RISK.max_capital_per_trade, self.current_capital * 0.50) / entry_premium
            allowed_shares = min(max_shares_by_risk, max_shares_by_capital)
            lots = max(1, int(allowed_shares // MARKET.lot_size))
                
        quantity = lots * MARKET.lot_size
        capital_req = quantity * entry_premium
        risk_amt = quantity * risk_per_share
        
        return PositionSizeResult(
            lots=lots,
            quantity=quantity,
            capital_required=capital_req,
            max_risk_amount=risk_amt,
            is_valid=True
        )

    def calculate_costs(
        self,
        buy_price: float,
        sell_price: float,
        quantity: int
    ) -> Dict[str, float]:
        """
        Calculates exact Indian market transaction charges & slippage:
        - Slippage: 0.5% on entry & exit
        - Brokerage: ₹20 buy + ₹20 sell = ₹40 flat
        - STT: 0.0625% on sell turnover (options)
        - Exchange turnover charges: 0.05%
        - SEBI turnover charges: ₹10/crore
        - Stamp duty: 0.003% on buy turnover
        - GST: 18% on (Brokerage + Exchange charges + SEBI)
        """
        buy_turnover = buy_price * quantity
        sell_turnover = sell_price * quantity
        total_turnover = buy_turnover + sell_turnover
        
        # Slippage cost (buying 0.5% higher, selling 0.5% lower)
        slippage = (buy_turnover * STRATEGY.slippage_pct) + (sell_turnover * STRATEGY.slippage_pct)
        
        brokerage = STRATEGY.brokerage_per_order * 2.0
        stt = sell_turnover * STRATEGY.stt_rate
        exchange_charges = total_turnover * STRATEGY.exchange_charges
        sebi_charges = total_turnover * 0.000001
        stamp_duty = buy_turnover * 0.00003
        gst = (brokerage + exchange_charges + sebi_charges) * STRATEGY.gst_rate
        
        total_charges = brokerage + stt + exchange_charges + sebi_charges + stamp_duty + gst + slippage
        
        return {
            "slippage": slippage,
            "brokerage": brokerage,
            "stt": stt,
            "exchange_charges": exchange_charges,
            "sebi_charges": sebi_charges,
            "stamp_duty": stamp_duty,
            "gst": gst,
            "total_costs": total_charges
        }

    def update_capital(self, net_pnl: float):
        """Update running capital and daily PnL."""
        self.current_capital += net_pnl
        self.daily_pnl += net_pnl
        self.daily_trade_count += 1

from typing import Tuple as Tuple_can_trade

