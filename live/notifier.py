"""
Notification and Alert Dispatcher for NIFTY Options AI Bot.
Formats mobile-ready instant alerts for Telegram, WhatsApp, Discord, or Webhooks.
"""
import os
import requests
from typing import Dict, Any, Optional

from config import MARKET, load_dotenv

load_dotenv()

def format_telegram_alert(advisory: Dict[str, Any], lots: int = 1, quantity: int = 65) -> str:
    """
    Formats institutional trade setup alert for mobile channels (Telegram / WhatsApp).
    """
    is_ce = advisory['option_type'] == "CE"
    direction_emoji = "🟢" if is_ce else "🔴"
    action_text = "BUY CALL (CE)" if is_ce else "BUY PUT (PE)"
    
    confluences = "\n".join([f"  • {c}" for c in advisory.get('confluences', [])])
    
    sl_pts = max(advisory['entry_premium'] - advisory['sl_premium'], 1.0)
    target_pts = max(advisory['target_premium'] - advisory['entry_premium'], 1.0)
    target2_pts = max(advisory['target_premium_2'] - advisory['entry_premium'], 1.0)
    
    msg = f"""
⚡ *NIFTY INTRADAY AI TRADE ALERT* ⚡
━━━━━━━━━━━━━━━━━━━━━━━━━━
{direction_emoji} *ACTION:* {action_text}
📌 *CONTRACT:* `{advisory['contract']}`
📊 *UNDERLYING SPOT:* ₹{advisory['spot_price']:,.2f}
🎯 *AI WIN CONFIDENCE:* {advisory['ai_confidence']}
━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 *EXECUTION LEVELS (OPTION PREMIUM):*
• *Action:* BUY AT CURRENT MARKET PRICE (CMP ~₹{advisory['entry_premium']:.1f})
• *Stop Loss:* Entry - {sl_pts:.1f} pts  [~₹{advisory['sl_premium']:.1f}]  *(Spot: {advisory['spot_sl']:.0f})*
• *Target 1 (50%):* Entry + {target_pts:.1f} pts  [~₹{advisory['target_premium']:.1f}]  *(Spot: {advisory['spot_target']:.0f})*
• *Target 2 (Runner):* Entry + {target2_pts:.1f} pts  [~₹{advisory['target_premium_2']:.1f}]  *(Spot: {advisory['spot_target_2']:.0f})*
• *Risk : Reward:* {advisory['risk_reward_ratio']}
━━━━━━━━━━━━━━━━━━━━━━━━━━
💼 *CAPITAL & POSITION SIZING:*
• *Recommended Size:* {lots} Lots ({quantity} Qty)
• *Max Risk per Lot:* -₹{advisory['risk_per_lot']:,.0f}
• *Expected Profit (T1):* +₹{advisory['gain_per_lot']:,.0f} / lot
• *Greeks:* Delta {advisory['delta']} | Daily Theta ₹{advisory['theta_daily']:.1f}
━━━━━━━━━━━━━━━━━━━━━━━━━━
🧠 *QUANTITATIVE CONFLUENCES:*
{confluences}
━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ *TRADE MANAGEMENT RULES:*
1. *Enter IMMEDIATELY at Market Price (CMP).* Do not wait for any higher price.
2. Place Stop Loss ~{sl_pts:.0f} pts below your actual buy price.
3. Once Target 1 (+{target_pts:.0f} pts) is hit, *trail SL to Cost*.
4. Auto square-off if not exited before *15:15 IST*.
━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    return msg.strip()

def format_target1_alert(contract: str, entry_premium: float, target_premium: float, lots: int = 1, quantity: int = 65) -> str:
    """Alert triggered when Target 1 is achieved and SL moves to breakeven."""
    gain_pts = max(target_premium - entry_premium, 0.0)
    gain_booked = (gain_pts * quantity) * 0.5  # 50% booked
    return f"""
🎯 *TARGET 1 HIT — PROFIT BOOKING ALERT* 🎯
━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 *Contract:* `{contract}`
💰 *Entry Price:* ₹{entry_premium:.1f}
🚀 *Target 1 Hit:* ₹{target_premium:.1f} (+{gain_pts:.1f} pts)
━━━━━━━━━━━━━━━━━━━━━━━━━━
🔒 *ACTIONS TO TAKE NOW:*
1. *Book 50% lots* (+₹{gain_booked:,.0f} profit secured)
2. *Move Stop Loss to Cost: ₹{entry_premium:.1f}*
✨ *Trade is now 100% Risk-Free!*
🏃 *Let remaining lots run toward Target 2.*
━━━━━━━━━━━━━━━━━━━━━━━━━━
""".strip()

def format_target2_alert(contract: str, entry_premium: float, target_premium_2: float, lots: int = 1, quantity: int = 65) -> str:
    """Alert triggered when Target 2 runner is hit."""
    gain_pts = max(target_premium_2 - entry_premium, 0.0)
    total_gain = gain_pts * quantity
    return f"""
