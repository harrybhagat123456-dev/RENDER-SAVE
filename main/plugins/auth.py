# Auth management plugin
# Only the owner (AUTH env-var) can add/remove/list authorized users.
#
# /addauth USER_ID    — grant a user access to all bot commands
# /removeauth USER_ID — revoke access
# /listauth           — show all authorized users

from .. import bot as Drone, AUTH, AUTHORIZED_USERS, save_auth_users
from telethon import events


def _owner_only(func):
    """Decorator: silently ignore if sender is not the owner."""
    async def wrapper(event):
        if event.sender_id != AUTH:
            return
        return await func(event)
    return wrapper


@Drone.on(events.NewMessage(incoming=True, pattern=r'/addauth(?:@\w+)?(?:\s|$)'))
@_owner_only
async def addauth_cmd(event):
    args = event.text.split(maxsplit=1)
    if len(args) < 2:
        await event.reply(
            "**Add Authorized User**\n\n"
            "Usage: `/addauth USER_ID`\n"
            "Get a user's ID by forwarding their message to @userinfobot."
        )
        return
    try:
        uid = int(args[1].strip())
    except ValueError:
        await event.reply("❌ Invalid user ID — must be a number.")
        return

    AUTHORIZED_USERS.add(uid)
    save_auth_users()
    await event.reply(f"✅ User `{uid}` added to authorized users.")


@Drone.on(events.NewMessage(incoming=True, pattern=r'/removeauth(?:@\w+)?(?:\s|$)'))
@_owner_only
async def removeauth_cmd(event):
    args = event.text.split(maxsplit=1)
    if len(args) < 2:
        await event.reply("Usage: `/removeauth USER_ID`")
        return
    try:
        uid = int(args[1].strip())
    except ValueError:
        await event.reply("❌ Invalid user ID — must be a number.")
        return

    if uid == AUTH:
        await event.reply("❌ Cannot remove the owner from the auth list.")
        return

    if uid not in AUTHORIZED_USERS:
        await event.reply(f"ℹ️ User `{uid}` is not in the authorized list.")
        return

    AUTHORIZED_USERS.discard(uid)
    save_auth_users()
    await event.reply(f"✅ User `{uid}` removed from authorized users.")


@Drone.on(events.NewMessage(incoming=True, pattern=r'/listauth(?:@\w+)?(?:\s|$)'))
@_owner_only
async def listauth_cmd(event):
    if not AUTHORIZED_USERS:
        await event.reply("No authorized users set.")
        return
    lines = []
    for uid in sorted(AUTHORIZED_USERS):
        tag = " *(owner)*" if uid == AUTH else ""
        lines.append(f"• `{uid}`{tag}")
    await event.reply("**Authorized Users:**\n" + "\n".join(lines))
