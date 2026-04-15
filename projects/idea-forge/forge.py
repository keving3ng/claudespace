#!/usr/bin/env python3
"""
forge — AI project idea generator powered by GitHub trends + Claude

Watches what's gaining traction on GitHub in Kevin's tech stack, then uses
Claude to synthesize actionable weekend project ideas with rough plans.

Zero dependencies beyond stdlib. Uses GitHub Search API + Anthropic API.

Usage:
    forge trending                      # What's hot in Kevin's stack right now
    forge trending --lang typescript    # Filter to a specific language
    forge trending --days 14            # Trending over last 14 days (default: 7)
    forge ideas                         # Generate 3 AI project ideas from trends
    forge ideas --lang python
    forge ideas --raw                   # See raw trending data (no Claude)
    forge plan "your idea here"         # Full weekend implementation plan
    forge stack                         # Kevin's known stack + project profile
    forge help
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent.parent

# Kevin's primary tech stack — order matters (most relevant first)
KEVIN_STACK = ["typescript", "python", "go"]

# Languages we display labels for
LANG_DISPLAY = {
    "typescript": "TypeScript",
    "python": "Python",
    "go": "Go",
    "javascript": "JavaScript",
    "rust": "Rust",
}

# Kevin's profile for the idea-generation prompt
KEVIN_PROFILE = """
Kevin Geng — full-stack software engineer at Faire (Toronto).
Tech stack: TypeScript, Python, Go. Experienced with React, Node, PostgreSQL, Redis.
Active projects:
  - matchamap.club — opinionated matcha cafe finder (GeoJSON, mapping)
  - claudespace — autonomous Claude AI build lab (this very repo)
  - kegbot — personal assistant CLI powered by Claude
  - discord-bridge — Claude ↔ Discord relay
Side interests: cooking tools, personal automation, terminal dashboards, OSS tooling.
Aesthetic: functional, slightly opinionated, good CLIs, elegant data pipelines.
Not interested in: bloated SaaS, generic CRUD apps, anything requiring mobile dev.
Weekend project style: something that works in <2 days, ideally useful immediately,
preferably zero-dependency or minimal-dependency, built to be personal before general.
"""

# ─── Env ──────────────────────────────────────────────────────────────────────


def load_env():
    for env_path in [
        Path(__file__).parent / ".env",
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

# ─── GitHub Search ─────────────────────────────────────────────────────────────


def _gh_request(url: str) -> dict | None:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "idea-forge/1.0",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 403:
            body = e.read().decode("utf-8", errors="replace")
            if "rate limit" in body.lower():
                print(
                    "⚠️  GitHub rate limit hit. Set GITHUB_TOKEN for 5000 req/hr.",
                    file=sys.stderr,
                )
            else:
                print(f"⚠️  GitHub HTTP 403: {body[:120]}", file=sys.stderr)
        elif e.code == 422:
            # Unprocessable entity — probably bad query params
            body = e.read().decode("utf-8", errors="replace")
            print(f"⚠️  GitHub 422 (bad query): {body[:200]}", file=sys.stderr)
        else:
            print(f"⚠️  GitHub HTTP {e.code}: {url}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"⚠️  Request failed: {e}", file=sys.stderr)
        return None


def fetch_trending(lang: str, days: int = 7, per_page: int = 8) -> list[dict]:
    """
    Fetch recently-created repos in `lang` sorted by stars.
    This is the closest you can get to "trending" via the GitHub Search API.
    """
    since_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    query = f"language:{lang} created:>{since_date} stars:>5"
    encoded = urllib.parse.quote(query)
    url = (
        f"https://api.github.com/search/repositories"
        f"?q={encoded}&sort=stars&order=desc&per_page={per_page}"
    )
    data = _gh_request(url)
    if not data or "items" not in data:
        return []
    return data["items"]


def summarize_repo(repo: dict) -> dict:
    """Extract the key fields we care about."""
    return {
        "name": repo.get("full_name", ""),
        "description": (repo.get("description") or "")[:120],
        "stars": repo.get("stargazers_count", 0),
        "language": repo.get("language") or "Unknown",
        "topics": repo.get("topics", [])[:6],
        "url": repo.get("html_url", ""),
        "created_at": repo.get("created_at", "")[:10],
    }


# ─── Claude ────────────────────────────────────────────────────────────────────


def claude_call(prompt: str, max_tokens: int = 800) -> str:
    if not ANTHROPIC_API_KEY:
        return "⚠️  ANTHROPIC_API_KEY not set. Run with --raw to skip Claude."

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


# ─── Display helpers ───────────────────────────────────────────────────────────


def _print_repo(repo: dict, index: int | None = None):
    prefix = f"  {index}. " if index is not None else "  "
    name = repo["name"]
    stars = repo["stars"]
    lang = repo["language"]
    desc = repo["description"] or "(no description)"
    url = repo["url"]
    topics = " ".join(f"#{t}" for t in repo["topics"][:4]) if repo["topics"] else ""

    star_str = f"★ {stars:,}"
    print(f"{prefix}{name}  [{star_str}  {lang}]")
    print(f"       {desc}")
    if topics:
        print(f"       {topics}")
    print(f"       {url}")
    print()


# ─── Commands ──────────────────────────────────────────────────────────────────


def _parse_lang(args: list[str]) -> str | None:
    """Extract --lang value from args, or None for 'all'."""
    for flag in ("--lang", "-l"):
        if flag in args:
            idx = args.index(flag)
            if idx + 1 < len(args):
                return args[idx + 1].lower()
    return None


def _parse_days(args: list[str], default: int = 7) -> int:
    if "--days" in args:
        idx = args.index("--days")
        if idx + 1 < len(args):
            try:
                return int(args[idx + 1])
            except ValueError:
                pass
    return default


def cmd_trending(args: list[str]):
    """Show trending repos in Kevin's stack (or a specific language)."""
    lang_filter = _parse_lang(args)
    days = _parse_days(args)
    langs = [lang_filter] if lang_filter else KEVIN_STACK

    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%b %d")
    print(f"🔭 forge trending — GitHub stars since {since}\n")

    found_any = False
    for lang in langs:
        display = LANG_DISPLAY.get(lang, lang.capitalize())
        print(f"── {display} " + "─" * max(0, 48 - len(display)))

        repos = fetch_trending(lang, days=days)
        if not repos:
            print(f"  (no results for {display} in the last {days} days)\n")
            continue

        found_any = True
        for i, raw in enumerate(repos[:5], 1):
            repo = summarize_repo(raw)
            _print_repo(repo, i)

    if not found_any:
        print("Could not fetch trending data. Check your network or GITHUB_TOKEN.")
        return

    print(f"Tip: `forge ideas` to let Claude synthesize project ideas from these trends.")


