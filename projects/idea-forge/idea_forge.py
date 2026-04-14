#!/usr/bin/env python3
"""
idea-forge — AI weekend project idea generator

Watches what's trending on GitHub in Kevin's tech stack (Python, TypeScript, Go),
then uses Claude to generate personalized weekend project ideas that fit his profile.
Not generic "learn React" exercises. Things he'd actually build and use.

Usage:
    idea_forge.py forge                   # 3 ideas from trending repos (default)
    idea_forge.py forge --days 7          # narrower trending window
    idea_forge.py forge --language python # focus on one language
    idea_forge.py forge --raw             # show repos only, skip Claude
    idea_forge.py trending                # show trending repos (no idea gen)
    idea_forge.py trending --language go
    idea_forge.py spark                   # one quick wild idea, no analysis
    idea_forge.py save "My Idea"          # save an idea to ideas.json
    idea_forge.py save "My Idea" --desc "it does X"
    idea_forge.py list                    # list saved ideas
    idea_forge.py help
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent.parent
IDEA_FORGE_DIR = Path(__file__).parent
IDEAS_FILE = IDEA_FORGE_DIR / "ideas.json"

KEVIN_LANGUAGES = ["python", "typescript", "go"]

KEVIN_PROFILE = """
Kevin Geng is a full-stack software engineer at Faire in Toronto.
- Primary stack: TypeScript, Python, Go
- Active side projects: matchamap.club (opinionated matcha cafe map), claudespace (autonomous AI build lab)
- Interests: developer tools, personal automation, Discord bots, cooking tools, terminal UIs, maps/GeoJSON
- He likes tools that are useful to *him personally* — not generic portfolio pieces
- He appreciates minimal dependencies, clever use of free APIs, and tools with personality
- Tech he uses: React, Node.js, Flask, stdlib-first Python, terminal dashboards
- He's into gamification of personal habits (coding streaks, recipe ratings), morning routines,
  and anything that makes Monday less painful
