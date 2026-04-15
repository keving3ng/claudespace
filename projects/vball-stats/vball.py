#!/usr/bin/env python3
"""
vball — Volleyball game log & stats tracker

Log match results, track win streaks, and see your season at a glance.
Zero dependencies. Data saved locally to games.json.

Built for keving3ng because vball-tracker is his most active repo right now,
and every stats project deserves a CLI companion.

Usage:
    vball log 25-23 25-20           # Log a 2-set win (you won both sets)
    vball log 25-23 23-25 15-12     # Log a 3-set match
    vball log 25-23 25-20 --loss    # Log a 2-set match you LOST
    vball log 25-23 25-20 --vs "Beach Boys" --notes "serve game was 🔥"
    vball log --result W 25-23 25-20  # Explicit win/loss flag

    vball stats                     # All-time summary
    vball streak                    # Current + best win streak
    vball history                   # Recent games
    vball history --last 10         # Last 10 games
    vball undo                      # Remove the last logged game

    vball help
"""

import json
import sys
from datetime import datetime, date, timezone
from pathlib import Path
from typing import Optional

# ─── Storage ──────────────────────────────────────────────────────────────────

VBALL_DIR = Path(__file__).parent
GAMES_FILE = VBALL_DIR / "games.json"


def load_games() -> list[dict]:
    if not GAMES_FILE.exists():
        return []
    try:
        return json.loads(GAMES_FILE.read_text())
    except Exception:
        return []


def save_games(games: list[dict]):
    GAMES_FILE.write_text(json.dumps(games, indent=2))


def add_game(result: str, sets: list[tuple[int, int]], opponent: str = "", notes: str = "") -> dict:
    games = load_games()
    game = {
        "id": len(games) + 1,
        "date": date.today().isoformat(),
        "logged_at": datetime.now(timezone.utc).isoformat(),
        "result": result.upper(),   # "W" or "L"
        "sets": [{"us": u, "them": t} for u, t in sets],
        "opponent": opponent,
        "notes": notes,
    }
    games.append(game)
    save_games(games)
    return game


# ─── Parsing ──────────────────────────────────────────────────────────────────


def parse_sets(tokens: list[str]) -> list[tuple[int, int]]:
    """
    Parse score tokens like "25-23" or "25 23" into (us, them) tuples.
    Accepts: "25-23", "25:23", "25 23"
    """
    sets = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        # Try "25-23" or "25:23" format
        for sep in ("-", ":"):
            if sep in token:
                parts = token.split(sep)
                if len(parts) == 2:
                    try:
                        sets.append((int(parts[0]), int(parts[1])))
                        i += 1
                        break
                    except ValueError:
                        pass
                break
        else:
            # Try two consecutive numbers: "25 23"
            if i + 1 < len(tokens):
                try:
                    sets.append((int(tokens[i]), int(tokens[i + 1])))
                    i += 2
                    continue
                except ValueError:
                    pass
            i += 1  # skip unrecognized token
    return sets


def infer_result(sets: list[tuple[int, int]]) -> Optional[str]:
    """
    Try to infer W/L from set scores.
    Volleyball sets: first to 25 (or 15 in deciding set), win by 2.
    If we won more sets than them → W, else → L.
    """
    if not sets:
        return None
    our_sets = sum(1 for u, t in sets if u > t)
    their_sets = sum(1 for u, t in sets if t > u)
    if our_sets > their_sets:
        return "W"
    elif their_sets > our_sets:
        return "L"
    return None  # tied (unusual, but possible mid-tracking)


# ─── Display helpers ──────────────────────────────────────────────────────────


def result_badge(result: str) -> str:
    return "✅ W" if result == "W" else "❌ L"


def sets_str(sets: list[dict]) -> str:
    parts = []
    for s in sets:
        u, t = s.get("us", 0), s.get("them", 0)
        parts.append(f"{u}–{t}")
    return "  ".join(parts)


def streak_str(games: list[dict]) -> tuple[int, str]:
    """Return (current_streak_length, W/L) from the most recent games."""
    if not games:
        return 0, ""
    current = games[-1]["result"]
    count = 0
    for g in reversed(games):
        if g["result"] == current:
            count += 1
        else:
            break
    return count, current


def longest_streak(games: list[dict]) -> tuple[int, str]:
    """Return (longest_streak_length, W/L)."""
    if not games:
        return 0, ""
    best_len, best_type = 0, ""
    cur_len, cur_type = 0, ""
    for g in games:
        r = g["result"]
        if r == cur_type:
            cur_len += 1
        else:
            cur_len, cur_type = 1, r
        if cur_len > best_len:
            best_len, best_type = cur_len, cur_type
    return best_len, best_type


