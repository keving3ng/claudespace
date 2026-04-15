#!/usr/bin/env python3
"""
forge — AI-powered weekend project idea generator

Analyzes trending GitHub repos in your tech stack, then uses Claude to
generate personalized project ideas tailored to who you are and what you
already build. Zero new dependencies. Pure stdlib + Claude API.

Usage:
    forge ideas                    # 5 ideas from trending repos in your stack
    forge ideas --lang python      # focus on one language
    forge ideas --lang typescript
    forge ideas --lang go
    forge ideas --save             # save ideas to ideas.json
    forge browse                   # browse previously saved ideas
    forge browse --top             # show highest-rated ideas first
    forge help
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

FORGE_DIR = Path(__file__).parent
REPO_ROOT = FORGE_DIR.parent.parent
IDEAS_FILE = FORGE_DIR / "ideas.json"

KEVIN_STACK = ["python", "typescript", "go"]

# Kevin's profile for the Claude prompt — tell it exactly who we're building for
KEVIN_PROFILE = """
Kevin Geng is a full-stack software engineer at Faire in Toronto.
Stack: React, TypeScript, Python, Go, Java/Kotlin/Spring Boot, AWS.
Active projects:
  - matchamap.club — opinionated matcha cafe finder (maps + place data)
  - claudespace — autonomous AI build lab (this repo, running Claude cycles)
  - kegbot — Python personal assistant with daily briefings, Discord integration
  - cookbook — recipe collection, interested in recipe-ai and meal planning
Interests: personal automation, Discord bots, CLI tools, maps, cooking,
           ML/AI, gaming, transit, personal finance, teaching + workshops.
He loves tools that are "fun + useful" and things that make his daily life
slightly better without requiring a PhD to set up.
"""

# ─── Env ──────────────────────────────────────────────────────────────────────


def load_env():
    for env_path in [
        FORGE_DIR / ".env",
        REPO_ROOT / ".env",
        REPO_ROOT / "projects" / "kegbot-claude" / ".env",
    ]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")

# ─── GitHub Search ────────────────────────────────────────────────────────────


def _gh_request(url: str) -> dict | list | None:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "idea-forge/1.0",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"  [github] HTTP {e.code}: {body[:120]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  [github] Error: {e}", file=sys.stderr)
        return None


def fetch_trending_repos(lang: str, days_back: int = 180, limit: int = 12) -> list[dict]:
    """
    Fetch recently-created repos for a language with meaningful star counts.
    We use 'created' date filtering to find genuinely new projects that are
    gaining traction — not just eternally popular giants.
    """
    # Calculate cutoff date
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")

    # Stars threshold: >10 for newer projects (meaningful interest, not noise)
    query = urllib.parse.quote(f"language:{lang} stars:>10 created:>{cutoff}")
    url = (
        f"https://api.github.com/search/repositories"
        f"?q={query}&sort=stars&order=desc&per_page={limit}"
    )

    data = _gh_request(url)
    if not data or not isinstance(data, dict):
        return []

    items = data.get("items", [])
    result = []
    for item in items:
        result.append({
            "name": item.get("full_name", ""),
            "description": item.get("description") or "",
            "stars": item.get("stargazers_count", 0),
            "language": item.get("language") or lang,
            "topics": item.get("topics", []),
            "url": item.get("html_url", ""),
            "created_at": item.get("created_at", "")[:10],
        })
    return result


def fetch_all_trending(langs: list[str]) -> list[dict]:
    """Fetch trending repos across multiple languages with rate-limit awareness."""
    all_repos = []
    for i, lang in enumerate(langs):
        if i > 0:
            time.sleep(1)  # be polite to GitHub search API
        repos = fetch_trending_repos(lang)
        all_repos.extend(repos)
        print(f"  [{lang}] {len(repos)} trending repo(s) found")
    return all_repos


# ─── Claude API ───────────────────────────────────────────────────────────────


def claude_call(prompt: str, max_tokens: int = 1200) -> str:
    if not ANTHROPIC_API_KEY:
        return "⚠️  ANTHROPIC_API_KEY not set — can't generate ideas without Claude."

    payload = json.dumps({
        "model": "claude-opus-4-6",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            result = json.loads(resp.read())
            return result["content"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return f"[Claude API error {e.code}: {body[:200]}]"
    except Exception as e:
        return f"[Claude API error: {e}]"


# ─── Idea generation ──────────────────────────────────────────────────────────


def build_idea_prompt(repos: list[dict], focus_lang: str | None) -> str:
    """
    Build a Claude prompt that uses trending repo data as inspiration
    for personalized weekend project ideas.
    """
    today = datetime.now().strftime("%B %d, %Y")

    # Format repos as a compact list for the prompt
    repo_lines = []
    for r in repos[:25]:  # cap at 25 to keep prompt size reasonable
        topics = ", ".join(r["topics"][:4]) if r["topics"] else "—"
        desc = r["description"][:80] if r["description"] else "(no description)"
        repo_lines.append(
            f"  • {r['name']} ({r['language']}, ★{r['stars']}) — {desc}"
            + (f" [topics: {topics}]" if r["topics"] else "")
        )

    repos_text = "\n".join(repo_lines) if repo_lines else "  (no trending repos found)"

    lang_note = f"Focus: The developer is specifically interested in {focus_lang} right now.\n" if focus_lang else ""

    return f"""Today is {today}. You are idea-forge, an AI project idea generator.

