# Transfer to Chat feature
# /setchat <chat_id> — set a target chat where bot is admin, save content there
# /mychat — show current target chat
# /clearchat — reset to user's DM (default)

import os, json
from .. import bot as Drone, Bot, is_authorized, DATA_DIR
from main.plugins.pyroplug import get_msg
from main.plugins.helpers import get_link, join

from telethon import events, Button

_SETCHAT_FILE = os.path.join(DATA_DIR, "user_target_chats.json")

_user_target_chats = {}


def _load_target_chats():
    try:
        if os.path.exists(_SETCHAT_FILE):
            with open(_SETCHAT_FILE) as f:
                raw = json.load(f)
            for k, v in raw.items():
                _user_target_chats[int(k)] = int(v)
            print(f"[SETCHAT] Loaded {len(_user_target_chats)} saved target chats")
    except Exception as e:
        print(f"[SETCHAT] Could not load target chats: {e}")


def _save_target_chats():
    try:
        with open(_SETCHAT_FILE, "w") as f:
            json.dump({str(k): v for k, v in _user_target_chats.items()}, f)
    except Exception as e:
        print(f"[SETCHAT] Could not save target chats: {e}")


_load_target_chats()


def get_target_chat(user_id):
    return _user_target_chats.get(user_id, None)


@Drone.on(events.NewMessage(incoming=True, pattern='/setchat'))
async def set_chat(event):
    if not is_authorized(event.sender_id):
        return
    args = event.text.split(maxsplit=1)
    if len(args) < 2:
        await event.reply(
            "**Set Transfer Chat**\n\n"
            "Usage: `/setchat -100XXXXXXXXXX`\n\n"
            "Set a target chat where all your saved content goes.\n"
            "The bot must be added as admin in that chat first.\n\n"
            "**Steps:**\n"
            "1. Create a channel/group (or use existing one)\n"
            "2. Add the bot as admin with 'Pin Messages' permission\n"
            "3. Get the chat ID (forward a message from there to @userinfobot)\n"
            "4. Use `/setchat <chat_id>`"
        )
        return

    try:
        chat_id = int(args[1].strip())
    except ValueError:
        await event.reply("Invalid chat ID. Must be a number like `-1002663154678`.")
        return

    try:
        chat = await Bot.get_chat(chat_id)
        chat_title = chat.title if chat else "Unknown"
    except Exception as e:
        await event.reply(
            f"**Cannot access chat** `{chat_id}`\n\nError: {str(e)[:200]}\n\n"
            "Make sure the bot is added as admin in that chat first."
        )
        return

    try:
        member = await Bot.get_chat_member(chat_id, "me")
        if member and member.status:
            status_name = str(member.status)
            if 'ADMIN' in status_name.upper():
                _user_target_chats[event.sender_id] = chat_id
                _save_target_chats()
                await event.reply(
                    f"**Transfer chat set!**\n\n"
                    f"**Chat:** {chat_title}\n**ID:** `{chat_id}`\n**Bot status:** Admin\n\n"
                    f"All your saved content will now go to this chat.\n"
                    f"Use `/clearchat` to reset to default."
                )
            else:
                await event.reply(
                    f"**Bot is not admin** in `{chat_title}`\n\nBot status: {status_name}\n\n"
                    "Add the bot as admin and try again."
                )
        else:
            _user_target_chats[event.sender_id] = chat_id
            _save_target_chats()
            await event.reply(
                f"**Transfer chat set!**\n\n**Chat:** {chat_title}\n**ID:** `{chat_id}`\n\n"
                f"Warning: Could not verify admin status. Pinning may not work."
            )
    except Exception as e:
        _user_target_chats[event.sender_id] = chat_id
        _save_target_chats()
        await event.reply(
            f"**Transfer chat set!**\n\n**Chat:** {chat_title}\n**ID:** `{chat_id}`\n\n"
            f"Warning: Could not verify admin status ({str(e)[:100]})."
        )


@Drone.on(events.NewMessage(incoming=True, pattern='/mychat'))
async def my_chat(event):
    if not is_authorized(event.sender_id):
        return
    target = _user_target_chats.get(event.sender_id)
    if target:
        try:
            chat = await Bot.get_chat(target)
            chat_title = chat.title if chat else "Unknown"
            await event.reply(
                f"**Your Transfer Chat:**\n\n**Name:** {chat_title}\n**ID:** `{target}`\n\n"
                f"Use `/clearchat` to reset to your DM."
            )
        except Exception:
            await event.reply(
                f"**Your Transfer Chat:** `{target}`\n\n"
                "(Could not fetch chat details — bot may have been removed.)\n\n"
                f"Use `/clearchat` to reset to your DM."
            )
    else:
        await event.reply(
            f"**No custom transfer chat set.**\n\nContent is being saved to: your DM\n\n"
            f"Use `/setchat <chat_id>` to set one."
        )


@Drone.on(events.NewMessage(incoming=True, pattern='/clearchat'))
async def clear_chat(event):
    if not is_authorized(event.sender_id):
        return
    if event.sender_id in _user_target_chats:
        del _user_target_chats[event.sender_id]
        _save_target_chats()
        await event.reply("**Transfer chat cleared.**\n\nContent will now be saved to your DM.")
    else:
        await event.reply("No custom transfer chat was set.")
