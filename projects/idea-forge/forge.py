#!/usr/bin/env python3
"""
idea-forge — AI project idea generator for Kevin

Scans trending GitHub repos in Kevin's tech stack (Python, TypeScript, React, Go),
sends them to Claude, and gets back 3 weekend project ideas tailored specifically
to what Kevin builds and cares about.

Zero external dependencies. Pure stdlib + Claude API.

Usage:
    forge ideas              # 3 personalized project ideas (requires ANTHROPIC_API_KEY)
    forge trending           # Show raw trending repos in Kevin's stack (no Claude)
    forge trending --lang go # Trending repos for a specific language
    forge help
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

# Kevin's tech stack (used when searching trending repos)
KEVIN_STACK = ["python", "typescript", "javascript", "go"]
STACK_LABEL = "Python, TypeScript, JavaScript, Go"

# How far back "recent" means for trending (repos created/updated in last 30 days)
TRENDING_SINCE_DAYS = 30

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

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"⚠️  GitHub API error {e.code}: {body[:200]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"⚠️  Request failed: {e}", file=sys.stderr)
        return None


def fetch_trending_repos(language: str, days: int = TRENDING_SINCE_DAYS, per_page: int = 5) -> list[dict]:
    """
    Fetch recently-starred repos for a language using GitHub search.
    Simulates 'trending' by searching repos created recently, sorted by stars.
    """
    since = (date.today() - timedelta(days=days)).isoformat()
    query = f"language:{language} created:>{since} stars:>50"
    encoded = urllib.parse.quote(query)
    url = (
        f"https://api.github.com/search/repositories"
        f"?q={encoded}&sort=stars&order=desc&per_page={per_page}"
    )
    data = _github_request(url)
    if not data or "items" not in data:
        return []
    return data["items"]


def format_repo(repo: dict) -> dict:
    """Extract the fields we care about from a raw GitHub repo object."""
    topics = repo.get("topics", [])[:5]
    return {
        "name": repo.get("full_name", "?"),
        "description": (repo.get("description") or "")[:120],
        "language": repo.get("language") or "?",
        "stars": repo.get("stargazers_count", 0),
        "topics": topics,
        "url": repo.get("html_url", ""),
    }


def gather_trending(languages: list[str] = KEVIN_STACK, n_per_lang: int = 4) -> list[dict]:
    """Fetch trending repos across all target languages, deduplicated."""
    seen = set()
    results = []
    for lang in languages:
        repos = fetch_trending_repos(lang, per_page=n_per_lang)
        for r in repos:
            name = r.get("full_name", "")
            if name and name not in seen:
                seen.add(name)
                results.append(format_repo(r))
    return results


# ─── Claude call ──────────────────────────────────────────────────────────────


def claude_call(prompt: str, max_tokens: int = 1000) -> str:
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
        with urllib.request.urlopen(req, timeout=45) as resp:
            result = json.loads(resp.read())
            return result["content"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return f"[Claude API error {e.code}: {body[:300]}]"
    except Exception as e:
        return f"[Claude API error: {e}]"


# ─── Commands ─────────────────────────────────────────────────────────────────


def cmd_trending(args: list[str]):
    """Show raw trending repos (no Claude needed)."""
    # Optional --lang filter
    lang_filter = None
    if "--lang" in args:
        idx = args.index("--lang")
        if idx + 1 < len(args):
            lang_filter = args[idx + 1].lower()

    langs = [lang_filter] if lang_filter else KEVIN_STACK

    print(f"🔭 idea-forge trending — last {TRENDING_SINCE_DAYS} days\n")
    print(f"   Scanning: {', '.join(langs)}\n")

    all_repos = []
    for lang in langs:
        repos = fetch_trending_repos(lang, per_page=5)
        for r in repos:
            all_repos.append(format_repo(r))

    if not all_repos:
        print("No trending repos found. Try a wider date range or check your network.")
        return

    # Deduplicate
    seen = set()
    unique = []
    for r in all_repos:
        if r["name"] not in seen:
            seen.add(r["name"])
            unique.append(r)

    # Sort by stars
    unique.sort(key=lambda r: r["stars"], reverse=True)

    for r in unique:
        topics_str = "  " + ", ".join(r["topics"]) if r["topics"] else ""
        stars = f"★ {r['stars']:,}"
        print(f"  {r['name']:<45}  {r['language']:<12}  {stars}")
        if r["description"]:
            print(f"    {r['description']}")
        if topics_str:
            print(f"    topics: {', '.join(r['topics'])}")
        print()

    print(f"  {len(unique)} repo(s) found across {len(langs)} language(s).")
    print("\n  Run `forge ideas` to generate project ideas from this data.\n")


def cmd_ideas(args: list[str]):
    """Generate 3 Claude-powered weekend project ideas tailored to Kevin."""
    discord = "--discord" in args
    verbose = "--verbose" in args

    print("⚡ idea-forge — generating project ideas for Kevin\n")
    print(f"   Step 1/2: Scanning trending repos in [{STACK_LABEL}]...")

    repos = gather_trending(n_per_lang=4)

    if not repos:
        print("⚠️  Couldn't fetch trending repos. Check your network.")
        print("   Try `forge trending` to debug.")
        return

    repos.sort(key=lambda r: r["stars"], reverse=True)

    if verbose:
        print(f"\n   Found {len(repos)} trending repos:\n")
        for r in repos[:12]:
            print(f"   · {r['name']} ({r['language']}, ★{r['stars']:,})")
            if r["description"]:
                print(f"     {r['description'][:80]}")
        print()

    print(f"   Found {len(repos)} trending repos. Step 2/2: Asking Claude for ideas...\n")

    # Build repo summary for the prompt
    repo_lines = []
    for r in repos[:15]:  # cap context size
        topics = ", ".join(r["topics"]) if r["topics"] else "—"
        repo_lines.append(
            f"- [{r['language']}] {r['name']} (★{r['stars']:,}): {r['description']}"
            + (f" [topics: {topics}]" if r["topics"] else "")
        )
    repo_summary = "\n".join(repo_lines)

    today = date.today().isoformat()

    prompt = f"""You are idea-forge, an AI that generates weekend project ideas for Kevin Geng.

