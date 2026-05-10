import os
from .. import bot as Drone, AUTH, is_authorized
from main.plugins.pyroplug import msg_map, _pinned_cache, _resolved_peers
from main.plugins.setchat import _user_target_chats
from main.plugins.batch import batch

import main as _main_module
from telethon import events

@Drone.on(events.NewMessage(incoming=True, pattern=r'/reset(?:@\w+)?(?:\s|$)'))
async def reset_cmd(event):
    if event.sender_id != AUTH:   # owner-only
        return

    cleared = []

    count = len(msg_map)
    msg_map.clear()
    cleared.append(f"Message history ({count} entries)")
    try:
        from .. import MSG_MAP_FILE
        if os.path.exists(MSG_MAP_FILE):
            os.remove(MSG_MAP_FILE)
    except Exception:
        pass

    _pinned_cache.clear()
    _resolved_peers.clear()
    cleared.append("Pinned & peer caches")

    if batch:
        batch.clear()
        cleared.append("Active batch")

    if _user_target_chats:
        _user_target_chats.clear()
        cleared.append("Transfer chat settings")

    lines = "\n".join(f"• {item}" for item in cleared)
    await event.reply(
        f"✅ **Bot state reset!**\n\n**Cleared:**\n{lines}\n\n"
        f"Userbot session is untouched — use /logout to disconnect it."
    )
