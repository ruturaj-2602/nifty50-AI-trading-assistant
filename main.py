"""
Main Entrypoint for NIFTY Intraday Options Trading AI Bot & Analyst.
Usage:
  python main.py --mode backtest
  python main.py --mode signal
  python main.py --mode live
"""
import argparse
import sys
import os

from config import MARKET, STRATEGY, RISK
from data.fetcher import get_nifty_intraday_data
from data.synthetic import generate_realistic_nifty_intraday
from data.angel_fetcher import fetch_angel_historical_data
from core.indicators import add_all_indicators
from ai.features import engineer_features
from ai.model import IntradaySignalClassifier
from ai.analyst import AIAnalyst
from backtester.engine import BacktestEngine
from backtester.metrics import calculate_performance_metrics
from ui.cli_view import (
    display_welcome_banner,
    display_signal_card,
    display_backtest_summary,
    display_trade_log,
    console
)
from ui.report_generator import generate_charts, generate_html_report

def run_backtest(data_source: str = "yahoo", days: int = 60):
    """Executes backtesting workflow."""
    display_welcome_banner()
    console.print(f"[bold cyan]Initiating Backtest Engine...[/bold cyan]")
    console.print(f"Index: [bold]{MARKET.index_name}[/] | Capital: [bold]₹{RISK.capital:,.0f}[/] | Lot Size: [bold]{MARKET.lot_size}[/]")
    console.print(f"Intraday Window: [bold]{MARKET.entry_start_time} - {MARKET.square_off_time} IST[/]")
    console.print()

    # 1. Fetch or generate data
    if data_source == "angel":
        console.print(f"[cyan]Downloading authentic NIFTY 50 5-min historical candles from Angel One SmartAPI ({days} days)...[/cyan]")
        df = fetch_angel_historical_data(days=days, interval="FIVE_MINUTE")
    elif data_source == "synthetic":
        console.print(f"[yellow]Loading synthetic calibrated NIFTY 50 intraday data ({days} days)...[/yellow]")
        df = generate_realistic_nifty_intraday(days=days, interval_mins=5)
    else:
        console.print(f"[cyan]Fetching NIFTY 50 5-min intraday data (Yahoo Finance ^NSEI)...[/cyan]")
        df = get_nifty_intraday_data(period=f"{days}d", interval="5m")

    console.print(f"[green]✓ Successfully loaded {len(df):,} candles across {len(set(df.index.date))} trading sessions.[/green]")
    console.print()

    # 2. Run Backtest
    engine = BacktestEngine(
        initial_capital=RISK.capital,
        confidence_threshold=STRATEGY.ml_confidence_threshold,
        iv=STRATEGY.default_iv
    )
    
    trades_df = engine.run(df, train_ratio=0.5)
    
    # 3. Calculate Performance Analytics
    metrics = calculate_performance_metrics(
        trades_df=trades_df,
        equity_curve=engine.equity_curve,
        initial_capital=RISK.capital,
        risk_free_rate=STRATEGY.risk_free_rate
    )
    
    # 4. Display in Terminal
    display_backtest_summary(metrics)
    display_trade_log(trades_df, max_rows=12)
    
    # 5. Generate Visual Reports
    chart_path = generate_charts(engine.equity_curve, trades_df)
    html_path = generate_html_report(metrics, trades_df, engine.equity_curve)
    
    if chart_path:
        console.print(f"[bold green]✓ Equity Curve Chart exported to:[/] [cyan]{chart_path}[/cyan]")
    console.print(f"[bold green]✓ Interactive HTML Dashboard exported to:[/] [cyan]{html_path}[/cyan]")
    console.print()
    return metrics, trades_df

