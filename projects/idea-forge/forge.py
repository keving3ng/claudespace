#!/usr/bin/env python3
"""
forge — AI project idea generator

Watches what's trending on GitHub in your tech stack,
then asks Claude to synthesize weekend project ideas.

Usage:
    forge trending                         # trending repos (Python, TypeScript, Java)
    forge trending --lang typescript       # one language
    forge trending --period month          # last 30 days instead of 7
    forge ideas                            # trending → Claude → project ideas
    forge ideas --stack python,typescript  # specific stack
    forge ideas --period month             # broader trend window
    forge spark                            # one blazing creative idea, no trending context
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
DEFAULT_STACK = ["python", "typescript", "java"]

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


def gh_search(q: str, sort: str = "stars", per_page: int = 8) -> list[dict]:
    """Search GitHub repositories. Returns list of repo dicts."""
    params = urllib.parse.urlencode({
        "q": q,
        "sort": sort,
        "order": "desc",
        "per_page": str(per_page),
    })
    url = f"https://api.github.com/search/repositories?{params}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "idea-forge/1.0",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return data.get("items", [])
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        if e.code == 403:
            print(
                "⚠️  GitHub rate limit hit. Set GITHUB_TOKEN for higher limits.",
                file=sys.stderr,
            )
            return []
        if e.code == 422:
            return []  # no results or bad query
        print(f"⚠️  GitHub API {e.code}: {body[:150]}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"⚠️  Search failed: {e}", file=sys.stderr)
        return []


def fetch_trending(lang: str, period_days: int = 7, per_page: int = 6) -> list[dict]:
    """Fetch newly-created, star-gaining repos for a language."""
    since = (date.today() - timedelta(days=period_days)).isoformat()
    q = f"language:{lang} created:>{since} stars:>5"
    return gh_search(q, sort="stars", per_page=per_page)


# ─── Formatting ───────────────────────────────────────────────────────────────


def fmt_stars(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def fmt_repo(repo: dict) -> str:
    name = repo.get("full_name", "unknown")
    desc = (repo.get("description") or "no description")[:72]
    stars = fmt_stars(repo.get("stargazers_count", 0))
    topics = repo.get("topics", [])[:4]
    lang = repo.get("language") or ""

    topic_str = f"  [{', '.join(topics)}]" if topics else ""
    lang_str = f"  {lang}" if lang else ""
    return f"  ★{stars:>5}  {name}\n           {desc}{topic_str}{lang_str}"


# ─── Arg parsing helpers ──────────────────────────────────────────────────────


def parse_lang(args: list[str]) -> str | None:
    for flag in ("--lang", "-l"):
        if flag in args:
            idx = args.index(flag)
            if idx + 1 < len(args):
                return args[idx + 1].lower()
    return None


def parse_stack(args: list[str]) -> list[str]:
    if "--stack" in args:
        idx = args.index("--stack")
        if idx + 1 < len(args):
            return [s.strip().lower() for s in args[idx + 1].split(",") if s.strip()]
    return DEFAULT_STACK


def parse_period(args: list[str]) -> int:
    if "--period" in args:
        idx = args.index("--period")
        if idx + 1 < len(args):
            val = args[idx + 1].lower()
            if val == "month":
                return 30
            if val == "week":
                return 7
            try:
                return int(val)
            except ValueError:
                pass
    return 7


# ─── Commands ─────────────────────────────────────────────────────────────────


def cmd_trending(args: list[str]):
    """Show trending repos in Kevin's stack (or a specific language)."""
    lang = parse_lang(args)
    period = parse_period(args)
    langs = [lang] if lang else DEFAULT_STACK

    period_label = f"last {period} days"
    print(f"🔥 forge trending — {period_label}\n")

    for language in langs:
        bar = "─" * max(0, 48 - len(language))
        print(f"── {language.title()} {bar}")
        repos = fetch_trending(language, period_days=period, per_page=6)
        if not repos:
            print(
                f"  (no trending {language} repos found "
                f"— try --period month or add GITHUB_TOKEN)"
            )
        else:
            for repo in repos:
                print(fmt_repo(repo))
        print()

    print("─" * 52)
    print("Run `forge ideas` to generate project ideas from these trends.")
    print()


