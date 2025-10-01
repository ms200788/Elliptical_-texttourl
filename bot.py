import os
import threading
from flask import Flask
import telebot
from telebot import types

# --- Config from Environment ---
TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

bot = telebot.TeleBot(TOKEN)

# Storage (in memory, can be swapped with DB later)
start_photo_id = None
force_channel = None
shared_chats = set()  # chats where bot will auto-post content


# --- Helpers ---
def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID


def check_channel(user_id: int) -> bool:
    global force_channel
    if force_channel and force_channel.lower() != "none":
        try:
            member = bot.get_chat_member(force_channel, user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except Exception:
            return False
    return True


def send_to_shared_chats(func, *args, **kwargs):
    """
    Helper: send same message to all saved chats.
    func = bot.send_message / bot.send_photo / bot.send_video
    """
    for cid in shared_chats:
        try:
            func(cid, *args, **kwargs)
        except Exception as e:
            print(f"Failed to send to {cid}: {e}")


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
        "/addchat → Add current chat to auto-share list\n"
        "/listchat → Show all saved chats\n"
        "/removechat → Remove this chat from auto-share list\n\n"
        "📌 *Content Commands:*\n"
        "/texturl Text | URL → Send text with clickable link (no preview)\n"
        "/settextbutton Text|URL, Text2|URL2 | Caption → Send text with inline buttons\n"
        "/setphotobutton ... → Reply to photo → send photo with buttons + caption\n"
        "/setvideobutton ... → Reply to video → send video with buttons + caption"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown", disable_web_page_preview=True)


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
    shared_chats.add(message.chat.id)
    bot.reply_to(message, f"✅ Chat `{message.chat.id}` added.", parse_mode="Markdown")


@bot.message_handler(commands=['listchat'])
def list_chat(message):
    if not is_owner(message.from_user.id):
        return bot.reply_to(message, "❌ Only owner can use this.")
    if not shared_chats:
        return bot.reply_to(message, "ℹ️ No chats saved yet.")
    chats_list = "\n".join([f"- `{cid}`" for cid in shared_chats])
    bot.reply_to(message, f"📋 Saved Chats:\n{chats_list}", parse_mode="Markdown")


@bot.message_handler(commands=['removechat'])
def remove_chat(message):
    if not is_owner(message.from_user.id):
        return bot.reply_to(message, "❌ Only owner can use this.")
    if message.chat.id in shared_chats:
        shared_chats.remove(message.chat.id)
        bot.reply_to(message, f"🗑️ Chat `{message.chat.id}` removed.", parse_mode="Markdown")
    else:
        bot.reply_to(message, "⚠️ This chat is not in the saved list.")


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

    bot.send_message(message.chat.id, msg_text, parse_mode="Markdown", disable_web_page_preview=True)
    send_to_shared_chats(bot.send_message, msg_text, parse_mode="Markdown", disable_web_page_preview=True)


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

    bot.send_message(message.chat.id, caption or "Here are your buttons:", reply_markup=kb, disable_web_page_preview=True)
    send_to_shared_chats(bot.send_message, caption or "Here are your buttons:", reply_markup=kb, disable_web_page_preview=True)


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
    bot.send_photo(message.chat.id, photo_id, caption=caption, reply_markup=kb)
    send_to_shared_chats(bot.send_photo, photo_id, caption=caption, reply_markup=kb)


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
    bot.send_video(message.chat.id, video_id, caption=caption, reply_markup=kb)
    send_to_shared_chats(bot.send_video, video_id, caption=caption, reply_markup=kb)


# --- Health check (Flask for Render) ---
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