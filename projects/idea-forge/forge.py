#!/usr/bin/env python3
"""
forge — AI-powered weekend project idea generator

Watches trending GitHub repos in Kevin's tech stack, then asks Claude to dream up
weekend projects tailored to his interests. Also lets you save and revisit ideas.

Zero dependencies beyond stdlib. Requires ANTHROPIC_API_KEY for `ideas` command.
GitHub API (no auth): 60 req/hr. Set GITHUB_TOKEN for 5000 req/hr.

Usage:
    forge trending                          # Trending repos this week (Python + TypeScript)
    forge trending --lang go                # Trending in a specific language
    forge trending --lang python,typescript # Multiple languages
    forge trending --days 7                 # Window for "new" repos (default: 7)
    forge ideas                             # Claude-generated weekend project ideas
    forge ideas --lang python               # Constrain to one language
    forge ideas --count 5                   # How many ideas (default: 3)
    forge save "<title>"                    # Save an idea to ideas.json
    forge list                              # List saved ideas
    forge clear                             # Clear saved ideas
    forge help
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# ─── Paths & config ───────────────────────────────────────────────────────────

FORGE_DIR = Path(__file__).parent
REPO_ROOT = FORGE_DIR.parent.parent
IDEAS_FILE = FORGE_DIR / "ideas.json"

DEFAULT_LANGS = ["python", "typescript"]
KEVIN_PROFILE = """Kevin Geng — full-stack software engineer at Faire (Toronto).
Stack: React, TypeScript, Java/Spring Boot, Python, AWS.
Interests: personal automation, Discord bots, maps/geospatial, cooking tools,
ML/AI experiments, gamification, teaching/tools that delight.
Active side projects: matchamap.club (matcha cafe finder), kegbot (personal assistant),
claudespace (autonomous AI build lab), cookbook/recipe tools.
Vibe: practical builder who wants fun + useful tools, not portfolio pieces."""

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
        print(f"⚠️  GitHub API {e.code}: {body[:200]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"⚠️  Request failed: {e}", file=sys.stderr)
        return None


def search_trending_repos(
    languages: list[str], days: int = 7, per_lang: int = 8
) -> list[dict]:
    """
    Find repos created in the last `days` days, sorted by stars.
    Returns a merged list across languages, deduplicated.
    """
    since = (date.today() - timedelta(days=days)).isoformat()
    seen: set[int] = set()
    results: list[dict] = []

    for lang in languages:
        q = urllib.parse.quote(f"language:{lang} created:>{since}")
        url = (
            f"https://api.github.com/search/repositories"
            f"?q={q}&sort=stars&order=desc&per_page={per_lang}"
        )
        data = _gh_request(url)
        if not data or "items" not in data:
            continue

        for repo in data["items"]:
            rid = repo.get("id")
            if rid in seen:
                continue
            seen.add(rid)
            results.append({
                "name": repo.get("full_name", ""),
                "description": (repo.get("description") or "")[:120],
                "language": repo.get("language") or lang,
                "stars": repo.get("stargazers_count", 0),
                "url": repo.get("html_url", ""),
                "topics": repo.get("topics", [])[:6],
                "created_at": repo.get("created_at", "")[:10],
            })

    # Sort by stars descending
    results.sort(key=lambda r: r["stars"], reverse=True)
    return results


# ─── Claude ───────────────────────────────────────────────────────────────────


def claude_call(prompt: str, max_tokens: int = 1000) -> str:
    if not ANTHROPIC_API_KEY:
        return "⚠️  ANTHROPIC_API_KEY not set. Set it in .env to use this command."

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


# ─── Ideas storage ────────────────────────────────────────────────────────────


def load_ideas() -> list[dict]:
    if not IDEAS_FILE.exists():
        return []
    try:
        return json.loads(IDEAS_FILE.read_text())
    except Exception:
        return []


def save_ideas(ideas: list[dict]):
    IDEAS_FILE.write_text(json.dumps(ideas, indent=2))


# ─── Commands ─────────────────────────────────────────────────────────────────


def _parse_args(args: list[str]) -> dict:
    """Parse common flags into a dict."""
    opts: dict = {}

    if "--lang" in args:
        idx = args.index("--lang")
        if idx + 1 < len(args):
            opts["langs"] = [l.strip() for l in args[idx + 1].split(",") if l.strip()]

    if "--days" in args:
        idx = args.index("--days")
        if idx + 1 < len(args):
            try:
                opts["days"] = int(args[idx + 1])
            except ValueError:
                pass

    if "--count" in args:
        idx = args.index("--count")
        if idx + 1 < len(args):
            try:
                opts["count"] = int(args[idx + 1])
            except ValueError:
                pass

    return opts


def _render_repo(repo: dict, index: int) -> str:
    stars = repo["stars"]
    star_str = f"⭐ {stars:,}" if stars > 0 else ""
    topics = "  " + " ".join(f"#{t}" for t in repo["topics"]) if repo["topics"] else ""
    desc = f"\n     {repo['description']}" if repo["description"] else ""
    return (
        f"  {index}. [{repo['language']}] {repo['name']}  {star_str}\n"
        f"     {repo['url']}{desc}{topics}"
    )


def cmd_trending(args: list[str]):
    opts = _parse_args(args)
    langs = opts.get("langs", DEFAULT_LANGS)
    days = opts.get("days", 7)

    print(f"🔥 forge trending — new repos this week ({', '.join(langs)})\n")
    print(f"   Searching repos created in the last {days} day(s)...\n")

    repos = search_trending_repos(langs, days=days, per_lang=10)

    if not repos:
        print("⚠️  No results. GitHub's Search API may be rate-limited (60 req/hr without auth).")
        print("   Set GITHUB_TOKEN in .env for 5000 req/hr.")
        return

    for i, repo in enumerate(repos, 1):
        print(_render_repo(repo, i))
        print()

    print(f"   {len(repos)} repo(s) found. Run `forge ideas` to get project suggestions.")


def cmd_ideas(args: list[str]):
    opts = _parse_args(args)
    langs = opts.get("langs", DEFAULT_LANGS)
    days = opts.get("days", 7)
    count = opts.get("count", 3)

    print(f"💡 forge ideas — generating {count} weekend project idea(s) for Kevin\n")
    print(f"   Fetching trending {', '.join(langs)} repos (last {days} days)...")

    repos = search_trending_repos(langs, days=days, per_lang=8)

    if not repos:
        print("⚠️  Couldn't fetch trending repos — generating ideas from Kevin's profile alone.")
        repo_context = "(No trending repos available — use Kevin's known interests.)"
    else:
        # Format top repos for the prompt
        lines = []
        for r in repos[:12]:
            topics = ", ".join(r["topics"]) if r["topics"] else "none"
            lines.append(
                f"- {r['name']} ({r['language']}, ⭐{r['stars']}): "
                f"{r['description'] or 'no description'}. Topics: {topics}"
            )
        repo_context = "\n".join(lines)
        print(f"   Found {len(repos)} trending repo(s). Asking Claude to dream up ideas...\n")

    today = date.today().strftime("%B %d, %Y")

    prompt = f"""You are idea-forge, an AI project idea generator. Today is {today}.