🚀 *TARGET 2 HIT — MAXIMUM TARGET ACHIEVED* 🚀
━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 *Contract:* `{contract}`
💰 *Entry Price:* ₹{entry_premium:.1f}
🎯 *Target 2 Hit:* ₹{target_premium_2:.1f} (+{gain_pts:.1f} pts)
━━━━━━━━━━━━━━━━━━━━━━━━━━
🏆 *FINAL TRADE OUTCOME:*
• *Total Gain:* +₹{total_gain:,.2f}
• *Exit Action:* Close all remaining open positions.
• *Trade Complete!*
━━━━━━━━━━━━━━━━━━━━━━━━━━
""".strip()

def format_stoploss_alert(contract: str, entry_premium: float, sl_premium: float, lots: int = 1, quantity: int = 65, was_trailed: bool = False) -> str:
    """Alert triggered when Stop Loss is hit."""
    if was_trailed:
        return f"""
🛡️ *STOP LOSS HIT (AT BREAKEVEN / COST)* 🛡️
━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 *Contract:* `{contract}`
💰 *Entry Cost:* ₹{entry_premium:.1f}
🛑 *Exit Price:* ₹{sl_premium:.1f}
━━━━━━━━━━━━━━━━━━━━━━━━━━
✨ *Capital Protected:* Stop loss was trailed to cost after Target 1.
🔒 *Net P&L on Runner:* ₹0.00 (Breakeven - No Loss!)
• *Exit Action:* All open lots closed.
━━━━━━━━━━━━━━━━━━━━━━━━━━
""".strip()
    else:
        loss_pts = max(entry_premium - sl_premium, 0.0)
        loss_per_lot = loss_pts * (quantity / max(lots, 1))
        total_loss = loss_pts * quantity
        return f"""
🛑 *STOP LOSS HIT — CAPITAL PROTECTION EXIT* 🛑
━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 *Contract:* `{contract}`
💰 *Entry Price:* ₹{entry_premium:.1f}
🛑 *Exit Price:* ₹{sl_premium:.1f} (-{loss_pts:.1f} pts)
━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ *TRADE OUTCOME:*
• *Loss per Lot:* -₹{loss_per_lot:,.0f}
• *Total Loss:* -₹{total_loss:,.2f}
• *Exit Action:* Hard Stop Loss triggered. Discipline maintained.
━━━━━━━━━━━━━━━━━━━━━━━━━━
""".strip()

def format_time_squareoff_alert(contract: str, entry_premium: float, exit_premium: float, quantity: int = 65) -> str:
    """Alert triggered on 15:15 IST mandatory square-off."""
    diff = exit_premium - entry_premium
    total_pnl = diff * quantity
    pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
    return f"""
⏰ *15:15 IST MANDATORY INTRADAY SQUARE-OFF* ⏰
━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 *Contract:* `{contract}`
💰 *Entry Price:* ₹{entry_premium:.1f}
🚪 *Exit Price:* ₹{exit_premium:.1f}
{pnl_emoji} *Net P&L:* ₹{total_pnl:+,.2f}
━━━━━━━━━━━━━━━━━━━━━━━━━━
🛡️ *No overnight positions held. Market session closed.*
━━━━━━━━━━━━━━━━━━━━━━━━━━
""".strip()

def format_eod_summary_alert(summary: Dict[str, Any]) -> str:
    """Formats the comprehensive End-Of-Day (EOD) Telegram report."""
    date_str = summary.get("date", "")
    total_trades = summary.get("total_trades", 0)
    net_pnl = summary.get("net_pnl", 0.0)
    gross_pnl = summary.get("gross_pnl", 0.0)
    charges = summary.get("total_charges", 0.0)
    wins = summary.get("wins", 0)
    losses = summary.get("losses", 0)
    win_rate = summary.get("win_rate_pct", 0.0)
    trades = summary.get("trades", [])

    pnl_emoji = "🟢" if net_pnl >= 0 else "🔴"
    pnl_sign = "+" if net_pnl >= 0 else ""

    if total_trades == 0:
        return f"""
📊 *NIFTY AI BOT — END OF DAY REPORT* 📊
📅 *DATE:* {date_str}
━━━━━━━━━━━━━━━━━━━━━━━━━━
💤 *NO TRADES TAKEN TODAY*
• *Market Status:* Rangebound / Chop.
• *AI Safety Filter:* Model confidence filter was not breached, preserving capital.
• *Capital Protected:* Zero loss, zero brokerage.
━━━━━━━━━━━━━━━━━━━━━━━━━━
🛡️ *Discipline maintained. Ready for tomorrow's open.*
""".strip()

    trade_lines = []
    for idx, t in enumerate(trades, 1):
        t_net = t.get("net_pnl", 0.0)
        t_emoji = "🟢" if t_net >= 0 else "🔴"
        t_sign = "+" if t_net >= 0 else ""
        entry_p = t.get("entry_premium", 0.0)
        exit_p = t.get("exit_premium", entry_p)
        entry_t = t.get("entry_time", "")
        exit_t = t.get("exit_time", "")
        reason = t.get("exit_reason", "COMPLETED")
        pts = t.get("points_pnl", 0.0)
        pts_sign = "+" if pts >= 0 else ""

        trade_lines.append(
            f"{idx}. {t_emoji} `{t.get('contract')}`\n"
            f"   • *Time:* {entry_t} ➔ {exit_t}\n"
            f"   • *Levels:* Entry ₹{entry_p:.1f} ➔ Exit ₹{exit_p:.1f} ({pts_sign}{pts:.1f} pts)\n"
            f"   • *Result:* {reason} ({t_sign}₹{t_net:,.2f} Net)"
        )

    trade_details = "\n\n".join(trade_lines)

    return f"""
