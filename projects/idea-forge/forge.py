#!/usr/bin/env python3
"""
forge — AI weekend project idea generator

Watches what's trending on GitHub across Kevin's stack (Python, TypeScript, Go),
then asks Claude to dream up weekend project ideas based on the landscape.

Zero dependencies beyond stdlib. GitHub search API (no auth required, 10 req/min).

Usage:
    forge suggest                    # 3 ideas, last 7 days, all stacks
    forge suggest --count 5          # 5 ideas
    forge suggest --days 14          # look at last 14 days of trending
    forge suggest --langs python,go  # only scan specific languages
    forge trending                   # raw trending repos (no Claude)
    forge trending --lang typescript # filter to one language
    forge trending --days 30         # wider window
    forge help
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent.parent

KEVIN_PROFILE = """
Kevin Geng — software engineer at Faire in Toronto, side project enthusiast, matcha devotee.

Stack: TypeScript, Python, Go
Active projects:
  - matchamap.club — opinionated matcha cafe discovery map (personal + community)
  - kegbot — Discord personal assistant bot with Claude AI superpowers
  - claudespace — autonomous Claude build lab (forge literally lives inside it)
  - cookbook — personal recipe collection

Preferences:
  - Prefers CLI tools, Discord bots, small web apps — nothing mobile
  - Values zero-dependency or low-dependency code
  - Loves tools built for one person that happen to work for everyone
  - Aesthetic: practical + slightly whimsical, not enterprise-y
  - Typical weekend project: 200–600 lines, something he'll actually use

Interests beyond code: specialty coffee/matcha, cooking, developer tooling,
maps & location data, personal automation, terminal aesthetics
"""

DEFAULT_LANGS = ["python", "typescript", "go"]

LANG_DISPLAY = {
    "python": "Python",
    "typescript": "TypeScript",
    "go": "Go",
    "rust": "Rust",
    "javascript": "JavaScript",
}


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


# ─── GitHub trending ──────────────────────────────────────────────────────────


def _github_request(url: str) -> dict | list | None:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "idea-forge/1.0",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        if e.code == 403 and "rate limit" in body.lower():
            print(
                "  [forge] GitHub rate limit hit. Wait a minute or add GITHUB_TOKEN to .env.",
                file=sys.stderr,
            )
        elif e.code not in (422,):
            print(f"  [forge] GitHub API {e.code}: {body[:120]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  [forge] Request failed: {e}", file=sys.stderr)
        return None


def fetch_trending_repos(lang: str, days: int = 7, per_page: int = 5) -> list[dict]:
    """
    Fetch recently-created repos gaining stars fast in a given language.
    Uses GitHub search API — no auth required (10 req/min unauthenticated).
    """
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    q = urllib.parse.quote(f"language:{lang} created:>{since} stars:>3")
    url = (
        f"https://api.github.com/search/repositories"
        f"?q={q}&sort=stars&order=desc&per_page={per_page}"
    )

    data = _github_request(url)
    if not data or not isinstance(data, dict):
        return []

    repos = []
    for r in data.get("items", [])[:per_page]:
        repos.append(
            {
                "name": r["full_name"],
                "description": (r.get("description") or "").strip(),
                "stars": r["stargazers_count"],
                "topics": r.get("topics", [])[:6],
                "url": r["html_url"],
                "language": lang,
                "created_at": r.get("created_at", "")[:10],
            }
        )
    return repos


# ─── Claude ───────────────────────────────────────────────────────────────────


def claude_generate_ideas(repos: list[dict], count: int = 3) -> str:
    """Ask Claude to generate weekend project ideas based on trending repos."""
    if not ANTHROPIC_API_KEY:
        return (
            "⚠️  ANTHROPIC_API_KEY not set.\n\n"
            "  export ANTHROPIC_API_KEY=sk-ant-...\n"
            "  Or add it to projects/kegbot-claude/.env\n\n"
            "  `forge trending` works without an API key."
        )

    repos_json = json.dumps(repos, indent=2)

    prompt = f"""You're an AI assistant helping a developer find their next weekend project.

Here's who you're helping:
{KEVIN_PROFILE}

Here are trending GitHub repositories in his tech stack right now:
{repos_json}

Generate {count} weekend project ideas inspired by what's trending. Each idea should:
- Be something Kevin would actually want to build AND use (personal itch, not portfolio piece)
- Take roughly one weekend (200–600 lines of code)
- Draw something interesting from the trending repos — a pattern, problem space, or technique
- Feel specific to Kevin's interests and situation, not generic
- Have a punchy name with personality

Format each idea exactly like this:

## [Punchy Project Name]
**Concept:** One sentence.
**Why now:** What from the trending list makes this timely (be specific about the repo).
**Stack:** Language + any key libraries (prefer stdlib-first).
**Build it as:**
- Specific bullet 1
- Specific bullet 2
- Specific bullet 3
**The twist:** One surprising or delightful detail that makes it distinctly Kevin's.

---

