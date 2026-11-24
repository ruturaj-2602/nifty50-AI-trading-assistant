"""
Diagnostic script to test Telegram Trade Alert Dispatch for all lifecycle events:
- Trade Entry Alert
- Target 1 Hit Alert (Book 50% & Trail SL to Cost)
- Target 2 Hit Alert (Max Profit Achievement)
- Stop Loss Hit Alert (Capital Protection Exit)
"""
import os
import sys
import time
import requests
from config import load_dotenv, MARKET
from live.notifier import (
    send_telegram_alert,
    format_target1_alert,
    format_target2_alert,
    format_stoploss_alert
)

load_dotenv()

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    print("=== Telegram Trade Alert Diagnostic Test ===")
    
    if not token or not chat_id:
        print("\n[!] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing in .env")
        return

    # Verify bot token with getMe
    try:
        me_res = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5).json()
        if not me_res.get("ok"):
            print(f"\n❌ Invalid Bot Token: {me_res.get('description', 'Unknown error')}")
            return
        bot_username = me_res.get("result", {}).get("username", "UnknownBot")
        print(f"✓ Bot verified: @{bot_username}")
    except Exception as e:
        print(f"❌ Connection error verifying bot token: {e}")
        return

    test_type = sys.argv[1].lower() if len(sys.argv) > 1 else "target_sl"

    contract = "NIFTY 25650 CE"
    entry_price = 146.2
    target_1 = 188.6
    target_2 = 207.3
    stop_loss = 119.0
    lots = 1
    qty = MARKET.lot_size

    if test_type in ("target1", "target_sl", "all"):
        print("\n[1/3] Dispatching Target 1 Hit alert...")
        msg = format_target1_alert(contract, entry_price, target_1, lots, qty)
        if send_telegram_alert(msg):
            print("  ✓ Target 1 Hit alert delivered to Telegram!")
        time.sleep(1)

    if test_type in ("target2", "all"):
        print("\n[2/3] Dispatching Target 2 Hit alert...")
        msg = format_target2_alert(contract, entry_price, target_2, lots, qty)
        if send_telegram_alert(msg):
            print("  ✓ Target 2 Hit alert delivered to Telegram!")
        time.sleep(1)

    if test_type in ("stoploss", "target_sl", "all"):
        print("\n[3/3] Dispatching Stop Loss Hit alert...")
        msg = format_stoploss_alert(contract, entry_price, stop_loss, lots, qty, was_trailed=False)
        if send_telegram_alert(msg):
            print("  ✓ Stop Loss Hit alert delivered to Telegram!")

    print("\n✓ Diagnostic completed. Check your Telegram chat to see the formatted alerts!")

if __name__ == "__main__":
    main()
