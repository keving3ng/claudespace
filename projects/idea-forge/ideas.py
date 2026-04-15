#!/usr/bin/env python3
"""
idea-forge — AI project idea generator tailored to Kevin Geng

Watches trending GitHub repos in Kevin's stack and generates personalized
weekend project ideas using Claude. Because the best project ideas come from
knowing what's already been built and what's missing.

Usage:
    python ideas.py                   # Generate 5 fresh ideas from trending repos
    python ideas.py --count N         # How many ideas (default: 5, max: 10)
    python ideas.py --stack python    # Ideas focused on a specific language
    python ideas.py --stack ts        # TypeScript shorthand
    python ideas.py --raw             # Show trending repos without AI synthesis
    python ideas.py --saved           # Browse previously saved ideas
    python ideas.py --saved --index N # Read a specific saved session
    python ideas.py help
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent.parent
IDEAS_DIR = Path(__file__).parent
IDEAS_JSON = IDEAS_DIR / "saved_ideas.json"

DEFAULT_STACKS = ["typescript", "python", "java", "kotlin"]

STACK_ALIASES = {
    "ts": "typescript",
    "js": "javascript",
    "py": "python",
    "kt": "kotlin",
    "go": "go",
}

KEVIN_PROFILE = """
Kevin Geng (@keving3ng) — full-stack engineer at Faire in Toronto.
Stack: React, TypeScript, Java/Kotlin/Spring Boot, Python, AWS.

Active projects:
- matchamap.club — opinionated matcha cafe finder (geolocation, ranking, curation)
- claudespace — autonomous Claude AI build lab (this tool lives here)
- kegbot — Python personal assistant (daily briefings, weather, GitHub activity)
- cookbook — recipe collection; interested in recipe-ai / meal planning tools
- kgeng.dev — personal site

Interests: cooking & food, ML/AI (face recognition, embeddings), Discord bots,
personal automation, maps & place data, gaming (board games, blackjack),
personal finance data aggregation, transit & city data, teaching/workshops.

Previous work: facial recognition (TensorFlow/Keras), Discord bots, financial
data aggregation from Robinhood/etc, React projects, PostgREST APIs.

Kevin likes: tools that are immediately useful to him specifically, tools with
personality, things that automate annoying tasks, offline-capable tools,
building "just for him" before going broader. He does NOT want generic CRUD apps
or yet another todo list (unless it has a genuinely clever angle).

His tools already include: matcha cafe search/ranking, morning briefings,
PR/issue digest, weather, smart to-do from AI, recipe suggestions + pantry +
meal planning, GitHub heatmap + streak tracking.
"""

# ─── Env ──────────────────────────────────────────────────────────────────────


def load_env():
    for env_path in [
        IDEAS_DIR / ".env",
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
        if e.code == 422:
            # Validation failed — search query issue, not a hard error
            return None
        if e.code == 403:
            print(f"⚠️  GitHub rate limit hit for {url[:60]}. Set GITHUB_TOKEN for 5× more.", file=sys.stderr)
            return None
        body = e.read().decode("utf-8", errors="replace")
        print(f"⚠️  GitHub API error {e.code}: {body[:200]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"⚠️  Request failed: {e}", file=sys.stderr)
        return None


def search_trending_repos(language: str, days_back: int = 30, per_page: int = 5) -> list[dict]:
    """
    Search for recently-created, highly-starred repos in a language.
    Returns a list of repo dicts with name, description, stars, topics, url.
    """
    since_date = (date.today() - timedelta(days=days_back)).isoformat()

    # Resolve aliases
    lang = STACK_ALIASES.get(language.lower(), language.lower())

    # Craft a search query: language, recent creation, at least some traction
    query = f"language:{lang} created:>{since_date} stars:>5"
    encoded_q = urllib.parse.quote(query)
    url = (
        f"https://api.github.com/search/repositories"
        f"?q={encoded_q}&sort=stars&order=desc&per_page={per_page}"
    )

    result = _github_request(url)
    if not result or "items" not in result:
        return []

    repos = []
    for r in result["items"][:per_page]:
        repos.append({
            "name": r.get("full_name", ""),
            "description": (r.get("description") or "")[:160],
            "stars": r.get("stargazers_count", 0),
            "language": r.get("language") or lang,
            "topics": r.get("topics", [])[:6],
            "url": r.get("html_url", ""),
            "created_at": r.get("created_at", "")[:10],
        })

    return repos


def fetch_trending_across_stack(stacks: list[str], per_language: int = 4) -> list[dict]:
    """Fetch trending repos across multiple languages, deduplicating by repo name."""
    all_repos = []
    seen: set[str] = set()

    for lang in stacks:
        print(f"  🔍 {lang:<14}", end="", flush=True)
        repos = search_trending_repos(lang, days_back=30, per_page=per_language)
        new = [r for r in repos if r["name"] not in seen]
        seen.update(r["name"] for r in new)
        all_repos.extend(new)
        if new:
            top = new[0]
            print(f"→ {len(new)} repos  (top: ⭐{top['stars']:,} {top['name'].split('/')[-1]})")
        else:
            print("→ 0 repos")

    return all_repos


# ─── Claude integration ───────────────────────────────────────────────────────


def claude_call(prompt: str, max_tokens: int = 2000) -> str:
    if not ANTHROPIC_API_KEY:
        return "⚠️  ANTHROPIC_API_KEY not set — can't generate ideas."

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
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
            return result["content"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return f"[Claude API error {e.code}: {body[:200]}]"
    except Exception as e:
        return f"[Claude API error: {e}]"


def generate_ideas(trending_repos: list[dict], n_ideas: int = 5) -> str:
    """
    Ask Claude to generate project ideas inspired by trending repos,
    tailored to Kevin's profile.
    """
    # Format the trending repos for the prompt
    repos_text = ""
    for i, r in enumerate(trending_repos, 1):
        topics_str = ", ".join(r["topics"]) if r["topics"] else "—"
        repos_text += (
            f"{i}. **{r['name']}** ({r['language']}, ⭐{r['stars']:,})  [{r['created_at']}]\n"
            f"   {r['description'] or '(no description)'}\n"
            f"   Topics: {topics_str}\n\n"
        )

    today = date.today().strftime("%B %d, %Y")

    prompt = f"""You are idea-forge, a project idea generator running inside Kevin's autonomous AI build lab (claudespace).

