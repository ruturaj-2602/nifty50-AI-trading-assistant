"""
Performance and Quantitative Analytics Engine.
Calculates institutional hedge-fund grade metrics: Sharpe, Sortino, Calmar,
Profit Factor, Max Drawdown, Expectancy, and statutory tax impact.
"""
from typing import Dict, Any, List
import pandas as pd
import numpy as np

def calculate_performance_metrics(
    trades_df: pd.DataFrame,
    equity_curve: List[Dict[str, Any]],
    initial_capital: float = 100000.0,
    risk_free_rate: float = 0.068
) -> Dict[str, Any]:
    """
    Computes comprehensive backtest performance statistics.
    """
    if trades_df.empty:
        return {
            "total_trades": 0,
            "message": "No trades executed during backtest period."
        }
        
    net_pnls = trades_df['net_pnl'].values
    gross_pnls = trades_df['gross_pnl'].values
    total_charges = trades_df['total_charges'].sum()
    
    total_trades = len(trades_df)
    winning_trades = trades_df[trades_df['net_pnl'] > 0]
    losing_trades = trades_df[trades_df['net_pnl'] <= 0]
    
    num_wins = len(winning_trades)
    num_losses = len(losing_trades)
    win_rate = (num_wins / total_trades) * 100.0 if total_trades > 0 else 0.0
    
    gross_profit = winning_trades['net_pnl'].sum() if num_wins > 0 else 0.0
    gross_loss = abs(losing_trades['net_pnl'].sum()) if num_losses > 0 else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
    
    avg_win = winning_trades['net_pnl'].mean() if num_wins > 0 else 0.0
    avg_loss = abs(losing_trades['net_pnl'].mean()) if num_losses > 0 else 0.0
    win_loss_ratio = (avg_win / avg_loss) if avg_loss > 0 else 0.0
    
    # Mathematical Expectancy
    win_prob = num_wins / total_trades if total_trades > 0 else 0.0
    loss_prob = num_losses / total_trades if total_trades > 0 else 0.0
    expectancy = (win_prob * avg_win) - (loss_prob * avg_loss)
    
    # Equity curve and Drawdown calculation
    eq_df = pd.DataFrame(equity_curve)
    if not eq_df.empty and 'capital' in eq_df.columns:
        caps = eq_df['capital'].values
        running_max = np.maximum.accumulate(caps)
        drawdowns = (caps - running_max) / running_max
        max_drawdown_pct = abs(float(np.min(drawdowns))) * 100.0
        max_drawdown_amt = float(np.max(running_max - caps))
        final_capital = caps[-1]
    else:
        final_capital = initial_capital + net_pnls.sum()
        max_drawdown_pct = 0.0
        max_drawdown_amt = 0.0
        
    net_profit = final_capital - initial_capital
    net_return_pct = (net_profit / initial_capital) * 100.0
    
    # Daily returns for Sharpe and Sortino
    trades_df['entry_date'] = pd.to_datetime(trades_df['entry_date'])
    daily_pnl = trades_df.groupby('entry_date')['net_pnl'].sum()
    daily_returns = daily_pnl / initial_capital
    
    trading_days = len(daily_returns)
    daily_rf = risk_free_rate / 252.0
    excess_returns = daily_returns - daily_rf
    
    if len(daily_returns) > 1 and daily_returns.std() > 0:
        sharpe_ratio = float((excess_returns.mean() / daily_returns.std()) * np.sqrt(252))
        
        downside_returns = daily_returns[daily_returns < 0]
        downside_std = downside_returns.std() if len(downside_returns) > 1 and downside_returns.std() > 0 else 1e-6
        sortino_ratio = float((excess_returns.mean() / downside_std) * np.sqrt(252))
    else:
        sharpe_ratio = 0.0
        sortino_ratio = 0.0
        
    # Calmar ratio
    annualized_return = net_return_pct * (252 / max(trading_days, 1))
    calmar_ratio = (annualized_return / max_drawdown_pct) if max_drawdown_pct > 0 else 0.0
    
    # Daily win rate
    winning_days = (daily_pnl > 0).sum()
    losing_days = (daily_pnl < 0).sum()
    daily_win_rate = (winning_days / max(trading_days, 1)) * 100.0
    
    # Exit reasons breakdown
    exit_reasons = trades_df['exit_reason'].value_counts().to_dict()
    
    return {
        "initial_capital": round(initial_capital, 2),
        "final_capital": round(final_capital, 2),
        "net_profit": round(net_profit, 2),
        "net_return_pct": round(net_return_pct, 2),
        "total_trades": total_trades,
        "winning_trades": num_wins,
        "losing_trades": num_losses,
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "avg_trade_pnl": round(float(net_pnls.mean()), 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "win_loss_ratio": round(win_loss_ratio, 2),
        "expectancy_per_trade": round(expectancy, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "max_drawdown_amt": round(max_drawdown_amt, 2),
        "sharpe_ratio": round(sharpe_ratio, 2),
        "sortino_ratio": round(sortino_ratio, 2),
        "calmar_ratio": round(calmar_ratio, 2),
        "total_charges_incurred": round(total_charges, 2),
        "trading_days": trading_days,
        "daily_win_rate_pct": round(daily_win_rate, 2),
        "exit_reasons": exit_reasons
    }