""".strip()

# ─── Env ──────────────────────────────────────────────────────────────────────


def load_env():
    for env_path in [
        IDEA_FORGE_DIR / ".env",
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


def _github_request(url: str) -> dict | list | None:
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
            body = e.read().decode("utf-8", errors="replace")
            if "rate limit" in body.lower():
                print(
                    "⚠️  GitHub rate limit hit. Set GITHUB_TOKEN in .env for 5000 req/hr.",
                    file=sys.stderr,
                )
                return None
        if e.code == 422:
            return None  # no results for this query window
        body = e.read().decode("utf-8", errors="replace")
        print(f"⚠️  GitHub API error {e.code}: {body[:200]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"⚠️  Request failed: {e}", file=sys.stderr)
        return None


def fetch_trending_repos(language: str, days: int = 14, per_page: int = 5) -> list[dict]:
    """
    Fetch recently popular repos for a language using GitHub Search API.
    'Recently popular' = created in the last N days, sorted by stars.
    Falls back to a wider window if the narrow search returns nothing.
    """
    for window in [days, days * 2, 90]:
        since_date = (datetime.now() - timedelta(days=window)).strftime("%Y-%m-%d")
        query = f"language:{language} created:>{since_date} stars:>5"
        encoded = urllib.parse.quote(query)
        url = (
            f"https://api.github.com/search/repositories"
            f"?q={encoded}&sort=stars&order=desc&per_page={per_page}"
        )
        data = _github_request(url)
        if data and isinstance(data, dict):
            items = data.get("items", [])
            if items:
                return items
    return []


def _repo_summary(repo: dict) -> str:
    """Format a repo dict into a compact one-liner for prompts."""
    name = repo.get("full_name", "unknown")
    desc = (repo.get("description") or "(no description)")[:90]
    stars = repo.get("stargazers_count", 0)
    lang = repo.get("language") or "?"
    topics = repo.get("topics", [])[:4]
    topic_str = f"  topics: {', '.join(topics)}" if topics else ""
    return f"- **{name}** ({stars}★, {lang})\n  {desc}{topic_str}"


# ─── Claude API ───────────────────────────────────────────────────────────────


def claude_call(prompt: str, max_tokens: int = 800) -> str:
    if not ANTHROPIC_API_KEY:
        return (
            "⚠️  ANTHROPIC_API_KEY not set.\n"
            "Add it to kegbot-claude/.env or the repo root .env.\n"
            "Run with --raw to see trending repos without Claude."
        )

    payload = json.dumps(
        {
            "model": "claude-opus-4-6",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode("utf-8")

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
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            return result["content"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return f"[Claude API error {e.code}: {body[:200]}]"
    except Exception as e:
        return f"[Claude API error: {e}]"


# ─── Idea storage ─────────────────────────────────────────────────────────────


def load_ideas() -> list[dict]:
    if IDEAS_FILE.exists():
        try:
            return json.loads(IDEAS_FILE.read_text())
        except Exception:
            return []
    return []


def _save_ideas(ideas: list[dict]):
    IDEAS_FILE.write_text(json.dumps(ideas, indent=2))


# ─── Commands ─────────────────────────────────────────────────────────────────


def _parse_days(args: list[str], default: int) -> int:
    if "--days" in args:
        idx = args.index("--days")
        if idx + 1 < len(args):
            try:
                return int(args[idx + 1])
            except ValueError:
                pass
    return default


def _parse_language(args: list[str]) -> str | None:
    if "--language" in args:
        idx = args.index("--language")
        if idx + 1 < len(args):
            return args[idx + 1].lower()
    if "-l" in args:
        idx = args.index("-l")
        if idx + 1 < len(args):
            return args[idx + 1].lower()
    return None


def cmd_trending(args: list[str]):
    """Show what's trending on GitHub in Kevin's stack. No idea generation."""
    days = _parse_days(args, 7)
    lang_filter = _parse_language(args)
    languages = [lang_filter] if lang_filter else KEVIN_LANGUAGES

    print(f"🔭 idea-forge trending — last {days} days\n")

    total = 0
    for lang in languages:
        repos = fetch_trending_repos(lang, days=days, per_page=5)
        if not repos:
            print(f"  {lang}: no results (rate limited or no matches in window)")
            continue

        print(f"── {lang.title()} " + "─" * max(0, 50 - len(lang)))
        for r in repos:
            name = r.get("full_name", "unknown")
            desc = (r.get("description") or "(no description)")[:70]
            stars = r.get("stargazers_count", 0)
            url = r.get("html_url", "")
            print(f"  ★ {stars:>5}  {name}")
            print(f"            {desc}")
            print(f"            {url}")
            print()
            total += 1

    if total == 0:
        print("No trending repos found. GitHub API may be rate-limited.")
        print("Set GITHUB_TOKEN in .env for 5000 req/hr (unauthenticated = 60).")
    else:
        print(f"Found {total} trending repo(s) across {len(languages)} language(s).")
        print(f"\nRun `idea_forge.py forge` to generate project ideas from these.")


def cmd_forge(args: list[str]):
    """The main event: fetch trending repos, generate personalized project ideas."""
    days = _parse_days(args, 14)
    lang_filter = _parse_language(args)
    raw = "--raw" in args
    n_ideas = 3

    languages = [lang_filter] if lang_filter else KEVIN_LANGUAGES

    print(f"⚗️  idea-forge — scanning {days}-day trending repos...\n")

    # Fetch trending repos across Kevin's stack
    all_repos: list[dict] = []
    for lang in languages:
        repos = fetch_trending_repos(lang, days=days, per_page=4)
        if repos:
            print(f"  ✓ {lang}: {len(repos)} repo(s) found")
        else:
            print(f"  ⚠ {lang}: no results")
        all_repos.extend(repos)

    print()

    if not all_repos:
        print("❌ No trending repos found. Check GITHUB_TOKEN for higher rate limits.")
        return

    if raw:
        print("── Trending Repos (raw) " + "─" * 37)
        for r in all_repos:
            print(_repo_summary(r))
            print()
        print("(--raw: skipping Claude idea generation)")
        return

    repo_block = "\n".join(_repo_summary(r) for r in all_repos)
    today = datetime.now().strftime("%B %d, %Y")

    prompt = f"""You are idea-forge, a creative project idea generator. Today is {today}.

## Kevin's Profile
{KEVIN_PROFILE}

## What's Trending on GitHub Right Now
These repos gained the most traction in the last {days} days:

{repo_block}

## Your Task
Generate exactly **{n_ideas} weekend project ideas** specifically for Kevin.

Important rules:
- These must be *inspired by* the trends above — NOT copies of those repos
- Each idea must fit Kevin's vibe: personal tools, dev automation, maps, food/cooking, Discord bots, terminal UIs
- Each idea must be realistically buildable in a weekend (a single developer, 2 days)
- Think: what would Kevin actually want to use himself?
- Be specific. A vague idea is a wasted idea.

For each idea, format exactly as:

### N. <Project Name>
**Pitch:** One punchy sentence — why does this exist?
**Inspired by:** Which trend(s) from above sparked this idea
**Weekend build plan:**
- [ ] Core thing that makes it work (day 1 morning)
- [ ] The thing that makes it useful (day 1 afternoon)
- [ ] The thing that makes it delightful (day 2, optional)
**Stack:** Primary language + key tools/APIs (prefer free/no-key when possible)
**Kevin's twist:** One sentence on what makes this *his* version, not a generic clone

---

Make these genuinely exciting. Kevin reads this when he wakes up on a weekend morning."""

    print("[claude] Forging ideas...\n")
    ideas_text = claude_call(prompt, max_tokens=1400)

    print("═" * 62)
    print(f"  idea-forge  ·  {n_ideas} weekend project ideas  ·  {today}")
    print("═" * 62)
    print()
    print(ideas_text)
    print()
    print("═" * 62)
    print(f"\n💾 Save one: idea_forge.py save \"<project name>\"")
    print(f"📋 See all:  idea_forge.py list")


def cmd_spark(args: list[str]):
    """One quick off-the-cuff idea. No trending analysis. Fast."""
    print("✨ idea-forge spark — one fresh idea, no warm-up required\n")

    today = datetime.now().strftime("%B %d, %Y")

    prompt = f"""You are idea-forge, Kevin's creative project idea generator. Today is {today}.

