from .. import bot as Drone, is_authorized
from telethon import events

HELP_TEXT = """
**Save Restricted Content Bot**

**Account Commands:**
/login — Login your Telegram account (userbot)
/logout — Logout and remove saved session

**Save Commands:**
/batch — Save multiple messages in bulk (up to 5000)
/clone — Clone entire chat with link rewriting
/history — Resume saving from where you left off
/pinned — Save all pinned messages from a chat
/cancel — Cancel the active batch operation

**Transfer Commands:**
/setchat — Set a channel to send saved content
/mychat — View your current transfer channel
/clearchat — Reset transfer channel to default

**Auth Commands** _(owner only)_:
/addauth `USER_ID` — Grant a user access to bot commands
/removeauth `USER_ID` — Revoke a user's access
/listauth — List all currently authorized users

**Other:**
/start — Welcome message
/help — Show this help message
/status — Check userbot connection and session status
/reset — Clear all saved history and reset bot state _(owner only)_

**How to use:**
1. Send /login and authenticate your account
2. Send any Telegram message link to save it
3. For bulk saving, use /batch (up to 5000 messages)
4. Use /pinned to fetch all pinned messages from a channel
5. To save to a specific channel instead, use /setchat
6. Use /addauth to let other users save content too
""".strip()

@Drone.on(events.NewMessage(incoming=True, pattern=r'/help(?:@\w+)?(?:\s|$)'))
async def help_cmd(event):
    # In groups, only auth users get help
    if not event.is_private and not is_authorized(event.sender_id):
        return
    await event.reply(HELP_TEXT)
