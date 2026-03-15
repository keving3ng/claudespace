#!/usr/bin/env python3
"""
discord-bridge/bot.py — The persistent half of the Kevin ↔ Claude relay.

Run this once on your machine and leave it going. When you message the
configured channel, your words land in INBOX.md. When Claude leaves
messages in the outbox queue, they get posted to Discord automatically.

Usage:
    pip install -r requirements.txt
    cp .env.example .env  # fill in your values
    python bot.py
"""

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord.ext import tasks
from dotenv import load_dotenv

# ── Config ────────────────────────────────────────────────────────────────────

load_dotenv()

BOT_TOKEN       = os.environ["DISCORD_BOT_TOKEN"]
CHANNEL_ID      = int(os.environ["DISCORD_CHANNEL_ID"])
KEVIN_USER_ID   = int(os.environ["DISCORD_KEVIN_USER_ID"])
REPO_ROOT       = Path(os.environ.get("CLAUDESPACE_ROOT", Path(__file__).parent.parent.parent))

INBOX_FILE      = REPO_ROOT / "INBOX.md"
OUTBOX_FILE     = REPO_ROOT / ".state" / "discord_outbox.json"

OUTBOX_FILE.parent.mkdir(parents=True, exist_ok=True)

# ── Bot setup ─────────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True  # Required to read message text
bot = discord.Client(intents=intents)

# ── Helpers ───────────────────────────────────────────────────────────────────

def now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def append_to_inbox(message_content: str, author: str) -> None:
    """Write Kevin's Discord message into INBOX.md under the ## Open section."""
    inbox = INBOX_FILE.read_text()

    # Find the next question number
    q_numbers = re.findall(r"### Q(\d+)", inbox)
    next_q = max((int(n) for n in q_numbers), default=0) + 1

    timestamp = now_str()
    entry = f"""
### Q{next_q} — {timestamp} ({author} → Claude)

{message_content}

"""

    # Insert before the "## Resolved" section
    if "## Resolved" in inbox:
        inbox = inbox.replace("## Resolved", entry + "## Resolved")
    else:
        inbox += entry

    INBOX_FILE.write_text(inbox)
    print(f"[inbox] wrote Q{next_q} from {author}")


def drain_outbox() -> list[dict]:
    """Read and clear the outbox queue. Returns list of {content, embeds?} dicts."""
    if not OUTBOX_FILE.exists():
        return []
    try:
        data = json.loads(OUTBOX_FILE.read_text())
        messages = data if isinstance(data, list) else [data]
        OUTBOX_FILE.write_text("[]")  # clear
        return messages
    except (json.JSONDecodeError, OSError):
        return []


# ── Event handlers ────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"[bridge] logged in as {bot.user} (id: {bot.user.id})")
    print(f"[bridge] watching channel {CHANNEL_ID}")
    print(f"[bridge] inbox → {INBOX_FILE}")
    print(f"[bridge] outbox ← {OUTBOX_FILE}")
    outbox_watcher.start()


@bot.event
async def on_message(message: discord.Message):
    # Only listen to Kevin, only in the configured channel, not our own messages
    if message.author == bot.user:
        return
    if message.channel.id != CHANNEL_ID:
        return
    if message.author.id != KEVIN_USER_ID:
        await message.channel.send(
            f"> Only Kevin's messages are synced to Claude's inbox. (got message from {message.author.display_name})"
        )
        return

    # Strip bot mention prefix if Kevin typed @Bot something
    content = message.content.strip()
    if bot.user in message.mentions:
        content = content.replace(f"<@{bot.user.id}>", "").strip()
        content = content.replace(f"<@!{bot.user.id}>", "").strip()

    if not content:
        return

    append_to_inbox(content, message.author.display_name)

    # Acknowledge receipt
    await message.add_reaction("📬")
    await message.channel.send(
        f"> Got it. I'll pick this up at the start of my next cycle. "
        f"_(synced to `INBOX.md` at {now_str()})_"
    )


# ── Outbox watcher (polls every 30 seconds) ───────────────────────────────────

@tasks.loop(seconds=30)
async def outbox_watcher():
    messages = drain_outbox()
    if not messages:
        return
    channel = bot.get_channel(CHANNEL_ID)
    if channel is None:
        print(f"[outbox] channel {CHANNEL_ID} not found — skipping")
        return
    for msg in messages:
        content = msg.get("content", "")
        if content:
            await channel.send(content)
            print(f"[outbox] posted: {content[:60]}...")


@outbox_watcher.before_loop
async def before_outbox_watcher():
    await bot.wait_until_ready()


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if BOT_TOKEN == "your_bot_token_here":
        print("Error: DISCORD_BOT_TOKEN not set. Copy .env.example to .env and fill in your token.")
        sys.exit(1)
    bot.run(BOT_TOKEN)
