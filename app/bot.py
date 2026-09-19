import html
import os

import httpx


def app_button() -> dict:
    return {
        "inline_keyboard": [[{
            "text": "🚀 ورود به بحساب",
            "web_app": {"url": os.getenv("APP_URL", "https://example.com")},
        }]]
    }


async def telegram_call(method: str, payload: dict) -> bool:
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        return False
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.post(f"https://api.telegram.org/bot{token}/{method}", json=payload)
            return response.is_success and response.json().get("ok", False)
    except (httpx.HTTPError, ValueError):
        return False


async def send_message(chat_id: int, text: str) -> bool:
    return await telegram_call("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": app_button(),
    })


async def send_start(chat_id: int, first_name: str) -> bool:
    name = html.escape(first_name)
    return await send_message(
        chat_id,
        f"سلام {name} 👋\nبه <b>بحساب</b> خوش آمدی. حساب‌های دونفره‌ات را ساده و دقیق مدیریت کن.",
    )


async def setup_webhook() -> None:
    token = os.getenv("BOT_TOKEN", "")
    app_url = os.getenv("APP_URL", "").rstrip("/")
    secret = os.getenv("WEBHOOK_SECRET", "")
    if not token or not app_url or "your-service" in app_url:
        return
    payload = {
        "url": f"{app_url}/telegram/webhook",
        "allowed_updates": ["message"],
    }
    if secret:
        payload["secret_token"] = secret
    await telegram_call("setWebhook", payload)


def money(value: int | float) -> str:
    return f"{int(value):,}".translate(str.maketrans("0123456789,", "۰۱۲۳۴۵۶۷۸۹٬"))
