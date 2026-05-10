#Github.com-Vasusen-code
#Modified: poll forwarding, message pinning, inline link rewriting
#Bug fixes: PeerIdInvalid, 'bytes'.get() crash, poll answers, photo upload,
#           no-media handling, copy ALL message types (stickers, animations, etc.)

import asyncio, time, os, re, json, urllib.parse

from .. import bot as Drone
from .. import userbot, Bot
from main.plugins.progress import progress_for_pyrogram
from main.plugins.helpers import screenshot

from pyrogram import Client, filters
from pyrogram.errors import ChannelBanned, ChannelInvalid, ChannelPrivate, ChatIdInvalid, ChatInvalid, PeerIdInvalid
from pyrogram.enums import MessageMediaType, PollType
from ethon.pyfunc import video_metadata
from ethon.telefunc import fast_upload
from telethon.tl.types import DocumentAttributeVideo
from telethon import events

# ---------------------------------------------------------------------------
# Global mapping: original chat_id+msg_id -> new msg_id in our saved channel
# Persisted to MSG_MAP_FILE so history/resume survives restarts.
# ---------------------------------------------------------------------------
msg_map = {}

def _map_key_to_str(k):
    return f"{k[0]}:{k[1]}"

def _str_to_map_key(s):
    parts = s.rsplit(":", 1)
    chat = parts[0]
    msg_id = int(parts[1])
    try:
        chat = int(chat)
    except ValueError:
        pass
    return (chat, msg_id)

def _load_msg_map():
    try:
        from .. import MSG_MAP_FILE
        if os.path.exists(MSG_MAP_FILE):
            with open(MSG_MAP_FILE) as f:
                raw = json.load(f)
            for k, v in raw.items():
                msg_map[_str_to_map_key(k)] = v
            print(f"[HISTORY] Loaded {len(msg_map)} entries from msg_map cache.")
    except Exception as e:
        print(f"[HISTORY] Could not load msg_map: {e}")

def _save_msg_map():
    try:
        from .. import MSG_MAP_FILE
        serialised = {_map_key_to_str(k): v for k, v in msg_map.items()}
        with open(MSG_MAP_FILE, "w") as f:
            json.dump(serialised, f)
    except Exception as e:
        print(f"[HISTORY] Could not save msg_map: {e}")

_load_msg_map()

# Cache of channel IDs we've already resolved to avoid repeated dialog scans
_resolved_peers = set()

# Cache of pinned message IDs per chat: {chat_id: set_of_msg_ids}
_pinned_cache = {}

# Media types that can be downloaded via userbot.download_media()
DOWNLOADABLE_MEDIA = {
    MessageMediaType.VIDEO, MessageMediaType.VIDEO_NOTE,
    MessageMediaType.PHOTO, MessageMediaType.DOCUMENT,
    MessageMediaType.AUDIO, MessageMediaType.ANIMATION,
    MessageMediaType.VOICE, MessageMediaType.STICKER,
}

async def resolve_peer_safe(client, chat_id):
    """Ensure Pyrogram has the access hash for chat_id in its session cache."""
    if chat_id in _resolved_peers:
        return True
    try:
        await client.resolve_peer(chat_id)
        _resolved_peers.add(chat_id)
        return True
    except Exception:
        pass
    try:
        await client.get_chat(chat_id)
        _resolved_peers.add(chat_id)
        return True
    except Exception:
        pass
    try:
        async for dialog in client.get_dialogs():
            if dialog.chat and dialog.chat.id == chat_id:
                _resolved_peers.add(chat_id)
                return True
    except Exception:
        pass
    return False


async def ensure_target_peer(client, target_chat):
    """Before sending to SAVE_CHANNEL, ensure the bot has the access hash cached."""
    if isinstance(target_chat, int) and target_chat < -1000000000000:
        resolved = await resolve_peer_safe(client, target_chat)
        if not resolved:
            print(f"[WARN] Could not resolve peer for {target_chat}. "
                  f"Make sure the bot is an admin in this channel.")
    return True


def thumbnail(sender):
    if os.path.exists(f'{sender}.jpg'):
        return f'{sender}.jpg'
    else:
        return None


# ---------------------------------------------------------------------------
# Pin the message to the saved channel
# ---------------------------------------------------------------------------
async def get_pinned_msg_ids(userbot_client, client, chat_id):
    """Fetch and cache ALL pinned message IDs from a source chat.
    Uses Pyrogram's PINNED_MESSAGES search filter to get every pinned message,
    not just the latest one."""
    if chat_id in _pinned_cache:
        return _pinned_cache[chat_id]

    pinned_ids = set()

    # Method 1: Pyrogram search_messages with PINNED_MESSAGES filter
    # This is the most reliable way — it returns ALL currently pinned messages
    try:
        from pyrogram.enums import MessagesFilter
        async for msg in userbot_client.search_messages(chat_id, filter=MessagesFilter.PINNED_MESSAGES):
            pinned_ids.add(msg.id)
        if pinned_ids:
            print(f"[PIN] Found {len(pinned_ids)} pinned messages via search_messages filter: {pinned_ids}")
    except Exception as e:
        print(f"[PIN] search_messages filter failed: {e}")

    # Method 2: Fallback — get_chat returns the single latest pinned message
    if not pinned_ids:
        try:
            chat_info = await userbot_client.get_chat(chat_id)
            if chat_info and hasattr(chat_info, 'pinned_message') and chat_info.pinned_message:
                pinned_ids.add(chat_info.pinned_message.id)
                print(f"[PIN] Found pinned message via userbot get_chat: {chat_info.pinned_message.id}")
        except Exception as e:
            print(f"[PIN] userbot get_chat failed: {e}")

    # Method 3: Last resort — try the bot client (works for public chats)
    if not pinned_ids:
        try:
            chat_info = await client.get_chat(chat_id)
            if chat_info and hasattr(chat_info, 'pinned_message') and chat_info.pinned_message:
                pinned_ids.add(chat_info.pinned_message.id)
                print(f"[PIN] Found pinned message via bot get_chat: {chat_info.pinned_message.id}")
        except Exception as e:
            print(f"[PIN] bot get_chat failed: {e}")

    _pinned_cache[chat_id] = pinned_ids
    if pinned_ids:
        print(f"[PIN] Cached {len(pinned_ids)} pinned message IDs for chat {chat_id}: {pinned_ids}")
    else:
        print(f"[PIN] No pinned messages found for chat {chat_id}")
    return pinned_ids


