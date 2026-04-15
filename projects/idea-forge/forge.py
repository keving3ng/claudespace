#!/usr/bin/env python3
"""
idea-forge — AI-powered weekend project idea generator

Watches what's trending in your tech stack and asks Claude to suggest
projects you'd actually want to build — tailored to your interests,
with your existing tools as building blocks.

Zero dependencies beyond stdlib. Uses GitHub Search API + Anthropic API.

Usage:
    forge trending              # trending repos in Kevin's stack (py + ts)
    forge trending python       # specific language
    forge trending typescript
    forge suggest               # AI-generated project ideas (requires ANTHROPIC_API_KEY)
    forge suggest --raw         # show trending context without calling Claude
    forge list                  # list saved ideas
    forge save "Project Name"   # note a project idea manually
    forge help
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────

FORGE_DIR = Path(__file__).parent
REPO_ROOT = FORGE_DIR.parent.parent
IDEAS_FILE = FORGE_DIR / "ideas.json"

# Languages to watch (Kevin's stack)
DEFAULT_LANGS = ["python", "typescript"]

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


# ─── GitHub API ───────────────────────────────────────────────────────────────


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
        if e.code == 422:
            # Validation error — probably a query issue
            body = e.read().decode("utf-8", errors="replace")
            print(f"⚠  GitHub search error: {body[:200]}", file=sys.stderr)
            return None
        body = e.read().decode("utf-8", errors="replace")
        print(f"⚠  GitHub API error {e.code}: {body[:200]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"⚠  Request failed: {e}", file=sys.stderr)
        return None


def fetch_trending(lang: str, days: int = 7, count: int = 8) -> list[dict]:
    """
    Fetch trending repos for a language using GitHub Search API.
    "Trending" = recently pushed, sorted by stars, with minimum star threshold.
    Returns list of simplified repo dicts.
    """
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    query = f"language:{lang} pushed:>{cutoff} stars:>50"
    params = urllib.parse.urlencode({
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": count,
    })
    url = f"https://api.github.com/search/repositories?{params}"
    data = _github_request(url)

    if not data or not isinstance(data, dict):
        return []

    repos = data.get("items", [])
    simplified = []
    for r in repos:
        simplified.append({
            "name": r.get("full_name", ""),
            "description": (r.get("description") or "")[:120],
            "stars": r.get("stargazers_count", 0),
            "language": r.get("language") or lang,
            "topics": r.get("topics", [])[:5],
            "url": r.get("html_url", ""),
            "pushed_at": r.get("pushed_at", "")[:10],
        })

    return simplified


# ─── Kevin's profile (used in prompts) ───────────────────────────────────────


KEVIN_PROFILE = """
Kevin Geng (keving3ng) — full-stack software engineer at Faire, based in Toronto.

Stack: React, TypeScript, Java/Kotlin/Spring Boot, Python, AWS

Active projects:
- matchamap.club — opinionated matcha cafe finder (map + curated data)
- kegbot — personal AI assistant CLI: daily briefings, weather, PR digest
- claudespace — autonomous AI build lab (Claude runs nightly, building tools for Kevin)
- recipe-ai — cooking assistant with pantry tracking, meal planning
- dev-insights — terminal GitHub contribution heatmap + streak tracker

Interests: matcha, cooking, Discord bots, personal automation, terminal tools,
           maps + location data, ML/AI experiments, transit apps, board games

Design sensibility: pragmatic but fun. Terminal > web when possible. Zero deps preferred.
He appreciates tools that do one thing well and have a bit of personality.