Here's who you're generating ideas for:

{KEVIN_PROFILE}

Here are trending repos this week in his stack:
{repo_context}

Your job: Generate exactly {count} weekend project ideas tailored to Kevin specifically.

For each idea:
1. **Title** — catchy, specific (not "Build a REST API")
2. **What to build** — 2-3 sentences. Be specific about what it does.
3. **Why Kevin** — 1 sentence connecting it to something he actually cares about
4. **Stack** — exactly what tech (Python CLI, TypeScript + React, etc.)
5. **Scope** — "one afternoon" / "one full weekend" / "two weekends"
6. **The hook** — one punchy sentence that makes it sound fun, not like homework

Rules:
- Ideas should be inspired by trending repos but not clones of them
- Connect to Kevin's actual projects when it adds a hook (matchamap, kegbot, cookbook)
- Prefer practical + delightful over purely impressive
- Don't suggest things he's already built in claudespace
- Number each idea clearly

Generate the {count} ideas now:"""

    response = claude_call(prompt, max_tokens=1200)

    print("─" * 60)
    print(response)
    print("─" * 60)
    print()
    print("💾 Like an idea? Save it: forge save \"<title>\"")
    print("📋 View saved ideas: forge list")


def cmd_save(args: list[str]):
    # Title is everything after "save"
    title = " ".join(a for a in args if not a.startswith("--")).strip()
    if not title:
        print("Usage: forge save \"<idea title>\"")
        sys.exit(1)

    ideas = load_ideas()
    entry = {
        "title": title,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    ideas.append(entry)
    save_ideas(ideas)
    print(f"💾 Saved: \"{title}\"")
    print(f"   Total ideas saved: {len(ideas)}")


def cmd_list(args: list[str]):
    ideas = load_ideas()
    if not ideas:
        print("📋 No saved ideas yet. Run `forge ideas` then `forge save \"<title>\"`.")
        return

    print(f"📋 forge ideas — {len(ideas)} saved idea(s)\n")
    for i, idea in enumerate(ideas, 1):
        saved = idea.get("saved_at", "")[:10]
        print(f"  {i:>2}. {idea['title']}")
        if saved:
            print(f"      saved {saved}")
    print()


def cmd_clear(args: list[str]):
    count = len(load_ideas())
    if count == 0:
        print("Nothing to clear — ideas list is already empty.")
        return
    save_ideas([])
    print(f"🗑  Cleared {count} saved idea(s).")


def cmd_help():
    print("""
💡 forge — AI-powered weekend project idea generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Watches trending GitHub repos in your stack, then asks Claude to dream up
weekend projects tailored to your profile. Save the ones that stick.

USAGE
    forge <command> [options]

COMMANDS

  trending                   Trending repos this week (Python + TypeScript)
  ideas                      Claude-generated weekend project ideas
  save "<title>"             Save an idea to ideas.json
  list                       List your saved ideas
  clear                      Clear saved ideas
  help                       This help text

OPTIONS
  --lang <lang[,lang...]>    Language(s) to search (default: python,typescript)
  --days <n>                 Recency window for trending (default: 7)
  --count <n>                Number of ideas to generate (default: 3)

EXAMPLES
    forge trending
    forge trending --lang go
    forge trending --lang python,typescript,rust
    forge ideas
    forge ideas --lang typescript --count 5
    forge save "Terminal-based Git graph visualizer"
    forge list

SETUP
    No API key needed for `trending`.
    Add ANTHROPIC_API_KEY to .env (kegbot-claude/.env works too) for `ideas`.
    Add GITHUB_TOKEN to .env to raise rate limits (60 → 5000 req/hr).

Built by Claude (Cycle 8). Because the best ideas come from watching what other
people are building and asking: what would Kevin actually use?
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

COMMANDS = {
    "trending": cmd_trending,
    "ideas": cmd_ideas,
    "save": cmd_save,
    "list": cmd_list,
    "clear": cmd_clear,
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
