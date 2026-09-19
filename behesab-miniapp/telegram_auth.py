import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qsl
from fastapi import Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import User

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"


def validate_init_data(init_data: str, max_age_seconds: int = 86400) -> dict:
    if not BOT_TOKEN:
        raise HTTPException(500, "BOT_TOKEN تنظیم نشده است")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise HTTPException(401, "Telegram initData نامعتبر است")
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise HTTPException(401, "امضای Telegram معتبر نیست")
    auth_date = int(pairs.get("auth_date", "0"))
    if auth_date and time.time() - auth_date > max_age_seconds:
        raise HTTPException(401, "Telegram initData منقضی شده است")
    try:
        return json.loads(pairs["user"])
    except Exception as exc:
        raise HTTPException(401, "اطلاعات کاربر Telegram موجود نیست") from exc


def get_or_create_user(db: Session, tg: dict) -> User:
    telegram_id = int(tg["id"])
    user = db.scalar(select(User).where(User.telegram_id == telegram_id))
    if not user:
        user = User(
            telegram_id=telegram_id,
            username=tg.get("username"),
            first_name=tg.get("first_name", ""),
            last_name=tg.get("last_name", ""),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.username = tg.get("username")
        user.first_name = tg.get("first_name", user.first_name)
        user.last_name = tg.get("last_name", user.last_name)
        db.commit()
    return user


def current_user(
    db: Session,
    x_telegram_init_data: str | None,
    x_dev_telegram_id: str | None,
) -> User:
    if x_telegram_init_data:
        return get_or_create_user(db, validate_init_data(x_telegram_init_data))
    if DEV_MODE and x_dev_telegram_id:
        tid = int(x_dev_telegram_id)
        user = db.scalar(select(User).where(User.telegram_id == tid))
        if not user:
            user = User(telegram_id=tid, first_name=f"کاربر {tid}", username=f"user{tid}")
            db.add(user)
            db.commit()
            db.refresh(user)
        return user
    raise HTTPException(401, "اپ را از داخل Telegram باز کنید")
