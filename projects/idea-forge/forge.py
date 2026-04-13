#!/usr/bin/env python3
"""
forge — AI-powered project idea generator

Watches trending GitHub repos in Kevin's tech stack, then uses Claude to
suggest weekend project ideas tailored to who he is and what he's building.

Usage:
    forge trending                     # Trending repos in your stack (7d)
    forge trending --days=30           # Look back 30 days
    forge trending --lang=go,rust      # Filter by specific languages
    forge ideas                        # 5 weekend project ideas from trends
    forge ideas --domain=ai            # Focus on a specific domain
    forge plan "your idea here"        # Concrete implementation plan
    forge help
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

HERE = Path(__file__).parent
CACHE_FILE = HERE / ".trending_cache.json"
CACHE_TTL_HOURS = 6  # Don't hammer the GitHub search API

# Kevin's tech stack and interests — used for both API filtering and prompting
KEVIN_STACK = ["python", "typescript", "javascript", "go"]
KEVIN_PROFILE = """
- Full-stack engineer at Faire in Toronto
- Stack: React, TypeScript, Python, Java/Kotlin, AWS
- Interests: personal automation, matcha maps (matchamap.club), cooking tools,
  Discord bots, ML/AI, CLI tools, transit/maps, finance data
- Active projects: matchamap.club (cafe finder), kegbot (personal assistant CLI),
  recipe-ai (cooking CLI), dev-insights (GitHub activity dashboard)
- Builder mindset: ships pragmatic, often zero-dependency tools.
  Loves things that are both fun AND useful.
- Weekend project budget: ~4–8 hours.
  Prefers Python for CLI, TypeScript for web.
