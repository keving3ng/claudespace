#!/usr/bin/env python3
"""
forge — AI-powered weekend project idea generator

Watches what's trending in Kevin's tech stack. Synthesizes it with his profile.
Returns 3 concrete, scoped weekend project ideas with rough implementation plans.

Zero dependencies beyond stdlib. Claude API for ideas (has --raw mode without it).

Usage:
    forge ideas                      # 3 AI project ideas based on what's trending
    forge ideas --stack python       # Python-focused ideas
    forge ideas --stack typescript   # TypeScript-focused ideas
    forge ideas --save               # Save ideas to ideas.json
    forge trending                   # Show what's hot in your stack right now
    forge trending --stack python    # Single-language trending
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
IDEAS_FILE = Path(__file__).parent / "ideas.json"

# Kevin's stack — languages we watch for trending repos
DEFAULT_STACKS = ["python", "typescript"]
STACK_ALIASES = {
    "ts": "typescript",
    "js": "javascript",
    "py": "python",
    "go": "go",
}

# Kevin's profile — baked in for Claude context
KEVIN_PROFILE = """
Kevin Geng is a full-stack software engineer at Faire (Toronto).
Active stack: React, TypeScript, Java/Kotlin/Spring Boot, Python, AWS.
Active projects:
  - matchamap.club — an opinionated matcha cafe map (Place data, GeoJSON, Leaflet)
  - kegbot — personal assistant CLI (Python, Claude API, Discord integration)
  - claudespace — autonomous AI build lab (this workspace)
Interests: cooking tools, personal automation, Discord bots, maps & place data,
           ML/AI (has ML background), terminal UIs, gaming, learning projects.
He prefers tools that are "fun + useful" — personality over boilerplate.
Weekend projects should be completable solo in 1-2 days.
He has a cookbook repo and is into food/recipes.
He likes things that delight him — easter eggs, unexpected angles, clean CLIs.
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


