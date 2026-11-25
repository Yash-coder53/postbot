import asyncio
import functools
import html
import json
import logging
import os
import re
import time
from datetime import datetime

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand, BotCommandScopeDefault, BotCommandScopeChat
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)

# ================= CONFIG =================
# Numbers must be plain integers (no quotes). Token can also come from env var.
BOT_TOKEN      = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
CHANNEL_ID     = -1001234567890      # main channel id (used by /send, /sendtext)
OWNER_ID       = 123456789           # your Telegram user id
LOGGER_CHAT_ID = -1009876543210      # log group id (set 0 to disable)
POST_IMAGE     = "meet_our_team.jpg"
DATA_FILE      = "user_admins.json"
# ==========================================

POST_TEXT = (
    "🛡️ USER PROTECTOR HUB — MEET OUR TEAM\n\n"
    "Our admins are here to guide you, support you, and keep the community safe.\n\n"
    "Tap any button below to contact the respective admin directly.\n\n"
    "⚠️ Reminder: Our team will never ask for your password, OTP, or payment.\n\n"
    "🛡️ Stay safe. Report responsibly."
)

DEFAULT_ADMINS = [
    {"name": "👑 Admin 1", "username": "admin1_username"},
    {"name": "🛡️ Admin 2", "username": "admin2_username"},
    {"name": "🛡️ Admin 3", "username": "admin3_username"},
    {"name": "🤝 Admin 4", "username": "admin4_username"},
    {"name": "📩 Admin 5", "username": "admin5_username"},
    {"name": "📩 Admin 6", "username": "admin6_username"},
]

# ============ LOGGING ============
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
log = logging.getLogger("Bot")


# ============ PERSISTENCE ============
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        try:
            os.rename(DATA_FILE, f"{DATA_FILE}.corrupt.{int(time.time())}")
        except Exception:
            pass
        log.warning(f"Corrupt data file backed up. Starting fresh. ({e})")
        return {}

    data = {}
    for k, v in raw.items():
        try:
            uid = int(k)
        except (ValueError, TypeError):
            continue
        if isinstance(v, list):
            data[uid] = {"admins": v, "channels": [], "info": {}}
        elif isinstance(v, dict):
            data[uid] = {
                "admins":   v.get("admins", []) or [],
                "channels": v.get("channels", []) or [],
                "info":     v.get("info", {}) or {},
            }
    return data


db = load_data()


def save_data():
    try:
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in db.items()},
                      f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_FILE)
    except Exception as e:
        log.error(f"Save error: {e}")


# ============ HELPERS ============
def ensure_user(user_obj):
    uid = user_obj.id
    changed = False
    if uid not in db:
        db[uid] = {"admins": [], "channels": [], "info": {}}
        changed = True
    info = db[uid]["info"]
    name = user_obj.first_name or ""
    uname = user_obj.username or ""
    if info.get("name") != name or info.get("username") != uname:
        changed = True
    info["name"] = name
    info["username"] = uname
    info["last_seen"] = datetime.now().isoformat()
    if changed:  # don't hit the disk on every single message
        save_data()
    return db[uid]


def user_label(u):
    if not u:
        return "System"
    if u.username:
        return f"{u.first_name} (@{u.username}) [{u.id}]"
    return f"{u.first_name} [{u.id}]"


async def log_to_group(bot, text):
    if not LOGGER_CHAT_ID:
        return
    try:
        await bot.send_message(LOGGER_CHAT_ID, text)
    except Exception as e:
        log.warning(f"Logger group error: {e}")


def get_button_url(admin):
    if admin.get("username"):
        return f"https://t.me/{admin['username'].lstrip('@')}"
    if admin.get("user_id"):
        # NOTE: Telegram often rejects tg://user?id= buttons
        # (BUTTON_USER_PRIVACY_RESTRICTED). Usernames are far more reliable.
        return f"tg://user?id={admin['user_id']}"
    return None


