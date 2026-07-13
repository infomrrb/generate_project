import asyncio
import logging
import os
import aiosqlite
import aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ================== কনফিগারেশন (এখানে আপনার তথ্য দিন) ==================
# 🚨 নিচের লাইনগুলো আপনার নিজের তথ্য দিয়ে প্রতিস্থাপন করুন

BOT_TOKEN = "8919343304:AAEmHznQk2Q2tlkxNcOgTYDkMZZ5PesoBPw"                     # আপনার বট টোকেন
ADMIN_ID = 1967494059                                # আপনার টেলিগ্রাম ID
ADMIN_USERNAME = "@RobiEntertainment"                # অ্যাডমিন ইউজারনেম (সাপোর্টের জন্য)
DEV_USERNAME = "RobiEntertainment"                   # ডেভেলপারের নাম (প্রোফাইলে দেখাবে)
SMS_API_URL = "http://hakvolution.com/KEY/sub.php?key=&number=&msg="                # SMS API এর URL
SMS_API_KEY = "Bacf_sms_Robi"                # SMS API কী
LOG_CHANNEL = -1001234567890                         # লগ পাঠানোর চ্যানেল ID (integer)
CHANNEL_LINK = "https://t.me/your_channel"           # জয়েন করতে চ্যানেল লিংক
FB_LINK = "https://facebook.com/your_page"           # ফেসবুক পেইজ লিংক
CHANNEL_USERNAME = "@your_channel_username"          # চ্যানেলের ইউজারনেম (@সহ)

# ===================================================================

# লগিং সেটআপ
logging.basicConfig(level=logging.INFO)