async def pin_if_channel(client, chat_id, msg_id, was_pinned=False):
    """Pin a message in channels/groups only if it was pinned in the original chat.
    Bots get BOT_ONESIDE_NOT_AVAIL error when trying to pin in DMs."""
    # Skip pinning in private chats (user DMs have positive IDs)
    if isinstance(chat_id, int) and chat_id > 0:
        return
    # Only pin if the original message was pinned
    if not was_pinned:
        return
    try:
        await client.pin_chat_message(
            chat_id=chat_id,
            message_id=msg_id,
            both_sides=False
        )
        print(f"[PIN] Pinned message {msg_id} in {chat_id}")
    except Exception as e:
        print(f"Could not pin message {msg_id} in {chat_id}: {e}")


# ---------------------------------------------------------------------------
# Resolve chat from a Telegram message link
# ---------------------------------------------------------------------------
def resolve_chat_from_link(msg_link):
    if 't.me/c/' in msg_link:
        channel_id = msg_link.split("/")[-2]
        chat = int('-100' + channel_id)
        return chat, True
    elif 't.me/b/' in msg_link:
        chat = str(msg_link.split("/")[-2])
        return chat, True
    else:
        chat = str(msg_link.split("/")[-2])
        return chat, False


# ---------------------------------------------------------------------------
# inline link rewriting
# ---------------------------------------------------------------------------
def rewrite_inline_links(text, original_chat_id, new_chat_id):
    if not text:
        return text

    def replace_link(match):
        full_url = match.group(0)
        private_match = re.match(r'(?:https?://)?t\.me/c/(\d+)/(\d+)', full_url)
        if private_match:
            link_chat = int('-100' + private_match.group(1))
            link_msg_id = int(private_match.group(2))
            map_key = (link_chat, link_msg_id)
            if map_key in msg_map:
                new_msg_id = msg_map[map_key]
                if isinstance(new_chat_id, int) and str(new_chat_id).startswith('-100'):
                    short_id = str(new_chat_id)[4:]
                    return f"https://t.me/c/{short_id}/{new_msg_id}"
                else:
                    return f"https://t.me/{new_chat_id}/{new_msg_id}"
            return full_url

        public_match = re.match(r'(?:https?://)?t\.me/([a-zA-Z][\w]{4,})/(\d+)', full_url)
        if public_match:
            link_chat = public_match.group(1)
            link_msg_id = int(public_match.group(2))
            map_key_str = (link_chat, link_msg_id)
            if map_key_str in msg_map:
                new_msg_id = msg_map[map_key_str]
                if isinstance(new_chat_id, int) and str(new_chat_id).startswith('-100'):
                    short_id = str(new_chat_id)[4:]
                    return f"https://t.me/c/{short_id}/{new_msg_id}"
                else:
                    return f"https://t.me/{new_chat_id}/{new_msg_id}"
            return full_url

        return full_url

    pattern = r'(?:https?://)?t\.me/(?:c/\d+|\w{5,})/\d+'
    result = re.sub(pattern, replace_link, text)
    return result


