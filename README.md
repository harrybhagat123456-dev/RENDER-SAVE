# SaveRestrictedContentBot — Modified & Enhanced

> Based on: [vasusen-code/SaveRestrictedContentBot](https://github.com/vasusen-code/SaveRestrictedContentBot) (1.9k+ stars)
> Framework: Pyrogram v4 + Telethon
> Repo: `harrybhagat123456-dev/SaveRestrictedContentBot`

---

## Table of Contents

1. [What This Bot Does](#what-this-bot-does)
2. [Project Structure](#project-structure)
3. [New Features Added](#new-features-added)
4. [Bugs Found & Fixed](#bugs-found--fixed)
5. [Architecture: How Content Flows](#architecture-how-content-flows)
6. [Key Functions Reference](#key-functions-reference)
7. [Environment Variables](#environment-variables)
8. [Known Issues & Limitations](#known-issues--limitations)
9. [Deployment Notes](#deployment-notes)

---

## What This Bot Does

A Telegram userbot that saves content from restricted/private channels that normal bots can't access. It uses a **Pyrogram userbot session** (logged in as a real user) to fetch messages, then forwards them to a target channel or the user's DM.

**Original capabilities:**
- Save text, videos, photos, documents from private/restricted channels
- Batch saving of multiple messages
- Force-subscribe system
- Works with `t.me/c/` (private) and `t.me/` (public) links

**Our added capabilities:**
- Forward polls with correct answers preserved (quiz + regular)
- Pin every saved message to the SAVE_CHANNEL
- Rewrite inline links in messages to point to saved copies
- Copy ALL message types (stickers, GIFs, contacts, locations, etc.)
- Proper error handling for every edge case

---

## Project Structure

```
SaveRestrictedContentBot/
├── main/
│   ├── __init__.py          # Bot startup, config variables, Pyrogram patch
│   ├── __main__.py          # Entry point: python3 -m main
│   ├── utils.py             # Utility functions
│   └── plugins/
│       ├── pyroplug.py      # ⭐ CORE: Message fetching, forwarding, all new features
│       ├── frontend.py      # User command handler (/start, link processing)
│       ├── batch.py         # Batch saving (/batch command)
│       ├── helpers.py       # Helper functions (screenshot, link parsing, join)
│       ├── progress.py      # Download/upload progress bar
│       └── start.py         # /start command handler
├── .gitignore               # Ignores sessions, __pycache__, downloads, .env
├── .replit                  # Replit deployment config
├── Dockerfile               # Docker deployment
├── requirements.txt         # Python dependencies
├── sync_from_github.sh      # Git sync (hard reset, no rebase)
├── start.sh                 # Startup script (cleanup + sync + run)
├── gen_session.py           # Generate Pyrogram string session
├── session_gen.py           # Alternative session generator
└── README.md                # This file
```

### Key Files Modified

| File | What Changed |
|------|-------------|
| `main/plugins/pyroplug.py` | **MOST CHANGED** — poll forwarding, pinning, link rewriting, peer resolution, all-media-type support, copy_message fallback |
| `main/plugins/frontend.py` | Separated `status_chat` (user DM) from `sender` (SAVE_CHANNEL), added `SAVE_CHANNEL` import |
| `main/__init__.py` | Added `SAVE_CHANNEL` config, monkey-patched `get_peer_type()`, pre-cached bot dialogs, startup peer resolution |
| `.gitignore` | Added `*.session`, `*.session-journal`, `downloads/`, `*.jpg`, `.env` |

---

## New Features Added

### 1. Poll Forwarding with Correct Answers

**Problem:** Telegram doesn't allow forwarding polls from restricted chats. The original bot just skipped them.

**Solution:** Re-create polls using `client.send_poll()` with all original properties:

```python
async def forward_poll(client, target_chat, msg, status_msg):
    # Preserves:
    # - Same question text
    # - Same options in same order
    # - Poll type (regular / quiz)
    # - Correct answer index (for quiz polls)
    # - Explanation text (for quiz polls)
    # - Anonymous setting
    # Also sends a "Vote Summary" follow-up message
```

**Critical detail:** In Pyrogram v4, `poll.options[i].data` is **raw bytes**, NOT a dict. We must use `poll.correct_option_index` directly. Calling `opt.data.get('correct')` crashes with `'bytes' object has no attribute 'get'`.

### 2. Message Pinning

Every saved message is automatically pinned in the SAVE_CHANNEL:

```python
async def pin_if_channel(client, chat_id, msg_id):
    await client.pin_chat_message(chat_id, msg_id, both_sides=False)
```

- `both_sides=False`: Only notifies pinner, not all members
- Silently fails if bot lacks pin permissions

### 3. Inline Link Rewriting

When a forwarded message contains `t.me/c/CHANNELID/MSGID` links pointing to other messages in the source chat, those links are rewritten to point to the corresponding saved messages in the user's SAVE_CHANNEL.

```python
# Example: Original message has link:
# https://t.me/c/2663154678/42
# 
# If message 42 was already saved as message 88 in our channel (-1009999999999):
# Rewritten to: https://t.me/c/9999999999/88
```

Uses a global `msg_map` dictionary: `(original_chat, original_msg_id) → new_msg_id`

Supports:
- Private channel links: `t.me/c/1234567/42`
- Public channel links: `t.me/channelname/42`
- Both `https://` and bare `t.me/` formats

### 4. Copy ALL Message Types

**Problem:** Original bot skipped stickers, animations, contacts, locations, venues, dice, games.

**Solution:** 3-tier fallback system — no message is ever skipped:

| Priority | Strategy | Message Types |
|----------|----------|---------------|
| 1 | Download + Upload | Video, Photo, Document, Audio, Animation, Voice, Sticker |
| 2 | `userbot.copy_message()` | Contact, Location, Venue, Dice, Game, any download failure |
| 3 | Text extraction fallback | Sends `[Unsupported media]` with any available text |

```python
async def copy_message_fallback(userbot_client, target_chat, source_chat, msg_id, caption=None):
    """Uses the userbot to copy any message type directly."""
    sent_msg = await userbot_client.copy_message(
        chat_id=target_chat,
        from_chat_id=source_chat,
        message_id=msg_id,
        caption=caption
    )
```

---

## Bugs Found & Fixed

### Bug 1: PeerIdInvalid — Mixed Chat Context 🔴 CRITICAL

**Error:** `Peer id invalid: -1002663154678`

**Root cause:** `frontend.py` sent "Processing!" message to user's DM, then called `get_msg()` with `sender=SAVE_CHANNEL` and `edit_id` from the DM. Inside `get_msg()`, every `client.edit_message_text(sender, edit_id, ...)` tried to edit a message in SAVE_CHANNEL that actually existed in the user's DM.

**Fix:** Added `status_chat` parameter to `get_msg()`. Status/progress messages go to `status_chat` (user DM), content goes to `sender` (SAVE_CHANNEL).

```
Before: get_msg(userbot, client, bot, sender, edit_id, msg_link, i)
After:  get_msg(userbot, client, bot, sender, edit_id, status_chat, msg_link, i)
```

### Bug 2: Pyrogram Internal PeerIdInvalid Crash 🔴 CRITICAL

**Error:** `ValueError: Peer id invalid: -1002173883690` inside `pyrogram/client.py:handle_updates()`

**Root cause:** Pyrogram's `handle_updates()` calls `resolve_peer()` → `get_peer_type()`. If a channel isn't in the SQLite session cache, `get_peer_type()` raises `ValueError`, crashing the entire update handler.

**Fix:** Monkey-patched `pyrogram.utils.get_peer_type()`:

```python
def _patched_get_peer_type(peer_id):
    try:
        return _original_get_peer_type(peer_id)
    except ValueError:
        if peer_id < -1000000000000:  # -100XXXXXXXXXX = channel
            return "channel"
        elif peer_id < 0:              # -XXXXXXXXX = group
            return "chat"
        else:                          # positive = user
            return "user"

pyrogram.utils.get_peer_type = _patched_get_peer_type
```

### Bug 3: `'bytes' object has no attribute 'get'` — Poll Crash 🔴 CRITICAL

**Root cause:** Code tried `opt.data.get('correct', False)` to find the correct quiz answer. In Pyrogram v4, `opt.data` is raw bytes (not a dict).

**Fix:** Use `poll.correct_option_index` directly — it's always available from the Telegram API for quiz polls.

### Bug 4: "The number of file parts is invalid" — Photo Upload 🔴

**Root cause:** Photos were sent via `bot.send_file()` (Telethon), which uploads as a generic document instead of a photo.

**Fix:** Now using `client.send_photo()` (Pyrogram) for photos. Falls back to `bot.send_file()` only if `send_photo()` fails.

### Bug 5: Syntax Bug in `rewrite_inline_links()` 🔴

**Root cause:** `msg_mapap_key]` instead of `msg_map[key]` — a typo that crashed the link rewriting function.

**Fix:** Corrected to `msg_map[map_key]`.

### Bug 6: Original Python Bug in Chat Link Parsing 🟡

**Root cause:** `if 't.me/c/' or 't.me/b/' in msg_link:` — this is ALWAYS True because `'t.me/c/'` is a truthy non-empty string.

**Fix:** `if 't.me/c/' in msg_link or 't.me/b/' in msg_link:`

### Bug 7: "This message doesn't contain any downloadable media" 🟡

**Root cause:** `userbot.download_media()` returns `None` for messages without downloadable media, but code didn't check and tried to upload a None file.

**Fix:** Check if `file` is None after download, then try `copy_message_fallback()`.

### Bug 8: Git Sync "Unstaged Changes" Error on Deployment 🟡

**Root cause:** Runtime session files and `__pycache__` caused `git pull --rebase` to fail.

**Fix:** `sync_from_github.sh` now uses `git fetch + git reset --hard origin/main` instead of `git pull --rebase`. `start.sh` cleans runtime files before syncing.

### Bug 9: Git Rebase Conflicts on Deployment 🟡

**Root cause:** Deployment server was trying to rebase old commits on top of our force-pushed history.

**Fix:** `sync_from_github.sh` uses hard reset instead of rebase. `start.sh` aborts any leftover rebase on startup. `.replit` has `[git] autopush = false`.

---

## Architecture: How Content Flows

### For Private/Restricted Channels

```
User sends link → frontend.py
    ↓
Sends "Processing!" to user DM (status_chat)
    ↓
Calls get_msg(userbot, Bot, Drone, SAVE_CHANNEL, edit_id, status_chat, link, 0)
    ↓
get_msg() flow:
    1. ensure_target_peer() — resolve SAVE_CHANNEL for bot client
    2. resolve_peer_safe() — resolve source channel for userbot
    3. userbot.get_messages() — fetch the message
    4. Route by message type:
       ├── Poll → forward_poll() → register + pin
       ├── Text → rewrite_inline_links() → send_message → register + pin
       ├── WebPage → rewrite_inline_links() → send_message → register + pin
       ├── Downloadable media → download → upload (by type) → register + pin
       ├── Other media → copy_message_fallback() → register + pin
       └── Fallback → send text with "[Unsupported media]" → register + pin
    5. Edit status message in user DM on completion/failure
```

### For Public Channels

```
Same flow, but simpler:
    - Uses client (bot) to get messages directly
    - Uses client.copy_message() for most content
    - Only polls get special handling
```

### Peer Resolution Strategy (3-tier)

```
1. client.resolve_peer(chat_id)  — fastest, cache-only
2. client.get_chat(chat_id)      — medium, makes API call
3. client.get_dialogs() loop     — slowest, scans all dialogs
```

Plus startup pre-caching:
- `Bot.get_dialogs()` at startup to cache all bot peers
- `Bot.get_chat(SAVE_CHANNEL)` to cache the target channel

---

## Key Functions Reference

### `get_msg(userbot, client, bot, sender, edit_id, status_chat, msg_link, i)`

| Param | Type | Description |
|-------|------|-------------|
| `userbot` | Pyrogram Client | Userbot session (has access to restricted chats) |
| `client` | Pyrogram Client | Bot client (sends to SAVE_CHANNEL, edits status) |
| `bot` | Telethon Client | Fallback upload client (for large files) |
| `sender` | int | Target chat for content (SAVE_CHANNEL or user DM) |
| `edit_id` | int | Message ID of "Processing!" status in status_chat |
| `status_chat` | int | Chat where status messages live (user's DM) |
| `msg_link` | str | Telegram message link (t.me/c/... or t.me/...) |
| `i` | int | Offset for batch saving (0 for single) |

### `forward_poll(client, target_chat, msg, status_msg)`

Re-creates a poll with all properties. Returns the sent message for pinning.

### `rewrite_inline_links(text, original_chat_id, new_chat_id)`

Rewrites `t.me/c/CHATID/MSGID` links using the `msg_map` dictionary.

### `resolve_peer_safe(client, chat_id)`

3-tier peer resolution. Returns True if resolved, False otherwise.

### `ensure_target_peer(client, target_chat)`

Called at the start of `get_msg()` to ensure the bot can send to SAVE_CHANNEL.

### `copy_message_fallback(userbot_client, target_chat, source_chat, msg_id, caption)`

Uses userbot's `copy_message()` to handle any message type. Last resort before text-only fallback.

### `pin_if_channel(client, chat_id, msg_id)`

Pins a message. Silently fails if bot lacks permissions.

### `register_msg_mapping(original_chat, original_msg_id, new_chat_id, new_msg_id)`

Stores `(original_chat, original_msg_id) → new_msg_id` in `msg_map` for inline link rewriting.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `API_ID` | Yes | Telegram API ID (from my.telegram.org) |
| `API_HASH` | Yes | Telegram API Hash |
| `BOT_TOKEN` | Yes | Bot token from @BotFather |
| `SESSION` | Yes | Pyrogram StringSession (userbot session) |
| `FORCESUB` | No | Channel username for force-subscribe |
| `AUTH` | No | User ID(s) authorized to use /batch |
| `SAVE_CHANNEL` | No* | Channel ID (with -100 prefix) where content is saved |

*`SAVE_CHANNEL` is required for pinning and inline link rewriting to work. Without it, content goes to the user's DM (original behavior).

---

## Known Issues & Limitations

1. **msg_map is in-memory only** — If the bot restarts, inline link rewriting won't work for previously saved messages because the mapping is lost. A persistent store (SQLite/Redis) would fix this.

2. **Polls don't forward votes** — We re-create polls with 0 votes. The "Vote Summary" message shows original vote counts for reference.

3. **Stickers sent as documents** — `userbot.download_media()` downloads stickers as .webp files, which are sent as documents (not as proper Telegram stickers). The `copy_message_fallback()` method handles stickers better by copying them directly.

4. **Telethon fallback needed for large files** — Pyrogram sometimes fails with "number of file parts is invalid" for large uploads. The code falls back to Telethon's `fast_upload()` + `bot.send_file()`.

5. **Replit auto-push conflicts** — Replit tries to push local changes back to GitHub. We've disabled this in `.replit` with `[git] autopush = false`, but if Replit ignores this setting, you may see push conflicts.

6. **Bot must be admin in SAVE_CHANNEL** — For pinning to work, the bot must have "Pin Messages" permission in the SAVE_CHANNEL.

---

## Deployment Notes

### On Replit

1. Fork/clone the repo
2. Set secrets (environment variables) in Replit
3. Run `bash start.sh` (handles cleanup, git sync, bot startup)
4. If git sync fails with rebase errors:
   ```bash
   git rebase --abort
   git fetch origin main
   git reset --hard origin/main
   git clean -fd
   ```

### The Pyrogram Patch

The monkey-patch in `__init__.py` is critical — without it, Pyrogram's internal update handler crashes on any channel not in the session cache. This patch MUST load before any Pyrogram client processes updates.

### Three Clients Running Simultaneously

| Client | Library | Purpose |
|--------|---------|---------|
| `userbot` | Pyrogram | Fetches messages from restricted chats (has user access) |
| `Bot` | Pyrogram | Sends content to SAVE_CHANNEL, edits status messages |
| `bot` (Drone) | Telethon | Receives user commands via events, fallback uploads |

### Startup Sequence

```
1. Apply get_peer_type patch
2. Start Telethon bot client
3. Start Pyrogram userbot
4. Start Pyrogram Bot client
5. Pre-cache Bot dialogs (walk get_dialogs())
6. Resolve SAVE_CHANNEL peer
7. Import plugins (registers handlers)
8. Bot is ready
```
