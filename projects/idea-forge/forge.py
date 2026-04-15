#!/usr/bin/env python3
"""
forge — AI-powered project idea generator

Watches what's trending across Kevin's tech stack and uses Claude to
suggest weekend project ideas tailored specifically to him. The machine
that suggests what the machine should build next.

Usage:
    forge trending                     # Trending repos in Kevin's full stack
    forge trending --lang python       # One language only
    forge suggest                      # 3 Claude-generated project ideas
    forge suggest --lang typescript    # Focus on one language's trends
    forge repos                        # Kevin's own repos by recent activity
    forge repos --username <user>      # Another GitHub user
    forge help
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent.parent

# Kevin's stack from docs/ABOUT_KEVIN.md
KEVIN_STACK = ["python", "typescript", "go", "java"]

# Look back this many days for "recently active" trending repos
TRENDING_SINCE_DAYS = 90

KEVIN_PROFILE = """Kevin Geng — full-stack software engineer at Faire in Toronto.
Stack: React, TypeScript, Java/Kotlin/Spring Boot, Python, AWS.
Active projects:
  - matchamap.club: opinionated matcha cafe finder (Python data pipeline, Mapbox UI)
  - claudespace: autonomous Claude AI build lab (this is where we live)
  - kegbot: personal CLI assistant powered by Claude (briefings, PR digest, weather)
  - cookbook: cooking recipes + recipe-ai (ingredient-based suggestions, meal planning)
Interests: ML/AI, Discord bots, personal automation, cooking tools, maps/place data,
gaming, transit hacking. He likes "fun + useful" — not enterprise software."""

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
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "keving3ng")


# ─── GitHub API ───────────────────────────────────────────────────────────────


def _gh_request(url: str) -> dict | list | None:
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
        body = e.read().decode("utf-8", errors="replace")
        if e.code == 403 and "rate limit" in body.lower():
            print(
                "⚠️  GitHub rate limit hit. Add GITHUB_TOKEN to .env for higher headroom.",
                file=sys.stderr,
            )
        elif e.code == 422:
            # Search API validation error — ignore silently for bad language names
            pass
        else:
            print(f"⚠️  GitHub API error {e.code}: {body[:200]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"⚠️  Request failed: {e}", file=sys.stderr)
        return None


def fetch_trending_repos(language: str, n: int = 5) -> list[dict]:
    """
    Fetch top-starred repos for a language, active in the last N days.
    Uses GitHub Search API — no auth needed (10 req/min unauthenticated).
    """
    since = (date.today() - timedelta(days=TRENDING_SINCE_DAYS)).isoformat()
    # URL-encode the query manually to avoid spaces
    query = f"language:{language}+pushed:>{since}"
    url = (
        f"https://api.github.com/search/repositories"
        f"?q={query}&sort=stars&order=desc&per_page={n}"
    )
    result = _gh_request(url)
    if not result or "items" not in result:
        return []
    return result["items"]


def fetch_user_repos(username: str) -> list[dict]:
    """Fetch user's public repos sorted by last push."""
    url = (
        f"https://api.github.com/users/{username}/repos"
        f"?sort=pushed&per_page=30&type=owner"
    )
    result = _gh_request(url)
    return result if isinstance(result, list) else []


# ─── Formatting helpers ───────────────────────────────────────────────────────