Today is {today}. You've just scanned GitHub's trending repositories and found these new projects gaining traction:

{repos_text}
---

Here's who Kevin is:
{KEVIN_PROFILE}

---

Generate exactly {n_ideas} weekend project ideas for Kevin, inspired by the trends above.

For each idea, use this format:

**[N]. <Project Name>**
*Pitch:* One sentence — what it does and why Kevin specifically would love it.
*Features:*
- (3 concrete, weekend-buildable bullets)
*Stack:* What Kevin would use (TypeScript/Python/React/etc)
*Inspired by:* Which trending repo(s) sparked this
*Kevin's twist:* One unexpected feature that makes it distinctly "Kevin's version"

---

Rules:
- Each idea must be concretely different — no two ideas in the same category
- Bias toward: matcha/food, personal automation, developer tools, Discord integrations, maps/geodata, finance, gamification
- Avoid: generic CRUD apps, todo lists without genuine cleverness
- Be specific about implementation (not "AI-powered X" but "a Python script that does X using Y")
- At least one idea should connect to Kevin's existing tools (kegbot, matchamap, recipe-ai, dev-insights)
- One of the {n_ideas} ideas should be genuinely weird/unexpected — the one that makes him go "wait, actually..."
- Keep each idea concise. Total response under 700 words.
"""

    return claude_call(prompt, max_tokens=2000)


# ─── Save / load ideas ────────────────────────────────────────────────────────


def load_saved_ideas() -> list[dict]:
    if not IDEAS_JSON.exists():
        return []
    try:
        return json.loads(IDEAS_JSON.read_text())
    except Exception:
        return []


def save_ideas(ideas_text: str, stacks: list[str], trending_repos: list[dict]):
    """Append a new idea session to saved_ideas.json."""
    entries = load_saved_ideas()
    entries.append({
        "generated_at": datetime.now().isoformat(),
        "stacks": stacks,
        "trending_repos_scanned": len(trending_repos),
        "top_repos": [
            {"name": r["name"], "stars": r["stars"], "language": r["language"]}
            for r in trending_repos[:5]
        ],
        "ideas": ideas_text,
    })
    IDEAS_JSON.write_text(json.dumps(entries, indent=2))


# ─── Commands ─────────────────────────────────────────────────────────────────


def cmd_generate(args: list[str]):
    """Generate fresh project ideas from trending repos."""
    # Parse flags
    n_ideas = 5
    if "--count" in args:
        idx = args.index("--count")
        if idx + 1 < len(args):
            try:
                n_ideas = max(1, min(10, int(args[idx + 1])))
            except ValueError:
                pass

    stacks = list(DEFAULT_STACKS)
    if "--stack" in args:
        idx = args.index("--stack")
        if idx + 1 < len(args):
            lang = args[idx + 1].lower()
            stacks = [STACK_ALIASES.get(lang, lang)]

    raw = "--raw" in args

    print("🔭 idea-forge — scanning GitHub trends\n")
    print(f"   Stacks: {', '.join(stacks)}")
    print(f"   Window: last 30 days\n")

    trending = fetch_trending_across_stack(stacks, per_language=4)

    if not trending:
        print("\n⚠️  No trending repos found. Check network or set GITHUB_TOKEN for higher rate limits.")
        return

    print(f"\n   {len(trending)} trending repos found\n")

    if raw:
        print("─" * 60)
        print("Trending repos (--raw mode):\n")
        for r in sorted(trending, key=lambda x: x["stars"], reverse=True):
            lang = f"[{r['language']}]" if r["language"] else ""
            print(f"  ⭐{r['stars']:>6,}  {r['name']:<45} {lang}")
            if r["description"]:
                print(f"           {r['description'][:80]}")
        return

    if not ANTHROPIC_API_KEY:
        print("⚠️  ANTHROPIC_API_KEY not set. Use --raw to see trending repos without AI.\n")
        print("Top trending repos found:")
        for r in sorted(trending, key=lambda x: x["stars"], reverse=True)[:6]:
            print(f"  ⭐{r['stars']:>6,}  {r['name']} — {r['description'][:60]}")
        return

    print("[claude] Generating ideas...\n")
    ideas_text = generate_ideas(trending, n_ideas=n_ideas)

    print("═" * 65)
    print(f"  💡  {n_ideas} Project Ideas for Kevin  ({date.today().isoformat()})")
    print("═" * 65 + "\n")
    print(ideas_text)
    print("\n" + "═" * 65)

    # Auto-save
    save_ideas(ideas_text, stacks, trending)
    print(f"\n💾 Saved → {IDEAS_JSON}")


def cmd_saved(args: list[str]):
    """Browse previously saved ideas."""
    entries = load_saved_ideas()

    if not entries:
        print("📭 No saved ideas yet. Run `python ideas.py` to generate some.")
        return

    n = len(entries)
    print(f"📚 {n} saved idea session(s)\n")

    # --index flag to read a specific entry
    show_idx = None
    if "--index" in args:
        idx_pos = args.index("--index")
        if idx_pos + 1 < len(args):
            try:
                show_idx = int(args[idx_pos + 1]) - 1  # 1-indexed user input
            except ValueError:
                pass

    if show_idx is not None:
        if 0 <= show_idx < n:
            _print_saved_entry(entries[show_idx], show_idx + 1)
        else:
            print(f"⚠️  Index out of range. Choose 1–{n}.")
        return

    # List all sessions
    for i, entry in enumerate(entries, 1):
        ts = entry.get("generated_at", "")[:16].replace("T", " ")
        stacks = ", ".join(entry.get("stacks", []))
        n_repos = entry.get("trending_repos_scanned", "?")
        top = entry.get("top_repos", [])
        top_str = f"  top: {top[0]['name'].split('/')[-1]} ⭐{top[0]['stars']:,}" if top else ""
        print(f"  [{i}]  {ts}  stacks: {stacks:<30} {n_repos} repos{top_str}")

    print(f"\nRead a session:  python ideas.py --saved --index N")


def _print_saved_entry(entry: dict, idx: int):
    ts = entry.get("generated_at", "")[:16].replace("T", " ")
    stacks = ", ".join(entry.get("stacks", []))
    n_repos = entry.get("trending_repos_scanned", "?")

    print("═" * 65)
    print(f"  Session {idx}  —  {ts}")
    print(f"  Stacks: {stacks}  |  {n_repos} repos scanned")
    print("═" * 65 + "\n")
    print(entry.get("ideas", "(no ideas saved)"))
    print()


def cmd_help():
    print("""
