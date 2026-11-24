"""
Zerodha Kite Connect Broker Adapter for NIFTY Options.
Automates order routing, quote retrieval, and margin management via Kite Connect API.
"""
from typing import Dict, Any, List, Optional
from brokers.base_broker import BaseBroker, OrderResult, Position

class ZerodhaBroker(BaseBroker):
    def __init__(self, api_key: str = "", api_secret: str = "", access_token: str = ""):
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        self.kite = None
        self.is_connected = False

    def connect(self) -> bool:
        """Initializes Kite Connect session."""
        try:
            from kiteconnect import KiteConnect
            self.kite = KiteConnect(api_key=self.api_key)
            if self.access_token:
                self.kite.set_access_token(self.access_token)
                self.is_connected = True
                return True
            print("[ZerodhaBroker] Access token not provided. Please authenticate Kite login.")
            return False
        except ImportError:
            print("[ZerodhaBroker] 'kiteconnect' package not installed. Run: pip install kiteconnect")
            return False
        except Exception as e:
            print(f"[ZerodhaBroker] Connection failed: {e}")
            return False

    def get_ltp(self, symbol: str) -> float:
        """Fetches LTP for NFO contract e.g. 'NFO:NIFTY24DEC24100CE'."""
        if not self.is_connected:
            return 0.0
        try:
            quotes = self.kite.ltp([symbol])
            return float(quotes[symbol]['last_price'])
        except Exception as e:
            print(f"[ZerodhaBroker] Error fetching LTP for {symbol}: {e}")
            return 0.0

    def place_order(
        self,
        symbol: str,
        action: str,
        quantity: int,
        order_type: str = "MARKET",
        price: float = 0.0
    ) -> OrderResult:
        """
        Places Intraday MIS order on NSE NFO.
        """
        if not self.is_connected:
            return OrderResult("ERR", "REJECTED", symbol, action, quantity, price, "Kite not connected")
            
        try:
            from kiteconnect import KiteConnect
            tx_type = self.kite.TRANSACTION_TYPE_BUY if action == "BUY" else self.kite.TRANSACTION_TYPE_SELL
            ord_type = self.kite.ORDER_TYPE_MARKET if order_type == "MARKET" else self.kite.ORDER_TYPE_LIMIT
            
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=self.kite.EXCHANGE_NFO,
                tradingsymbol=symbol,
                transaction_type=tx_type,
                quantity=quantity,
                product=self.kite.PRODUCT_MIS, # Intraday product
                order_type=ord_type,
                price=price if order_type == "LIMIT" else None
            )
            return OrderResult(str(order_id), "COMPLETE", symbol, action, quantity, price, "Order placed successfully")
        except Exception as e:
            return OrderResult("ERR", "REJECTED", symbol, action, quantity, price, str(e))

    def get_positions(self) -> List[Position]:
        """Fetches open net intraday positions."""
        if not self.is_connected:
            return []
        try:
            net_positions = self.kite.positions().get("net", [])
            results = []
            for p in net_positions:
                if p.get("product") == "MIS" and p.get("quantity", 0) != 0:
                    results.append(Position(
                        symbol=p['tradingsymbol'],
                        strike=0,
                        option_type="CE" if "CE" in p['tradingsymbol'] else "PE",
                        quantity=p['quantity'],
                        lots=abs(p['quantity']) // 25,
                        buy_price=float(p['average_price']),
                        current_price=float(p['last_price']),
                        unrealized_pnl=float(p['pnl']),
                        sl_price=0.0,
                        target_price=0.0,
                        target_2_price=0.0
                    ))
            return results
        except Exception as e:
            print(f"[ZerodhaBroker] Error fetching positions: {e}")
            return []

    def square_off_all(self) -> List[OrderResult]:
        """Emergency or 15:15 square off for all open MIS positions."""
        results = []
        for pos in self.get_positions():
            action = "SELL" if pos.quantity > 0 else "BUY"
            res = self.place_order(pos.symbol, action, abs(pos.quantity))
            results.append(res)
        return results

