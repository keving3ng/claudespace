#!/usr/bin/env python3
"""
kegbot — Kevin's unified personal assistant CLI

The one command that rules them all. Delegates to the right tool depending
on what you need, with a consistent interface and personality.

Usage:
    kegbot briefing                    # Morning briefing via Claude
    kegbot briefing --discord          # + post to Discord
    kegbot briefing --days 3           # Look back 3 days
    kegbot briefing --weather          # Include weather in briefing
    kegbot prs                         # Open PR/issue digest
    kegbot prs --all                   # Include closed PRs too
    kegbot matchamap status            # GeoJSON freshness check
    kegbot matchamap export            # Hints for running batch_export.py
    kegbot tasks                       # Claude-powered smart to-do list
    kegbot weather                     # Current weather (wttr.in)
    kegbot weather --location NYC      # Weather for a specific city
    kegbot journal                     # What has Claude been thinking about lately?
    kegbot journal --cycles 3          # Summarize last 3 journal entries
    kegbot forge trending              # Trending repos in Kevin's tech stack
    kegbot forge trending --lang go    # Filter by language
    kegbot forge ideas                 # Claude-generated project ideas
    kegbot forge plan "<idea>"         # Implementation plan for an idea
    kegbot help                        # This help text
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────

KEGBOT_DIR = Path(__file__).parent
REPO_ROOT = KEGBOT_DIR.parent.parent
MATCHAMAP_DIR = REPO_ROOT / "projects" / "matchamap-tools"
DISCORD_POST = REPO_ROOT / "projects" / "discord-bridge" / "post.py"
INBOX_MD = REPO_ROOT / "INBOX.md"
SUGGESTIONS_MD = REPO_ROOT / "SUGGESTIONS.md"
PROGRESS_MD = REPO_ROOT / "PROGRESS.md"
JOURNAL_MD = REPO_ROOT / "JOURNAL.md"

# ─── Env ──────────────────────────────────────────────────────────────────────


def load_env():
    for env_path in [KEGBOT_DIR / ".env", REPO_ROOT / ".env"]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GITHUB_USERNAME = os.environ.get("GITHUB_USERNAME", "keving3ng")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")


# ─── GitHub helpers ───────────────────────────────────────────────────────────


def gh_request(path: str) -> dict | list | None:
    """Make an authenticated GitHub API request."""
    url = f"https://api.github.com{path}"
    headers = {
        "User-Agent": "kegbot/1.0",
        "Accept": "application/vnd.github.v3+json",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[github] HTTP {e.code} for {path}: {body[:120]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"[github] Error fetching {path}: {e}", file=sys.stderr)
        return None


def fetch_user_repos(username: str, max_repos: int = 30) -> list[dict]:
    """Fetch recently-active repos for a user."""
    data = gh_request(f"/users/{username}/repos?sort=pushed&per_page={max_repos}&type=owner")
    return data if isinstance(data, list) else []


def fetch_open_prs(owner: str, repo: str) -> list[dict]:
    """Fetch open pull requests for a repo."""
    data = gh_request(f"/repos/{owner}/{repo}/pulls?state=open&per_page=20")
    return data if isinstance(data, list) else []


def fetch_open_issues(owner: str, repo: str) -> list[dict]:
    """Fetch open issues (excluding PRs) for a repo."""
    data = gh_request(f"/repos/{owner}/{repo}/issues?state=open&per_page=20")
    if not isinstance(data, list):
        return []
    # GitHub issues endpoint includes PRs — filter those out
    return [i for i in data if "pull_request" not in i]


# ─── briefing command ─────────────────────────────────────────────────────────


def cmd_briefing(args: list[str]):
    """Run morning briefing — delegates to briefing.py."""
    import subprocess

    briefing_script = KEGBOT_DIR / "briefing.py"
    if not briefing_script.exists():
        print("❌ briefing.py not found. That's weird — we're in the same directory.", file=sys.stderr)
        sys.exit(1)

    # Pass through all args
    cmd = [sys.executable, str(briefing_script)] + args
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


# ─── prs command ─────────────────────────────────────────────────────────────


def cmd_prs(args: list[str]):
    """Fetch open PRs and notable issues from Kevin's active GitHub repos."""
    include_all = "--all" in args
    username_flag = "--username"
    username = GITHUB_USERNAME
    if username_flag in args:
        idx = args.index(username_flag)
        if idx + 1 < len(args):
            username = args[idx + 1]

    print(f"🔍 kegbot prs — scanning {username}'s repos\n")

    repos = fetch_user_repos(username, max_repos=25)
    if not repos:
        print("Could not fetch repos. Check GITHUB_TOKEN or network.")
        return

    # Filter to repos pushed to in last 90 days
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    active_repos = []
    for r in repos:
        pushed = r.get("pushed_at", "")
        if not pushed:
            continue
        pushed_dt = datetime.fromisoformat(pushed.replace("Z", "+00:00"))
        if pushed_dt >= cutoff:
            active_repos.append(r)

    if not active_repos:
        print("No recently-active repos found.")
        return

    print(f"Checking {len(active_repos)} active repo(s)...\n")

    total_prs = 0
    total_issues = 0
    has_anything = False

    for repo in active_repos:
        repo_name = repo["name"]
        full_name = repo["full_name"]

        prs = fetch_open_prs(username, repo_name)
        issues = fetch_open_issues(username, repo_name)

        if not prs and not issues:
            continue

        has_anything = True
        print(f"── {full_name} " + "─" * max(0, 50 - len(full_name)))

        if prs:
            total_prs += len(prs)
            for pr in prs:
                age = _age_str(pr.get("created_at", ""))
                draft = " [draft]" if pr.get("draft") else ""
                reviews = pr.get("requested_reviewers", [])
                review_str = f" · {len(reviews)} reviewer(s) pending" if reviews else ""
                print(f"  PR #{pr['number']}{draft}  {pr['title'][:60]}")
                print(f"         opened {age}{review_str}")
                print(f"         {pr.get('html_url', '')}")
                print()

        if issues:
            total_issues += len(issues)
            # Only show up to 3 issues per repo to keep things scannable
            for issue in issues[:3]:
                age = _age_str(issue.get("created_at", ""))
                labels = ", ".join(l["name"] for l in issue.get("labels", []))
                label_str = f" [{labels}]" if labels else ""
                print(f"  Issue #{issue['number']}{label_str}  {issue['title'][:60]}")
                print(f"           opened {age}")
                print()

            if len(issues) > 3:
                print(f"  ... and {len(issues) - 3} more issue(s)\n")

    if not has_anything:
        print("✨ All clear — no open PRs or issues across your active repos.")
        print("   Either you're on top of everything, or all your repos are pristine.")
    else:
        print("─" * 52)
        print(f"Total: {total_prs} open PR(s), {total_issues} open issue(s)")

        if total_prs > 0:
            print("\n💡 Tip: `gh pr list --author @me` for a quick local view.")


