from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand, BotCommandScopeDefault, BotCommandScopeChat
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)
import json
import os
from datetime import datetime

# ================= CONFIG =================
BOT_TOKEN      = "YOUR_BOT_TOKEN"
CHANNEL_ID     = "your_channel_username"
OWNER_ID       = owner_id
LOGGER_CHAT_ID = your_logger_chat_id
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

# ============ PERSISTENCE (auto-migration) ============
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return {}
    data = {}
    for k, v in raw.items():
        try:
            uid = int(k)
        except ValueError:
            continue
        if isinstance(v, list):            # v1 format
            data[uid] = {"admins": v, "channels": [], "info": {}}
        elif isinstance(v, dict):          # v2/v3 format
            data[uid] = {
                "admins":   v.get("admins", []),
                "channels": v.get("channels", []),
                "info":     v.get("info", {}),
            }
    return data

def save_data():
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in user_data.items()},
                      f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Save error: {e}")

user_data = load_data()

# ============ HELPERS ============
def ensure_user(user_obj):
    uid = user_obj.id
    if uid not in user_data:
        user_data[uid] = {"admins": [], "channels": [], "info": {}}
    user_data[uid]["info"] = {
        "name": user_obj.first_name or "",
        "username": user_obj.username or "",
        "last_seen": datetime.now().isoformat(),
    }
    save_data()
    return user_data[uid]

def user_label(u):
    if not u: return "System"
    if u.username: return f"{u.first_name} (@{u.username}) [{u.id}]"
    return f"{u.first_name} [{u.id}]"

async def log(bot, text):
    if not LOGGER_CHAT_ID: return
    try:
        await bot.send_message(LOGGER_CHAT_ID, text)
    except Exception as e:
        print(f"Log error: {e}")

def get_button_url(admin):
    if admin.get("username"): return f"https://t.me/{admin['username'].lstrip('@')}"
    if admin.get("user_id"):  return f"tg://user?id={admin['user_id']}"
    return None

def build_keyboard(admins):
    keyboard, row = [], []
    for a in admins:
        url = get_button_url(a)
        if not url: continue
        row.append(InlineKeyboardButton(a["name"], url=url))
        if len(row) == 2:
            keyboard.append(row); row = []
    if row: keyboard.append(row)
    return InlineKeyboardMarkup(keyboard) if keyboard else None

async def send_post_to(bot, chat_id, admins):
    kb = build_keyboard(admins)
    if not kb:
        raise ValueError("No valid buttons")
    if os.path.exists(POST_IMAGE):
        with open(POST_IMAGE, "rb") as img:
            await bot.send_photo(chat_id=chat_id, photo=img,
                                 caption=POST_TEXT, reply_markup=kb)
    else:
        await bot.send_message(chat_id=chat_id, text=POST_TEXT, reply_markup=kb)

# ============ DECORATOR ============
def owner_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id != OWNER_ID:
            await update.message.reply_text("🚫 Yeh command sirf bot owner ke liye hai.")
            await log(context.bot,
                      f"⚠️ UNAUTHORIZED attempt\n👤 {user_label(user)}\n"
                      f"🔧 Command: {update.message.text}")
            return
        return await func(update, context)
    return wrapper

# ============ STATES ============
ASK_NAME, ASK_TARGET, ASK_CHANNEL = range(3)

# ============ /start ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)
    await log(context.bot, f"👋 /start\n👤 {user_label(user)}")
    text = (
        f"👋 Namaste {user.first_name}!\n\n"
        "Yeh bot aapko apne admins ke contact buttons banane aur "
        "apne channel par post karne mein madad karta hai.\n\n"
        "📌 Admin Commands:\n"
        "/add — Naya admin button add karein\n"
        "/list — Apne admins dekhein\n"
        "/preview — Buttons preview\n"
        "/clear — List clear karein\n\n"
        "📢 Channel Commands:\n"
        "/addchannel — Apna channel add karein\n"
        "/mychannels — Apne channels dekhein\n"
        "/removechannel — Channel remove karein\n"
        "/post — Channel par post bhejein\n\n"
        "/cancel — Cancel karein"
    )
    await update.message.reply_text(text)

# ============ /add ============
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
    await update.message.reply_text(
        "Step 2️⃣ — Ab username (bina @) ya User ID bhejein:"
    )
    return ASK_TARGET