## About the Developer
{KEVIN_PROFILE.strip()}

## What's Trending on GitHub Right Now
These are recently-created repositories gaining traction in the developer's tech stack:
{repos_text}

{lang_note}
## Your Task
Generate exactly 5 weekend project ideas tailored to this developer.

Rules:
- Each idea should be **buildable solo in 1–3 days** with their stack
- Draw **inspiration from the trends** above (themes, technologies, patterns) — not copies
- Each idea should feel **personal** — something Kevin specifically would enjoy building and using
- Mix practical utility with fun; avoid generic CRUD apps or tutorials
- Think about what would delight him when he opens his laptop on a Saturday morning

## Output Format (strictly follow this):
For each idea, output:

### N. [Project Name] — [Tagline]
**What it is:** One sentence.
**Why Kevin:** One sentence on why this fits him specifically.
**Stack:** Technologies (be specific).
**Weekend plan:** 3 bullet points — what to build Day 1, Day 2, Day 3 (or "Day 1-2" for 2-day projects).
**Wildcard hook:** One unexpected feature or twist that makes it memorable.

---

Be creative. Be specific. No boilerplate. These ideas should make him actually want to close this terminal and go build something.
"""


def generate_ideas(repos: list[dict], focus_lang: str | None) -> str:
    prompt = build_idea_prompt(repos, focus_lang)
    print("\n[claude] Synthesizing trends into personalized project ideas...")
    return claude_call(prompt, max_tokens=1500)


# ─── Ideas storage ────────────────────────────────────────────────────────────


def load_ideas() -> list[dict]:
    if not IDEAS_FILE.exists():
        return []
    try:
        return json.loads(IDEAS_FILE.read_text())
    except Exception:
        return []


def save_ideas(raw_text: str, langs_used: list[str], repo_count: int) -> Path:
    ideas = load_ideas()
    entry = {
        "id": len(ideas) + 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "languages": langs_used,
        "repo_count": repo_count,
        "raw": raw_text,
    }
    ideas.append(entry)
    IDEAS_FILE.write_text(json.dumps(ideas, indent=2))
    return IDEAS_FILE


# ─── Commands ─────────────────────────────────────────────────────────────────


def cmd_ideas(args: list[str]):
    save = "--save" in args
    focus_lang = None

    if "--lang" in args:
        idx = args.index("--lang")
        if idx + 1 < len(args):
            focus_lang = args[idx + 1].lower()

    langs = [focus_lang] if focus_lang else KEVIN_STACK

    print("💡 idea-forge — Weekend Project Ideas")
    print("━" * 42)
    print()
    print(f"Searching GitHub for trending repos in: {', '.join(langs)}")
    print()

    repos = fetch_all_trending(langs)

    if not repos:
        print("\n⚠️  Could not fetch trending repos. Check network / GITHUB_TOKEN.")
        print("   (GitHub search API: 10 req/min unauthenticated, 30 with token)")
        return

    total = len(repos)
    print(f"\n  {total} repo(s) collected — sending to Claude...\n")

    ideas_text = generate_ideas(repos, focus_lang)

    print("\n" + "═" * 62)
    print(ideas_text)
    print("═" * 62)
    print()

    if save:
        path = save_ideas(ideas_text, langs, total)
        print(f"✅ Ideas saved to {path.relative_to(REPO_ROOT)}")
        print("   Run `forge browse` to see all saved idea sets.\n")
    else:
        print("💾 Tip: run `forge ideas --save` to keep these for later.")
        print()


def cmd_browse(args: list[str]):
    top = "--top" in args
    ideas = load_ideas()

    if not ideas:
        print("📭 No saved ideas yet. Run `forge ideas --save` to get started.")
        return

    print(f"📚 idea-forge — Saved Ideas ({len(ideas)} session(s))\n")

    # Show in reverse chronological order (or as-is if --top, since we can't rate yet)
    entries = list(reversed(ideas)) if not top else ideas

    for entry in entries:
        dt = entry.get("generated_at", "")[:10]
        langs = ", ".join(entry.get("languages", []))
        repo_count = entry.get("repo_count", "?")
        entry_id = entry.get("id", "?")

        print(f"── Session #{entry_id}  {dt}  [{langs}]  {repo_count} repos analyzed")
        print()

        raw = entry.get("raw", "(no content)")
        # Trim very long outputs for browsing
        lines = raw.splitlines()
        if len(lines) > 60:
            print("\n".join(lines[:60]))
            print(f"\n  ... ({len(lines) - 60} more lines — open ideas.json to read in full)")
        else:
            print(raw)

        print()
        print("─" * 62)
        print()


def cmd_help():
    print("""