# ---------------------------------------------------------------------------
# Poll forwarding — multi-strategy approach
#
# Strategy order:
#   1. Try quiz poll via Pyrogram send_poll (with correct_option_index if available)
#   2. Try quiz poll via Telethon raw API (works even without correct_option_index attr)
#   3. Try regular poll via Pyrogram send_poll (loses quiz marking but creates the poll)
#   4. Fallback: send poll data as text
# ---------------------------------------------------------------------------
def _extract_correct_option(poll):
    """
    Try every possible way to find the correct option index for a quiz poll.
    Returns (index, explanation, explanation_entities) or (None, None, None).
    """
    correct_idx = None
    explanation = None
    explanation_entities = None

    # Method 1: Direct attribute (Pyrogram >= 2.0)
    if hasattr(poll, 'correct_option_index') and poll.correct_option_index is not None:
        correct_idx = poll.correct_option_index
        print(f"[POLL] Found correct_option_index via attribute: {correct_idx}")

    # Method 2: Check _raw attribute (some Pyrogram versions store it here)
    if correct_idx is None and hasattr(poll, '_raw'):
        raw = poll._raw
        if hasattr(raw, 'correct_answer') and raw.correct_answer:
            # correct_answer is bytes matching one of the option.data values
            try:
                for i, opt in enumerate(poll.options):
                    opt_data = getattr(opt, 'data', None) or getattr(opt, 'option', None)
                    if opt_data and opt_data == raw.correct_answer:
                        correct_idx = i
                        print(f"[POLL] Found correct answer via _raw.correct_answer: option {i}")
                        break
            except Exception as e:
                print(f"[POLL] _raw method failed: {e}")

    # Method 3: Check results in the Poll object
    if correct_idx is None and hasattr(poll, 'results') and poll.results:
        results = poll.results
        if hasattr(results, 'results') and results.results:
            for i, r in enumerate(results.results):
                if getattr(r, 'correct', False):
                    correct_idx = i
                    print(f"[POLL] Found correct answer via results.results[{i}].correct")
                    break

    # Extract explanation
    explanation = getattr(poll, 'explanation', None)
    explanation_entities = getattr(poll, 'explanation_entities', None)
    # Also try from _raw
    if explanation is None and hasattr(poll, '_raw'):
        raw = poll._raw
        explanation = getattr(raw, 'solution', None)
        explanation_entities = getattr(raw, 'solution_entities', None)

    return correct_idx, explanation, explanation_entities


# ---------------------------------------------------------------------------
# OCR + UPSC Answer Search
#
# When a quiz poll has an image, this module:
#   1. Downloads the image
#   2. OCRs it using pytesseract to extract question text
#   3. Searches UPSC sites (BYJU'S, ClearIAS, Drishti IAS, etc.) for the answer
#   4. Matches the found answer against poll options
#   5. Returns the correct option index (or None if unsure)
# ---------------------------------------------------------------------------

# UPSC answer sites to search (ordered by reliability)
_UPSC_SEARCH_QUERIES = [
    'site:byjus.com UPSC question answer {question}',
    'site:clearias.com UPSC question answer {question}',
    'site:drishtiias.com UPSC question answer {question}',
    'site:iasbaba.com UPSC question answer {question}',
    'site:mrunal.org UPSC question answer {question}',
    'site:visionias.in UPSC question answer {question}',
    'UPSC previous year question answer {question}',
    'UPSC answer key {question}',
]

# Known UPSC answer patterns in search snippets
_ANSWER_PATTERNS = [
    re.compile(r'(?:correct\s*answer|answer\s*(?:is|:)|option\s*(?:is|:))\s*[–\-:]?\s*(?:option\s*)?([A-Da-d])', re.IGNORECASE),
    re.compile(r'(?:answer|option)\s*(?:key|is)\s*[–\-:]?\s*\(?([A-Da-d])\)?', re.IGNORECASE),
    re.compile(r'\b([A-Da-d])\)\s*(?:is\s+correct|✓|✔|✅)', re.IGNORECASE),
    re.compile(r'\bans(?:wer)?\s*(?:\.|:|\-)\s*([A-Da-d])\b', re.IGNORECASE),
    re.compile(r'\boption\s+([A-Da-d])\b.*?(?:correct|right|answer)', re.IGNORECASE),
    re.compile(r'(?:correct|right)\s*(?:option|answer)\s*(?:is|:)\s*([A-Da-d])', re.IGNORECASE),
]

# Option letter mapping
_LETTER_TO_INDEX = {'a': 0, 'b': 1, 'c': 2, 'd': 3}


def _ocr_image(image_path):
    """Run pytesseract OCR on an image and return extracted text."""
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, lang='eng')
        return text.strip()
    except ImportError:
        print("[OCR] pytesseract or PIL not installed — OCR skipped")
        return None
    except Exception as e:
        print(f"[OCR] OCR failed: {e}")
        return None


async def _search_upsc_answer(question_text, options_list):
    """
    Search UPSC answer sites for the correct answer to a question.
    Returns (correct_idx, explanation_links) where explanation_links is a list of
    (title, url) tuples from sites that mention the answer.
    Returns (None, []) if not found with sufficient confidence.
    """
    if not question_text or len(question_text.strip()) < 10:
        return None, []

    # Clean up the question text for searching (take first ~150 chars)
    search_text = question_text.strip().replace('\n', ' ')[:150]

    try:
        from ddgs import DDGS
    except ImportError:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            print("[SEARCH] ddgs not installed — UPSC search skipped")
            return None, []

    # Build option letter map (A=0, B=1, C=2, D=3)
    option_count = len(options_list)
    letter_map = {}
    for i in range(min(option_count, 4)):
        letter_map[chr(65 + i)] = i  # A->0, B->1, C->2, D->3

    best_answer = None
    confidence = 0
    # Collect up to 3 unique explanation links that mention the correct answer
    explanation_links = []
    seen_urls = set()

    _KNOWN_SITES = [
        'testbook.com', 'byjus.com', 'clearias.com', 'drishtiias.com',
        'iasbaba.com', 'mrunal.org', 'visionias.in', 'unacademy.com',
        'neostencil.com', 'adda247.com', 'gktoday.in', 'jagranjosh.com',
    ]

    for query_template in _UPSC_SEARCH_QUERIES:
        query = query_template.format(question=search_text)
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))

            for result in results:
                snippet = result.get('body', '') or result.get('title', '')
                url = result.get('href', '')
                title = result.get('title', url)
                if not snippet or not url:
                    continue

                is_known_site = any(site in url for site in _KNOWN_SITES)

                # Try each answer pattern
                for pattern in _ANSWER_PATTERNS:
                    match = pattern.search(snippet)
                    if match:
                        letter = match.group(1).upper()
                        if letter in letter_map:
                            idx = letter_map[letter]
                            this_confidence = 2 if is_known_site else 1
                            if best_answer is not None and best_answer == idx:
                                this_confidence += 3
                            if this_confidence > confidence:
                                best_answer = idx
                                confidence = this_confidence
                                print(f"[SEARCH] Found answer: Option {letter} (index {idx}) "
                                      f"confidence={confidence} from {url[:60]}")
                            # Collect this URL as an explanation link for the winning answer
                            if url not in seen_urls and len(explanation_links) < 3:
                                seen_urls.add(url)
                                explanation_links.append((title[:60], url))
                        break

        except Exception as e:
            print(f"[SEARCH] Search failed for query '{query[:50]}': {e}")
            continue

        if confidence >= 5:
            break  # Confident enough, stop searching

    if best_answer is not None and confidence >= 2:
        return best_answer, explanation_links

    return None, explanation_links