Be opinionated. Be specific. Pick ideas that would make Kevin think "I actually want to build that."
"""

    payload = json.dumps(
        {
            "model": "claude-opus-4-6",
            "max_tokens": 1800,
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


# ─── Arg parsing ──────────────────────────────────────────────────────────────


def parse_flags(args: list[str], defaults: dict) -> dict:
    """Simple --key value flag parser."""
    result = dict(defaults)
    i = 0
    while i < len(args):
        key = args[i]
        if key.startswith("--") and i + 1 < len(args):
            result[key[2:]] = args[i + 1]
            i += 2
        else:
            i += 1
    return result


# ─── Commands ─────────────────────────────────────────────────────────────────


def cmd_suggest(args: list[str]):
    """Fetch trending repos and ask Claude to generate project ideas."""
    opts = parse_flags(args, {"count": "3", "days": "7", "langs": ",".join(DEFAULT_LANGS)})
    count = int(opts["count"])
    days = int(opts["days"])
    langs = [l.strip().lower() for l in opts["langs"].split(",") if l.strip()]

    lang_display = ", ".join(LANG_DISPLAY.get(l, l) for l in langs)
    print(f"🔭 idea-forge — scanning trending repos ({lang_display}, last {days}d)...\n")

    all_repos: list[dict] = []
    for i, lang in enumerate(langs):
        label = LANG_DISPLAY.get(lang, lang)
        print(f"  [{i + 1}/{len(langs)}] {label}...")
        repos = fetch_trending_repos(lang, days=days, per_page=5)
        all_repos.extend(repos)
        if repos:
            print(f"         {len(repos)} repo(s) found")
        if i < len(langs) - 1:
            time.sleep(0.8)  # gentle on unauthenticated search API (10 req/min)

    if not all_repos:
        print("\n⚠️  No trending repos found.")
        print("   Try: --days 30 for a wider window, or add GITHUB_TOKEN to .env")
        return

    print(f"\n  {len(all_repos)} repos total → asking Claude for {count} idea(s)...\n")

    ideas = claude_generate_ideas(all_repos, count=count)

    width = 62
    print("=" * width)
    print(f"  idea-forge — {datetime.now().strftime('%Y-%m-%d')}")
    print(f"  {count} weekend project idea(s) · {len(all_repos)} trending repos scanned")
    print("=" * width)
    print()
    print(ideas)
    print()
    print("=" * width)
    print("  `forge trending` — see the raw repo list")
    print("  `forge suggest --count 5 --days 14` — more ideas, wider window")
    print("=" * width)


def cmd_trending(args: list[str]):
    """Show raw trending repos without Claude."""
    opts = parse_flags(args, {"lang": "", "days": "7"})
    days = int(opts["days"])
    langs = [opts["lang"].strip().lower()] if opts["lang"] else DEFAULT_LANGS

    print(f"🔭 Trending repos (last {days}d)\n")

    for i, lang in enumerate(langs):
        display = LANG_DISPLAY.get(lang, lang)
        print(f"── {display} " + "─" * max(0, 52 - len(display)))
        repos = fetch_trending_repos(lang, days=days, per_page=8)

        if not repos:
            print("  (none found)\n")
        else:
            for r in repos:
                stars = f"{r['stars']:,}"
                bar = "★" * min(r["stars"] // 30 + 1, 15)
                desc = r["description"][:72] if r["description"] else "(no description)"
                topics_str = f"  [{', '.join(r['topics'][:4])}]" if r["topics"] else ""
                print(f"  {r['name']}")
                print(f"  {bar} {stars} ★  —  {desc}")
                if topics_str:
                    print(f"  {topics_str}")
                print()

        if i < len(langs) - 1:
            time.sleep(0.8)


def cmd_help():
    print("""
🔭 idea-forge — AI weekend project idea generator

Scans trending GitHub repos in your stack and asks Claude what to build next.

USAGE
    forge <command> [options]

COMMANDS

  suggest                   Generate 3 project ideas (requires ANTHROPIC_API_KEY)
    --count N                 Number of ideas (default: 3)
    --days N                  Days to look back for trending data (default: 7)
    --langs lang1,lang2       Languages to scan (default: python,typescript,go)

  trending                  Show raw trending repos (no Claude or API key needed)
    --lang LANG               Filter to one language (python, typescript, go, ...)
    --days N                  Days to look back (default: 7)

  help                      This help text

SETUP
  No API key needed for `forge trending`.
  For `forge suggest`: set ANTHROPIC_API_KEY in your environment or in
  projects/kegbot-claude/.env (forge will find it automatically).
  Optional: add GITHUB_TOKEN to .env for higher GitHub rate limits (60 → 5000/hr).

EXAMPLES
    forge suggest
    forge suggest --count 5 --days 14
    forge suggest --langs python
    forge trending
    forge trending --lang go --days 30

Built by Claude (Cycle 8). Curiosity-driven, Kevin-shaped.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

COMMANDS = {
    "suggest": cmd_suggest,
    "trending": cmd_trending,
    "help": lambda _: cmd_help(),
    "--help": lambda _: cmd_help(),
    "-h": lambda _: cmd_help(),
}


def main():
    argv = sys.argv[1:]

    if not argv or argv[0] in ("help", "--help", "-h"):
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
