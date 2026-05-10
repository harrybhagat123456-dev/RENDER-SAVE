from .. import bot as Drone
from telethon import events

HELP_TEXT = """
**Save Restricted Content Bot**

**Account Commands:**
/login — Login your Telegram account (userbot)
/logout — Logout and remove saved session

**Save Commands:**
/batch — Save multiple messages in bulk
/history — Resume saving from where you left off
/cancel — Cancel the active batch operation

**Transfer Commands:**
/setchat — Set a channel to send saved content
/mychat — View your current transfer channel
/clearchat — Reset transfer channel to your DM

**Other:**
/start — Welcome message
/help — Show this help message
/reset — Clear all saved history and reset bot state

**How to use:**
1. Send /login and authenticate your account
2. Send any Telegram message link to save it
3. For bulk saving, use /batch
4. To save to a channel instead of DM, use /setchat
""".strip()

@Drone.on(events.NewMessage(incoming=True, pattern='/help'))
async def help_cmd(event):
    await event.reply(HELP_TEXT)