💡 idea-forge — Weekend project idea generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USAGE
    forge <command> [options]

COMMANDS

  ideas                      Generate 5 weekend project ideas
    --lang LANG                Focus on one language (python/typescript/go)
    --save                     Save ideas to ideas.json

  browse                     Browse previously saved idea sets
    --top                      Show oldest-first (default: newest-first)

  help                       Show this help

SETUP
  Requires ANTHROPIC_API_KEY in .env for idea generation.
  Optionally add GITHUB_TOKEN for higher GitHub API rate limits.

HOW IT WORKS
  1. Searches GitHub for recently-created repos gaining traction
     in Python, TypeScript, and Go (last 6 months, 10+ stars)
  2. Feeds trending repo data + Kevin's profile to Claude
  3. Claude generates 5 personalized weekend project ideas with
     day-by-day build plans and "wildcard hooks"

EXAMPLES
    forge ideas
    forge ideas --lang python --save
    forge browse

Built by Claude (Cycle 8). Because sometimes you need an AI to tell
you what to build with AI.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────


COMMANDS = {
    "ideas": cmd_ideas,
    "browse": cmd_browse,
    "help": lambda _: cmd_help(),
    "--help": lambda _: cmd_help(),
    "-h": lambda _: cmd_help(),
}


def main():
    argv = sys.argv[1:]

    if not argv:
        cmd_help()
        return

    command = argv[0]
    rest = argv[1:]

    if command not in COMMANDS:
        print(f"❓ Unknown command: {command}")
        print("Run `forge help` for available commands.")
        sys.exit(1)

    COMMANDS[command](rest)


if __name__ == "__main__":
    main()
