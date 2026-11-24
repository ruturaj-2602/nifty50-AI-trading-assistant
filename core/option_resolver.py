"""
Angel One Real Option Contract & LTP Resolver.
Resolves live NIFTY weekly option contracts, tokens, and real-time exchange LTP.
"""
import os
import json
import urllib.request
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data_cache")
CACHE_FILE = os.path.join(CACHE_DIR, "nifty_options_instruments.json")
SCRIP_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"

class OptionResolver:
    _instance = None
    _instruments = []

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OptionResolver, cls).__new__(cls)
            cls._instance._load_instruments()
        return cls._instance

    def _load_instruments(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        # Check cache freshness (refresh if older than 24 hours)
        need_download = True
        if os.path.exists(CACHE_FILE):
            try:
                mtime = os.path.getmtime(CACHE_FILE)
                if (datetime.now().timestamp() - mtime) < 86400:
                    with open(CACHE_FILE, "r") as f:
                        self._instruments = json.load(f)
                    need_download = False
            except Exception:
                need_download = True

        if need_download:
            try:
                req = urllib.request.Request(SCRIP_URL, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.load(resp)
                    self._instruments = [
                        x for x in data
                        if x.get("exch_seg") == "NFO" and x.get("name") == "NIFTY" and x.get("instrumenttype") == "OPTIDX"
                    ]
                with open(CACHE_FILE, "w") as f:
                    json.dump(self._instruments, f)
            except Exception as e:
                # If offline and old cache exists, keep using old cache
                if os.path.exists(CACHE_FILE) and not self._instruments:
                    try:
                        with open(CACHE_FILE, "r") as f:
                            self._instruments = json.load(f)
                    except Exception:
                        pass

    def get_nearest_contract(self, strike: int, option_type: str) -> Optional[Dict[str, Any]]:
        """Resolves the nearest active weekly expiry contract for a given strike and CE/PE."""
        target_strike = f"{strike}00.000000"
        candidates = [
            x for x in self._instruments
            if x.get("strike") == target_strike and x.get("symbol", "").endswith(option_type)
        ]
        if not candidates:
            return None

        today = datetime.now().date()
        def parse_exp(x):
            try:
                return datetime.strptime(x["expiry"], "%d%b%Y").date()
            except Exception:
                return datetime.max.date()

        valid = [x for x in candidates if parse_exp(x) >= today]
        valid.sort(key=parse_exp)
        return valid[0] if valid else None

    def get_real_option_quote(
        self,
        strike: int,
        option_type: str,
        broker=None
    ) -> Tuple[Optional[str], Optional[str], float]:
        """
        Returns (tradingsymbol, token, real_ltp).
        If broker is connected, fetches the real exchange LTP.
        """
        contract = self.get_nearest_contract(strike, option_type)
        if not contract:
            return None, None, 0.0

        symbol = contract.get("symbol", "")
        token = str(contract.get("token", ""))

        if broker and hasattr(broker, "get_ltp") and getattr(broker, "is_connected", False):
            real_ltp = broker.get_ltp(symbol=symbol, symbol_token=token, exchange="NFO")
            if real_ltp > 0:
                return symbol, token, float(real_ltp)

        return symbol, token, 0.0

RESOLVER = OptionResolver()
