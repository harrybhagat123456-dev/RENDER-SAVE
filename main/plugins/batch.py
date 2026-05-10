#Tg:MaheshChauhan/DroneBots
#Github.com/Vasusen-code

import time, os, asyncio

from .. import bot as Drone, Bot, is_authorized, get_target_chat
from main.plugins.pyroplug import get_bulk_msg
from main.plugins.helpers import get_link, screenshot

import main as _main_module

from telethon import events, Button, errors
from pyrogram.errors import FloodWait

batch = []

@Drone.on(events.NewMessage(incoming=True, pattern=r'/cancel(?:@\w+)?(?:\s|$)'))
async def cancel(event):
    if not is_authorized(event.sender_id):
        return
    if event.sender_id not in batch:
        return await event.reply("No batch active.")
    batch.remove(event.sender_id)
    await event.reply("Batch cancelled.")


@Drone.on(events.NewMessage(incoming=True, pattern=r'/batch(?:@\w+)?(?:\s|$)'))
async def _batch(event):
    if not is_authorized(event.sender_id):
        return

    if not _main_module.userbot:
        await event.reply(
            "⚠️ **Userbot is not logged in.**\n\nSend /login to authenticate first."
        )
        return

    if event.sender_id in batch:
        return await event.reply("You already have a batch running. Send /cancel to stop it.")

    # --- GROUP MODE: inline args required ---
    # Usage in group: /batch <link> <count>
    if not event.is_private:
        parts = event.text.strip().split()
        # Strip /batch or /batch@botname
        args = [p for p in parts[1:] if p]

        link = None
        count = None

        for arg in args:
            parsed = get_link(arg)
            if parsed:
                link = parsed
            else:
                try:
                    count = int(arg)
                except ValueError:
                    pass

        if not link or not count:
            await event.reply(
                "**Group Batch Usage:**\n\n"
                "`/batch <message_link> <count>`\n\n"
                "**Example:**\n"
                "`/batch https://t.me/c/1234567890/100 50`\n\n"
                "This saves 50 messages starting from message #100.\n"
                "Max count: 100 messages.\n\n"
                "Or use `/batch` in a private chat with me for interactive mode."
            )
            return

        if count > 100:
            await event.reply("Max count is 100 messages per batch.")
            return

        # Destination: setchat target or the group itself
        target = get_target_chat(event.sender_id) or event.chat_id
        status_chat = event.chat_id

        batch.append(event.sender_id)
        await event.reply(
            f"✅ **Batch started!**\n\n"
            f"• Link: `{link}`\n"
            f"• Count: **{count}** messages\n"
            f"• Destination: `{target}`\n\n"
            f"Send /cancel to stop."
        )
        await run_batch(_main_module.userbot, Bot, event.sender_id, link, count, target, status_chat)
        if event.sender_id in batch:
            batch.remove(event.sender_id)
        return

    # --- PRIVATE MODE: interactive conversation ---
    async with Drone.conversation(event.chat_id) as conv:
        await conv.send_message(
            "Send me the message link you want to start saving from, as a reply to this message.",
            buttons=Button.force_reply()
        )
        try:
            link_msg = await conv.get_response()
            try:
                _link = get_link(link_msg.text)
                if not _link:
                    await conv.send_message("No valid link found. Send /batch again.")
                    return conv.cancel()
            except Exception:
                await conv.send_message("No link found.")
                return conv.cancel()
        except Exception as e:
            print(e)
            await conv.send_message("Cannot wait longer for your response!")
            return conv.cancel()

        await conv.send_message(
            "Send me the number of files/range you want to save from the given message. (Max 100)",
            buttons=Button.force_reply()
        )
        try:
            _range_msg = await conv.get_response()
        except Exception as e:
            print(e)
            await conv.send_message("Cannot wait longer for your response!")
            return conv.cancel()

        try:
            value = int(_range_msg.text.strip())
            if value > 100:
                await conv.send_message("You can only get up to 100 files in a single batch.")
                return conv.cancel()
        except ValueError:
            await conv.send_message("Range must be an integer!")
            return conv.cancel()

        # Destination: setchat target or sender DM
        target = get_target_chat(event.sender_id) or event.sender_id
        status_chat = event.sender_id

        batch.append(event.sender_id)
        await conv.send_message(
            f"✅ **Batch started!**\n\n"
            f"• Link: `{_link}`\n"
            f"• Count: **{value}** messages\n"
            f"• Destination: `{target}`\n\n"
            f"Send /cancel to stop."
        )
        conv.cancel()
        await run_batch(_main_module.userbot, Bot, event.sender_id, _link, value, target, status_chat)
        if event.sender_id in batch:
            batch.remove(event.sender_id)


async def run_batch(userbot, client, sender, link, _range, target, status_chat=None):
    if status_chat is None:
        status_chat = sender
    for i in range(_range):
        timer = 10 if i < 50 else 15
        if 't.me/c/' not in link:
            timer = 10
        if sender not in batch:
            await client.send_message(status_chat, "✅ Batch completed.")
            return
        try:
            await get_bulk_msg(userbot, client, target, link, i)
        except FloodWait as fw:
            if int(fw.x) > 299:
                await client.send_message(status_chat, "⚠️ Cancelling batch — floodwait > 5 minutes.")
                break
            await asyncio.sleep(fw.x + 5)
            try:
                await get_bulk_msg(userbot, client, target, link, i)
            except Exception as e:
                await client.send_message(status_chat, f"⚠️ Skipped message {i+1}: {e}")
        except Exception as e:
            await client.send_message(status_chat, f"⚠️ Skipped message {i+1}: {e}")
        protection = await client.send_message(status_chat, f"`Saving... {i+1}/{_range}` — sleeping {timer}s")
        await asyncio.sleep(timer)
        await protection.delete()
    await client.send_message(status_chat, f"✅ **Batch complete!** Saved {_range} messages to `{target}`.")
