#Github.com-Vasusen-code

import time, os

from .. import bot as Drone
from .. import Bot
from main.plugins.pyroplug import get_msg
from main.plugins.helpers import get_link, join
from main.plugins.setchat import get_target_chat

import main as _main_module

from telethon import events
from pyrogram.errors import FloodWait

message = "Send me the message link you want to start saving from, as a reply to this message."

@Drone.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def clone(event):
    if event.is_reply:
        reply = await event.get_reply_message()
        if reply.text == message:
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

    # Determine where to save the content:
    # 1. If user set a custom transfer chat via /setchat, use that
    # 2. Otherwise, fall back to saving in the user's DM
    target = get_target_chat(event.sender_id) or event.sender_id

    # Status/progress messages always stay in the user's DM.
    if target != event.sender_id:
        status_msg = await Drone.send_message(event.sender_id, "Processing!")
        edit_id = status_msg.id
        status_chat = event.sender_id
    else:
        edit = await event.reply("Processing!")
        edit_id = edit.id
        status_chat = event.sender_id

    userbot = _main_module.userbot

    try:
        if 't.me/+' in link:
            q = await join(userbot, link)
            await Drone.send_message(event.sender_id, q)
            return
        if 't.me/' in link:
            await get_msg(userbot, Bot, Drone, target, edit_id, status_chat, link, 0)
    except FloodWait as fw:
        return await Drone.send_message(event.sender_id, f'Try again after {fw.x} seconds due to floodwait from telegram.')
    except Exception as e:
        print(e)
        await Drone.send_message(event.sender_id, f"An error occurred during cloning of `{link}`\n\n**Error:** {str(e)}")
