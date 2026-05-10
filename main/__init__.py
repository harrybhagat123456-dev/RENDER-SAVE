#Github.com/Vasusen-code

from pyrogram import Client
import pyrogram.utils

from telethon.sessions import StringSession
from telethon.sync import TelegramClient

from decouple import config
import logging, time, sys, traceback, os

logging.basicConfig(format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s',
                    level=logging.WARNING)

# variables — safe cast: returns None instead of crashing when env var is unset
_safe_int = lambda x: int(x) if x is not None else None

API_ID = config("API_ID", default=None, cast=_safe_int)
API_HASH = config("API_HASH", default=None)
BOT_TOKEN = config("BOT_TOKEN", default=None)
SESSION = config("SESSION", default=None)
FORCESUB = config("FORCESUB", default=None)
AUTH = config("AUTH", default=None, cast=_safe_int)

SESSION_FILE = "user_session.txt"

# ---------------------------------------------------------------------------
# MONKEY-PATCH: Fix Pyrogram's get_peer_type to handle unknown channel IDs
# ---------------------------------------------------------------------------
_original_get_peer_type = pyrogram.utils.get_peer_type

def _patched_get_peer_type(peer_id):
    try:
        return _original_get_peer_type(peer_id)
    except ValueError:
        if peer_id < -1000000000000:
            return "channel"
        elif peer_id < 0:
            return "chat"
        else:
            return "user"

pyrogram.utils.get_peer_type = _patched_get_peer_type
print("[PATCH] Applied get_peer_type patch — Pyrogram won't crash on unknown channels")


# ---------------------------------------------------------------------------
# ClientRef — a transparent proxy that can hold (or not hold) a Pyrogram
# Client.  All attribute accesses are forwarded to the underlying client so
# existing plugin code (`await userbot.get_messages(...)`) keeps working
# without any changes.
# ---------------------------------------------------------------------------
class ClientRef:
    """Mutable proxy around a Pyrogram Client.

    Usage
    -----
    userbot = ClientRef()          # empty — bool(userbot) is False
    userbot.set(some_client)       # attach a running client
    userbot.clear()                # detach & disconnect
    await userbot.get_messages(…)  # proxied to underlying client
    """

    def __init__(self):
        self._client = None

    # --- state management ---------------------------------------------------

    def set(self, client):
        self._client = client

    def clear(self):
        self._client = None

    @property
    def is_connected(self):
        if self._client is None:
            return False
        try:
            return self._client.is_connected
        except Exception:
            return False

    # --- bool / repr --------------------------------------------------------

    def __bool__(self):
        return self._client is not None

    def __repr__(self):
        return f"<ClientRef client={self._client!r}>"

    # --- transparent proxy --------------------------------------------------

    def __getattr__(self, name):
        # Avoid infinite recursion for our own attributes
        if name.startswith('_') or name in ('set', 'clear', 'is_connected'):
            raise AttributeError(name)
        if self._client is None:
            raise RuntimeError(
                "Userbot is not logged in. Send /login to authenticate."
            )
        return getattr(self._client, name)


# ---------------------------------------------------------------------------
# Bot clients (Telethon + Pyrogram)
# ---------------------------------------------------------------------------
bot = TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

Bot = Client(
    "SaveRestricted",
    bot_token=BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH,
)

try:
    Bot.start()
except Exception as e:
    print("Bot (Pyrogram) failed to start:")
    traceback.print_exc()
    sys.exit(1)

# ---------------------------------------------------------------------------
# Userbot — optional; loaded from SESSION env-var or saved session file
# ---------------------------------------------------------------------------
userbot = ClientRef()


def _load_session_string():
    """Return a session string from env-var or saved file, or None."""
    if SESSION:
        return SESSION
    if os.path.exists(SESSION_FILE):
        with open(SESSION_FILE) as f:
            s = f.read().strip()
            if s:
                return s
    return None


def _start_userbot(session_string):
    """Create, start and attach a Pyrogram client for the given session string."""
    client = Client(
        "saverestricted",
        session_string=session_string,
        api_hash=API_HASH,
        api_id=API_ID,
    )
    client.start()
    userbot.set(client)
    print("[USERBOT] Userbot started successfully.")


_saved_session = _load_session_string()
if _saved_session:
    try:
        _start_userbot(_saved_session)
    except Exception:
        print("[USERBOT] Could not start userbot from saved session:")
        traceback.print_exc()
        print("[USERBOT] Send /login to authenticate.")
else:
    print("[USERBOT] No session found. Send /login to authenticate.")


# ---------------------------------------------------------------------------
# Pre-cache all dialogs for the Bot client
# ---------------------------------------------------------------------------
async def precache_bot_peers():
    try:
        count = 0
        async for dialog in Bot.get_dialogs():
            count += 1
        print(f"[CACHE] Pre-cached {count} bot dialogs")
    except Exception as e:
        print(f"[CACHE] Warning: Could not pre-cache bot dialogs: {e}")


try:
    import asyncio
    loop = asyncio.get_event_loop()
    if loop.is_running():
        asyncio.ensure_future(precache_bot_peers())
    else:
        loop.run_until_complete(precache_bot_peers())
except Exception as e:
    print(f"[CACHE] Warning: Pre-cache scheduling failed: {e}")
