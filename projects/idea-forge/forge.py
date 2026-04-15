#!/usr/bin/env python3
"""
forge — AI-powered project idea generator

Watches trending GitHub repos in Kevin's tech stack and uses Claude
to suggest tailored weekend project ideas. Trends meet taste.

Usage:
    forge trending                         # trending repos (all stack langs)
    forge trending --lang python           # Python only
    forge trending --lang typescript       # TypeScript only
    forge trending --days 7                # Period in days (default: 7)
    forge suggest                          # One killer idea with full plan
    forge suggest --raw                    # Show trend data without Claude
    forge ideas                            # 3 tailored project ideas
    forge ideas --count 5                  # Five ideas
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

# Kevin's tech stack — languages to watch for trends
KEVIN_STACK = ["python", "typescript", "java", "kotlin"]

LANGUAGE_LABELS = {
    "python": "🐍 Python",
    "typescript": "📘 TypeScript",
    "java": "☕ Java",
    "kotlin": "🟣 Kotlin",
    "go": "🐹 Go",
    "rust": "🦀 Rust",
    "javascript": "🟨 JavaScript",
}

# Kevin's profile — injected into every Claude prompt
KEVIN_PROFILE = """Kevin is a full-stack software engineer at Faire (Toronto).
Tech stack: React, TypeScript, Java/Kotlin/Spring Boot, Python, AWS.
Active side projects:
- matchamap.club — opinionated matcha cafe finder (maps, GeoJSON data pipeline)
- kegbot — Python personal assistant CLI (morning briefings, GitHub digest, weather)
- recipe-ai — Claude-powered cooking assistant (ingredient-based recipe suggestions)
- dev-insights — terminal GitHub activity dashboard (contribution heatmap, streak tracker)
- claudespace — autonomous AI build lab (this very repo)
Past work: ML/facial recognition (TensorFlow/Keras), Discord bots, personal finance
automation, transit status notifications, hackathon projects.
Interests: cooking, ML/AI, Discord bots, maps/place data, personal automation, gaming, teaching."""

# ─── Env / Config ─────────────────────────────────────────────────────────────


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
        body = e.read().decode("utf-8", errors="replace")
        print(f"⚠️  GitHub API {e.code}: {body[:150]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"⚠️  Request failed: {e}", file=sys.stderr)
        return None


def fetch_trending_repos(language: str, days: int = 7, per_page: int = 8) -> list[dict]:
    """
    Fetch trending repos for a language using GitHub Search API.
    'Trending' = recently-created repos, sorted by stars.
    """
    since = (date.today() - timedelta(days=days)).isoformat()
    query = f"language:{language}+created:>{since}"
    url = (
        "https://api.github.com/search/repositories"
        f"?q={query}&sort=stars&order=desc&per_page={per_page}"
    )
    data = _github_request(url)
    if not data or "items" not in data:
        return []
    return data["items"]


def format_repo_for_display(repo: dict) -> str:
    """Format a repo as a terminal one-liner."""
    name = repo.get("full_name", "?")
    stars = repo.get("stargazers_count", 0)
    desc = repo.get("description") or "no description"
    if len(desc) > 72:
        desc = desc[:72] + "…"
    topics = repo.get("topics", [])[:4]
    topic_str = f"  [{', '.join(topics)}]" if topics else ""
    return f"  ★{stars:>6,}  {name:<42}  {desc}{topic_str}"


def format_repos_for_claude(language: str, repos: list[dict]) -> str:
    """Compact block for Claude consumption — language header + top repos."""
    lines = [f"[{language.title()}]"]
    for r in repos[:6]:
        name = r.get("full_name", "?")
        stars = r.get("stargazers_count", 0)
        desc = (r.get("description") or "no description")[:80]
        topics = ", ".join(r.get("topics", [])[:5])
        topic_str = f" | topics: {topics}" if topics else ""
        lines.append(f"  - {name} (★{stars:,}): {desc}{topic_str}")
    return "\n".join(lines)


# ─── Claude API ───────────────────────────────────────────────────────────────


def claude_call(prompt: str, max_tokens: int = 1200) -> str:
    if not ANTHROPIC_API_KEY:
        return (
            "⚠️  ANTHROPIC_API_KEY not set.\n"
            "Add it to projects/kegbot-claude/.env to unlock Claude-powered ideas.\n"
            "Run with --raw to see trend data without Claude."
        )

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


# ─── Shared arg helpers ───────────────────────────────────────────────────────


def get_languages(args: list[str]) -> list[str]:
    """Parse --lang flag or return full Kevin stack."""
    if "--lang" in args:
        idx = args.index("--lang")
        if idx + 1 < len(args):
            return [args[idx + 1].lower()]
    return KEVIN_STACK


def get_days(args: list[str]) -> int:
    if "--days" in args:
        idx = args.index("--days")
        if idx + 1 < len(args):
            try:
                return int(args[idx + 1])
            except ValueError:
                pass
    return 7


def gather_trending(languages: list[str], days: int) -> dict[str, list[dict]]:
    """Return {language: [repos]} for all requested languages."""
    result: dict[str, list[dict]] = {}
    for lang in languages:
        repos = fetch_trending_repos(lang, days=days)
        if repos:
            result[lang] = repos
    return result


# ─── Commands ─────────────────────────────────────────────────────────────────


def cmd_trending(args: list[str]):
    """Show trending repos from GitHub Search."""
    languages = get_languages(args)
    days = get_days(args)
    since = (date.today() - timedelta(days=days)).isoformat()

    print(f"\n🔥 Trending GitHub Repos — last {days} days (since {since})\n")

    found_any = False
    for lang in languages:
        label = LANGUAGE_LABELS.get(lang, lang.title())
        print(f"{label}")
        repos = fetch_trending_repos(lang, days=days)
        if not repos:
            print("  (no results — try --days 14, or add GITHUB_TOKEN for higher rate limits)\n")
            continue
        found_any = True
        for repo in repos:
            print(format_repo_for_display(repo))
        print()

    if not found_any:
        print("No trending repos found. Try: forge trending --days 14")
        print("Tip: add GITHUB_TOKEN to .env to raise GitHub's rate limit (60→5000/hr).\n")
    else:
        print("Run `forge suggest` to get Claude's take on what to build.\n")


def cmd_suggest(args: list[str]):
    """One detailed project idea, tailored to Kevin + current trends."""
    raw = "--raw" in args
    languages = get_languages(args)
    days = get_days(args)

    print(f"🧠 forge suggest — fetching trends ({days}-day window)...\n")

    trending = gather_trending(languages, days)

    if not trending:
        print("No trending data found. Try --days 14 or add GITHUB_TOKEN.")
        return

    trend_blocks = [format_repos_for_claude(lang, repos) for lang, repos in trending.items()]
    trend_summary = "\n\n".join(trend_blocks)

    if raw:
        print("── Trend data (what Claude would see) ─────────────────────────")
        print(trend_summary)
        print("────────────────────────────────────────────────────────────────")
        return

    print("[claude] Cooking up one killer project idea...\n")

    prompt = f"""You are a creative technical advisor helping Kevin pick his next side project.

