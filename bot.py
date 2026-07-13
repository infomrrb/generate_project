import asyncio
import logging
import os
import re
from datetime import datetime
from typing import Optional, Tuple

import aiohttp
import aiosqlite
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from dotenv import load_dotenv

# -------------------- Load Environment --------------------
load_dotenv()

BOT_TOKEN = os.getenv("8919343304:AAEmHznQk2Q2tlkxNcOgTYDkMZZ5PesoBPw")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing from environment")

ADMIN_ID = int(os.getenv("1967494059", 0))
ADMIN_USERNAME = @RobiEntertainment", "@RobiEntertainment")
DEV_USERNAME = os.getenv("RobiEntertainment", "Developer")
SMS_API_URL = os.getenv("http://hakvolution.com/KEY/sub.php?key=&number=&msg=")
SMS_API_KEY = os.getenv("Bacf_sms_Robi")
LOG_CHANNEL = int(os.getenv("1001234567890", 0))

if not SMS_API_URL or not SMS_API_KEY:
    raise ValueError("SMS_API_URL and SMS_API_KEY are required")

# -------------------- Logging --------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# -------------------- Bot & Dispatcher --------------------
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# -------------------- Database --------------------
DB_PATH = "bot_database.db"

async def init_db():
    """Create tables if they don't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                login_username TEXT,
                balance INTEGER DEFAULT 0,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'active'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                username TEXT PRIMARY KEY,
                password TEXT,
                telegram_id INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS redeem_codes (
                code TEXT PRIMARY KEY,
                amount INTEGER,
                usages INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS redeem_history (
                user_id INTEGER,
                code TEXT,
                PRIMARY KEY (user_id, code)
            )
        """)
        # Insert admin if not exists
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, login_username, balance, status) VALUES (?, 'Admin', 9999, 'active')",
            (ADMIN_ID,)
        )
        await db.commit()
    logger.info("Database initialized.")

# -------------------- Utility Functions --------------------
def format_phone_number(raw: str) -> Tuple[Optional[str], bool]:
    """
    Clean and format a Bangladeshi phone number.
    Returns (formatted_number, is_valid).
    """
    cleaned = re.sub(r'[\s\-+]', '', raw.strip())
    if cleaned.startswith('880'):
        cleaned = cleaned[3:]
    if cleaned.startswith('0') and len(cleaned) == 11 and cleaned.isdigit():
        return cleaned, True
    if cleaned.startswith('1') and len(cleaned) == 10 and cleaned.isdigit():
        return '0' + cleaned, True
    return None, False