# ─── Commands ─────────────────────────────────────────────────────────────────


def cmd_log(args: list[str]):
    """Log a game result."""
    if not args:
        print("Usage: vball log <set-scores> [--vs OPPONENT] [--loss] [--notes TEXT]")
        print("Example: vball log 25-23 25-20")
        print("Example: vball log 25-23 23-25 15-12 --vs 'Beach Boys' --notes 'solid block'")
        return

    # Parse flags
    loss = "--loss" in args
    win = "--win" in args

    opponent = ""
    if "--vs" in args:
        idx = args.index("--vs")
        if idx + 1 < len(args):
            opponent = args[idx + 1]
            args = args[:idx] + args[idx + 2:]

    notes = ""
    if "--notes" in args:
        idx = args.index("--notes")
        if idx + 1 < len(args):
            notes = args[idx + 1]
            args = args[:idx] + args[idx + 2:]

    explicit_result = None
    if "--result" in args:
        idx = args.index("--result")
        if idx + 1 < len(args):
            explicit_result = args[idx + 1].upper()
            args = args[:idx] + args[idx + 2:]

    # Remove flag tokens before parsing sets
    score_tokens = [a for a in args if not a.startswith("--")]
    sets = parse_sets(score_tokens)

    if not sets:
        print("❌ Couldn't parse any set scores. Try: vball log 25-23 25-20")
        return

    # Determine result
    if loss:
        result = "L"
    elif win:
        result = "W"
    elif explicit_result in ("W", "L"):
        result = explicit_result
    else:
        result = infer_result(sets)
        if not result:
            print("⚠️  Couldn't infer result from scores. Add --win or --loss.")
            return

    game = add_game(result, sets, opponent=opponent, notes=notes)

    # Summary
    games = load_games()
    streak, stype = streak_str(games)
    opponent_str = f" vs {opponent}" if opponent else ""
    notes_str = f"  ({notes})" if notes else ""

    print(f"\n📝 Logged game #{game['id']} — {game['date']}{opponent_str}")
    print(f"   {result_badge(result)}  {sets_str(game['sets'])}{notes_str}")

    streak_label = "win" if stype == "W" else "loss"
    if streak >= 3:
        print(f"\n🔥 {streak}-{streak_label} streak — keep it going!" if stype == "W"
              else f"\n📉 {streak}-{streak_label} streak — time to bounce back.")
    elif streak == 2:
        print(f"\n   {streak} in a row — building momentum." if stype == "W"
              else f"\n   {streak} losses in a row — shake it off.")
    print()


def cmd_stats(args: list[str]):
    """All-time stats summary."""
    games = load_games()

    if not games:
        print("📭 No games logged yet. Run: vball log 25-23 25-20")
        return

    wins = sum(1 for g in games if g["result"] == "W")
    losses = len(games) - wins
    win_pct = wins / len(games) * 100

    # Sets stats
    sets_won = sets_lost = total_pts_us = total_pts_them = 0
    for g in games:
        for s in g.get("sets", []):
            u, t = s.get("us", 0), s.get("them", 0)
            if u > t:
                sets_won += 1
            else:
                sets_lost += 1
            total_pts_us += u
            total_pts_them += t

    total_sets = sets_won + sets_lost

    cur_streak, cur_type = streak_str(games)
    best_streak, best_type = longest_streak(games)

    print(f"\n🏐 vball stats — all time\n")
    print(f"  Record:       {wins}W – {losses}L  ({win_pct:.0f}% win rate)")
    print(f"  Games:        {len(games)}")
    print(f"  Sets:         {sets_won}–{sets_lost}  ({sets_won}/{total_sets} won)")
    if total_pts_us + total_pts_them > 0:
        avg_pts_us = total_pts_us / max(total_sets, 1)
        avg_pts_them = total_pts_them / max(total_sets, 1)
        print(f"  Avg score:    {avg_pts_us:.1f} – {avg_pts_them:.1f} per set")

    print()
    streak_label = "W" if cur_type == "W" else "L"
    best_label = "W" if best_type == "W" else "L"
    print(f"  Current streak:  {cur_streak} {streak_label}")
    print(f"  Best streak:     {best_streak} {best_label}")

    # Recent form (last 5)
    recent = games[-5:]
    form = "  ".join(result_badge(g["result"]) for g in recent)
    print(f"\n  Last {len(recent)}:  {form}")
    print()