# বট ও ডিসপ্যাচার
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ---------- ডেটাবেস ইনিশিয়ালাইজেশন ----------
async def init_db():
    async with aiosqlite.connect("bot_database.db") as db:
        # ইউজার টেবিল
        await db.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            login_username TEXT,
            balance INTEGER DEFAULT 0,
            join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active'
        )""")
        # অ্যাকাউন্ট টেবিল (লগইন তথ্য)
        await db.execute("""CREATE TABLE IF NOT EXISTS accounts (
            username TEXT PRIMARY KEY,
            password TEXT,
            telegram_id INTEGER
        )""")
        # রিডিম কোড টেবিল
        await db.execute("""CREATE TABLE IF NOT EXISTS redeem_codes (
            code TEXT PRIMARY KEY,
            amount INTEGER,
            usages INTEGER
        )""")
        # রিডিম ইতিহাস
        await db.execute("""CREATE TABLE IF NOT EXISTS redeem_history (
            user_id INTEGER,
            code TEXT,
            PRIMARY KEY (user_id, code)
        )""")
        # অ্যাডমিনকে ইউজার টেবিলে যোগ করি (যদি না থাকে)
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, login_username, balance, status) VALUES (?, 'Admin', 9999, 'active')",
            (ADMIN_ID,)
        )
        await db.commit()

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

join_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="📢 Join Channel", url=CHANNEL_LINK)],
        [InlineKeyboardButton(text="👍 Like Facebook Page", url=FB_LINK)],
        [InlineKeyboardButton(text="✅ I Have Joined", callback_data="check_join")]
    ]
)

# ---------- FSM স্টেট ----------
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

# ---------- হেল্পার ফাংশন ----------
async def is_logged_in_and_active(user_id):
    """চেক করে ইউজার লগইন করেছে এবং active কিনা (অ্যাডমিন সবসময় True)"""
    if user_id == ADMIN_ID:
        return True
    async with aiosqlite.connect("bot_database.db") as db:
        async with db.execute("SELECT status FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row and row[0] == 'active':
                return True
    return False

async def is_joined(user_id):
    """চেক করে ইউজার চ্যানেলে জয়েন করেছে কিনা (অ্যাডমিনের জন্য স্কিপ)"""
    if user_id == ADMIN_ID:
        return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        if member.status in ['member', 'administrator', 'creator', 'restricted']:
            return True
    except Exception:
        # কোনো কারণে চেক করতে না পারলে false রিটার্ন করি
        return False
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
                # ইতিমধ্যে লগইন করা ইউজার
                await bot.send_message(chat_id, f"👋 Welcome back {user_first_name}!", reply_markup=user_kb)
                return

    # নতুন ইউজার – লগইন ফর্ম দেখাই
    await bot.send_message(chat_id, "🔒 **Login Required**\n\nPlease enter your **Username**:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(AuthState.wait_username)

# ---------- /start কমান্ড ----------
@dp.message(Command("start"))
async def start_command(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id

    # অ্যাডমিন চেক
    if user_id == ADMIN_ID:
        await message.answer("👑 **Admin Panel**\nWelcome back, Admin!", reply_markup=admin_kb)
        return

    # জয়েন চেক
    if not await is_joined(user_id):
        text = ("⚠️ **Welcome to BNCT SMS BOT!**\n\n"
                "Before using the bot, you must complete the following steps:\n"
                "1️⃣ Join our Telegram Channel.\n"
                "2️⃣ Like our Facebook Page.\n\n"
                "After doing both, click the **'✅ I Have Joined'** button below.")
        await message.answer(text, reply_markup=join_kb)
        return

    await proceed_to_login(user_id, message.from_user.first_name, state)

# ---------- জয়েন চেক কলব্যাক ----------
@dp.callback_query(F.data == "check_join")
async def check_join_callback(call: types.CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    if await is_joined(user_id):
        await call.message.delete()
        await proceed_to_login(user_id, call.from_user.first_name, state)
    else:
        await call.answer("❌ You haven't joined the Telegram channel yet! Please join first.", show_alert=True)

# ---------- /admin কমান্ড ----------
@dp.message(Command("admin"))
async def admin_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    if message.from_user.id == ADMIN_ID:
        await message.answer("👑 **Admin Panel**", reply_markup=admin_kb)

# ---------- ব্যাক বাটন ----------
@dp.message(F.text == "⬅️ Back")
async def back_u(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Switched to User Mode.", reply_markup=user_kb)

# ---------- প্রোফাইল ----------
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

# ---------- এসএমএস পাঠানো ----------
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

    await message.answer("📱 Please enter the **Phone Number** (e.g. 017XXXXXX):")
    await state.set_state(SMSState.waiting_for_number)

@dp.message(SMSState.waiting_for_number)
async def process_number(message: types.Message, state: FSMContext):
    await state.update_data(number=message.text.strip())
    await message.answer("💬 Enter **Message**:")
    await state.set_state(SMSState.waiting_for_message)

@dp.message(SMSState.waiting_for_message)
async def process_message(message: types.Message, state: FSMContext):
    data = await state.get_data()
    number = data['number']
    sms_text = message.text
    user_id = message.from_user.id

    await message.answer(f"⏳ Sending SMS to `{number}`...\n*Please wait...*", parse_mode="Markdown")

    # API কল
    params = {"key": SMS_API_KEY, "number": number, "msg": sms_text}
    success = False
    api_res = "No response"
    log_status = ""

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(SMS_API_URL, params=params) as resp:
                api_res = await resp.text()
                # সাধারণত API সফল হলে 200 এবং error কিংবা invalid শব্দ থাকবে না
                if resp.status == 200 and "error" not in api_res.lower() and "invalid" not in api_res.lower():
                    success = True
    except Exception as e:
        api_res = str(e)

    # ব্যালেন্স আপডেট
    if success:
        async with aiosqlite.connect("bot_database.db") as db:
            # ডাবল চেক যে ব্যালেন্স >= 1
            async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cur:
                bal_row = await cur.fetchone()
                if bal_row and bal_row[0] >= 1:
                    await db.execute("UPDATE users SET balance = balance - 1 WHERE user_id = ?", (user_id,))
                    await db.commit()
                    await message.answer(f"✅ **SMS Sent Successfully!**\n💰 1 Credit deducted.\n\n*(API: {api_res})*", parse_mode="Markdown")
                    log_status = "✅ Success"
                else:
                    await message.answer("❌ Insufficient credits after re-check. Please try again.")
                    log_status = "❌ Failed (insufficient balance)"
                    success = False
    else:
        await message.answer(f"❌ **Failed to send SMS.** No credits deducted.\n\n⚠️ **API Server Error:** `{api_res}`", parse_mode="Markdown")
        log_status = f"❌ Failed\n⚠️ Error: `{api_res}`"

    await state.clear()

    # লগ চ্যানেলে পাঠাই
    log_text = (
        f"📝 **NEW SMS LOG**\n\n"
        f"👤 **Sender ID:** `{user_id}`\n"
        f"📱 **Target Number:** `{number}`\n"
        f"💬 **Message:**\n{sms_text}\n\n"
        f"🚦 **Status:** {log_status}"
    )
    try:
        await bot.send_message(chat_id=LOG_CHANNEL, text=log_text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Failed to send log to channel: {e}")

# ---------- রিডিম কোড ----------
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
        # চেক করি ইতিমধ্যে ব্যবহার করেছে কিনা
        async with db.execute("SELECT 1 FROM redeem_history WHERE user_id = ? AND code = ?", (user_id, code)) as cur:
            if await cur.fetchone():
                await message.answer("❌ You have already used this code.")
                await state.clear()
                return

        # কোড বৈধ কিনা
        async with db.execute("SELECT amount, usages FROM redeem_codes WHERE code = ?", (code,)) as cur:
            row = await cur.fetchone()
            if not row or row[1] <= 0:
                await message.answer("❌ Invalid or Expired Code.")
                await state.clear()
                return

            amount = row[0]
            # ব্যালেন্স যোগ করি
            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
            # ব্যবহার সংখ্যা কমাই
            await db.execute("UPDATE redeem_codes SET usages = usages - 1 WHERE code = ?", (code,))
            # ইতিহাসে যোগ করি
            await db.execute("INSERT INTO redeem_history (user_id, code) VALUES (?, ?)", (user_id, code))
            await db.commit()

    await message.answer(f"🎉 **Code Redeemed!**\n✅ You got +{amount} Credits.")
    await state.clear()

# ---------- রেফারেল ----------
@dp.message(F.text == "👥 Referral")
async def referral_info(message: types.Message, state: FSMContext):
    await state.clear()
    if not await is_logged_in_and_active(message.from_user.id):
        return
    await message.answer(f"👥 **Referral System**\n\nCurrently disabled for Private Mode. Ask your friends to contact Admin ({ADMIN_USERNAME}) for accounts.")

# ---------- সাপোর্ট ----------
@dp.message(F.text == "☎️ Support")
async def support(message: types.Message, state: FSMContext):
    await state.clear()
    if not await is_logged_in_and_active(message.from_user.id):
        return
    await message.answer(f"☎️ **Support**\n\nFor any issues or to buy credits, please message the Admin:\n👨‍💻 **{ADMIN_USERNAME}**")

# ---------- লগইন হ্যান্ডলার ----------
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
                # চেক করি এই অ্যাকাউন্ট অন্য কেউ ব্যবহার করছে কিনা
                if row[1] is not None and row[1] != user_id:
                    await message.answer(f"❌ Account linked to another device.\nContact Admin: {ADMIN_USERNAME}")
                    await state.clear()
                    return
                # আপডেট করি
                await db.execute("UPDATE accounts SET telegram_id = ? WHERE username = ?", (user_id, username))
                # ইউজার টেবিলে যোগ করি (যদি না থাকে)
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

# ---------- অ্যাডমিন কমান্ড ----------
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

# ---------- অ্যাডমিন স্টেট হ্যান্ডলার ----------
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
        # চেক করি ইউজার আছে কিনা
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
            await asyncio.sleep(0.05)  # rate limit
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

# ---------- মেইন ফাংশন ----------
async def main():
    await init_db()
    logging.info("✅ Bot started successfully!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
