#Github.com/Vasusen-code

import os
from .. import bot as Drone, is_authorized
from telethon import events, Button

S = '/' + 's' + 't' + 'a' + 'r' + 't'

START_TEXT = """
**Save Restricted Content Bot**

Send me any Telegram message link to save it.
For private channels, send the invite link first.

**Quick start:**
/login — Connect your Telegram account
/help — See all available commands

**Support:** @TeamDrone
""".strip()

@Drone.on(events.callbackquery.CallbackQuery(data="set"))
async def sett(event):
    client = event.client
    await event.delete()
    async with client.conversation(event.chat_id) as conv:
        xx = await conv.send_message(
            "Send me any image for thumbnail as a `reply` to this message.",
            buttons=Button.force_reply()
        )
        x = await conv.get_response()
        if not x.media:
            return await xx.edit("No media found.")
        mime = x.file.mime_type
        if not any(ext in mime for ext in ('png', 'jpg', 'jpeg')):
            return await xx.edit("No image found. Please send a JPG or PNG.")
        await xx.delete()
        t = await client.send_message(event.chat_id, 'Saving thumbnail...')
        path = await client.download_media(x.media)
        if os.path.exists(f'{event.sender_id}.jpg'):
            os.remove(f'{event.sender_id}.jpg')
        os.rename(path, f'./{event.sender_id}.jpg')
        await t.edit("Thumbnail saved!")

@Drone.on(events.callbackquery.CallbackQuery(data="rem"))
async def remt(event):
    await event.edit('Removing...')
    try:
        os.remove(f'{event.sender_id}.jpg')
        await event.edit('Thumbnail removed!')
    except Exception:
        await event.edit("No thumbnail was saved.")

@Drone.on(events.NewMessage(incoming=True, pattern=rf'{S}(?:@\w+)?(?:\s|$)'))
async def start(event):
    # In groups, only auth users get the full response
    if not event.is_private and not is_authorized(event.sender_id):
        return
    await event.reply(
        START_TEXT,
        buttons=[
            [Button.inline("Set Thumbnail", b"set"), Button.inline("Remove Thumbnail", b"rem")]
        ]
    )