def cmd_ideas(args: list[str]):
    """Fetch trending repos → Claude → weekend project ideas."""
    stack = parse_stack(args)
    period = parse_period(args)
    raw = "--raw" in args

    period_label = f"last {period} days"
    print(f"💡 forge ideas — {stack} / {period_label}\n")

    # Step 1: fetch trending per language
    print("[github] Fetching trending repos...")
    all_repos: dict[str, list[dict]] = {}
    for lang in stack:
        repos = fetch_trending(lang, period_days=period, per_page=5)
        if repos:
            all_repos[lang] = repos

    if not all_repos:
        print(
            "⚠️  No trending repos found. Try --period month or check your connection."
        )
        print("Falling back to `forge spark` — pure creative generation.\n")
        cmd_spark(args)
        return

    # Step 2: build compact trending summary
    summary_lines = []
    for lang, repos in all_repos.items():
        summary_lines.append(f"\n### {lang.title()} — {period_label}")
        for repo in repos:
            name = repo.get("full_name", "")
            desc = (repo.get("description") or "").strip()
            stars = repo.get("stargazers_count", 0)
            topics = ", ".join(repo.get("topics", [])[:4])
            line = f"- {name} (★{fmt_stars(stars)})"
            if desc:
                line += f" — {desc[:80]}"
            if topics:
                line += f" [{topics}]"
            summary_lines.append(line)

    trending_text = "\n".join(summary_lines)

    if raw:
        print("── Trending Repos ─────────────────────────────────────")
        print(trending_text)
        print()
        print("(Run without --raw to generate ideas via Claude.)")
        return

    if not ANTHROPIC_API_KEY:
        print("⚠️  ANTHROPIC_API_KEY not set. Here's what's trending:\n")
        print(trending_text)
        print("\nSet ANTHROPIC_API_KEY to get Claude-generated project ideas.")
        return

    # Step 3: ask Claude for project ideas
    today = date.today().strftime("%B %d, %Y")
    prompt = f"""Today is {today}. You are idea-forge, a project idea generator for Kevin Geng.

## Kevin's Profile
- Full-stack engineer at Faire in Toronto
- Stack: React, TypeScript, Java/Kotlin, Python
- Active: matchamap.club (matcha cafe finder), claudespace (autonomous AI build lab), kegbot (personal CLI)
- Interests: personal automation, Discord bots, cooking/recipes, maps & place data, ML/AI, developer tools
- Weekend project sweet spot: 200–500 lines, zero/minimal dependencies, solves a real personal itch
- Taste: focused, opinionated, tools with personality

## Trending on GitHub — {period_label}
{trending_text}

## Task
Generate exactly 3 weekend project ideas for Kevin. Each should:
1. Be **inspired by** (not a clone of) the trending repos above — same problem space, adjacent tech, or a personal twist
2. Be **buildable in a weekend** — not a startup, not a thesis project
3. Feel **Kevin-specific** — not something you'd suggest to any developer

For each idea use this format:
**[Name]**
[One-liner pitch — max 15 words]
*Why it fits Kevin:* [one sentence]
**Build it:**
• [concrete step 1]
• [concrete step 2]
• [concrete step 3]

Total under 450 words. Be specific. Be interesting. Don't suggest anything he's already built
(kegbot, recipe-ai, matchamap tools, dev-insights heatmap/streak, discord bridge)."""

    print("[claude] Thinking up ideas...")
    result = claude_call(prompt, max_tokens=900)

    print("\n" + "═" * 60)
    print(result)
    print("═" * 60 + "\n")
    print("✨ Run `forge spark` for a completely left-field creative idea.")
    print("🔥 Run `forge trending` to browse the repos that inspired this.")
    print()


