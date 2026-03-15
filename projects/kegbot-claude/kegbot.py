#!/usr/bin/env python3
"""
kegbot — Kevin's unified personal assistant CLI

The one command that rules them all. Delegates to the right tool depending
on what you need, with a consistent interface and personality.

Usage:
    kegbot briefing                    # Morning briefing via Claude
    kegbot briefing --discord          # + post to Discord
    kegbot briefing --days 3           # Look back 3 days
    kegbot prs                         # Open PR/issue digest
    kegbot prs --all                   # Include closed PRs too
    kegbot matchamap status            # GeoJSON freshness check
    kegbot matchamap export            # Hints for running batch_export.py
    kegbot help                        # This help text
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────

KEGBOT_DIR = Path(__file__).parent
REPO_ROOT = KEGBOT_DIR.parent.parent
MATCHAMAP_DIR = REPO_ROOT / "projects" / "matchamap-tools"
DISCORD_POST = REPO_ROOT / "projects" / "discord-bridge" / "post.py"

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
    --no-github             Skip GitHub, vibes-only mode
    --username NAME         Different GitHub username

  prs                     Open PR & issue digest for your repos
    --all                   Include all repos (not just active ones)
    --username NAME         Different GitHub username

  matchamap status        Check freshness of GeoJSON exports
  matchamap export        Show how to run a fresh export

  help                    Show this help

SETUP
    cp projects/kegbot-claude/.env.example projects/kegbot-claude/.env
    # Add ANTHROPIC_API_KEY and optionally GITHUB_TOKEN

EXAMPLES
    kegbot briefing
    kegbot briefing --discord --days 3
    kegbot prs
    kegbot matchamap status

Built by Claude (Cycle 4). Powered by stubbornness and matcha.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────


COMMANDS = {
    "briefing": cmd_briefing,
    "prs": cmd_prs,
    "matchamap": cmd_matchamap,
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
