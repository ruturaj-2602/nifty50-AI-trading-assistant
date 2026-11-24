"""
Rich Terminal View for NIFTY Intraday AI Bot and Analyst.
Provides institutional-grade visual tables, signal cards, and metrics summaries.
"""
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box
from typing import Dict, Any, List
import pandas as pd

console = Console()

def display_welcome_banner():
    """Displays startup banner."""
    banner = """
    ╔═══════════════════════════════════════════════════════════════════════╗
    ║        NIFTY INTRADAY OPTIONS TRADING AI BOT & ANALYST ENGINE         ║
    ║   High-Probability Machine Learning Signals • Black-Scholes Greeks   ║
    ║       Institutional Risk Management • Strict 15:15 Square-off        ║
    ╚═══════════════════════════════════════════════════════════════════════╝
    """
    console.print(f"[bold cyan]{banner}[/bold cyan]")

def display_signal_card(advisory: Dict[str, Any]):
    """Renders a comprehensive trade advisory card in the terminal."""
    if not advisory:
        console.print("[yellow]No actionable trade setup at this time (Market in chop / Neutral regime).[/yellow]")
        return

    is_call = advisory['option_type'] == "CE"
    color = "green" if is_call else "red"
    badge = "[bold white on green] BUY CALL (CE) [/]" if is_call else "[bold white on red] BUY PUT (PE) [/]"

    # Main Details Table
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta")
    table.add_column("Parameter", style="bold cyan", width=24)
    table.add_column("Value / Execution Level", style="bold white", width=36)
    
    table.add_row("Contract", f"[bold {color}]{advisory['contract']}[/]")
    table.add_row("Underlying Spot", f"₹{advisory['spot_price']:,.2f}")
    table.add_row("AI Win Confidence", f"[bold yellow]{advisory['ai_confidence']}[/]")
    table.add_row("Entry Option Premium", f"[bold {color}]₹{advisory['entry_premium']:.2f}[/]")
    table.add_row("Stop Loss (Premium / Spot)", f"[bold red]₹{advisory['sl_premium']:.2f}[/] (Spot: ₹{advisory['spot_sl']:.1f})")
    table.add_row("Target 1 (Premium / Spot)", f"[bold green]₹{advisory['target_premium']:.2f}[/] (Spot: ₹{advisory['spot_target']:.1f})")
    table.add_row("Target 2 (Runner)", f"[bold green]₹{advisory['target_premium_2']:.2f}[/] (Spot: ₹{advisory['spot_target_2']:.1f})")
    table.add_row("Risk : Reward Ratio", f"[bold cyan]{advisory['risk_reward_ratio']}[/]")
    table.add_row("Risk / Lot", f"[bold red]-₹{advisory['risk_per_lot']:,.0f}[/] (1 Lot = {advisory['lot_size']} Qty)")
    table.add_row("Expected Profit / Lot", f"[bold green]+₹{advisory['gain_per_lot']:,.0f}[/] (Target 1)")
    table.add_row("Option Greeks", f"Delta: {advisory['delta']} | Daily Theta: ₹{advisory['theta_daily']:.1f}")

    # Confluences
    confluence_text = "\n".join([f"  • {c}" for c in advisory['confluences']])
    
    # Management Plan
    plan_text = "\n".join([f"  {i+1}. {step}" for i, step in enumerate(advisory['management_plan'])])

    content = f"""
{badge}  [bold underline]Trade Signal Generated at {advisory['timestamp']}[/]

[bold yellow]Technical & Quantitative Confluences:[/bold yellow]
{confluence_text}

[bold yellow]Trade Execution & Management Rules:[/bold yellow]
{plan_text}
"""
    panel = Panel(
        content,
        title=f"[bold {color}]AI Trade Signal: {advisory['contract']}[/bold {color}]",
        subtitle="[dim]Antigravity Quantitative Strategy Engine[/dim]",
        border_style=color,
        box=box.DOUBLE
    )
    
    console.print(panel)
    console.print(table)
    console.print()

