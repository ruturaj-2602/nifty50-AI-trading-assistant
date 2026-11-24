"""
Angel One SmartAPI Broker Adapter for NIFTY Options.
Automates session generation with dynamic TOTP, order placement (NFO INTRADAY),
and position management via the official SmartConnect SDK.
"""
import os
import json
import pyotp
import logging
import logzero
from typing import Dict, Any, List, Optional

# Suppress internal SmartConnect error log spam
logzero.loglevel(logging.CRITICAL)
from config import BROKER, MARKET, load_dotenv
from brokers.base_broker import BaseBroker, OrderResult, Position

class AngelOneBroker(BaseBroker):
    def __init__(
        self,
        api_key: Optional[str] = None,
        client_code: Optional[str] = None,
        pin: Optional[str] = None,
        totp_key: Optional[str] = None
    ):
        load_dotenv()
        self.api_key = api_key or os.getenv("ANGEL_API_KEY", BROKER.angel_api_key)
        self.client_code = client_code or os.getenv("ANGEL_CLIENT_CODE", BROKER.angel_client_code)
        self.pin = pin or os.getenv("ANGEL_PIN", BROKER.angel_pin)
        self.totp_key = totp_key or os.getenv("ANGEL_TOTP_KEY", BROKER.angel_totp_key)
        
        self.smart_api = None
        self.is_connected = False
        self.jwt_token = None
        self.refresh_token = None
        self.feed_token = None
        self.token_cache = {}

    def connect(self) -> bool:
        """
        Connects and authenticates with Angel One SmartAPI using TOTP.
        """
        try:
            from SmartApi import SmartConnect
            self.smart_api = SmartConnect(api_key=self.api_key)
            
            # Generate current TOTP code
            totp = pyotp.TOTP(self.totp_key)
            current_totp = totp.now()
            
            session_data = self.smart_api.generateSession(
                clientCode=self.client_code,
                password=self.pin,
                totp=current_totp
            )
            
            if session_data.get("status"):
                self.jwt_token = session_data["data"]["jwtToken"]
                self.refresh_token = session_data["data"]["refreshToken"]
                self.feed_token = self.smart_api.getfeedToken()
                self.is_connected = True
                print(f"[AngelOneBroker] Authenticated successfully as Client: {self.client_code}")
                return True
            else:
                msg = session_data.get("message", "Unknown login failure")
                print(f"[AngelOneBroker] Login failed: {msg}")
                return False
        except Exception as e:
            print(f"[AngelOneBroker] Connection error: {e}")
            return False

    def get_ltp(self, symbol: str, symbol_token: str = "", exchange: str = "NFO") -> float:
        """Fetches Last Traded Price for a symbol token."""
        if not self.is_connected:
            return 0.0
        try:
            quote = self.smart_api.ltpData(exchange=exchange, tradingsymbol=symbol, symboltoken=symbol_token)
            if quote.get("status") and "data" in quote:
                return float(quote["data"]["ltp"])
            return 0.0
        except Exception as e:
            print(f"[AngelOneBroker] Error fetching LTP for {symbol}: {e}")
            return 0.0

    def place_order(
        self,
        symbol: str,
        action: str,
        quantity: int,
        order_type: str = "MARKET",
        price: float = 0.0,
        symbol_token: str = "0",
        **kwargs
    ) -> OrderResult:
        """
        Places NFO INTRADAY order on Angel One.
        """
        if not self.is_connected:
            return OrderResult("ERR", "REJECTED", symbol, action, quantity, price, "Angel One not connected")
            
        try:
            order_params = {
                "variety": "NORMAL",
                "tradingsymbol": symbol,
                "symboltoken": symbol_token,
                "transactiontype": "BUY" if action == "BUY" else "SELL",
                "exchange": "NFO",
                "ordertype": "MARKET" if order_type == "MARKET" else "LIMIT",
                "producttype": "INTRADAY",
                "duration": "DAY",
                "price": str(price) if order_type == "LIMIT" else "0",
                "squareoff": "0",
                "stoploss": "0",
                "quantity": str(quantity)
            }
            res = self.smart_api.placeOrder(order_params)
            
            if res.get("status"):
                order_id = res.get("data", {}).get("orderid", "OK")
                return OrderResult(order_id, "COMPLETE", symbol, action, quantity, price, "Order placed successfully")
            else:
                err_msg = res.get("message", "Order placement rejected")
                return OrderResult("ERR", "REJECTED", symbol, action, quantity, price, err_msg)
        except Exception as e:
            return OrderResult("ERR", "REJECTED", symbol, action, quantity, price, str(e))

    def get_positions(self) -> List[Position]:
        """Fetches current intraday positions."""
        if not self.is_connected:
            return []
        try:
            pos_resp = self.smart_api.position()
            positions = []
            if pos_resp.get("status") and "data" in pos_resp:
                for p in pos_resp["data"]:
                    net_qty = int(p.get("netqty", 0))
                    if net_qty != 0:
                        positions.append(Position(
                            symbol=p.get("tradingsymbol", ""),
                            strike=0,
                            option_type="CE" if "CE" in p.get("tradingsymbol", "") else "PE",
                            quantity=net_qty,
                            lots=max(1, abs(net_qty) // MARKET.lot_size),
                            buy_price=float(p.get("buyavgprice", 0.0)),
                            current_price=float(p.get("ltp", 0.0)),
                            unrealized_pnl=float(p.get("pnl", 0.0)),
                            sl_price=0.0,
                            target_price=0.0,
                            target_2_price=0.0
                        ))
            return positions
        except Exception as e:
            print(f"[AngelOneBroker] Error getting positions: {e}")
            return []

    def square_off_all(self) -> List[OrderResult]:
        """Squares off all active intraday positions."""
        results = []
        for pos in self.get_positions():
            action = "SELL" if pos.quantity > 0 else "BUY"
            res = self.place_order(pos.symbol, action, abs(pos.quantity))
            results.append(res)
        return results
