import html
import os
import re

import httpx


def webhook_secret() -> str:
    raw = os.getenv("WEBHOOK_SECRET", "").strip()
    return re.sub(r"[^A-Za-z0-9_-]", "", raw)[:256]


def app_button() -> dict:
    return {
        "inline_keyboard": [[{
            "text": "🚀 ورود به باجت",
            "web_app": {"url": os.getenv("APP_URL", "https://example.com")},
        }]]
    }


async def telegram_call(method: str, payload: dict) -> bool:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        return False
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.post(f"https://api.telegram.org/bot{token}/{method}", json=payload)
            data = response.json()
            succeeded = response.is_success and data.get("ok", False)
            if not succeeded:
                description = data.get("description", "Unknown Telegram API error")
                print(f"Telegram API {method} failed: HTTP {response.status_code} - {description}", flush=True)
            return succeeded
    except (httpx.HTTPError, ValueError) as exc:
        print(f"Telegram API {method} request error: {type(exc).__name__}", flush=True)
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
        f"سلام {name} 👋\nبه <b>باجت</b> خوش آمدی. حساب‌های دونفره‌ات را ساده و دقیق مدیریت کن.",
    )


async def setup_webhook() -> bool:
    token = os.getenv("BOT_TOKEN", "").strip()
    app_url = os.getenv("APP_URL", "").strip().rstrip("/")
    secret = webhook_secret()
    if not token or not app_url or "your-service" in app_url:
        print("Telegram webhook skipped: BOT_TOKEN or APP_URL is missing.", flush=True)
        return False
    payload = {
        "url": f"{app_url}/telegram/webhook",
        "allowed_updates": ["message"],
    }
    if secret:
        payload["secret_token"] = secret
    configured = await telegram_call("setWebhook", payload)
    print(f"Telegram webhook configured: {configured}", flush=True)
    return configured


def money(value: int | float) -> str:
    return f"{int(value):,}".translate(str.maketrans("0123456789,", "۰۱۲۳۴۵۶۷۸۹٬"))
