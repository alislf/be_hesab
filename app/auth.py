import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from fastapi import Header, HTTPException


@dataclass
class TelegramIdentity:
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None


def validate_init_data(raw: str) -> TelegramIdentity:
    token = os.getenv("BOT_TOKEN", "")
    if not token:
        raise HTTPException(503, "توکن ربات تنظیم نشده است.")

    values = dict(parse_qsl(raw, keep_blank_values=True))
    received_hash = values.pop("hash", None)
    if not received_hash:
        raise HTTPException(401, "اطلاعات ورود تلگرام کامل نیست.")

    check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(received_hash, expected):
        raise HTTPException(401, "امضای تلگرام معتبر نیست.")

    auth_date = int(values.get("auth_date", "0"))
    if not auth_date or abs(time.time() - auth_date) > 86400:
        raise HTTPException(401, "اطلاعات ورود تلگرام منقضی شده است.")

    try:
        user = json.loads(values["user"])
        return TelegramIdentity(
            id=int(user["id"]),
            first_name=user.get("first_name") or "کاربر باجت",
            last_name=user.get("last_name"),
            username=user.get("username"),
            photo_url=user.get("photo_url"),
        )
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(401, "اطلاعات کاربر تلگرام معتبر نیست.") from exc


async def telegram_identity(
    x_telegram_init_data: str | None = Header(None),
    x_demo_user: str | None = Header(None),
) -> TelegramIdentity:
    if os.getenv("DEMO_MODE", "false").lower() == "true" and x_demo_user:
        demo_id = int(x_demo_user)
        people = {
            900001: ("علی", "soltanifard"),
            900002: ("رضا", "reza_demo"),
            900003: ("سارا", "sara_demo"),
        }
        name, username = people.get(demo_id, ("کاربر آزمایشی", f"demo_{demo_id}"))
        return TelegramIdentity(demo_id, name, username=username)
    if not x_telegram_init_data:
        raise HTTPException(401, "اپ را از داخل تلگرام باز کنید.")
    return validate_init_data(x_telegram_init_data)
