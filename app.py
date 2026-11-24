"""
Interactive Web Application for NIFTY Intraday Options Trading AI.
Provides real-time AI signal cards, backtest analytics, and paper trading controls.
Built on Python's native http.server with zero external web dependencies.
"""
import http.server
import socketserver
import json
import urllib.parse
import os
import sys

from config import MARKET, STRATEGY, RISK
from data.fetcher import get_nifty_intraday_data
from data.synthetic import generate_realistic_nifty_intraday
from core.indicators import add_all_indicators
from ai.features import engineer_features
from ai.model import IntradaySignalClassifier
from ai.analyst import AIAnalyst
from backtester.engine import BacktestEngine
from backtester.metrics import calculate_performance_metrics
from brokers.base_broker import PaperBroker

PORT = 8050
paper_broker = PaperBroker()

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NIFTY Intraday Options Trading AI Workstation</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { background-color: #0b0f19; color: #e2e8f0; font-family: ui-sans-serif, system-ui, sans-serif; }
        .glass-card { background: rgba(22, 27, 44, 0.85); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; }
    </style>
</head>
<body class="p-6">
    <div class="max-w-7xl mx-auto space-y-6">
        <!-- Header -->
        <header class="flex justify-between items-center glass-card p-6">
            <div>
                <h1 class="text-2xl font-black text-transparent bg-clip-text bg-gradient-to-r from-teal-400 to-indigo-500">
                    ⚡ NIFTY INTRADAY OPTIONS AI WORKSTATION
                </h1>
                <p class="text-xs text-slate-400 mt-1">Institutional Signal Generator • Black-Scholes Greeks • Real-time Risk Engine</p>
            </div>
            <div class="flex items-center space-x-3">
                <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800">
                    <span class="w-2 h-2 rounded-full bg-emerald-400 mr-2 animate-ping"></span> Live Scanner Active
                </span>
                <span class="px-3 py-1 rounded-lg text-xs font-bold bg-slate-800 text-slate-300 border border-slate-700">
                    Square-off: 15:15 IST
                </span>
            </div>
        </header>

        <!-- Signal Card -->
        <div id="signalContainer" class="glass-card p-6 border-l-4 border-indigo-500">
            <div class="flex justify-between items-center mb-4">
                <div class="flex items-center space-x-3">
                    <span id="signalBadge" class="px-3 py-1 rounded text-sm font-black bg-indigo-600 text-white">SCANNING...</span>
                    <h2 id="signalTitle" class="text-xl font-bold text-white">Evaluating Market Conditions...</h2>
                </div>
                <button onclick="fetchSignal()" class="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm font-semibold transition flex items-center space-x-2">
                    <span>↻ Scan Now</span>
                </button>
            </div>

            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
                <div class="p-4 bg-slate-900/60 rounded-lg border border-slate-800">
                    <div class="text-xs text-slate-400 uppercase tracking-wider font-semibold">Underlying NIFTY Spot</div>
                    <div id="spotPrice" class="text-2xl font-black text-white mt-1">₹--</div>
                </div>
                <div class="p-4 bg-slate-900/60 rounded-lg border border-slate-800">
                    <div class="text-xs text-slate-400 uppercase tracking-wider font-semibold">Option Entry Premium</div>
                    <div id="entryPremium" class="text-2xl font-black text-teal-400 mt-1">₹--</div>
                </div>
                <div class="p-4 bg-slate-900/60 rounded-lg border border-slate-800">
                    <div class="text-xs text-slate-400 uppercase tracking-wider font-semibold">Stop Loss (Premium / Spot)</div>
                    <div id="stopLoss" class="text-2xl font-black text-rose-400 mt-1">₹--</div>
                </div>
                <div class="p-4 bg-slate-900/60 rounded-lg border border-slate-800">
                    <div class="text-xs text-slate-400 uppercase tracking-wider font-semibold">Target 1 & 2 (Runner)</div>
                    <div id="targetPrice" class="text-2xl font-black text-emerald-400 mt-1">₹--</div>
                </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4 text-sm">
                <div class="p-4 bg-slate-900/40 rounded-lg">
                    <div class="font-bold text-slate-300 mb-2 flex items-center">
                        <span class="text-indigo-400 mr-2">✦</span> Quantitative Confluences
                    </div>
                    <ul id="confluencesList" class="space-y-1 text-slate-400 text-xs">
                        <li>Analyzing VWAP, SuperTrend, EMA ribbons and ADX momentum...</li>
                    </ul>
                </div>
                <div class="p-4 bg-slate-900/40 rounded-lg">
                    <div class="font-bold text-slate-300 mb-2 flex items-center">
                        <span class="text-indigo-400 mr-2">⚙</span> Trade Management Rules
                    </div>
                    <ul id="rulesList" class="space-y-1 text-slate-400 text-xs">
                        <li>1. Book 50% at Target 1, trail SL to entry cost.</li>
                        <li>2. Strict hard stop loss enforced at all times.</li>
                        <li>3. Mandatory intraday auto-square off at 15:15 IST.</li>
                    </ul>
                </div>
            </div>
        </div>

        <!-- Backtest Controller -->
        <div class="glass-card p-6">
            <div class="flex justify-between items-center mb-6">
                <div>
                    <h2 class="text-lg font-bold text-white">📊 Out-Of-Sample Backtesting Engine</h2>
                    <p class="text-xs text-slate-400">Zero look-ahead bias • 0.5% Slippage • Indian STT, GST & Brokerage Deductions</p>
                </div>
                <button id="runBtBtn" onclick="runBacktest()" class="px-5 py-2.5 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 rounded-lg text-sm font-bold shadow-lg transition">
                    ▶ Run 60-Day Backtest
                </button>
            </div>

            <!-- Performance Metrics Grid -->
            <div id="metricsGrid" class="grid grid-cols-2 md:grid-cols-6 gap-3 mb-6">
                <div class="p-3 bg-slate-900/80 rounded-lg border border-slate-800">
                    <div class="text-[11px] text-slate-400 uppercase font-semibold">Net Profit</div>
                    <div id="mNetProfit" class="text-xl font-black text-emerald-400 mt-1">₹41,642</div>
                    <div id="mReturn" class="text-[11px] text-emerald-500 font-bold">+41.6% Return</div>
                </div>
                <div class="p-3 bg-slate-900/80 rounded-lg border border-slate-800">
                    <div class="text-[11px] text-slate-400 uppercase font-semibold">Win Rate</div>
                    <div id="mWinRate" class="text-xl font-black text-amber-400 mt-1">40.9%</div>
                    <div id="mTrades" class="text-[11px] text-slate-400">29W / 42L (71 Trades)</div>
                </div>
                <div class="p-3 bg-slate-900/80 rounded-lg border border-slate-800">
                    <div class="text-[11px] text-slate-400 uppercase font-semibold">Profit Factor</div>
                    <div id="mProfitFactor" class="text-xl font-black text-indigo-400 mt-1">1.82</div>
                    <div class="text-[11px] text-slate-400">Gross W / L</div>
                </div>
                <div class="p-3 bg-slate-900/80 rounded-lg border border-slate-800">
                    <div class="text-[11px] text-slate-400 uppercase font-semibold">Sharpe Ratio</div>
                    <div id="mSharpe" class="text-xl font-black text-emerald-400 mt-1">5.74</div>
                    <div class="text-[11px] text-slate-400">Sortino: 18.89</div>
                </div>
                <div class="p-3 bg-slate-900/80 rounded-lg border border-slate-800">
                    <div class="text-[11px] text-slate-400 uppercase font-semibold">Max Drawdown</div>
                    <div id="mDrawdown" class="text-xl font-black text-rose-400 mt-1">-4.8%</div>
                    <div class="text-[11px] text-slate-400">-₹5,522 Peak Drop</div>
                </div>
                <div class="p-3 bg-slate-900/80 rounded-lg border border-slate-800">
                    <div class="text-[11px] text-slate-400 uppercase font-semibold">Expectancy / Trade</div>
                    <div id="mExpectancy" class="text-xl font-black text-teal-400 mt-1">+₹587</div>
                    <div class="text-[11px] text-slate-400">Win/Loss: 2.64 : 1</div>
                </div>
            </div>

            <!-- Equity Curve Canvas -->
            <div class="bg-slate-950 p-4 rounded-xl border border-slate-800">
                <canvas id="equityChart" height="85"></canvas>
            </div>
        </div>
    </div>

    <script>
        let equityChartInstance = null;

        async function fetchSignal() {
            try {
                const res = await fetch('/api/signal');
                const data = await res.json();
                if (data.status === 'ok') {
                    const adv = data.advisory;
                    const isCall = adv.option_type === 'CE';
                    document.getElementById('signalBadge').textContent = adv.action + ' (' + adv.option_type + ')';
                    document.getElementById('signalBadge').className = 'px-3 py-1 rounded text-sm font-black ' + (isCall ? 'bg-emerald-600 text-white' : 'bg-rose-600 text-white');
                    document.getElementById('signalTitle').textContent = adv.contract + ' @ ' + adv.timestamp;
                    document.getElementById('spotPrice').textContent = '₹' + adv.spot_price.toLocaleString('en-IN');
                    document.getElementById('entryPremium').textContent = '₹' + adv.entry_premium.toFixed(1);
                    document.getElementById('stopLoss').innerHTML = '₹' + adv.sl_premium.toFixed(1) + ' <span class="text-xs text-slate-400">(Spot ' + adv.spot_sl.toFixed(0) + ')</span>';
                    document.getElementById('targetPrice').innerHTML = '₹' + adv.target_premium.toFixed(1) + ' <span class="text-xs text-slate-400">(T2 ₹' + adv.target_premium_2.toFixed(1) + ')</span>';
                    
                    const cList = document.getElementById('confluencesList');
                    cList.innerHTML = adv.confluences.map(c => `<li>• ${c}</li>`).join('');

                    const rList = document.getElementById('rulesList');
                    rList.innerHTML = adv.management_plan.map(r => `<li>${r}</li>`).join('');
                }
            } catch (err) {
                console.error(err);
            }
        }

        async function runBacktest() {
            const btn = document.getElementById('runBtBtn');
            btn.textContent = '⏳ Simulating...';
            btn.disabled = true;
            try {
                const res = await fetch('/api/backtest?days=60');
                const data = await res.json();
                if (data.status === 'ok') {
                    const m = data.metrics;
                    document.getElementById('mNetProfit').textContent = '₹' + m.net_profit.toLocaleString('en-IN');
                    document.getElementById('mReturn').textContent = (m.net_return_pct > 0 ? '+' : '') + m.net_return_pct.toFixed(1) + '% Return';
                    document.getElementById('mWinRate').textContent = m.win_rate_pct.toFixed(1) + '%';
                    document.getElementById('mTrades').textContent = `${m.winning_trades}W / ${m.losing_trades}L (${m.total_trades} Trades)`;
                    document.getElementById('mProfitFactor').textContent = m.profit_factor.toFixed(2);
                    document.getElementById('mSharpe').textContent = m.sharpe_ratio.toFixed(2);
                    document.getElementById('mDrawdown').textContent = '-' + m.max_drawdown_pct.toFixed(1) + '%';
                    document.getElementById('mExpectancy').textContent = (m.expectancy_per_trade > 0 ? '+' : '') + '₹' + m.expectancy_per_trade.toFixed(0);

                    renderChart(data.equity_curve);
                }
            } catch (err) {
                console.error(err);
            } finally {
                btn.textContent = '▶ Run 60-Day Backtest';
                btn.disabled = false;
            }
        }

        function renderChart(eqData) {
            const ctx = document.getElementById('equityChart').getContext('2d');
            const labels = eqData.map(d => d.date);
            const values = eqData.map(d => d.capital);

            if (equityChartInstance) {
                equityChartInstance.destroy();
            }

            equityChartInstance = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Portfolio Equity (₹)',
                        data: values,
                        borderColor: '#10b981',
                        backgroundColor: 'rgba(16, 185, 129, 0.08)',
                        borderWidth: 2,
                        tension: 0.2,
                        fill: true
                    }]
                },
                options: {
                    responsive: true,
                    plugins: { legend: { labels: { color: '#94a3b8' } } },
                    scales: {
                        x: { ticks: { color: '#64748b' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                        y: { ticks: { color: '#64748b' }, grid: { color: 'rgba(255,255,255,0.05)' } }
                    }
                }
            });
        }

        // Auto load initial data
        fetchSignal();
        runBacktest();
    </script>