""".strip()


# ─── Env loading ──────────────────────────────────────────────────────────────


def load_env():
    """Load .env files from forge dir, kegbot dir, or repo root."""
    candidates = [
        HERE / ".env",
        HERE.parent / "kegbot-claude" / ".env",
        HERE.parent.parent / ".env",
    ]
    for path in candidates:
        if path.exists():
            for line in path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ─── GitHub API ───────────────────────────────────────────────────────────────


def _github_request(url: str) -> dict | None:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "idea-forge/1.0 (keving3ng)",
    }
    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"token {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 403:
            print(
                "⚠️  GitHub rate limit hit. Set GITHUB_TOKEN in .env for "
                "higher limits (60 → 5000 req/hr).",
                file=sys.stderr,
            )
        elif e.code != 404:
            print(f"⚠️  GitHub API error {e.code}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"⚠️  Request failed: {e}", file=sys.stderr)
        return None


def _fetch_trending_for_language(language: str, days: int) -> list[dict]:
    """Fetch recently-created repos for a language, sorted by stars."""
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    query = f"language:{language} created:>{since} stars:>5"
    params = urllib.parse.urlencode({
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": 8,
    })
    data = _github_request(f"https://api.github.com/search/repositories?{params}")
    return (data or {}).get("items", [])


# ─── Cache ────────────────────────────────────────────────────────────────────


def _load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            cache = json.loads(CACHE_FILE.read_text())
            ts = datetime.fromisoformat(cache.get("timestamp", "2000-01-01"))
            if ts > datetime.utcnow() - timedelta(hours=CACHE_TTL_HOURS):
                return cache
        except Exception:
            pass
    return {"timestamp": "2000-01-01", "buckets": {}}


def _save_cache(cache: dict):
    cache["timestamp"] = datetime.utcnow().isoformat()
    try:
        CACHE_FILE.write_text(json.dumps(cache, indent=2))
    except Exception:
        pass  # cache is optional


def get_trending(
    languages: list[str] | None = None,
    days: int = 7,
    force: bool = False,
) -> list[dict]:
    """Return deduplicated, star-sorted trending repos across given languages."""
    if languages is None:
        languages = KEVIN_STACK

    cache = {} if force else _load_cache()
    bucket_key = f"{'_'.join(sorted(languages))}_d{days}"

    if not force and bucket_key in cache.get("buckets", {}):
        return cache["buckets"][bucket_key]

    seen: set[int] = set()
    all_repos: list[dict] = []

    for lang in languages:
        for item in _fetch_trending_for_language(lang, days):
            rid = item.get("id")
            if rid and rid not in seen:
                seen.add(rid)
                all_repos.append({
                    "name": item["full_name"],
                    "description": (item.get("description") or "")[:110],
                    "stars": item.get("stargazers_count", 0),
                    "language": item.get("language") or lang,
                    "topics": (item.get("topics") or [])[:5],
                    "url": item.get("html_url", ""),
                    "created": (item.get("created_at") or "")[:10],
                })

    all_repos.sort(key=lambda r: r["stars"], reverse=True)

    cache.setdefault("buckets", {})[bucket_key] = all_repos
    _save_cache(cache)
    return all_repos


# ─── Claude API ───────────────────────────────────────────────────────────────


def _claude_call(prompt: str, max_tokens: int = 1500) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return "[ANTHROPIC_API_KEY not set — add it to projects/idea-forge/.env]"

    payload = json.dumps({
        "model": "claude-opus-4-6",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            result = json.loads(resp.read())
            return result["content"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return f"[Claude API error {e.code}: {body[:200]}]"
    except Exception as e:
        return f"[Claude API error: {e}]"


# ─── Commands ─────────────────────────────────────────────────────────────────


def cmd_trending(args: list[str]):
    """Show trending repos in Kevin's stack."""
    days = 7
    langs = list(KEVIN_STACK)

    for a in args:
        if a.startswith("--days="):
            try:
                days = int(a.split("=", 1)[1])
            except ValueError:
                pass
        elif a.startswith("--lang="):
            langs = [l.strip() for l in a.split("=", 1)[1].split(",") if l.strip()]

    print(f"\n📈  Trending GitHub repos — last {days}d")
    print(f"    Languages: {', '.join(langs)}\n")

    repos = get_trending(langs, days)

    if not repos:
        print("  No results (GitHub API may be rate-limited today)")
        print("  Tip: Set GITHUB_TOKEN in .env for 5000 req/hr instead of 60\n")
        return

    for i, r in enumerate(repos[:15], 1):
        lang_tag = f"[{r['language']}]" if r["language"] else ""
        topics_str = "  ·  " + ", ".join(r["topics"][:3]) if r["topics"] else ""

        print(f"  {i:>2}.  {r['name']}  {lang_tag}")
        if r["description"]:
            print(f"        {r['description']}")
        print(f"        ⭐ {r['stars']:,}{topics_str}  ·  created {r['created']}")
        print()

    print(f"  → Run `forge ideas` to generate project ideas from these trends.\n")


def cmd_ideas(args: list[str]):
    """Use Claude to generate weekend project ideas based on trending repos."""
    days = 7
    domain = ""

    for a in args:
        if a.startswith("--days="):
            try:
                days = int(a.split("=", 1)[1])
            except ValueError:
                pass
        elif a.startswith("--domain="):
            domain = a.split("=", 1)[1].strip()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not set.")
        print("Add it to projects/idea-forge/.env and try again.")
        sys.exit(1)

    print(f"\n💡  Fetching trends + asking Claude for ideas...\n")

    repos = get_trending(days=days)[:20]

    if repos:
        repos_text = "\n".join(
            f"- {r['name']}: {r['description']} (⭐{r['stars']:,}, {r['language']})"
            for r in repos
        )
    else:
        repos_text = "(GitHub trending unavailable — inventing ideas from first principles)"

    domain_line = f"\nFocus your ideas specifically on the '{domain}' domain." if domain else ""

    prompt = f"""You are an AI assistant helping Kevin Geng find his next weekend project.

Kevin's profile:
{KEVIN_PROFILE}
{domain_line}

Trending GitHub repos this week in Kevin's stack:
{repos_text}

Suggest **5 weekend project ideas** inspired by these trends but tailored to Kevin specifically.

For each idea format exactly like this:

### N. ProjectName
**What it does:** one sentence, plain language
**Why it fits Kevin:** one specific reason — not generic, connect to his actual life/projects
**Stack:** 2–3 bullet points
**Effort:** X–Y hours

Be opinionated. If something on the trending list directly translates into a Kevin-sized project, say so.
Skip anything he's already building. Make them feel achievable, not enterprise.
"""

    result = _claude_call(prompt, max_tokens=1600)
    print(result)
    print()


