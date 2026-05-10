import glob, asyncio
from pathlib import Path
from main.utils import load_plugins
import logging
from . import bot, Bot

logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s',
                    level=logging.WARNING)

path = "main/plugins/*.py"
files = glob.glob(path)
for name in files:
    with open(name) as a:
        patt = Path(a.name)
        plugin_name = patt.stem
        load_plugins(plugin_name.replace(".py", ""))

#Don't be a thief 
print("Successfully deployed!")
print("By MaheshChauhan • DroneBots")

# ---------------------------------------------------------------------------
# Register bot menu commands so they appear in the "/" menu inside Telegram
# ---------------------------------------------------------------------------
async def set_commands():
    try:
        from pyrogram.types import BotCommand
        commands = [
            BotCommand("start",    "Start the bot"),
            BotCommand("login",    "Login your Telegram account (userbot)"),
            BotCommand("logout",   "Logout and remove saved session"),
            BotCommand("batch",    "Save multiple messages in bulk"),
            BotCommand("setchat",  "Set transfer channel for saved content"),
            BotCommand("mychat",   "View your current transfer channel"),
            BotCommand("clearchat","Reset transfer channel to your DM"),
            BotCommand("cancel",   "Cancel the active batch operation"),
        ]
        await Bot.set_bot_commands(commands)
        print("[COMMANDS] Bot menu commands registered successfully.")
    except Exception as e:
        print(f"[COMMANDS] Could not set bot commands: {e}")

try:
    loop = asyncio.get_event_loop()
    if loop.is_running():
        asyncio.ensure_future(set_commands())
    else:
        loop.run_until_complete(set_commands())
except Exception as e:
    print(f"[COMMANDS] Scheduling failed: {e}")

if __name__ == "__main__":
    bot.run_until_disconnected()
