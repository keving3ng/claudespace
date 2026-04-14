#!/usr/bin/env python3
"""
idea-forge — AI project idea generator
Watches trending GitHub repos in your stack, suggests weekend projects.

Usage:
    idea trending [--lang python|typescript|go] [--days N]
    idea suggest  [--lang LANG] [--days N]
    idea inspire  <topic>
    idea save     <title> [--note TEXT] [--status STATUS]
    idea done     <id>
    idea list     [--status backlog|in-progress|done|dropped]
    idea help
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

IDEA_DIR = Path(__file__).parent
REPO_ROOT = IDEA_DIR.parent.parent
IDEAS_FILE = IDEA_DIR / "ideas.json"

KEVIN_LANGUAGES = ["python", "typescript", "go"]

KEVIN_PROFILE = """Kevin Geng is a full-stack software developer at Faire in Toronto.
Active projects: matchamap.club (opinionated matcha cafe finder), kegbot (personal CLI assistant),
recipe-ai (cooking assistant), dev-insights (GitHub activity dashboard).
Stack: Python, TypeScript, Go. Values: tools with personality, zero-dependency CLIs,
things that are personal not generic, matcha tea, home cooking, minimal footprint.
Weekend project ceiling: 1–3 days solo."""

# ─── Env ──────────────────────────────────────────────────────────────────────


def load_env():
    for env_path in [
        IDEA_DIR / ".env",
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

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
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
        body = e.read().decode("utf-8", errors="replace")
        if e.code == 403 and "rate limit" in body.lower():
            print(
                "⚠️  GitHub API rate limit hit. Set GITHUB_TOKEN for higher limits.",
                file=sys.stderr,
            )
        elif e.code != 404:
            print(f"⚠️  GitHub API error {e.code}: {body[:120]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"⚠️  Request failed: {e}", file=sys.stderr)
        return None


def fetch_trending_repos(lang: str, days: int = 30, count: int = 8) -> list[dict]:
    """Fetch recently-created repos gaining traction in a given language."""
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    query = urllib.parse.quote(f"language:{lang} created:>{since} stars:>10")
    url = (
        f"https://api.github.com/search/repositories"
        f"?q={query}&sort=stars&order=desc&per_page={count}"
    )
    data = _github_request(url)
    if not data or not isinstance(data, dict):
        return []
    return data.get("items", [])


def format_repo_summary(repo: dict, lang: str) -> dict:
    return {
        "name": repo.get("full_name", ""),
        "description": (repo.get("description") or "")[:100],
        "stars": repo.get("stargazers_count", 0),
        "topics": repo.get("topics", [])[:5],
        "language": lang,
        "url": repo.get("html_url", ""),
    }


# ─── Claude API ───────────────────────────────────────────────────────────────


def claude_call(prompt: str, max_tokens: int = 1200) -> str:
    if not API_KEY:
        return "⚠️  ANTHROPIC_API_KEY not set. Add it to .env or set in environment."

    payload = json.dumps(
        {
            "model": "claude-opus-4-6",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": API_KEY,
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
    if IDEAS_FILE.exists():
        try:
            return json.loads(IDEAS_FILE.read_text())
        except Exception:
            return []
    return []


def save_ideas_file(ideas: list[dict]):
    IDEAS_FILE.write_text(json.dumps(ideas, indent=2, ensure_ascii=False))


# ─── Arg helpers ──────────────────────────────────────────────────────────────


def get_arg(args: list[str], flag: str) -> str | None:
    if flag in args:
        idx = args.index(flag)
        if idx + 1 < len(args):
            return args[idx + 1]
    return None


# ─── Commands ─────────────────────────────────────────────────────────────────


def cmd_trending(args: list[str]):
    lang_filter = get_arg(args, "--lang")
    days = int(get_arg(args, "--days") or 30)
    langs = [lang_filter] if lang_filter else KEVIN_LANGUAGES

    print(f"\n🔭 idea-forge trending — new repos from the last {days} days\n")

    for lang in langs:
        print("─" * 54)
        print(f"  {lang.title()}  (sorted by stars)")
        print("─" * 54)

        repos = fetch_trending_repos(lang, days=days, count=8)
        if not repos:
            print(
                f"  No results. (rate limit? try --lang {lang} with GITHUB_TOKEN set)\n"
            )
            continue

        for i, repo in enumerate(repos, 1):
            r = format_repo_summary(repo, lang)
            desc = r["description"] or "(no description)"
            topics_str = (
                f"  [{', '.join(r['topics'][:3])}]" if r["topics"] else ""
            )
            print(f"  {i:2}. ★ {r['stars']:>5}  {r['name']}")
            print(f"        {desc[:72]}")
            if topics_str:
                print(f"       {topics_str}")
        print()


def cmd_suggest(args: list[str]):
    lang_filter = get_arg(args, "--lang")
    days = int(get_arg(args, "--days") or 45)
    langs = [lang_filter] if lang_filter else KEVIN_LANGUAGES

    print("\n💡 idea-forge suggest — fetching trending repos...\n")

    all_repos: list[dict] = []
    for lang in langs:
        repos = fetch_trending_repos(lang, days=days, count=6)
        for repo in repos:
            all_repos.append(format_repo_summary(repo, lang))

    if not all_repos:
        print(
            "Could not fetch trending data.\n"
            "Try setting GITHUB_TOKEN, or use `idea inspire <topic>` for offline mode."
        )
        return

    repo_lines = "\n".join(
        f"- [{r['language']}] {r['name']} (★{r['stars']}): {r['description']}"
        + (f" [topics: {', '.join(r['topics'][:3])}]" if r["topics"] else "")
        for r in all_repos[:15]
    )

    prompt = f"""You're looking at recently-trending GitHub repos in Kevin's tech stack.
