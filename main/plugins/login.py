# Login / Logout plugin
# Lets the AUTH user authenticate a Telegram account interactively through
# the bot — no SESSION env-var required.
#
# Commands
# --------
# /login   — start interactive phone + OTP (+ 2FA password if needed) flow
# /logout  — disconnect the userbot and delete the saved session file

import os
import asyncio
import traceback

from .. import bot as Drone, API_ID, API_HASH, SESSION_FILE, AUTH
import main as _main_module

from telethon import events
from pyrogram import Client
from pyrogram.errors import (
    SessionPasswordNeeded,
    PhoneCodeInvalid,
    PhoneCodeExpired,
    PhoneNumberInvalid,
    BadRequest,
)

_TIMEOUT = 120


async def _ask(conv, question, timeout=_TIMEOUT):
    """Send a question and wait for the user's next text reply."""
    await conv.send_message(question)
    try:
        reply = await conv.get_reply(timeout=timeout)
        return reply.text.strip() if reply and reply.text else None
    except asyncio.TimeoutError:
        await conv.send_message("⏱ Timed out. Please send /login again.")
        return None


@Drone.on(events.NewMessage(incoming=True, from_users=AUTH, pattern='/login'))
async def login_cmd(event):
    if not event.is_private:
        await event.reply("Please use /login in a private chat with me.")
        return

    if _main_module.userbot and _main_module.userbot.is_connected:
        await event.reply(
            "Userbot is already logged in. Send /logout first if you want to switch accounts."
        )
        return

    async with Drone.conversation(event.chat_id, timeout=_TIMEOUT) as conv:
        phone = await _ask(
            conv,
            "📱 Send your phone number in international format\n(e.g. `+919876543210`):"
        )
        if not phone:
            return

        # Fresh in-memory Pyrogram client — no session file created on disk
        temp_client = Client(
            name="login_temp",
            api_id=API_ID,
            api_hash=API_HASH,
            in_memory=True,
        )

        try:
            await temp_client.connect()
        except Exception as e:
            await conv.send_message(f"❌ Could not connect to Telegram: {e}")
            return

        # Request OTP
        try:
            sent = await temp_client.send_code(phone)
        except PhoneNumberInvalid:
            await conv.send_message("❌ That phone number is invalid. Try /login again.")
            await temp_client.disconnect()
            return
        except Exception as e:
            await conv.send_message(f"❌ Failed to send OTP: {e}")
            await temp_client.disconnect()
            return

        code = await _ask(
            conv,
            "🔐 OTP sent! Enter the code (spaces are fine, e.g. `1 2 3 4 5` or `12345`):"
        )
        if not code:
            await temp_client.disconnect()
            return

        code = code.replace(" ", "")

        # Sign in
        try:
            await temp_client.sign_in(phone, sent.phone_code_hash, code)

        except SessionPasswordNeeded:
            password = await _ask(conv, "🔒 2FA is enabled. Enter your password:")
            if not password:
                await temp_client.disconnect()
                return
            try:
                await temp_client.check_password(password)
            except BadRequest as e:
                await conv.send_message(f"❌ Wrong password: {e}")
                await temp_client.disconnect()
                return
            except Exception as e:
                await conv.send_message(f"❌ 2FA check failed: {e}")
                await temp_client.disconnect()
                return

        except PhoneCodeInvalid:
            await conv.send_message("❌ Invalid code. Please try /login again.")
            await temp_client.disconnect()
            return

        except PhoneCodeExpired:
            await conv.send_message("❌ Code expired. Please try /login again.")
            await temp_client.disconnect()
            return

        except Exception as e:
            await conv.send_message(f"❌ Sign-in failed: {e}")
            traceback.print_exc()
            await temp_client.disconnect()
            return

        # Export and persist session string
        try:
            session_string = await temp_client.export_session_string()
            with open(SESSION_FILE, "w") as f:
                f.write(session_string)
        except Exception as e:
            await conv.send_message(f"❌ Could not save session: {e}")
            await temp_client.disconnect()
            return

        # Attach as the live userbot
        _main_module.userbot.set(temp_client)

        try:
            me = await temp_client.get_me()
            name = f"{me.first_name or ''} {me.last_name or ''}".strip() or "Unknown"
            username = f"@{me.username}" if me.username else "(no username)"
        except Exception:
            name, username = "Unknown", ""

        await conv.send_message(
            f"✅ **Logged in successfully!**\n\n"
            f"**Account:** {name} {username}\n"
            f"**Phone:** `{phone}`\n\n"
            f"Session saved — bot will remember this across restarts.\n"
            f"Use /logout to disconnect."
        )


@Drone.on(events.NewMessage(incoming=True, from_users=AUTH, pattern='/logout'))
async def logout_cmd(event):
    if not _main_module.userbot:
        await event.reply("No userbot is currently logged in.")
        return

    # Grab the underlying client before clearing the ref
    underlying = _main_module.userbot._client

    _main_module.userbot.clear()

    if underlying is not None:
        try:
            await underlying.log_out()
        except Exception:
            pass
        try:
            await underlying.disconnect()
        except Exception:
            pass

    # Remove saved session file
    if os.path.exists(SESSION_FILE):
        try:
            os.remove(SESSION_FILE)
        except Exception:
            pass

    await event.reply(
        "✅ **Logged out.**\n\n"
        "The userbot session has been terminated.\n"
        "Use /login to authenticate again."
    )