📊 *NIFTY AI BOT — END OF DAY REPORT* 📊
📅 *DATE:* {date_str}
━━━━━━━━━━━━━━━━━━━━━━━━━━
💰 *PERFORMANCE ACHIEVED TODAY:*
• *Net P&L:* {pnl_emoji} *{pnl_sign}₹{net_pnl:,.2f}*
• *Gross Trading P&L:* ₹{gross_pnl:+,.2f}
• *Brokerage & Taxes:* ₹{charges:,.2f}
• *Total Trades Taken:* {total_trades} ({wins} Wins / {losses} Losses)
• *Win Rate:* {win_rate:.1f}%
━━━━━━━━━━━━━━━━━━━━━━━━━━
📜 *DETAILED TRADE BREAKDOWN:*
{trade_details}
━━━━━━━━━━━━━━━━━━━━━━━━━━
🛡️ *STATUS:* All intraday positions squared off. Zero overnight exposure.
✨ *Market closed. Great execution today!*
""".strip()

def format_exit_alert(contract: str, reason: str, exit_price: float, pnl: float) -> str:
    """Alert triggered upon full position exit."""
    pnl_emoji = "🟢" if pnl >= 0 else "🔴"
    return f"""
🔔 *TRADE CLOSED - EXIT NOTIFICATION* 🔔
━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 *Contract:* `{contract}`
🚪 *Reason:* {reason}
💰 *Exit Price:* ₹{exit_price:.1f}
{pnl_emoji} *Estimated P&L:* ₹{pnl:+,.2f}
━━━━━━━━━━━━━━━━━━━━━━━━━━
""".strip()

def send_telegram_alert(message: str) -> bool:
    """
    Sends message to Telegram via Bot API if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set in .env.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        res = requests.post(url, json=payload, timeout=5)
        return res.status_code == 200
    except Exception as e:
        print(f"[Notifier] Telegram dispatch error: {e}")
        return False

def send_whatsapp_alert(message: str) -> bool:
    """
    Sends message to WhatsApp.
    Supports:
    1. CallMeBot API (Easiest 100% Free personal WhatsApp notification):
       - Send 'I allow callmebot to send me messages' to +34 941 83 07 43 on WhatsApp.
       - Receive your apikey.
       - Configure WHATSAPP_PHONE and WHATSAPP_API_KEY in .env.
    2. Twilio WhatsApp API:
       - Configure TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM, and WHATSAPP_PHONE.
    """
    # 1. CallMeBot Gateway (Free, no business verification needed)
    phone = os.getenv("WHATSAPP_PHONE", "").strip().replace("+", "").replace(" ", "").replace("-", "")
    apikey = os.getenv("WHATSAPP_API_KEY", "").strip()
    
    if phone and apikey:
        try:
            import urllib.parse
            # WhatsApp clean formatting: remove double asterisks if any
            clean_msg = message.replace("**", "*")
            encoded_msg = urllib.parse.quote_plus(clean_msg)
            url = f"https://api.callmebot.com/whatsapp.php?phone={phone}&text={encoded_msg}&apikey={apikey}"
            res = requests.get(url, timeout=10)
            if res.status_code == 200:
                return True
            else:
                print(f"[Notifier] CallMeBot error HTTP {res.status_code}: {res.text}")
        except Exception as e:
            print(f"[Notifier] WhatsApp CallMeBot error: {e}")

    # 2. Twilio WhatsApp API Gateway
    twilio_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    twilio_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    twilio_from = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886").strip()
    twilio_to = os.getenv("WHATSAPP_PHONE", "").strip()
    if twilio_sid and twilio_token and twilio_to:
        try:
            target_to = twilio_to if twilio_to.startswith("whatsapp:") else f"whatsapp:{'+' + twilio_to.lstrip('+')}"
            url = f"https://api.twilio.com/2010-04-01/Accounts/{twilio_sid}/Messages.json"
            clean_msg = message.replace("**", "*")
            res = requests.post(
                url,
                data={
                    "From": twilio_from,
                    "To": target_to,
                    "Body": clean_msg
                },
                auth=(twilio_sid, twilio_token),
                timeout=10
            )
            return res.status_code in (200, 201)
        except Exception as e:
            print(f"[Notifier] Twilio WhatsApp error: {e}")

    return False