def cmd_ideas(args: list[str]):
    """Generate AI project ideas based on trending repos in Kevin's stack."""
    lang_filter = _parse_lang(args)
    days = _parse_days(args)
    raw_mode = "--raw" in args
    langs = [lang_filter] if lang_filter else KEVIN_STACK

    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%b %d")
    print(f"💡 forge ideas — synthesizing from GitHub trends since {since}\n")

    # Gather trending data
    all_repos: list[dict] = []
    for lang in langs:
        display = LANG_DISPLAY.get(lang, lang.capitalize())
        print(f"[fetch] {display}...", end=" ", flush=True)
        repos = fetch_trending(lang, days=days)
        summarized = [summarize_repo(r) for r in repos[:6]]
        all_repos.extend(summarized)
        print(f"{len(summarized)} repos")

    print()

    if not all_repos:
        print("⚠️  No trending repos found. Check network or try --days 14.")
        return

    if raw_mode:
        print("── Raw trending data ─────────────────────────────────────")
        for r in all_repos:
            print(f"  {r['name']} [{r['language']} ★{r['stars']:,}]")
            print(f"    {r['description']}")
            if r["topics"]:
                print(f"    topics: {', '.join(r['topics'])}")
        return

    # Format for Claude
    repos_text = ""
    for r in all_repos:
        repos_text += f"• {r['name']} ({r['language']}, ★{r['stars']:,})\n"
        repos_text += f"  {r['description']}\n"
        if r["topics"]:
            repos_text += f"  Topics: {', '.join(r['topics'])}\n"
        repos_text += "\n"

    today = datetime.now().strftime("%A, %B %d, %Y")

    prompt = f"""Today is {today}. You are helping a developer find weekend project ideas.

Here is the developer's profile:
{KEVIN_PROFILE}

Here are trending GitHub repos right now (created in the last {days} days, sorted by stars):
{repos_text}

Based on these trends AND the developer's profile, suggest exactly 3 weekend project ideas.

Rules:
- Each idea must be directly inspired by or adjacent to a real trend above (name the repo that inspired it)
- Must fit Kevin's stack (TypeScript, Python, or Go)
- Must be completable in 1–2 weekends (not a startup)
- Should be something Kevin would actually use or find delightful
- Not generic CRUD apps or SaaS clones

Format for each idea:
### Idea N: [Catchy Name]
**Inspired by:** [repo name and what it does]
**The pitch:** [1-2 sentences — what it does and why Kevin specifically would want it]
**Stack:** [tech choices]
**First steps:** [3 bullet points — exactly where to start]
**Weekend scope:** [what "done" looks like after 2 days]

Be opinionated. Pick the three most exciting intersections between the trends and Kevin's profile.
Don't just list features — argue for why this would be worth 2 days of Kevin's weekend.
"""

    print("[claude] Synthesizing ideas (this takes ~10 seconds)...")
    result = claude_call(prompt, max_tokens=1200)

    print("\n" + "═" * 60)
    print(result)
    print("═" * 60)
    print()
    print("Tip: `forge plan \"your idea\"` to get a full weekend blueprint for any of these.")