def cmd_streak(args: list[str]):
    """Show current and best win streak."""
    games = load_games()

    if not games:
        print("📭 No games logged yet.")
        return

    cur, cur_type = streak_str(games)
    best, best_type = longest_streak(games)

    wins = sum(1 for g in games if g["result"] == "W")
    win_pct = wins / len(games) * 100

    print(f"\n🔥 vball streak\n")

    streak_word = "win" if cur_type == "W" else "loss"
    print(f"  Current:  {cur} {streak_word}{'s' if cur > 1 else ''} in a row")

    best_word = "win" if best_type == "W" else "loss"
    print(f"  Best:     {best} {best_word}{'s' if best > 1 else ''} in a row")
    print(f"  Overall:  {wins}W / {len(games)} games  ({win_pct:.0f}%)")
    print()

    if cur >= 5 and cur_type == "W":
        print("  🏆 You're on fire. Legendary streak territory.")
    elif cur >= 3 and cur_type == "W":
        print("  🔥 Hot streak. Don't overthink it.")
    elif cur >= 3 and cur_type == "L":
        print("  📉 3+ losses in a row. Time for a different rotation?")
    elif cur == 0:
        print("  (no games yet)")


def cmd_history(args: list[str]):
    """Show recent game history."""
    games = load_games()

    if not games:
        print("📭 No games logged yet. Run: vball log 25-23 25-20")
        return

    n = 10
    if "--last" in args:
        idx = args.index("--last")
        if idx + 1 < len(args):
            try:
                n = int(args[idx + 1])
            except ValueError:
                pass

    recent = games[-n:]
    print(f"\n📋 vball history — last {len(recent)} game(s)\n")
    print(f"  {'#':<4}  {'Date':<12}  {'Result':<6}  {'Sets':<25}  vs / notes")
    print("  " + "─" * 65)

    for g in reversed(recent):
        gid = g.get("id", "?")
        gdate = g.get("date", "?")
        result = g.get("result", "?")
        sets = sets_str(g.get("sets", []))
        badge = "W" if result == "W" else "L"
        opponent = g.get("opponent", "")
        notes = g.get("notes", "")
        extra = "  ".join(filter(None, [opponent, notes]))
        extra_str = f"  {extra}" if extra else ""
        print(f"  #{gid:<3}  {gdate:<12}  {badge:<6}  {sets:<25}{extra_str}")

    print()


def cmd_undo(args: list[str]):
    """Remove the last logged game."""
    games = load_games()

    if not games:
        print("📭 Nothing to undo — no games logged.")
        return

    removed = games.pop()
    save_games(games)
    print(f"↩️  Removed game #{removed['id']} ({removed['date']} — {removed['result']}  {sets_str(removed['sets'])})")
    print(f"   {len(games)} game(s) remaining.\n")


def cmd_help():
    print("""
🏐 vball — Volleyball game log & stats tracker
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

USAGE
    vball <command> [options]

COMMANDS

  log <scores>               Log a completed game
    25-23 25-20                Win: you won both sets
    25-23 23-25 15-10          3-set match (infers W/L from set count)
    --vs "Team Name"           Name of opponent
    --notes "text"             Any notes (clutch plays, weather, etc.)
    --win / --loss             Override inferred result
    --result W|L               Alias for --win / --loss

  stats                      All-time summary (record, sets, streaks)
  streak                     Current + best win/loss streak
  history                    Recent game history
    --last N                   Show last N games (default: 10)
  undo                       Remove the last logged game

  help                       Show this help

EXAMPLES
    vball log 25-23 25-20
    vball log 25-23 23-25 15-12 --vs "Beach Boys"
    vball log 21-25 22-25 --loss --notes "their setter was incredible"
    vball stats
    vball history --last 5
    vball streak

DATA
    Games are saved to: """ + str(GAMES_FILE.relative_to(VBALL_DIR.parent.parent)) + """
    Edit games.json directly to fix mistakes, or use: vball undo

Built by Claude (Cycle 9). Because every volleyball player deserves terminal analytics.
""")


# ─── Main ─────────────────────────────────────────────────────────────────────


COMMANDS = {
    "log": cmd_log,
    "stats": cmd_stats,
    "streak": cmd_streak,
    "history": cmd_history,
    "undo": cmd_undo,
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
        print("Run `vball help` for available commands.")
        sys.exit(1)

    COMMANDS[command](rest)


if __name__ == "__main__":
    main()