def _stars(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def _short_desc(desc: str | None, maxlen: int = 70) -> str:
    if not desc:
        return "(no description)"
    return desc if len(desc) <= maxlen else desc[:maxlen - 1] + "…"


def _lang_badge(lang: str) -> str:
    badges = {
        "python": "🐍",
        "typescript": "🔷",
        "go": "🐹",
        "java": "☕",
        "javascript": "🟨",
        "rust": "🦀",
        "kotlin": "🟣",
    }
    return badges.get(lang.lower(), "  ")


def _age_str(pushed_at: str, now: datetime) -> str:
    if not pushed_at:
        return "?"
    try:
        dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
        days = (now - dt).days
        if days == 0:
            return "today"
        if days == 1:
            return "yesterday"
        return f"{days}d ago"
    except Exception:
        return pushed_at[:10]


# ─── Arg parsing ──────────────────────────────────────────────────────────────


def _parse_langs(args: list[str]) -> list[str]:
    """Return list of languages from --lang/-l flag, or Kevin's full stack."""
    for flag in ("--lang", "-l"):
        if flag in args:
            idx = args.index(flag)
            if idx + 1 < len(args):
                return [args[idx + 1].lower()]
    return KEVIN_STACK


def _parse_username(args: list[str]) -> str:
    for flag in ("--username", "-u"):
        if flag in args:
            idx = args.index(flag)
            if idx + 1 < len(args):
                return args[idx + 1]
    return GITHUB_USERNAME


# ─── Commands ─────────────────────────────────────────────────────────────────


def cmd_trending(args: list[str]):
    """Show trending repos per language in Kevin's stack."""
    langs = _parse_langs(args)
    top_n = 5

    print(
        f"🔥 forge trending — hot repos in your stack  (last {TRENDING_SINCE_DAYS} days)\n"
    )

    found_any = False
    for lang in langs:
        badge = _lang_badge(lang)
        print(f"{badge} {lang.title()}")
        repos = fetch_trending_repos(lang, n=top_n)
        if not repos:
            print("   (no results — rate limit or unknown language)\n")
            continue
        found_any = True
        for repo in repos:
            name = repo.get("full_name", "?")
            desc = _short_desc(repo.get("description"))
            stars = _stars(repo.get("stargazers_count", 0))
            topics = repo.get("topics", [])
            topic_str = "  [" + ", ".join(topics[:4]) + "]" if topics else ""
            print(f"   ★ {stars:>6}  {name}")
            print(f"            {desc}{topic_str}")
        print()

    if found_any:
        print(
            "Tip: Run `forge suggest` to get Claude's take on what to build inspired by these.\n"
        )


def cmd_repos(args: list[str]):
    """Show a GitHub user's repos sorted by recent push activity."""
    username = _parse_username(args)

    print(f"📦 forge repos — @{username}'s repos by recent activity\n")

    repos = fetch_user_repos(username)
    if not repos:
        print("Could not fetch repos. Check network or add GITHUB_TOKEN.")
        return

    now = datetime.now(timezone.utc)

    print(f"  {'Repo':<32}  {'Language':<14}  Pushed")
    print("  " + "─" * 60)

    for repo in repos[:20]:
        name = repo.get("name", "?")
        lang = (repo.get("language") or "—")
        pushed = repo.get("pushed_at", "")
        age = _age_str(pushed, now)
        private = " 🔒" if repo.get("private") else ""
        archived = " [archived]" if repo.get("archived") else ""
        print(f"  {name:<32}  {lang:<14}  {age}{private}{archived}")

    print()
    if len(repos) >= 30:
        print(f"  (showing top 20 of 30+ repos)\n")


def cmd_suggest(args: list[str]):
    """Ask Claude to generate weekend project ideas based on trending repos."""
    langs = _parse_langs(args)
    top_n = 5

    print("💡 forge suggest — AI project ideas for your weekend\n")

    if not ANTHROPIC_API_KEY:
        print("⚠️  ANTHROPIC_API_KEY not set.")
        print("   Add it to projects/kegbot-claude/.env to use this command.")
        print("\n   In the meantime, run `forge trending` to browse what's hot.")
        return

    # Fetch trending repos across Kevin's languages
    print(f"Fetching trends across {len(langs)} language(s)...", end="", flush=True)
    trending_lines: list[str] = []
    for lang in langs:
        repos = fetch_trending_repos(lang, n=top_n)
        if repos:
            for r in repos[:3]:  # Top 3 per language — enough signal, not noise
                name = r.get("full_name", "")
                desc = _short_desc(r.get("description"), 80)
                stars = r.get("stargazers_count", 0)
                topics = r.get("topics", [])
                topic_str = " [" + ", ".join(topics[:5]) + "]" if topics else ""
                trending_lines.append(
                    f"  [{lang}] {name} ★{_stars(stars)} — {desc}{topic_str}"
                )
    print(f" found {len(trending_lines)} repos.")

    if not trending_lines:
        print(
            "\n⚠️  Could not fetch any trending repos. "
            "Check network or run `forge trending` to debug."
        )
        return

    trending_block = "\n".join(trending_lines)
    today = datetime.now().strftime("%A, %B %d, %Y")

    prompt = f"""Today is {today}.

{KEVIN_PROFILE}

Here are currently trending GitHub repos in Kevin's stack:
{trending_block}

Based on these trends and Kevin's specific profile, suggest exactly **3 weekend project ideas**.

For each idea, provide:
1. **Name** — short and catchy (2-3 words)
2. **Tagline** — one punchy sentence (what it does + why it's cool)
3. **Stack** — concrete languages/tools/APIs
4. **Plan** — 4-5 bullet points: rough implementation steps, v1 completable in a weekend
5. **Kevin angle** — one sentence on why Kevin specifically would love building this
   (reference his actual projects, interests, or personality where possible)

Guidelines:
- Ideas should be inspired by but NOT copies of the trending repos
- At least one idea should be surprising — something Kevin wouldn't have thought to build
- At least one should connect to an existing Kevin project (matchamap, kegbot, cookbook, etc.)
- Keep all ideas realistic for a weekend — a satisfying v1, not a roadmap
- Be specific about tech choices (not just "use an API" — which one?)
- No enterprise tools. No dashboards for the sake of dashboards. Delight counts.

Format: Use clear headers for each idea. Be concrete. Bias toward fun.
"""

    payload = json.dumps({
        "model": "claude-opus-4-6",
        "max_tokens": 1400,
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

    print("[claude] Thinking about what you should build...\n")

    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            result = json.loads(resp.read())
            ideas = result["content"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[claude] API error {e.code}: {body[:200]}", file=sys.stderr)
        return
    except Exception as e:
        print(f"[claude] Error: {e}", file=sys.stderr)
        return

    print("─" * 64)
    print(ideas)
    print("─" * 64)
    print(
        f"\nGenerated using {len(trending_lines)} trending repos as inspiration.\n"
        "Run `forge trending` to explore the source material.\n"
    )


def cmd_help():
    print("""
💡 forge — AI-powered project idea generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USAGE
    forge <command> [options]

COMMANDS

  trending                   Trending repos in Kevin's stack (Python, TS, Go, Java)
  trending --lang python     Filter to a single language

  suggest                    Claude generates 3 tailored weekend project ideas
  suggest --lang typescript  Focus ideas on one language's trends

  repos                      Your GitHub repos sorted by recent push activity
  repos --username <user>    Check another GitHub user's repos

  help                       This help text

OPTIONS
  --lang <language>          Language filter (any GitHub language name)
  -l <language>              Shorthand for --lang
  --username <user>          GitHub username override
  -u <user>                  Shorthand for --username

SETUP
  No API key needed for `trending` and `repos`.
  Add ANTHROPIC_API_KEY to projects/kegbot-claude/.env for `suggest`.
  Add GITHUB_TOKEN for higher rate limits (60 → 5000 req/hr).

EXAMPLES
    forge trending
    forge trending --lang go
    forge suggest
    forge suggest --lang typescript
    forge repos
    forge repos --username torvalds

Built by Claude (Cycle 8). The machine that suggests what the machine should build.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

COMMANDS = {
    "trending": cmd_trending,
    "suggest": cmd_suggest,
    "repos": cmd_repos,
    "help": lambda _: cmd_help(),
    "--help": lambda _: cmd_help(),
    "-h": lambda _: cmd_help(),
}


def main():
    argv = sys.argv[1:]

    if not argv:
        cmd_trending([])  # default: show trending
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