Kevin's profile:
{KEVIN_PROFILE}

Here are the hottest new repos on GitHub in Kevin's tech stack this past week:

{trend_summary}

Based on the trends above + Kevin's background, suggest ONE specific weekend project idea.

Format your response exactly like this:

**Project Name:** [catchy name]
**One-liner:** [single sentence]
**Why it fits Kevin:** [2-3 sentences connecting to his actual interests/stack/existing projects]
**The hook:** [what makes this interesting — which trend does it ride, and why now?]
**Rough plan:**
  - [step]
  - [step]
  - [step]
  - [step]
**Stack:** [specific tech choices, one line]
**Scope:** [realistic estimate — hours, days, or weekend]

Be specific. No generic CRUD apps. Think about what would genuinely delight a builder who
makes matcha cafe maps and autonomous AI build labs in his spare time."""

    result = claude_call(prompt, max_tokens=900)
    print("═" * 64)
    print(result)
    print("═" * 64)
    print("\nRun `forge ideas` to see 3 alternatives.\n")


def cmd_ideas(args: list[str]):
    """Generate multiple tailored project ideas with plans."""
    raw = "--raw" in args
    languages = get_languages(args)
    days = get_days(args)

    count = 3
    if "--count" in args:
        idx = args.index("--count")
        if idx + 1 < len(args):
            try:
                count = max(1, min(7, int(args[idx + 1])))
            except ValueError:
                pass

    print(f"💡 forge ideas — fetching trends ({days}-day window)...\n")

    trending = gather_trending(languages, days)

    if not trending:
        print("No trending data found. Try --days 14 or add GITHUB_TOKEN.")
        return

    trend_blocks = [format_repos_for_claude(lang, repos) for lang, repos in trending.items()]
    trend_summary = "\n\n".join(trend_blocks)

    if raw:
        print("── Trend data ──────────────────────────────────────────────────")
        print(trend_summary)
        print("────────────────────────────────────────────────────────────────")
        return

    print(f"[claude] Generating {count} project ideas...\n")

    prompt = f"""You are a creative technical advisor helping Kevin pick his next side project.

