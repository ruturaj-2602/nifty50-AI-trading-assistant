"""
Base Broker Interface and Paper Trading Broker.
Standardizes order execution, quote fetching, and position management across Indian brokers.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import os

from config import MARKET

@dataclass
class OrderResult:
    order_id: str
    status: str       # "COMPLETE", "REJECTED", "CANCELLED"
    symbol: str
    action: str       # "BUY", "SELL"
    quantity: int
    price: float
    message: str = ""

@dataclass
class Position:
    symbol: str
    strike: int
    option_type: str
    quantity: int
    lots: int
    buy_price: float
    current_price: float
    unrealized_pnl: float
    sl_price: float
    target_price: float
    target_2_price: float
    sl_trailed: bool = False

class BaseBroker(ABC):
    @abstractmethod
    def connect(self) -> bool:
        pass

    @abstractmethod
    def get_ltp(self, symbol: str) -> float:
        pass

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        action: str,
        quantity: int,
        order_type: str = "MARKET",
        price: float = 0.0
    ) -> OrderResult:
        pass

    @abstractmethod
    def get_positions(self) -> List[Position]:
        pass

    @abstractmethod
    def square_off_all(self) -> List[OrderResult]:
        pass

class PaperBroker(BaseBroker):
    """
    Realistic Local Paper Broker.
    Simulates real execution with 0.5% slippage, trade ledger persistence,
    and automatic PnL calculations.
    """
    def __init__(self, initial_capital: float = 100000.0, ledger_file: str = "data_cache/paper_ledger.json"):
        self.capital = initial_capital
        self.ledger_file = ledger_file
        self.positions: Dict[str, Position] = {}
        self.order_history: List[Dict[str, Any]] = []
        self._load_ledger()

    def connect(self) -> bool:
        return True

    def get_ltp(self, symbol: str) -> float:
        return 0.0

    def place_order(
        self,
        symbol: str,
        action: str,
        quantity: int,
        order_type: str = "MARKET",
        price: float = 0.0,
        sl: float = 0.0,
        target: float = 0.0,
        target_2: float = 0.0,
        strike: int = 0,
        option_type: str = "CE"
    ) -> OrderResult:
        order_id = f"PAPER_{datetime.now().strftime('%Y%m%d%H%M%S%f')[:17]}"
        
        # Apply 0.5% realistic slippage
        exec_price = price * (1.005 if action == "BUY" else 0.995) if price > 0 else 100.0
        
        if action == "BUY":
            req_capital = exec_price * quantity
            if req_capital > self.capital:
                return OrderResult(order_id, "REJECTED", symbol, action, quantity, 0.0, "Insufficient paper capital")
                
            self.capital -= req_capital
            pos = Position(
                symbol=symbol,
                strike=strike,
                option_type=option_type,
                quantity=quantity,
                lots=max(1, quantity // MARKET.lot_size),
                buy_price=round(exec_price, 2),
                current_price=round(exec_price, 2),
                unrealized_pnl=0.0,
                sl_price=round(sl, 2),
                target_price=round(target, 2),
                target_2_price=round(target_2, 2)
            )
            self.positions[symbol] = pos
            msg = f"Bought {quantity} qty of {symbol} @ ₹{exec_price:.2f}"
        else: # SELL
            if symbol in self.positions:
                pos = self.positions.pop(symbol)
                gross_pnl = (exec_price - pos.buy_price) * quantity
                self.capital += (exec_price * quantity)
                msg = f"Closed {quantity} qty of {symbol} @ ₹{exec_price:.2f} (Net PnL: ₹{gross_pnl:+,.1f})"
            else:
                return OrderResult(order_id, "REJECTED", symbol, action, quantity, 0.0, "No open position to exit")

        record = {
            "order_id": order_id,
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "action": action,
            "quantity": quantity,
            "price": round(exec_price, 2),
            "status": "COMPLETE",
            "message": msg
        }
        self.order_history.append(record)
        self._save_ledger()
        return OrderResult(order_id, "COMPLETE", symbol, action, quantity, round(exec_price, 2), msg)

    def get_positions(self) -> List[Position]:
        return list(self.positions.values())

    def square_off_all(self) -> List[OrderResult]:
        results = []
        for symbol, pos in list(self.positions.items()):
            res = self.place_order(symbol, "SELL", pos.quantity, price=pos.current_price)
            results.append(res)
        return results

    def _save_ledger(self):
        os.makedirs(os.path.dirname(self.ledger_file), exist_ok=True)
        data = {
            "capital": self.capital,
            "positions": {k: v.__dict__ for k, v in self.positions.items()},
            "order_history": self.order_history
        }
        with open(self.ledger_file, "w") as f:
            json.dump(data, f, indent=2)

    def _load_ledger(self):
        if os.path.exists(self.ledger_file):
            try:
                with open(self.ledger_file, "r") as f:
                    data = json.load(f)
                    self.capital = data.get("capital", self.capital)
                    self.order_history = data.get("order_history", [])
            except Exception:
                pass