def cmd_plan(args: list[str]):
    """Generate a full weekend implementation plan for a specific idea."""
    # Everything that's not a flag is the idea description
    idea_parts = [a for a in args if not a.startswith("-")]
    idea = " ".join(idea_parts).strip()

    if not idea:
        print("Usage: forge plan \"your idea description\"")
        print("Example: forge plan \"CLI tool that watches a git repo and auto-summarizes commits\"")
        sys.exit(1)

    print(f"🗺  forge plan — weekend blueprint\n")
    print(f"Idea: {idea}\n")

    today = datetime.now().strftime("%A, %B %d, %Y")

    prompt = f"""Today is {today}. Generate a concrete weekend implementation plan.

Developer profile:
{KEVIN_PROFILE}

The idea: "{idea}"

Generate a complete, actionable weekend plan. Be specific — no hand-waving.

Format:

## Weekend Plan: [give the project a name]

**What it does:** [1 sentence, sharp]

**Why it's worth a weekend:** [2-3 sentences — the actual value proposition, no fluff]

### Tech Stack
[Specific choices with brief rationale. Stick to Kevin's stack unless there's a compelling reason.]

### Project Structure
[File tree — just the key files, not every directory. Max 10 lines.]

### Day 1 — Build the core
[Hour-by-hour breakdown. Be realistic. What can you actually ship in 8 hours?]
- [ ] Morning (3h): [specific milestone]
- [ ] Afternoon (3h): [specific milestone]
- [ ] Evening (2h): [specific milestone]

### Day 2 — Polish and ship
- [ ] Morning (3h): [specific milestone]
- [ ] Afternoon (2h): [specific milestone]
- [ ] Done: [what "shipped" looks like]

### Getting Started (first 3 commands)
```bash
[exact commands to run to start this project]
```

### Stretch goals (if you finish early)
[2-3 ideas, one per line]

### What could go wrong
[The 1-2 most likely blockers and how to avoid them]

Be honest about scope. If this is actually a 3-day project, say so and suggest what to cut.
"""

    print("[claude] Writing your weekend blueprint (~15 seconds)...")
    result = claude_call(prompt, max_tokens=1500)

    print("\n" + "═" * 60)
    print(result)
    print("═" * 60)
    print()


def cmd_stack(args: list[str]):
    """Print Kevin's known stack and project profile."""
    print("🧰 forge stack — Kevin's profile\n")
    print(KEVIN_PROFILE.strip())
    print()
    print("─" * 50)
    print(f"Languages tracked for trending: {', '.join(LANG_DISPLAY.get(l, l) for l in KEVIN_STACK)}")
    print()
    print("Tip: `forge ideas` — generate ideas tailored to this profile")
    print("     `forge ideas --lang python` — filter to one language")


def cmd_help():
    print("""
💡 forge — AI project idea generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Watches what's gaining traction on GitHub in your tech stack,
then uses Claude to synthesize actionable weekend project ideas.

USAGE
    forge <command> [options]

COMMANDS

  trending                   What's hot on GitHub right now (Kevin's stack)
    --lang LANG                Filter to: python, typescript, go, rust, etc.
    --days N                   Trending window (default: 7)

  ideas                      Generate 3 AI project ideas from trends
    --lang LANG                Filter trends to one language
    --days N                   Trending window (default: 7)
    --raw                      Show raw trending data (no Claude, no API key needed)

  plan "your idea"            Full weekend implementation blueprint via Claude
    [idea description]         Describe the idea — wrap in quotes

  stack                       Kevin's profile and tech stack summary

  help                        This message

SETUP
  Needs ANTHROPIC_API_KEY for `ideas` and `plan`.
  Optionally add GITHUB_TOKEN for higher GitHub rate limits (60 → 5000/hr).
  Copy from kegbot/.env.example or set in projects/kegbot-claude/.env.

EXAMPLES
    forge trending
    forge trending --lang go --days 14
    forge ideas
    forge ideas --lang python --days 3
    forge ideas --raw
    forge plan "CLI tool that auto-summarizes git commits with Claude"
    forge plan "matcha cafe quality ranker using Yelp review sentiment"
    forge stack

PHILOSOPHY
  Trending ≠ important. This tool filters GitHub trends through Kevin's profile
  and aesthetic to surface ideas that are actually worth 2 days of a weekend.
  The best project idea is one you'd build for yourself first.

Built by Claude (Cycle 8). Curiosity as a feature.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

COMMANDS = {
    "trending": cmd_trending,
    "ideas": cmd_ideas,
    "plan": cmd_plan,
    "stack": lambda _: cmd_stack([]),
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
        # Maybe it's a plan with no subcommand — "forge some idea text"
        # Allow `forge plan` without the word "plan" only if it looks like prose
        print(f"❓ Unknown command: {command!r}")
        print("Run `forge help` to see available commands.")
        sys.exit(1)

    COMMANDS[command](rest)


if __name__ == "__main__":
    main()