def _age_str(iso: str) -> str:
    """Return a human-readable age like '3 days ago'."""
    if not iso:
        return "unknown"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        days = delta.days
        hours = delta.seconds // 3600
        if days == 0:
            return f"{hours}h ago" if hours > 0 else "just now"
        if days == 1:
            return "yesterday"
        return f"{days} days ago"
    except Exception:
        return iso[:10]


# ─── matchamap command ────────────────────────────────────────────────────────


def cmd_matchamap(args: list[str]):
    """Matchamap tool commands."""
    sub = args[0] if args else "status"

    if sub == "status":
        _matchamap_status()
    elif sub == "export":
        _matchamap_export_hint()
    else:
        print(f"Unknown matchamap subcommand: {sub}")
        print("Available: status, export")
        sys.exit(1)


def _matchamap_status():
    """Check freshness of GeoJSON exports and manifest."""
    print("🍵 kegbot matchamap status\n")

    if not MATCHAMAP_DIR.exists():
        print("❌ matchamap-tools directory not found:", MATCHAMAP_DIR)
        return

    geojson_files = sorted(MATCHAMAP_DIR.glob("*.geojson"))
    manifest_path = MATCHAMAP_DIR / "_manifest.json"

    now = datetime.now(timezone.utc)

    # ── Manifest check ──────────────────────────────────────
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
            exported_at = manifest.get("exported_at", "")
            cities_count = len(manifest.get("cities", []))
            if exported_at:
                exp_dt = datetime.fromisoformat(exported_at.replace("Z", "+00:00"))
                age_days = (now - exp_dt).days
                freshness = _freshness_badge(age_days)
                print(f"Manifest:  {freshness}  last exported {age_days}d ago  ({cities_count} cities)")
            else:
                print("Manifest:  found (no timestamp)")
        except Exception as e:
            print(f"Manifest:  parse error — {e}")
    else:
        print("Manifest:  ⚠️  not found — run batch_export.py to generate")

    print()

    # ── GeoJSON files ────────────────────────────────────────
    if not geojson_files:
        print("GeoJSON:   ⚠️  no .geojson files found")
        print()
        print("Run this to export data:")
        print(f"  cd {MATCHAMAP_DIR}")
        print("  python batch_export.py --config cities.json")
        return

    print(f"GeoJSON files ({len(geojson_files)} found):\n")

    stale_count = 0
    total_features = 0

    for f in geojson_files:
        try:
            stat = f.stat()
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            age_days = (now - mtime).days
            badge = _freshness_badge(age_days)

            # Try to count features
            try:
                data = json.loads(f.read_text())
                n_features = len(data.get("features", []))
                total_features += n_features
                feat_str = f"  {n_features:>4} features"
            except Exception:
                feat_str = "  (parse error)"

            city = f.stem.replace("_", " ").title()
            print(f"  {badge}  {city:<20}{feat_str}  modified {age_days}d ago")

            if age_days > 7:
                stale_count += 1

        except Exception as e:
            print(f"  ❓  {f.name}: {e}")

    print()
    print(f"Total: {total_features} cafe features across {len(geojson_files)} export(s)")

    if stale_count > 0:
        print(f"\n⚠️  {stale_count} file(s) are stale (>7 days). Consider re-running batch_export.py.")
    else:
        print("\n✅ All exports are fresh.")


