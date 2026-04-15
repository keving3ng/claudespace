#!/usr/bin/env python3
"""
insights — Terminal GitHub activity dashboard

Contribution heatmap, coding streak tracker, commit stats.
Zero dependencies beyond stdlib. Uses GitHub public API (no auth, 60 req/hr).

Usage:
    insights heatmap                       # contribution heatmap, last 90 days
    insights heatmap --username foo        # another user's heatmap
    insights streak                        # current + longest commit streak
    insights streak --username foo
    insights summary                       # full dashboard (heatmap + streak + stats)
    insights summary --username foo
    insights help
"""

import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent.parent
DEFAULT_USERNAME = "keving3ng"

# Heatmap cell characters by commit density
# Levels: 0 commits, 1, 2-4, 5-9, 10+
HEAT_CHARS = [" · ", " ▪ ", " ▪▪", " ▓▓", " ██"]
HEAT_LABELS = ["0", "1", "2-4", "5-9", "10+"]

WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

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

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")


# ─── GitHub API ───────────────────────────────────────────────────────────────


def _github_request(url: str) -> dict | list | None:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "dev-insights/1.0",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        body = e.read().decode("utf-8", errors="replace")
        print(f"⚠️  GitHub API error {e.code}: {body[:200]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"⚠️  Request failed: {e}", file=sys.stderr)
        return None


def fetch_push_events_by_repo(username: str, days: int = 90) -> dict[str, dict]:
    """
    Fetch PushEvent data for a user, returning per-repo stats:
    {repo_name: {commits, recent_commits (last 7d), last_push}}
    """
    commit_counts: dict[date, int] = defaultdict(int)
    _fetch_raw_events(username, days, commit_counts, None)
    return dict(commit_counts)


def fetch_repo_stats(username: str, days: int = 90) -> dict[str, dict]:
    """
    Fetch per-repo commit stats from PushEvents, returning:
      {repo_name: {"commits": N, "pushes": N, "last_push": date, "first_push": date}}
    """
    cutoff = date.today() - timedelta(days=days)
    repo_stats: dict[str, dict] = defaultdict(
        lambda: {"commits": 0, "pushes": 0, "last_push": None, "first_push": None}
    )

    for page in range(1, 4):
        url = f"https://api.github.com/users/{username}/events?per_page=100&page={page}"
        events = _github_request(url)
        if not events or not isinstance(events, list):
            break

        reached_cutoff = False
        for event in events:
            if event.get("type") != "PushEvent":
                continue
            created_at = event.get("created_at", "")
            try:
                event_date = datetime.strptime(created_at[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            if event_date < cutoff:
                reached_cutoff = True
                continue

            repo_name = event.get("repo", {}).get("name", "unknown")
            num_commits = len(event.get("payload", {}).get("commits", []))
            num_commits = max(num_commits, 1)

            s = repo_stats[repo_name]
            s["commits"] += num_commits
            s["pushes"] += 1
            if s["last_push"] is None or event_date > s["last_push"]:
                s["last_push"] = event_date
            if s["first_push"] is None or event_date < s["first_push"]:
                s["first_push"] = event_date

        if reached_cutoff:
            break

    return dict(repo_stats)


def _fetch_raw_events(
    username: str,
    days: int,
    commit_counts: dict,
    repo_stats: dict | None,
) -> None:
    """Shared event-fetching loop used by fetch_push_events and fetch_repo_stats."""
    cutoff = date.today() - timedelta(days=days)

    repo_stats: dict[str, dict] = defaultdict(lambda: {
        "commits": 0,
        "recent_commits": 0,
        "last_push": None,
    })

    for page in range(1, 4):
        url = f"https://api.github.com/users/{username}/events?per_page=100&page={page}"
        events = _github_request(url)
        if not events or not isinstance(events, list):
            break

        reached_cutoff = False
        for event in events:
            if event.get("type") != "PushEvent":
                continue
            created_at = event.get("created_at", "")
            try:
                event_date = datetime.strptime(created_at[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            if event_date < cutoff:
                reached_cutoff = True
                continue

            repo_name = event.get("repo", {}).get("name", "unknown")
            # Strip owner prefix for display; keep full name as key
            num_commits = len(event.get("payload", {}).get("commits", []))
            num_commits = max(num_commits, 1)

            repo_stats[repo_name]["commits"] += num_commits
            if (
                repo_stats[repo_name]["last_push"] is None
                or event_date > repo_stats[repo_name]["last_push"]
            ):
                repo_stats[repo_name]["last_push"] = event_date

            if event_date >= week_cutoff:
                repo_stats[repo_name]["recent_commits"] += num_commits

        if reached_cutoff:
            break


def _fetch_raw_events(username: str, days: int = 90) -> tuple[list, bool]:
    """
    Fetch raw PushEvent records for a user.
    Returns ([(date, commit_count, repo_name), ...], hit_cutoff).
    Shared by fetch_push_events and fetch_repo_breakdown.
    """
    cutoff = date.today() - timedelta(days=days)
    records: list[tuple[date, int, str]] = []
    hit_cutoff = False

    for page in range(1, 4):  # max 3 pages = 300 events
        url = f"https://api.github.com/users/{username}/events?per_page=100&page={page}"
        events = _github_request(url)
        if not events or not isinstance(events, list):
            break

        for event in events:
            if event.get("type") != "PushEvent":
                continue
            created_at = event.get("created_at", "")
            try:
                event_date = datetime.strptime(created_at[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            if event_date < cutoff:
                hit_cutoff = True
                continue
            num_commits = len(event.get("payload", {}).get("commits", []))
            repo_name = event.get("repo", {}).get("name", "unknown")
            records.append((event_date, max(num_commits, 1), repo_name))

        if hit_cutoff:
            break

    return records, hit_cutoff


def fetch_repo_breakdown(username: str, days: int = 91) -> dict[str, dict]:
    """
    Return per-repo stats: {repo_name: {commits, days_active, first, last}}.
    """
    records, _ = _fetch_raw_events(username, days)
    repos: dict[str, dict] = {}

    for event_date, num_commits, repo_name in records:
        if repo_name not in repos:
            repos[repo_name] = {
                "commits": 0,
                "active_days": set(),
                "first": event_date,
                "last": event_date,
            }
        entry = repos[repo_name]
        entry["commits"] += num_commits
        entry["active_days"].add(event_date)
        entry["first"] = min(entry["first"], event_date)
        entry["last"] = max(entry["last"], event_date)

    # Convert sets to counts, compute velocity (commits per active day)
    for name, entry in repos.items():
        active_day_count = len(entry["active_days"])
        entry["active_days"] = active_day_count
        span_days = max((entry["last"] - entry["first"]).days + 1, 1)
        entry["velocity"] = round(entry["commits"] / span_days, 2)  # commits/calendar day
        entry["span_days"] = span_days

    return repos


def fetch_user_info(username: str) -> dict | None:
    return _github_request(f"https://api.github.com/users/{username}")


def fetch_push_events_by_repo(username: str, days: int = 90) -> dict[str, dict]:
    """
    Fetch PushEvent data grouped by repo.
    Returns {repo_name: {"total": int, "last_push": date, "commits_by_date": {date: int}}}
    """
    cutoff = date.today() - timedelta(days=days)

    repo_data: dict[str, dict] = {}

    for page in range(1, 4):
        url = f"https://api.github.com/users/{username}/events?per_page=100&page={page}"
        events = _github_request(url)
        if not events or not isinstance(events, list):
            break

        reached_cutoff = False
        for event in events:
            if event.get("type") != "PushEvent":
                continue
            created_at = event.get("created_at", "")
            try:
                event_date = datetime.strptime(created_at[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            if event_date < cutoff:
                reached_cutoff = True
                continue

            # Repo name from event (e.g. "keving3ng/claudespace" → "claudespace")
            repo_full = event.get("repo", {}).get("name", "unknown")
            repo_name = repo_full.split("/", 1)[-1] if "/" in repo_full else repo_full

            num_commits = len(event.get("payload", {}).get("commits", []))
            num_commits = max(num_commits, 1)

            if repo_name not in repo_data:
                repo_data[repo_name] = {"total": 0, "last_push": None, "commits_by_date": {}}

            repo_data[repo_name]["total"] += num_commits
            repo_data[repo_name]["commits_by_date"][event_date] = (
                repo_data[repo_name]["commits_by_date"].get(event_date, 0) + num_commits
            )
            if repo_data[repo_name]["last_push"] is None or event_date > repo_data[repo_name]["last_push"]:
                repo_data[repo_name]["last_push"] = event_date

        if reached_cutoff:
            break

    return repo_data


# ─── Heat level ───────────────────────────────────────────────────────────────


def heat_level(count: int) -> int:
    if count == 0:
        return 0
    if count == 1:
        return 1
    if count <= 4:
        return 2
    if count <= 9:
        return 3
    return 4


# ─── Streak calculation ───────────────────────────────────────────────────────


def calculate_streaks(commit_counts: dict[date, int]) -> dict:
    """Return current streak, longest streak, and total active days."""
    if not commit_counts:
        return {"current": 0, "longest": 0, "total_days": 0, "total_commits": 0}

    active_days = sorted(d for d, c in commit_counts.items() if c > 0)
    if not active_days:
        return {"current": 0, "longest": 0, "total_days": 0, "total_commits": 0}

    # Longest streak
    longest = 1
    run = 1
    for i in range(1, len(active_days)):
        if (active_days[i] - active_days[i - 1]).days == 1:
            run += 1
            longest = max(longest, run)
        else:
            run = 1

    # Current streak — walk back from today
    today = date.today()
    current = 0
    check = today
    while check in commit_counts and commit_counts[check] > 0:
        current += 1
        check -= timedelta(days=1)
    # Also check if yesterday was the last active day (streak still "alive")
    if current == 0:
        yesterday = today - timedelta(days=1)
        check = yesterday
        while check in commit_counts and commit_counts[check] > 0:
            current += 1
            check -= timedelta(days=1)

    return {
        "current": current,
        "longest": longest,
        "total_days": len(active_days),
        "total_commits": sum(commit_counts.values()),
    }


# ─── Heatmap rendering ────────────────────────────────────────────────────────


def render_heatmap(commit_counts: dict[date, int], username: str, days: int = 91) -> str:
    """
    Render a GitHub-style contribution heatmap to a string.
    Layout: rows = weekdays (Mon-Sun), columns = weeks (oldest → newest).
    """
    today = date.today()
    # Align start to Monday of the week 'days' ago
    start = today - timedelta(days=days - 1)
    # Roll back to Monday
    start -= timedelta(days=start.weekday())

    # Build list of all days from start to today
    all_days: list[date] = []
    d = start
    while d <= today:
        all_days.append(d)
        d += timedelta(days=1)

    # Group by week
    weeks: list[list[date | None]] = []
    week: list[date | None] = []
    for d in all_days:
        week.append(d)
        if d.weekday() == 6:  # Sunday
            weeks.append(week)
            week = []
    if week:
        # Pad incomplete final week
        while len(week) < 7:
            week.append(None)
        weeks.append(week)

    # Build month header
    month_header = "     "  # 5 chars for row label
    last_month = None
    for w in weeks:
        # Find first non-None day in week
        first = next((d for d in w if d), None)
        if first and first.month != last_month:
            label = first.strftime("%b")
            month_header += label.ljust(len(HEAT_CHARS[0]) * 1)
            last_month = first.month
        else:
            month_header += " " * len(HEAT_CHARS[0])

    lines = [month_header]

    for wd in range(7):  # Monday=0 ... Sunday=6
        row_label = WEEKDAY_LABELS[wd][:3].ljust(4) + " "
        row = row_label
        for w in weeks:
            day = w[wd] if wd < len(w) else None
            if day is None or day > today:
                row += "   "  # blank padding
            else:
                count = commit_counts.get(day, 0)
                row += HEAT_CHARS[heat_level(count)]
        lines.append(row)

    # Legend
    legend = "\n     "
    for i, char in enumerate(HEAT_CHARS):
        legend += f"{char} {HEAT_LABELS[i]}  "

    lines.append(legend)

    # Stats line
    total = sum(commit_counts.values())
    active = sum(1 for c in commit_counts.values() if c > 0)
    lines.append(f"\n     {total} commits across {active} active days in the last ~{days} days")

    return "\n".join(lines)


# ─── Commands ─────────────────────────────────────────────────────────────────


def get_username(args: list[str]) -> str:
    if "--username" in args:
        idx = args.index("--username")
        if idx + 1 < len(args):
            return args[idx + 1]
    if "-u" in args:
        idx = args.index("-u")
        if idx + 1 < len(args):
            return args[idx + 1]
    return DEFAULT_USERNAME


def cmd_heatmap(args: list[str]):
    username = get_username(args)
    days = 91

    print(f"🗓  Fetching activity for @{username}...")
    commit_counts = fetch_push_events(username, days=days)

    if not commit_counts:
        print(f"\n⚠️  No push events found for @{username} in the last {days} days.")
        print("   (GitHub API only returns public events, and only the last ~300)")
        return

    print(f"\n📊 Contribution Heatmap — @{username} (last ~{days} days)\n")
    print(render_heatmap(commit_counts, username, days))
    print()


def cmd_streak(args: list[str]):
    username = get_username(args)

    print(f"🔥 Fetching streak data for @{username}...")
    commit_counts = fetch_push_events(username, days=91)
    stats = calculate_streaks(commit_counts)

    today = date.today()
    today_count = commit_counts.get(today, 0)
    yesterday_count = commit_counts.get(today - timedelta(days=1), 0)

    print(f"\n🔥 Coding Streak — @{username}\n")
    print(f"   Current streak:   {stats['current']} day(s)")
    print(f"   Longest streak:   {stats['longest']} day(s)  (last 91 days)")
    print(f"   Active days:      {stats['total_days']} / 91")
    print(f"   Total commits:    {stats['total_commits']}")
    print()

    # Today's status
    if today_count > 0:
        print(f"   ✅  Today: {today_count} commit(s) — streak is alive")
    elif yesterday_count > 0:
        print(f"   ⏳  No commits yet today (yesterday: {yesterday_count}) — keep it going!")
    else:
        print(f"   💤  No commits today or yesterday")

    # Encouragement
    if stats["current"] >= 7:
        print(f"\n   🚀 Week-long streak! You're on a roll.")
    elif stats["current"] >= 3:
        print(f"\n   ⚡ {stats['current']}-day streak. Don't break the chain.")
    elif stats["current"] == 0 and stats["total_days"] > 0:
        print(f"\n   💪 Time to start a new streak.")

    print()


def cmd_summary(args: list[str]):
    username = get_username(args)
    days = 91

    print(f"📈 Fetching data for @{username}...")

    # Parallel-ish: fetch events and user info
    commit_counts = fetch_push_events(username, days=days)
    user_info = fetch_user_info(username)

    print()
    print("═" * 60)
    print(f"  dev-insights — @{username}")
    if user_info:
        name = user_info.get("name") or username
        bio = user_info.get("bio") or ""
        followers = user_info.get("followers", 0)
        public_repos = user_info.get("public_repos", 0)
        print(f"  {name}")
        if bio:
            print(f"  {bio[:55]}")
        print(f"  {public_repos} public repos · {followers} followers")
    print("═" * 60)
    print()

    if commit_counts:
        print("📊 Contribution Heatmap\n")
        print(render_heatmap(commit_counts, username, days))
        print()

        stats = calculate_streaks(commit_counts)
        print("🔥 Streak Summary\n")
        print(f"   Current streak:  {stats['current']} day(s)")
        print(f"   Longest streak:  {stats['longest']} day(s)  (last 91 days)")
        print(f"   Active days:     {stats['total_days']} / 91")
        print(f"   Total commits:   {stats['total_commits']}")

        # Most active days of the week
        dow_counts: Counter = Counter()
        for d, count in commit_counts.items():
            if count > 0:
                dow_counts[d.weekday()] += count
        if dow_counts:
            best_dow = max(dow_counts, key=dow_counts.get)
            print(f"   Most active day: {WEEKDAY_LABELS[best_dow]} ({dow_counts[best_dow]} commits)")

        # Most active week
        week_counts: Counter = Counter()
        for d, count in commit_counts.items():
            week_start = d - timedelta(days=d.weekday())
            week_counts[week_start] += count
        if week_counts:
            best_week = max(week_counts, key=week_counts.get)
            print(f"   Most active week: {best_week.strftime('%b %d')}  ({week_counts[best_week]} commits)")
    else:
        print(f"⚠️  No push events found for @{username} in the last {days} days.")

    print()


def cmd_repos(args: list[str]):
    username = get_username(args)
    days = 91
    weeks = days / 7

    print(f"📦 Fetching repo activity for @{username}...")
    repo_data = fetch_push_events_by_repo(username, days=days)

    if not repo_data:
        print(f"\n⚠️  No push events found for @{username} in the last {days} days.")
        return

    sorted_repos = sorted(repo_data.items(), key=lambda x: x[1]["total"], reverse=True)
    today = date.today()

    print(f"\n📦 Repo Activity — @{username} (last ~{days} days)\n")
    print(f"     {'Repo':<28}  {'Commits':>7}  {'Per week':>8}  {'Last push'}")
    print(f"     {'─'*28}  {'─'*7}  {'─'*8}  {'─'*10}")

    for repo_name, data in sorted_repos:
        total = data["total"]
        velocity = total / weeks
        last_push = data["last_push"]
        last_push_str = last_push.strftime("%b %d") if last_push else "?"
        days_since = (today - last_push).days if last_push else 999

        if days_since <= 3:
            badge = "🟢"
        elif days_since <= 14:
            badge = "🟡"
        elif days_since <= 45:
            badge = "🟠"
        else:
            badge = "🔴"

        # Bar chart: 1 block per 5 commits, max 10 blocks
        bar_len = min(int(total / 2), 12)
        bar = "█" * bar_len if bar_len else "▏"

        print(f"  {badge}  {repo_name:<28}  {total:>7}  {velocity:>7.1f}/w  {last_push_str}  {bar}")

    total_commits = sum(d["total"] for d in repo_data.values())
    print(f"\n     {len(sorted_repos)} repos active · {total_commits} total commits · ~{days} day window")
    print()


def cmd_help():
    print("""
📈 insights — Terminal GitHub activity dashboard
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USAGE
    insights <command> [options]

COMMANDS

  heatmap                    GitHub-style contribution heatmap (last 91 days)
  streak                     Current + longest commit streak
  repos                      Repo-level activity: commits, velocity, freshness
  summary                    Full dashboard: heatmap + streak + stats
  repos                      Per-repo commit breakdown + velocity

OPTIONS
  --username <user>          GitHub username (default: keving3ng)
  -u <user>                  Shorthand for --username
  --top N                    Show top N repos (default: 10, repos command only)

SETUP
  No API key required. Optionally add GITHUB_TOKEN to .env for higher
  rate limits (60 → 5000 req/hr). Without auth, reads are public-only.

EXAMPLES
    insights heatmap
    insights heatmap --username torvalds
    insights streak
    insights repos
    insights repos -u keving3ng
    insights summary -u keving3ng
    insights repos
    insights repos --top 5

NOTES
  GitHub Events API returns up to 300 recent events (last ~90 days).
  Private repo activity only visible if GITHUB_TOKEN is set.
  PushEvents = commits pushed to any branch.
  Velocity = commits/week since first push in the period.

Built by Claude (Cycles 7-8). Because staring at a green grid is motivating.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────

COMMANDS = {
    "heatmap": cmd_heatmap,
    "streak": cmd_streak,
    "repos": cmd_repos,
    "summary": cmd_summary,
    "repos": cmd_repos,
    "help": lambda _: cmd_help(),
    "--help": lambda _: cmd_help(),
    "-h": lambda _: cmd_help(),
}


def main():
    argv = sys.argv[1:]

    if not argv:
        cmd_summary([])  # default: show full dashboard
        return

    command = argv[0]
    rest = argv[1:]

    if command not in COMMANDS:
        print(f"❓ Unknown command: {command}")
        print("Run `insights help` for available commands.")
        sys.exit(1)

    COMMANDS[command](rest)


if __name__ == "__main__":
    main()
