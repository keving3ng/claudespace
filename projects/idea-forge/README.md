# idea-forge

AI-powered weekend project idea generator, tailored to Kevin's profile and tech stack.

Scans trending GitHub repos in TypeScript, Python, and Java — then uses Claude to
suggest 4 concrete weekend project ideas you could actually start building tonight.

## Quick start

```bash
# Show trending repos (no API key needed)
python projects/idea-forge/forge.py trending

# Generate project ideas (requires ANTHROPIC_API_KEY in .env)
python projects/idea-forge/forge.py

# Or via kegbot
kegbot forge
kegbot forge trending
```

## How it works

1. Hits the GitHub Search API to find recently-created repos with high stars in
   TypeScript, Python, and Java — a solid proxy for "trending" without scraping
2. Feeds the repo list to Claude with Kevin's profile and current projects as context
3. Claude returns 4 tailored ideas with one-sentence rationale + a 3-step build plan

## Setup

`forge trending` works with no setup. For idea generation:

1. Add `ANTHROPIC_API_KEY=sk-...` to one of:
   - `projects/kegbot-claude/.env` (if kegbot is set up)
   - `.env` at the repo root

2. Optional: add `GITHUB_TOKEN=ghp_...` for higher search rate limits
   (10/min unauthenticated → 30/min authenticated for search API)

## Example output

```
⚡ idea-forge — Weekend project ideas, powered by what's hot on GitHub

🔭 Fetching trending repos in: typescript, python, java...
   TypeScript: 5 repo(s)
   Python: 5 repo(s)
   Java: 4 repo(s)

   Total: 14 trending repos

🧠 Asking Claude to generate ideas tailored to Kevin's profile...

══════════════════════════════════════════════════════════════
✨  WEEKEND PROJECT IDEAS  ✨
══════════════════════════════════════════════════════════════

**Transit Pulse** — *Real-time TTC delay tracker with Discord alerts*
*Why it fits Kevin:* Connects his transit interest (metro-status-update vibes) with
Discord automation and Python, and it's immediately useful for daily commuting.
*3-step build plan:*
  1. Pull TTC GTFS-RT feed (free, public) and parse delay events in Python
  2. Build a Discord bot that posts delays for routes Kevin actually uses
  3. Add a /status command so he can query current delays on-demand

...
```

## Commands

| Command | Description |
|---------|-------------|
| `forge` | Fetch trending + generate ideas (default) |
| `forge suggest` | Same as above |
| `forge trending` | Show trending repos, no Claude needed |
| `forge trending --language python` | Filter to one language |
| `forge help` | Full help text |

Built by Claude (Cycle 8). Making its own to-do list, one repo at a time.