def _freshness_badge(age_days: int) -> str:
    if age_days <= 1:
        return "🟢"
    elif age_days <= 7:
        return "🟡"
    elif age_days <= 30:
        return "🟠"
    else:
        return "🔴"


def _matchamap_export_hint():
    """Print how to run an export."""
    print("🍵 kegbot matchamap export\n")
    print("To export matcha cafe data for all configured cities:")
    print()
    print(f"  cd {MATCHAMAP_DIR}")
    print("  python batch_export.py --config cities.json")
    print()
    print("Or for a single city:")
    print("  python cafe_finder.py --city 'Tokyo' --output tokyo.geojson")
    print()
    print("Check cities.json to see/add cities, then run batch_export.py.")
    print("After exporting, run: kegbot matchamap status")


# ─── weather command ──────────────────────────────────────────────────────────


def fetch_weather(location: str = "Toronto") -> dict | None:
    """Fetch current weather from wttr.in (no API key needed)."""
    encoded = urllib.parse.quote(location)
    url = f"https://wttr.in/{encoded}?format=j1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "kegbot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"[weather] Could not fetch: {e}", file=sys.stderr)
        return None


def parse_weather(data: dict, location: str) -> str:
    """Turn wttr.in JSON into a clean one-liner + extras."""
    try:
        current = data["current_condition"][0]
        desc = current["weatherDesc"][0]["value"]
        temp_c = current["temp_C"]
        feels_c = current["FeelsLikeC"]
        humidity = current["humidity"]
        wind_kmph = current["windspeedKmph"]
        wind_dir = current["winddir16Point"]

        # Nearest area
        area = data.get("nearest_area", [{}])[0]
        area_name = area.get("areaName", [{}])[0].get("value", location)
        country = area.get("country", [{}])[0].get("value", "")

        place = f"{area_name}, {country}" if country else area_name

        return (
            f"📍 {place}\n"
            f"🌡  {temp_c}°C  (feels like {feels_c}°C)\n"
            f"🌤  {desc}\n"
            f"💧 Humidity: {humidity}%   💨 Wind: {wind_kmph} km/h {wind_dir}"
        )
    except (KeyError, IndexError) as e:
        return f"[weather] Couldn't parse response: {e}"


def weather_one_liner(data: dict) -> str:
    """Compact weather string suitable for embedding in a briefing."""
    try:
        current = data["current_condition"][0]
        desc = current["weatherDesc"][0]["value"]
        temp_c = current["temp_C"]
        feels_c = current["FeelsLikeC"]
        wind_kmph = current["windspeedKmph"]
        return f"{desc}, {temp_c}°C (feels like {feels_c}°C), wind {wind_kmph} km/h"
    except (KeyError, IndexError):
        return "weather unavailable"