# ─── GitHub search ────────────────────────────────────────────────────────────


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
            print("⚠️  GitHub rate limit hit. Set GITHUB_TOKEN in .env for 5000 req/hr.", file=sys.stderr)
        elif e.code != 404:
            body = e.read().decode("utf-8", errors="replace")
            print(f"⚠️  GitHub API {e.code}: {body[:150]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"⚠️  Request failed: {e}", file=sys.stderr)
        return None


def fetch_trending(language: str, days: int = 7, per_page: int = 8) -> list[dict]:
    """
    Fetch trending repos for a language — new repos created in the last `days`
    days, sorted by star count. These are repos that blew up quickly.
    """
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    lang_encoded = urllib.request.pathname2url(language) if hasattr(urllib.request, 'pathname2url') else language.replace(" ", "+")

    url = (
        f"https://api.github.com/search/repositories"
        f"?q=language:{language}+created:%3E{cutoff}"
        f"&sort=stars&order=desc&per_page={per_page}"
    )

    data = _github_request(url)
    if not data or not isinstance(data, dict):
        return []

    items = data.get("items", [])
    results = []
    for repo in items:
        results.append({
            "name": repo.get("full_name", ""),
            "description": (repo.get("description") or "")[:120],
            "stars": repo.get("stargazers_count", 0),
            "url": repo.get("html_url", ""),
            "topics": repo.get("topics", [])[:5],
            "language": repo.get("language") or language,
            "created_at": repo.get("created_at", "")[:10],
        })

    return results


def fetch_hot_repos(language: str, per_page: int = 5) -> list[dict]:
    """
    Fetch recently-active repos with significant stars (established but buzzing).
    Complements the new-repo trending data with mature-but-active repos.
    """
    cutoff = (date.today() - timedelta(days=1)).isoformat()
    url = (
        f"https://api.github.com/search/repositories"
        f"?q=language:{language}+pushed:%3E{cutoff}+stars:%3E500"
        f"&sort=stars&order=desc&per_page={per_page}"
    )
    data = _github_request(url)
    if not data or not isinstance(data, dict):
        return []
    items = data.get("items", [])
    return [
        {
            "name": r.get("full_name", ""),
            "description": (r.get("description") or "")[:120],
            "stars": r.get("stargazers_count", 0),
            "url": r.get("html_url", ""),
            "topics": r.get("topics", [])[:5],
            "language": r.get("language") or language,
        }
        for r in items
    ]


# ─── Claude API ───────────────────────────────────────────────────────────────


def claude_call(prompt: str, max_tokens: int = 1200) -> str:
    if not ANTHROPIC_API_KEY:
        return "⚠️  ANTHROPIC_API_KEY not set. Run with --raw to see trending data without AI."

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


# ─── Helpers ──────────────────────────────────────────────────────────────────


def resolve_stack(raw: str) -> str:
    """Normalize a user-supplied stack name."""
    lower = raw.lower()
    return STACK_ALIASES.get(lower, lower)


def format_repo_list(repos: list[dict]) -> str:
    """Format a list of repos for display and for the Claude prompt."""
    lines = []
    for r in repos:
        stars = f"★{r['stars']:,}"
        topics = f"  [{', '.join(r['topics'])}]" if r.get("topics") else ""
        lines.append(f"  {r['name']}  {stars}")
        if r.get("description"):
            lines.append(f"    {r['description']}{topics}")
    return "\n".join(lines)


def get_parse_arg(args: list[str], flag: str) -> str | None:
    """Extract --flag value from args list."""
    if flag in args:
        idx = args.index(flag)
        if idx + 1 < len(args):
            return args[idx + 1]
    return None


# ─── Commands ─────────────────────────────────────────────────────────────────


def cmd_trending(args: list[str]):
    """Display trending repos in Kevin's stack."""
    stack_arg = get_parse_arg(args, "--stack") or get_parse_arg(args, "-s")
    stacks = [resolve_stack(stack_arg)] if stack_arg else DEFAULT_STACKS

    print(f"🔥 forge trending — what's hot right now\n")

    for lang in stacks:
        print(f"── {lang.capitalize()} ────────────────────────────────────")
        repos = fetch_trending(lang, days=7, per_page=6)
        if not repos:
            print(f"  No results (rate limit or network). Try again with GITHUB_TOKEN set.\n")
            continue

        for r in repos:
            stars = f"★{r['stars']:,}"
            print(f"  {r['name']:<40} {stars:>10}")
            if r["description"]:
                print(f"    {r['description']}")
            if r.get("topics"):
                print(f"    [{', '.join(r['topics'][:4])}]")
            print()

    print("Tip: `forge ideas` to generate project ideas from these trends.")
    print()


def cmd_ideas(args: list[str]):
    """Generate AI-powered weekend project ideas based on trending repos."""
    stack_arg = get_parse_arg(args, "--stack") or get_parse_arg(args, "-s")
    stacks = [resolve_stack(stack_arg)] if stack_arg else DEFAULT_STACKS
    save = "--save" in args
    raw = "--raw" in args

    today = date.today().isoformat()

    print(f"💡 forge ideas — generating project ideas for {today}\n")
    print(f"   Stack: {', '.join(stacks)}")
    print(f"   Fetching trending repos...\n")

    # Gather trending data
    trending_sections = {}
    for lang in stacks:
        new_repos = fetch_trending(lang, days=7, per_page=6)
        trending_sections[lang] = new_repos

    # Build a compact summary for Claude
    trend_summary_lines = []
    for lang, repos in trending_sections.items():
        if repos:
            trend_summary_lines.append(f"\n{lang.upper()} — trending new repos this week:")
            for r in repos[:5]:
                trend_summary_lines.append(
                    f"  • {r['name']} (★{r['stars']:,}): {r['description'] or '(no description)'}"
                )
        else:
            trend_summary_lines.append(f"\n{lang.upper()}: (no trending data available)")

    trend_summary = "\n".join(trend_summary_lines)

    if raw:
        print("── Trending Data (raw, no Claude) ───────────────")
        print(trend_summary)
        print()
        return

    if not ANTHROPIC_API_KEY:
        print("⚠️  ANTHROPIC_API_KEY not set. Add it to .env to generate ideas.")
        print("\nHere's what's trending (raw):\n")
        print(trend_summary)
        return

    prompt = f"""You are a creative technical advisor to Kevin, a full-stack engineer in Toronto.
Today is {today}.

KEVIN'S PROFILE:
{KEVIN_PROFILE.strip()}

WHAT'S TRENDING IN KEVIN'S STACK RIGHT NOW:
{trend_summary}

---

Generate exactly 3 weekend project ideas for Kevin.

Rules:
- Each idea must be achievable solo in 1-2 days
- At least one idea must connect to or extend one of his active projects
  (matchamap.club, kegbot, claudespace, cookbook)
- At least one idea must be inspired by (not a clone of) a trending repo above
- Ideas should have personality — not generic "build a CRUD app"
- Be concrete and opinionated

For each idea, use EXACTLY this format:

---
💡 [N]. [Project Name] — [One-line tagline]

What: [2 sentences describing what it does]
Why Kevin: [1 sentence on why this fits him specifically]
Stack: [Language + key tools, keep it short]
First commit: [The very first thing to build — one specific, concrete step]
Wildcard: [One unexpected twist or easter egg that makes it more fun]
---

After the 3 ideas, add one line: "Forge score: [1-10] — [one-sentence take on this week's trends]"
"""

    print("[claude] Thinking about what to build...\n")
    ideas_text = claude_call(prompt, max_tokens=1400)

    print("═" * 64)
    print(ideas_text)
    print("═" * 64)
    print()

    if save:
        _save_ideas(ideas_text, today, stacks)


def _save_ideas(ideas_text: str, generated_at: str, stacks: list[str]):
    """Append generated ideas to ideas.json."""
    if IDEAS_FILE.exists():
        try:
            existing = json.loads(IDEAS_FILE.read_text())
        except Exception:
            existing = []
    else:
        existing = []

    if not isinstance(existing, list):
        existing = []

    existing.append({
        "generated_at": generated_at,
        "stacks": stacks,
        "ideas": ideas_text,
    })

    IDEAS_FILE.write_text(json.dumps(existing, indent=2))
    print(f"[forge] Saved to {IDEAS_FILE.relative_to(REPO_ROOT)}")
    print(f"        {len(existing)} idea set(s) in archive.")
    print()


def cmd_history(args: list[str]):
    """Show previously generated idea sets."""
    if not IDEAS_FILE.exists():
        print("No ideas saved yet. Run: forge ideas --save")
        return

    try:
        data = json.loads(IDEAS_FILE.read_text())
    except Exception as e:
        print(f"Could not read ideas.json: {e}")
        return

    if not data:
        print("ideas.json is empty.")
        return

    n = int(get_parse_arg(args, "--last") or 3)
    entries = data[-n:]

    print(f"📚 forge history — last {len(entries)} idea set(s)\n")
    for i, entry in enumerate(reversed(entries), 1):
        print(f"── Set {i} — {entry.get('generated_at', '?')} "
              f"(stacks: {', '.join(entry.get('stacks', []))}) ──")
        print(entry.get("ideas", "(empty)"))
        print()


def cmd_help():
    print("""
💡 forge — AI-powered project idea generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USAGE
    forge <command> [options]

COMMANDS

  ideas                      Generate 3 weekend project ideas (Claude required)
    --stack LANG               Focus on a specific language (python, typescript, go, js)
    --save                     Append generated ideas to ideas.json

  trending                   Show trending new repos in your stack (no Claude needed)
    --stack LANG               Focus on a specific language

  history                    Show previously saved idea sets
    --last N                   Show last N sets (default: 3)

  help                       This help text

STACKS
  Supported: python (py), typescript (ts), javascript (js), go
  Default: python + typescript (Kevin's primary stack)

SETUP
  ANTHROPIC_API_KEY — required for `forge ideas`
  GITHUB_TOKEN      — optional but recommended (60 → 5000 req/hr)
  Both can go in projects/kegbot-claude/.env or a local .env

EXAMPLES
    forge ideas                        # Full AI ideas based on trending
    forge ideas --stack python --save  # Python-focused, save to ideas.json
    forge trending                     # Just the raw trending list
    forge trending --stack typescript
    forge history                      # Revisit past idea sets

HOW IT WORKS
  1. Fetches repos created in the last 7 days, sorted by stars
     (i.e. "what blew up this week" — not stale stats)
  2. Sends Kevin's profile + trends to Claude
  3. Claude generates 3 scoped, personalized, creative ideas
  4. Each idea includes: what, why, stack, first commit, wildcard twist

Built by Claude (Cycle 8). "Claude suggesting what Claude should build" — yes, that's intentional.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

COMMANDS = {
    "ideas": cmd_ideas,
    "trending": cmd_trending,
    "history": cmd_history,
    "help": lambda _: cmd_help(),
    "--help": lambda _: cmd_help(),
    "-h": lambda _: cmd_help(),
}


def main():
    argv = sys.argv[1:]

    if not argv:
        cmd_ideas([])  # default: generate ideas
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