Your job: suggest 3 weekend project ideas he could actually build and ship.

Kevin's profile:
{KEVIN_PROFILE}

Trending repos right now:
{repo_lines}

Rules for your suggestions:
- Each idea should be buildable solo in 1–3 days
- Should be genuinely useful or delightful to Kevin personally — not generic portfolio pieces
- Inspired by (but distinct from) the trending repos — remix, don't copy
- Include: title, one-line pitch, rough stack, first 3 steps
- Be specific ("a CLI that does X" beats "a tool for Y")
- One idea should be weird or unexpected — Kevin likes surprises

Format each idea as:
### [Title]
**Pitch:** one line, punchy
**Stack:** language + key tools
**Build plan:**
  1. ...
  2. ...
  3. ...
**Why Kevin:** one sentence on why this fits him specifically
"""

    print("[claude] Generating project ideas from what's trending...\n")
    result = claude_call(prompt, max_tokens=1500)
    print("─" * 60)
    print(result)
    print("─" * 60)
    print("\n💾 Like an idea? Run `idea save \"<title>\"` to stash it in your backlog.")


def cmd_inspire(args: list[str]):
    """Wild card: ideas on any topic, no trending data needed."""
    topic = " ".join(a for a in args if not a.startswith("--")) or "something Kevin would love"

    prompt = f"""Give Kevin 2 concrete weekend project ideas about: {topic}

Kevin's profile:
{KEVIN_PROFILE}

Rules:
- Weekend-sized (1–3 days solo)
- Specific, not vague
- One idea should be unexpected or surprising
- Include: title, one-line pitch, stack, 3-step build plan

Format:
### [Title]
**Pitch:** ...
**Stack:** ...
**Build plan:**
  1. ...
  2. ...
  3. ...
