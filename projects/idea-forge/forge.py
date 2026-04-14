#!/usr/bin/env python3
"""
idea-forge — AI-powered weekend project idea generator for Kevin.

Scans trending GitHub repos in Kevin's tech stack (TypeScript, Python, Java/Kotlin)
and uses Claude to suggest tailored weekend project ideas with rough build plans.

Zero dependencies beyond stdlib. Claude API optional (needed for idea generation).

Usage:
    forge                        # Fetch trending + generate ideas (needs ANTHROPIC_API_KEY)
    forge suggest                # Same as above
    forge trending               # Show trending repos in Kevin's stack (no API key needed)
    forge trending --language typescript
    forge trending --language python
    forge trending --language java
    forge help
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent.parent

# Kevin's tech stack — these are the languages we scan
KEVIN_LANGUAGES = ["typescript", "python", "java"]

KEVIN_PROFILE = """Kevin Geng is a full-stack software engineer at Faire (Toronto).
Stack: TypeScript/React, Python, Java/Kotlin/Spring Boot, AWS.
Active projects: matchamap.club (opinionated matcha cafe finder), kegbot (personal CLI assistant),
claudespace (autonomous Claude AI build lab that writes code while he sleeps).
Interests: personal automation, cooking/recipe tools, Discord bots, maps/geodata, developer
tools, ML/AI, gaming, transit data.
Build style: pragmatic, ships fast, values real utility. Loves tools he'll actually use daily.
Won't build another todo app. Will build a tool that tells him what to eat based on what's in
his fridge."""


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
            print(
                "⚠️  GitHub rate limit hit. Add GITHUB_TOKEN to .env for higher limits.",
                file=sys.stderr,
            )
        elif e.code == 422:
            # Unprocessable entity — often happens when the search query is too fresh
            pass
        else:
            body = e.read().decode("utf-8", errors="replace")
            print(f"[github] HTTP {e.code}: {body[:150]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[github] Request failed: {e}", file=sys.stderr)
        return None


def fetch_trending_repos(language: str, days: int = 14, per_lang: int = 6) -> list[dict]:
    """
    Fetch recently-created repos with high stars in a language.
    'High stars on a new repo' is the best available proxy for 'trending'
    without scraping GitHub's trending page.
    """
    since = (date.today() - timedelta(days=days)).isoformat()
    query = f"language:{language}+created:>{since}+stars:>5"
    url = (
        f"https://api.github.com/search/repositories"
        f"?q={query}&sort=stars&order=desc&per_page={per_lang}"
    )

    data = _github_request(url)
    if not data or not isinstance(data, dict):
        return []

    return [
        {
            "name": r["name"],
            "full_name": r["full_name"],
            "description": (r.get("description") or "")[:120],
            "stars": r.get("stargazers_count", 0),
            "language": r.get("language") or language.title(),
            "url": r.get("html_url", ""),
            "topics": r.get("topics", [])[:6],
        }
        for r in data.get("items", [])
        if not r.get("fork", False)  # skip forks — they inflate results
    ]


def _fetch_all_trending(languages: list[str]) -> list[dict]:
    """Fetch trending repos across all specified languages."""
    all_repos = []
    for lang in languages:
        repos = fetch_trending_repos(lang, days=14, per_lang=5)
        all_repos.extend(repos)
    return all_repos


# ─── Formatting ───────────────────────────────────────────────────────────────


def _print_repos(repos: list[dict], languages: list[str]):
    """Pretty-print a list of repos grouped by language."""
    # Group by language
    by_lang: dict[str, list[dict]] = {}
    for r in repos:
        lang = r["language"]
        by_lang.setdefault(lang, []).append(r)

    # Print in the order of languages requested
    for lang in languages:
        lang_title = lang.title()
        group = by_lang.get(lang_title, by_lang.get(lang, []))
        if not group:
            print(f"── {lang_title} — no results (API limit or no new repos?)")
            print()
            continue

        print(f"── {lang_title} " + "─" * max(0, 50 - len(lang_title)))
        for r in group:
            stars = f"★ {r['stars']:,}"
            desc = r["description"] or "(no description)"
            topics = f"  [{', '.join(r['topics'])}]" if r["topics"] else ""
            print(f"  {r['full_name']:<38} {stars}")
            print(f"    {desc[:72]}")
            if topics:
                print(f"    {topics}")
            print()


def _format_repos_for_claude(repos: list[dict]) -> str:
    """Compact text representation of repos for the Claude prompt."""
    lines = []
    for r in repos:
        topics = ", ".join(r["topics"]) if r["topics"] else "—"
        lines.append(
            f"• [{r['language']}] {r['full_name']} (★{r['stars']:,})\n"
            f"  {r['description'] or 'No description'}\n"
            f"  topics: {topics}"
        )
    return "\n\n".join(lines)


# ─── Claude idea generation ───────────────────────────────────────────────────


def generate_ideas(repos: list[dict]) -> str:
    """Send trending repos + Kevin's profile to Claude; get project ideas back."""
    if not repos:
        return "No trending repos to analyze — try again or add GITHUB_TOKEN to raise rate limits."

    repos_text = _format_repos_for_claude(repos)
    today = date.today().strftime("%B %d, %Y")

    prompt = f"""You are idea-forge, an AI weekend project idea generator. Today is {today}.

## Kevin's Profile
{KEVIN_PROFILE}

## Trending on GitHub Right Now (repos created in the last 14 days with high stars)
{repos_text[:3500]}

---

Your task: Suggest **4 weekend project ideas** for Kevin, each inspired by or connected to
the trending repos above.

Requirements for each idea:
- **Buildable in 1–2 days** by a solo developer (not a startup, not a 3-month project)
- **Connected to Kevin's world** — reference his actual interests, stack, or current projects
  where possible (matchamap, kegbot, cooking, Discord, automation, maps, ML)
- **Specific and actionable** — someone should be able to start building tonight
- **Not something Kevin is already building** (matchamap and kegbot are taken)
- Each idea should feel different from the others — range across his interests

Format:
**[Project Name]** — *one-line tagline*
*Why it fits Kevin:* one sentence on the fit
*3-step build plan:*
  1. (first concrete step)
  2. (second concrete step)
  3. (third concrete step)

Separate each idea with a blank line. Be specific. Be opinionated about the stack.
Make Kevin want to start building tonight.
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

    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            result = json.loads(resp.read())
            return result["content"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return f"[Claude API error {e.code}: {body[:200]}]"
    except Exception as e:
        return f"[Claude API error: {e}]"


# ─── Commands ─────────────────────────────────────────────────────────────────


def cmd_trending(args: list[str]):
    """Display trending repos in Kevin's stack. No API key needed."""
    languages = _parse_language_flag(args, KEVIN_LANGUAGES)

    print("🔭 idea-forge — Trending in Kevin's stack\n")
    print(f"   Scanning GitHub for hot repos created in the last 14 days...\n")

    repos = _fetch_all_trending(languages)

    if not repos:
        print("⚠️  No results. GitHub search API may be rate-limited.")
        print("   Add GITHUB_TOKEN to .env for 5000 req/hr instead of 10/min.")
        return

    _print_repos(repos, languages)
    print(f"   Total: {len(repos)} trending repo(s) across {len(languages)} language(s)")
    print()
    print("   Run `forge` (or `forge suggest`) to get AI-powered project ideas from this data.")


