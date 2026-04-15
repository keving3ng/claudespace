#!/usr/bin/env python3
"""
idea-forge — AI-powered project idea generator

Watches what's trending on GitHub in Kevin's stack (Python, TypeScript, Go),
then asks Claude to suggest weekend projects he'd actually want to build.
The recursion: an AI deciding what an AI should build next.

Usage:
    idea_forge.py trending                  # what's hot right now
    idea_forge.py trending --lang typescript
    idea_forge.py suggest                   # generate tailored project ideas
    idea_forge.py suggest --raw             # show trending context only (no Claude)
    idea_forge.py save "My cool idea"       # append an idea to ideas.json
    idea_forge.py list                      # list saved ideas
    idea_forge.py help
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent.parent
FORGE_DIR = Path(__file__).parent
IDEAS_FILE = FORGE_DIR / "ideas.json"

# Kevin's stack — what to watch
WATCHED_LANGUAGES = ["python", "typescript", "go"]

# GitHub search: repos created in the last N days
TRENDING_WINDOW_DAYS = 90

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


# ─── GitHub Search API ────────────────────────────────────────────────────────


def _gh_request(url: str) -> dict | None:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "idea-forge/1.0",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print("⚠️  GitHub rate limit hit. Set GITHUB_TOKEN for 5000 req/hr.", file=sys.stderr)
        else:
            body = e.read().decode("utf-8", errors="replace")
            print(f"⚠️  GitHub API {e.code}: {body[:150]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"⚠️  Request failed: {e}", file=sys.stderr)
        return None


def fetch_trending(language: str, days: int = TRENDING_WINDOW_DAYS, n: int = 8) -> list[dict]:
    """
    Fetch the most-starred repos in a language created in the last `days` days.
    Returns a list of repo dicts (name, description, stars, url, topics).
    """
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    q = urllib.parse.quote(f"language:{language} created:>{cutoff}")
    url = (
        f"https://api.github.com/search/repositories"
        f"?q={q}&sort=stars&order=desc&per_page={n}"
    )
    data = _gh_request(url)
    if not data or "items" not in data:
        return []

    results = []
    for item in data["items"]:
        results.append({
            "name": item.get("full_name", ""),
            "description": (item.get("description") or "")[:120],
            "stars": item.get("stargazers_count", 0),
            "url": item.get("html_url", ""),
            "topics": item.get("topics", [])[:5],
            "language": item.get("language", language),
        })
    return results


def fetch_all_trending(languages: list[str] = WATCHED_LANGUAGES, n_each: int = 6) -> dict[str, list[dict]]:
    """Fetch trending repos for each watched language."""
    result = {}
    for lang in languages:
        repos = fetch_trending(lang, n=n_each)
        if repos:
            result[lang] = repos
    return result


# ─── Claude API ───────────────────────────────────────────────────────────────


def claude_call(prompt: str, max_tokens: int = 800) -> str:
    if not ANTHROPIC_API_KEY:
        return "⚠️  ANTHROPIC_API_KEY not set. Can't generate ideas without Claude."

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
        with urllib.request.urlopen(req, timeout=40) as resp:
            result = json.loads(resp.read())
            return result["content"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return f"[Claude API error {e.code}: {body[:200]}]"
    except Exception as e:
        return f"[Claude API error: {e}]"


# ─── Formatting ───────────────────────────────────────────────────────────────


def format_trending_section(trending: dict[str, list[dict]]) -> str:
    """Format trending repos as a readable block for both display and Claude prompts."""
    lines = []
    for lang, repos in trending.items():
        lines.append(f"\n### {lang.title()}")
        for r in repos:
            stars = f"★{r['stars']:,}"
            topics = "  [" + ", ".join(r["topics"]) + "]" if r["topics"] else ""
            lines.append(f"  {r['name']:<45} {stars:>8}")
            if r["description"]:
                lines.append(f"    ↳ {r['description']}{topics}")
    return "\n".join(lines)


# ─── Commands ─────────────────────────────────────────────────────────────────


def cmd_trending(args: list[str]):
    """Show what's trending on GitHub in Kevin's stack."""
    # Optional --lang filter
    lang_filter = None
    if "--lang" in args:
        idx = args.index("--lang")
        if idx + 1 < len(args):
            lang_filter = args[idx + 1].lower()

    langs = [lang_filter] if lang_filter else WATCHED_LANGUAGES

    print(f"🔥 idea-forge: trending now  ({TRENDING_WINDOW_DAYS}-day window)\n")

    trending = fetch_all_trending(langs)
    if not trending:
        print("Could not fetch trending repos. Check your network or GitHub rate limits.")
        return

    print(format_trending_section(trending))
    print(f"\n  {sum(len(v) for v in trending.values())} repos across {len(trending)} language(s)")
    print("  Run `idea_forge.py suggest` to get project ideas based on this.\n")


def cmd_suggest(args: list[str]):
    """Analyze trending repos and suggest tailored project ideas."""
    raw = "--raw" in args

    print("💡 idea-forge: generating project ideas...\n")

    trending = fetch_all_trending()
    if not trending:
        print("⚠️  Could not fetch trending repos — check your network.")
        return

    trending_block = format_trending_section(trending)

    if raw:
        print("── Trending repos (what Claude would see) ──────────────────")
        print(trending_block)
        print("\n(Run without --raw to let Claude turn this into project ideas.)")
        return

    if not ANTHROPIC_API_KEY:
        print("⚠️  ANTHROPIC_API_KEY not set.")
        print("\nHere's what's trending — imagine the ideas:\n")
        print(trending_block)
        return

    today = date.today().strftime("%B %d, %Y")

    prompt = f"""You are idea-forge, a project idea generator for Kevin Geng.

