import asyncio

from .. import bot as Drone, Bot, is_authorized, get_target_chat
from main.plugins.pyroplug import get_bulk_msg, msg_map
from main.plugins.helpers import get_link

import main as _main_module

from telethon import events, Button
from pyrogram.errors import FloodWait

_TIMEOUT = 120


def _parse_link(link):
    try:
        if 't.me/c/' in link:
            parts = link.rstrip('/').split('/')
            chat = int('-100' + parts[-2])
            msg_id = int(parts[-1])
            return chat, msg_id
        elif 't.me/b/' in link:
            parts = link.rstrip('/').split('/')
            return str(parts[-2]), int(parts[-1])
        elif 't.me/' in link:
            parts = link.rstrip('/').split('/')
            return str(parts[-2]), int(parts[-1])
    except Exception:
        pass
    return None, None


def _find_resume_point(chat_id):
    saved_ids = [msg_id for (chat, msg_id) in msg_map.keys() if chat == chat_id]
    if not saved_ids:
        return 0, None
    return len(saved_ids), max(saved_ids)


@Drone.on(events.NewMessage(incoming=True, pattern=r'/history(?:@\w+)?(?:\s|$)'))
async def history_cmd(event):
    if not is_authorized(event.sender_id):
        return
    if not event.is_private:
        await event.reply("Please use /history in a private chat with me.")
        return

    if not _main_module.userbot:
        await event.reply("⚠️ **Userbot is not logged in.**\n\nSend /login to authenticate first.")
        return

    async with Drone.conversation(event.chat_id, timeout=_TIMEOUT) as conv:
        await conv.send_message(
            "📎 Send the **starting message link** to scan from:\n"
            "(e.g. `https://t.me/c/1234567890/100`)",
            buttons=Button.force_reply()
        )
        try:
            link_msg = await conv.get_response(timeout=_TIMEOUT)
        except asyncio.TimeoutError:
            await conv.send_message("⏱ Timed out. Send /history again.")
            return

        raw_link = link_msg.text.strip() if link_msg and link_msg.text else ""
        link = get_link(raw_link) or raw_link

        chat_id, start_msg_id = _parse_link(link)
        if chat_id is None:
            await conv.send_message("❌ Could not parse that link.")
            return

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

        await conv.send_message(
            "📦 How many messages to save from the resume point? (max **200**):",
            buttons=Button.force_reply()
        )
        try:
            count_msg = await conv.get_response(timeout=_TIMEOUT)
        except asyncio.TimeoutError:
            await conv.send_message("⏱ Timed out. Send /history again.")
            return

        try:
            count = min(max(int(count_msg.text.strip()), 1), 200)
        except (ValueError, AttributeError):
            await conv.send_message("❌ Invalid number. Send /history again.")
            return

        if isinstance(chat_id, int):
            short_id = str(chat_id)[4:]
            resume_link = f"https://t.me/c/{short_id}/{resume_from}"
        else:
            resume_link = f"https://t.me/{chat_id}/{resume_from}"

        target = get_target_chat(event.sender_id) or event.sender_id
        dest_label = f"`{target}`" if target != event.sender_id else "your DM"

        await conv.send_message(
            f"✅ **Starting resume batch**\n\n"
            f"• From: `{resume_link}`\n"
            f"• Count: **{count}** messages\n"
            f"• Destination: {dest_label}\n\nUse /cancel to stop."
        )

        await _run_history_batch(_main_module.userbot, Bot, event.sender_id, resume_link, count, target)


async def _run_history_batch(userbot, client, sender, start_link, count, target):
    for i in range(count):
        try:
            await get_bulk_msg(userbot, client, target, start_link, i)
        except FloodWait as fw:
            if fw.x > 299:
                await client.send_message(sender, "⚠️ Floodwait > 5 min — stopping batch.")
                return
            await asyncio.sleep(fw.x + 5)
            try:
                await get_bulk_msg(userbot, client, target, start_link, i)
            except Exception as e:
                await client.send_message(sender, f"⚠️ Skipped message {i+1}: {e}")
        except Exception as e:
            await client.send_message(sender, f"⚠️ Skipped message {i+1}: {e}")
        await asyncio.sleep(8)
    await client.send_message(sender, f"✅ History batch complete — saved {count} messages.")