async def _download_poll_image(userbot_client, msg):
    """
    Download the image attached to a poll message (or the previous message).
    Returns the local file path, or None if no image found.
    """
    image_path = None

    if msg.photo:
        try:
            image_path = await userbot_client.download_media(msg, file_name="poll_img.jpg")
            print(f"[IMG] Downloaded poll image: {image_path}")
        except Exception as e:
            print(f"[IMG] Could not download poll image: {e}")

    if not image_path or not os.path.exists(image_path or ''):
        try:
            chat_id = msg.chat.id if msg.chat else None
            msg_id = msg.id if msg.id else None
            if chat_id and msg_id:
                prev_msg = await userbot_client.get_messages(chat_id, msg_id - 1)
                if prev_msg and prev_msg.photo:
                    image_path = await userbot_client.download_media(prev_msg, file_name="poll_img.jpg")
                    print(f"[IMG] Downloaded prev-message image: {image_path}")
        except Exception as e:
            print(f"[IMG] Could not get previous message image: {e}")

    return image_path if (image_path and os.path.exists(image_path)) else None


def _sync_upload(image_path, bot_token, chat_id):
    """
    Upload image via the Telegram Bot API (always reachable from this server).
    Steps:
      1. sendPhoto to chat_id  → get file_id + message_id
      2. getFile(file_id)      → get file_path on Telegram CDN
      3. deleteMessage         → remove the temp photo from the channel
      4. Return https://api.telegram.org/file/bot{TOKEN}/{file_path}
    The returned URL is a direct, publicly accessible image URL (no auth needed).
    """
    import requests

    if not bot_token or not chat_id:
        print("[UPLOAD] No bot_token or chat_id — cannot upload")
        return None

    base = f"https://api.telegram.org/bot{bot_token}"

    # Step 1: send photo
    try:
        with open(image_path, 'rb') as f:
            r = requests.post(
                f"{base}/sendPhoto",
                data={'chat_id': str(chat_id), 'disable_notification': 'true'},
                files={'photo': ('image.jpg', f, 'image/jpeg')},
                timeout=30,
            )
        result = r.json()
        if not result.get('ok'):
            print(f"[UPLOAD] sendPhoto failed: {result}")
            return None
        sent = result['result']
        msg_id = sent['message_id']
        # Telegram returns photo as list of sizes; last = largest
        file_id = sent['photo'][-1]['file_id']
        print(f"[UPLOAD] sendPhoto OK, msg_id={msg_id}, file_id={file_id[:20]}...")
    except Exception as e:
        print(f"[UPLOAD] sendPhoto error: {e}")
        return None

    # Step 2: getFile to get the CDN path
    try:
        r2 = requests.get(
            f"{base}/getFile",
            params={'file_id': file_id},
            timeout=15,
        )
        fdata = r2.json()
        if not fdata.get('ok'):
            print(f"[UPLOAD] getFile failed: {fdata}")
            return None
        file_path = fdata['result']['file_path']
        public_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        print(f"[UPLOAD] CDN URL: {public_url}")
    except Exception as e:
        print(f"[UPLOAD] getFile error: {e}")
        return None

    # Step 3: delete the temporary photo we just sent
    try:
        requests.post(
            f"{base}/deleteMessage",
            data={'chat_id': str(chat_id), 'message_id': str(msg_id)},
            timeout=10,
        )
        print(f"[UPLOAD] Deleted temp photo msg_id={msg_id}")
    except Exception as e:
        print(f"[UPLOAD] deleteMessage error (non-fatal): {e}")

    return public_url


async def upload_image_get_url(image_path, chat_id):
    """
    Async wrapper for _sync_upload. Runs in a thread to avoid blocking.
    Returns a publicly accessible Telegram CDN URL, or None on failure.
    """
    if not image_path or not os.path.exists(image_path):
        return None
    from .. import BOT_TOKEN as _BOT_TOKEN
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_upload, image_path, _BOT_TOKEN, chat_id)


