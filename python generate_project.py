import os

FILES = {
    "sms_bot_pro/.env": """
BOT_TOKEN=8753784982:AAFne0Gus1tJJlmF9vR4EOlCF0-BlBB7wv0
ADMIN_IDS=1967494059
ADMIN_USERNAME=@RobiEntertainment
DEV_USERNAME=RobiEntertainment
SMS_API_URL=https://api.paglahost.shop/Custom_SMS/api.php
SMS_API_KEY=Shuvo55356
LOG_CHANNEL=-1001234567890
DATABASE_URL=sqlite+aiosqlite:///./data/bot.db
""".strip(),

    "sms_bot_pro/.gitignore": """
.env
__pycache__/
*.pyc
*.db
*.sqlite3
data/
bot.log
.DS_Store
""".strip(),

    "sms_bot_pro/README.md": """
# 📱 Professional SMS Telegram Bot

A modular, enterprise-grade Telegram bot for sending SMS via API, user management, redeem codes, and admin panel.

## Features
- 🔐 Secure Login System (Username/Password)
- 💰 Credit-based SMS Sending
- 🎁 Redeem Code System
- 👑 Full Admin Panel (Add/Remove Credits, Ban/Unban, Broadcast)
- 🛡️ Rate Limiting & Spam Protection
- 📝 Auto Logging to Channel & File
- 🗄️ SQLAlchemy ORM (SQLite/PostgreSQL ready)

## Quick Start
1. Install dependencies: `pip install -r requirements.txt`
2. Run: `python -m app.main`

## Deployment
- Use Docker or systemd for production.
- Recommended: Python 3.10+ VPS.
""".strip(),

    "sms_bot_pro/requirements.txt": """
aiogram==3.4.1
sqlalchemy==2.0.25
aiosqlite==0.19.0
python-dotenv==1.0.0
aiohttp==3.9.1
""".strip(),

    "sms_bot_pro/app/__init__.py": "",
    "sms_bot_pro/app/config.py": """
import os
from dotenv import load_dotenv
from typing import List

load_dotenv()

class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_IDS: List[int] = [int(id) for id in os.getenv("ADMIN_IDS", "").split(",") if id.isdigit()]
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "@Admin")
    DEV_USERNAME: str = os.getenv("DEV_USERNAME", "Dev")
    SMS_API_URL: str = os.getenv("SMS_API_URL", "")
    SMS_API_KEY: str = os.getenv("SMS_API_KEY", "")
    LOG_CHANNEL: int = int(os.getenv("LOG_CHANNEL", "-1001234567890"))
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/bot.db")
    RATE_LIMIT_WINDOW: int = 2
    RATE_LIMIT_MAX: int = 3
    SMS_RETRY_COUNT: int = 2
""".strip(),

    "sms_bot_pro/app/database.py": """
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from app.config import Config

engine = create_async_engine(Config.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)
Base = declarative_base()

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
""".strip(),

    "sms_bot_pro/app/models.py": """
from sqlalchemy import Column, Integer, String, DateTime, BigInteger, Boolean
from datetime import datetime
from app.database import Base

class User(Base):
    __tablename__ = "users"
    user_id = Column(BigInteger, primary_key=True)
    login_username = Column(String, nullable=True)
    balance = Column(Integer, default=0)
    join_date = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="active")  # active, banned
    is_admin = Column(Boolean, default=False)

class Account(Base):
    __tablename__ = "accounts"
    username = Column(String, primary_key=True)
    password = Column(String, nullable=False)
    telegram_id = Column(BigInteger, nullable=True)

class RedeemCode(Base):
    __tablename__ = "redeem_codes"
    code = Column(String, primary_key=True)
    amount = Column(Integer, nullable=False)
    usages = Column(Integer, nullable=False)

class RedeemHistory(Base):
    __tablename__ = "redeem_history"
    user_id = Column(BigInteger, primary_key=True)
    code = Column(String, primary_key=True)
    used_at = Column(DateTime, default=datetime.utcnow)
""".strip(),

    "sms_bot_pro/app/main.py": """
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from app.config import Config
from app.database import engine, Base
from app.handlers import auth, user, admin, sms
from app.middlewares.rate_limit import RateLimitMiddleware
from app.middlewares.logging import LoggingMiddleware
from app.utils.logger import setup_logger

async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logging.info("✅ Database tables ready.")

async def main():
    setup_logger()
    bot = Bot(token=Config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.startup.register(on_startup)

    dp.message.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())
    dp.message.middleware(LoggingMiddleware())

    dp.include_router(auth.router)
    dp.include_router(user.router)
    dp.include_router(admin.router)
    dp.include_router(sms.router)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
""".strip(),

    "sms_bot_pro/app/handlers/__init__.py": "",
    "sms_bot_pro/app/handlers/auth.py": """
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from app.database import AsyncSessionLocal
from app.models import User, Account
from app.utils.keyboards import user_keyboard, admin_keyboard
from app.config import Config

router = Router()

class AuthStates(StatesGroup):
    wait_username = State()
    wait_password = State()

@router.message(Command("start"))
async def start_cmd(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    if user_id in Config.ADMIN_IDS:
        await message.answer("👑 **Admin Panel**", reply_markup=admin_keyboard())
        return
    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        if user:
            if user.status == "banned":
                await message.answer(f"⛔ You are banned. Contact Admin: {Config.ADMIN_USERNAME}", reply_markup=ReplyKeyboardRemove())
                return
            await message.answer(f"👋 Welcome back {message.from_user.first_name}!", reply_markup=user_keyboard())
            return
    await message.answer("🔒 **Login Required**\\n\\nPlease enter your **Username**:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(AuthStates.wait_username)

@router.message(AuthStates.wait_username)
async def auth_username(message: Message, state: FSMContext):
    await state.update_data(username=message.text.strip())
    await message.answer("🔑 Enter **Password**:")
    await state.set_state(AuthStates.wait_password)

@router.message(AuthStates.wait_password)
async def auth_password(message: Message, state: FSMContext):
    data = await state.get_data()
    username = data.get('username')
    password = message.text.strip()
    user_id = message.from_user.id
    async with AsyncSessionLocal() as db:
        account = await db.get(Account, username)
        if not account or account.password != password:
            await message.answer(f"❌ **Wrong Username or Password!**\\nContact Admin: {Config.ADMIN_USERNAME}")
            await state.clear()
            return
        if account.telegram_id and account.telegram_id != user_id:
            await message.answer(f"❌ Account already linked to another device.\\nContact Admin: {Config.ADMIN_USERNAME}")
            await state.clear()
            return
        account.telegram_id = user_id
        user = await db.get(User, user_id)
        if not user:
            user = User(user_id=user_id, login_username=username)
            db.add(user)
        else:
            user.login_username = username
        await db.commit()
        await message.answer("✅ **Login Successful!**", reply_markup=user_keyboard())
    await state.clear()
""".strip(),

    "sms_bot_pro/app/handlers/user.py": """
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func
from app.database import AsyncSessionLocal
from app.models import User, RedeemCode, RedeemHistory
from app.config import Config

router = Router()

class UserStates(StatesGroup):
    waiting_redeem = State()

@router.message(F.text == "👤 My Profile")
async def profile(message: Message, state: FSMContext):
    await state.clear()
    async with AsyncSessionLocal() as db:
        user = await db.get(User, message.from_user.id)
        if not user:
            await message.answer("Please /start again.")
            return
        await message.answer(
            f"👤 **MY PROFILE**\\n\\n"
            f"🆔 TG ID: `{message.from_user.id}`\\n"
            f"👤 Username: {user.login_username or 'N/A'}\\n"
            f"💰 Credits: {user.balance}\\n"
            f"🚦 Status: {user.status.capitalize()}\\n\\n"
            f"👨‍💻 Dev: {Config.DEV_USERNAME}",
            parse_mode="Markdown"
        )

@router.message(F.text == "🎁 Redeem Code")
async def ask_redeem(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🎟 Enter your Promo Code:")
    await state.set_state(UserStates.waiting_redeem)

@router.message(UserStates.waiting_redeem)
async def process_redeem(message: Message, state: FSMContext):
    code = message.text.strip()
    user_id = message.from_user.id
    async with AsyncSessionLocal() as db:
        used = await db.execute(select(RedeemHistory).where(RedeemHistory.user_id == user_id, RedeemHistory.code == code))
        if used.scalar():
            await message.answer("❌ You already used this code.")
            await state.clear()
            return
        redeem = await db.get(RedeemCode, code)
        if not redeem or redeem.usages <= 0:
            await message.answer("❌ Invalid or Expired Code.")
            await state.clear()
            return
        user = await db.get(User, user_id)
        if not user:
            await message.answer("Please /start first.")
            await state.clear()
            return
        user.balance += redeem.amount
        redeem.usages -= 1
        db.add(RedeemHistory(user_id=user_id, code=code))
        await db.commit()
        await message.answer(f"🎉 **Redeemed!** +{redeem.amount} Credits.")
    await state.clear()

@router.message(F.text == "👥 Referral")
async def referral(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(f"👥 **Referral System**\\n\\nCurrently disabled. Contact Admin: {Config.ADMIN_USERNAME}")

@router.message(F.text == "☎️ Support")
async def support(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(f"☎️ **Support**\\n\\nContact Admin: {Config.ADMIN_USERNAME}")
""".strip(),

    "sms_bot_pro/app/handlers/sms.py": """
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from app.database import AsyncSessionLocal
from app.models import User
from app.services.sms_api import send_sms
from app.utils.helpers import format_phone_number
from app.config import Config

router = Router()

class SMSStates(StatesGroup):
    waiting_number = State()
    waiting_message = State()

@router.message(F.text == "🚀 Send SMS")
async def start_sms(message: Message, state: FSMContext):
    user_id = message.from_user.id
    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        if not user or user.status == "banned" or user.balance < 1:
            await message.answer(f"❌ Insufficient credits. Contact Admin: {Config.ADMIN_USERNAME}")
            return
    await message.answer("📱 Enter phone number (e.g., 018XXXXXXXX):")
    await state.set_state(SMSStates.waiting_number)

@router.message(SMSStates.waiting_number)
async def sms_number(message: Message, state: FSMContext):
    number, valid = format_phone_number(message.text)
    if not valid:
        await message.answer("❌ Invalid number. Use format: 018XXXXXXXX")
        return
    await state.update_data(number=number)
    await message.answer("💬 Now enter your message:")
    await state.set_state(SMSStates.waiting_message)

@router.message(SMSStates.waiting_message)
async def sms_message(message: Message, state: FSMContext):
    data = await state.get_data()
    number = data['number']
    sms_text = message.text
    user_id = message.from_user.id

    await message.answer("⏳ Sending...")

    success, response = await send_sms(number, sms_text)

    if success:
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            if user and user.balance >= 1:
                user.balance -= 1
                await db.commit()
                await message.answer(f"✅ SMS sent! 1 credit deducted.\\n📩 API Reply: `{response}`", parse_mode="Markdown")
            else:
                await message.answer("❌ Balance insufficient after retry.")
                success = False
    else:
        await message.answer(f"❌ Failed to send. No credit deducted.\\n⚠️ Response: `{response}`", parse_mode="Markdown")

    log_text = (
        f"📝 **SMS LOG**\\n"
        f"User: `{user_id}`\\n"
        f"Number: `{number}`\\n"
        f"Message: {sms_text}\\n"
        f"Status: {'✅ Success' if success else '❌ Failed'}\\n"
        f"Response: `{response}`"
    )
    try:
        await message.bot.send_message(Config.LOG_CHANNEL, log_text, parse_mode="Markdown")
    except:
        pass
    await state.clear()
""".strip(),

    "sms_bot_pro/app/handlers/admin.py": """
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func
import asyncio
from app.database import AsyncSessionLocal
from app.models import User, Account, RedeemCode
from app.config import Config
from app.utils.keyboards import admin_keyboard, user_keyboard

router = Router()

class AdminStates(StatesGroup):
    add_id = State(); add_amount = State()
    rem_id = State(); rem_amount = State()
    ban_id = State(); unban_id = State()
    broadcast_msg = State()
    code_name = State(); code_amount = State(); code_usages = State()
    acc_user = State(); acc_pass = State()

@router.message(F.text == "⬅️ Back")
async def back_to_user(message: Message, state: FSMContext):
    if message.from_user.id not in Config.ADMIN_IDS: return
    await state.clear()
    await message.answer("🔽 Switched to User Panel.", reply_markup=user_keyboard())

@router.message(F.text == "➕ Add Credit")
async def add_credit(message: Message, state: FSMContext):
    if message.from_user.id not in Config.ADMIN_IDS: return
    await state.set_state(AdminStates.add_id)
    await message.answer("👤 Enter Telegram ID:")

@router.message(AdminStates.add_id)
async def add_credit_id(message: Message, state: FSMContext):
    if message.from_user.id not in Config.ADMIN_IDS: return
    try:
        await state.update_data(uid=int(message.text.strip()))
        await message.answer("💰 Enter Amount:")
        await state.set_state(AdminStates.add_amount)
    except: await message.answer("❌ Invalid ID."); await state.clear()

@router.message(AdminStates.add_amount)
async def add_credit_amount(message: Message, state: FSMContext):
    if message.from_user.id not in Config.ADMIN_IDS: return
    data = await state.get_data()
    try:
        amount = int(message.text.strip())
        async with AsyncSessionLocal() as db:
            user = await db.get(User, data['uid'])
            if not user: await message.answer("❌ User not found."); await state.clear(); return
            user.balance += amount
            await db.commit()
        await message.answer(f"✅ Added {amount} credits to {data['uid']}.")
    except: await message.answer("❌ Invalid amount.")
    await state.clear()

@router.message(F.text == "➖ Remove Credit")
async def remove_credit(message: Message, state: FSMContext):
    if message.from_user.id not in Config.ADMIN_IDS: return
    await state.set_state(AdminStates.rem_id)
    await message.answer("👤 Enter Telegram ID:")

@router.message(AdminStates.rem_id)
async def rem_credit_id(message: Message, state: FSMContext):
    if message.from_user.id not in Config.ADMIN_IDS: return
    try:
        await state.update_data(uid=int(message.text.strip()))
        await message.answer("💰 Enter Amount to Remove:")
        await state.set_state(AdminStates.rem_amount)
    except: await message.answer("❌ Invalid ID."); await state.clear()

@router.message(AdminStates.rem_amount)
async def rem_credit_amount(message: Message, state: FSMContext):
    if message.from_user.id not in Config.ADMIN_IDS: return
    data = await state.get_data()
    try:
        amount = int(message.text.strip())
        async with AsyncSessionLocal() as db:
            user = await db.get(User, data['uid'])
            if not user: await message.answer("❌ User not found."); await state.clear(); return
            if user.balance < amount: await message.answer(f"❌ User has only {user.balance} credits."); await state.clear(); return
            user.balance -= amount
            await db.commit()
        await message.answer(f"✅ Removed {amount} credits from {data['uid']}.")
    except: await message.answer("❌ Invalid amount.")
    await state.clear()

@router.message(F.text == "🚫 User Ban")
async def ban_user(message: Message, state: FSMContext):
    if message.from_user.id not in Config.ADMIN_IDS: return
    await state.set_state(AdminStates.ban_id)
    await message.answer("👤 Enter Telegram ID to BAN:")

@router.message(AdminStates.ban_id)
async def process_ban(message: Message, state: FSMContext):
    if message.from_user.id not in Config.ADMIN_IDS: return
    try:
        uid = int(message.text.strip())
        async with AsyncSessionLocal() as db:
            user = await db.get(User, uid)
            if not user: await message.answer("❌ User not found."); await state.clear(); return
            user.status = "banned"
            await db.commit()
        await message.answer(f"🚫 User {uid} banned.")
    except: await message.answer("❌ Invalid ID.")
    await state.clear()

@router.message(F.text == "✅ User Unban")
async def unban_user(message: Message, state: FSMContext):
    if message.from_user.id not in Config.ADMIN_IDS: return
    await state.set_state(AdminStates.unban_id)
    await message.answer("👤 Enter Telegram ID to UNBAN:")

@router.message(AdminStates.unban_id)
async def process_unban(message: Message, state: FSMContext):
    if message.from_user.id not in Config.ADMIN_IDS: return
    try:
        uid = int(message.text.strip())
        async with AsyncSessionLocal() as db:
            user = await db.get(User, uid)
            if not user: await message.answer("❌ User not found."); await state.clear(); return
            user.status = "active"
            await db.commit()
        await message.answer(f"✅ User {uid} unbanned.")
    except: await message.answer("❌ Invalid ID.")
    await state.clear()

@router.message(F.text == "📣 Broadcast")
async def ask_broadcast(message: Message, state: FSMContext):
    if message.from_user.id not in Config.ADMIN_IDS: return
    await state.set_state(AdminStates.broadcast_msg)
    await message.answer("📢 Send your broadcast message:")

@router.message(AdminStates.broadcast_msg)
async def process_broadcast(message: Message, state: FSMContext):
    if message.from_user.id not in Config.ADMIN_IDS: return
    text = message.text
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User.user_id))
        users = result.scalars().all()
    await message.answer(f"⏳ Broadcasting to {len(users)} users...")
    success = 0
    for uid in users:
        try:
            await message.bot.send_message(uid, f"📢 **Admin Announcement:**\\n\\n{text}")
            success += 1
            await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ Sent to {success} users.")
    await state.clear()

@router.message(F.text == "👥 Total User")
async def total_stats(message: Message, state: FSMContext):
    if message.from_user.id not in Config.ADMIN_IDS: return
    await state.clear()
    async with AsyncSessionLocal() as db:
        total_users = await db.scalar(select(func.count()).select_from(User))
        total_accounts = await db.scalar(select(func.count()).select_from(Account))
    await message.answer(
        f"📊 **SYSTEM STATS**\\n\\n"
        f"👥 Logged-in Users: {total_users}\\n"
        f"🔐 Created Accounts: {total_accounts}"
    )

@router.message(F.text == "🔐 Create Account")
async def create_acc(message: Message, state: FSMContext):
    if message.from_user.id not in Config.ADMIN_IDS: return
    await state.set_state(AdminStates.acc_user)
    await message.answer("👤 Enter new Username:")

@router.message(AdminStates.acc_user)
async def acc_username(message: Message, state: FSMContext):
    if message.from_user.id not in Config.ADMIN_IDS: return
    await state.update_data(u=message.text.strip())
    await message.answer("🔑 Enter Password:")
    await state.set_state(AdminStates.acc_pass)

@router.message(AdminStates.acc_pass)
async def acc_password(message: Message, state: FSMContext):
    if message.from_user.id not in Config.ADMIN_IDS: return
    data = await state.get_data()
    async with AsyncSessionLocal() as db:
        try:
            db.add(Account(username=data['u'], password=message.text.strip()))
            await db.commit()
            await message.answer(f"✅ Account Created!\\n👤 `{data['u']}`\\n🔑 `{message.text}`", parse_mode="Markdown")
        except Exception:
            await message.answer("❌ Username already exists.")
    await state.clear()

@router.message(F.text == "🎟 Create Redeem Code")
async def create_redeem(message: Message, state: FSMContext):
    if message.from_user.id not in Config.ADMIN_IDS: return
    await state.set_state(AdminStates.code_name)
    await message.answer("🎟 Enter Code Name (e.g., FREE50):")

@router.message(AdminStates.code_name)
async def redeem_name(message: Message, state: FSMContext):
    if message.from_user.id not in Config.ADMIN_IDS: return
    await state.update_data(c_name=message.text.strip().upper())
    await message.answer("💰 Enter Amount (Credits):")
    await state.set_state(AdminStates.code_amount)

@router.message(AdminStates.code_amount)
async def redeem_amount(message: Message, state: FSMContext):
    if message.from_user.id not in Config.ADMIN_IDS: return
    try:
        await state.update_data(c_amt=int(message.text.strip()))
        await message.answer("👥 How many total uses?")
        await state.set_state(AdminStates.code_usages)
    except: await message.answer("❌ Invalid number."); await state.clear()

@router.message(AdminStates.code_usages)
async def redeem_usages(message: Message, state: FSMContext):
    if message.from_user.id not in Config.ADMIN_IDS: return
    data = await state.get_data()
    try:
        usages = int(message.text.strip())
        async with AsyncSessionLocal() as db:
            db.add(RedeemCode(code=data['c_name'], amount=data['c_amt'], usages=usages))
            await db.commit()
        await message.answer(f"✅ Code `{data['c_name']}` created with {usages} uses!")
    except Exception:
        await message.answer(f"❌ Code `{data['c_name']}` already exists.")
    await state.clear()
""".strip(),

    "sms_bot_pro/app/middlewares/__init__.py": "",
    "sms_bot_pro/app/middlewares/rate_limit.py": """
from typing import Any, Dict
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
import time
from collections import defaultdict
from app.config import Config

class RateLimitMiddleware(BaseMiddleware):
    def __init__(self):
        self.storage = defaultdict(list)

    async def __call__(self, handler, event: Any, data: Dict[str, Any]):
        user_id = None
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
        else:
            return await handler(event, data)
        now = time.time()
        self.storage[user_id] = [t for t in self.storage[user_id] if now - t < Config.RATE_LIMIT_WINDOW]
        if len(self.storage[user_id]) >= Config.RATE_LIMIT_MAX:
            if isinstance(event, Message):
                await event.answer("⏳ Too many requests. Please wait.")
            return
        self.storage[user_id].append(now)
        return await handler(event, data)
""".strip(),

    "sms_bot_pro/app/middlewares/logging.py": """
from typing import Any, Dict
from aiogram import BaseMiddleware
from aiogram.types import Message
import logging

logger = logging.getLogger(__name__)

class LoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Message, data: Dict[str, Any]):
        if isinstance(event, Message):
            logger.info(f"User {event.from_user.id} sent: {event.text}")
        return await handler(event, data)
""".strip(),

    "sms_bot_pro/app/services/__init__.py": "",
    "sms_bot_pro/app/services/sms_api.py": """
import aiohttp
import asyncio
import logging
from app.config import Config

logger = logging.getLogger(__name__)

async def send_sms(number: str, message: str) -> tuple[bool, str]:
    params = {
        "key": Config.SMS_API_KEY,
        "number": number,
        "msg": message
    }
    for attempt in range(1, Config.SMS_RETRY_COUNT + 1):
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(Config.SMS_API_URL, params=params) as resp:
                    raw_text = await resp.text()
                    try:
                        data = await resp.json()
                        if data.get("status") == "success":
                            return True, data.get("message", "Success")
                        else:
                            return False, data.get("message", raw_text)
                    except:
                        if resp.status == 200 and "error" not in raw_text.lower():
                            return True, raw_text
                        else:
                            return False, raw_text
        except asyncio.TimeoutError:
            logger.warning(f"SMS API timeout attempt {attempt}")
            if attempt == Config.SMS_RETRY_COUNT:
                return False, "❌ API Timeout after retries"
        except Exception as e:
            logger.error(f"SMS API error: {e}")
            if attempt == Config.SMS_RETRY_COUNT:
                return False, f"❌ Error: {str(e)}"
        await asyncio.sleep(1)
    return False, "Unknown error"
""".strip(),

    "sms_bot_pro/app/utils/__init__.py": "",
    "sms_bot_pro/app/utils/helpers.py": """
import re
from typing import Tuple

def format_phone_number(raw: str) -> Tuple[str, bool]:
    cleaned = re.sub(r'[\\s\\-+]', '', raw.strip())
    if cleaned.startswith('880'):
        cleaned = cleaned[3:]
    if cleaned.startswith('0') and len(cleaned) == 11 and cleaned.isdigit():
        return cleaned, True
    if cleaned.startswith('1') and len(cleaned) == 10 and cleaned.isdigit():
        return '0' + cleaned, True
    return cleaned, False
""".strip(),

    "sms_bot_pro/app/utils/keyboards.py": """
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def user_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚀 Send SMS"), KeyboardButton(text="👤 My Profile")],
            [KeyboardButton(text="👥 Referral"), KeyboardButton(text="🎁 Redeem Code")],
            [KeyboardButton(text="☎️ Support")]
        ],
        resize_keyboard=True,
        persistent=True
    )

def admin_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Add Credit"), KeyboardButton(text="➖ Remove Credit")],
            [KeyboardButton(text="🚫 User Ban"), KeyboardButton(text="✅ User Unban")],
            [KeyboardButton(text="📣 Broadcast"), KeyboardButton(text="🎟 Create Redeem Code")],
            [KeyboardButton(text="👥 Total User"), KeyboardButton(text="🔐 Create Account")],
            [KeyboardButton(text="⬅️ Back")]
        ],
        resize_keyboard=True,
        persistent=True
    )
""".strip(),

    "sms_bot_pro/app/utils/logger.py": """
import logging
import sys

def setup_logger():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("bot.log"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logging.getLogger("aiogram").setLevel(logging.WARNING)
""".strip(),
}

def create_project():
    for file_path, content in FILES.items():
        dir_name = os.path.dirname(file_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ Created: {file_path}")

    os.makedirs("sms_bot_pro/data", exist_ok=True)
    with open("sms_bot_pro/data/.gitkeep", 'w') as f:
        pass

    print("\n🎉 সব ফাইল তৈরি হয়েছে!")
    print("📁 'sms_bot_pro' ফোল্ডারে যান।")
    print("🚀 রান করুন: pip install -r requirements.txt")
    print("🚀 তারপর: python -m app.main")
    print("\n🔒 নিরাপত্তা সতর্কতা: আপনার .env ফাইলটি গিট রেপোতে পুশ হবে না ( .gitignore-এর কারণে )।")

if __name__ == "__main__":
    create_project()
