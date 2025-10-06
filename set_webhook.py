import os
import requests
from dotenv import load_dotenv

load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

def set_webhook():
    if not TELEGRAM_BOT_TOKEN or not WEBHOOK_URL:
        print("❌ BOT_TOKEN hoặc WEBHOOK_URL chưa được thiết lập.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
    payload = {"url": WEBHOOK_URL}
    try:
        response = requests.post(url, data=payload)
        result = response.json()
        if result.get("ok"):
            print("✅ Webhook đã được thiết lập thành công!")
        else:
            print(f"❌ Lỗi khi thiết lập webhook: {result}")
    except Exception as e:
        print(f"⚠️ Lỗi kết nối: {e}")
if __name__ == "__main__":
    set_webhook()
