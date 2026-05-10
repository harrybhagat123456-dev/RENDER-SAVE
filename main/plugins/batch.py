#Tg:MaheshChauhan/DroneBots
#Github.com/Vasusen-code

import time, os, asyncio

from .. import bot as Drone, Bot, is_authorized
from main.plugins.pyroplug import get_bulk_msg
from main.plugins.helpers import get_link, screenshot

import main as _main_module

from telethon import events, Button, errors
from telethon.tl.types import DocumentAttributeVideo
from pyrogram import Client
from pyrogram.errors import FloodWait
from ethon.pyfunc import video_metadata

batch = []

@Drone.on(events.NewMessage(incoming=True, pattern='/cancel'))
async def cancel(event):
    if not is_authorized(event.sender_id):
        return
    if event.sender_id not in batch:
        return await event.reply("No batch active.")
    batch.clear()
    await event.reply("Done.")

@Drone.on(events.NewMessage(incoming=True, pattern='/batch'))
async def _batch(event):
    if not is_authorized(event.sender_id):
        return
    if not event.is_private:
        return

    if not _main_module.userbot:
        await event.reply(
            "⚠️ **Userbot is not logged in.**\n\nSend /login to authenticate first."
        )
        return

    if event.sender_id in batch:
        return await event.reply("You've already started one batch, wait for it to complete.")

    async with Drone.conversation(event.chat_id) as conv:
        await conv.send_message(
            "Send me the message link you want to start saving from, as a reply to this message.",
            buttons=Button.force_reply()
        )
        try:
            link = await conv.get_response()
            try:
                _link = get_link(link.text)
            except Exception:
                await conv.send_message("No link found.")
                return conv.cancel()
        except Exception as e:
            print(e)
            await conv.send_message("Cannot wait longer for your response!")
            return conv.cancel()

        await conv.send_message(
            "Send me the number of files/range you want to save from the given message.",
            buttons=Button.force_reply()
        )
        try:
            _range = await conv.get_response()
        except Exception as e:
            print(e)
            await conv.send_message("Cannot wait longer for your response!")
            return conv.cancel()

        try:
            value = int(_range.text)
            if value > 100:
                await conv.send_message("You can only get up to 100 files in a single batch.")
                return conv.cancel()
        except ValueError:
            await conv.send_message("Range must be an integer!")
            return conv.cancel()

        batch.append(event.sender_id)
        await run_batch(_main_module.userbot, Bot, event.sender_id, _link, value)
        conv.cancel()
        batch.clear()


async def run_batch(userbot, client, sender, link, _range):
    for i in range(_range):
        timer = 10 if i < 50 else 15
        if 't.me/c/' not in link:
            timer = 10
        try:
            if sender not in batch:
                await client.send_message(sender, "Batch completed.")
                break
        except Exception as e:
            print(e)
            await client.send_message(sender, "Batch completed.")
            break
        try:
            await get_bulk_msg(userbot, client, sender, link, i)
        except FloodWait as fw:
            if int(fw.x) > 299:
                await client.send_message(sender, "Cancelling batch — floodwait > 5 minutes.")
                break
            await asyncio.sleep(fw.x + 5)
            await get_bulk_msg(userbot, client, sender, link, i)
        protection = await client.send_message(sender, f"Sleeping for `{timer}` seconds to avoid Floodwaits.")
        await asyncio.sleep(timer)
        await protection.delete()