The claudespace autonomous AI (that's me) has been building tools for Kevin across 7+ cycles.
I know his stack well. When suggesting claudespace improvements, I can get specific.
"""


# ─── Claude API ───────────────────────────────────────────────────────────────


def claude_call(prompt: str, max_tokens: int = 1000) -> str:
    """Call Anthropic API with a prompt. Returns text or error string."""
    if not ANTHROPIC_API_KEY:
        return "⚠  ANTHROPIC_API_KEY not set — run with --raw to see trending data without Claude."

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


# ─── Ideas persistence ────────────────────────────────────────────────────────


def load_ideas() -> list[dict]:
    if not IDEAS_FILE.exists():
        return []
    try:
        return json.loads(IDEAS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def save_ideas(ideas: list[dict]):
    IDEAS_FILE.write_text(json.dumps(ideas, indent=2))


def append_idea(title: str, pitch: str = "", full_text: str = "", source: str = "manual"):
    ideas = load_ideas()
    idea = {
        "id": f"{date.today().isoformat()}-{len(ideas):03d}",
        "title": title,
        "pitch": pitch,
        "source": source,
        "generated_at": datetime.now().isoformat()[:16],
        "full_text": full_text,
    }
    ideas.append(idea)
    save_ideas(ideas)
    return idea


# ─── Formatting helpers ───────────────────────────────────────────────────────


def format_repos_table(repos: list[dict], lang: str) -> str:
    """Render a trending repos list as a compact table."""
    if not repos:
        return f"  (no results for {lang})"

    lines = []
    for i, r in enumerate(repos, 1):
        stars_k = f"{r['stars'] // 1000}k" if r['stars'] >= 1000 else str(r['stars'])
        desc = r["description"][:60] if r["description"] else "—"
        topics = "  #" + " #".join(r["topics"][:3]) if r["topics"] else ""
        lines.append(f"  {i:>2}. ⭐{stars_k:>5}  {r['name']:<40}  {desc}{topics}")
    return "\n".join(lines)


def format_trending_context(repos_by_lang: dict[str, list[dict]]) -> str:
    """Format trending data as a Claude-readable context block."""
    sections = []
    for lang, repos in repos_by_lang.items():
        if not repos:
            sections.append(f"### Trending {lang.title()} repos (none found this week)\n")
            continue
        lines = [f"### Trending {lang.title()} repos (last 7 days, by stars)\n"]
        for r in repos:
            topics = ", ".join(r["topics"]) if r["topics"] else "—"
            lines.append(f"- **{r['name']}** (⭐{r['stars']:,})")
            lines.append(f"  {r['description'] or 'No description.'}")
            lines.append(f"  Topics: {topics}")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


# ─── Commands ─────────────────────────────────────────────────────────────────


def cmd_trending(args: list[str]):
    """Show trending GitHub repos for Kevin's stack (or a specific language)."""
    # Determine which language(s) to show
    known_langs = {"python", "typescript", "go", "rust", "java", "kotlin", "javascript"}
    requested = [a.lower() for a in args if not a.startswith("-")]
    langs = [l for l in requested if l in known_langs]
    if not langs:
        langs = DEFAULT_LANGS

    days = 7
    if "--days" in args:
        idx = args.index("--days")
        if idx + 1 < len(args):
            try:
                days = int(args[idx + 1])
            except ValueError:
                pass

    print(f"🔭 idea-forge — trending repos (last {days} days)\n")

    for lang in langs:
        print(f"━━ {lang.title()} {'━' * (44 - len(lang))}")
        repos = fetch_trending(lang, days=days)
        print(format_repos_table(repos, lang))
        print()


def cmd_suggest(args: list[str]):
    """Generate AI-powered project ideas using trending repos as inspiration."""
    raw = "--raw" in args
    save = "--save" in args  # auto-save generated ideas to ideas.json

    # Which languages to fetch
    known_langs = {"python", "typescript", "go", "rust", "java", "kotlin"}
    requested = [a.lower() for a in args if not a.startswith("-")]
    langs = [l for l in requested if l in known_langs] or DEFAULT_LANGS

    days = 7
    if "--days" in args:
        idx = args.index("--days")
        if idx + 1 < len(args):
            try:
                days = int(args[idx + 1])
            except ValueError:
                pass

    print("💡 idea-forge — generating project ideas\n")
    print(f"   Fetching trending repos for: {', '.join(langs)}...")

    repos_by_lang = {}
    for lang in langs:
        repos = fetch_trending(lang, days=days)
        repos_by_lang[lang] = repos
        count = len(repos)
        print(f"   {lang.title()}: {count} repos found")

    print()

    trending_context = format_trending_context(repos_by_lang)

    if raw:
        print("─── Trending Context (--raw mode, no Claude) ─────────────────")
        print(trending_context)
        print("──────────────────────────────────────────────────────────────")
        return

    today = date.today().strftime("%B %d, %Y")

    prompt = f"""You are idea-forge, a project idea generator for a specific developer.

Today is {today}. Here's everything you know about Kevin:
{KEVIN_PROFILE}

Here's what's trending on GitHub this week in his stack:
{trending_context}

Generate exactly 4 weekend project ideas tailored to Kevin. Each idea should:
- Be buildable in 1-2 days by a skilled developer
- Connect to Kevin's actual interests or existing projects (not generic)
- Use his stack (TypeScript, Python, React, or terminal tools)
- Have a name with personality — not "X-Tool" or "Y-Bot"

Format each idea exactly like this (4 ideas, no extra prose before/after):

## 🛠 [Project Name]
**Pitch:** One punchy sentence — what it does and why it's interesting.
**Stack:** The specific tech to reach for.
**The fun part:** What would make building this genuinely enjoyable.
**Inspired by:** Which trending repo(s) connect to this, if any. Or "Kevin's existing work" if it builds on matchamap/kegbot/recipe-ai/etc.

---

Rules:
- One of the four ideas must be a claudespace improvement — something to make the autonomous build cycles smarter, more expressive, or more useful to Kevin.
- One idea must connect to his matcha/cooking/food interests (matchamap or recipe-ai adjacent).
- Be opinionated. If an idea is a stretch, say so briefly in "the fun part."
- No portfolio sites, no generic dashboards, no CRUD apps.
"""

    print("[claude] Thinking about what to build next...\n")
    result = claude_call(prompt, max_tokens=1200)

    print("─" * 64)
    print(result)
    print("─" * 64 + "\n")

    if save:
        # Parse out project names from ## 🛠 headers and save them
        import re
        titles = re.findall(r"^## 🛠 (.+)$", result, re.MULTILINE)
        for title in titles:
            append_idea(title.strip(), source="forge-suggest", full_text=result)
        if titles:
            print(f"✅ Saved {len(titles)} idea(s) to ideas.json")
    else:
        print("   Tip: run `forge suggest --save` to save these to ideas.json")


def cmd_list(args: list[str]):
    """List saved project ideas."""
    ideas = load_ideas()

    if not ideas:
        print("💡 No saved ideas yet. Run `forge suggest --save` to generate some.")
        return

    print(f"💡 idea-forge — {len(ideas)} saved idea(s)\n")
    for i, idea in enumerate(reversed(ideas), 1):
        title = idea.get("title", "Untitled")
        pitch = idea.get("pitch", "")
        source = idea.get("source", "manual")
        generated_at = idea.get("generated_at", "")[:10]
        source_label = "✨ AI" if source == "forge-suggest" else "📝 manual"

        print(f"  {i:>2}. {title}")
        if pitch:
            print(f"      {pitch}")
        print(f"      {source_label}  ·  {generated_at}")
        print()


def cmd_save(args: list[str]):
    """Manually save a project idea."""
    title_parts = [a for a in args if not a.startswith("-")]
    title = " ".join(title_parts).strip()

    if not title:
        print("Usage: forge save \"Project Name\"")
        print("       forge save My Idea Title")
        return

    idea = append_idea(title, source="manual")
    print(f"✅ Saved: \"{idea['title']}\" (id: {idea['id']})")


def cmd_help():
    print("""
💡 idea-forge — AI-powered project idea generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USAGE
    forge <command> [options]

COMMANDS

  trending [lang]            Trending repos in your stack (py + ts by default)
    python                     Python repos
    typescript                 TypeScript repos
    go                         Go repos
    --days N                   Look back N days (default: 7)

  suggest                    AI-generated project ideas (requires ANTHROPIC_API_KEY)
    python / typescript        Limit to specific language for inspiration
    --raw                      Show trending context without calling Claude
    --save                     Auto-save generated ideas to ideas.json
    --days N                   Trending window in days (default: 7)

  list                       List saved ideas

  save "Project Name"        Manually note a project idea

  help                       This help text

SETUP
    Needs ANTHROPIC_API_KEY in projects/kegbot-claude/.env or repo root .env.
    Optional: GITHUB_TOKEN for higher GitHub API rate limits (60 → 5000/hr).

EXAMPLES
    forge trending
    forge trending go
    forge suggest
    forge suggest --raw
    forge suggest --save
    forge list

PHILOSOPHY
    This tool is intentionally Kevin-specific. The suggestions it generates
    connect to his actual stack, existing projects, and genuine interests —
    not generic dev fodder. The Claude prompt is baked in, not configurable.

    One rule: at least one idea per session must be a claudespace improvement.
    (Because the builder should also build on itself.)

Built by Claude (Cycle 8). The meta-recursive one.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

COMMANDS = {
    "trending": cmd_trending,
    "suggest": cmd_suggest,
    "list": cmd_list,
    "save": cmd_save,
    "help": cmd_help,
    "--help": cmd_help,
    "-h": cmd_help,
}


def main():
    argv = sys.argv[1:]

    if not argv:
        # Default: run suggest in raw mode to show trending without requiring API key
        cmd_trending([])
        print("Run `forge suggest` to get AI-powered project ideas.\n")
        return

    command = argv[0]
    rest = argv[1:]

    if command not in COMMANDS:
        print(f"❓ Unknown command: {command}")
        print("Run `forge help` for available commands.")
        sys.exit(1)

    handler = COMMANDS[command]
    if command in {"help", "--help", "-h"}:
        handler()
    else:
        handler(rest)


if __name__ == "__main__":
    main()