def cmd_plan(args: list[str]):
    """Generate a concrete weekend implementation plan for an idea."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    idea_parts = [a for a in args if not a.startswith("--")]
    if not idea_parts:
        print("Usage: forge plan \"describe your project idea here\"")
        print("Example: forge plan \"a CLI tool that watches my GitHub stars\"")
        sys.exit(1)

    idea = " ".join(idea_parts)
    title = idea if len(idea) <= 60 else idea[:57] + "..."

    print(f"\n🗺️   Implementation plan: {title}\n")

    prompt = f"""Kevin Geng wants to build a weekend project. Create a concrete implementation plan.

Kevin's context:
{KEVIN_PROFILE}

**Project idea:** {idea}

Write a focused implementation plan using exactly this format:

## Scope
[1–2 sentences. Scope it ruthlessly to a weekend. If the idea is too big, cut it down and say so.]

## Tech Stack
- [choice + 1-line rationale]
- [choice + 1-line rationale]
- [choice + 1-line rationale]

## Build Order
1. [step — ~30–60 min each, ordered by dependency]
2. ...
(6–9 steps total)

## Done Means Done ✓
- [what v1 delivers — 3–4 concrete checkboxes]

## Stretch Goals (if there's time)
- [1–2 bonus things]

Be direct. If there's a smarter approach to scope or stack, say so.
"""

    result = _claude_call(prompt, max_tokens=1200)
    print(result)
    print()


# ─── Help ─────────────────────────────────────────────────────────────────────

HELP = """
forge — AI-powered project idea generator

USAGE
    forge <command> [options]

COMMANDS

  trending                   Show trending GitHub repos in Kevin's stack (7d)
    --days=N                 Look back N days (default: 7)
    --lang=py,ts,go          Comma-separated language list

  ideas                      Generate 5 weekend project ideas from trending repos
    --days=N                 Trending window (default: 7d)
    --domain=NAME            Focus on a domain (ai, cli, web, ml, discord, etc.)

  plan "your idea here"      Get a concrete implementation plan for a project idea

  help                       Show this message

SETUP
    cp projects/idea-forge/.env.example projects/idea-forge/.env
    # Fill in ANTHROPIC_API_KEY (required for ideas + plan)
    # Optionally add GITHUB_TOKEN (raises rate limit 60 → 5000 req/hr)

EXAMPLES
    forge trending
    forge trending --days=30 --lang=python,typescript
    forge ideas
    forge ideas --domain=cli-tools
    forge ideas --domain=ai --days=14
    forge plan "a GitHub stars tracker that pings Discord when a repo hits milestones"
    forge plan "a terminal pomodoro timer that logs sessions to a JSON file"

CACHING
    Trending results are cached for 6 hours in .trending_cache.json.
    Delete that file or set GITHUB_TOKEN to refresh.

Built by Claude (Cycle 8). Turning trending repos into your next obsession.
"""


# ─── Main ─────────────────────────────────────────────────────────────────────


def main():
    load_env()
    argv = sys.argv[1:]

    if not argv or argv[0] in ("help", "--help", "-h"):
        print(HELP)
        return

    cmd = argv[0]
    rest = argv[1:]

    dispatch = {
        "trending": cmd_trending,
        "ideas": cmd_ideas,
        "plan": cmd_plan,
    }

    if cmd not in dispatch:
        print(f"Unknown command: {cmd}")
        print("Run `forge help` for available commands.")
        sys.exit(1)

    dispatch[cmd](rest)


if __name__ == "__main__":
    main()