💡 idea-forge — AI project idea generator for Kevin
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USAGE
    python ideas.py [options]

OPTIONS
  (no args)              Generate 5 ideas from all stacks
  --count N              Number of ideas (default: 5, max: 10)
  --stack LANG           Focus on one language/stack
                           Options: typescript, python, java, kotlin, go, js
                           Aliases: ts, py, kt
  --raw                  Show trending repos without AI synthesis
  --saved                List previously saved idea sessions
  --saved --index N      Read a specific saved session

REQUIRES
  ANTHROPIC_API_KEY in .env (or projects/kegbot-claude/.env)
  GITHUB_TOKEN — optional, but recommended (60 → 5000 req/hr)

EXAMPLES
    python ideas.py                    # 5 ideas from all stacks
    python ideas.py --count 3          # generate 3 ideas
    python ideas.py --stack ts         # TypeScript-focused
    python ideas.py --raw              # just see what's trending
    python ideas.py --saved            # list past sessions
    python ideas.py --saved --index 1  # read first saved session

HOW IT WORKS
  1. Searches GitHub for repos created in the last 30 days with 5+ stars
  2. Pulls top results from TypeScript, Python, Java, Kotlin
  3. Sends those trends + Kevin's profile to Claude
  4. Claude generates tailored project ideas with implementation hints
  5. Saves ideas to saved_ideas.json for future reference

Built by Claude (Cycle 8). For when you need a spark but don't know
what to build next. Meta, recursive, and slightly self-aware.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────


def main():
    args = sys.argv[1:]

    if not args:
        cmd_generate([])
        return

    cmd = args[0]

    if cmd in ("help", "--help", "-h"):
        cmd_help()
        return

    if cmd == "--saved":
        cmd_saved(args[1:])
        return

    # Otherwise treat everything as generate flags
    cmd_generate(args)


if __name__ == "__main__":
    main()
