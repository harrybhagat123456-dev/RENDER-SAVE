#Tg:MaheshChauhan/DroneBots
#Github.com/Vasusen-code

import asyncio, time

from .. import bot as Drone, Bot, is_authorized, get_target_chat, AUTH
from main.plugins.pyroplug import get_bulk_msg, save_pinned_messages, clone_chat
from main.plugins.helpers import get_link, fw_secs

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
    if not is_authorized(event.sender_id):
        return

    if event.sender_id in batch:
        batch.remove(event.sender_id)
        await event.reply("✅ Cancelled.")
    else:
        await event.reply("No active batch found.")


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
        "🔢 **Step 2/2** — How many messages to save? (max 5000):",
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
    if count > 5000:
        await Drone.send_message(chat_id, "⚠️ Capping at 5000 messages.")
        count = 5000

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
    import math, time as _time
    if status_chat is None:
        status_chat = sender

    start_time = _time.time()
    progress_msg = None
    last_edit = 0.0
    BAR_LEN = 20

    def _bar(done, total):
        pct = min(done / total, 1.0) if total > 0 else 0
        filled = math.floor(pct * BAR_LEN)
        return f"`[{'█' * filled}{'░' * (BAR_LEN - filled)}]` **{pct * 100:.1f}%**"

    def _fmt_secs(s):
        s = max(0, int(s))
        h, s = divmod(s, 3600); m, s = divmod(s, 60)
        parts = []
        if h: parts.append(f"{h}h")
        if m: parts.append(f"{m}m")
        parts.append(f"{s}s")
        return " ".join(parts)

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
            _fw_secs = fw_secs(fw)
            if _fw_secs > 299:
                await client.send_message(
                    status_chat, "⚠️ Floodwait > 5 min — batch stopped."
                )
                return
            await asyncio.sleep(_fw_secs + 5)
            try:
                await get_bulk_msg(userbot, client, target, link, i)
            except Exception as e:
                await client.send_message(status_chat, f"⚠️ Skipped #{i+1}: {e}")
        except Exception as e:
            await client.send_message(status_chat, f"⚠️ Skipped #{i+1}: {e}")

        # Live progress bar (edit same message, throttle to ~1 per 5s)
        now = _time.time()
        if (now - last_edit) >= 5 or (i + 1) == _range:
            done = i + 1
            elapsed = now - start_time
            speed = done / elapsed if elapsed > 0 else 0
            eta = ((elapsed / done) * (_range - done)) if done > 0 else 0
            bar = _bar(done, _range)
            text = (
                f"📦 **Batch — Saving messages**\n\n"
                f"{bar}\n\n"
                f"• **{done}** / **{_range}** messages\n"
                f"• Speed: **{speed:.1f} msg/s**\n"
                f"• Elapsed: **{_fmt_secs(elapsed)}**\n"
                f"• ETA: **{_fmt_secs(eta)}**"
            )
            try:
                if progress_msg:
                    await Drone.edit_message(status_chat, progress_msg, text)
                else:
                    progress_msg = (await Drone.send_message(status_chat, text)).id
            except Exception:
                try:
                    progress_msg = (await Drone.send_message(status_chat, text)).id
                except Exception:
                    pass
            last_edit = now

        await asyncio.sleep(timer)

    elapsed = _time.time() - start_time
    speed = _range / elapsed if elapsed > 0 else 0
    await Drone.send_message(
        status_chat,
        f"✅ **Batch complete!**\n\n"
        f"{_bar(_range, _range)}\n\n"
        f"• Saved: **{_range}** messages → `{target}`\n"
        f"• Total time: **{_fmt_secs(elapsed)}**\n"
        f"• Average speed: **{speed:.1f} msg/s**"
    )