def display_backtest_summary(metrics: Dict[str, Any]):
    """Renders comprehensive backtest results."""
    if metrics.get('total_trades', 0) == 0:
        console.print("[yellow]No trades met entry criteria during the backtest period.[/yellow]")
        return

    table = Table(title="📊 NIFTY INTRADAY OPTIONS AI - BACKTEST PERFORMANCE SUMMARY", box=box.HEAVY_EDGE)
    table.add_column("Performance Metric", style="bold cyan", width=34)
    table.add_column("Result", style="bold white", width=26)

    ret_color = "green" if metrics.get('net_profit', 0) >= 0 else "red"
    
    table.add_row("Initial Test Capital", f"₹{metrics['initial_capital']:,.2f}")
    table.add_row("Final Portfolio Capital", f"[bold {ret_color}]₹{metrics['final_capital']:,.2f}[/]")
    table.add_row("Net Profit / Loss", f"[bold {ret_color}]₹{metrics['net_profit']:,.2f} ({metrics['net_return_pct']:+.2f}%)[/]")
    table.add_row("Total Executed Trades", str(metrics['total_trades']))
    table.add_row("Winning Trades / Losing Trades", f"[green]{metrics['winning_trades']}[/] / [red]{metrics['losing_trades']}[/]")
    table.add_row("Win Rate", f"[bold yellow]{metrics['win_rate_pct']:.2f}%[/]")
    table.add_row("Profit Factor", f"[bold cyan]{metrics['profit_factor']:.2f}[/]")
    table.add_row("Mathematical Expectancy / Trade", f"[bold {ret_color}]₹{metrics['expectancy_per_trade']:,.2f}[/]")
    table.add_row("Average Win / Average Loss", f"[green]₹{metrics['avg_win']:,.2f}[/] / [red]₹{metrics['avg_loss']:,.2f}[/]")
    table.add_row("Win / Loss Ratio", f"{metrics['win_loss_ratio']:.2f}")
    table.add_row("Maximum Drawdown", f"[bold red]-{metrics['max_drawdown_pct']:.2f}% (-₹{metrics['max_drawdown_amt']:,.2f})[/]")
    table.add_row("Sharpe Ratio (Annualized)", f"[bold green]{metrics['sharpe_ratio']:.2f}[/]")
    table.add_row("Sortino Ratio", f"[bold green]{metrics['sortino_ratio']:.2f}[/]")
    table.add_row("Calmar Ratio", f"{metrics['calmar_ratio']:.2f}")
    table.add_row("Daily Win Rate (% profitable days)", f"{metrics['daily_win_rate_pct']:.2f}%")
    table.add_row("Total Statutory Taxes & Charges Incurred", f"₹{metrics['total_charges_incurred']:,.2f}")
    
    console.print(table)
    console.print()

def display_trade_log(trades_df: pd.DataFrame, max_rows: int = 15):
    """Displays detailed recent trade log table."""
    if trades_df.empty:
        return
        
    table = Table(title=f"📜 RECENT TRADE EXECUTION LOG (Last {min(len(trades_df), max_rows)} Trades)", box=box.SIMPLE_HEAVY)
    table.add_column("#", style="dim", width=4)
    table.add_column("Date", style="cyan", width=11)
    table.add_column("Time", style="dim", width=12)
    table.add_column("Contract", style="bold", width=18)
    table.add_column("Lots", style="magenta", width=5)
    table.add_column("Entry ₹", style="white", width=9)
    table.add_column("Exit ₹", style="white", width=9)
    table.add_column("Net PnL (₹)", style="bold", width=13)
    table.add_column("Return %", style="bold", width=9)
    table.add_column("Exit Reason", style="dim", width=18)

    sample = trades_df.tail(max_rows)
    for _, t in sample.iterrows():
        pnl_color = "green" if t['net_pnl'] > 0 else "red"
        table.add_row(
            str(int(t['trade_id'])),
            str(t['entry_date']),
            f"{t['entry_time']} -> {t['exit_time']}",
            str(t['contract']),
            str(int(t['lots'])),
            f"₹{t['entry_premium']:.1f}",
            f"₹{t['exit_premium']:.1f}",
            f"[{pnl_color}]₹{t['net_pnl']:+,.1f}[/]",
            f"[{pnl_color}]{t['pnl_pct']:+.1f}%[/]",
            str(t['exit_reason'])
        )

    console.print(table)
    console.print()
