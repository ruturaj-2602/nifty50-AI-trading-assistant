# ⚡ NIFTY Intraday Options Trading AI Bot & Analyst

An institutional-grade, quantitative AI trading system designed specifically for **NSE NIFTY 50 Index Options**. It combines multi-timeframe market microstructure, technical indicators (VWAP, SuperTrend, EMA ribbons, ADX), Black-Scholes Greeks modeling, and Marcos López de Prado's Triple-Barrier Machine Learning classification to generate high-probability trade setups with precise strike selection, entry premiums, stop losses, and targets.

---

## 🎯 Key Capabilities

1. **High-Probability AI Signal Generator**:
   - Predicts direction (Bullish Call `CE` or Bearish Put `PE`).
   - Dynamic strike selector (ATM, ITM, OTM).
   - Exact Stop Loss & Take Profit mapped from Spot points to Option Premium points using **Black-Scholes Delta & Gamma**.
   - Dual Targets: Target 1 (book 50%, trail SL to Cost) and Target 2 (runner).

2. **Institutional Risk & Money Management**:
   - Risk budgeting per trade (1.5% capital target risk).
   - Position sizing calculated dynamically based on premium and stop loss.
   - Max 3 trades per day circuit breaker to prevent overtrading.
   - Strict **15:15 IST mandatory intraday square-off** to eliminate overnight gap risk.

3. **Realistic Indian Market Friction Accounting**:
   - Accounts for **0.5% slippage** on market orders.
   - Flat brokerage: ₹20 buy + ₹20 sell = ₹40 round trip.
   - STT: 0.0625% on option sell turnover.
   - Exchange transaction charges: 0.05%.
   - SEBI turnover charges & Stamp Duty (0.003%).
   - GST: 18% on (Brokerage + Exchange fees).

4. **Walk-Forward Out-Of-Sample Backtesting Engine**:
   - Event-driven, bar-by-bar simulation with zero look-ahead bias.
   - Calculates **Sharpe Ratio**, **Sortino Ratio**, **Calmar Ratio**, **Profit Factor**, **Expectancy**, and **Drawdown**.
   - Generates interactive HTML dashboard reports and visual equity curve PNG charts.

---

## 🚀 Quick Start Guide

### 1. Requirements
Ensure Python 3.10+ is installed. Dependencies:
```bash
pip install numpy pandas scipy scikit-learn yfinance matplotlib rich tabulate
```

### 2. Run Backtest
Run a walk-forward out-of-sample backtest over 60 trading days:
```bash
python main.py --mode backtest --source synthetic --days 60
```
*(Or test with live Yahoo Finance data using `--source yahoo`)*

The engine will output:
- Full summary table with Sharpe, Sortino, Max Drawdown, and Win/Loss metrics.
- Recent 12-trade execution log.
- High-resolution equity curve chart saved to `reports/equity_curve.png`.
- Interactive HTML report saved to `reports/nifty_ai_report.html`.

### 3. Generate Live / Latest Signal
Scan the market for the latest actionable trade setup:
```bash
python main.py --mode signal
```

Outputs an institutional AI Analyst Card:
```text
╔══════════════════════ AI Trade Signal: NIFTY 23250 PE ══════════════════════╗
║  BUY PUT (PE)   Trade Signal Generated at 15:25 IST                         ║
║                                                                             ║
║ Technical & Quantitative Confluences:                                       ║
║   • Bearish: Trading below Intraday VWAP                                    ║
║   • Bearish: SuperTrend Resistance @ 23,277.2                               ║
║   • Bearish: RSI Momentum Declining (44.6)                                  ║
║   • Trend Strength: ADX Strong (25.5)                                       ║
║                                                                             ║
║ Trade Execution & Management Rules:                                         ║
║   1. Entry: Buy at ₹121.8 (Option) / 23,228.7 (Spot)                        ║
║   2. Stop Loss: Hard Stop at ₹102.8 (Max loss ₹476/lot)                     ║
║   3. Target 1: Book 50% lots at ₹154.3 (+₹812/lot)                          ║
║   4. Target 2: Trail remaining lots to ₹168.6 (+₹1,169/lot)                 ║
║   5. Trailing Rule: Move Stop Loss to Cost (₹121.8) once Target 1 is hit    ║
║   6. Mandatory Exit: Close all open intraday positions before 15:15 IST     ║
╚═════════════════════════════════════════════════════════════════════════════╝
```

---

## 🏗️ Project Architecture

```
Nifty Intraday Options Trading AI/
├── config.py                 # Core market, strategy, and risk configurations
├── main.py                   # CLI entrypoint for backtesting and signal generation
├── data/
│   ├── fetcher.py            # Yahoo Finance (^NSEI) fetcher with local caching
│   └── synthetic.py          # Calibrated NSE microstructure intraday generator
├── core/
│   ├── indicators.py         # VWAP, SuperTrend, EMA 9/21/50/200, ATR, RSI, ADX
│   ├── options_pricer.py     # Black-Scholes Greeks engine & Spot-to-Option SL/TP mapper
│   └── risk_manager.py       # Position sizing, daily circuit breakers, STT/taxes/charges
├── ai/
│   ├── features.py           # Multi-timeframe quantitative feature pipeline
│   ├── model.py              # Triple-barrier labeler & HistGradientBoosting classifier
│   └── analyst.py            # AI Trading Analyst commentary & advisory builder
├── backtester/
│   ├── engine.py             # Event-driven walk-forward backtest simulation
│   └── metrics.py            # Sharpe, Sortino, Calmar, Profit Factor & Expectancy
├── ui/
│   ├── cli_view.py           # Rich terminal tables, banners, and signal cards
│   └── report_generator.py   # HTML interactive dashboard & Matplotlib charts
└── reports/                  # Generated equity curves and HTML reports
```

---

## 📈 Live Broker Integration

### Angel One SmartAPI (Configured & Verified ✓)
Configure your Angel One credentials in `.env`:
- **Client Code**: `YOUR_CLIENT_CODE`
- **Dynamic 2FA**: Automatic TOTP generation enabled via `pyotp`.

1. **Test Connection Anytime**:
   ```bash
   python test_angel_connection.py
   ```
2. **Run Live Market Scanner with Angel One**:
   ```bash
   # Advisory Mode (Generates signals & monitors market using Angel One)
   python main.py --mode live --broker angel

   # Auto-Trade Mode (Directly places MIS Intraday orders on NFO)
   python main.py --mode live --broker angel --auto
   ```

### Other Supported Brokers
- **Zerodha Kite Connect**: Subscribe to WebSocket ticks, feed candles to `add_all_indicators`, and execute orders via `kite.place_order()`.
- **Dhan / Shoonya Finvasia**: Zero-brokerage trading using the exact limit/stop-loss order parameters calculated by `AIAnalyst`.

