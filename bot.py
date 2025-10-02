import os
import threading
import re
from flask import Flask
import telebot
from telebot import types

# --- Config from Environment ---
TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
DEFAULT_START_IMAGE = os.getenv("DEFAULT_START_IMAGE")  # permanent fallback image_id

bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")

# Storage (in memory, resets after restart)
start_photo_id = None   # temporary image (set by /setimage)
force_channel = None
shared_chats = {}  # alias -> chat_id


# -------------------------
# Helpers
# -------------------------
def is_owner(user_id: int) -> bool:
    try:
        return int(user_id) == int(OWNER_ID)
    except Exception:
        return False


def check_channel(user_id: int) -> bool:
    """Return True if either no force_channel is set OR user is a member of force_channel."""
    global force_channel
    if not force_channel or (str(force_channel).lower() == "none"):
        return True
    try:
        member = bot.get_chat_member(force_channel, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False


def _join_channel_keyboard():
    """Return InlineKeyboardMarkup pointing to the force channel (safe to call only if force_channel set)."""
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{force_channel.lstrip('@')}"))
    return kb


def send_to_all(message, extra_text: str = None):
    """Broadcast message to all chats in shared_chats."""
    for alias, cid in shared_chats.items():
        try:
            markup = getattr(message, "reply_markup", None)
            ct = message.content_type
            if ct == "text":
                text = message.text or ""
                if extra_text:
                    text = text + "\n\n" + extra_text
                bot.send_message(cid, text, reply_markup=markup, disable_web_page_preview=True)
            elif ct == "photo":
                file_id = message.photo[-1].file_id
                caption = message.caption or ""
                if extra_text:
                    caption = caption + "\n\n" + extra_text
                bot.send_photo(cid, file_id, caption=caption, reply_markup=markup)
            elif ct == "video":
                file_id = message.video.file_id
                caption = message.caption or ""
                if extra_text:
                    caption = caption + "\n\n" + extra_text
                bot.send_video(cid, file_id, caption=caption, reply_markup=markup)
            elif ct == "document":
                file_id = message.document.file_id
                caption = message.caption or ""
                if extra_text:
                    caption = caption + "\n\n" + extra_text
                bot.send_document(cid, file_id, caption=caption, reply_markup=markup)
            else:
                bot.copy_message(cid, message.chat.id, message.message_id)
        except Exception as e:
            print(f"❌ Failed to send to {alias} ({cid}): {e}")


def send_to_chat(alias: str, message):
    """Send replied message to one alias chat."""
    if alias not in shared_chats:
        return False, f"⚠️ Alias `{alias}` not found."
    cid = shared_chats[alias]
    try:
        markup = getattr(message, "reply_markup", None)
        ct = message.content_type
        if ct == "text":
            bot.send_message(cid, message.text or "", reply_markup=markup, disable_web_page_preview=True)
        elif ct == "photo":
            bot.send_photo(cid, message.photo[-1].file_id, caption=message.caption or "", reply_markup=markup)
        elif ct == "video":
            bot.send_video(cid, message.video.file_id, caption=message.caption or "", reply_markup=markup)
        elif ct == "document":
            bot.send_document(cid, message.document.file_id, caption=message.caption or "", reply_markup=markup)
        else:
            bot.copy_message(cid, message.chat.id, message.message_id)
        return True, f"✅ Message sent to `{alias}`."
    except Exception as e:
        return False, f"❌ Failed to send to `{alias}`: {e}"


# -------------------------
# Command handlers
# -------------------------
@bot.message_handler(commands=['start'])
def cmd_start(message):
    global start_photo_id
    if not check_channel(message.from_user.id):
        return bot.send_message(message.chat.id, "⚠️ Please join the channel first.", reply_markup=_join_channel_keyboard())
    photo_id = start_photo_id or DEFAULT_START_IMAGE
    if photo_id:
        bot.send_photo(message.chat.id, photo_id, caption="Welcome To Our Bot.\n\nThis Bot is a private Bot.")
    else:
        bot.send_message(message.chat.id, "✅ Bot is online.")


@bot.message_handler(commands=['help'])
def cmd_help(message):
    help_text = (
        "📖 *Bot Commands:*\n\n"
        "/start → Show bot is online\n"
        "/help → Show this help\n\n"
        "👥 *Owner only:*\n"
        "/setimage → Reply to a photo to set as start image (temporary)\n"
        "/resetimage → Reset start image back to default (from DEFAULT_START_IMAGE)\n"
        "/setchannel → Set force join channel (@channel or none)\n"
        "/addchat → Add alias + chat_id to auto-share list\n"
        "/listchat → Show all saved chats\n"
        "/removechat → Remove chat by alias\n"
        "/sendto `alias` (reply) → Send replied message to alias (buttons preserved)\n"
        "/broadcast (reply) → Send replied message to all saved chats\n\n"
        "📌 *Content Commands:*\n"
        "/texturl (reply to text) → Use `{ word | url }` inside your passage to make clickable links.\n"
        "/settextbutton Text|URL,... → Reply to a text and add buttons (original text kept)\n"
        "/setphotobutton Text|URL,... → Reply to a photo and add buttons (original caption kept)\n"
        "/setvideobutton Text|URL,... → Reply to a video and add buttons (original caption kept)"
    )
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown", disable_web_page_preview=True)


@bot.message_handler(commands=['setimage'])
def cmd_setimage(message):
    global start_photo_id
    if not is_owner(message.from_user.id):
        return bot.reply_to(message, "❌ Only owner can use this.")
    if not message.reply_to_message or not message.reply_to_message.photo:
        return bot.reply_to(message, "❌ Reply to a photo with /setimage.")
    start_photo_id = message.reply_to_message.photo[-1].file_id
    bot.reply_to(message, "✅ Start image updated (temporary — will reset on restart).")


@bot.message_handler(commands=['resetimage'])
def cmd_resetimage(message):
    global start_photo_id
    if not is_owner(message.from_user.id):
        return bot.reply_to(message, "❌ Only owner can use this.")
    start_photo_id = None
    bot.reply_to(message, "✅ Start image reset to default (env fallback).")


@bot.message_handler(commands=['setchannel'])
def cmd_setchannel(message):
    global force_channel
    if not is_owner(message.from_user.id):
        return bot.reply_to(message, "❌ Only owner can use this.")
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return bot.reply_to(message, "Usage: /setchannel @channelusername or none")
    force_channel = args[1].strip()
    bot.reply_to(message, f"✅ Force join channel set to: {force_channel}")


@bot.message_handler(commands=['addchat'])
def cmd_addchat(message):
    if not is_owner(message.from_user.id):
        return bot.reply_to(message, "❌ Only owner can use this.")
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        return bot.reply_to(message, "Usage: /addchat <alias> <chat_id>")
    alias = args[1].strip()
    try:
        chat_id = int(args[2].strip())
    except ValueError:
        return bot.reply_to(message, "❌ Invalid chat ID. Use a numeric ID (e.g. -1001234567890).")
    shared_chats[alias] = chat_id
    bot.reply_to(message, f"✅ Chat added:\nAlias: `{alias}`\nID: `{chat_id}`", parse_mode="Markdown")


@bot.message_handler(commands=['listchat'])
def cmd_listchat(message):
    if not is_owner(message.from_user.id):
        return bot.reply_to(message, "❌ Only owner can use this.")
    if not shared_chats:
        return bot.reply_to(message, "ℹ️ No chats saved yet.")
    lines = [f"- `{alias}` → `{cid}`" for alias, cid in shared_chats.items()]
    bot.reply_to(message, "📋 Saved Chats:\n" + "\n".join(lines), parse_mode="Markdown")


@bot.message_handler(commands=['removechat'])
def cmd_removechat(message):
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


@bot.message_handler(commands=['sendto'])
def cmd_sendto(message):
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


@bot.message_handler(commands=['broadcast'])
def cmd_broadcast(message):
    if not is_owner(message.from_user.id):
        return bot.reply_to(message, "❌ Only owner can use this.")
    if not message.reply_to_message:
        return bot.reply_to(message, "⚠️ Reply to a message to broadcast.")
    send_to_all(message.reply_to_message)
    bot.reply_to(message, "✅ Broadcast attempted to all saved chats.")


# --- Improved /texturl ---
@bot.message_handler(commands=['texturl'])
def cmd_texturl(message):
    if not message.reply_to_message or not message.reply_to_message.text:
        return bot.reply_to(message, "⚠️ Reply to a text message containing `{ word | url }` patterns.")
    if not check_channel(message.from_user.id):
        return bot.send_message(message.chat.id, "⚠️ Please join the channel first.", reply_markup=_join_channel_keyboard())

    text = message.reply_to_message.text

    def replacer(match):
        word, url = match.group(1).strip(), match.group(2).strip()
        return f"[{word}]({url})"

    new_text = re.sub(r"\{([^|]+)\|([^}]+)\}", replacer, text)

    sent = bot.send_message(message.chat.id, new_text, parse_mode="Markdown", disable_web_page_preview=True)
    send_to_all(sent)


# --- Helper to build keyboard ---
def _build_keyboard(buttons_str: str):
    kb = types.InlineKeyboardMarkup()
    for part in [p.strip() for p in buttons_str.split(",") if p.strip()]:
        if "|" in part:
            t, u = [x.strip() for x in part.split("|", 1)]
            kb.add(types.InlineKeyboardButton(t, url=u))
    return kb


# --- Add buttons but keep original caption/text ---
@bot.message_handler(commands=['settextbutton'])
def cmd_settextbutton(message):
    if not message.reply_to_message or not message.reply_to_message.text:
        return bot.reply_to(message, "❌ Reply to a text message with /settextbutton Text|URL,...")
    args = message.text.split(" ", 1)
    if len(args) < 2:
        return bot.reply_to(message, "Usage: /settextbutton Text|URL, Text2|URL2")

    kb = _build_keyboard(args[1])
    text = message.reply_to_message.text
    sent = bot.send_message(message.chat.id, text, reply_markup=kb, disable_web_page_preview=True)
    send_to_all(sent)


@bot.message_handler(commands=['setphotobutton'])
def cmd_setphotobutton(message):
    if not message.reply_to_message or not message.reply_to_message.photo:
        return bot.reply_to(message, "❌ Reply to a photo with /setphotobutton Text|URL,...")
    args = message.text.split(" ", 1)
    if len(args) < 2:
        return bot.reply_to(message, "Usage: /setphotobutton Text|URL, Text2|URL2")

    kb = _build_keyboard(args[1])
    photo_id = message.reply_to_message.photo[-1].file_id
    caption = message.reply_to_message.caption or ""
    sent = bot.send_photo(message.chat.id, photo_id, caption=caption, reply_markup=kb)
    send_to_all(sent)


@bot.message_handler(commands=['setvideobutton'])
def cmd_setvideobutton(message):
    if not message.reply_to_message or not message.reply_to_message.video:
        return bot.reply_to(message, "❌ Reply to a video with /setvideobutton Text|URL,...")
    args = message.text.split(" ", 1)
    if len(args) < 2:
        return bot.reply_to(message, "Usage: /setvideobutton Text|URL, Text2|URL2")

    kb = _build_keyboard(args[1])
    video_id = message.reply_to_message.video.file_id
    caption = message.reply_to_message.caption or ""
    sent = bot.send_video(message.chat.id, video_id, caption=caption, reply_markup=kb)
    send_to_all(sent)


# -------------------------
# Health check (Flask for Render)
# -------------------------
app = Flask(__name__)

@app.route('/health')
def health():
    return "OK", 200

def run_web():
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))


# --- RUN BOT ---
if __name__ == "__main__":
    print("🤖 Bot is running...")
    threading.Thread(target=run_web).start()
    bot.infinity_polling()