async def get_user_status(user_id: int) -> Optional[str]:
    """Return status of a user or None if not found."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT status FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else None

async def is_active_user(user_id: int) -> bool:
    """Check if user is logged in and active."""
    if user_id == ADMIN_ID:
        return True
    status = await get_user_status(user_id)
    return status == "active"

async def log_action(action: str, user_id: int, details: str = ""):
    """Log admin actions to the log channel."""
    if LOG_CHANNEL:
        try:
            msg = f"📋 **Admin Action**\n\n👤 User ID: `{user_id}`\n🔧 Action: {action}\n📝 Details: {details}"
            await bot.send_message(LOG_CHANNEL, msg, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Failed to send log: {e}")

# -------------------- Reply Keyboards --------------------
user_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🚀 Send SMS"), KeyboardButton(text="👤 My Profile")],
        [KeyboardButton(text="👥 Referral"), KeyboardButton(text="🎁 Redeem Code")],
        [KeyboardButton(text="☎️ Support")]
    ],
    resize_keyboard=True,
    persistent=True
)

admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➕ Add Credit"), KeyboardButton(text="➖ Remove Credit")],
        [KeyboardButton(text="🚫 User Ban"), KeyboardButton(text="✅ User Unban")],
        [KeyboardButton(text="📣 Broadcast"), KeyboardButton(text="🎟 Create Redeem Code")],
        [KeyboardButton(text="👥 Total Users"), KeyboardButton(text="🔐 Create Account")],
        [KeyboardButton(text="⬅️ Back")]
    ],
    resize_keyboard=True,
    persistent=True
)

# -------------------- FSM States --------------------
class AuthState(StatesGroup):
    wait_username = State()
    wait_password = State()

class SMSState(StatesGroup):
    waiting_for_number = State()
    waiting_for_message = State()

class UserState(StatesGroup):
    waiting_for_code = State()

class AdminState(StatesGroup):
    add_id = State()
    add_amount = State()
    rem_id = State()
    rem_amount = State()
    ban_id = State()
    unban_id = State()
    broadcast_msg = State()
    code_name = State()
    code_amount = State()
    code_usages = State()
    acc_user = State()
    acc_pass = State()

# -------------------- Handlers --------------------

@dp.message(Command("start"))
async def start_command(message: types.Message, state: FSMContext):
    """Handle /start command."""
    await state.clear()
    user_id = message.from_user.id

    if user_id == ADMIN_ID:
        await message.answer("👑 **Admin Panel**\nWelcome back, Admin!", reply_markup=admin_kb)
        return

    # Check if already a user
    status = await get_user_status(user_id)
    if status:
        if status == "banned":
            await message.answer(f"⛔ You are banned. Contact Admin: {ADMIN_USERNAME}", reply_markup=ReplyKeyboardRemove())
            return
        await message.answer(f"👋 Welcome back {message.from_user.first_name}!", reply_markup=user_kb)
    else:
        # New user: start login
        await message.answer("🔒 **Login Required**\n\nPlease enter your **Username**:", reply_markup=ReplyKeyboardRemove())
        await state.set_state(AuthState.wait_username)

@dp.message(Command("admin"))
async def admin_cmd(message: types.Message, state: FSMContext):
    """Admin panel command."""
    await state.clear()
    if message.from_user.id == ADMIN_ID:
        await message.answer("👑 **Admin Panel**", reply_markup=admin_kb)
    else:
        await message.answer("⛔ Unauthorized.")

@dp.message(F.text == "⬅️ Back")
async def back_to_user(message: types.Message, state: FSMContext):
    """Return to user keyboard."""
    await state.clear()
    if message.from_user.id == ADMIN_ID:
        await message.answer("Switched to User Mode.", reply_markup=user_kb)
    else:
        await message.answer("Home", reply_markup=user_kb)

@dp.message(F.text == "👤 My Profile")
async def my_profile(message: types.Message, state: FSMContext):
    """Show user profile."""
    await state.clear()
    if not await is_active_user(message.from_user.id):
        return
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT balance, login_username, status FROM users WHERE user_id = ?",
            (message.from_user.id,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                await message.answer(
                    f"👤 **MY PROFILE**\n\n"
                    f"🆔 **TG ID:** `{message.from_user.id}`\n"
                    f"👤 **Username:** {row[1]}\n"
                    f"💰 **Credits:** {row[0]}\n"
                    f"🚦 **Status:** {row[2].capitalize()}\n\n"
                    f"👨‍💻 **Dev:** {DEV_USERNAME}",
                    parse_mode="Markdown"
                )

# -------------------- SMS Flow --------------------
@dp.message(F.text == "🚀 Send SMS")
async def start_sms_flow(message: types.Message, state: FSMContext):
    """Initiate SMS sending."""
    await state.clear()
    user_id = message.from_user.id
    if not await is_active_user(user_id):
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if not row or row[0] < 1:
                await message.answer(
                    f"❌ You don't have enough credits. Please use a Redeem Code or contact Admin {ADMIN_USERNAME}."
                )
                return

    await message.answer("📱 Please enter the **Phone Number** (e.g. 018XXXXXXXX, 017XXXXXXXX):")
    await state.set_state(SMSState.waiting_for_number)

@dp.message(SMSState.waiting_for_number)
async def process_number(message: types.Message, state: FSMContext):
    """Handle phone number input."""
    raw = message.text.strip()
    formatted, valid = format_phone_number(raw)
    if not valid:
        await message.answer(
            f"❌ Invalid number format!\n\n"
            f"Please enter a valid 11-digit Bangladeshi number starting with **0** (e.g. 01827572551).\n"
            f"Your input: `{raw}`",
            parse_mode="Markdown"
        )
        return

    await state.update_data(number=formatted)
    await message.answer(
        f"✅ Number set to: `{formatted}`\n\n💬 Now enter your **Message**:",
        parse_mode="Markdown"
    )
    await state.set_state(SMSState.waiting_for_message)

@dp.message(SMSState.waiting_for_message)
async def process_message(message: types.Message, state: FSMContext):
    """Handle message and send SMS."""
    data = await state.get_data()
    number = data.get("number")
    sms_text = message.text.strip()

    # Validate message length (optional)
    if len(sms_text) > 160:
        await message.answer("❌ Message too long. Please keep it under 160 characters.")
        return

    user_id = message.from_user.id
    await message.answer(f"⏳ Sending SMS to `{number}`...\n*Please wait...*", parse_mode="Markdown")

    params = {
        "key": SMS_API_KEY,
        "number": number,
        "msg": sms_text
    }

    success = False
    api_response = "No response"
    details = ""

    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(SMS_API_URL, params=params) as resp:
                raw_text = await resp.text()
                api_response = raw_text

                # Try to parse JSON response
                try:
                    data_json = await resp.json()
                    details = f"JSON: {data_json}"
                    if data_json.get("status") == "success":
                        success = True
                        api_response = data_json.get("message", "Success")
                    else:
                        success = False
                        api_response = data_json.get("message", "API returned non-success")
                except:
                    # Fallback: check plain text for success indicators
                    details = f"Plain: {raw_text}"
                    if resp.status == 200 and "error" not in raw_text.lower() and "invalid" not in raw_text.lower():
                        success = True
                        api_response = raw_text
                    else:
                        success = False
                        api_response = raw_text
    except asyncio.TimeoutError:
        api_response = "❌ API Timeout (Server not responding)"
        details = "Timeout"
        success = False
    except Exception as e:
        api_response = f"❌ Error: {str(e)}"
        details = f"Exception: {str(e)}"
        success = False

    # Deduct credit if successful
    if success:
        async with aiosqlite.connect(DB_PATH) as db:
            # Re-check balance
            async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
                if row and row[0] >= 1:
                    await db.execute("UPDATE users SET balance = balance - 1 WHERE user_id = ?", (user_id,))
                    await db.commit()
                    await message.answer(
                        f"✅ **SMS Sent Successfully!**\n💰 1 Credit deducted.\n\n📩 API Reply: `{api_response}`",
                        parse_mode="Markdown"
                    )
                else:
                    success = False
                    await message.answer("❌ Insufficient credits after re-check. Please try again.")
    else:
        await message.answer(
            f"❌ **Failed to send SMS.** No credits deducted.\n\n⚠️ **Server Response:**\n`{api_response}`",
            parse_mode="Markdown"
        )

    await state.clear()

    # Log to channel
    log_text = (
        f"📝 **SMS LOG**\n\n"
        f"👤 **User ID:** `{user_id}`\n"
        f"📱 **Number:** `{number}`\n"
        f"💬 **Message:**\n{sms_text}\n\n"
        f"🚦 **Status:** {'✅ Success' if success else '❌ Failed'}\n"
        f"📡 **Response:**\n`{api_response}`\n\n"
        f"🔍 **Details:** {details}"
    )
    try:
        await bot.send_message(LOG_CHANNEL, log_text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Log channel error: {e}")

# -------------------- Redeem Code --------------------
@dp.message(F.text == "🎁 Redeem Code")
async def ask_redeem(message: types.Message, state: FSMContext):
    """Ask for redeem code."""
    await state.clear()
    if not await is_active_user(message.from_user.id):
        return
    await message.answer("🎟 Enter your **Redeem Code**:")
    await state.set_state(UserState.waiting_for_code)

@dp.message(UserState.waiting_for_code)
async def process_redeem(message: types.Message, state: FSMContext):
    """Process redeem code."""
    code = message.text.strip()
    user_id = message.from_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        # Check if already used
        async with db.execute("SELECT 1 FROM redeem_history WHERE user_id = ? AND code = ?", (user_id, code)) as cur:
            if await cur.fetchone():
                await message.answer("❌ You have already used this code.")
                await state.clear()
                return

        # Check code validity
        async with db.execute("SELECT amount, usages FROM redeem_codes WHERE code = ?", (code,)) as cur:
            row = await cur.fetchone()
            if not row or row[1] <= 0:
                await message.answer("❌ Invalid or Expired Code.")
                await state.clear()
                return

        amount = row[0]
        # Update user balance, decrease usages, record history
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.execute("UPDATE redeem_codes SET usages = usages - 1 WHERE code = ?", (code,))
        await db.execute("INSERT INTO redeem_history (user_id, code) VALUES (?, ?)", (user_id, code))
        await db.commit()

    await message.answer(f"🎉 **Code Redeemed!**\n✅ You got +{amount} Credits.")
    await state.clear()

# -------------------- Referral & Support --------------------
@dp.message(F.text == "👥 Referral")
async def referral_info(message: types.Message, state: FSMContext):
    """Placeholder for referral."""
    await state.clear()
    if not await is_active_user(message.from_user.id):
        return
    await message.answer(
        f"👥 **Referral System**\n\nCurrently disabled. Ask friends to contact Admin ({ADMIN_USERNAME})."
    )

@dp.message(F.text == "☎️ Support")
async def support(message: types.Message, state: FSMContext):
    """Support contact."""
    await state.clear()
    if not await is_active_user(message.from_user.id):
        return
    await message.answer(
        f"☎️ **Support**\n\nFor issues or buying credits, contact Admin:\n👨‍💻 **{ADMIN_USERNAME}**"
    )

# -------------------- Authentication Flow --------------------
@dp.message(AuthState.wait_username)
async def process_username(message: types.Message, state: FSMContext):
    """Handle username input."""
    username = message.text.strip()
    await state.update_data(username=username)
    await message.answer("🔑 Enter **Password**:")
    await state.set_state(AuthState.wait_password)

@dp.message(AuthState.wait_password)
async def process_password(message: types.Message, state: FSMContext):
    """Handle password input and authenticate."""
    data = await state.get_data()
    username = data.get("username")
    password = message.text.strip()
    user_id = message.from_user.id

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT password, telegram_id FROM accounts WHERE username = ?", (username,)) as cur:
            row = await cur.fetchone()
            if row and row[0] == password:
                # Check if account is linked to another device
                if row[1] and row[1] != user_id:
                    await message.answer(
                        f"❌ Account linked to another device.\nContact Admin: {ADMIN_USERNAME}"
                    )
                    await state.clear()
                    return
                # Update telegram_id and create user entry
                await db.execute("UPDATE accounts SET telegram_id = ? WHERE username = ?", (user_id, username))
                await db.execute(
                    "INSERT OR IGNORE INTO users (user_id, login_username, balance, status) VALUES (?, ?, 0, 'active')",
                    (user_id, username)
                )
                await db.commit()
                await message.answer("✅ **Login Successful!**", reply_markup=user_kb)
            else:
                await message.answer(
                    f"❌ **Wrong Username or Password!**\n\nIf you need an account, please contact Admin:\n👨‍💻 **{ADMIN_USERNAME}**"
                )
    await state.clear()

# -------------------- Admin Handlers --------------------

@dp.message(F.text == "🔐 Create Account", F.from_user.id == ADMIN_ID)
async def admin_create_account(message: types.Message, state: FSMContext):
    """Start creating an account."""
    await state.clear()
    await message.answer("👤 Enter a new **Username**:")
    await state.set_state(AdminState.acc_user)

@dp.message(AdminState.acc_user, F.from_user.id == ADMIN_ID)
async def admin_acc_user(message: types.Message, state: FSMContext):
    """Store username and ask for password."""
    await state.update_data(u=message.text.strip())
    await message.answer("🔑 Enter **Password**:")
    await state.set_state(AdminState.acc_pass)

@dp.message(AdminState.acc_pass, F.from_user.id == ADMIN_ID)
async def admin_acc_pass(message: types.Message, state: FSMContext):
    """Create account."""
    data = await state.get_data()
    username = data.get("u")
    password = message.text.strip()
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("INSERT INTO accounts (username, password) VALUES (?, ?)", (username, password))
            await db.commit()
            await message.answer(
                f"✅ **Account Created!**\n👤 Username: `{username}`\n🔑 Password: `{password}`",
                parse_mode="Markdown"
            )
            await log_action("Create Account", ADMIN_ID, f"Username: {username}")
        except aiosqlite.IntegrityError:
            await message.answer("❌ Username already exists!")
    await state.clear()

# Add Credit
@dp.message(F.text == "➕ Add Credit", F.from_user.id == ADMIN_ID)
async def admin_add_credit(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("👤 Enter **Telegram ID** to add credits:")
    await state.set_state(AdminState.add_id)

@dp.message(AdminState.add_id, F.from_user.id == ADMIN_ID)
async def admin_add_id(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
        await state.update_data(u_id=uid)
        await message.answer("💰 Enter **Amount**:")
        await state.set_state(AdminState.add_amount)
    except ValueError:
        await message.answer("❌ Invalid Telegram ID. Please enter a number.")
        await state.clear()

@dp.message(AdminState.add_amount, F.from_user.id == ADMIN_ID)
async def admin_add_amount(message: types.Message, state: FSMContext):
    data = await state.get_data()
    uid = data.get("u_id")
    try:
        amount = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Invalid amount. Please enter a number.")
        await state.clear()
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (uid,)) as cur:
            if not await cur.fetchone():
                await message.answer(f"❌ User ID {uid} not found.")
                await state.clear()
                return
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, uid))
        await db.commit()
    await message.answer(f"✅ Added {amount} credits to user {uid}.")
    await log_action("Add Credit", ADMIN_ID, f"User: {uid}, Amount: {amount}")
    await state.clear()

# Remove Credit
@dp.message(F.text == "➖ Remove Credit", F.from_user.id == ADMIN_ID)
async def admin_remove_credit(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("👤 Enter **Telegram ID** to remove credits:")
    await state.set_state(AdminState.rem_id)

@dp.message(AdminState.rem_id, F.from_user.id == ADMIN_ID)
async def admin_rem_id(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
        await state.update_data(u_id=uid)
        await message.answer("💰 Enter **Amount**:")
        await state.set_state(AdminState.rem_amount)
    except ValueError:
        await message.answer("❌ Invalid Telegram ID.")
        await state.clear()

@dp.message(AdminState.rem_amount, F.from_user.id == ADMIN_ID)
async def admin_rem_amount(message: types.Message, state: FSMContext):
    data = await state.get_data()
    uid = data.get("u_id")
    try:
        amount = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Invalid amount.")
        await state.clear()
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (uid,)) as cur:
            row = await cur.fetchone()
            if not row:
                await message.answer(f"❌ User {uid} not found.")
                await state.clear()
                return
            if row[0] < amount:
                await message.answer(f"❌ User has only {row[0]} credits. Cannot remove {amount}.")
                await state.clear()
                return
        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, uid))
        await db.commit()
    await message.answer(f"✅ Removed {amount} credits from user {uid}.")
    await log_action("Remove Credit", ADMIN_ID, f"User: {uid}, Amount: {amount}")
    await state.clear()

# Ban / Unban
@dp.message(F.text == "🚫 User Ban", F.from_user.id == ADMIN_ID)
async def admin_ban(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("👤 Enter **Telegram ID** to BAN:")
    await state.set_state(AdminState.ban_id)

@dp.message(AdminState.ban_id, F.from_user.id == ADMIN_ID)
async def admin_ban_id(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Invalid ID.")
        await state.clear()
        return
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (uid,)) as cur:
            if not await cur.fetchone():
                await message.answer(f"❌ User {uid} not found.")
                await state.clear()
                return
        await db.execute("UPDATE users SET status = 'banned' WHERE user_id = ?", (uid,))
        await db.commit()
    await message.answer(f"🚫 User {uid} banned.")
    await log_action("Ban User", ADMIN_ID, f"User: {uid}")
    await state.clear()

@dp.message(F.text == "✅ User Unban", F.from_user.id == ADMIN_ID)
async def admin_unban(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("👤 Enter **Telegram ID** to UNBAN:")
    await state.set_state(AdminState.unban_id)

@dp.message(AdminState.unban_id, F.from_user.id == ADMIN_ID)
async def admin_unban_id(message: types.Message, state: FSMContext):
    try:
        uid = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Invalid ID.")
        await state.clear()
        return
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (uid,)) as cur:
            if not await cur.fetchone():
                await message.answer(f"❌ User {uid} not found.")
                await state.clear()
                return
        await db.execute("UPDATE users SET status = 'active' WHERE user_id = ?", (uid,))
        await db.commit()
    await message.answer(f"✅ User {uid} unbanned.")
    await log_action("Unban User", ADMIN_ID, f"User: {uid}")
    await state.clear()

# Broadcast
@dp.message(F.text == "📣 Broadcast", F.from_user.id == ADMIN_ID)
async def admin_broadcast(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("📢 Send the message you want to broadcast:")
    await state.set_state(AdminState.broadcast_msg)

@dp.message(AdminState.broadcast_msg, F.from_user.id == ADMIN_ID)
async def admin_broadcast_send(message: types.Message, state: FSMContext):
    broadcast_text = message.text
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as cur:
            users = await cur.fetchall()
    await message.answer(f"⏳ Broadcasting to {len(users)} users...")
    success = 0
    for (uid,) in users:
        try:
            await bot.send_message(uid, f"📢 **Admin Message:**\n\n{broadcast_text}")
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await message.answer(f"✅ Sent to {success} users.")
    await log_action("Broadcast", ADMIN_ID, f"Sent to {success} users")
    await state.clear()

# Create Redeem Code
@dp.message(F.text == "🎟 Create Redeem Code", F.from_user.id == ADMIN_ID)
async def admin_create_code(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🎟 Enter **Code Name** (e.g. FREE50):")
    await state.set_state(AdminState.code_name)

@dp.message(AdminState.code_name, F.from_user.id == ADMIN_ID)
async def admin_code_name(message: types.Message, state: FSMContext):
    await state.update_data(c_name=message.text.strip())
    await message.answer("💰 Enter **Amount**:")
    await state.set_state(AdminState.code_amount)

@dp.message(AdminState.code_amount, F.from_user.id == ADMIN_ID)
async def admin_code_amount(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        await state.update_data(c_amt=amount)
        await message.answer("👥 How many **Users**? (usages):")
        await state.set_state(AdminState.code_usages)
    except ValueError:
        await message.answer("❌ Invalid amount. Please enter a number.")
        await state.clear()

@dp.message(AdminState.code_usages, F.from_user.id == ADMIN_ID)
async def admin_code_usages(message: types.Message, state: FSMContext):
    data = await state.get_data()
    code = data.get("c_name")
    amount = data.get("c_amt")
    try:
        usages = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Invalid number. Please enter a number.")
        await state.clear()
        return
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("INSERT INTO redeem_codes (code, amount, usages) VALUES (?, ?, ?)", (code, amount, usages))
            await db.commit()
            await message.answer(f"✅ **Code Created!** `{code}` with {usages} uses.")
            await log_action("Create Redeem Code", ADMIN_ID, f"Code: {code}, Amount: {amount}, Usages: {usages}")
        except aiosqlite.IntegrityError:
            await message.answer(f"❌ Code '{code}' already exists.")
    await state.clear()

# Total Users
@dp.message(F.text == "👥 Total Users", F.from_user.id == ADMIN_ID)
async def admin_stats(message: types.Message, state: FSMContext):
    await state.clear()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            total_users = await cur.fetchone()
        async with db.execute("SELECT COUNT(*) FROM accounts") as cur:
            total_accounts = await cur.fetchone()
    await message.answer(
        f"📊 **SYSTEM STATS**\n\n"
        f"👥 Logged-in Users: {total_users[0]}\n"
        f"🔐 Created Accounts: {total_accounts[0]}"
    )

# -------------------- Help Command --------------------
@dp.message(Command("help"))
async def help_command(message: types.Message):
    """Show help text."""
    help_text = (
        "🤖 **Bot Commands & Usage**\n\n"
        "• `/start` – Login or show main menu\n"
        "• `/admin` – Admin panel (admins only)\n"
        "• `/help` – Show this help\n\n"
        "**User Buttons:**\n"
        "• 🚀 Send SMS – Send an SMS (1 credit)\n"
        "• 👤 My Profile – View credits & info\n"
        "• 🎁 Redeem Code – Use a promo code\n"
        "• 👥 Referral – Referral info (disabled)\n"
        "• ☎️ Support – Contact admin\n\n"
        "**Admin Buttons:**\n"
        "• Manage credits, users, redeem codes, broadcast\n\n"
        f"👨‍💻 **Developer:** {DEV_USERNAME}\n"
        f"📞 **Support:** {ADMIN_USERNAME}"
    )
    await message.answer(help_text, parse_mode="Markdown")

# -------------------- Main --------------------
async def main():
    """Start the bot."""
    await init_db()
    logger.info("🤖 Bot is starting...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
