import os
from .. import bot as Drone, AUTH
from main.plugins.pyroplug import msg_map, _pinned_cache, _resolved_peers
from main.plugins.setchat import _user_target_chats
from main.plugins.batch import batch

import main as _main_module
from telethon import events

@Drone.on(events.NewMessage(incoming=True, from_users=AUTH, pattern='/reset'))
async def reset_cmd(event):
    cleared = []

    # Clear message history map + delete persisted file
    count = len(msg_map)
    msg_map.clear()
    cleared.append(f"Message history ({count} entries)")
    try:
        from .. import MSG_MAP_FILE
        if os.path.exists(MSG_MAP_FILE):
            os.remove(MSG_MAP_FILE)
    except Exception:
        pass

    # Clear internal caches
    _pinned_cache.clear()
    _resolved_peers.clear()
    cleared.append("Pinned & peer caches")

    # Clear any active batch
    if batch:
        batch.clear()
        cleared.append("Active batch")

    # Clear transfer chat settings
    if _user_target_chats:
        _user_target_chats.clear()
        cleared.append("Transfer chat settings")

    lines = "\n".join(f"• {item}" for item in cleared)
    await event.reply(
        f"✅ **Bot state reset!**\n\n"
        f"**Cleared:**\n{lines}\n\n"
        f"The bot is now in a clean state.\n"
        f"Userbot session is untouched — use /logout to disconnect it."
    )