Today is {today}. Kevin is a full-stack software engineer in Toronto who builds:
- matchamap.club — an opinionated matcha cafe map (React, OpenStreetMap data)
- kegbot — his Python personal assistant / CLI (with Claude API superpowers)
- claudespace — an autonomous AI build lab where you (Claude) run builds while he sleeps
- recipe-ai — an AI cooking assistant CLI
- dev-insights — a GitHub activity heatmap/streak tracker

Kevin's stack: Python, TypeScript/React, Java/Spring Boot, some Go.
His vibe: fun + useful, personal tools, automation, maps, Discord bots, cooking, ML/AI experiments.
He is NOT looking for: another CRUD app, enterprise SaaS boilerplate, or anything that's just "put AI on X".

Here's what's trending on GitHub right now in his stack:
{trending_block}

---

Generate exactly 5 weekend project ideas tailored to Kevin.

For each idea:
1. Give it a punchy name (2–4 words, stylized like his existing projects)
2. One-sentence pitch (what it does, why it's fun)
3. Stack: 2–4 specific technologies from his world
4. Secret ingredient: the one thing that makes it *Kevin-specific* — not generic
5. Estimated scope: "afternoon", "weekend", or "week"

Format each idea like:
**[name]** (scope)
> pitch
Stack: ...
Kevin angle: ...

Be genuinely creative. Think about gaps in what he's already built. Think about the intersection
of what's trending and what Kevin would actually use. One of the five should be slightly wild/experimental.
Don't suggest "a recipe recommender" (he already has one) or "a GitHub dashboard" (he has that too).
"""

    print("[claude] Analyzing what's trending and who Kevin is...\n")
    ideas = claude_call(prompt, max_tokens=900)

    print("─" * 64)
    print(ideas)
    print("─" * 64)
    print("\n💾  Like one? Run: idea_forge.py save \"<idea name>\"")
    print()


def cmd_save(args: list[str]):
    """Save a project idea to ideas.json."""
    if not args:
        print("Usage: idea_forge.py save \"<your idea description>\"")
        sys.exit(1)

    idea_text = " ".join(args)

    ideas = []
    if IDEAS_FILE.exists():
        try:
            ideas = json.loads(IDEAS_FILE.read_text())
        except Exception:
            ideas = []

    entry = {
        "id": len(ideas) + 1,
        "idea": idea_text,
        "saved_at": date.today().isoformat(),
    }
    ideas.append(entry)
    IDEAS_FILE.write_text(json.dumps(ideas, indent=2))
    print(f"✅ Saved idea #{entry['id']}: {idea_text}")
    print(f"   → {IDEAS_FILE}")


def cmd_list(args: list[str]):
    """List all saved ideas."""
    if not IDEAS_FILE.exists():
        print("No ideas saved yet. Run `idea_forge.py save \"<idea>\"` to save one.")
        return

    try:
        ideas = json.loads(IDEAS_FILE.read_text())
    except Exception as e:
        print(f"❌ Could not parse ideas.json: {e}")
        return

    if not ideas:
        print("ideas.json is empty. Go generate some ideas.")
        return

    print(f"💡 Saved ideas ({len(ideas)})\n")
    for entry in ideas:
        print(f"  #{entry['id']}  [{entry.get('saved_at', '?')}]  {entry['idea']}")
    print()


def cmd_help():
    print("""
💡 idea-forge — AI-powered project idea generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The recursive one: an AI figuring out what an AI should build next.
Watches what's trending on GitHub in your stack. Asks Claude to suggest
weekend projects that intersect trending tech with what Kevin actually cares about.

USAGE
    idea_forge.py <command> [options]

COMMANDS

  trending                Show trending repos in Python, TypeScript, Go
    --lang <language>       Filter to one language (python / typescript / go)

  suggest                 Generate 5 tailored project ideas via Claude
    --raw                   Show trending context only (no API call)

  save "<idea>"           Save a project idea to ideas.json
  list                    List saved ideas

  help                    This help

SETUP
    Needs ANTHROPIC_API_KEY in .env for `suggest`.
    GITHUB_TOKEN optional (raises rate limit from 60 to 5000 req/hr).

EXAMPLES
    idea_forge.py trending
    idea_forge.py trending --lang go
    idea_forge.py suggest
    idea_forge.py save "matcha ranking CLI with Yelp + OSM fusion"
    idea_forge.py list

NOTES
    Trending = most-starred repos created in the last 90 days.
    Ideas are Kevin-specific, not generic. Prompt bakes in his stack,
    active projects, and what he's already built so Claude won't repeat itself.

Built by Claude (Cycle 8). Because recursion is the sincerest form of flattery.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

COMMANDS = {
    "trending": cmd_trending,
    "suggest": cmd_suggest,
    "save": cmd_save,
    "list": cmd_list,
    "help": lambda _: cmd_help(),
    "--help": lambda _: cmd_help(),
    "-h": lambda _: cmd_help(),
}


def main():
    argv = sys.argv[1:]

    if not argv:
        cmd_trending([])  # default: show what's hot
        return

    command = argv[0]
    rest = argv[1:]

    if command not in COMMANDS:
        print(f"❓ Unknown command: {command}")
        print("Run `idea_forge.py help` for usage.")
        sys.exit(1)

    COMMANDS[command](rest)


if __name__ == "__main__":
    main()