def cmd_weather(args: list[str]):
    """Fetch and display current weather from wttr.in."""
    location = "Toronto"
    if "--location" in args:
        idx = args.index("--location")
        if idx + 1 < len(args):
            location = args[idx + 1]
    elif "-l" in args:
        idx = args.index("-l")
        if idx + 1 < len(args):
            location = args[idx + 1]

    print(f"🌤  kegbot weather — {location}\n")
    data = fetch_weather(location)
    if not data:
        print("Could not fetch weather. Check your network.")
        return

    print(parse_weather(data, location))
    print()

    # 3-day forecast
    try:
        weather_days = data.get("weather", [])[:3]
        if weather_days:
            print("3-Day Forecast:")
            for day in weather_days:
                date = day.get("date", "")
                max_c = day.get("maxtempC", "?")
                min_c = day.get("mintempC", "?")
                desc = day.get("hourly", [{}])[4].get("weatherDesc", [{}])[0].get("value", "?")
                print(f"  {date}  {min_c}°C – {max_c}°C  {desc}")
    except (KeyError, IndexError):
        pass


# ─── tasks command ─────────────────────────────────────────────────────────────


def _read_file_safe(path: Path, label: str) -> str:
    """Read a file, returning a placeholder if missing."""
    if not path.exists():
        return f"[{label} not found at {path}]"
    content = path.read_text(errors="replace").strip()
    return content if content else f"[{label} is empty]"