**Who is Kevin?**
- Full-stack engineer at Faire (Toronto)
- Stack: React, TypeScript, Python, Java/Spring Boot, AWS
- Active projects: matchamap.club (matcha cafe map), claudespace (autonomous AI lab), kegbot (personal assistant CLI)
- Interests: cooking, ML/AI, Discord bots, personal automation, maps/place data, gaming, transit
- Vibe: pragmatic builder — he wants things that are fun AND actually useful. Not portfolio fluff.

**Trending GitHub repos right now ({today}):**
{repo_summary}

**Your job:**
Generate exactly 3 weekend project ideas for Kevin. Each idea should:
1. Be genuinely buildable in 1-2 weekends (not a startup)
2. Connect to something Kevin actually cares about (see above)
3. Be inspired by (but NOT just a clone of) one or more of the trending repos

**Format each idea exactly like this:**

---
### 💡 [Catchy project name]

**What it is:** One sentence. Concrete and specific — not "a tool that helps you..."

**Why Kevin would love it:** One sentence. Reference something specific about him.

**Inspired by:** Which trending repo(s) sparked this idea

**Stack:** The tech you'd use (Kevin's stack preferred)

**Weekend 1:** What you'd build first (the core)
**Weekend 2:** What you'd add to make it actually useful/fun

---

Be specific. Be honest about scope. Don't pad. If an idea is weak, don't include it.
The best idea-forge output makes Kevin think "wait, I could actually build that this Saturday."
"""

    result = claude_call(prompt, max_tokens=1200)

    print("─" * 65)
    print(result)
    print("─" * 65)
    print()
    print(f"  Run `forge trending` to see the full trending repo list.")
    print(f"  Run `forge ideas --verbose` to see which repos were used.\n")

    if discord:
        _post_to_discord(f"⚡ **idea-forge: Weekend Project Ideas**\n\n{result[:1800]}")


def _post_to_discord(content: str):
    discord_post = REPO_ROOT / "projects" / "discord-bridge" / "post.py"
    if not discord_post.exists():
        print("[discord] post.py not found — skipping.", file=sys.stderr)
        return
    import subprocess
    try:
        subprocess.run(
            [sys.executable, str(discord_post), content],
            timeout=15, check=False
        )
        print("[discord] Posted.")
    except Exception as e:
        print(f"[discord] Failed: {e}", file=sys.stderr)


def cmd_help():
    print("""
⚡ idea-forge — AI-powered weekend project idea generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Scans trending GitHub repos in Kevin's stack and uses Claude
to suggest 3 weekend project ideas tailored to what he builds.

USAGE
    forge <command> [options]

COMMANDS

  ideas                      Generate 3 project ideas (requires API key)
    --discord                  Also post to Discord
    --verbose                  Show which trending repos were used

  trending                   Show raw trending repos (no API key needed)
    --lang LANGUAGE            Filter to a single language (python, typescript, go, etc.)

  help                       Show this help

SETUP
  Set ANTHROPIC_API_KEY in projects/kegbot-claude/.env or .env
  Optionally set GITHUB_TOKEN for higher GitHub rate limits

EXAMPLES
    forge ideas
    forge ideas --verbose
    forge trending
    forge trending --lang python
    forge trending --lang typescript

NOTES
  "Trending" = repos created in the last 30 days with >50 stars, sorted by stars.
  GitHub Search API: 10 req/min unauthenticated, 30 req/min authenticated.
  Uses Claude Opus for the idea generation (quality over cost here).

Built by Claude (Cycle 8). The meta-project: Claude suggesting what Claude should build next.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

COMMANDS = {
    "ideas": cmd_ideas,
    "trending": cmd_trending,
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