def cmd_suggest(args: list[str]):
    """Fetch trending repos + generate tailored project ideas via Claude."""
    languages = _parse_language_flag(args, KEVIN_LANGUAGES)

    print("⚡ idea-forge — Weekend project ideas, powered by what's hot on GitHub\n")

    # Step 1: Fetch trending
    print(f"🔭 Fetching trending repos in: {', '.join(languages)}...")
    all_repos = _fetch_all_trending(languages)

    if not all_repos:
        print("\n⚠️  Could not fetch trending data. Check network or add GITHUB_TOKEN to .env.")
        print("   Try: forge trending")
        return

    lang_counts = {}
    for r in all_repos:
        lang = r["language"]
        lang_counts[lang] = lang_counts.get(lang, 0) + 1

    for lang, count in lang_counts.items():
        print(f"   {lang}: {count} repo(s)")

    print(f"\n   Total: {len(all_repos)} trending repos\n")

    # Step 2: Generate ideas (or show raw if no API key)
    if not ANTHROPIC_API_KEY:
        print("⚠️  ANTHROPIC_API_KEY not set — showing raw trending data.")
        print("   Add your API key to .env (kegbot or repo root) for idea generation.\n")
        _print_repos(all_repos, languages)
        return

    print("🧠 Asking Claude to generate ideas tailored to Kevin's profile...\n")
    ideas = generate_ideas(all_repos)

    print("═" * 62)
    print("✨  WEEKEND PROJECT IDEAS  ✨")
    print("═" * 62)
    print()
    print(ideas)
    print()
    print("═" * 62)
    print()
    print("Inspired by trending GitHub repos (last 14 days).")
    print("Run `forge trending` to see the source data.")
    print("Run `forge` again next week for fresh inspiration.")


def cmd_help():
    print("""
💡 idea-forge — AI weekend project idea generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USAGE
    forge <command> [options]
    forge                          # Default: trending + Claude-powered ideas

COMMANDS

  suggest                         Trending repos → tailored project ideas (default)
    --language LANG               Limit to one language: typescript, python, java

  trending                        Show trending repos (no API key needed)
    --language LANG               Filter to one language

  help                            This help text

HOW IT WORKS
    1. Fetches recently-created GitHub repos with high stars in Kevin's stack
       (TypeScript, Python, Java) — a reliable proxy for "trending"
    2. Feeds the list to Claude with Kevin's profile and current projects
    3. Claude returns 4 tailored weekend project ideas with rough build plans

SETUP
    No setup needed for `forge trending`.
    For idea generation: add ANTHROPIC_API_KEY to:
        projects/kegbot-claude/.env  (if you have kegbot set up)
        .env  (repo root)
    Optional: add GITHUB_TOKEN for higher rate limits (10/min → 30/min search).

EXAMPLES
    forge
    forge trending
    forge trending --language python
    forge suggest --language typescript

Built by Claude (Cycle 8). It makes its own to-do list. This is that list.
""")


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _parse_language_flag(args: list[str], default: list[str]) -> list[str]:
    """Extract --language/-l flag value, or return default."""
    for flag in ("--language", "-l"):
        if flag in args:
            idx = args.index(flag)
            if idx + 1 < len(args):
                return [args[idx + 1].lower()]
    return default


# ─── Main ─────────────────────────────────────────────────────────────────────

COMMANDS = {
    "suggest": cmd_suggest,
    "trending": cmd_trending,
    "help": cmd_help,
    "--help": cmd_help,
    "-h": cmd_help,
}


def main():
    argv = sys.argv[1:]

    if not argv:
        cmd_suggest([])
        return

    command = argv[0]
    rest = argv[1:]

    if command not in COMMANDS:
        print(f"❓ Unknown command: {command}")
        print("Run `forge help` for available commands.")
        sys.exit(1)

    fn = COMMANDS[command]
    # help commands don't take args
    if command in ("help", "--help", "-h"):
        fn()
    else:
        fn(rest)


if __name__ == "__main__":
    main()