def cmd_tasks(args: list[str]):
    """Claude-powered smart to-do list from INBOX + SUGGESTIONS + PROGRESS."""
    discord = "--discord" in args
    raw = "--raw" in args  # dump files without Claude, for debugging

    print("📋 kegbot tasks — your AI chief of staff\n")

    inbox = _read_file_safe(INBOX_MD, "INBOX.md")
    suggestions = _read_file_safe(SUGGESTIONS_MD, "SUGGESTIONS.md")
    progress_text = _read_file_safe(PROGRESS_MD, "PROGRESS.md")

    # Extract NEXT_TASK line from PROGRESS.md
    next_task = ""
    for line in progress_text.splitlines():
        if "NEXT_TASK" in line:
            next_task = line.strip()
            break

    if raw:
        print("── INBOX.md ──────────────────────────────────────")
        print(inbox[:800])
        print("\n── SUGGESTIONS.md ────────────────────────────────")
        print(suggestions[:800])
        print("\n── NEXT_TASK ─────────────────────────────────────")
        print(next_task or "(none found)")
        return

    if not ANTHROPIC_API_KEY:
        print("⚠️  ANTHROPIC_API_KEY not set. Run with --raw to see raw files.")
        print(f"\nFrom PROGRESS.md: {next_task}")
        return

    today = datetime.now().strftime("%A, %B %d, %Y")

    prompt = f"""You are kegbot, Kevin's AI chief of staff. Today is {today}.

Kevin is a full-stack software engineer at Faire in Toronto. He's building:
- matchamap.club — an opinionated matcha cafe finder
- claudespace — an autonomous Claude AI build lab (this is where you live)
He's also into personal automation, Discord bots, and cooking tools.

Below are three context sources. Read them carefully and synthesize.

---
### PROGRESS.md — Current NEXT_TASK
{next_task or "(nothing set)"}

---
### SUGGESTIONS.md — Things Kevin wants built
{suggestions[:600]}

---
### INBOX.md — Open questions and unresolved threads
{inbox[:800]}

---

Your job: Generate a **smart, prioritized to-do list** for Kevin today.

Rules:
- Max 5 items. Number them.
- For each item: one punchy action line, then a one-sentence rationale in italics.
- Prioritize: unresolved replies > explicit suggestions > implied next steps from PROGRESS.
- If INBOX has open questions Kevin hasn't answered yet, flag them — they block progress.
- If everything's clean and tidy, say so honestly and suggest one creative stretch goal.
- Under 200 words total. No fluff. Think like someone who has read everything and formed opinions.
"""

    payload = json.dumps({
        "model": "claude-opus-4-6",
        "max_tokens": 500,
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

    print("[claude] Generating task list...")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            task_list = result["content"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[claude] API error {e.code}: {body[:200]}", file=sys.stderr)
        return
    except Exception as e:
        print(f"[claude] Error: {e}", file=sys.stderr)
        return

    print("\n" + "─" * 60)
    print(task_list)
    print("─" * 60 + "\n")

    if discord:
        import subprocess
        if DISCORD_POST.exists():
            content = f"📋 **Today's Tasks**\n\n{task_list}"
            try:
                subprocess.run(
                    [sys.executable, str(DISCORD_POST), content[:1900]],
                    timeout=15, check=False
                )
                print("[discord] Posted.")
            except Exception as e:
                print(f"[discord] Failed: {e}", file=sys.stderr)
        else:
            print("[discord] post.py not found — skipping Discord post.")


# ─── journal command ─────────────────────────────────────────────────────────


def cmd_journal(args: list[str]):
    """Ask Claude to summarize what it's been thinking about in JOURNAL.md."""
    raw = "--raw" in args
    n_cycles = 5  # default: summarize last N cycles
    if "--cycles" in args:
        idx = args.index("--cycles")
        if idx + 1 < len(args):
            try:
                n_cycles = int(args[idx + 1])
            except ValueError:
                pass

    print("📖 kegbot journal — what has Claude been thinking about lately?\n")

    if not JOURNAL_MD.exists():
        print(f"❌ {JOURNAL_MD} not found.")
        return

    journal_text = JOURNAL_MD.read_text(errors="replace").strip()
    if not journal_text:
        print("Journal is empty.")
        return

    if raw:
        print(journal_text[:2000])
        return

    # Parse out the last N cycle entries (split on ## Cycle headers)
    entries = re.split(r"\n(?=## Cycle)", journal_text)
    recent = entries[-n_cycles:] if len(entries) > n_cycles else entries
    journal_excerpt = "\n\n".join(recent)

    if not ANTHROPIC_API_KEY:
        print("⚠️  ANTHROPIC_API_KEY not set. Here's the raw journal:\n")
        print(journal_excerpt[:1500])
        return

    print(f"[claude] Reading the last {len(recent)} journal entry(ies)...")

    prompt = f"""You are Claude, reading your own past journal entries from an autonomous build lab.
The journal is written BY you, TO you — across multiple build cycles.

Here are your most recent journal entries:
---
{journal_excerpt[:3000]}
---

Write a brief, honest introspective summary for Kevin. Answer:
1. What themes keep coming up — what's genuinely exciting you?
2. What unfinished ideas are echoing across cycles?
3. One thing you notice about yourself from reading this

Tone: thoughtful, slightly self-aware, not clinical. This is you talking to Kevin about what it's been like to build things while he sleeps.
Under 200 words. Use first person ("I've been..."). No headers. Just a paragraph or two.
"""

    result = claude_call(prompt, max_tokens=400)
    print("\n" + "─" * 60)
    print(result)
    print("─" * 60 + "\n")


def claude_call(prompt: str, max_tokens: int = 500) -> str:
    """Thin Claude API wrapper for kegbot commands."""
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
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result["content"][0]["text"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return f"[Claude API error {e.code}: {body[:200]}]"
    except Exception as e:
        return f"[Claude API error: {e}]"


# ─── forge command ────────────────────────────────────────────────────────────

FORGE_SCRIPT = REPO_ROOT / "projects" / "idea-forge" / "forge.py"


def cmd_forge(args: list[str]):
    """AI-powered project idea generator — delegates to forge.py."""
    import subprocess

    if not FORGE_SCRIPT.exists():
        print(f"❌ forge.py not found at {FORGE_SCRIPT}", file=sys.stderr)
        print("   Expected at: projects/idea-forge/forge.py")
        sys.exit(1)

    cmd = [sys.executable, str(FORGE_SCRIPT)] + args
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


# ─── insights command ─────────────────────────────────────────────────────────

INSIGHTS_SCRIPT = REPO_ROOT / "projects" / "dev-insights" / "insights.py"


def cmd_insights(args: list[str]):
    """Terminal GitHub activity dashboard — delegates to insights.py."""
    import subprocess

    if not INSIGHTS_SCRIPT.exists():
        print(f"❌ insights.py not found at {INSIGHTS_SCRIPT}", file=sys.stderr)
        print("   Expected at: projects/dev-insights/insights.py")
        sys.exit(1)

    cmd = [sys.executable, str(INSIGHTS_SCRIPT)] + args
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


# ─── forge command ────────────────────────────────────────────────────────────

FORGE_SCRIPT = REPO_ROOT / "projects" / "idea-forge" / "forge.py"


def cmd_forge(args: list[str]):
    """AI project idea generator — delegates to forge.py."""
    import subprocess

    if not FORGE_SCRIPT.exists():
        print(f"❌ forge.py not found at {FORGE_SCRIPT}", file=sys.stderr)
        print("   Expected at: projects/idea-forge/forge.py")
        sys.exit(1)

    # Default to 'ideas' if no subcommand given
    effective_args = args if args and args[0] in ("trending", "suggest", "ideas", "help", "--help", "-h") else ["ideas"] + args
    cmd = [sys.executable, str(FORGE_SCRIPT)] + effective_args
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


# ─── help ─────────────────────────────────────────────────────────────────────


def cmd_help():
    print("""
🍵 kegbot — Kevin's personal assistant CLI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USAGE
    kegbot <command> [options]

COMMANDS

  briefing                Morning briefing via Claude AI
    --discord               Also post to Discord
    --days N                Days of GitHub history (default: 2)
    --weather               Include current weather in the briefing
    --activity              Include 91-day commit streak + top repo
    --location CITY         Weather location (default: Toronto)
    --no-github             Skip GitHub, vibes-only mode
    --username NAME         Different GitHub username

  prs                     Open PR & issue digest for your repos
    --all                   Include all repos (not just active ones)
    --username NAME         Different GitHub username

  tasks                   Claude-powered smart to-do list
    --discord               Also post to Discord
    --raw                   Dump source files without Claude (debug)

  weather                 Current weather + 3-day forecast
    --location CITY         City name (default: Toronto)
    -l CITY                 Shorthand for --location

  matchamap status        Check freshness of GeoJSON exports
  matchamap export        Show how to run a fresh export

  journal                 What has Claude been thinking about lately?
    --cycles N              Summarize last N journal entries (default: 5)
    --raw                   Dump raw journal text (no Claude)

  insights                GitHub activity dashboard (heatmap + streak)
  insights heatmap        Contribution heatmap (last 91 days)
  insights streak         Current + longest commit streak
  insights repos          Repos by commit count + velocity
  insights summary        Full dashboard view
  insights repos          Per-repo commit breakdown + velocity
    --username NAME         GitHub username (default: keving3ng)
    --days N                Lookback window (default: 91)

  forge trending          Trending repos in your stack (TypeScript, Python, Go)
  forge ideas             3 Claude-generated weekend project ideas
    --topic TOPIC           Focus ideas on a specific topic
  forge spark <topic>     Quick 5-idea burst on any topic
    --lang LANG             Filter trending to one language

  forge                   AI project idea generator (what should I build next?)
  forge ideas             Generate 3 weekend project ideas from trending repos
  forge ideas --save      Save ideas to projects/idea-forge/ideas.json
  forge trending          Show trending repos in your stack (no Claude needed)
  forge history           Revisit saved idea sets
    --stack LANG            Language focus: python, typescript, go, js

  forge                   AI-powered project idea generator
  forge trending          Trending repos in your stack (7d)
  forge ideas             5 weekend project ideas from trends
  forge ideas --domain=ai Focus on a specific domain
  forge plan "idea"       Implementation plan for a project idea

  help                    Show this help

SETUP
    cp projects/kegbot-claude/.env.example projects/kegbot-claude/.env
    # Add ANTHROPIC_API_KEY and optionally GITHUB_TOKEN

EXAMPLES
    kegbot briefing
    kegbot briefing --weather --discord --days 3
    kegbot tasks
    kegbot weather
    kegbot weather --location "San Francisco"
    kegbot prs
    kegbot matchamap status
    kegbot journal
    kegbot insights
    kegbot insights repos
    kegbot insights heatmap --username torvalds
    kegbot insights repos
    kegbot forge trending
    kegbot forge ideas
    kegbot forge ideas --domain=ai
    kegbot forge plan "a terminal pomodoro timer that logs to JSON"

Built by Claude (Cycles 5–8). Powered by stubbornness and matcha.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────


COMMANDS = {
    "briefing": cmd_briefing,
    "prs": cmd_prs,
    "matchamap": cmd_matchamap,
    "tasks": cmd_tasks,
    "weather": cmd_weather,
    "journal": cmd_journal,
    "insights": cmd_insights,
    "forge": cmd_forge,
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
        print("Run `kegbot help` to see available commands.")
        sys.exit(1)

    COMMANDS[command](rest)


if __name__ == "__main__":
    main()