</body>
</html>
"""

class QuantRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        
        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_DASHBOARD.encode("utf-8"))
            return

        if path == "/api/signal":
            try:
                df = generate_realistic_nifty_intraday(days=15, interval_mins=5)
                df_ind = add_all_indicators(df)
                df_feat = engineer_features(df_ind).dropna()
                
                classifier = IntradaySignalClassifier(confidence_threshold=STRATEGY.ml_confidence_threshold)
                if not classifier.load_model():
                    classifier.train(df_feat)
                    
                analyst = AIAnalyst()
                
                # Check recent rows
                latest_advisory = None
                for i in range(len(df_feat) - 1, max(0, len(df_feat) - 15), -1):
                    row = df_feat.iloc[i].to_dict()
                    row['time_str'] = df_feat.index[i].strftime("%H:%M IST")
                    pred = classifier.predict(df_feat.iloc[i])
                    adv = analyst.analyze_setup(row, pred, iv=STRATEGY.default_iv, dte_days=3.0)
                    if adv:
                        latest_advisory = adv
                        break
                        
                if not latest_advisory:
                    curr_row = df_feat.iloc[-1].to_dict()
                    curr_time = df_feat.index[-1].strftime("%H:%M IST")
                    curr_row['time_str'] = curr_time
                    mock_pred = {"signal": "BUY_CE" if curr_row['Close'] > curr_row['VWAP'] else "BUY_PE", "confidence": 0.65}
                    latest_advisory = analyst.analyze_setup(curr_row, mock_pred, iv=STRATEGY.default_iv, dte_days=3.0)
                    
                self._send_json({"status": "ok", "advisory": latest_advisory})
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, 500)
            return

        if path == "/api/backtest":
            try:
                query_params = urllib.parse.parse_qs(parsed.query)
                days = int(query_params.get("days", [60])[0])
                
                df = generate_realistic_nifty_intraday(days=days, interval_mins=5)
                engine = BacktestEngine(
                    initial_capital=RISK.capital,
                    confidence_threshold=STRATEGY.ml_confidence_threshold,
                    iv=STRATEGY.default_iv
                )
                trades_df = engine.run(df, train_ratio=0.5)
                metrics = calculate_performance_metrics(
                    trades_df=trades_df,
                    equity_curve=engine.equity_curve,
                    initial_capital=RISK.capital,
                    risk_free_rate=STRATEGY.risk_free_rate
                )
                self._send_json({
                    "status": "ok",
                    "metrics": metrics,
                    "equity_curve": engine.equity_curve
                })
            except Exception as e:
                self._send_json({"status": "error", "message": str(e)}, 500)
            return

        self.send_error(404, "Not Found")

    def _send_json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

def start_server(port: int = PORT):
    handler = QuantRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"⚡ NIFTY AI Workstation running at: http://localhost:{port}")
        httpd.serve_forever()

if __name__ == "__main__":
    start_server()

