import glob, asyncio, threading, os
from pathlib import Path
from main.utils import load_plugins
import logging, requests
from . import bot, Bot
from decouple import config

from telethon.tl.functions.bots import SetBotCommandsRequest
from telethon.tl.types import BotCommand, BotCommandScopeDefault

logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s',
                    level=logging.WARNING)

# ---------------------------------------------------------------------------
# Health-check HTTP server (required by Render Web Service port detection)
# Listens on $PORT (default 10000) and replies 200 OK to every request.
# Runs in a daemon thread so it doesn't block the bot.
# ---------------------------------------------------------------------------
def _start_health_server():
    import http.server, socketserver

    port = int(os.environ.get("PORT", 10000))

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        def log_message(self, *_):
            pass   # silence request logs

    try:
        with socketserver.TCPServer(("", port), _Handler) as httpd:
            print(f"[HEALTH] Health-check server listening on port {port}")
            httpd.serve_forever()
    except Exception as e:
        print(f"[HEALTH] Could not start health server: {e}")

_health_thread = threading.Thread(target=_start_health_server, daemon=True)
_health_thread.start()

path = "main/plugins/*.py"
files = glob.glob(path)
for name in files:
    with open(name) as a:
        patt = Path(a.name)
        plugin_name = patt.stem
        load_plugins(plugin_name.replace(".py", ""))

print("Successfully deployed!")
print("By MaheshChauhan • DroneBots")

# Start GitHub auto-push background thread
try:
    from main.plugins.autogit import start_auto_push
    start_auto_push()
except Exception as e:
    print(f"[AUTOGIT] Could not start auto-push: {e}")

# ---------------------------------------------------------------------------
# Register menu commands via direct HTTP Bot API — most reliable method
# ---------------------------------------------------------------------------
_COMMANDS = [
    {"command": "start",      "description": "Start the bot"},
    {"command": "help",       "description": "List all available commands"},
    {"command": "login",      "description": "Login your Telegram account"},
    {"command": "logout",     "description": "Logout and remove saved session"},
    {"command": "batch",      "description": "Save multiple messages in bulk"},
    {"command": "history",    "description": "Resume saving from where you left off"},
    {"command": "setchat",    "description": "Set transfer channel for saved content"},
    {"command": "mychat",     "description": "View your current transfer channel"},
    {"command": "clearchat",  "description": "Reset transfer channel to DM"},
    {"command": "cancel",     "description": "Cancel active batch operation"},
    {"command": "reset",      "description": "Clear saved history and reset bot state"},
    {"command": "addauth",    "description": "Grant a user access to bot commands"},
    {"command": "removeauth", "description": "Revoke a user's access"},
    {"command": "listauth",   "description": "List all authorized users"},
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
