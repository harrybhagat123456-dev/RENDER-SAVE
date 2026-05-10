import glob, asyncio
from pathlib import Path
from main.utils import load_plugins
import logging, requests
from . import bot, Bot
from decouple import config

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
# Register menu commands via direct HTTP Bot API — most reliable method
# ---------------------------------------------------------------------------
_COMMANDS = [
    {"command": "start",     "description": "Start the bot"},
    {"command": "help",      "description": "List all available commands"},
    {"command": "login",     "description": "Login your Telegram account"},
    {"command": "logout",    "description": "Logout and remove saved session"},
    {"command": "batch",     "description": "Save multiple messages in bulk"},
    {"command": "history",   "description": "Resume saving from where you left off"},
    {"command": "setchat",   "description": "Set transfer channel for saved content"},
    {"command": "mychat",    "description": "View your current transfer channel"},
    {"command": "clearchat", "description": "Reset transfer channel to DM"},
    {"command": "cancel",    "description": "Cancel active batch operation"},
    {"command": "reset",     "description": "Clear saved history and reset bot state"},
]

try:
    BOT_TOKEN = config("BOT_TOKEN", default=None)
    base = f"https://api.telegram.org/bot{BOT_TOKEN}"
    requests.post(f"{base}/deleteMyCommands", json={}, timeout=10)
    r = requests.post(f"{base}/setMyCommands", json={"commands": _COMMANDS}, timeout=10)
    if r.json().get("ok"):
        print(f"[COMMANDS] {len(_COMMANDS)} menu commands registered successfully.")
    else:
        print(f"[COMMANDS] setMyCommands failed: {r.json()}")
except Exception as e:
    print(f"[COMMANDS] Could not register commands: {e}")

if __name__ == "__main__":
    bot.run_until_disconnected()