async def add_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip().lstrip("@")
    name = context.user_data.pop("new_admin_name", None)
    if not name:
        await update.message.reply_text("❌ /add dobara try karein.")
        return ConversationHandler.END

    user = update.effective_user
    udata = ensure_user(user)
    admin = {"name": name}
    if raw.isdigit():
        admin["user_id"] = int(raw);  display = f"🆔 ID: {raw}"
    else:
        admin["username"] = raw;      display = f"@{raw}"
    udata["admins"].append(admin); save_data()

    await update.message.reply_text(
        f"✅ Admin add ho gaya!\n\n👤 Name: {name}\n🔗 Target: {display}\n"
        f"📊 Total: {len(udata['admins'])}"
    )
    await log(context.bot,
              f"➕ Admin added\n👤 {user_label(user)}\n"
              f"🔗 {name} → {display}\n📊 Total: {len(udata['admins'])}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("new_admin_name", None)
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END

# ============ /list / /preview / /clear ============
async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    udata = ensure_user(update.effective_user)
    admins = udata["admins"]
    if not admins:
        await update.message.reply_text("❌ List khaali hai. /add se add karein.")
        return
    lines = ["📋 Aapke Admins:\n"]
    for i, a in enumerate(admins, 1):
        tgt = f"@{a['username']}" if a.get("username") else f"ID: {a['user_id']}"
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
    await update.message.reply_text("🛡️ Preview:", reply_markup=kb)

async def clear_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    udata = ensure_user(user)
    udata["admins"] = []
    save_data()
    await update.message.reply_text("🗑️ Admins clear ho gaye.")
    await log(context.bot, f"🗑️ Admins cleared\n👤 {user_label(user)}")

# ============ /addchannel ============
async def addchannel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_user(update.effective_user)
    if context.args:
        return await addchannel_process(update, context, " ".join(context.args))
    await update.message.reply_text(
        "📢 Apna channel add karein\n\n"
        "Bhejein:\n"
        "• `@yourchannelusername` (public), ya\n"
        "• `-1001234567890` (private channel ID)\n\n"
        "⚠️ Bot ko pehle channel ka **admin** banayein.\n"
        "Cancel: /cancel",
        parse_mode="Markdown"
    )
    return ASK_CHANNEL

async def addchannel_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await addchannel_process(update, context, update.message.text.strip())

async def addchannel_process(update, context, channel_input):
    user = update.effective_user
    udata = ensure_user(user)
    try:
        bot_member = await context.bot.get_chat_member(channel_input, context.bot.id)
        if bot_member.status not in ("administrator", "creator"):
            await update.message.reply_text(
                "❌ Bot is channel ka **admin** nahi hai.\n"
                "Pehle bot ko channel mein add + admin banayein.",
                parse_mode="Markdown"
            )
            await log(context.bot,
                      f"❌ Channel add failed (not admin)\n"
                      f"👤 {user_label(user)}\n📢 {channel_input}")
            return ConversationHandler.END
        chat = await context.bot.get_chat(channel_input)
    except Exception as e:
        await update.message.reply_text(f"❌ Channel verify fail:\n{e}")
        await log(context.bot,
                  f"❌ Channel add error\n👤 {user_label(user)}\n"
                  f"📢 {channel_input}\n⚠️ {e}")
        return ConversationHandler.END

    if chat.type != "channel":
        await update.message.reply_text("❌ Sirf channels add kar sakte hain (groups nahi).")
        return ConversationHandler.END

    if any(c["id"] == chat.id for c in udata["channels"]):
        await update.message.reply_text("⚠️ Yeh channel already added hai.")
        return ConversationHandler.END

    udata["channels"].append({
        "id": chat.id, "username": chat.username, "title": chat.title
    })
    save_data()
    await update.message.reply_text(
        f"✅ Channel added!\n\n📢 {chat.title}\n🆔 `{chat.id}`\n\n"
        f"Ab /post se yahan post kar sakte hain.",
        parse_mode="Markdown"
    )
    await log(context.bot,
              f"📢 Channel added\n👤 {user_label(user)}\n"
              f"📢 {chat.title} (`{chat.id}`)")
    return ConversationHandler.END

# ============ /mychannels / /removechannel ============
async def mychannels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    udata = ensure_user(update.effective_user)
    chans = udata["channels"]
    if not chans:
        await update.message.reply_text("❌ Koi channel nahi. /addchannel se add karein.")
        return
    lines = ["📢 Aapke Channels:\n"]
    for i, c in enumerate(chans, 1):
        uname = f"@{c['username']}" if c.get("username") else f"`{c['id']}`"
        lines.append(f"{i}. {c['title']} — {uname}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def removechannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    udata = ensure_user(update.effective_user)
    if not udata["channels"]:
        await update.message.reply_text("❌ Koi channel nahi.")
        return
    buttons = [[InlineKeyboardButton(f"❌ {c['title']}", callback_data=f"rmch_{c['id']}")]
               for c in udata["channels"]]
    await update.message.reply_text(
        "Kis channel ko remove karna hai?",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def removechannel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not q.data.startswith("rmch_"): return
    cid = int(q.data.replace("rmch_", ""))
    user = q.from_user
    udata = ensure_user(user)
    before = len(udata["channels"])
    udata["channels"] = [c for c in udata["channels"] if c["id"] != cid]
    save_data()
    if len(udata["channels"]) < before:
        await q.edit_message_text("✅ Channel remove ho gaya.")
        await log(context.bot,
                  f"🗑️ Channel removed\n👤 {user_label(user)}\n📢 ID: {cid}")
    else:
        await q.edit_message_text("⚠️ Channel nahi mila.")

# ============ /post (users' own channels) ============
async def post_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    udata = ensure_user(user)
    if not udata["admins"]:
        await update.message.reply_text("❌ Pehle /add se admin add karein.")
        return
    if not udata["channels"]:
        await update.message.reply_text("❌ Pehle /addchannel se channel add karein.")
        return
    if context.args:
        target = " ".join(context.args).lstrip("@")
        for c in udata["channels"]:
            if str(c["id"]) == target or \
               (c.get("username") and c["username"].lower() == target.lower()):
                return await do_post(update, context, c)
        await update.message.reply_text("❌ Channel nahi mila. /mychannels dekhein.")
        return
    if len(udata["channels"]) == 1:
        return await do_post(update, context, udata["channels"][0])
    buttons = [[InlineKeyboardButton(f"📢 {c['title']}", callback_data=f"postch_{c['id']}")]
               for c in udata["channels"]]
    await update.message.reply_text(
        "Kis channel par post karna hai?",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def do_post(update, context, channel):
    user = update.effective_user
    udata = ensure_user(user)
    try:
        await send_post_to(context.bot, channel["id"], udata["admins"])
        msg = f"✅ Post bhej diya!\n📢 {channel['title']}\n🔢 {len(udata['admins'])} buttons"
        if update.callback_query:
            await update.callback_query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        await log(context.bot,
                  f"📤 Post sent\n👤 {user_label(user)}\n"
                  f"📢 {channel['title']} (`{channel['id']}`)\n"
                  f"🔢 {len(udata['admins'])} buttons")
    except Exception as e:
        msg = f"❌ Post failed: {e}"
        if update.callback_query:
            await update.callback_query.edit_message_text(msg)
        else:
            await update.message.reply_text(msg)
        await log(context.bot,
                  f"❌ Post failed\n👤 {user_label(user)}\n"
                  f"📢 {channel.get('title')}\n⚠️ {e}")

async def post_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not q.data.startswith("postch_"): return
    cid = int(q.data.replace("postch_", ""))
    udata = ensure_user(q.from_user)
    channel = next((c for c in udata["channels"] if c["id"] == cid), None)
    if not channel:
        await q.edit_message_text("❌ Channel nahi mila.")
        return
    await do_post(update, context, channel)

# ============ OWNER-ONLY ============
@owner_only
async def seed_defaults(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    udata = ensure_user(user)
    udata["admins"].extend(DEFAULT_ADMINS)
    save_data()
    await update.message.reply_text(f"✅ {len(DEFAULT_ADMINS)} default admins load ho gaye.")
    await log(context.bot, f"🌱 Default admins seeded\n👤 {user_label(user)}")

@owner_only
async def send_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    udata = ensure_user(user)
    if not udata["admins"]:
        await update.message.reply_text("❌ Pehle /add ya /seed karein.")
        return
    try:
        await send_post_to(context.bot, CHANNEL_ID, udata["admins"])
        await update.message.reply_text("✅ MAIN channel par post bhej diya!")
        await log(context.bot,
                  f"📤 Owner → MAIN\n👤 {user_label(user)}\n"
                  f"📢 {CHANNEL_ID}\n🔢 {len(udata['admins'])} buttons")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        await log(context.bot, f"❌ Owner send failed\n⚠️ {e}")

@owner_only
async def sendtext_only(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    udata = ensure_user(user)
    kb = build_keyboard(udata["admins"]) if udata["admins"] else None
    if not kb:
        await update.message.reply_text("❌ Pehle /add ya /seed.")
        return
    try:
        await context.bot.send_message(chat_id=CHANNEL_ID, text=POST_TEXT, reply_markup=kb)
        await update.message.reply_text("✅ Text post bhej diya!")
        await log(context.bot, f"📤 Owner text-posted\n👤 {user_label(user)}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

@owner_only
async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not user_data:
        await update.message.reply_text("❌ Koi user nahi.")
        return
    lines = [f"👥 Total Users: {len(user_data)}\n"]
    for uid, d in user_data.items():
        info = d.get("info", {})
        name = info.get("name", "?")
        uname = f"@{info['username']}" if info.get("username") else "no-username"
        lines.append(
            f"• {name} ({uname}) [{uid}]\n"
            f"   → {len(d.get('admins', []))} admins, {len(d.get('channels', []))} channels"
        )
        if len(lines) > 40:
            lines.append("... (truncated)"); break
    await update.message.reply_text("\n".join(lines))

@owner_only
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    msg = " ".join(context.args)
    sent = failed = 0
    for uid in list(user_data.keys()):
        try:
            await context.bot.send_message(uid, msg); sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text(f"📤 Broadcast: ✅ {sent} | ❌ {failed}")
    await log(context.bot, f"📢 Broadcast by owner\n✅ {sent} | ❌ {failed}")

# ============ POST-INIT: command scoping ============
async def post_init(app: Application):
    default_cmds = [
        BotCommand("start", "Bot start karein"),
        BotCommand("add", "Admin button add karein"),
        BotCommand("list", "Apne admins dekhein"),
        BotCommand("preview", "Button preview"),
        BotCommand("clear", "List clear karein"),
        BotCommand("addchannel", "Apna channel add karein"),
        BotCommand("mychannels", "Apne channels dekhein"),
        BotCommand("removechannel", "Channel remove karein"),
        BotCommand("post", "Channel par post bhejein"),
        BotCommand("cancel", "Cancel"),
    ]
    owner_cmds = default_cmds + [
        BotCommand("seed", "Default admins load"),
        BotCommand("send", "Main channel par post"),
        BotCommand("sendtext", "Main channel text post"),
        BotCommand("users", "Sabhi users dekhein"),
        BotCommand("broadcast", "Broadcast message"),
    ]
    try:
        await app.bot.set_my_commands(default_cmds, scope=BotCommandScopeDefault())
        await app.bot.set_my_commands(owner_cmds, scope=BotCommandScopeChat(chat_id=OWNER_ID))
        print("✅ Commands set (default + owner scope)")
    except Exception as e:
        print(f"❌ Command setup error: {e}")

# ============ MAIN ============
def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    add_conv = ConversationHandler(
        entry_points=[CommandHandler("add", add_start)],
        states={
            ASK_NAME:   [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name)],
            ASK_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_target)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    addch_conv = ConversationHandler(
        entry_points=[CommandHandler("addchannel", addchannel_start)],
        states={
            ASK_CHANNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, addchannel_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # User handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(add_conv)
    app.add_handler(addch_conv)
    app.add_handler(CommandHandler("list", list_admins))
    app.add_handler(CommandHandler("preview", preview))
    app.add_handler(CommandHandler("clear", clear_admins))
    app.add_handler(CommandHandler("mychannels", mychannels))
    app.add_handler(CommandHandler("removechannel", removechannel))
    app.add_handler(CommandHandler("post", post_command))

    # Owner handlers
    app.add_handler(CommandHandler("seed", seed_defaults))
    app.add_handler(CommandHandler("send", send_post))
    app.add_handler(CommandHandler("sendtext", sendtext_only))
    app.add_handler(CommandHandler("users", list_users))
    app.add_handler(CommandHandler("broadcast", broadcast))

    # Callbacks
    app.add_handler(CallbackQueryHandler(post_callback, pattern=r"^postch_"))
    app.add_handler(CallbackQueryHandler(removechannel_callback, pattern=r"^rmch_"))

    print("✅ Bot started. Polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
