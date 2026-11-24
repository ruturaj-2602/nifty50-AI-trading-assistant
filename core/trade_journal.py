"""
Trade Journal & Daily Performance Reporting System.
Tracks all intraday suggested and executed trades, records entries, exits,
partial profit bookings, and computes the complete End-of-Day (EOD) P&L breakdown.
Persists trades to disk in reports/trades_YYYY-MM-DD.json.
"""
import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")

class TradeJournal:
    def __init__(self, journal_date: Optional[str] = None):
        self.date_str = journal_date or datetime.now().strftime("%Y-%m-%d")
        os.makedirs(REPORTS_DIR, exist_ok=True)
        self.file_path = os.path.join(REPORTS_DIR, f"trades_{self.date_str}.json")
        self.trades: List[Dict[str, Any]] = self._load()

    def _load(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, "r") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save(self):
        try:
            with open(self.file_path, "w") as f:
                json.dump(self.trades, f, indent=2)
        except Exception as e:
            print(f"[Journal] Error saving trades: {e}")

    def record_entry(self, trade_data: Dict[str, Any]) -> int:
        """Records a new trade entry. Returns trade ID."""
        trade_id = len(self.trades) + 1
        entry_record = {
            "id": trade_id,
            "contract": trade_data.get("contract", "NIFTY"),
            "option_type": trade_data.get("option_type", "PE"),
            "strike": trade_data.get("strike", 0),
            "lots": trade_data.get("lots", 1),
            "quantity": trade_data.get("quantity", 65),
            "entry_time": trade_data.get("entry_time", datetime.now().strftime("%H:%M:%S")),
            "entry_premium": round(float(trade_data.get("entry_premium", 0.0)), 2),
            "spot_entry": round(float(trade_data.get("entry_spot", 0.0)), 2),
            "spot_sl": round(float(trade_data.get("spot_sl", 0.0)), 2),
            "spot_target": round(float(trade_data.get("spot_target", 0.0)), 2),
            "spot_target_2": round(float(trade_data.get("spot_target_2", 0.0)), 2),
            "sl_premium": round(float(trade_data.get("sl_premium", 0.0)), 2),
            "target_premium": round(float(trade_data.get("target_premium", 0.0)), 2),
            "target_premium_2": round(float(trade_data.get("target_premium_2", 0.0)), 2),
            "ai_confidence": trade_data.get("ai_confidence", "N/A"),
            "status": "OPEN",
            "target1_hit": False,
            "target1_profit": 0.0,
            "exit_time": None,
            "exit_premium": None,
            "exit_reason": None,
            "points_pnl": 0.0,
            "gross_pnl": 0.0,
            "taxes_and_charges": 0.0,
            "net_pnl": 0.0
        }
        self.trades.append(entry_record)
        self._save()
        return trade_id

    def record_target1(self, trade_id: int, target_premium: float):
        """Marks Target 1 hit and books 50% lots profit."""
        for t in self.trades:
            if t["id"] == trade_id and t["status"] == "OPEN":
                t["target1_hit"] = True
                gain_pts = max(target_premium - t["entry_premium"], 0.0)
                # 50% lots booked
                t["target1_profit"] = round(gain_pts * (t["quantity"] * 0.5), 2)
                self._save()
                break

    def record_exit(self, trade_id: int, exit_premium: float, exit_reason: str):
        """Records full trade exit, computes final P&L and friction charges."""
        for t in self.trades:
            if t["id"] == trade_id and t["status"] == "OPEN":
                t["status"] = "CLOSED"
                t["exit_time"] = datetime.now().strftime("%H:%M:%S")
                t["exit_premium"] = round(float(exit_premium), 2)
                t["exit_reason"] = exit_reason
                
                entry_p = t["entry_premium"]
                exit_p = float(exit_premium)
                qty = t["quantity"]
                
                if t.get("target1_hit"):
                    t1_pnl = t.get("target1_profit", 0.0)
                    runner_pts = exit_p - entry_p
                    runner_pnl = runner_pts * (qty * 0.5)
                    gross = t1_pnl + runner_pnl
                    pts = ((t["target_premium"] - entry_p) + runner_pts) / 2.0
                else:
                    pts = exit_p - entry_p
                    gross = pts * qty

                # Realistic Indian market taxes & brokerage:
                # Flat ₹40 brokerage (₹20 buy + ₹20 sell) + STT (0.0625% on sell) + GST 18% + Exchange 0.05%
                stt = exit_p * qty * 0.000625
                brokerage = 40.0
                exchange_fees = (entry_p + exit_p) * qty * 0.0005
                gst = (brokerage + exchange_fees) * 0.18
                total_charges = round(brokerage + stt + exchange_fees + gst, 2)
                
                net = gross - total_charges
                
                t["points_pnl"] = round(pts, 2)
                t["gross_pnl"] = round(gross, 2)
                t["taxes_and_charges"] = total_charges
                t["net_pnl"] = round(net, 2)
                self._save()
                break

    def get_eod_summary(self) -> Dict[str, Any]:
        """Calculates total day summary metrics."""
        total_trades = len(self.trades)
        closed_trades = [t for t in self.trades if t.get("status") == "CLOSED"]
        
        wins = [t for t in closed_trades if t.get("net_pnl", 0) > 0]
        losses = [t for t in closed_trades if t.get("net_pnl", 0) < 0]
        breakevens = [t for t in closed_trades if t.get("net_pnl", 0) == 0]
        
        gross_pnl = sum(t.get("gross_pnl", 0) for t in closed_trades)
        total_charges = sum(t.get("taxes_and_charges", 0) for t in closed_trades)
        net_pnl = sum(t.get("net_pnl", 0) for t in closed_trades)
        
        win_rate = (len(wins) / len(closed_trades) * 100) if closed_trades else 0.0
        
        return {
            "date": self.date_str,
            "total_trades": total_trades,
            "closed_trades": len(closed_trades),
            "wins": len(wins),
            "losses": len(losses),
            "breakevens": len(breakevens),
            "win_rate_pct": round(win_rate, 1),
            "gross_pnl": round(gross_pnl, 2),
            "total_charges": round(total_charges, 2),
            "net_pnl": round(net_pnl, 2),
            "trades": self.trades
        }
