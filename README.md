# 🛡️ User Protector Hub — Multi-User Admin Button Bot

Telegram bot jisme **har user** apne admins ke buttons bana kar **apne channel** par post kar sakta hai.  
**Owner-only commands** sirf aapko dikhte hain. Saara activity aapke **logger group** mein log hota hai.

---

## ✨ Features

- 🧑‍🤝‍🧑 **Multi-user** — har user apni admin list + channel list banata hai
- 🔗 **Username ya User ID** — dono support (`t.me/...` ya `tg://user?id=...`)
- 📢 **Multi-channel** — user apne kitne bhi channels add kar sakta hai
- 🎯 **Command scoping** — owner commands users ko dikhte hi nahi
- 📝 **Logger group** — add, post, error, unauthorized attempt — sab log
- 🖼️ **Image + Buttons post** support
- 💾 **JSON persist + auto-migration**

---

## 📦 Setup

### 1️⃣ Dependencies
```bash
pip install "python-telegram-bot>=20.0"
```

### 2️⃣ Config (bot.py)
```python
BOT_TOKEN      = "YOUR_BOT_TOKEN"
CHANNEL_ID     = "@UPH_TEAM"      # owner ka main channel
OWNER_ID       = 123456789                 # aapki ID
LOGGER_CHAT_ID = -1001234567890            # logger group ID
POST_IMAGE     = "meet_our_team.jpg"
```

### 3️⃣ Logger group banayein
1. Private group banayein
2. Bot ko add karein
3. Group ko supergroup banayein (koi member add karke remove kar do)
4. Group ID lein (`-100...`) → `LOGGER_CHAT_ID` mein daalein

### 4️⃣ Image rakhein
`meet_our_team.jpg` bot folder mein save karein.  
(Optional — nahi ho to bot sirf text bhejega)

### 5️⃣ Bot run karein
```bash
python bot.py
```

---

## 🚀 Commands

### 👤 Sab users ke liye

| Command | Kaam |
|---|---|
| `/start` | Intro + commands list |
| `/add` | Admin button add (name + @username/ID) |
| `/list` | Apne admins |
| `/preview` | Button preview |
| `/clear` | Admins clear |
| `/addchannel` | Apna channel add |
| `/mychannels` | Apne channels |
| `/removechannel` | Channel remove |
| `/post` | Channel par post |
| `/cancel` | Cancel |

### 👑 Owner-only (sirf aapko dikhengi)

| Command | Kaam |
|---|---|
| `/seed` | Default 6 admins load |
| `/send` | Main channel par post |
| `/sendtext` | Main channel text post |
| `/users` | Sabhi users list |
| `/broadcast` | Sab users ko message |

---

## 📋 Typical Flows

### 👤 User ke liye
```
/add → naam → @username/id → ✅
/addchannel → @mychannel → ✅  (bot admin hona chahiye)
/post → channel select → ✅
```

### 👑 Owner ke liye
```
/seed              ← default admins
/preview           ← check
/send              ← main channel par post
/users             ← dekhein kitne users
/broadcast <msg>   ← sab users ko
```

---

## 📝 Logger Output Examples

```
➕ Admin added
👤 Rahul (@rahul123) [123456789]
🔗 👑 Admin 1 → @admin_one
📊 Total: 3

📢 Channel added
👤 Rahul (@rahul123) [123456789]
📢 My Channel (`-1001234567890`)

📤 Post sent
👤 Rahul (@rahul123) [123456789]
📢 My Channel (`-1001234567890`)
🔢 3 buttons

⚠️ UNAUTHORIZED attempt
👤 Random User [999]
🔧 Command: /send
```

---

## 🔒 Channel Add Rules

- Bot **us channel ka admin hona chahiye** (Post Messages permission)
- Sirf **channels** add ho sakte hain (groups nahi)
- Public: `@channelusername`  
- Private: `-1001234567890`

---

## 🐛 Troubleshooting

| Issue | Fix |
|---|---|
| Owner commands users ko dikh rahi | BotFather → `/setcommands` → delete old, phir bot restart |
| `/send` Forbidden | Bot ko channel admin banayein |
| ID button web pe nahi khulta | Mobile/Desktop app use karein (`tg://` sirf app me) |
| Logger nahi aata | `LOGGER_CHAT_ID` check, bot ko group mein add |
| Data delete ho gaya | `user_admins.json` backup rakhein |

---

## 🔄 Migration

Purana `user_admins.json` (v1/v2) **automatically migrate** ho jata hai.  
Naya format:
```json
{
  "123": {
    "admins": [{"name": "...", "username": "..."}],
    "channels": [{"id": -100..., "username": "...", "title": "..."}],
    "info": {"name": "...", "username": "...", "last_seen": "..."}
  }
}
```

---

**🛡️ Stay safe. Report responsibly.**
