import asyncio
import html
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import TelegramIdentity, telegram_identity
from .bot import money, send_message, send_start, setup_webhook, webhook_secret
from .database import Base, SessionLocal, engine, get_db
from .models import Friendship, PersonalExpense, Transaction, User, utcnow
from .schemas import ExpenseCreate, FriendRequestCreate, FriendRequestDecision, TransactionCreate, TransactionUpdate


STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await setup_webhook()
    yield
    await engine.dispose()


app = FastAPI(title="بحساب", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def pair(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def user_name(user: User) -> str:
    return " ".join(filter(None, [user.first_name, user.last_name])).strip()


async def current_user(
    identity: TelegramIdentity = Depends(telegram_identity),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await db.get(User, identity.id)
    if user is None:
        user = User(
            id=identity.id,
            first_name=identity.first_name,
            last_name=identity.last_name,
            username=identity.username.lower() if identity.username else None,
            photo_url=identity.photo_url,
        )
        db.add(user)
    else:
        user.first_name = identity.first_name
        user.last_name = identity.last_name
        user.username = identity.username.lower() if identity.username else None
        user.photo_url = identity.photo_url
    await db.commit()
    await db.refresh(user)
    return user


async def friendship_or_404(db: AsyncSession, me: int, friend_id: int) -> Friendship:
    low, high = pair(me, friend_id)
    relation = await db.scalar(select(Friendship).where(
        Friendship.user_low_id == low,
        Friendship.user_high_id == high,
        Friendship.status == "accepted",
    ))
    if not relation:
        raise HTTPException(404, "این کاربر در فهرست دوستان شما نیست.")
    return relation


async def balance_between(db: AsyncSession, me: int, friend_id: int) -> int:
    low, high = pair(me, friend_id)
    rows = (await db.scalars(select(Transaction).where(
        Transaction.user_low_id == low,
        Transaction.user_high_id == high,
    ))).all()
    total = 0
    for item in rows:
        amount = int(item.amount)
        if item.kind == "debt":
            total += amount if item.to_user_id == me else -amount
        else:
            total += amount if item.from_user_id == me else -amount
    return total


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "name": user_name(user),
        "first_name": user.first_name,
        "username": user.username,
        "photo_url": user.photo_url,
    }


def serialize_transaction(item: Transaction, names: dict[int, str], me: int) -> dict:
    if item.kind == "debt":
        direction_text = f"{names[item.from_user_id]} به {names[item.to_user_id]} بدهکار شد"
    elif item.kind == "payment":
        direction_text = f"{names[item.from_user_id]} به {names[item.to_user_id]} پرداخت کرد"
    else:
        direction_text = f"{names[item.from_user_id]} حساب را تسویه کرد"
    return {
        "id": item.id,
        "kind": item.kind,
        "amount": int(item.amount),
        "description": item.description,
        "happened_on": item.happened_on.isoformat(),
        "creator_id": item.creator_id,
        "creator_name": names[item.creator_id],
        "from_user_id": item.from_user_id,
        "to_user_id": item.to_user_id,
        "direction_text": direction_text,
        "is_edited": item.is_edited,
        "can_edit": item.creator_id == me,
    }


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    return {"ok": True, "service": "behesab"}


@app.get("/api/me")
async def get_me(me: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    pending = await db.scalar(select(func.count()).select_from(Friendship).where(
        Friendship.recipient_id == me.id, Friendship.status == "pending"
    ))
    friends = await db.scalar(select(func.count()).select_from(Friendship).where(
        or_(Friendship.user_low_id == me.id, Friendship.user_high_id == me.id),
        Friendship.status == "accepted",
    ))
    expenses = await db.scalar(select(func.coalesce(func.sum(PersonalExpense.amount), 0)).where(
        PersonalExpense.user_id == me.id
    ))
    today = datetime.now(ZoneInfo("Asia/Tehran")).date()
    return {
        **serialize_user(me),
        "pending_requests": int(pending or 0),
        "friends_count": int(friends or 0),
        "expenses_total": int(expenses or 0),
        "today": today.isoformat(),
    }


@app.get("/api/friends")
async def list_friends(me: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    relations = (await db.scalars(select(Friendship).where(
        or_(Friendship.user_low_id == me.id, Friendship.user_high_id == me.id),
        Friendship.status == "accepted",
    ).order_by(Friendship.responded_at.desc()))).all()
    result = []
    for relation in relations:
        friend_id = relation.user_high_id if relation.user_low_id == me.id else relation.user_low_id
        friend = await db.get(User, friend_id)
        if friend:
            result.append({**serialize_user(friend), "balance": await balance_between(db, me.id, friend_id)})
    return result


@app.get("/api/friend-requests")
async def list_requests(me: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    requests = (await db.scalars(select(Friendship).where(
        Friendship.recipient_id == me.id,
        Friendship.status == "pending",
    ).order_by(Friendship.created_at.desc()))).all()
    result = []
    for item in requests:
        sender = await db.get(User, item.requester_id)
        if sender:
            result.append({"id": item.id, "sender": serialize_user(sender), "created_at": item.created_at.isoformat()})
    return result


@app.post("/api/friend-requests", status_code=201)
async def create_request(payload: FriendRequestCreate, me: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    target = await db.scalar(select(User).where(func.lower(User.username) == payload.username))
    if not target:
        raise HTTPException(404, "این نام کاربری هنوز وارد ربات بحساب نشده است.")
    if target.id == me.id:
        raise HTTPException(400, "نمی‌توانید خودتان را به‌عنوان دوست اضافه کنید.")
    low, high = pair(me.id, target.id)
    existing = await db.scalar(select(Friendship).where(
        Friendship.user_low_id == low, Friendship.user_high_id == high
    ))
    if existing and existing.status == "accepted":
        raise HTTPException(409, "این کاربر از قبل دوست شماست.")
    if existing and existing.status == "pending":
        raise HTTPException(409, "یک درخواست دوستی در انتظار پاسخ است.")
    if existing:
        existing.requester_id = me.id
        existing.recipient_id = target.id
        existing.status = "pending"
        existing.created_at = utcnow()
        existing.responded_at = None
        request_item = existing
    else:
        request_item = Friendship(
            user_low_id=low, user_high_id=high,
            requester_id=me.id, recipient_id=target.id, status="pending",
        )
        db.add(request_item)
    await db.commit()
    await send_message(target.id, f"👤 {html.escape(user_name(me))} برای شما درخواست دوستی ارسال کرده است.")
    return {"message": "درخواست دوستی ارسال شد."}


@app.post("/api/friend-requests/{request_id}/respond")
async def respond_request(request_id: int, payload: FriendRequestDecision, me: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    item = await db.get(Friendship, request_id)
    if not item or item.recipient_id != me.id or item.status != "pending":
        raise HTTPException(404, "درخواست دوستی پیدا نشد.")
    item.status = "accepted" if payload.accept else "rejected"
    item.responded_at = utcnow()
    requester = await db.get(User, item.requester_id)
    await db.commit()
    if payload.accept and requester:
        await send_message(requester.id, f"✅ درخواست دوستی شما توسط {html.escape(user_name(me))} تأیید شد.")
    return {"message": "درخواست تأیید شد." if payload.accept else "درخواست رد شد."}


@app.get("/api/friends/{friend_id}/transactions")
async def list_transactions(friend_id: int, me: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await friendship_or_404(db, me.id, friend_id)
    friend = await db.get(User, friend_id)
    low, high = pair(me.id, friend_id)
    items = (await db.scalars(select(Transaction).where(
        Transaction.user_low_id == low, Transaction.user_high_id == high
    ).order_by(Transaction.happened_on.desc(), Transaction.created_at.desc()))).all()
    names = {me.id: user_name(me), friend_id: user_name(friend)}
    return {
        "friend": serialize_user(friend),
        "balance": await balance_between(db, me.id, friend_id),
        "transactions": [serialize_transaction(item, names, me.id) for item in items],
    }


@app.post("/api/friends/{friend_id}/transactions", status_code=201)
async def create_transaction(friend_id: int, payload: TransactionCreate, me: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    await friendship_or_404(db, me.id, friend_id)
    friend = await db.get(User, friend_id)
    low, high = pair(me.id, friend_id)
    amount = payload.amount
    if payload.kind == "settlement":
        current = await balance_between(db, me.id, friend_id)
        if current == 0:
            raise HTTPException(400, "حساب شما از قبل تسویه است.")
        amount = abs(current)
        from_id, to_id = (friend_id, me.id) if current > 0 else (me.id, friend_id)
    else:
        if amount is None:
            raise HTTPException(422, "مبلغ را وارد کنید.")
        from_id, to_id = (me.id, friend_id) if payload.direction == "me_to_friend" else (friend_id, me.id)
    item = Transaction(
        user_low_id=low, user_high_id=high, creator_id=me.id,
        from_user_id=from_id, to_user_id=to_id, kind=payload.kind,
        amount=amount, description=payload.description.strip(), happened_on=payload.happened_on,
    )
    db.add(item)
    await db.commit()
    if payload.kind == "debt":
        note = f"💳 {html.escape(user_name(me))} مبلغ {money(amount)} تومان برای شما ثبت کرد."
        if payload.description:
            note += f"\n📝 بابت: {html.escape(payload.description)}"
    elif payload.kind == "payment":
        note = f"💵 {html.escape(user_name(me))} مبلغ {money(amount)} تومان پرداخت برای شما ثبت کرد."
    else:
        note = f"✅ حساب شما و {html.escape(user_name(me))} تسویه شد."
    await send_message(friend.id, note)
    return {"message": "تراکنش ثبت شد.", "id": item.id}


@app.put("/api/transactions/{transaction_id}")
async def update_transaction(transaction_id: int, payload: TransactionUpdate, me: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    item = await db.get(Transaction, transaction_id)
    if not item or item.creator_id != me.id:
        raise HTTPException(404, "تراکنش پیدا نشد یا اجازه ویرایش آن را ندارید.")
    friend_id = item.user_high_id if item.user_low_id == me.id else item.user_low_id
    friend = await db.get(User, friend_id)
    item.amount = payload.amount
    item.description = payload.description.strip()
    item.happened_on = payload.happened_on
    item.is_edited = True
    await db.commit()
    await send_message(friend.id, f"✏️ {html.escape(user_name(me))} یک تراکنش مالی بین شما را ویرایش کرد.")
    return {"message": "تراکنش ویرایش شد."}


@app.delete("/api/transactions/{transaction_id}")
async def delete_transaction(transaction_id: int, me: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    item = await db.get(Transaction, transaction_id)
    if not item or item.creator_id != me.id:
        raise HTTPException(404, "تراکنش پیدا نشد یا اجازه حذف آن را ندارید.")
    friend_id = item.user_high_id if item.user_low_id == me.id else item.user_low_id
    friend = await db.get(User, friend_id)
    await db.delete(item)
    await db.commit()
    await send_message(friend.id, f"🗑 {html.escape(user_name(me))} یک تراکنش مالی بین شما را حذف کرد.")
    return {"message": "تراکنش حذف شد و مانده حساب دوباره محاسبه شد."}


@app.get("/api/expenses")
async def list_expenses(me: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    items = (await db.scalars(select(PersonalExpense).where(
        PersonalExpense.user_id == me.id
    ).order_by(PersonalExpense.happened_on.desc(), PersonalExpense.created_at.desc()))).all()
    return [{
        "id": item.id, "amount": int(item.amount), "description": item.description,
        "happened_on": item.happened_on.isoformat(), "is_edited": item.is_edited,
    } for item in items]


@app.post("/api/expenses", status_code=201)
async def create_expense(payload: ExpenseCreate, me: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    item = PersonalExpense(user_id=me.id, **payload.model_dump())
    db.add(item)
    await db.commit()
    return {"message": "هزینه شخصی ثبت شد.", "id": item.id}


@app.put("/api/expenses/{expense_id}")
async def update_expense(expense_id: int, payload: ExpenseCreate, me: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    item = await db.get(PersonalExpense, expense_id)
    if not item or item.user_id != me.id:
        raise HTTPException(404, "هزینه پیدا نشد.")
    item.amount = payload.amount
    item.description = payload.description
    item.happened_on = payload.happened_on
    item.is_edited = True
    await db.commit()
    return {"message": "هزینه ویرایش شد."}


@app.delete("/api/expenses/{expense_id}")
async def delete_expense(expense_id: int, me: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    item = await db.get(PersonalExpense, expense_id)
    if not item or item.user_id != me.id:
        raise HTTPException(404, "هزینه پیدا نشد.")
    await db.delete(item)
    await db.commit()
    return {"message": "هزینه حذف شد."}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: str | None = Header(None)):
    configured_secret = webhook_secret()
    if configured_secret and x_telegram_bot_api_secret_token != configured_secret:
        raise HTTPException(403, "Webhook secret is invalid")
    update = await request.json()
    message = update.get("message") or {}
    text = message.get("text", "")
    sender = message.get("from") or {}
    chat = message.get("chat") or {}
    if text.split()[0:1] == ["/start"] and sender.get("id"):
        identity = TelegramIdentity(
            id=int(sender["id"]), first_name=sender.get("first_name") or "کاربر بحساب",
            last_name=sender.get("last_name"), username=sender.get("username"),
        )
        async with SessionLocal() as db:
            user = await db.get(User, identity.id)
            if not user:
                db.add(User(
                    id=identity.id, first_name=identity.first_name, last_name=identity.last_name,
                    username=identity.username.lower() if identity.username else None,
                ))
            else:
                user.first_name, user.last_name = identity.first_name, identity.last_name
                user.username = identity.username.lower() if identity.username else None
            await db.commit()
        await send_start(int(chat.get("id", identity.id)), identity.first_name)
    return {"ok": True}
