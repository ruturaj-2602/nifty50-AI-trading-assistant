"""
HTML and Visual Report Generator for NIFTY Options AI Bot.
Creates an interactive dashboard and equity curve charts.
"""
import os
import tempfile
os.environ.setdefault("MPLCONFIGDIR", os.path.join(tempfile.gettempdir(), "matplotlib_cache"))
import json
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from typing import Dict, Any, List

REPORT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports")

def generate_charts(equity_curve: List[Dict[str, Any]], trades_df: pd.DataFrame, output_dir: str = REPORT_DIR):
    """Generates equity curve and drawdown charts using Matplotlib."""
    os.makedirs(output_dir, exist_ok=True)
    eq_df = pd.DataFrame(equity_curve)
    
    if eq_df.empty or 'capital' not in eq_df.columns:
        return None
        
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={'height_ratios': [2.5, 1]})
    
    # Equity Curve
    dates = range(len(eq_df))
    capital = eq_df['capital'].values
    running_max = pd.Series(capital).cummax().values
    drawdown = (capital - running_max) / running_max * 100.0
    
    ax1.plot(dates, capital, label='Portfolio Capital (₹)', color='#00C853', linewidth=2.0)
    ax1.plot(dates, running_max, label='High Watermark', color='#B0BEC5', linestyle='--', alpha=0.7)
    ax1.set_title('NIFTY Intraday Options Trading AI - Equity Growth Curve', fontsize=14, fontweight='bold', pad=12)
    ax1.set_ylabel('Capital (INR)', fontsize=11)
    ax1.grid(True, linestyle=':', alpha=0.6)
    ax1.legend(loc='upper left')
    
    # Drawdown Chart
    ax2.fill_between(dates, drawdown, 0, color='#D32F2F', alpha=0.4, label='Drawdown (%)')
    ax2.plot(dates, drawdown, color='#D32F2F', linewidth=1.2)
    ax2.set_title('Underwater Drawdown Profile', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Drawdown (%)', fontsize=11)
    ax2.set_xlabel('Trading Session Index', fontsize=11)
    ax2.grid(True, linestyle=':', alpha=0.6)
    ax2.legend(loc='lower left')
    
    plt.tight_layout()
    chart_path = os.path.join(output_dir, "equity_curve.png")
    plt.savefig(chart_path, dpi=200)
    plt.close()
    return chart_path

def generate_html_report(
    metrics: Dict[str, Any],
    trades_df: pd.DataFrame,
    equity_curve: List[Dict[str, Any]],
    latest_advisory: Dict[str, Any] = None,
    output_dir: str = REPORT_DIR
) -> str:
    """Generates an institutional-grade HTML dashboard report."""
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, "nifty_ai_report.html")
    
    # Prepare trade table rows
    trade_rows_html = ""
    if not trades_df.empty:
        for _, t in trades_df.tail(50).iterrows():
            pnl_cls = "text-success" if t['net_pnl'] > 0 else "text-danger"
            trade_rows_html += f"""
            <tr>
                <td>{t['trade_id']}</td>
                <td>{t['entry_date']}</td>
                <td>{t['entry_time']} - {t['exit_time']}</td>
                <td><strong>{t['contract']}</strong></td>
                <td>{t['lots']}</td>
                <td>₹{t['entry_premium']:.1f}</td>
                <td>₹{t['exit_premium']:.1f}</td>
                <td class="{pnl_cls}"><strong>₹{t['net_pnl']:+,.1f}</strong></td>
                <td class="{pnl_cls}">{t['pnl_pct']:+.1f}%</td>
                <td><span class="badge bg-secondary">{t['exit_reason']}</span></td>
            </tr>
            """
            
    # Advisory card HTML
    advisory_html = ""
    if latest_advisory:
        adv = latest_advisory
        badge_cls = "bg-success" if adv['option_type'] == "CE" else "bg-danger"
        confluences_li = "".join([f"<li>{c}</li>" for c in adv['confluences']])
        plan_li = "".join([f"<li>{p}</li>" for p in adv['management_plan']])
        
        advisory_html = f"""
        <div class="card mb-4 border-primary shadow-sm">
            <div class="card-header bg-dark text-white d-flex justify-content-between align-items-center">
                <h5 class="mb-0">🤖 Live AI Trade Recommendation</h5>
                <span class="badge {badge_cls} fs-6">{adv['contract']}</span>
            </div>
            <div class="card-body">
                <div class="row g-3">
                    <div class="col-md-3">
                        <small class="text-muted">Underlying Spot</small>
                        <h4 class="fw-bold">₹{adv['spot_price']:,.2f}</h4>
                    </div>
                    <div class="col-md-3">
                        <small class="text-muted">Option Entry Premium</small>
                        <h4 class="fw-bold text-primary">₹{adv['entry_premium']:.2f}</h4>
                    </div>
                    <div class="col-md-3">
                        <small class="text-muted">Stop Loss (Premium / Spot)</small>
                        <h4 class="fw-bold text-danger">₹{adv['sl_premium']:.2f} <small class="text-muted fs-6">({adv['spot_sl']:.0f})</small></h4>
                    </div>
                    <div class="col-md-3">
                        <small class="text-muted">Target 1 (Premium / Spot)</small>
                        <h4 class="fw-bold text-success">₹{adv['target_premium']:.2f} <small class="text-muted fs-6">({adv['spot_target']:.0f})</small></h4>
                    </div>
                </div>
                <hr/>
                <div class="row">
                    <div class="col-md-6">
                        <h6>Quantitative Confluences</h6>
                        <ul>{confluences_li}</ul>
                    </div>
                    <div class="col-md-6">
                        <h6>Trade Management Rules</h6>
                        <ul>{plan_li}</ul>
                    </div>
                </div>
            </div>
        </div>
        """

    # Equity data for chart.js
    dates_js = json.dumps([e['date'] for e in equity_curve])
    caps_js = json.dumps([e['capital'] for e in equity_curve])

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NIFTY Intraday Options AI - Institutional Analytics Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ background-color: #0e1117; color: #f0f2f5; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        .card {{ background-color: #1a1f2c; border-color: #2b3245; color: #f0f2f5; border-radius: 10px; }}
        .table {{ color: #e1e7f0; }}
        .metric-title {{ font-size: 0.85rem; color: #94a3b8; text-transform: uppercase; font-weight: 600; }}
        .metric-val {{ font-size: 1.6rem; font-weight: 700; margin-top: 4px; }}
        .text-success {{ color: #10b981 !important; }}
        .text-danger {{ color: #ef4444 !important; }}
    </style>
</head>
<body class="p-4">
    <div class="container-fluid">
        <header class="d-flex justify-content-between align-items-center pb-3 mb-4 border-bottom border-secondary">
            <div>
                <h2 class="fw-bold text-white mb-0">⚡ NIFTY INTRADAY OPTIONS AI BOT & ANALYST</h2>
                <small class="text-secondary">Walk-Forward Out-Of-Sample Backtesting & Signal Generator Engine</small>
            </div>
            <div class="text-end">
                <span class="badge bg-primary px-3 py-2">NIFTY 50 INDEX</span>
                <span class="badge bg-dark px-3 py-2 border border-secondary ms-2">15:15 IST Square-off</span>
            </div>
        </header>

        {advisory_html}

        <!-- Key Metrics Cards -->
        <div class="row g-3 mb-4">
            <div class="col-md-2">
                <div class="card p-3">
                    <div class="metric-title">Net Profit</div>
                    <div class="metric-val text-success">₹{metrics['net_profit']:+,.0f}</div>
                    <small class="text-muted">Return: {metrics['net_return_pct']:+.1f}%</small>
                </div>
            </div>
            <div class="col-md-2">
                <div class="card p-3">
                    <div class="metric-title">Win Rate</div>
                    <div class="metric-val text-warning">{metrics['win_rate_pct']:.1f}%</div>
                    <small class="text-muted">{metrics['winning_trades']}W / {metrics['losing_trades']}L</small>
                </div>
            </div>
            <div class="col-md-2">
                <div class="card p-3">
                    <div class="metric-title">Profit Factor</div>
                    <div class="metric-val text-info">{metrics['profit_factor']:.2f}</div>
                    <small class="text-muted">Gross W / L Ratio</small>
                </div>
            </div>
            <div class="col-md-2">
                <div class="card p-3">
                    <div class="metric-title">Sharpe Ratio</div>
                    <div class="metric-val text-success">{metrics['sharpe_ratio']:.2f}</div>
                    <small class="text-muted">Sortino: {metrics['sortino_ratio']:.2f}</small>
                </div>
            </div>
            <div class="col-md-2">
                <div class="card p-3">
                    <div class="metric-title">Max Drawdown</div>
                    <div class="metric-val text-danger">-{metrics['max_drawdown_pct']:.1f}%</div>
                    <small class="text-muted">-₹{metrics['max_drawdown_amt']:,.0f}</small>
                </div>
            </div>
            <div class="col-md-2">
                <div class="card p-3">
                    <div class="metric-title">Expectancy / Trade</div>
                    <div class="metric-val text-success">₹{metrics['expectancy_per_trade']:+,.0f}</div>
                    <small class="text-muted">Avg Win: ₹{metrics['avg_win']:,.0f}</small>
                </div>
            </div>
        </div>

        <!-- Equity Chart -->
        <div class="card p-4 mb-4">
            <h5 class="fw-bold mb-3">📈 Portfolio Equity Curve (₹)</h5>
            <canvas id="equityChart" height="90"></canvas>
        </div>

        <!-- Trade Execution History -->
        <div class="card p-4">
            <h5 class="fw-bold mb-3">📜 Trade Execution History</h5>
            <div class="table-responsive">
                <table class="table table-hover align-middle">
                    <thead class="table-dark">
                        <tr>
                            <th>#</th>
                            <th>Date</th>
                            <th>Window</th>
                            <th>Contract</th>
                            <th>Lots</th>
                            <th>Entry ₹</th>
                            <th>Exit ₹</th>
                            <th>Net PnL</th>
                            <th>Return %</th>
                            <th>Exit Trigger</th>
                        </tr>
                    </thead>
                    <tbody>
                        {trade_rows_html}
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        const ctx = document.getElementById('equityChart').getContext('2d');
        const dates = {dates_js};
        const caps = {caps_js};
        
        new Chart(ctx, {{
            type: 'line',
            data: {{
                labels: dates,
                datasets: [{{
                    label: 'Portfolio Equity (₹)',
                    data: caps,
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    borderWidth: 2.5,
                    fill: true,
                    tension: 0.2
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{ labels: {{ color: '#e1e7f0' }} }}
                }},
                scales: {{
                    x: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#2b3245' }} }},
                    y: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#2b3245' }} }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    return report_path