async def ocr_and_search_answer(userbot_client, msg, poll):
    """
    OCR the poll image and search UPSC/education sites for explanation links.
    Returns a list of (title, url) tuples. Empty list if nothing found.
    """
    image_path = await _download_poll_image(userbot_client, msg)
    if not image_path:
        return []

    ocr_text = _ocr_image(image_path)
    # NOTE: image_path is kept alive for the caller (forward_poll reuses it);
    # caller is responsible for cleanup.

    if not ocr_text:
        print("[OCR] No text extracted from image")
        return []

    print(f"[OCR] Extracted text: {ocr_text[:200]}")
    options = [opt.text for opt in poll.options]
    _idx, explanation_links = await _search_upsc_answer(ocr_text, options)
    return explanation_links


async def _send_caption(client, target_chat, msg, original_chat, sender):
    """Send the original message's caption as a pink-styled blockquote message."""
    caption_text = None
    if msg.caption:
        caption_text = msg.caption
    elif msg.text and msg.poll is not None:
        # For poll-only messages, the "caption" might be the text before the poll
        caption_text = None

    if not caption_text:
        return None

    # Rewrite any inline links in the caption
    rewritten = rewrite_inline_links(caption_text, original_chat, sender)

    # Send as a pink blockquote-style message
    # Telegram blockquote shows a colored left bar — we use it for the "pink caption" effect
    try:
        from pyrogram.types import MessageEntity
        caption_msg = await client.send_message(
            target_chat,
            rewritten,
            quote=True,  # blockquote styling
        )
        return caption_msg
    except Exception:
        # Fallback if quote param not supported — use markdown blockquote
        try:
            quoted = f"> {rewritten}"
            caption_msg = await client.send_message(target_chat, quoted)
            return caption_msg
        except Exception as e:
            print(f"[CAPTION] Could not send caption: {e}")
            return None


async def forward_poll(client, target_chat, msg, status_msg, original_chat=None, sender=None):
    """
    For quiz polls: download the question image, upload to a public host,
    and send ONLY the direct image URL so it can be pasted into Google Lens.
    Non-quiz polls are silently skipped.
    """
    poll = msg.poll
    if poll is None:
        return None

    if poll.type != PollType.QUIZ:
        return None

    try:
        await status_msg.edit("Uploading image...")
    except Exception:
        pass

    image_path = await _download_poll_image(userbot, msg)
    public_url = await upload_image_get_url(image_path, target_chat)

    if image_path:
        try:
            os.remove(image_path)
        except Exception:
            pass

    if not public_url:
        print("[POLL] Image upload failed — no URL to send")
        try:
            await status_msg.edit("Could not upload image.")
        except Exception:
            pass
        return None

    try:
        sent_msg = await client.send_message(
            target_chat,
            public_url,
            disable_web_page_preview=True,
        )
        print(f"[POLL] Sent image URL: {public_url}")
        return sent_msg
    except Exception as e:
        print(f"[POLL] Failed to send URL: {e}")
        return None


# ---------------------------------------------------------------------------
# Fallback: copy message using userbot (handles stickers, animations, etc.)
# ---------------------------------------------------------------------------
async def copy_message_fallback(userbot_client, target_chat, source_chat, msg_id, caption=None):
    """
    Use the userbot's copy_message to copy any message type that we can't
    handle with download+upload (stickers, animations, contacts, locations,
    venues, dice, games, etc.). This works because the userbot has access
    to the source chat.

    Returns the sent message, or None if it fails.
    """
    try:
        sent_msg = await userbot_client.copy_message(
            chat_id=target_chat,
            from_chat_id=source_chat,
            message_id=msg_id,
            caption=caption
        )
        return sent_msg
    except Exception as e:
        print(f"copy_message_fallback failed: {e}")
        return None


def register_msg_mapping(original_chat, original_msg_id, new_chat_id, new_msg_id):
    msg_map[(original_chat, original_msg_id)] = new_msg_id
    _save_msg_map()


