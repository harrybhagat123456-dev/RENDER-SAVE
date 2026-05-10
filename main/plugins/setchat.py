# Transfer to Chat feature
# /setchat <chat_id> — set a target chat where bot is admin, save content there
# /mychat — show current target chat
# /clearchat — reset to user's DM (default)

import os
from .. import bot as Drone
from .. import Bot, AUTH
from main.plugins.pyroplug import get_msg
from main.plugins.helpers import get_link, join

from telethon import events, Button
from pyrogram.errors import ChatAdminRequired as PyroChatAdminRequired, Forbidden

# Per-user target chat storage
# Key: user_id, Value: chat_id (int)
_user_target_chats = {}

def get_target_chat(user_id):
    """Get the user's custom target chat, or None (falls back to their DM)."""
    return _user_target_chats.get(user_id, None)

@Drone.on(events.NewMessage(incoming=True, from_users=AUTH, pattern='/setchat'))
async def set_chat(event):
    """
    Set a custom target chat where content will be saved.
    The bot must be an admin in that chat for pinning to work.
    Usage: /setchat -100XXXXXXXXXX
    """
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

    # Verify the bot can access this chat
    try:
        chat = await Bot.get_chat(chat_id)
        chat_title = chat.title if chat else "Unknown"
    except Exception as e:
        await event.reply(
            f"**Cannot access chat** `{chat_id}`\n\n"
            f"Error: {str(e)[:200]}\n\n"
            "Make sure the bot is added as admin in that chat first."
        )
        return

    # Verify the bot is admin
    try:
        member = await Bot.get_chat_member(chat_id, "me")
        if member and member.status:
            status_name = str(member.status)
            if 'ADMIN' in status_name.upper():
                _user_target_chats[event.sender_id] = chat_id
                await event.reply(
                    f"**Transfer chat set!**\n\n"
                    f"**Chat:** {chat_title}\n"
                    f"**ID:** `{chat_id}`\n"
                    f"**Bot status:** Admin\n\n"
                    f"All your saved content will now go to this chat.\n"
                    f"Use `/clearchat` to reset to default."
                )
            else:
                await event.reply(
                    f"**Bot is not admin** in `{chat_title}`\n\n"
                    f"Bot status: {status_name}\n\n"
                    "The bot needs admin rights (especially 'Pin Messages') to work properly.\n"
                    "Add the bot as admin and try again."
                )
        else:
            _user_target_chats[event.sender_id] = chat_id
            await event.reply(
                f"**Transfer chat set!**\n\n"
                f"**Chat:** {chat_title}\n"
                f"**ID:** `{chat_id}`\n\n"
                f"Warning: Could not verify admin status. Pinning may not work."
            )
    except Exception as e:
        _user_target_chats[event.sender_id] = chat_id
        await event.reply(
            f"**Transfer chat set!**\n\n"
            f"**Chat:** {chat_title}\n"
            f"**ID:** `{chat_id}`\n\n"
            f"Warning: Could not verify admin status ({str(e)[:100]}).\n"
            f"Pinning may not work if bot is not admin."
        )


@Drone.on(events.NewMessage(incoming=True, from_users=AUTH, pattern='/mychat'))
async def my_chat(event):
    """Show the current target chat for this user."""
    target = _user_target_chats.get(event.sender_id)
    if target:
        try:
            chat = await Bot.get_chat(target)
            chat_title = chat.title if chat else "Unknown"
            await event.reply(
                f"**Your Transfer Chat:**\n\n"
                f"**Name:** {chat_title}\n"
                f"**ID:** `{target}`\n\n"
                f"Use `/clearchat` to reset to default channel."
            )
        except Exception:
            await event.reply(
                f"**Your Transfer Chat:** `{target}`\n\n"
                "(Could not fetch chat details — bot may have been removed.)\n\n"
                f"Use `/clearchat` to reset to your DM."
            )
    else:
        await event.reply(
            f"**No custom transfer chat set.**\n\n"
            f"Content is being saved to: your DM\n\n"
            f"Use `/setchat <chat_id>` to set one."
        )


@Drone.on(events.NewMessage(incoming=True, from_users=AUTH, pattern='/clearchat'))
async def clear_chat(event):
    """Reset the target chat to the user's DM."""
    if event.sender_id in _user_target_chats:
        del _user_target_chats[event.sender_id]
        await event.reply(
            "**Transfer chat cleared.**\n\n"
            "Content will now be saved to your DM."
        )
    else:
        await event.reply("No custom transfer chat was set.")
