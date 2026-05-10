#Tg:MaheshChauhan/DroneBots
#Github.com/Vasusen-code

import asyncio, time

from .. import bot as Drone, Bot, is_authorized, get_target_chat, AUTH
from main.plugins.pyroplug import get_bulk_msg
from main.plugins.helpers import get_link

import main as _main_module

from telethon import events, Button
from pyrogram.errors import FloodWait

batch = []

# ---------------------------------------------------------------------------
# Helper: wait for a single reply from a specific user in any chat (DM or group)
# Uses a temporary event handler filtered by chat + sender so it ignores
# messages from other users in the same group.
# ---------------------------------------------------------------------------
async def _ask(chat_id, sender_id, prompt, timeout=120):
    """Send `prompt` and wait up to `timeout` seconds for a reply from `sender_id`.
    Returns the reply text, or None on timeout."""
    try:
        await Drone.send_message(chat_id, prompt, buttons=Button.force_reply())
    except Exception:
        await Drone.send_message(chat_id, prompt)

    result_queue = asyncio.Queue(maxsize=1)

    async def _temp_handler(ev):
        if result_queue.full():
            return
        await result_queue.put(ev.text or "")
        raise events.StopPropagation

    Drone.add_event_handler(
        _temp_handler,
        events.NewMessage(chats=chat_id, from_users=sender_id, incoming=True)
    )
    try:
        return await asyncio.wait_for(result_queue.get(), timeout=timeout)
    except asyncio.TimeoutError:
        return None
    finally:
        Drone.remove_event_handler(_temp_handler)


# ---------------------------------------------------------------------------
# /cancel
# ---------------------------------------------------------------------------
@Drone.on(events.NewMessage(incoming=True, pattern=r'/cancel(?:@\w+)?(?:\s|$)'))
async def cancel(event):
    if event.sender_id != AUTH:
        return
    if event.sender_id not in batch:
        return await event.reply("No active batch found for you.")
    batch.remove(event.sender_id)
    await event.reply("✅ Batch cancelled.")


# ---------------------------------------------------------------------------
# /batch — interactive in both private and group chats
# ---------------------------------------------------------------------------
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
        return await event.reply(
            "You already have a batch running.\nSend /cancel to stop it first."
        )

    chat_id = event.chat_id
    sender_id = event.sender_id

    # --- Step 1: Ask for the starting link ---
    raw_link = await _ask(
        chat_id, sender_id,
        "📎 **Step 1/2** — Send the message link to start saving from:\n"
        "(e.g. `https://t.me/c/1234567890/100`)",
        timeout=120
    )
    if raw_link is None:
        await Drone.send_message(chat_id, "⏱ Timed out. Send /batch again.")
        return

    link = get_link(raw_link.strip())
    if not link:
        await Drone.send_message(chat_id, "❌ No valid link found. Send /batch again.")
        return

    # --- Step 2: Ask for count ---
    raw_count = await _ask(
        chat_id, sender_id,
        "🔢 **Step 2/2** — How many messages to save? (max 100):",
        timeout=60
    )
    if raw_count is None:
        await Drone.send_message(chat_id, "⏱ Timed out. Send /batch again.")
        return

    try:
        count = int(raw_count.strip())
    except ValueError:
        await Drone.send_message(chat_id, "❌ Must be a number. Send /batch again.")
        return

    if count < 1:
        await Drone.send_message(chat_id, "❌ Count must be at least 1.")
        return
    if count > 100:
        await Drone.send_message(chat_id, "⚠️ Capping at 100 messages.")
        count = 100

    # Destination: setchat target, or the current chat
    target = get_target_chat(sender_id) or chat_id

    batch.append(sender_id)
    await Drone.send_message(
        chat_id,
        f"✅ **Batch started!**\n\n"
        f"• Link: `{link}`\n"
        f"• Count: **{count}** messages\n"
        f"• Destination: `{target}`\n\n"
        f"Send /cancel to stop at any time."
    )

    await run_batch(_main_module.userbot, Bot, sender_id, link, count, target, chat_id)

    if sender_id in batch:
        batch.remove(sender_id)


# ---------------------------------------------------------------------------
# Core batch runner
# ---------------------------------------------------------------------------
async def run_batch(userbot, client, sender, link, _range, target, status_chat=None):
    if status_chat is None:
        status_chat = sender

    for i in range(_range):
        if sender not in batch:
            await client.send_message(status_chat, "🛑 Batch cancelled.")
            return

        timer = 10 if i < 50 else 15
        if 't.me/c/' not in link:
            timer = 10

        try:
            await get_bulk_msg(userbot, client, target, link, i)
        except FloodWait as fw:
            if int(fw.x) > 299:
                await client.send_message(
                    status_chat, "⚠️ Floodwait > 5 min — batch stopped."
                )
                return
            await asyncio.sleep(fw.x + 5)
            try:
                await get_bulk_msg(userbot, client, target, link, i)
            except Exception as e:
                await client.send_message(status_chat, f"⚠️ Skipped #{i+1}: {e}")
        except Exception as e:
            await client.send_message(status_chat, f"⚠️ Skipped #{i+1}: {e}")

        progress = await client.send_message(
            status_chat, f"`Saving {i+1}/{_range}...` sleeping {timer}s"
        )
        await asyncio.sleep(timer)
        await progress.delete()

    await client.send_message(
        status_chat,
        f"✅ **Batch complete!**\n\nSaved {_range} messages → `{target}`"
    )
