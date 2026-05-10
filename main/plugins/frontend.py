#Github.com-Vasusen-code

import time, os

from .. import bot as Drone, Bot, is_authorized, get_target_chat
from main.plugins.pyroplug import get_msg
from main.plugins.helpers import get_link, join

import main as _main_module

from telethon import events
from pyrogram.errors import FloodWait

message = "Send me the message link you want to start saving from, as a reply to this message."

@Drone.on(events.NewMessage(incoming=True))
async def clone(event):
    # Only authorized users can trigger saves (both in private and groups)
    if not is_authorized(event.sender_id):
        return

    if event.is_reply:
        reply = await event.get_reply_message()
        if reply and reply.text == message:
            return

    try:
        link = get_link(event.text)
        if not link:
            return
    except TypeError:
        return

    # Check userbot is logged in
    if not _main_module.userbot:
        await event.reply(
            "⚠️ **Userbot is not logged in.**\n\n"
            "Send /login to authenticate a Telegram account first."
        )
        return

    # Status messages go back to the same chat (group or DM)
    status_chat = event.chat_id

    # Destination for saved content:
    # 1. User's /setchat target (if configured)
    # 2. Otherwise the same chat where the link was sent
    target = get_target_chat(event.sender_id) or event.chat_id

    edit = await event.reply("Processing!")
    edit_id = edit.id

    userbot = _main_module.userbot

    try:
        if 't.me/+' in link:
            q = await join(userbot, link)
            await Drone.send_message(status_chat, q)
            return
        if 't.me/' in link:
            await get_msg(userbot, Bot, Drone, target, edit_id, status_chat, link, 0)
    except FloodWait as fw:
        return await Drone.send_message(status_chat, f'Try again after {fw.x} seconds due to floodwait from telegram.')
    except Exception as e:
        print(e)
        await Drone.send_message(status_chat, f"An error occurred during cloning of `{link}`\n\n**Error:** {str(e)}")
