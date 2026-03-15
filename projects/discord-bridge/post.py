#!/usr/bin/env python3
"""
discord-bridge/post.py — Post a message to Discord from Claude.

Two modes:
  1. Webhook (fast, no bot required): direct HTTP POST to a webhook URL
  2. Outbox queue (requires bot.py running): writes to .state/discord_outbox.json
     and the bot picks it up on its next 30-second poll

The webhook mode is what Claude's cron cycles use for immediate dispatch.
The outbox mode is a fallback when you want fire-and-forget without HTTP.

Usage:
    # Post directly via webhook
    python post.py "Cycle 7 done — built kegbot-claude briefing tool 🎉"

    # Post via outbox (if bot.py is running)
    python post.py --outbox "Question for you: do you want weather in celsius or fahrenheit?"

    # Post a formatted journal entry
    python post.py --journal path/to/cycle_entry.txt

    # Read from stdin
    echo "some message" | python post.py -
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the discord-bridge directory or parent
load_dotenv(Path(__file__).parent / ".env")
load_dotenv()  # fallback to cwd

WEBHOOK_URL   = os.environ.get("DISCORD_WEBHOOK_URL", "")
REPO_ROOT     = Path(os.environ.get("CLAUDESPACE_ROOT", Path(__file__).parent.parent.parent))
OUTBOX_FILE   = REPO_ROOT / ".state" / "discord_outbox.json"

CLAUDE_AVATAR = "https://avatars.githubusercontent.com/u/132310085"  # Anthropic org avatar
CLAUDE_NAME   = "Claude (Autonomous)"


def post_webhook(content: str, username: str = CLAUDE_NAME) -> bool:
    """POST to Discord webhook. Returns True on success."""
    if not WEBHOOK_URL or WEBHOOK_URL == "https://discord.com/api/webhooks/your_webhook_url_here":
        print("Error: DISCORD_WEBHOOK_URL not configured.", file=sys.stderr)
        return False

    payload = json.dumps({
        "content": content,
        "username": username,
        "avatar_url": CLAUDE_AVATAR,
    }).encode("utf-8")

    req = urllib.request.Request(
        WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status in (200, 204):
                return True
            print(f"Webhook returned {resp.status}", file=sys.stderr)
            return False
    except urllib.error.HTTPError as e:
        print(f"Webhook HTTP error {e.code}: {e.reason}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Webhook error: {e}", file=sys.stderr)
        return False


def post_outbox(content: str) -> bool:
    """Append message to outbox queue for bot.py to pick up."""
    OUTBOX_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if OUTBOX_FILE.exists():
        try:
            existing = json.loads(OUTBOX_FILE.read_text())
        except json.JSONDecodeError:
            existing = []
    existing.append({"content": content, "queued_at": datetime.now(timezone.utc).isoformat()})
    OUTBOX_FILE.write_text(json.dumps(existing, indent=2))
    print(f"[outbox] queued: {content[:60]}...")
    return True


def format_cycle_summary(cycle_num: int, built: str, next_task: str) -> str:
    """Format a standard cycle-complete Discord notification."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"**Cycle {cycle_num} complete** _{ts}_\n"
        f"> {built}\n\n"
        f"**Next:** {next_task}"
    )


def main():
    parser = argparse.ArgumentParser(description="Post a message to Discord from Claude")
    parser.add_argument("message", nargs="?", help="Message text (or '-' to read stdin)")
    parser.add_argument("--outbox", action="store_true", help="Queue via outbox instead of webhook")
    parser.add_argument("--journal", metavar="FILE", help="Post contents of a file as a journal entry")
    parser.add_argument("--cycle", metavar="N", type=int, help="Include cycle number in header")
    args = parser.parse_args()

    # Build content
    if args.journal:
        path = Path(args.journal)
        if not path.exists():
            print(f"File not found: {path}", file=sys.stderr)
            sys.exit(1)
        text = path.read_text().strip()
        header = f"**Journal — Cycle {args.cycle}**\n" if args.cycle else "**Journal Entry**\n"
        content = header + "```\n" + text[:1800] + "\n```"
    elif args.message == "-":
        content = sys.stdin.read().strip()
    elif args.message:
        content = args.message
    else:
        parser.print_help()
        sys.exit(1)

    if args.cycle and not args.journal:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        content = f"**Cycle {args.cycle}** _{ts}_\n{content}"

    # Dispatch
    if args.outbox:
        success = post_outbox(content)
    else:
        success = post_webhook(content)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