# ---------------------------------------------------------------------------
# Core message handler
# ---------------------------------------------------------------------------
async def get_msg(userbot, client, bot, sender, edit_id, status_chat, msg_link, i):

    """ 
    userbot: PyrogramUserBot
    client: PyrogramBotClient  
    bot: TelethonBotClient
    sender: Target chat for content (SAVE_CHANNEL or user DM)
    edit_id: Message ID of the "Processing!" status message in status_chat
    status_chat: Chat where status/progress messages live (user's DM)
    """

    edit = ""
    chat = ""
    round_message = False
    if "?single" in msg_link:
        msg_link = msg_link.split("?single")[0]
    msg_id = int(msg_link.split("/")[-1]) + int(i)
    height, width, duration, thumb_path = 90, 90, 0, None

    # Before doing anything, ensure the bot client can resolve the target chat
    await ensure_target_peer(client, sender)

    # Determine if this message was pinned in the original chat
    was_pinned = False

    if 't.me/c/' in msg_link or 't.me/b/' in msg_link:
        if 't.me/b/' in msg_link:
            chat = str(msg_link.split("/")[-2])
        else:
            chat = int('-100' + str(msg_link.split("/")[-2]))
        file = ""
        try:
            # Ensure the access hash for this channel is in userbot's cache.
            await resolve_peer_safe(userbot, chat)
            msg = await userbot.get_messages(chat, msg_id)

            # Check if this message was pinned in the original chat.
            # Two-stage check:
            #   1. Direct: Pyrogram sets msg.pinned=True on the message object itself
            #      when it is currently pinned (from Telegram's MTProto flags).
            #   2. Fallback: search all pinned message IDs for the chat and check.
            try:
                was_pinned = bool(getattr(msg, 'pinned', False))
                if was_pinned:
                    print(f"[PIN] Message {msg_id} is pinned (direct msg.pinned flag)")
                else:
                    pinned_ids = await get_pinned_msg_ids(userbot, client, chat)
                    was_pinned = msg_id in pinned_ids
                    if was_pinned:
                        print(f"[PIN] Message {msg_id} was pinned in original chat (via pinned list)")
            except Exception as e:
                print(f"[PIN] Could not check pinned status: {e}")

            # ---- POLL HANDLING ----
            if msg.poll is not None:
                edit = await client.edit_message_text(status_chat, edit_id, "Processing poll...")
                sent_msg = await forward_poll(client, sender, msg, edit, original_chat=chat, sender=sender)
                if sent_msg:
                    register_msg_mapping(chat, msg_id, sender, sent_msg.id)
                    await pin_if_channel(client, sender, sent_msg.id, was_pinned=was_pinned)
                await edit.delete()
                return
            # ---- END POLL HANDLING ----

            # ---- TEXT ONLY (no media) ----
            if not msg.media and msg.text:
                edit = await client.edit_message_text(status_chat, edit_id, "Cloning.")
                text = msg.text.markdown if msg.text else ""
                rewritten = rewrite_inline_links(text, chat, sender)
                sent_msg = await client.send_message(sender, rewritten)
                register_msg_mapping(chat, msg_id, sender, sent_msg.id)
                await pin_if_channel(client, sender, sent_msg.id, was_pinned=was_pinned)
                await edit.delete()
                return

            # ---- WEB PAGE PREVIEW ----
            if msg.media == MessageMediaType.WEB_PAGE:
                edit = await client.edit_message_text(status_chat, edit_id, "Cloning.")
                text = msg.text.markdown if msg.text else ""
                rewritten = rewrite_inline_links(text, chat, sender)
                await client.send_message(sender, rewritten)
                await edit.delete()
                return

            # ---- DOWNLOADABLE MEDIA ----
            if msg.media in DOWNLOADABLE_MEDIA:
                edit = await client.edit_message_text(status_chat, edit_id, "Trying to Download.")
                file = await userbot.download_media(
                    msg,
                    progress=progress_for_pyrogram,
                    progress_args=(
                        client,
                        "**DOWNLOADING:**\n",
                        edit,
                        time.time()
                    )
                )

                # If download failed or file is empty, try copy_message as fallback
                if not file or not os.path.exists(file) or os.path.getsize(file) == 0:
                    print(f"[WARN] download_media returned empty/missing file for msg {msg_id}, trying copy_message fallback")
                    edit = await client.edit_message_text(status_chat, edit_id, "Trying to copy...")
                    caption = None
                    if msg.caption is not None:
                        caption = rewrite_inline_links(msg.caption, chat, sender)
                    sent_msg = await copy_message_fallback(userbot, sender, chat, msg_id, caption)
                    if sent_msg:
                        register_msg_mapping(chat, msg_id, sender, sent_msg.id)
                        await pin_if_channel(client, sender, sent_msg.id, was_pinned=was_pinned)
                        await edit.delete()
                    else:
                        await client.edit_message_text(status_chat, edit_id, f"Could not save message `{msg_link}`")
                    return

                print(file)
                await edit.edit('Preparing to Upload!')
                caption = None
                if msg.caption is not None:
                    caption = rewrite_inline_links(msg.caption, chat, sender)

                sent_msg = None
                if msg.media==MessageMediaType.VIDEO_NOTE:
                    round_message = True
                    print("Trying to get metadata")
                    data = video_metadata(file)
                    height, width, duration = data["height"], data["width"], data["duration"]
                    print(f'd: {duration}, w: {width}, h:{height}')
                    try:
                        thumb_path = await screenshot(file, duration, sender)
                    except Exception:
                        thumb_path = None
                    sent_msg = await client.send_video_note(
                        chat_id=sender,
                        video_note=file,
                        length=height, duration=duration,
                        thumb=thumb_path,
                        progress=progress_for_pyrogram,
                        progress_args=(
                            client,
                            '**UPLOADING:**\n',
                            edit,
                            time.time()
                        )
                    )
                elif msg.media==MessageMediaType.VIDEO and msg.video.mime_type in ["video/mp4", "video/x-matroska"]:
                    print("Trying to get metadata")
                    data = video_metadata(file)
                    height, width, duration = data["height"], data["width"], data["duration"]
                    print(f'd: {duration}, w: {width}, h:{height}')
                    try:
                        thumb_path = await screenshot(file, duration, sender)
                    except Exception:
                        thumb_path = None
                    sent_msg = await client.send_video(
                        chat_id=sender,
                        video=file,
                        caption=caption,
                        supports_streaming=True,
                        height=height, width=width, duration=duration,
                        thumb=thumb_path,
                        progress=progress_for_pyrogram,
                        progress_args=(
                            client,
                            '**UPLOADING:**\n',
                            edit,
                            time.time()
                        )
                    )

                elif msg.media==MessageMediaType.PHOTO:
                    await edit.edit("Uploading photo.")
                    try:
                        sent_msg = await client.send_photo(
                            chat_id=sender,
                            photo=file,
                            caption=caption,
                            progress=progress_for_pyrogram,
                            progress_args=(
                                client,
                                '**UPLOADING:**\n',
                                edit,
                                time.time()
                            )
                        )
                    except Exception as photo_err:
                        print(f"send_photo failed, falling back to bot.send_file: {photo_err}")
                        sent_msg = await bot.send_file(sender, file, caption=caption)
                elif msg.media==MessageMediaType.STICKER:
                    # Send sticker as document to preserve it
                    sent_msg = await client.send_document(
                        sender, file,
                        caption=caption,
                        progress=progress_for_pyrogram,
                        progress_args=(
                            client, '**UPLOADING:**\n', edit, time.time()
                        )
                    )
                elif msg.media==MessageMediaType.ANIMATION:
                    # GIF / animation - send as animation
                    try:
                        sent_msg = await client.send_animation(
                            chat_id=sender,
                            animation=file,
                            caption=caption,
                            progress=progress_for_pyrogram,
                            progress_args=(
                                client, '**UPLOADING:**\n', edit, time.time()
                            )
                        )
                    except Exception:
                        sent_msg = await client.send_document(
                            sender, file,
                            caption=caption,
                            progress=progress_for_pyrogram,
                            progress_args=(
                                client, '**UPLOADING:**\n', edit, time.time()
                            )
                        )
                elif msg.media==MessageMediaType.AUDIO:
                    sent_msg = await client.send_audio(
                        chat_id=sender,
                        audio=file,
                        caption=caption,
                        progress=progress_for_pyrogram,
                        progress_args=(
                            client, '**UPLOADING:**\n', edit, time.time()
                        )
                    )
                elif msg.media==MessageMediaType.VOICE:
                    sent_msg = await client.send_voice(
                        chat_id=sender,
                        voice=file,
                        caption=caption,
                        progress=progress_for_pyrogram,
                        progress_args=(
                            client, '**UPLOADING:**\n', edit, time.time()
                        )
                    )
                else:
                    thumb_path=thumbnail(sender)
                    sent_msg = await client.send_document(
                        sender, file,
                        caption=caption,
                        thumb=thumb_path,
                        progress=progress_for_pyrogram,
                        progress_args=(
                            client, '**UPLOADING:**\n', edit, time.time()
                        )
                    )

                # Register mapping and pin the message
                if sent_msg:
                    register_msg_mapping(chat, msg_id, sender, sent_msg.id)
                    await pin_if_channel(client, sender, sent_msg.id, was_pinned=was_pinned)

                try:
                    os.remove(file)
                    if os.path.isfile(file) == True:
                        os.remove(file)
                except Exception:
                    pass
                await edit.delete()

            # ---- OTHER MEDIA (contact, location, venue, dice, game, etc.) ----
            # These can't be downloaded, so use copy_message via the userbot
            else:
                edit = await client.edit_message_text(status_chat, edit_id, "Copying message...")
                caption = None
                if msg.caption is not None:
                    caption = rewrite_inline_links(msg.caption, chat, sender)
                sent_msg = await copy_message_fallback(userbot, sender, chat, msg_id, caption)
                if sent_msg:
                    register_msg_mapping(chat, msg_id, sender, sent_msg.id)
                    await pin_if_channel(client, sender, sent_msg.id, was_pinned=was_pinned)
                else:
                    # Last resort: send whatever text we can extract
                    fallback_text = ""
                    if msg.text:
                        fallback_text = msg.text.markdown if msg.text else ""
                    if msg.caption:
                        fallback_text += ("\n" if fallback_text else "") + msg.caption
                    if fallback_text:
                        rewritten = rewrite_inline_links(fallback_text, chat, sender)
                        sent_msg = await client.send_message(sender, f"[Unsupported media] {rewritten}")
                        register_msg_mapping(chat, msg_id, sender, sent_msg.id)
                        await pin_if_channel(client, sender, sent_msg.id, was_pinned=was_pinned)
                    else:
                        print(f"[WARN] Could not save message {msg_id} — no text, no downloadable media")
                await edit.delete()
                return

        except (ChannelBanned, ChannelInvalid, ChannelPrivate, ChatIdInvalid, ChatInvalid):
            await client.edit_message_text(status_chat, edit_id, "Cannot access this channel. Make sure the userbot has joined it.")
            return
        except PeerIdInvalid:
            await client.edit_message_text(
                status_chat, edit_id,
                "**Peer id invalid** — the userbot account is not a member of "
                "this channel.\n\nSend the channel's invite link first so the "
                "userbot can join, then retry."
            )
            return
        except Exception as e:
            print(e)
            if "messages.SendMedia" in str(e) \
            or "SaveBigFilePartRequest" in str(e) \
            or "SendMediaRequest" in str(e) \
            or "number of file parts" in str(e) \
            or str(e) == "File size equals to 0 B":
                try:
                    if msg.media==MessageMediaType.VIDEO and msg.video.mime_type in ["video/mp4", "video/x-matroska"]:
                        UT = time.time()
                        uploader = await fast_upload(f'{file}', f'{file}', UT, bot, edit, '**UPLOADING:**')
                        attributes = [DocumentAttributeVideo(duration=duration, w=width, h=height, round_message=round_message, supports_streaming=True)]
                        sent_msg = await bot.send_file(sender, uploader, caption=caption, thumb=thumb_path, attributes=attributes, force_document=False)
                    elif msg.media==MessageMediaType.VIDEO_NOTE:
                        UT = time.time()
                        uploader = await fast_upload(f'{file}', f'{file}', UT, bot, edit, '**UPLOADING:**')
                        attributes = [DocumentAttributeVideo(duration=duration, w=width, h=height, round_message=round_message, supports_streaming=True)]
                        sent_msg = await bot.send_file(sender, uploader, caption=caption, thumb=thumb_path, attributes=attributes, force_document=False)
                    elif msg.media==MessageMediaType.PHOTO:
                        UT = time.time()
                        sent_msg = await bot.send_file(sender, file, caption=caption)
                    else:
                        UT = time.time()
                        uploader = await fast_upload(f'{file}', f'{file}', UT, bot, edit, '**UPLOADING:**')
                        sent_msg = await bot.send_file(sender, uploader, caption=caption, thumb=thumb_path, force_document=True)

                    if sent_msg:
                        register_msg_mapping(chat, msg_id, sender, sent_msg.id)
                        await pin_if_channel(client, sender, sent_msg.id, was_pinned=was_pinned)

                    if os.path.isfile(file) == True:
                        os.remove(file)
                except Exception as e2:
                    print(f"Telethon fallback also failed: {e2}")
                    # Telethon upload failed too — try copy_message as last resort
                    try:
                        os.remove(file)
                    except Exception:
                        pass
                    caption = None
                    if msg.caption is not None:
                        caption = rewrite_inline_links(msg.caption, chat, sender)
                    sent_msg = await copy_message_fallback(userbot, sender, chat, msg_id, caption)
                    if sent_msg:
                        register_msg_mapping(chat, msg_id, sender, sent_msg.id)
                        await pin_if_channel(client, sender, sent_msg.id, was_pinned=was_pinned)
                        await client.edit_message_text(status_chat, edit_id, "Saved via copy (upload failed).")
                    else:
                        await client.edit_message_text(status_chat, edit_id, f'Failed to save: `{msg_link}`\n\nError: {str(e2)}')
                    return
            else:
                # Non-upload error — try copy_message fallback before giving up
                caption = None
                if msg.caption is not None:
                    caption = rewrite_inline_links(msg.caption, chat, sender)
                sent_msg = await copy_message_fallback(userbot, sender, chat, msg_id, caption)
                if sent_msg:
                    register_msg_mapping(chat, msg_id, sender, sent_msg.id)
                    await pin_if_channel(client, sender, sent_msg.id, was_pinned=was_pinned)
                    await client.edit_message_text(status_chat, edit_id, "Saved via copy (direct upload failed).")
                else:
                    await client.edit_message_text(status_chat, edit_id, f'Failed to save: `{msg_link}`\n\nError: {str(e)}')
                try:
                    os.remove(file)
                except Exception:
                    pass
                return
        try:
            os.remove(file)
            if os.path.isfile(file) == True:
                os.remove(file)
        except Exception:
            pass
        await edit.delete()
    else:
        edit = await client.edit_message_text(status_chat, edit_id, "Cloning.")
        chat = msg_link.split("t.me")[1].split("/")[1]
        try:
            msg = await client.get_messages(chat, msg_id)

            # Check if this message was pinned in the original public chat.
            # Two-stage check: direct msg.pinned flag first, then full pinned list.
            try:
                was_pinned = bool(getattr(msg, 'pinned', False))
                if was_pinned:
                    print(f"[PIN] Message {msg_id} is pinned (direct msg.pinned flag, public chat)")
                else:
                    pinned_ids = await get_pinned_msg_ids(userbot, client, chat)
                    was_pinned = msg_id in pinned_ids
                    if was_pinned:
                        print(f"[PIN] Message {msg_id} was pinned in original public chat (via pinned list)")
            except Exception as e:
                print(f"[PIN] Could not check pinned status for public chat: {e}")

            # ---- POLL HANDLING for public chats ----
            if msg.poll is not None:
                sent_msg = await forward_poll(client, sender, msg, edit, original_chat=chat, sender=sender)
                if sent_msg:
                    register_msg_mapping(chat, msg_id, sender, sent_msg.id)
                    await pin_if_channel(client, sender, sent_msg.id, was_pinned=was_pinned)
                await edit.delete()
                return

            if msg.empty:
                new_link = f't.me/b/{chat}/{int(msg_id)}'
                return await get_msg(userbot, client, bot, sender, edit_id, status_chat, new_link, i)

            # For public chats, use copy_message
            sent_msg = await client.copy_message(sender, chat, msg_id)
            if sent_msg:
                register_msg_mapping(chat, msg_id, sender, sent_msg.id)
                await pin_if_channel(client, sender, sent_msg.id, was_pinned=was_pinned)

                if msg.text:
                    original_text = msg.text.markdown if msg.text else ""
                    rewritten = rewrite_inline_links(original_text, chat, sender)
                    if rewritten != original_text:
                        try:
                            await client.edit_message_text(sender, sent_msg.id, rewritten)
                        except Exception as e:
                            print(f"Could not edit message for inline link rewriting: {e}")

        except Exception as e:
            print(e)
            return await client.edit_message_text(status_chat, edit_id, f'Failed to save: `{msg_link}`\n\nError: {str(e)}')
        await edit.delete()

async def get_bulk_msg(userbot, client, sender, msg_link, i):
    x = await client.send_message(sender, "Processing!")
    await get_msg(userbot, client, Drone, sender, x.id, sender, msg_link, i)
