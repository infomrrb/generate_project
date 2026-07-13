import asyncio
import logging
import re
import aiosqlite
import aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ================== কনফিগারেশন ==================
BOT_TOKEN = "8919343304:AAEmHznQk2Q2tlkxNcOgTYDkMZZ5PesoBPw"
ADMIN_ID = 1967494059
ADMIN_USERNAME = "@RobiEntertainment"
DEV_USERNAME = "RobiEntertainment"
SMS_API_URL = "http://hakvolution.com/KEY/sub.php?key=&number=&msg="
SMS_API_KEY = "Bacf_sms_Robi"
LOG_CHANNEL = -1001234567890  # আপনার লগ চ্যানেল আইডি
# =================================================

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ---------- ডেটাবেস ----------
async def init_db():
    async with aiosqlite.connect("bot_database.db") as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            login_username TEXT,
            balance INTEGER DEFAULT 0,
            join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active'
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS accounts (
            username TEXT PRIMARY KEY,
            password TEXT,
            telegram_id INTEGER
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS redeem_codes (
            code TEXT PRIMARY KEY,
            amount INTEGER,
            usages INTEGER
        )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS redeem_history (
            user_id INTEGER,
            code TEXT,
            PRIMARY KEY (user_id, code)
        )""")
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, login_username, balance, status) VALUES (?, 'Admin', 9999, 'active')",
            (ADMIN_ID,)
        )
        await db.commit()

# ---------- নম্বর ফরম্যাটিং (API-উপযোগী) ----------
def format_phone_number(raw: str) -> tuple:
    """API-তে পাঠানোর উপযোগী ১১ ডিজিটের ০-দিয়ে-শুরু নম্বর তৈরি করে।"""
    cleaned = re.sub(r'[\s\-+]', '', raw.strip())
    if cleaned.startswith('880'):
        cleaned = cleaned[3:]
    if cleaned.startswith('0') and len(cleaned) == 11 and cleaned.isdigit():
        return cleaned, True
    if cleaned.startswith('1') and len(cleaned) == 10 and cleaned.isdigit():
        return '0' + cleaned, True
    return cleaned, False

# ---------- কিবোর্ড ----------
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
        [KeyboardButton(text="👥 Total User"), KeyboardButton(text="🔐 Create Account")],
        [KeyboardButton(text="⬅️ Back")]
    ],
    resize_keyboard=True,
    persistent=True
)

# ---------- FSM ----------
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

# ---------- চেক ফাংশন ----------
async def is_logged_in_and_active(user_id):
    if user_id == ADMIN_ID:
        return True
    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT status FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0] == 'active':
                return True
    return False

async def proceed_to_login(chat_id, user_first_name, state):
    """লগইন প্রক্রিয়া শুরু করে (ইউজারকে username চাওয়া)"""
    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT status FROM users WHERE user_id = ?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                if row[0] == 'banned':
                    await bot.send_message(chat_id, f"⛔ You are banned. Contact Admin: {ADMIN_USERNAME}", reply_markup=ReplyKeyboardRemove())
                    return
                await bot.send_message(chat_id, f"👋 Welcome back {user_first_name}!", reply_markup=user_kb)
                return
    # নতুন ইউজার – লগইন ফর্ম
    await bot.send_message(chat_id, "🔒 **Login Required**\n\nPlease enter your **Username**:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(AuthState.wait_username)

# ---------- /start ----------
@dp.message(Command("start"))
async def start_command(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id

    # অ্যাডমিন চেক
    if user_id == ADMIN_ID:
        await message.answer("👑 **Admin Panel**\nWelcome back, Admin!", reply_markup=admin_kb)
        return

    # সরাসরি লগইন প্রক্রিয়া (কোনো চ্যানেল/পেজ চেক নেই)
    await proceed_to_login(user_id, message.from_user.first_name, state)

# ---------- অন্যান্য কমান্ড ----------
@dp.message(Command("admin"))
async def admin_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    if message.from_user.id == ADMIN_ID:
        await message.answer("👑 **Admin Panel**", reply_markup=admin_kb)

@dp.message(F.text == "⬅️ Back")
async def back_u(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Switched to User Mode.", reply_markup=user_kb)

@dp.message(F.text == "👤 My Profile")
async def my_profile(message: types.Message, state: FSMContext):
    await state.clear()
    if not await is_logged_in_and_active(message.from_user.id):
        return
    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT balance, login_username, status FROM users WHERE user_id = ?", (message.from_user.id,)) as cursor:
            row = await cursor.fetchone()
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

# ---------- 📱 এসএমএস পাঠানো ----------
@dp.message(F.text == "🚀 Send SMS")
async def start_sms_flow(message: types.Message, state: FSMContext):
    await state.clear()
    if not await is_logged_in_and_active(message.from_user.id):
        return

    user_id = message.from_user.id
    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row or row[0] < 1:
                await message.answer(f"❌ You don't have enough credits. Please use a Redeem Code or contact Admin {ADMIN_USERNAME}.")
                return

    await message.answer("📱 Please enter the **Phone Number** (e.g. 018XXXXXXXX, 017XXXXXXXX):")
    await state.set_state(SMSState.waiting_for_number)

@dp.message(SMSState.waiting_for_number)
async def process_number(message: types.Message, state: FSMContext):
    raw = message.text.strip()
    formatted, valid = format_phone_number(raw)
    if not valid:
        await message.answer(
            f"❌ Invalid number format!\n\n"
            f"Please enter a valid 11-digit Bangladeshi number starting with **0** (e.g. 01827572551).\n"
            f"Your input: `{raw}`"
        )
        return

    await state.update_data(number=formatted)
    await message.answer(f"✅ Number set to: `{formatted}`\n\n💬 Now enter your **Message**:", parse_mode="Markdown")
    await state.set_state(SMSState.waiting_for_message)

@dp.message(SMSState.waiting_for_message)
async def process_message(message: types.Message, state: FSMContext):
    data = await state.get_data()
    number = data['number']
    sms_text = message.text
    user_id = message.from_user.id

    await message.answer(f"⏳ Sending SMS to `{number}`...\n*Please wait...*", parse_mode="Markdown")

    params = {
        "key": SMS_API_KEY,
        "number": number,
        "msg": sms_text
    }

    success = False
    api_response_text = "No response"
    log_details = ""

    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(SMS_API_URL, params=params) as resp:
                raw_text = await resp.text()
                api_response_text = raw_text

                try:
                    json_data = await resp.json()
                    log_details = f"JSON: {json_data}"
                    if json_data.get("status") == "success":
                        success = True
                        api_response_text = json_data.get("message", "Success")
                    else:
                        success = False
                        api_response_text = json_data.get("message", "API returned non-success status")
                except:
                    log_details = f"Plain Text: {raw_text}"
                    if resp.status == 200 and "error" not in raw_text.lower() and "invalid" not in raw_text.lower():
                        success = True
                        api_response_text = raw_text
                    else:
                        success = False
                        api_response_text = raw_text
    except asyncio.TimeoutError:
        api_response_text = "❌ API Timeout (Server not responding)"
        log_details = "Timeout Error"
        success = False
    except Exception as e:
        api_response_text = f"❌ Error: {str(e)}"
        log_details = f"Exception: {str(e)}"
        success = False

    if success:
        async with aiosqlite.connect("bot_database.db") as db:
            async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cur:
                bal_row = await cur.fetchone()
                if bal_row and bal_row[0] >= 1:
                    await db.execute("UPDATE users SET balance = balance - 1 WHERE user_id = ?", (user_id,))
                    await db.commit()
                    await message.answer(
                        f"✅ **SMS Sent Successfully!**\n💰 1 Credit deducted.\n\n📩 API Reply: `{api_response_text}`",
                        parse_mode="Markdown"
                    )
                else:
                    success = False
                    await message.answer("❌ Insufficient credits after re-check. Please try again.")
    else:
        await message.answer(
            f"❌ **Failed to send SMS.** No credits deducted.\n\n⚠️ **Server Response:**\n`{api_response_text}`",
            parse_mode="Markdown"
        )

    await state.clear()

    log_text = (
        f"📝 **SMS LOG**\n\n"
        f"👤 **User ID:** `{user_id}`\n"
        f"📱 **Number:** `{number}`\n"
        f"💬 **Message:**\n{sms_text}\n\n"
        f"🚦 **Status:** {'✅ Success' if success else '❌ Failed'}\n"
        f"📡 **Response:**\n`{api_response_text}`\n\n"
        f"🔍 **Details:** {log_details}"
    )
    try:
        await bot.send_message(chat_id=LOG_CHANNEL, text=log_text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Log channel error: {e}")

# ---------- রিডিম ----------
@dp.message(F.text == "🎁 Redeem Code")
async def ask_redeem(message: types.Message, state: FSMContext):
    await state.clear()
    if not await is_logged_in_and_active(message.from_user.id):
        return
    await message.answer("🎟 **Enter your Promo/Redeem Code:**")
    await state.set_state(UserState.waiting_for_code)

@dp.message(UserState.waiting_for_code)
async def process_redeem(message: types.Message, state: FSMContext):
    code = message.text.strip()
    user_id = message.from_user.id

    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT 1 FROM redeem_history WHERE user_id = ? AND code = ?", (user_id, code)) as cur:
            if await cur.fetchone():
                await message.answer("❌ You have already used this code.")
                await state.clear()
                return

        async with db.execute("SELECT amount, usages FROM redeem_codes WHERE code = ?", (code,)) as cur:
            row = await cur.fetchone()
            if not row or row[1] <= 0:
                await message.answer("❌ Invalid or Expired Code.")
                await state.clear()
                return

            amount = row[0]
            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
            await db.execute("UPDATE redeem_codes SET usages = usages - 1 WHERE code = ?", (code,))
            await db.execute("INSERT INTO redeem_history (user_id, code) VALUES (?, ?)", (user_id, code))
            await db.commit()

    await message.answer(f"🎉 **Code Redeemed!**\n✅ You got +{amount} Credits.")
    await state.clear()

@dp.message(F.text == "👥 Referral")
async def referral_info(message: types.Message, state: FSMContext):
    await state.clear()
    if not await is_logged_in_and_active(message.from_user.id):
        return
    await message.answer(f"👥 **Referral System**\n\nCurrently disabled. Ask friends to contact Admin ({ADMIN_USERNAME}).")

@dp.message(F.text == "☎️ Support")
async def support(message: types.Message, state: FSMContext):
    await state.clear()
    if not await is_logged_in_and_active(message.from_user.id):
        return
    await message.answer(f"☎️ **Support**\n\nFor issues or buying credits, contact Admin:\n👨‍💻 **{ADMIN_USERNAME}**")

# ---------- লগইন ----------
@dp.message(AuthState.wait_username)
async def process_username(message: types.Message, state: FSMContext):
    await state.update_data(username=message.text.strip())
    await message.answer("🔑 Enter **Password**:")
    await state.set_state(AuthState.wait_password)

@dp.message(AuthState.wait_password)
async def process_password(message: types.Message, state: FSMContext):
    data = await state.get_data()
    username = data.get('username')
    password = message.text.strip()
    user_id = message.from_user.id

    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT password, telegram_id FROM accounts WHERE username = ?", (username,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0] == password:
                if row[1] is not None and row[1] != user_id:
                    await message.answer(f"❌ Account linked to another device.\nContact Admin: {ADMIN_USERNAME}")
                    await state.clear()
                    return
                await db.execute("UPDATE accounts SET telegram_id = ? WHERE username = ?", (user_id, username))
                await db.execute(
                    "INSERT OR IGNORE INTO users (user_id, login_username, balance) VALUES (?, ?, 0)",
                    (user_id, username)
                )
                await db.commit()
                await message.answer("✅ **Login Successful!**", reply_markup=user_kb)
            else:
                await message.answer(
                    f"❌ **Wrong Username or Password!**\n\nIf you need an account, please contact Admin:\n👨‍💻 **{ADMIN_USERNAME}**"
                )
    await state.clear()

# ---------- অ্যাডমিন ----------
@dp.message(F.text == "🔐 Create Account", F.from_user.id == ADMIN_ID)
async def create_acc(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("👤 Enter a new **Username**:")
    await state.set_state(AdminState.acc_user)

@dp.message(F.text == "➕ Add Credit", F.from_user.id == ADMIN_ID)
async def add_cr(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("👤 Enter **Telegram ID** to add credits:")
    await state.set_state(AdminState.add_id)

@dp.message(F.text == "➖ Remove Credit", F.from_user.id == ADMIN_ID)
async def rem_cr(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("👤 Enter **Telegram ID** to remove credits:")
    await state.set_state(AdminState.rem_id)

@dp.message(F.text == "🚫 User Ban", F.from_user.id == ADMIN_ID)
async def ban_u(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("👤 Enter **Telegram ID** to BAN:")
    await state.set_state(AdminState.ban_id)

@dp.message(F.text == "✅ User Unban", F.from_user.id == ADMIN_ID)
async def unban_u(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("👤 Enter **Telegram ID** to UNBAN:")
    await state.set_state(AdminState.unban_id)

@dp.message(F.text == "📣 Broadcast", F.from_user.id == ADMIN_ID)
async def ask_broadcast(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("📢 Send the message you want to broadcast:")
    await state.set_state(AdminState.broadcast_msg)

@dp.message(F.text == "🎟 Create Redeem Code", F.from_user.id == ADMIN_ID)
async def cr_code(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("🎟 Enter **Code Name** (e.g. FREE50):")
    await state.set_state(AdminState.code_name)

@dp.message(F.text == "👥 Total User", F.from_user.id == ADMIN_ID)
async def stats_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cur:
            total_users = await cur.fetchone()
        async with db.execute("SELECT COUNT(*) FROM accounts") as cur:
            total_accounts = await cur.fetchone()
    await message.answer(
        f"📊 **SYSTEM STATS**\n\n"
        f"👥 Logged-in Users: {total_users[0]}\n"
        f"🔐 Created Accounts: {total_accounts[0]}"
    )

@dp.message(AdminState.acc_user)
async def acc_u(message: types.Message, state: FSMContext):
    await state.update_data(u=message.text.strip())
    await message.answer("🔑 Enter **Password**:")
    await state.set_state(AdminState.acc_pass)

@dp.message(AdminState.acc_pass)
async def acc_p(message: types.Message, state: FSMContext):
    data = await state.get_data()
    username = data['u']
    password = message.text.strip()
    async with aiosqlite.connect("bot_database.db") as db:
        try:
            await db.execute("INSERT INTO accounts (username, password) VALUES (?, ?)", (username, password))
            await db.commit()
            await message.answer(f"✅ **Account Created!**\n👤 Username: `{username}`\n🔑 Password: `{password}`", parse_mode="Markdown")
        except aiosqlite.IntegrityError:
            await message.answer("❌ Username already exists!")
    await state.clear()

@dp.message(AdminState.add_id)
async def add_i(message: types.Message, state: FSMContext):
    try:
        user_id = int(message.text.strip())
        await state.update_data(u_id=user_id)
        await message.answer("💰 Enter **Amount**:")
        await state.set_state(AdminState.add_amount)
    except ValueError:
        await message.answer("❌ Invalid Telegram ID. Please enter a number.")
        await state.clear()

@dp.message(AdminState.add_amount)
async def add_a(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data['u_id']
    try:
        amount = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Invalid amount. Please enter a number.")
        await state.clear()
        return
    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cur:
            if not await cur.fetchone():
                await message.answer(f"❌ User ID {user_id} not found.")
                await state.clear()
                return
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()
    await message.answer(f"✅ Added {amount} credits to user {user_id}.")
    await state.clear()

@dp.message(AdminState.rem_id)
async def rem_i(message: types.Message, state: FSMContext):
    try:
        user_id = int(message.text.strip())
        await state.update_data(u_id=user_id)
        await message.answer("💰 Enter **Amount**:")
        await state.set_state(AdminState.rem_amount)
    except ValueError:
        await message.answer("❌ Invalid Telegram ID. Please enter a number.")
        await state.clear()

@dp.message(AdminState.rem_amount)
async def rem_a(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = data['u_id']
    try:
        amount = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Invalid amount.")
        await state.clear()
        return
    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                await message.answer(f"❌ User ID {user_id} not found.")
                await state.clear()
                return
            if row[0] < amount:
                await message.answer(f"❌ User has only {row[0]} credits. Cannot remove {amount}.")
                await state.clear()
                return
        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        await db.commit()
    await message.answer(f"✅ Removed {amount} credits from user {user_id}.")
    await state.clear()

@dp.message(AdminState.ban_id)
async def ban_i(message: types.Message, state: FSMContext):
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Invalid ID.")
        await state.clear()
        return
    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cur:
            if not await cur.fetchone():
                await message.answer(f"❌ User {user_id} not found.")
                await state.clear()
                return
        await db.execute("UPDATE users SET status = 'banned' WHERE user_id = ?", (user_id,))
        await db.commit()
    await message.answer(f"🚫 User {user_id} banned.")
    await state.clear()

@dp.message(AdminState.unban_id)
async def unban_i(message: types.Message, state: FSMContext):
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Invalid ID.")
        await state.clear()
        return
    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cur:
            if not await cur.fetchone():
                await message.answer(f"❌ User {user_id} not found.")
                await state.clear()
                return
        await db.execute("UPDATE users SET status = 'active' WHERE user_id = ?", (user_id,))
        await db.commit()
    await message.answer(f"✅ User {user_id} unbanned.")
    await state.clear()

@dp.message(AdminState.broadcast_msg)
async def bc_msg(message: types.Message, state: FSMContext):
    broadcast_text = message.text
    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT user_id FROM users") as cur:
            rows = await cur.fetchall()
    await message.answer(f"⏳ Broadcasting to {len(rows)} users...")
    success = 0
    for row in rows:
        try:
            await bot.send_message(row[0], f"📢 **Admin Message:**\n\n{broadcast_text}")
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
    await message.answer(f"✅ Sent to {success} users.")
    await state.clear()

@dp.message(AdminState.code_name)
async def c_name(message: types.Message, state: FSMContext):
    await state.update_data(c_name=message.text.strip())
    await message.answer("💰 Enter **Amount**:")
    await state.set_state(AdminState.code_amount)

@dp.message(AdminState.code_amount)
async def c_amt(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        await state.update_data(c_amt=amount)
        await message.answer("👥 How many **Users**? (usages):")
        await state.set_state(AdminState.code_usages)
    except ValueError:
        await message.answer("❌ Invalid amount. Please enter a number.")
        await state.clear()

@dp.message(AdminState.code_usages)
async def c_use(message: types.Message, state: FSMContext):
    data = await state.get_data()
    code = data['c_name']
    amount = data['c_amt']
    try:
        usages = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Invalid number. Please enter a number.")
        await state.clear()
        return
    async with aiosqlite.connect("bot_database.db") as db:
        try:
            await db.execute("INSERT INTO redeem_codes (code, amount, usages) VALUES (?, ?, ?)", (code, amount, usages))
            await db.commit()
            await message.answer(f"✅ **Code Created!** `{code}` with {usages} uses.")
        except aiosqlite.IntegrityError:
            await message.answer(f"❌ Code '{code}' already exists.")
    await state.clear()

# ---------- মেইন ----------
async def main():
    await init_db()
    logging.info("✅ Bot started successfully!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())Bacf_sms_Robi