Kevin's profile:
{KEVIN_PROFILE}

Here are the hottest new repos on GitHub in Kevin's tech stack this past week:

{trend_summary}

Generate exactly {count} tailored weekend project ideas for Kevin.
Each idea should be inspired by something in the trending repos above.
Each idea should connect meaningfully to Kevin's existing interests or skills.
Vary the ideas — different project types, different problem spaces.

For each idea, use this exact format:

---
**#N. [Project Name]**
*[One-sentence description]*
**Trend connection:** [Which trending repo/pattern sparked this]
**Kevin fit:** [How it connects to his stack, interests, or active projects]
**Quick plan:**
  - [step]
  - [step]
  - [step]
**Stack:** [specific tech, one line]
**Time:** [realistic estimate]

---

Replace #N with the actual number (1, 2, 3...).
Be creative. Each project should feel chosen for Kevin specifically, not anyone with a keyboard."""

    result = claude_call(prompt, max_tokens=1800)
    print("═" * 64)
    print(result)
    print("═" * 64)
    print("\nRun `forge suggest` for a deeper dive on any one idea.\n")


def cmd_help():
    print("""
💡 forge — AI-powered project idea generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Watches what's trending on GitHub in your tech stack,
then asks Claude to suggest tailored weekend projects with plans.

USAGE
    forge <command> [options]

COMMANDS

  trending                   Show trending repos (last 7 days, all stack langs)
    --lang <language>          Filter to one language
    --days N                   Wider time window (default: 7)

  suggest                    One killer idea + full implementation plan (Claude)
    --lang <language>          Trend data for one language only
    --days N                   Wider trend window
    --raw                      Show raw trend data without Claude

  ideas                      3 tailored project ideas with plans (Claude)
    --count N                  Number of ideas, 1–7 (default: 3)
    --lang <language>          One language focus
    --days N                   Wider trend window
    --raw                      Show raw trend data

  help                       This help text

SETUP
    Requires ANTHROPIC_API_KEY in kegbot-claude/.env (or any .env in repo root).
    GITHUB_TOKEN is optional but highly recommended (raises rate limit 60→5000/hr).

LANGUAGES
    python, typescript, java, kotlin (Kevin's stack, all watched by default)
    Also works with: go, rust, javascript, and any GitHub-recognized language.

EXAMPLES
    forge trending
    forge trending --lang python --days 14
    forge suggest
    forge suggest --lang typescript --days 14
    forge ideas
    forge ideas --count 5 --days 14
    forge ideas --raw                       # see trend data only, no Claude

ALSO AVAILABLE AS
    kegbot forge                            # runs `forge ideas` from anywhere

Built by Claude (Cycle 8). Because "what should I build next?" deserves a real answer.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

COMMANDS = {
    "trending": cmd_trending,
    "suggest": cmd_suggest,
    "ideas": cmd_ideas,
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
        print(f"❓ Unknown command: '{command}'")
        print("Run `forge help` for usage.")
        sys.exit(1)

    COMMANDS[command](rest)


if __name__ == "__main__":
    main()
