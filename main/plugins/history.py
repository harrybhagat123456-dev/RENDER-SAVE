# /history — Resume / scan command
#
# Flow:
#  1. User sends /history
#  2. Bot asks for the starting message link
#  3. Bot parses chat_id + start_msg_id from the link
#  4. Bot scans msg_map to find the highest msg_id already saved from that chat
#  5. Reports what was found and sets the resume point
#  6. Asks how many messages to save from the resume point (max 200)
#  7. Uses the user's /setchat destination (or their DM) and runs the batch

import asyncio

from .. import bot as Drone, Bot, AUTH
from main.plugins.pyroplug import get_bulk_msg, msg_map
from main.plugins.helpers import get_link
from main.plugins.setchat import get_target_chat

import main as _main_module

from telethon import events, Button
from pyrogram.errors import FloodWait

_TIMEOUT = 120


def _parse_link(link):
    """
    Return (chat_id, msg_id) from a t.me link, or (None, None) on failure.
    chat_id is int for private chats (-100XXX) or str for public (@username).
    """
    try:
        if 't.me/c/' in link:
            parts = link.rstrip('/').split('/')
            chat = int('-100' + parts[-2])
            msg_id = int(parts[-1])
            return chat, msg_id
        elif 't.me/b/' in link:
            parts = link.rstrip('/').split('/')
            chat = str(parts[-2])
            msg_id = int(parts[-1])
            return chat, msg_id
        elif 't.me/' in link:
            parts = link.rstrip('/').split('/')
            chat = str(parts[-2])
            msg_id = int(parts[-1])
            return chat, msg_id
    except Exception:
        pass
    return None, None


def _find_resume_point(chat_id):
    """
    Scan msg_map for the highest msg_id already saved from chat_id.
    Returns (count_saved, highest_msg_id) or (0, None) if nothing found.
    """
    saved_ids = [
        msg_id for (chat, msg_id) in msg_map.keys()
        if chat == chat_id
    ]
    if not saved_ids:
        return 0, None
    return len(saved_ids), max(saved_ids)


@Drone.on(events.NewMessage(incoming=True, from_users=AUTH, pattern='/history'))
async def history_cmd(event):
    if not event.is_private:
        await event.reply("Please use /history in a private chat with me.")
        return

    if not _main_module.userbot:
        await event.reply(
            "⚠️ **Userbot is not logged in.**\n\n"
            "Send /login to authenticate first."
        )
        return

    async with Drone.conversation(event.chat_id, timeout=_TIMEOUT) as conv:

        # Step 1 — get the starting message link
        await conv.send_message(
            "📎 Send the **starting message link** to scan from:\n"
            "(e.g. `https://t.me/c/1234567890/100` or `https://t.me/username/100`)",
            buttons=Button.force_reply()
        )
        try:
            link_msg = await conv.get_reply(timeout=_TIMEOUT)
        except asyncio.TimeoutError:
            await conv.send_message("⏱ Timed out. Send /history again.")
            return

        raw_link = link_msg.text.strip() if link_msg and link_msg.text else ""
        link = get_link(raw_link) or raw_link

        chat_id, start_msg_id = _parse_link(link)
        if chat_id is None:
            await conv.send_message(
                "❌ Could not parse that link. Make sure it's a valid Telegram message link."
            )
            return

        # Step 2 — scan msg_map for this chat
        count_saved, last_saved_id = _find_resume_point(chat_id)

        if count_saved == 0:
            resume_from = start_msg_id
            status_text = (
                f"🔍 **No history found** for this chat.\n\n"
                f"Starting fresh from message **#{start_msg_id}**."
            )
        else:
            resume_from = last_saved_id + 1
            status_text = (
                f"📊 **History found!**\n\n"
                f"• Messages already saved: **{count_saved}**\n"
                f"• Last saved message: **#{last_saved_id}**\n"
                f"• Resuming from: **#{resume_from}**"
            )

        await conv.send_message(status_text)

        # Step 3 — how many messages to save
        await conv.send_message(
            "📦 How many messages to save from the resume point?\n"
            "(Enter a number, max **200**):",
            buttons=Button.force_reply()
        )
        try:
            count_msg = await conv.get_reply(timeout=_TIMEOUT)
        except asyncio.TimeoutError:
            await conv.send_message("⏱ Timed out. Send /history again.")
            return

        try:
            count = int(count_msg.text.strip())
            if count < 1:
                raise ValueError
            count = min(count, 200)
        except (ValueError, AttributeError):
            await conv.send_message("❌ Invalid number. Send /history again.")
            return

        # Step 4 — build the resume link (same chat, new starting msg_id)
        if isinstance(chat_id, int):
            short_id = str(chat_id)[4:]  # strip -100
            resume_link = f"https://t.me/c/{short_id}/{resume_from}"
        else:
            resume_link = f"https://t.me/{chat_id}/{resume_from}"

        # Step 5 — determine destination
        target = get_target_chat(event.sender_id) or event.sender_id
        dest_label = f"`{target}`" if target != event.sender_id else "your DM"

        await conv.send_message(
            f"✅ **Starting resume batch**\n\n"
            f"• From: `{resume_link}`\n"
            f"• Count: **{count}** messages\n"
            f"• Destination: {dest_label}\n\n"
            f"Use /cancel to stop."
        )

        # Step 6 — run the batch
        await _run_history_batch(
            _main_module.userbot, Bot, event.sender_id,
            resume_link, count, target
        )


async def _run_history_batch(userbot, client, sender, start_link, count, target):
    for i in range(count):
        try:
            await get_bulk_msg(userbot, client, target, start_link, i)
        except FloodWait as fw:
            if fw.x > 299:
                await client.send_message(
                    sender,
                    "⚠️ Floodwait > 5 min — stopping batch."
                )
                return
            await asyncio.sleep(fw.x + 5)
            try:
                await get_bulk_msg(userbot, client, target, start_link, i)
            except Exception as e:
                await client.send_message(sender, f"⚠️ Skipped message {i+1}: {e}")
        except Exception as e:
            await client.send_message(sender, f"⚠️ Skipped message {i+1}: {e}")

        # short sleep to avoid flood
        await asyncio.sleep(8)

    await client.send_message(sender, f"✅ History batch complete — saved {count} messages.")