**Twist:** what makes this one surprising or different
"""

    print(f'\n✨ idea-forge inspire — topic: "{topic}"\n')
    result = claude_call(prompt, max_tokens=900)
    print("─" * 60)
    print(result)
    print("─" * 60)
    print("\n💾 `idea save \"<title>\"` to keep one.")


def cmd_save(args: list[str]):
    if not args or args[0].startswith("--"):
        print("Usage: idea save <title> [--note TEXT] [--status STATUS]")
        return

    title = args[0]
    note = get_arg(args, "--note") or get_arg(args, "--idea") or ""
    status = get_arg(args, "--status") or "backlog"

    ideas = load_ideas()
    entry = {
        "id": len(ideas) + 1,
        "title": title,
        "note": note,
        "status": status,
        "saved_at": datetime.now().strftime("%Y-%m-%d"),
    }
    ideas.append(entry)
    save_ideas_file(ideas)
    print(f"✅ Saved [{entry['id']}]: {title}  (status: {status})")


def cmd_done(args: list[str]):
    """Mark an idea as done by ID."""
    if not args:
        print("Usage: idea done <id>")
        return
    try:
        idea_id = int(args[0])
    except ValueError:
        print("Error: id must be a number")
        return

    ideas = load_ideas()
    for idea in ideas:
        if idea.get("id") == idea_id:
            idea["status"] = "done"
            idea["done_at"] = datetime.now().strftime("%Y-%m-%d")
            save_ideas_file(ideas)
            print(f"✅ Marked [{idea_id}]: {idea['title']} → done")
            return
    print(f"No idea with id {idea_id} found. Run `idea list` to see ids.")


def cmd_list(args: list[str]):
    status_filter = get_arg(args, "--status")
    ideas = load_ideas()

    if not ideas:
        print("\nNo saved ideas yet.")
        print(
            "Run `idea suggest` to get inspired, "
            "then `idea save \"<title>\"` to keep the good ones."
        )
        return

    filtered = (
        [i for i in ideas if i.get("status") == status_filter]
        if status_filter
        else ideas
    )

    icons = {"backlog": "○", "in-progress": "◑", "done": "●", "dropped": "×"}

    label = f"status: {status_filter}" if status_filter else "all"
    print(f"\n{'─' * 56}")
    print(f"  Saved Ideas  ({len(filtered)} shown, {label})")
    print(f"{'─' * 56}")

    for idea in filtered:
        icon = icons.get(idea.get("status", "backlog"), "○")
        date_str = idea.get("saved_at", "?")
        done_str = f"  done: {idea['done_at']}" if idea.get("done_at") else ""
        print(f"  {icon} [{idea['id']:>2}] {idea['title']}")
        if idea.get("note"):
            print(f"         {idea['note'][:72]}")
        print(f"         {date_str}  ·  {idea.get('status', 'backlog')}{done_str}")
    print()


# ─── Help ─────────────────────────────────────────────────────────────────────

HELP = """
idea-forge — AI project idea generator
Watches what's trending in your stack, suggests weekend projects.

USAGE
    idea <command> [options]

COMMANDS

  trending [--lang LANG] [--days N]
      Show trending GitHub repos (created in last N days, default 30)
      Langs: python, typescript, go (default: all three)

  suggest [--lang LANG] [--days N]
      Claude-powered weekend project ideas based on trending repos

  inspire <topic>
      Wild card: ideas on any topic, no GitHub data needed
      e.g.: idea inspire "matcha + machine learning"
            idea inspire "something Kevin would love at 2am"

  save <title> [--note TEXT] [--status STATUS]
      Save an idea to your backlog (stored in ideas.json)

  done <id>
      Mark an idea as done

  list [--status backlog|in-progress|done|dropped]
      Show saved ideas (default: all)

  help
      Show this text

ENVIRONMENT
  ANTHROPIC_API_KEY   Required for suggest and inspire
  GITHUB_TOKEN        Optional — raises GitHub API rate limit (60 → 5000/hr)

EXAMPLES
  idea trending
  idea trending --lang go --days 14
  idea suggest
  idea inspire "matcha + technology"
  idea save "Matcha Strain Classifier" --note "train a CNN on matcha grades"
  idea list
  idea done 3

Built by Claude (Cycle 8). Ideas are free. Shipping is the hard part.
"""

# ─── Main ─────────────────────────────────────────────────────────────────────

COMMANDS = {
    "trending": cmd_trending,
    "suggest": cmd_suggest,
    "inspire": cmd_inspire,
    "save": cmd_save,
    "done": cmd_done,
    "list": cmd_list,
    "help": lambda _: print(HELP),
    "--help": lambda _: print(HELP),
    "-h": lambda _: print(HELP),
}


def main():
    argv = sys.argv[1:]
    if not argv or argv[0] in ("help", "--help", "-h"):
        print(HELP)
        return

    cmd = argv[0]
    if cmd not in COMMANDS:
        print(f"❓ Unknown command: {cmd}")
        print("Run `idea help` for available commands.")
        sys.exit(1)

    COMMANDS[cmd](argv[1:])


if __name__ == "__main__":
    main()
