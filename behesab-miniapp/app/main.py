import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from .models import FriendRequest, Friendship, PersonalExpense, Transaction, User
from .telegram_auth import current_user
from .telegram_bot import app_keyboard, send_notification, setup_webhook, bot_api

BASE_DIR = Path(__file__).resolve().parent
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    try:
        await setup_webhook()
    except Exception as exc:
        print("Webhook setup warning:", exc)
    yield

app = FastAPI(title="بحساب API", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

class FriendRequestIn(BaseModel):
    target: str = Field(min_length=1, max_length=80)

class TransactionIn(BaseModel):
    kind: str = Field(pattern="^(debt|settlement)$")
    amount: float = Field(gt=0)
    title: str = Field(min_length=1, max_length=180)
    note: str = Field(default="", max_length=1000)
    direction: str

class PersonalIn(BaseModel):
    amount: float = Field(gt=0)
    title: str = Field(min_length=1, max_length=180)
    note: str = Field(default="", max_length=1000)


def me_dep(
    db: Session = Depends(get_db),
    x_telegram_init_data: str | None = Header(default=None),
    x_dev_telegram_id: str | None = Header(default=None),
):
    return current_user(db, x_telegram_init_data, x_dev_telegram_id)


def user_json(u: User):
    return {"id": u.id, "telegram_id": u.telegram_id, "username": u.username, "first_name": u.first_name, "last_name": u.last_name, "display_name": (u.first_name + " " + u.last_name).strip() or ("@" + u.username if u.username else str(u.telegram_id))}


def friend_pair(a: int, b: int):
    return (a, b) if a < b else (b, a)


def ensure_friend(db: Session, a: int, b: int):
    x, y = friend_pair(a, b)
    fr = db.scalar(select(Friendship).where(Friendship.user_a_id == x, Friendship.user_b_id == y))
    if not fr:
        raise HTTPException(403, "این کاربر هنوز دوست شما نیست")
    return fr


def pair_transactions(db: Session, a: int, b: int):
    return list(db.scalars(select(Transaction).where(or_(
        and_(Transaction.from_user_id == a, Transaction.to_user_id == b),
        and_(Transaction.from_user_id == b, Transaction.to_user_id == a),
    )).order_by(Transaction.created_at.desc())))


def balance_for(db: Session, me_id: int, friend_id: int) -> float:
    balance = 0.0
    for t in pair_transactions(db, me_id, friend_id):
        if t.kind == "debt":
            balance += t.amount if t.to_user_id == me_id else -t.amount
        else:
            balance += t.amount if t.from_user_id == me_id else -t.amount
    return round(balance, 2)


def tx_json(t: Transaction, me_id: int):
    return {
        "id": t.id,
        "kind": t.kind,
        "amount": t.amount,
        "title": t.title,
        "note": t.note,
        "from_user_id": t.from_user_id,
        "to_user_id": t.to_user_id,
        "created_by_id": t.created_by_id,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
        "direction": (
            "i_owe" if t.kind == "debt" and t.from_user_id == me_id else
            "they_owe" if t.kind == "debt" else
            "i_paid" if t.from_user_id == me_id else "they_paid"
        ),
    }

@app.get("/")
def index():
    return FileResponse(BASE_DIR / "static" / "index.html")

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/api/me")
def get_me(me: User = Depends(me_dep)):
    return user_json(me)

@app.get("/api/friends")
def get_friends(db: Session = Depends(get_db), me: User = Depends(me_dep)):
    rows = db.scalars(select(Friendship).where(or_(Friendship.user_a_id == me.id, Friendship.user_b_id == me.id))).all()
    out = []
    for row in rows:
        fid = row.user_b_id if row.user_a_id == me.id else row.user_a_id
        u = db.get(User, fid)
        out.append({**user_json(u), "balance": balance_for(db, me.id, fid)})
    return out

@app.get("/api/friends/requests")
def get_requests(db: Session = Depends(get_db), me: User = Depends(me_dep)):
    rows = db.scalars(select(FriendRequest).where(FriendRequest.to_user_id == me.id, FriendRequest.status == "pending").order_by(FriendRequest.created_at.desc())).all()
    return [{"id": r.id, "from_user": user_json(db.get(User, r.from_user_id)), "created_at": r.created_at.isoformat()} for r in rows]

@app.post("/api/friends/requests")
async def create_request(data: FriendRequestIn, db: Session = Depends(get_db), me: User = Depends(me_dep)):
    raw = data.target.strip().lstrip("@")
    target = None
    if raw.isdigit():
        target = db.scalar(select(User).where(User.telegram_id == int(raw)))
    else:
        target = db.scalar(select(User).where(User.username == raw))
    if not target:
        raise HTTPException(404, "کاربر باید ابتدا ربات یا اپ بحساب را باز کرده باشد")
    if target.id == me.id:
        raise HTTPException(400, "نمی‌توانید خودتان را اضافه کنید")
    x, y = friend_pair(me.id, target.id)
    if db.scalar(select(Friendship).where(Friendship.user_a_id == x, Friendship.user_b_id == y)):
        raise HTTPException(400, "این کاربر از قبل دوست شماست")
    existing = db.scalar(select(FriendRequest).where(FriendRequest.from_user_id == me.id, FriendRequest.to_user_id == target.id, FriendRequest.status == "pending"))
    if existing:
        raise HTTPException(400, "درخواست قبلاً ارسال شده است")
    req = FriendRequest(from_user_id=me.id, to_user_id=target.id)
    db.add(req); db.commit(); db.refresh(req)
    await send_notification(target.telegram_id, f"👤 {user_json(me)['display_name']} برای شما درخواست دوستی در بحساب فرستاد.")
    return {"ok": True, "id": req.id}

@app.post("/api/friends/requests/{request_id}/{action}")
async def act_request(request_id: int, action: str, db: Session = Depends(get_db), me: User = Depends(me_dep)):
    if action not in {"accept", "reject"}:
        raise HTTPException(400, "عملیات نامعتبر است")
    req = db.get(FriendRequest, request_id)
    if not req or req.to_user_id != me.id or req.status != "pending":
        raise HTTPException(404, "درخواست پیدا نشد")
    req.status = "accepted" if action == "accept" else "rejected"
    sender = db.get(User, req.from_user_id)
    if action == "accept":
        x, y = friend_pair(me.id, sender.id)
        if not db.scalar(select(Friendship).where(Friendship.user_a_id == x, Friendship.user_b_id == y)):
            db.add(Friendship(user_a_id=x, user_b_id=y))
    db.commit()
    await send_notification(sender.telegram_id, f"✅ {user_json(me)['display_name']} درخواست دوستی شما را {'تأیید' if action == 'accept' else 'رد'} کرد.")
    return {"ok": True}

@app.get("/api/friends/{friend_id}/transactions")
def get_transactions(friend_id: int, db: Session = Depends(get_db), me: User = Depends(me_dep)):
    ensure_friend(db, me.id, friend_id)
    friend = db.get(User, friend_id)
    return {"friend": user_json(friend), "balance": balance_for(db, me.id, friend_id), "transactions": [tx_json(t, me.id) for t in pair_transactions(db, me.id, friend_id)]}

@app.post("/api/friends/{friend_id}/transactions")
async def create_transaction(friend_id: int, data: TransactionIn, db: Session = Depends(get_db), me: User = Depends(me_dep)):
    ensure_friend(db, me.id, friend_id)
    friend = db.get(User, friend_id)
    valid = {"debt": {"i_owe", "they_owe"}, "settlement": {"i_paid", "they_paid"}}
    if data.direction not in valid[data.kind]:
        raise HTTPException(400, "جهت تراکنش نامعتبر است")
    if data.direction in {"i_owe", "i_paid"}:
        from_id, to_id = me.id, friend_id
    else:
        from_id, to_id = friend_id, me.id
    t = Transaction(from_user_id=from_id, to_user_id=to_id, created_by_id=me.id, kind=data.kind, amount=round(data.amount, 2), title=data.title.strip(), note=data.note.strip())
    db.add(t); db.commit(); db.refresh(t)
    if data.kind == "debt":
        text = f"💳 مبلغ {data.amount:,.0f} تومان بدهی توسط {user_json(me)['display_name']} برای حساب شما ثبت شد.\n📝 {data.title}"
    else:
        text = f"✅ یک تسویه به مبلغ {data.amount:,.0f} تومان توسط {user_json(me)['display_name']} ثبت شد.\n📝 {data.title}"
    await send_notification(friend.telegram_id, text)
    return {"transaction": tx_json(t, me.id), "balance": balance_for(db, me.id, friend_id)}

@app.put("/api/transactions/{tx_id}")
async def update_transaction(tx_id: int, data: TransactionIn, db: Session = Depends(get_db), me: User = Depends(me_dep)):
    t = db.get(Transaction, tx_id)
    if not t or me.id not in {t.from_user_id, t.to_user_id}:
        raise HTTPException(404, "تراکنش پیدا نشد")
    friend_id = t.to_user_id if t.from_user_id == me.id else t.from_user_id
    valid = {"debt": {"i_owe", "they_owe"}, "settlement": {"i_paid", "they_paid"}}
    if data.direction not in valid[data.kind]: raise HTTPException(400, "جهت نامعتبر")
    if data.direction in {"i_owe", "i_paid"}: t.from_user_id, t.to_user_id = me.id, friend_id
    else: t.from_user_id, t.to_user_id = friend_id, me.id
    t.kind, t.amount, t.title, t.note = data.kind, round(data.amount, 2), data.title.strip(), data.note.strip()
    db.commit(); db.refresh(t)
    friend = db.get(User, friend_id)
    await send_notification(friend.telegram_id, f"✏️ {user_json(me)['display_name']} یک تراکنش {data.amount:,.0f} تومانی را ویرایش کرد.\n📝 {data.title}")
    return {"transaction": tx_json(t, me.id), "balance": balance_for(db, me.id, friend_id)}

@app.delete("/api/transactions/{tx_id}")
async def delete_transaction(tx_id: int, db: Session = Depends(get_db), me: User = Depends(me_dep)):
    t = db.get(Transaction, tx_id)
    if not t or me.id not in {t.from_user_id, t.to_user_id}:
        raise HTTPException(404, "تراکنش پیدا نشد")
    friend_id = t.to_user_id if t.from_user_id == me.id else t.from_user_id
    friend = db.get(User, friend_id)
    amount, title = t.amount, t.title
    db.delete(t); db.commit()
    await send_notification(friend.telegram_id, f"🗑 {user_json(me)['display_name']} تراکنش {amount:,.0f} تومانی «{title}» را حذف کرد.")
    return {"ok": True, "balance": balance_for(db, me.id, friend_id)}

@app.get("/api/personal")
def personal_list(db: Session = Depends(get_db), me: User = Depends(me_dep)):
    rows = db.scalars(select(PersonalExpense).where(PersonalExpense.user_id == me.id).order_by(PersonalExpense.created_at.desc())).all()
    return [{"id": x.id, "amount": x.amount, "title": x.title, "note": x.note, "created_at": x.created_at.isoformat(), "updated_at": x.updated_at.isoformat()} for x in rows]

@app.post("/api/personal")
def personal_create(data: PersonalIn, db: Session = Depends(get_db), me: User = Depends(me_dep)):
    x = PersonalExpense(user_id=me.id, amount=round(data.amount, 2), title=data.title.strip(), note=data.note.strip())
    db.add(x); db.commit(); db.refresh(x)
    return {"id": x.id}

@app.put("/api/personal/{expense_id}")
def personal_update(expense_id: int, data: PersonalIn, db: Session = Depends(get_db), me: User = Depends(me_dep)):
    x = db.get(PersonalExpense, expense_id)
    if not x or x.user_id != me.id: raise HTTPException(404, "مورد پیدا نشد")
    x.amount, x.title, x.note = round(data.amount, 2), data.title.strip(), data.note.strip(); db.commit()
    return {"ok": True}

@app.delete("/api/personal/{expense_id}")
def personal_delete(expense_id: int, db: Session = Depends(get_db), me: User = Depends(me_dep)):
    x = db.get(PersonalExpense, expense_id)
    if not x or x.user_id != me.id: raise HTTPException(404, "مورد پیدا نشد")
    db.delete(x); db.commit(); return {"ok": True}

@app.post("/api/telegram/webhook")
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    if WEBHOOK_SECRET and x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(403, "Forbidden")
    update = await request.json()
    msg = update.get("message") or {}
    chat = msg.get("chat") or {}
    text = msg.get("text", "")
    if chat.get("id") and text.startswith("/start"):
        await bot_api("sendMessage", {
            "chat_id": chat["id"],
            "text": "سلام 👋\nبه «بحساب» خوش اومدی؛ حساب‌وکتاب دونفره، ساده و شفاف.",
            "reply_markup": app_keyboard(),
        })
    return {"ok": True}