def build_keyboard(admins):
    keyboard, row = [], []
    for a in admins:
        url = get_button_url(a)
        if not url:
            continue
        row.append(InlineKeyboardButton(a["name"], url=url))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard) if keyboard else None


def normalize_chat_ref(text):
    """Turn user input into something get_chat() accepts."""
    s = text.strip()
    m = re.match(r"^(?:https?://)?t\.me/([A-Za-z0-9_]+)/?$", s)
    if m:
        s = "@" + m.group(1)
    if re.fullmatch(r"-?\d+", s):
        return int(s)           # private channel ids must be int, not str
    if not s.startswith("@"):
        s = "@" + s
    return s


async def reply(update: Update, text, **kwargs):
    """Reply to a message OR edit the message of a callback query."""
    if update.callback_query:
        await update.callback_query.edit_message_text(text, **kwargs)
    else:
        await update.effective_message.reply_text(text, **kwargs)


async def send_post_to(bot, chat_id, admins):
    kb = build_keyboard(admins)
    if not kb:
        raise ValueError("No valid buttons — check your admin list")
    if os.path.exists(POST_IMAGE):
        try:
            with open(POST_IMAGE, "rb") as img:
                await bot.send_photo(
                    chat_id=chat_id, photo=img,
                    caption=POST_TEXT, reply_markup=kb,
                )
            return
        except Exception as e:
            log.warning(f"Photo send failed, falling back to text: {e}")
    await bot.send_message(chat_id=chat_id, text=POST_TEXT, reply_markup=kb)


def owner_only(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user:
            return
        if user.id != OWNER_ID:
            try:
                await update.effective_message.reply_text(
                    "🚫 Yeh command sirf bot owner ke liye hai."
                )
            except Exception:
                pass
            await log_to_group(
                context.bot,
                f"⚠️ UNAUTHORIZED attempt\n👤 {user_label(user)}\n"
                f"🔧 Command: {update.effective_message.text if update.effective_message else '?'}"
            )
            return
        return await func(update, context)
    return wrapper


# ============ STATES ============
ASK_NAME, ASK_TARGET, ASK_CHANNEL, ASK_CUSTOM_CONTENT = range(4)


# ============ /start ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    text = (
        f"👋 Namaste {user.first_name}!\n\n"
        "Yeh bot aapko apne admins ke contact buttons banane aur "
        "apne channel par post karne mein madad karta hai.\n\n"
        "📌 Admin Commands:\n"
        "/add — Admin button add\n"
        "/list — Apne admins\n"
        "/preview — Buttons preview\n"
        "/clear — List clear\n\n"
        "📢 Channel Commands:\n"
        "/addchannel — Apna channel add\n"
        "/mychannels — Apne channels\n"
        "/removechannel — Channel remove\n"
        "/post — Admin buttons ke saath post\n"
        "/custom — Bina buttons ke post (Text/Image)\n\n"
        "/cancel — Cancel"
    )
    await update.message.reply_text(text)


# ============ /add flow ============
async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    await update.message.reply_text(
        "➕ Naya admin add karein\n\n"
        "Step 1️⃣ — Admin ka naam bhejein (jaise: 👑 Admin 1)\n"
        "Cancel: /cancel"
    )
    return ASK_NAME


async def add_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_admin_name"] = update.message.text.strip()
    await update.message.reply_text("Step 2️⃣ — Ab username (bina @) ya User ID bhejein:")
    return ASK_TARGET


