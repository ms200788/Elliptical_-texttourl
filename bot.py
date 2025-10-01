import os
import threading
from flask import Flask
import telebot
from telebot import types

# --- Config from Environment ---
TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")

# Storage (in memory, can be swapped with DB later)
start_photo_id = None
force_channel = None
shared_chats = {}  # alias → chat_id


# -------------------------
# Helpers
# -------------------------
def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

def check_channel(user_id: int) -> bool:
    """Check if user is in force-join channel (if set)."""
    global force_channel
    if force_channel and force_channel.lower() != "none":
        try:
            member = bot.get_chat_member(force_channel, user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except Exception:
            return False
    return True

def send_to_shared_chats(message, extra_text=None, reply_markup=None):
    """Send/copy message to all saved chats."""
    for alias, cid in shared_chats.items():
        try:
            if message.content_type == "text":
                bot.send_message(
                    cid,
                    (message.text + ("\n\n" + extra_text if extra_text else "")),
                    reply_markup=reply_markup,
                    disable_web_page_preview=True
                )
            elif message.content_type == "photo":
                bot.send_photo(
                    cid,
                    message.photo[-1].file_id,
                    caption=(message.caption or "") + (("\n\n" + extra_text) if extra_text else ""),
                    reply_markup=reply_markup
                )
            elif message.content_type == "video":
                bot.send_video(
                    cid,
                    message.video.file_id,
                    caption=(message.caption or "") + (("\n\n" + extra_text) if extra_text else ""),
                    reply_markup=reply_markup
                )
            else:
                bot.copy_message(cid, message.chat.id, message.message_id)
        except Exception as e:
            print(f"❌ Failed to send to {alias} ({cid}): {e}")

def send_to_chat(alias, message):
    """Send (copy) a reply message to one alias chat."""
    if alias not in shared_chats:
        return False, f"⚠️ Alias `{alias}` not found."

    cid = shared_chats[alias]
    try:
        bot.copy_message(cid, message.chat.id, message.message_id)
        return True, f"✅ Message sent to `{alias}`."
    except Exception as e:
        return False, f"❌ Failed to send to `{alias}`: {e}"


# -------------------------
# Commands
# -------------------------

# --- START ---
@bot.message_handler(commands=['start'])
def start(message):
    global start_photo_id
    if not check_channel(message.from_user.id):
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{force_channel.lstrip('@')}"))
        return bot.send_message(message.chat.id, "⚠️ Please join the channel first.", reply_markup=kb)

    if start_photo_id:
        bot.send_photo(
            message.chat.id,
            start_photo_id,
            caption="Welcome To Our Bot.\n\nThis Bot is a private Bot."
        )
    else:
        bot.send_message(message.chat.id, "✅ Bot is online.")


# --- HELP ---
@bot.message_handler(commands=['help'])
def help_cmd(message):
    text = (
        "📖 *Bot Commands:*\n\n"
        "/start → Show bot is online\n"
        "/help → Show this help\n\n"
        "👥 *Owner only:*\n"
        "/setimage → Reply to a photo to set as start image\n"
        "/setchannel → Set force join channel (@channel or none)\n"
        "/addchat → Add alias + chat_id to auto-share list\n"
        "/listchat → Show all saved chats\n"
        "/removechat → Remove chat by alias\n"
        "/sendto <alias> (reply to a message) → Send message to one alias\n\n"
        "📌 *Content Commands:*\n"
        "/texturl Text | URL → Send text with clickable link\n"
        "/settextbutton Text|URL, Text2|URL2 | Caption → Text + inline buttons\n"
        "/setphotobutton ... → Reply to photo + add buttons\n"
        "/setvideobutton ... → Reply to video + add buttons"
    )
    bot.send_message(message.chat.id, text, disable_web_page_preview=True)


# --- SET IMAGE ---
@bot.message_handler(commands=['setimage'])
def set_image(message):
    global start_photo_id
    if not is_owner(message.from_user.id):
        return bot.reply_to(message, "❌ Only owner can use this.")
    if not message.reply_to_message or not message.reply_to_message.photo:
        return bot.reply_to(message, "❌ Reply to a photo with /setimage.")
    start_photo_id = message.reply_to_message.photo[-1].file_id
    bot.reply_to(message, "✅ Start image updated.")


# --- SET CHANNEL ---
@bot.message_handler(commands=['setchannel'])
def set_channel(message):
    global force_channel
    if not is_owner(message.from_user.id):
        return bot.reply_to(message, "❌ Only owner can use this.")
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return bot.reply_to(message, "Usage: /setchannel @channelusername or none")
    force_channel = args[1].strip()
    bot.reply_to(message, f"✅ Force join channel set to: {force_channel}")


# --- CHAT MANAGEMENT ---
@bot.message_handler(commands=['addchat'])
def add_chat(message):
    if not is_owner(message.from_user.id):
        return bot.reply_to(message, "❌ Only owner can use this.")
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        return bot.reply_to(message, "Usage: /addchat <alias> <chat_id>")

    alias = args[1].strip()
    try:
        chat_id = int(args[2].strip())
    except ValueError:
        return bot.reply_to(message, "❌ Invalid chat ID. Use a numeric ID.")

    shared_chats[alias] = chat_id
    bot.reply_to(message, f"✅ Chat added:\nAlias: `{alias}`\nID: `{chat_id}`", parse_mode="Markdown")

@bot.message_handler(commands=['listchat'])
def list_chat(message):
    if not is_owner(message.from_user.id):
        return bot.reply_to(message, "❌ Only owner can use this.")
    if not shared_chats:
        return bot.reply_to(message, "ℹ️ No chats saved yet.")
    lines = [f"- `{alias}` → `{cid}`" for alias, cid in shared_chats.items()]
    bot.reply_to(message, "📋 Saved Chats:\n" + "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(commands=['removechat'])
def remove_chat(message):
    if not is_owner(message.from_user.id):
        return bot.reply_to(message, "❌ Only owner can use this.")
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return bot.reply_to(message, "Usage: /removechat <alias>")
    alias = args[1].strip()
    if alias in shared_chats:
        cid = shared_chats.pop(alias)
        bot.reply_to(message, f"🗑️ Removed alias `{alias}` (ID: `{cid}`)", parse_mode="Markdown")
    else:
        bot.reply_to(message, f"⚠️ Alias `{alias}` not found.")


# --- SEND TO ONE ALIAS ---
@bot.message_handler(commands=['sendto'])
def sendto(message):
    if not is_owner(message.from_user.id):
        return bot.reply_to(message, "❌ Only owner can use this.")
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return bot.reply_to(message, "Usage: reply with /sendto <alias>")
    alias = args[1].strip()
    if not message.reply_to_message:
        return bot.reply_to(message, "⚠️ You must reply to a message to use /sendto.")
    success, response = send_to_chat(alias, message.reply_to_message)
    bot.reply_to(message, response, parse_mode="Markdown")


# --- TEXT URL ---
@bot.message_handler(commands=['texturl'])
def texturl(message):
    if not check_channel(message.from_user.id):
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{force_channel.lstrip('@')}"))
        return bot.send_message(message.chat.id, "⚠️ Please join the channel first.", reply_markup=kb)
    args = message.text.split(" ", 1)
    if len(args) < 2 or "|" not in args[1]:
        return bot.reply_to(message, "Usage: /texturl Text | URL")
    text, url = [x.strip() for x in args[1].split("|", 1)]
    msg_text = f"[{text}]({url})"
    sent = bot.send_message(message.chat.id, msg_text, disable_web_page_preview=True)
    send_to_shared_chats(sent)


# --- SET TEXT WITH BUTTONS ---
@bot.message_handler(commands=['settextbutton'])
def set_text_button(message):
    if not check_channel(message.from_user.id):
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{force_channel.lstrip('@')}"))
        return bot.send_message(message.chat.id, "⚠️ Please join the channel first.", reply_markup=kb)
    args = message.text.split(" ", 1)
    if len(args) < 2 or "|" not in args[1]:
        return bot.reply_to(message, "Usage: /settextbutton Text|URL, Text2|URL2 | Caption")
    buttons_part, caption = "", ""
    if " | " in args[1]:
        buttons_part, caption = args[1].rsplit(" | ", 1)
    else:
        buttons_part = args[1]
        caption = ""
    kb = types.InlineKeyboardMarkup()
    for part in [p.strip() for p in buttons_part.split(",") if p.strip()]:
        if "|" in part:
            t, u = [x.strip() for x in part.split("|", 1)]
            kb.add(types.InlineKeyboardButton(t, url=u))
    sent = bot.send_message(message.chat.id, caption or "Here are your buttons:", reply_markup=kb, disable_web_page_preview=True)
    send_to_shared_chats(sent, reply_markup=kb)


# --- SET PHOTO WITH BUTTONS ---
@bot.message_handler(commands=['setphotobutton'])
def set_photo_button(message):
    if not message.reply_to_message or not message.reply_to_message.photo:
        return bot.reply_to(message, "❌ Reply to a photo with /setphotobutton Text|URL, Text2|URL2 | Caption")
    args = message.text.split(" ", 1)
    buttons_part, caption = "", ""
    if len(args) > 1 and " | " in args[1]:
        buttons_part, caption = args[1].rsplit(" | ", 1)
    elif len(args) > 1:
        buttons_part = args[1]
        caption = message.reply_to_message.caption or ""
    else:
        return bot.reply_to(message, "Usage: /setphotobutton Text|URL, Text2|URL2 | Caption")
    kb = types.InlineKeyboardMarkup()
    for part in [p.strip() for p in buttons_part.split(",") if p.strip()]:
        if "|" in part:
            t, u = [x.strip() for x in part.split("|", 1)]
            kb.add(types.InlineKeyboardButton(t, url=u))
    photo_id = message.reply_to_message.photo[-1].file_id
    sent = bot.send_photo(message.chat.id, photo_id, caption=caption, reply_markup=kb)
    send_to_shared_chats(sent, reply_markup=kb)


# --- SET VIDEO WITH BUTTONS ---
@bot.message_handler(commands=['setvideobutton'])
def set_video_button(message):
    if not message.reply_to_message or not message.reply_to_message.video:
        return bot.reply_to(message, "❌ Reply to a video with /setvideobutton Text|URL, Text2|URL2 | Caption")
    args = message.text.split(" ", 1)
    buttons_part, caption = "", ""
    if len(args) > 1 and " | " in args[1]:
        buttons_part, caption = args[1].rsplit(" | ", 1)
    elif len(args) > 1:
        buttons_part = args[1]
        caption = message.reply_to_message.caption or ""
    else:
        return bot.reply_to(message, "Usage: /setvideobutton Text|URL, Text2|URL2 | Caption")
    kb = types.InlineKeyboardMarkup()
    for part in [p.strip() for p in buttons_part.split(",") if p.strip()]:
        if "|" in part:
            t, u = [x.strip() for x in part.split("|", 1)]
            kb.add(types.InlineKeyboardButton(t, url=u))
    video_id = message.reply_to_message.video.file_id
    sent = bot.send_video(message.chat.id, video_id, caption=caption, reply_markup=kb)
    send_to_shared_chats(sent, reply_markup=kb)


# -------------------------
# Health check (Flask for Render)
# -------------------------
app = Flask(__name__)

@app.route('/health')
def health():
    return "OK", 200

def run_web():
    app.run(host="0.0.0.0", port=10000)


# --- RUN BOT ---
print("🤖 Bot is running...")
threading.Thread(target=run_web).start()
bot.infinity_polling()