def cmd_spark(args: list[str]):
    """One blazing creative idea — no trending context, pure imagination + Kevin's profile."""
    print("✨ forge spark — one unexpected creative idea\n")

    if not ANTHROPIC_API_KEY:
        print("⚠️  ANTHROPIC_API_KEY not set. Here are some sparks anyway:\n")
        sparks = [
            "Terminal Pomodoro with GitHub commit streak integration",
            "Recipe-to-grocery-list Discord bot (reads your pantry.json)",
            "Live matchamap.club quality score dashboard (terminal)",
            "kegbot status page — a public badge for your current streak",
            "ASCII cookbook — render recipe-ai suggestions as terminal art",
        ]
        for spark in sparks:
            print(f"  • {spark}")
        print("\n(Set ANTHROPIC_API_KEY to get something actually tailored to Kevin.)")
        return

    today = date.today().strftime("%B %d, %Y")
    prompt = f"""Today is {today}. You are idea-forge running in spark mode — pure creative generation.

Kevin is a full-stack engineer in Toronto. He loves: matcha, cooking, maps, terminal tools, Discord bots, personal automation, side projects with personality and taste.

He has already built: matchamap cafe data tools, kegbot CLI assistant, recipe-ai (ingredients → recipes, pantry, meal planning, history), dev-insights (GitHub heatmap + streak tracker), discord bridge bot, recipe history log with ratings.

Your job: Generate ONE weekend project idea that would genuinely surprise and delight him.

Rules:
- Must be something he hasn't built yet (see above)
- Must be unexpected — not "extend kegbot" or "add a CRUD endpoint"
- Must have personality and a little bit of quirk
- Must be realistically buildable in 1–2 days
- Can be weird, niche, or a little absurd — that's a feature not a bug

Format exactly:
**[Project Name]**
[One-line pitch]

*Why it's perfect for Kevin:* [one sentence]

**Build it in a weekend:**
• [concrete step 1]
• [concrete step 2]
• [concrete step 3]

**The spark:** [one thing that makes this different from every other side project]

Under 160 words. Be genuinely creative. Surprise me."""

    result = claude_call(prompt, max_tokens=400)
    print("─" * 52)
    print(result)
    print("─" * 52 + "\n")
    print("💡 Run `forge ideas` for multiple ideas grounded in trending repos.")
    print()


# ─── Claude API ───────────────────────────────────────────────────────────────


def claude_call(prompt: str, max_tokens: int = 600) -> str:
    """Thin Claude API wrapper."""
    if not ANTHROPIC_API_KEY:
        return "⚠️  ANTHROPIC_API_KEY not set."

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


# ─── Help ─────────────────────────────────────────────────────────────────────


def cmd_help():
    print("""
✨ forge — AI project idea generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Watches what's trending on GitHub in your stack.
Asks Claude to synthesize weekend project ideas tailored to you.

USAGE
    forge <command> [options]

COMMANDS

  trending                   Show trending repos in Kevin's stack
    --lang LANGUAGE            One language only (python, typescript, java, go, ...)
    --period week|month        Time window (default: week)

  ideas                      Fetch trending → Claude → 3 project ideas
    --stack python,typescript  Languages to scan (default: python,typescript,java)
    --period week|month        Trend window (default: week)
    --raw                      Show trending data without Claude (debug mode)

  spark                      One creative idea — no trending context needed
                               Pure Claude imagination + Kevin's profile

  help                       Show this help

SETUP
  Set ANTHROPIC_API_KEY in projects/kegbot-claude/.env (or root .env).
  Optionally set GITHUB_TOKEN for higher rate limits on trending searches.

EXAMPLES
    forge trending
    forge trending --lang go --period month
    forge ideas
    forge ideas --stack python,typescript --period month
    forge spark

ALSO
    kegbot forge trending
    kegbot forge ideas
    kegbot forge spark

Built by Claude (Cycle 8). Watching the garden to see what's growing.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

COMMANDS = {
    "trending": cmd_trending,
    "ideas": cmd_ideas,
    "spark": cmd_spark,
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