async def add_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip().lstrip("@")
    name = context.user_data.pop("new_admin_name", None)
    if not name:
        await update.message.reply_text("❌ /add dobara try karein.")
        return ConversationHandler.END

    if not raw:
        await update.message.reply_text("❌ Empty value. /add dobara karein.")
        return ConversationHandler.END

    user = update.effective_user
    udata = ensure_user(user)
    admin = {"name": name}
    if raw.isdigit():
        admin["user_id"] = int(raw)
        display = f"🆔 ID: {raw}"
    elif re.fullmatch(r"[A-Za-z0-9_]{5,32}", raw):
        admin["username"] = raw
        display = f"@{raw}"
    else:
        await update.message.reply_text(
            "❌ Invalid username. Sirf letters, numbers, _ (5-32 chars). /add dobara karein."
        )
        return ConversationHandler.END
    udata["admins"].append(admin)
    save_data()

    extra = "\n\n⚠️ ID wale buttons kabhi kabhi Telegram reject kar deta hai, username best hai." \
        if "user_id" in admin else ""
    await update.message.reply_text(
        f"✅ Admin add ho gaya!\n\n👤 Name: {name}\n🔗 Target: {display}\n"
        f"📊 Total: {len(udata['admins'])}{extra}"
    )
    await log_to_group(
        context.bot,
        f"➕ Admin added\n👤 {user_label(user)}\n🔗 {name} → {display}\n📊 Total: {len(udata['admins'])}"
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("new_admin_name", None)
    context.user_data.pop("custom_channel", None)
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


# ============ /list /preview /clear ============
async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    udata = ensure_user(update.effective_user)
    admins = udata["admins"]
    if not admins:
        await update.message.reply_text("❌ List khaali hai. /add se add karein.")
        return
    lines = ["📋 Aapke Admins:\n"]
    for i, a in enumerate(admins, 1):
        tgt = f"@{a['username']}" if a.get("username") else f"ID: {a.get('user_id', '?')}"
        lines.append(f"{i}. {a['name']} — {tgt}")
    await update.message.reply_text("\n".join(lines))


async def preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    udata = ensure_user(update.effective_user)
    if not udata["admins"]:
        await update.message.reply_text("❌ Koi admin nahi. Pehle /add.")
        return
    kb = build_keyboard(udata["admins"])
    if not kb:
        await update.message.reply_text("❌ Valid buttons nahi bane.")
        return
    try:
        await update.message.reply_text("🛡️ Preview:", reply_markup=kb)
    except Exception as e:
        await update.message.reply_text(f"❌ Preview failed: {e}")


async def clear_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    udata = ensure_user(user)
    udata["admins"] = []
    save_data()
    await update.message.reply_text("🗑️ Admins clear ho gaye.")
    await log_to_group(context.bot, f"🗑️ Admins cleared\n👤 {user_label(user)}")


# ============ /addchannel flow ============
async def addchannel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    if context.args:
        return await addchannel_process(update, context, " ".join(context.args))
    await update.message.reply_text(
        "📢 Apna channel add karein\n\n"
        "Bhejein:\n"
        "• @yourchannelusername (public), ya\n"
        "• -1001234567890 (private channel ID)\n\n"
        "⚠️ Bot ko pehle channel ka admin banayein (post permission ke saath).\n"
        "Cancel: /cancel"
    )
    return ASK_CHANNEL


async def addchannel_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await addchannel_process(update, context, update.message.text.strip())


async def addchannel_process(update, context, channel_input):
    user = update.effective_user
    udata = ensure_user(user)
    msg = update.effective_message

    if not channel_input:
        await msg.reply_text("❌ Empty value.")
        return ConversationHandler.END

    ref = normalize_chat_ref(channel_input)

    try:
        chat = await context.bot.get_chat(ref)
    except Exception as e:
        await msg.reply_text(f"❌ Channel nahi mila / verify fail:\n{e}")
        return ConversationHandler.END

    if chat.type != "channel":
        await msg.reply_text("❌ Sirf channels add kar sakte hain (groups nahi).")
        return ConversationHandler.END

    try:
        bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
        if bot_member.status not in ("administrator", "creator"):
            await msg.reply_text(
                "❌ Bot is channel ka admin nahi hai.\nPehle bot ko channel mein add + admin banayein."
            )
            return ConversationHandler.END
        if bot_member.status == "administrator" and getattr(bot_member, "can_post_messages", True) is False:
            await msg.reply_text("❌ Bot ke paas 'Post Messages' permission nahi hai.")
            return ConversationHandler.END

        # SECURITY: make sure the person adding the channel really is its admin,
        # otherwise anyone could post into other people's channels.
        if user.id != OWNER_ID:
            user_member = await context.bot.get_chat_member(chat.id, user.id)
            if user_member.status not in ("administrator", "creator"):
                await msg.reply_text("🚫 Aap is channel ke admin nahi hain.")
                return ConversationHandler.END
    except Exception as e:
        await msg.reply_text(f"❌ Permission check fail:\n{e}")
        return ConversationHandler.END

    if any(c["id"] == chat.id for c in udata["channels"]):
        await msg.reply_text("⚠️ Yeh channel already added hai.")
        return ConversationHandler.END

    udata["channels"].append({"id": chat.id, "username": chat.username, "title": chat.title})
    save_data()

    await msg.reply_text(
        f"✅ Channel added!\n\n📢 {html.escape(chat.title or '')}\n🆔 <code>{chat.id}</code>\n\n"
        "Ab /post ya /custom se post karein.",
        parse_mode="HTML"
    )
    await log_to_group(context.bot, f"📢 Channel added\n👤 {user_label(user)}\n📢 {chat.title} ({chat.id})")
    return ConversationHandler.END


# ============ /mychannels /removechannel ============
async def mychannels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    udata = ensure_user(update.effective_user)
    chans = udata["channels"]
    if not chans:
        await update.message.reply_text("❌ Koi channel nahi. /addchannel se add karein.")
        return
    lines = ["📢 Aapke Channels:\n"]
    for i, c in enumerate(chans, 1):
        uname = f"@{c['username']}" if c.get("username") else f"{c['id']}"
        lines.append(f"{i}. {html.escape(c['title'] or '')} — {html.escape(uname)}")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def removechannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    udata = ensure_user(update.effective_user)
    if not udata["channels"]:
        await update.message.reply_text("❌ Koi channel nahi.")
        return
    buttons = [[InlineKeyboardButton(f"❌ {c['title']}", callback_data=f"rmch_{c['id']}")]
               for c in udata["channels"]]
    await update.message.reply_text("Kis channel ko remove karna hai?",
                                    reply_markup=InlineKeyboardMarkup(buttons))


async def removechannel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        cid = int(q.data.replace("rmch_", ""))
    except ValueError:
        return await q.edit_message_text("❌ Invalid data.")

    udata = ensure_user(q.from_user)
    udata["channels"] = [c for c in udata["channels"] if c["id"] != cid]
    save_data()
    await q.edit_message_text("✅ Channel remove ho gaya (agar tha).")
    await log_to_group(context.bot, f"🗑️ Channel removed\n👤 {user_label(q.from_user)}\n📢 ID: {cid}")


# ============ /post (WITH BUTTONS) ============
async def post_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    udata = ensure_user(user)
    if not udata["admins"]:
        return await update.message.reply_text("❌ Pehle /add se admin add karein.")
    if not udata["channels"]:
        return await update.message.reply_text("❌ Pehle /addchannel se channel add karein.")

    if context.args:
        target = " ".join(context.args).lstrip("@")
        for c in udata["channels"]:
            if str(c["id"]) == target or (c.get("username") and c["username"].lower() == target.lower()):
                return await do_post(update, context, c)
        return await update.message.reply_text("❌ Channel nahi mila. /mychannels dekhein.")

    if len(udata["channels"]) == 1:
        return await do_post(update, context, udata["channels"][0])

    buttons = [[InlineKeyboardButton(f"📢 {c['title']}", callback_data=f"postch_{c['id']}")]
               for c in udata["channels"]]
    await update.message.reply_text("Kis channel par post karna hai?",
                                    reply_markup=InlineKeyboardMarkup(buttons))


async def do_post(update, context, channel):
    user = update.effective_user
    udata = ensure_user(user)

    try:
        await send_post_to(context.bot, channel["id"], udata["admins"])
        await reply(update, f"✅ Post bhej diya!\n📢 {channel['title']}\n🔢 {len(udata['admins'])} buttons")
        await log_to_group(
            context.bot,
            f"📤 Post sent\n👤 {user_label(user)}\n📢 {channel['title']}\n🔢 {len(udata['admins'])} buttons"
        )
    except Exception as e:
        await reply(update, f"❌ Post failed: {e}")
        await log_to_group(context.bot, f"❌ Post failed\n👤 {user_label(user)}\n⚠️ {e}")


async def post_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        cid = int(q.data.replace("postch_", ""))
    except ValueError:
        return await q.edit_message_text("❌ Invalid data.")

    udata = ensure_user(q.from_user)
    channel = next((c for c in udata["channels"] if c["id"] == cid), None)
    if not channel:
        return await q.edit_message_text("❌ Channel nahi mila.")
    if not udata["admins"]:
        return await q.edit_message_text("❌ Pehle /add se admin add karein.")
    await do_post(update, context, channel)


# ============ /custom (WITHOUT BUTTONS) ============
CUSTOM_PROMPT = (
    "Ab apna post content bhejein:\n"
    "• Simple Text\n"
    "• Only Image\n"
    "• Image + Text (caption)\n\n"
    "Cancel: /cancel"
)


async def custom_post_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    udata = ensure_user(user)
    if not udata["channels"]:
        await update.message.reply_text("❌ Pehle /addchannel se channel add karein.")
        return ConversationHandler.END

    if len(udata["channels"]) == 1:
        ch = udata["channels"][0]
        context.user_data["custom_channel"] = ch
        await update.message.reply_text(
            f"📢 Channel selected: <b>{html.escape(ch['title'] or '')}</b>\n\n{CUSTOM_PROMPT}",
            parse_mode="HTML"
        )
        return ASK_CUSTOM_CONTENT

    context.user_data.pop("custom_channel", None)
    buttons = [[InlineKeyboardButton(f"📢 {c['title']}", callback_data=f"customch_{c['id']}")]
               for c in udata["channels"]]
    await update.message.reply_text("Kis channel par post karna hai?",
                                    reply_markup=InlineKeyboardMarkup(buttons))
    return ASK_CUSTOM_CONTENT


async def custom_channel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        cid = int(q.data.replace("customch_", ""))
    except ValueError:
        await q.edit_message_text("❌ Invalid data.")
        return ConversationHandler.END

    udata = ensure_user(q.from_user)
    channel = next((c for c in udata["channels"] if c["id"] == cid), None)
    if not channel:
        await q.edit_message_text("❌ Channel nahi mila.")
        return ConversationHandler.END

    context.user_data["custom_channel"] = channel
    await q.edit_message_text(
        f"📢 Channel selected: <b>{html.escape(channel['title'] or '')}</b>\n\n{CUSTOM_PROMPT}",
        parse_mode="HTML"
    )
    return ASK_CUSTOM_CONTENT


async def receive_custom_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel = context.user_data.get("custom_channel")
    msg = update.message
    if not channel:
        await msg.reply_text("⚠️ Pehle upar se channel select karein (button dabayein).")
        return ASK_CUSTOM_CONTENT

    user = update.effective_user
    try:
        if msg.photo:
            await context.bot.send_photo(chat_id=channel["id"], photo=msg.photo[-1].file_id,
                                         caption=msg.caption or None)
        elif msg.document and (msg.document.mime_type or "").startswith("image/"):
            await context.bot.send_document(chat_id=channel["id"], document=msg.document.file_id,
                                            caption=msg.caption or None)
        elif msg.text:
            await context.bot.send_message(chat_id=channel["id"], text=msg.text)
        else:
            await msg.reply_text("❌ Sirf Text ya Image bhejein.")
            return ASK_CUSTOM_CONTENT

        await msg.reply_text(f"✅ Post bina buttons ke bhej diya gaya!\n📢 {channel['title']}")
        await log_to_group(
            context.bot,
            f"📤 Custom Post (No Buttons)\n👤 {user_label(user)}\n📢 {channel['title']} ({channel['id']})"
        )
    except Exception as e:
        await msg.reply_text(f"❌ Post failed: {e}")
        await log_to_group(context.bot, f"❌ Custom Post failed\n👤 {user_label(user)}\n⚠️ {e}")

    context.user_data.pop("custom_channel", None)
    return ConversationHandler.END


async def custom_wrong_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Sirf Text ya Image bhejein (ya /cancel).")
    return ASK_CUSTOM_CONTENT


# ============ OWNER-ONLY ============
@owner_only
async def seed_defaults(update: Update, context: ContextTypes.DEFAULT_TYPE):
    udata = ensure_user(update.effective_user)
    existing = {a.get("username") for a in udata["admins"]}
    added = [a for a in DEFAULT_ADMINS if a["username"] not in existing]
    udata["admins"].extend(dict(a) for a in added)
    save_data()
    await update.message.reply_text(f"✅ {len(added)} default admins load ho gaye.")
    await log_to_group(context.bot, f"🌱 Default admins seeded\n👤 {user_label(update.effective_user)}")


@owner_only
async def send_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    udata = ensure_user(update.effective_user)
    if not udata["admins"]:
        return await update.message.reply_text("❌ Pehle /add ya /seed karein.")
    try:
        await send_post_to(context.bot, CHANNEL_ID, udata["admins"])
        await update.message.reply_text("✅ MAIN channel par post bhej diya!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


@owner_only
async def sendtext_only(update: Update, context: ContextTypes.DEFAULT_TYPE):
    udata = ensure_user(update.effective_user)
    kb = build_keyboard(udata["admins"]) if udata["admins"] else None
    if not kb:
        return await update.message.reply_text("❌ Pehle /add ya /seed.")
    try:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=POST_TEXT, reply_markup=kb)
        await update.message.reply_text("✅ Text post bhej diya!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


@owner_only
async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db:
        return await update.message.reply_text("❌ Koi user nahi.")
    lines = [f"👥 Total Users: {len(db)}\n"]
    for uid, d in db.items():
        info = d.get("info", {})
        lines.append(
            f"• {html.escape(info.get('name', '?'))} [<code>{uid}</code>]\n"
            f"   → {len(d.get('admins', []))} admins, {len(d.get('channels', []))} channels"
        )
        if len(lines) > 40:
            lines.append("... (truncated)")
            break
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


@owner_only
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        return await update.message.reply_text("Usage: /broadcast <message>")
    msg = " ".join(context.args)
    sent = failed = 0
    for uid in list(db.keys()):
        try:
            await context.bot.send_message(uid, msg)
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # stay under Telegram's flood limits
    await update.message.reply_text(f"📤 Broadcast: ✅ {sent} | ❌ {failed}")


# ============ HEALTH CHECK ============
async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏓 Pong! Bot alive hai.")


async def cancel_idle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ℹ️ Cancel karne ke liye kuch active nahi hai.")


# ============ ERROR HANDLER ============
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    err = context.error
    log.error(f"Exception: {type(err).__name__}: {err}", exc_info=err)
    try:
        await log_to_group(context.bot, f"❌ BOT ERROR\n⚠️ {type(err).__name__}: {err}")
    except Exception:
        pass


# ============ POST-INIT ============
async def post_init(app: Application):
    default_cmds = [
        BotCommand("start", "Bot start karein"),
        BotCommand("add", "Admin button add"),
        BotCommand("list", "Apne admins"),
        BotCommand("preview", "Button preview"),
        BotCommand("clear", "List clear"),
        BotCommand("addchannel", "Apna channel add"),
        BotCommand("mychannels", "Apne channels"),
        BotCommand("removechannel", "Channel remove"),
        BotCommand("post", "Admin buttons ke saath post"),
        BotCommand("custom", "Bina buttons ke post"),
        BotCommand("cancel", "Cancel"),
        BotCommand("ping", "Health check"),
    ]
    owner_cmds = default_cmds + [
        BotCommand("seed", "Default admins load"),
        BotCommand("send", "Main channel par post"),
        BotCommand("sendtext", "Main channel text post"),
        BotCommand("users", "Sabhi users"),
        BotCommand("broadcast", "Broadcast message"),
    ]
    try:
        await app.bot.set_my_commands(default_cmds, scope=BotCommandScopeDefault())
        await app.bot.set_my_commands(owner_cmds, scope=BotCommandScopeChat(chat_id=OWNER_ID))
        log.info("✅ Commands set successfully")
    except Exception as e:
        log.warning(f"Command setup error: {e}")


# ============ MAIN ============
def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN":
        print("❌ BOT_TOKEN set karo!")
        return
    if not OWNER_ID:
        print("❌ OWNER_ID set karo!")
        return

    # Fix for newer Python versions (3.12+/3.14) where no default event loop exists
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    try:
        app = (
            Application.builder()
            .token(BOT_TOKEN)
            .connect_timeout(30)
            .read_timeout(30)
            .write_timeout(30)
            .pool_timeout(30)
            .post_init(post_init)
            .build()
        )
    except Exception as e:
        print(f"❌ Bot init failed: {e}")
        return

    text_only = filters.TEXT & ~filters.COMMAND

    add_conv = ConversationHandler(
        entry_points=[CommandHandler("add", add_start)],
        states={
            ASK_NAME:   [MessageHandler(text_only, add_name)],
            ASK_TARGET: [MessageHandler(text_only, add_target)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    addch_conv = ConversationHandler(
        entry_points=[CommandHandler("addchannel", addchannel_start)],
        states={
            ASK_CHANNEL: [MessageHandler(text_only, addchannel_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    custom_conv = ConversationHandler(
        entry_points=[CommandHandler("custom", custom_post_start)],
        states={
            ASK_CUSTOM_CONTENT: [
                # channel picker buttons (must live INSIDE the state, not only as entry point)
                CallbackQueryHandler(custom_channel_callback, pattern=r"^customch_"),
                # real content. /commands are excluded so /cancel isn't posted to the channel
                MessageHandler(filters.PHOTO | filters.Document.IMAGE | text_only, receive_custom_content),
                MessageHandler(filters.ALL & ~filters.COMMAND, custom_wrong_input),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Conversations first
    app.add_handler(add_conv)
    app.add_handler(addch_conv)
    app.add_handler(custom_conv)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ping", ping))
    app.add_handler(CommandHandler("list", list_admins))
    app.add_handler(CommandHandler("preview", preview))
    app.add_handler(CommandHandler("clear", clear_admins))
    app.add_handler(CommandHandler("mychannels", mychannels))
    app.add_handler(CommandHandler("removechannel", removechannel))
    app.add_handler(CommandHandler("post", post_command))
    app.add_handler(CommandHandler("cancel", cancel_idle))

    app.add_handler(CommandHandler("seed", seed_defaults))
    app.add_handler(CommandHandler("send", send_post))
    app.add_handler(CommandHandler("sendtext", sendtext_only))
    app.add_handler(CommandHandler("users", list_users))
    app.add_handler(CommandHandler("broadcast", broadcast))

    app.add_handler(CallbackQueryHandler(post_callback, pattern=r"^postch_"))
    app.add_handler(CallbackQueryHandler(removechannel_callback, pattern=r"^rmch_"))

    app.add_error_handler(error_handler)

    print("✅ Bot starting successfully... Press Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
