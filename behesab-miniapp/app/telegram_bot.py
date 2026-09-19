import os
import httpx

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")


def app_keyboard():
    return {
        "inline_keyboard": [[{
            "text": "🚀 ورود به بحساب",
            "web_app": {"url": PUBLIC_URL or "https://example.com"}
        }]]
    }


async def bot_api(method: str, payload: dict):
    if not BOT_TOKEN:
        return None
    async with httpx.AsyncClient(timeout=12) as client:
        r = await client.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", json=payload)
        r.raise_for_status()
        return r.json()


async def send_notification(chat_id: int, text: str):
    if not BOT_TOKEN or not PUBLIC_URL:
        return
    await bot_api("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": app_keyboard(),
    })


async def setup_webhook():
    if not BOT_TOKEN or not PUBLIC_URL:
        return
    payload = {"url": f"{PUBLIC_URL}/api/telegram/webhook"}
    if WEBHOOK_SECRET:
        payload["secret_token"] = WEBHOOK_SECRET
    await bot_api("setWebhook", payload)