# ---------------------------------------------------------------------------
# /pinned — Save all pinned messages from a source chat
# ---------------------------------------------------------------------------
@Drone.on(events.NewMessage(incoming=True, pattern=r'/pinned(?:@\w+)?(?:\s|$)'))
async def _pinned(event):
    if not is_authorized(event.sender_id):
        return

    if not _main_module.userbot:
        await event.reply(
            "⚠️ **Userbot is not logged in.**\n\nSend /login to authenticate first."
        )
        return

    chat_id = event.chat_id
    sender_id = event.sender_id

    # Ask for the chat link
    raw_link = await _ask(
        chat_id, sender_id,
        "📌 Send the **channel/group link** (or any message link from it) "
        "to fetch pinned messages:\n"
        "(e.g. `https://t.me/c/1234567890/100` or `https://t.me/channelname/1`)",
        timeout=120
    )
    if raw_link is None:
        await Drone.send_message(chat_id, "⏱ Timed out. Send /pinned again.")
        return

    link = get_link(raw_link.strip())
    if not link:
        await Drone.send_message(chat_id, "❌ No valid link found. Send /pinned again.")
        return

    # Parse the chat ID from the link
    if 't.me/c/' in link:
        source_chat = int('-100' + link.split("/")[-2])
    elif 't.me/b/' in link:
        source_chat = str(link.split("/")[-2])
    else:
        source_chat = str(link.split("/")[-2])

    # Destination: setchat target, or the current chat
    target = get_target_chat(sender_id) or chat_id

    status = await Drone.send_message(
        chat_id,
        f"📌 **Fetching pinned messages...**\n\n"
        f"• Source: `{source_chat}`\n"
        f"• Destination: `{target}`"
    )

    try:
        total_found, total_saved = await save_pinned_messages(
            _main_module.userbot, Bot, Drone, source_chat, target, chat_id
        )

        if total_found == 0:
            await status.edit("📌 No pinned messages found in that chat.")
        else:
            await status.edit(
                f"✅ **Pinned messages saved!**\n\n"
                f"• Found: **{total_found}** pinned messages\n"
                f"• Saved: **{total_saved}** → `{target}`"
            )
    except Exception as e:
        await status.edit(f"❌ Failed to save pinned messages: {e}")


# ---------------------------------------------------------------------------
# /clone — 3-phase clone of an entire chat with forward-link fixing
#
# Usage:
#   /clone https://t.me/c/1234567890/1        ← clone entire chat
#   /clone https://t.me/c/1234567890/1 500    ← limit to 500 messages
# ---------------------------------------------------------------------------
@Drone.on(events.NewMessage(incoming=True, pattern=r'/clone(?:@\w+)?(?:\s|$)'))
async def _clone(event):
    if not is_authorized(event.sender_id):
        return

    if not _main_module.userbot:
        await event.reply(
            "⚠️ **Userbot is not logged in.**\n\nSend /login to authenticate first."
        )
        return

    chat_id = event.chat_id
    sender_id = event.sender_id
    args = event.text.split()

    if len(args) < 2:
        await event.reply(
            "**Usage:**\n"
            "`/clone <link>` — clone entire chat\n"
            "`/clone <link> 500` — clone latest 500 messages"
        )
        return

    msg_link = get_link(args[1])
    if not msg_link:
        await event.reply("❌ Invalid link. Send a t.me message link.")
        return

    limit = 0  # 0 = no limit (all messages)
    if len(args) >= 3 and args[2].isdigit():
        limit = int(args[2])
        if limit > 5000:
            await event.reply("⚠️ Capping at 5000 messages.")
            limit = 5000

    # Parse the source chat ID from the link
    if 't.me/c/' in msg_link:
        source_chat = int('-100' + msg_link.split("/")[-2])
    elif 't.me/b/' in msg_link:
        source_chat = str(msg_link.split("/")[-2])
    else:
        source_chat = str(msg_link.split("/")[-2])

    # Destination: setchat target, or the current chat
    target = get_target_chat(sender_id) or chat_id

    status = await Drone.send_message(
        chat_id,
        f"🔄 **Starting clone...**\n\n"
        f"• Source: `{source_chat}`\n"
        f"• Destination: `{target}`\n"
        f"• Limit: {'All messages' if limit == 0 else f'{limit} messages'}\n\n"
        f"⚠️ This may take a very long time for large chats."
    )

    try:
        result = await clone_chat(
            _main_module.userbot, Bot, Drone,
            source_chat, target, chat_id, sender_id, limit
        )

        if "error" in result:
            await status.edit(f"❌ Clone failed: `{result['error']}`")
            return

        await status.edit(
            f"✅ **Clone complete!**\n\n"
            f"• Total messages: **{result['total']}**\n"
            f"• Saved: **{result['saved']}**\n"
            f"• Skipped (already saved): **{result['skipped']}**\n"
            f"• Failed: **{result['failed']}**\n"
            f"• Forward links fixed: **{result['fixed_links']}/{result['deferred_links']}**\n\n"
            f"→ `{target}`"
        )
    except Exception as e:
        await status.edit(f"❌ Clone failed: {e}")