Kevin's profile:
{KEVIN_PROFILE}

Generate ONE bold, creative weekend project idea for Kevin.
No trending analysis — just a spark. Something he hasn't thought of.
Something with personality.

Format:
### <Project Name>
**Pitch:** One sentence.
**Build plan:**
- [ ] Thing 1 (the core)
- [ ] Thing 2 (what makes it fun)
- [ ] Thing 3 (the bonus)
**Stack:** What to use (prefer free/minimal deps).
**Why Kevin:** One sentence on why this is *for him*, not everyone.

Be bold. A mediocre idea is worse than no idea."""

    result = claude_call(prompt, max_tokens=450)
    print(result)
    print()
    print("💾 Like it? `idea_forge.py save \"<name>\" --desc \"...\"` to save it.")


def cmd_save(args: list[str]):
    """Save an idea to ideas.json."""
    if not args:
        print("Usage: idea_forge.py save \"Project Name\" [--desc \"description\"]")
        sys.exit(1)

    name = args[0]
    description = ""
    if "--desc" in args:
        idx = args.index("--desc")
        if idx + 1 < len(args):
            description = args[idx + 1]

    ideas = load_ideas()
    idea = {
        "name": name,
        "description": description,
        "saved_at": datetime.now().isoformat()[:16],
    }
    ideas.append(idea)
    _save_ideas(ideas)

    print(f"✅ Saved: \"{name}\"")
    if description:
        print(f"   {description}")
    print(f"\n📋 {len(ideas)} saved idea(s) total. `idea_forge.py list` to see all.")


def cmd_list(args: list[str]):
    """List all saved ideas."""
    ideas = load_ideas()

    if not ideas:
        print("📋 No saved ideas yet.")
        print("   Run `idea_forge.py forge` or `spark`, then save the good ones.")
        return

    print(f"💡 idea-forge — {len(ideas)} saved idea(s)\n")
    for i, idea in enumerate(ideas, 1):
        name = idea.get("name", "(unnamed)")
        desc = idea.get("description", "")
        date_str = idea.get("saved_at", "")[:10]
        print(f"  {i:>2}. {name}")
        if desc:
            print(f"      {desc}")
        print(f"      saved {date_str}")
        print()


def cmd_help(_args=None):
    print("""
⚗️  idea-forge — AI weekend project idea generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Watches what's trending on GitHub in Kevin's stack (Python, TypeScript, Go),
then uses Claude to generate personalized weekend project ideas.
Not generic. Not boilerplate. Things you'd actually build and use.

USAGE
    idea_forge.py <command> [options]

COMMANDS

  forge                    3 ideas from trending repos (default)
    --days N               Trending window in days (default: 14)
    --language LANG        Focus on one language: python, typescript, go
    -l LANG                Shorthand for --language
    --raw                  Show repos only — skip Claude

  trending                 Show trending repos without generating ideas
    --days N               Trending window (default: 7)
    --language / -l LANG   Filter by language

  spark                    One quick bold idea — no trending analysis (fast)

  save <name>              Save an idea to ideas.json
    --desc "description"   Add a description

  list                     List all saved ideas

  help                     Show this help

SETUP
  No API key needed for `trending`.
  For idea generation: add ANTHROPIC_API_KEY to kegbot-claude/.env or root .env.
  Optional: GITHUB_TOKEN for 5000 req/hr (default: 60 unauthenticated).

EXAMPLES
    idea_forge.py forge
    idea_forge.py forge --language python
    idea_forge.py forge --days 7 --raw
    idea_forge.py trending --language typescript
    idea_forge.py spark
    idea_forge.py save "Terminal Matcha Timer" --desc "countdown + history"
    idea_forge.py list

Also available as: kegbot ideas [subcommand]

Built by Claude (Cycle 8). Because the best project is the one you actually build.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

COMMANDS = {
    "forge": cmd_forge,
    "trending": cmd_trending,
    "spark": cmd_spark,
    "save": cmd_save,
    "list": cmd_list,
    "help": cmd_help,
    "--help": cmd_help,
    "-h": cmd_help,
}


def main():
    argv = sys.argv[1:]

    if not argv:
        cmd_forge([])  # default: forge ideas
        return

    command = argv[0]
    rest = argv[1:]

    if command not in COMMANDS:
        print(f"❓ Unknown command: {command}")
        print("Run `idea_forge.py help` for available commands.")
        sys.exit(1)

    fn = COMMANDS[command]
    if command in ("help", "--help", "-h"):
        fn()
    else:
        fn(rest)


if __name__ == "__main__":
    main()
