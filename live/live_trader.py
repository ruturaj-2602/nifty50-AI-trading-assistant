"""
Live Market Execution and Real-Time Scanner Engine for NIFTY Options.
Runs during live NSE market hours (09:15 to 15:30 IST).
Handles real-time candle ingestion, ML scoring, auto-trading or alert dispatch,
live trailing SL updates, and mandatory 15:15 IST square-off.
"""
import os
import time
from datetime import datetime, time as dtime
from typing import Optional, Dict, Any
import pandas as pd

from config import MARKET, STRATEGY, RISK, BROKER
from core.indicators import add_all_indicators
from core.options_pricer import BlackScholesEngine
from core.risk_manager import RiskManager
from ai.features import engineer_features
from ai.model import IntradaySignalClassifier
from ai.analyst import AIAnalyst
from brokers.base_broker import BaseBroker, PaperBroker
from brokers.angelone_adapter import AngelOneBroker
from ui.cli_view import display_signal_card, console
from live.notifier import (
    format_telegram_alert,
    format_target1_alert,
    format_target2_alert,
    format_stoploss_alert,
    format_time_squareoff_alert,
    send_telegram_alert,
    send_whatsapp_alert
)

class LiveMarketRunner:
    def __init__(
        self,
        broker: Optional[BaseBroker] = None,
        broker_type: str = "paper",
        auto_trade: bool = False,
        poll_interval_sec: int = 15
    ):
        if broker is not None:
            self.broker = broker
        elif broker_type.lower() == "angel" or BROKER.mode == "ANGEL_ONE":
            console.print("[cyan]Connecting to Angel One SmartAPI...[/cyan]")
            self.broker = AngelOneBroker()
            connected = self.broker.connect()
            if not connected:
                console.print("[yellow]Angel One connection could not authenticate. Falling back to PaperBroker simulation.[/yellow]")
                self.broker = PaperBroker()
        else:
            self.broker = PaperBroker()
        self.auto_trade = auto_trade
        self.poll_interval = poll_interval_sec
        self.bs_engine = BlackScholesEngine(risk_free_rate=STRATEGY.risk_free_rate)
        self.risk_manager = RiskManager(capital=RISK.capital)
        self.analyst = AIAnalyst()
        self.classifier = IntradaySignalClassifier(confidence_threshold=STRATEGY.ml_confidence_threshold)
        
        # Load trained ML model
        if not self.classifier.load_model():
            print("[LiveRunner] No pre-trained model found. Initializing training...")
            from data.synthetic import generate_realistic_nifty_intraday
            df = generate_realistic_nifty_intraday(days=45)
            self.classifier.train(df)

        self.active_trades: Dict[str, Dict[str, Any]] = {}
        self.last_candle_time = None
        self.startup_synced = False
        self.cached_candles = None
        self.last_fetch_ts = 0.0
        self.today_synced = False
        from core.trade_journal import TradeJournal
        self.journal = TradeJournal()
        self.eod_report_sent = False

        # Restore any OPEN trades from today's journal to prevent duplicate contract signals across restarts
        for t in self.journal.trades:
            if t.get("status") == "OPEN":
                contract = t.get("contract")
                if contract:
                    self.active_trades[contract] = {
                        "journal_id": t["id"],
                        "contract": contract,
                        "option_type": t["option_type"],
                        "strike": t["strike"],
                        "lots": t["lots"],
                        "quantity": t["quantity"],
                        "entry_spot": t["spot_entry"],
                        "entry_premium": t["entry_premium"],
                        "spot_sl": t["spot_sl"],
                        "spot_target": t["spot_target"],
                        "spot_target_2": t["spot_target_2"],
                        "sl_premium": t["sl_premium"],
                        "target_premium": t["target_premium"],
                        "target_premium_2": t["target_premium_2"],
                        "sl_trailed": t.get("target1_hit", False),
                        "entry_time": t.get("entry_time", "")
                    }

    def is_market_open(self) -> bool:
        """Checks if current time is within NSE market hours (09:15 - 15:30 IST)."""
        now = datetime.now().time()
        return dtime(9, 15) <= now <= dtime(15, 30)

    def is_entry_allowed(self) -> bool:
        """Entry allowed between 09:20 and 14:45 IST."""
        now = datetime.now().time()
        return dtime(9, 20) <= now <= dtime(14, 45)

    def is_square_off_time(self) -> bool:
        """Mandatory square off at or after 15:15 IST."""
        now = datetime.now().time()
        return now >= dtime(15, 15)

    def fetch_live_feed(self) -> pd.DataFrame:
        """
        Fetches the latest intraday 5-min candles efficiently.
        Loads baseline once, then queries today's bars ONLY when a new 5-minute candle has closed,
        with a strict minimum 60-second cooldown to guarantee zero AB1021 rate-limit errors.
        """
        now = datetime.now()
        now_ts = time.time()

        # Smart 5-minute candle synchronization & Rate-limiting guard:
        # A new 5-minute candle only closes at 09:20, 09:25, 09:30, 09:35, etc.
        # Don't poll getCandleData unless:
        # 1. Baseline cache is not loaded yet (startup)
        # 2. At least 60 seconds have passed since the last API call
        # 3. A new 5-minute bar has completed (now >= last_candle_time + 5 mins + 5 sec)
        if self.cached_candles is not None:
            time_since_fetch = now_ts - self.last_fetch_ts
            min_cooldown = 60 if self.today_synced else 5
            if time_since_fetch < min_cooldown:
                return self.cached_candles
            if self.today_synced and self.last_candle_time is not None:
                try:
                    last_dt = pd.to_datetime(self.last_candle_time)
                    if hasattr(last_dt, 'tz_localize') and last_dt.tzinfo is None:
                        last_dt = last_dt.tz_localize("Asia/Kolkata")
                    next_bar_ts = last_dt.timestamp() + 300 + 5 # 5 mins + 5s buffer
                    if now_ts < next_bar_ts:
                        return self.cached_candles
                except Exception:
                    pass

        # If connected to Angel One
        if isinstance(self.broker, AngelOneBroker) and self.broker.is_connected:
            try:
                today_str = datetime.now().strftime("%Y-%m-%d")
                
                # Step 1: Ensure baseline historical candles (loaded once)
                if self.cached_candles is None:
                    console.print("[cyan]Loading baseline historical market candles from Angel One cache...[/cyan]")
                    from data.angel_fetcher import fetch_angel_historical_data
                    self.cached_candles = fetch_angel_historical_data(
                        days=5,
                        interval="FIVE_MINUTE",
                        force_refresh=False,
                        broker=self.broker
                    )
                    if not isinstance(self.cached_candles.index, pd.DatetimeIndex):
                        self.cached_candles.index = pd.to_datetime(self.cached_candles.index)
                    if self.cached_candles.index.tz is None:
                        self.cached_candles.index = self.cached_candles.index.tz_localize("Asia/Kolkata")
                    else:
                        self.cached_candles.index = self.cached_candles.index.tz_convert("Asia/Kolkata")
                    # If baseline refresh already pulled the current bar (< 5m old), skip redundant startup API hit
                    last_bar_ts = self.cached_candles.index[-1].timestamp()
                    if (now_ts - last_bar_ts) < 300:
                        self.today_synced = True
                        self.last_fetch_ts = time.time()
                        return self.cached_candles
                    # Small pause after baseline fetch before live intraday bar query to avoid rate limits
                    time.sleep(0.8)

                # Step 2: Fetch only today's completed 5-min candles using existing broker session
                params = {
                    "exchange": "NSE",
                    "symboltoken": "99926000",
                    "interval": "FIVE_MINUTE",
                    "fromdate": f"{today_str} 09:15",
                    "todate": f"{today_str} 15:30"
                }
                res = None
                for attempt in range(2):
                    try:
                        res = self.broker.smart_api.getCandleData(params)
                        break
                    except Exception as api_err:
                        if attempt == 0 and "access rate" in str(api_err).lower():
                            time.sleep(2.0)
                            continue
                        raise

                self.last_fetch_ts = time.time()
                if res and res.get("status") and res.get("data"):
                    today_data = res["data"]
                    df_today = pd.DataFrame(today_data, columns=["Timestamp", "Open", "High", "Low", "Close", "Volume"])
                    df_today["Timestamp"] = pd.to_datetime(df_today["Timestamp"])
                    df_today.set_index("Timestamp", inplace=True)
                    if df_today.index.tz is None:
                        df_today.index = df_today.index.tz_localize("Asia/Kolkata")
                    else:
                        df_today.index = df_today.index.tz_convert("Asia/Kolkata")
                    for col in ["Open", "High", "Low", "Close"]:
                        df_today[col] = df_today[col].astype(float)
                    df_today["Volume"] = df_today["Volume"].astype(int)
                    
                    # Merge with baseline candles
                    combined = pd.concat([self.cached_candles, df_today])
                    combined = combined[~combined.index.duplicated(keep="last")].sort_index()
                    self.cached_candles = combined
                    self.today_synced = True
                    return self.cached_candles
                elif self.cached_candles is not None:
                    return self.cached_candles
            except Exception as e:
                self.last_fetch_ts = time.time()
                if self.cached_candles is not None:
                    console.print(f"[yellow]Notice: Could not refresh today's candle bar yet ({e}). Will retry shortly.[/yellow]")
                    return self.cached_candles
                console.print(f"[yellow]Angel One live feed fallback ({e}), checking Yahoo Finance...[/yellow]")

        from data.fetcher import get_nifty_intraday_data
        try:
            df = get_nifty_intraday_data(period="5d", interval="5m", force_refresh=True)
            self.cached_candles = df
            self.last_fetch_ts = now_ts
            return df
        except Exception:
            from data.synthetic import generate_realistic_nifty_intraday
            return generate_realistic_nifty_intraday(days=5, interval_mins=5)

    def _is_contract_active(self, contract: str = "", strike: int = 0, option_type: str = "") -> bool:
        """Checks whether a trade is already active in the same contract or (strike, option_type)."""
        if contract and contract in self.active_trades:
            return True
        for t in self.active_trades.values():
            if t.get("strike") == strike and t.get("option_type") == option_type:
                return True
        return False

    def _manage_all_active_trades(self, current_bar: Optional[pd.Series] = None, live_spot: Optional[float] = None):
        """Monitors all open contracts and removes any contract once its trade completes."""
        for contract_key in list(self.active_trades.keys()):
            trade = self.active_trades.get(contract_key)
            if trade is not None:
                exited = self._manage_live_position(trade, current_bar=current_bar, live_spot=live_spot)
                if exited:
                    self.active_trades.pop(contract_key, None)

    def evaluate_new_bar(self, df_ind: pd.DataFrame):
        """Processes the most recent completed 5-minute bar."""
        df_feat = engineer_features(df_ind).dropna()
        if df_feat.empty:
            return

        latest_bar = df_feat.iloc[-1]
        candle_time = df_feat.index[-1]

        if candle_time == self.last_candle_time:
            return # Already evaluated this bar
        self.last_candle_time = candle_time

        now_dt = datetime.now(candle_time.tzinfo) if getattr(candle_time, "tzinfo", None) is not None else datetime.now()
        is_today_candle = candle_time.date() == now_dt.date()
        is_fresh_candle = is_today_candle and abs((now_dt - candle_time).total_seconds()) <= 900

        # Startup baseline sync: do NOT fire an immediate trade on the initial historical/startup bar
        if not self.startup_synced:
            self.startup_synced = True
            console.print(
                f"[cyan][Startup] Baseline synced to {candle_time.strftime('%Y-%m-%d %H:%M IST')} "
                f"(Spot: ₹{latest_bar['Close']:,.1f}). Waiting for next live 5m bar before scanning signals...[/cyan]"
            )
            return

        console.print(f"[dim][{datetime.now().strftime('%H:%M:%S')}] New 5m Bar ({candle_time.strftime('%H:%M')}): ₹{latest_bar['Close']:,.1f} (VWAP: ₹{latest_bar['VWAP']:,.1f})[/dim]")

        # 1. Manage all currently active trades (only against fresh live bars)
        if is_fresh_candle and self.active_trades:
            self._manage_all_active_trades(current_bar=latest_bar)

        # Guard against stale/non-today bars so an outdated candle never triggers an entry
        if not is_fresh_candle:
            console.print(f"[yellow]Skipping signal scan: candle {candle_time.strftime('%Y-%m-%d %H:%M')} is stale or not from today's live session.[/yellow]")
            return

        # 2. Check entry timing filter
        if not self.is_entry_allowed():
            return

        # 3. Check Risk Manager Circuit Breakers
        can_trade, reason = self.risk_manager.can_take_trade()
        if not can_trade:
            console.print(f"[yellow]Trade Skipped: {reason}[/yellow]")
            return

        # 4. Evaluate Technical + ML Confluence
        spot_close = float(latest_bar['Close'])
        vwap = float(latest_bar['VWAP'])
        supertrend_dir = latest_bar['SuperTrend_Dir']

        pred = self.classifier.predict(latest_bar)
        bull_prob = pred['bull_prob']
        bear_prob = pred['bear_prob']

        signal = None
        if spot_close >= vwap and supertrend_dir == 1 and bull_prob >= self.classifier.confidence_threshold:
            signal = "BUY_CE"
        elif spot_close <= vwap and supertrend_dir == -1 and bear_prob >= self.classifier.confidence_threshold:
            signal = "BUY_PE"

        if signal:
            # Verify live spot anchor so entry_spot/SL cannot diverge from real-time feed
            entry_spot = spot_close
            if isinstance(self.broker, AngelOneBroker) and self.broker.is_connected:
                try:
                    live_spot = self.broker.get_ltp("Nifty 50", "99926000", "NSE")
                    if live_spot > 0:
                        if abs(live_spot - spot_close) > 50.0:
                            console.print(f"[yellow]Signal skipped: Bar close (₹{spot_close:.1f}) diverged from live spot (₹{live_spot:.1f}).[/yellow]")
                            return
                        entry_spot = float(live_spot)
                except Exception:
                    pass

            option_type = "CE" if signal == "BUY_CE" else "PE"
            candidate_strike = self.analyst.bs_engine.select_strike(
                spot=entry_spot,
                option_type=option_type,
                selection_mode=STRATEGY.strike_selection,
                strike_gap=MARKET.strike_gap
            )
            if self._is_contract_active(strike=candidate_strike, option_type=option_type):
                console.print(f"[dim]Signal skipped: NIFTY {candidate_strike} {option_type} already has an active trade.[/dim]")
                return

            candle_dict = latest_bar.to_dict()
            candle_dict['Close'] = entry_spot
            candle_dict['time_str'] = datetime.now().strftime("%H:%M IST")
            
            # Days to Thursday weekly expiry (calibrated for real trading-day DTE)
            days_to_thursday = (3 - datetime.now().weekday()) % 7
            dte = max(days_to_thursday * 0.4 + 0.1, 0.15)

            advisory = self.analyst.analyze_setup(
                current_candle=candle_dict,
                ml_prediction={"signal": signal, "confidence": max(bull_prob, bear_prob)},
                iv=STRATEGY.default_iv,
                dte_days=dte,
                broker=self.broker
            )

            if advisory:
                if self._is_contract_active(
                    contract=advisory['contract'],
                    strike=advisory['strike'],
                    option_type=advisory['option_type']
                ):
                    console.print(f"[dim]Signal skipped: {advisory['contract']} already has an active trade.[/dim]")
                    return

                # Check position sizing
                pos_res = self.risk_manager.calculate_position_size(
                    entry_premium=advisory['entry_premium'],
                    risk_per_share=advisory['risk_per_share']
                )

                if self.auto_trade and not (pos_res.is_valid and pos_res.lots >= 1):
                    console.print(f"[yellow]Auto-Trade skipped: {pos_res.rejection_reason}[/yellow]")
                    return

                lots = pos_res.lots if (pos_res.is_valid and pos_res.lots >= 1) else 1
                qty = pos_res.quantity if (pos_res.is_valid and pos_res.lots >= 1) else MARKET.lot_size
                if not pos_res.is_valid:
                    console.print(f"[dim]Advisory note: {pos_res.rejection_reason}. Tracking 1-lot ({qty} Qty) advisory & SL/TP alerts.[/dim]")

                display_signal_card(advisory)

                # Dispatch Telegram / WhatsApp alerts if configured
                tg_msg = format_telegram_alert(advisory, lots=lots, quantity=qty)
                if send_telegram_alert(tg_msg):
                    console.print("[bold green]✓ Telegram Trade Alert dispatched.[/bold green]")
                if send_whatsapp_alert(tg_msg):
                    console.print("[bold green]✓ WhatsApp Trade Alert dispatched.[/bold green]")

                # Always record into persistent trade journal & active tracker whenever an alert is sent
                trade_payload = {
                    "contract": advisory['contract'],
                    "option_type": advisory['option_type'],
                    "strike": advisory['strike'],
                    "lots": lots,
                    "quantity": qty,
                    "entry_time": datetime.now().strftime("%H:%M:%S"),
                    "entry_premium": advisory['entry_premium'],
                    "entry_spot": entry_spot,
                    "spot_sl": advisory['spot_sl'],
                    "spot_target": advisory['spot_target'],
                    "spot_target_2": advisory['spot_target_2'],
                    "sl_premium": advisory['sl_premium'],
                    "target_premium": advisory['target_premium'],
                    "target_premium_2": advisory['target_premium_2'],
                    "ai_confidence": advisory.get('ai_confidence', 'N/A')
                }
                journal_id = self.journal.record_entry(trade_payload)

                if self.auto_trade:
                    console.print(f"[bold green]🚀 AUTO-TRADE TRIGGERED: Placing {lots} Lots ({qty} Qty) on {advisory['contract']}...[/bold green]")
                    res = self.broker.place_order(
                        symbol=advisory['contract'],
                        action="BUY",
                        quantity=qty,
                        price=advisory['entry_premium'],
                        sl=advisory['sl_premium'],
                        target=advisory['target_premium'],
                        target_2=advisory['target_premium_2'],
                        strike=advisory['strike'],
                        option_type=advisory['option_type']
                    )
                    console.print(f"[bold green]✓ Order Executed: {res.message}[/bold green]")

                self.active_trades[advisory['contract']] = {
                    "journal_id": journal_id,
                    "contract": advisory['contract'],
                    "option_type": advisory['option_type'],
                    "strike": advisory['strike'],
                    "lots": lots,
                    "quantity": qty,
                    "entry_spot": entry_spot,
                    "entry_premium": advisory['entry_premium'],
                    "spot_sl": advisory['spot_sl'],
                    "spot_target": advisory['spot_target'],
                    "spot_target_2": advisory['spot_target_2'],
                    "sl_premium": advisory['sl_premium'],
                    "target_premium": advisory['target_premium'],
                    "target_premium_2": advisory['target_premium_2'],
                    "sl_trailed": False,
                    "entry_time": datetime.now().strftime("%H:%M:%S")
                }

    def _manage_live_position(
        self,
        trade: Dict[str, Any],
        current_bar: Optional[pd.Series] = None,
        live_spot: Optional[float] = None
    ) -> bool:
        """Monitors an active trade against SL, Target 1, Target 2, and 15:15 IST cutoff. Returns True if exited."""
        if trade is None:
            return False

        if current_bar is not None:
            spot = current_bar['Close']
            high = current_bar['High']
            low = current_bar['Low']
        elif live_spot is not None:
            spot = live_spot
            high = live_spot
            low = live_spot
        else:
            return False

        is_ce = trade['option_type'] == "CE"

        exit_triggered = False
        exit_reason = ""
        exit_alert_msg = ""

        # 1. Mandatory 15:15 IST Square-off
        if self.is_square_off_time():
            exit_triggered = True
            exit_reason = "15:15 IST Mandatory Intraday Square-off"
            exit_alert_msg = format_time_squareoff_alert(
                contract=trade['contract'],
                entry_premium=trade['entry_premium'],
                exit_premium=trade['entry_premium'],
                quantity=trade['quantity']
            )

        # 2. Stop Loss Check
        elif (is_ce and low <= trade['spot_sl']) or (not is_ce and high >= trade['spot_sl']):
            exit_triggered = True
            was_trailed = trade.get('sl_trailed', False)
            exit_reason = "Stop Loss Hit (Trailed to Breakeven)" if was_trailed else f"Hard Stop Loss Hit (Spot {trade['spot_sl']:.1f})"
            exit_premium = trade['entry_premium'] if was_trailed else trade['sl_premium']
            exit_alert_msg = format_stoploss_alert(
                contract=trade['contract'],
                entry_premium=trade['entry_premium'],
                sl_premium=exit_premium,
                lots=trade['lots'],
                quantity=trade['quantity'],
                was_trailed=was_trailed
            )

        # 3. Target 2 Runner Check
        elif (is_ce and high >= trade['spot_target_2']) or (not is_ce and low <= trade['spot_target_2']):
            exit_triggered = True
            exit_reason = f"Target 2 Full Hit (Spot {trade['spot_target_2']:.1f})"
            exit_alert_msg = format_target2_alert(
                contract=trade['contract'],
                entry_premium=trade['entry_premium'],
                target_premium_2=trade['target_premium_2'],
                lots=trade['lots'],
                quantity=trade['quantity']
            )

        # 4. Target 1: Trail Stop Loss to Entry Cost
        elif not trade['sl_trailed']:
            if (is_ce and high >= trade['spot_target']) or (not is_ce and low <= trade['spot_target']):
                trade['spot_sl'] = trade['entry_spot'] # Trail to breakeven
                trade['sl_trailed'] = True
                if trade.get('journal_id'):
                    self.journal.record_target1(trade['journal_id'], trade['target_premium'])
                console.print(f"[bold cyan]🎯 Target 1 Reached! Stop-loss trailed to Breakeven (Spot: ₹{trade['entry_spot']:.1f})[/bold cyan]")
                t1_msg = format_target1_alert(
                    contract=trade['contract'],
                    entry_premium=trade['entry_premium'],
                    target_premium=trade['target_premium'],
                    lots=trade['lots'],
                    quantity=trade['quantity']
                )
                send_telegram_alert(t1_msg)
                send_whatsapp_alert(t1_msg)

        # Execute Exit if triggered
        if exit_triggered:
            console.print(f"[bold red]🔔 EXIT TRIGGERED ({trade['contract']}): {exit_reason}[/bold red]")
            if "Target 2" in exit_reason:
                exit_premium_used = trade['target_premium_2']
            elif trade.get('sl_trailed') and "Stop Loss" in exit_reason:
                exit_premium_used = trade['entry_premium']
            elif "Square-off" in exit_reason:
                exit_premium_used = trade['entry_premium']
            else:
                exit_premium_used = trade['sl_premium']
            if trade.get('journal_id'):
                self.journal.record_exit(trade['journal_id'], exit_premium_used, exit_reason)
            if self.auto_trade:
                res = self.broker.place_order(trade['contract'], "SELL", trade['quantity'], price=exit_premium_used)
                console.print(f"[yellow]{res.message}[/yellow]")
            if exit_alert_msg:
                send_telegram_alert(exit_alert_msg)
                send_whatsapp_alert(exit_alert_msg)
        return exit_triggered

    def send_and_save_eod_summary(self) -> str:
        """Generates, prints, persists to disk, and sends the EOD summary report to Telegram."""
        summary = self.journal.get_eod_summary()
        from live.notifier import format_eod_summary_alert, send_telegram_alert, send_whatsapp_alert
        
        # 1. Format Telegram Message
        eod_msg = format_eod_summary_alert(summary)
        
        # 2. Print to Console
        console.print("\n[bold cyan]═══════════════════ END OF DAY PERFORMANCE REPORT ═══════════════════[/bold cyan]")
        console.print(eod_msg)
        console.print("[bold cyan]═════════════════════════════════════════════════════════════════════[/bold cyan]\n")
        
        # 3. Save a persistent copy to disk (reports/daily_summary_YYYY-MM-DD.txt)
        reports_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")
        os.makedirs(reports_dir, exist_ok=True)
        txt_path = os.path.join(reports_dir, f"daily_summary_{summary['date']}.txt")
        try:
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(eod_msg)
            console.print(f"[bold green]✓ Saved persistent EOD report copy to:[/] [cyan]{txt_path}[/cyan]")
        except Exception as e:
            console.print(f"[yellow]Could not save EOD text copy: {e}[/yellow]")
            
        # 4. Dispatch to Telegram and WhatsApp
        if send_telegram_alert(eod_msg):
            console.print("[bold green]✓ EOD Summary Report dispatched to Telegram![/bold green]")
        if send_whatsapp_alert(eod_msg):
            console.print("[bold green]✓ EOD Summary Report dispatched to WhatsApp![/bold green]")
        return eod_msg

    def start_loop(self):
        """Main live loop polling candles every interval."""
        console.print("[bold cyan]⚡ Live NIFTY Options AI Scanner Started.[/bold cyan]")
        console.print(f"Auto-Execution: [bold]{'ENABLED' if self.auto_trade else 'DISABLED (Advisory Only)'}[/bold]")
        console.print("Press Ctrl+C to stop scanner.\n")

        try:
            while True:
                # EOD Report Trigger (at or after 15:30 IST)
                now_t = datetime.now().time()
                if now_t >= dtime(15, 30) and not self.eod_report_sent:
                    self.send_and_save_eod_summary()
                    self.eod_report_sent = True

                # Real-time position tracking between 5m bars using lightweight LTP
                if self.active_trades and isinstance(self.broker, AngelOneBroker) and self.broker.is_connected:
                    try:
                        spot_ltp = self.broker.get_ltp("Nifty 50", "99926000", "NSE")
                        if spot_ltp > 0:
                            self._manage_all_active_trades(live_spot=spot_ltp)
                    except Exception:
                        pass

                df = self.fetch_live_feed()
                df_ind = add_all_indicators(df)
                self.evaluate_new_bar(df_ind)
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            console.print("\n[yellow]Scanner paused by user.[/yellow]")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--auto", action="store_true", help="Enable automatic paper/broker order execution")
    args = parser.parse_args()
    
    runner = LiveMarketRunner(auto_trade=args.auto, poll_interval_sec=10)
    runner.start_loop()

