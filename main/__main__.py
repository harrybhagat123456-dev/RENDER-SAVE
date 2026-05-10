import glob, asyncio
from pathlib import Path
from main.utils import load_plugins
import logging
from . import bot, Bot

from telethon.tl.functions.bots import SetBotCommandsRequest
from telethon.tl.types import BotCommand, BotCommandScopeDefault

logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s',
                    level=logging.WARNING)

path = "main/plugins/*.py"
files = glob.glob(path)
for name in files:
    with open(name) as a:
        patt = Path(a.name)
        plugin_name = patt.stem
        load_plugins(plugin_name.replace(".py", ""))

print("Successfully deployed!")
print("By MaheshChauhan • DroneBots")

# ---------------------------------------------------------------------------
# Register bot menu commands via Telethon raw API (runs synchronously)
# so they show up in the "/" menu in Telegram for every user.
# ---------------------------------------------------------------------------
try:
    bot(SetBotCommandsRequest(
        scope=BotCommandScopeDefault(),
        lang_code="",
        commands=[
            BotCommand("start",     "▶️ Start the bot"),
            BotCommand("login",     "🔐 Login your Telegram account"),
            BotCommand("logout",    "🚪 Logout and remove saved session"),
            BotCommand("batch",     "📦 Save multiple messages in bulk"),
            BotCommand("setchat",   "📤 Set transfer channel for saved content"),
            BotCommand("mychat",    "📋 View your current transfer channel"),
            BotCommand("clearchat", "🗑 Reset transfer channel to DM"),
            BotCommand("cancel",    "❌ Cancel active batch operation"),
        ]
    ))
    print("[COMMANDS] Bot menu commands registered successfully.")
except Exception as e:
    print(f"[COMMANDS] Could not set bot commands: {e}")

if __name__ == "__main__":
    bot.run_until_disconnected()