def generate_live_signal(data_source: str = "yahoo"):
    """Generates real-time / latest trade signal with full AI Analyst advisory."""
    display_welcome_banner()
    console.print("[bold cyan]Scanning NIFTY market for actionable setups...[/bold cyan]")
    
    broker = None
    if data_source == "angel":
        from brokers.angelone_adapter import AngelOneBroker
        b = AngelOneBroker()
        if b.connect():
            broker = b
    
    if data_source == "synthetic":
        df = generate_realistic_nifty_intraday(days=20, interval_mins=5)
    else:
        df = get_nifty_intraday_data(period="5d", interval="5m")
        
    df_ind = add_all_indicators(df)
    df_feat = engineer_features(df_ind).dropna()
    
    # Initialize / train classifier
    classifier = IntradaySignalClassifier(confidence_threshold=STRATEGY.ml_confidence_threshold)
    if not classifier.load_model():
        console.print("[yellow]Training AI Model on recent historical market data...[/yellow]")
        classifier.train(df_feat)
        
    analyst = AIAnalyst()
    
    # Evaluate latest candle or scan back up to 5 candles for latest active trigger
    latest_advisory = None
    for i in range(len(df_feat) - 1, max(0, len(df_feat) - 10), -1):
        candle = df_feat.iloc[i].to_dict()
        candle['time_str'] = df_feat.index[i].strftime("%Y-%m-%d %H:%M IST")
        
        ml_pred = classifier.predict(df_feat.iloc[i])
        advisory = analyst.analyze_setup(
            current_candle=candle,
            ml_prediction=ml_pred,
            iv=STRATEGY.default_iv,
            dte_days=1.2,
            broker=broker
        )
        if advisory:
            latest_advisory = advisory
            break
            
    if latest_advisory:
        display_signal_card(latest_advisory)
        from live.notifier import format_telegram_alert, send_telegram_alert
        tg_msg = format_telegram_alert(latest_advisory, lots=1, quantity=MARKET.lot_size)
        if send_telegram_alert(tg_msg):
            console.print("[bold green]✓ AI Trade Signal dispatched to your Telegram chat.[/bold green]")
    else:
        # If no active trigger in last few candles, synthesize the current state
        curr_row = df_feat.iloc[-1].to_dict()
        curr_time = df_feat.index[-1].strftime("%Y-%m-%d %H:%M IST")
        console.print(f"[yellow]Current NIFTY Level: ₹{curr_row['Close']:.2f} at {curr_time}[/yellow]")
        console.print("[dim]Status: Rangebound / Neutral. AI Model Confidence filter did not reach threshold (> 58%). No new entry advised.[/dim]")
        
        # Display simulated highest probability scenario
        mock_pred = {"signal": "BUY_CE" if curr_row['Close'] > curr_row['VWAP'] else "BUY_PE", "confidence": 0.65}
        curr_row['time_str'] = curr_time
        sim_adv = analyst.analyze_setup(curr_row, mock_pred, iv=STRATEGY.default_iv, dte_days=3.0)
        console.print("\n[bold cyan]--- Scenario Analysis If Trend Resumes ---[/bold cyan]")
        display_signal_card(sim_adv)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NIFTY Intraday Options Trading AI Bot & Analyst")
    parser.add_argument("--mode", choices=["backtest", "signal", "live", "server", "summary"], default="backtest", help="Execution mode")
    parser.add_argument("--source", choices=["angel", "synthetic", "yahoo"], default="angel", help="Data source (angel, synthetic, yahoo)")
    parser.add_argument("--days", type=int, default=60, help="Number of days to backtest")
    parser.add_argument("--broker", choices=["paper", "angel"], default="angel", help="Execution broker")
    parser.add_argument("--auto", action="store_true", help="Enable automated order routing (in live mode)")
    
    args = parser.parse_args()
    
    if args.mode == "backtest":
        run_backtest(data_source=args.source, days=args.days)
    elif args.mode == "signal":
        generate_live_signal(data_source=args.source)
    elif args.mode == "live":
        from live.live_trader import LiveMarketRunner
        runner = LiveMarketRunner(broker_type=args.broker, auto_trade=args.auto, poll_interval_sec=15)
        runner.start_loop()
    elif args.mode == "server":
        from app import start_server
        start_server()
    elif args.mode == "summary":
        from live.live_trader import LiveMarketRunner
        runner = LiveMarketRunner(broker_type=args.broker, auto_trade=False)
        runner.send_and_save_eod_summary()

