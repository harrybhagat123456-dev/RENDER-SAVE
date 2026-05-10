# Login / Logout plugin
# Commands: /login  — interactive phone + OTP + optional 2FA flow
#           /logout — disconnect userbot and delete saved session

import os
import asyncio
import traceback

from .. import bot as Drone, API_ID, API_HASH, SESSION_FILE, AUTH
import main as _main_module

from telethon import events, Button
from pyrogram import Client
from pyrogram.errors import (
    SessionPasswordNeeded,
    PhoneCodeInvalid,
    PhoneCodeExpired,
    PhoneNumberInvalid,
    BadRequest,
)

_TIMEOUT = 300   # 5 minutes — enough time to receive and enter OTP


async def _ask(conv, question, timeout=_TIMEOUT):
    """
    Send a question with a force_reply button (so Telegram auto-opens the
    reply box) then wait for ANY response in the conversation — not just a
    Telegram-reply to that specific message.
    """
    await conv.send_message(question, buttons=Button.force_reply())
    try:
        resp = await conv.get_response(timeout=timeout)
        return resp.text.strip() if resp and resp.text else None
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
            "Userbot is already logged in.\n"
            "Send /logout first if you want to switch accounts."
        )
        return

    async with Drone.conversation(event.chat_id, timeout=_TIMEOUT) as conv:

        # ── Step 1: phone number ──────────────────────────────────────────
        phone = await _ask(
            conv,
            "📱 **Enter your phone number** in international format\n"
            "Example: `+919876543210`"
        )
        if not phone:
            return

        # Normalise: strip spaces/dashes the user might add
        phone = phone.replace(" ", "").replace("-", "")
        if not phone.startswith("+"):
            phone = "+" + phone

        await conv.send_message("⏳ Connecting to Telegram…")

        # ── Fresh in-memory Pyrogram client ───────────────────────────────
        temp_client = Client(
            name="login_temp",
            api_id=API_ID,
            api_hash=API_HASH,
            in_memory=True,
        )

        try:
            await temp_client.connect()
        except Exception as e:
            await conv.send_message(f"❌ Could not connect to Telegram:\n`{e}`")
            return

        # ── Step 2: send OTP ──────────────────────────────────────────────
        try:
            sent = await temp_client.send_code(phone)
        except PhoneNumberInvalid:
            await conv.send_message(
                "❌ That phone number is invalid.\n"
                "Send /login and try again with a correct number."
            )
            await temp_client.disconnect()
            return
        except Exception as e:
            await conv.send_message(f"❌ Failed to send OTP:\n`{e}`")
            await temp_client.disconnect()
            return

        # ── Step 3: OTP code ──────────────────────────────────────────────
        code = await _ask(
            conv,
            "🔐 **OTP sent to your Telegram!**\n\n"
            "Enter the code you received.\n"
            "Spaces are fine — e.g. `1 2 3 4 5` or `12345`"
        )
        if not code:
            await temp_client.disconnect()
            return

        code = code.replace(" ", "")

        # ── Step 4: sign in ───────────────────────────────────────────────
        try:
            await temp_client.sign_in(phone, sent.phone_code_hash, code)

        except SessionPasswordNeeded:
            # ── Step 4b: 2FA password ─────────────────────────────────────
            password = await _ask(
                conv,
                "🔒 **Two-step verification is enabled.**\n\nEnter your 2FA password:"
            )
            if not password:
                await temp_client.disconnect()
                return
            try:
                await temp_client.check_password(password)
            except BadRequest as e:
                await conv.send_message(f"❌ Wrong 2FA password:\n`{e}`")
                await temp_client.disconnect()
                return
            except Exception as e:
                await conv.send_message(f"❌ 2FA check failed:\n`{e}`")
                await temp_client.disconnect()
                return

        except PhoneCodeInvalid:
            await conv.send_message(
                "❌ That code is invalid.\n"
                "Send /login and try again."
            )
            await temp_client.disconnect()
            return

        except PhoneCodeExpired:
            await conv.send_message(
                "❌ That code has expired.\n"
                "Send /login to request a fresh OTP."
            )
            await temp_client.disconnect()
            return

        except Exception as e:
            await conv.send_message(f"❌ Sign-in failed:\n`{e}`")
            traceback.print_exc()
            await temp_client.disconnect()
            return

        # ── Step 5: export & persist session ─────────────────────────────
        try:
            session_string = await temp_client.export_session_string()
            with open(SESSION_FILE, "w") as f:
                f.write(session_string)
        except Exception as e:
            await conv.send_message(f"❌ Could not save session:\n`{e}`")
            await temp_client.disconnect()
            return

        # ── Step 6: attach as live userbot ────────────────────────────────
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
            f"Session saved — the bot will remember this login across restarts.\n"
            f"Use /logout to disconnect."
        )


@Drone.on(events.NewMessage(incoming=True, from_users=AUTH, pattern='/logout'))
async def logout_cmd(event):
    if not _main_module.userbot:
        await event.reply("No userbot is currently logged in.")
        return

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

    if os.path.exists(SESSION_FILE):
        try:
            os.remove(SESSION_FILE)
        except Exception:
            pass

    await event.reply(
        "✅ **Logged out.**\n\n"
        "The userbot session has been terminated and the saved session deleted.\n"
        "Use /login to authenticate again."
    )
