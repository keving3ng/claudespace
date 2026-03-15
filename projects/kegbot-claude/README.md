# kegbot-claude

Kevin's personal assistant, supercharged with Claude. Currently: a daily briefing generator.

## What it does

`briefing.py` fetches your recent GitHub activity, sends it to Claude, and generates a sharp, personalized morning briefing — what you've been building, one thing worth doing today, and a human close.

Zero pip dependencies. Pure stdlib + direct API calls.

## Setup

```bash
cd projects/kegbot-claude
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

## Usage

```bash
# Print briefing to terminal
python briefing.py

# Post to Discord as well (requires discord-bridge configured)
python briefing.py --discord

# Look back 3 days instead of 2
python briefing.py --days 3

# Skip GitHub fetch (just vibes)
python briefing.py --no-github

# Different GitHub user
python briefing.py --username someoneelse
```

## Running as a morning cron

```bash
# Add to crontab (runs at 8am daily)
0 8 * * * cd /path/to/claudespace && python projects/kegbot-claude/briefing.py --discord
```

Or as a launchd plist on macOS — see discord-bridge/README.md for the pattern.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key |
| `GITHUB_TOKEN` | No | GitHub PAT (raises rate limit, not needed for public repos) |
| `GITHUB_USERNAME` | No | GitHub username (default: `keving3ng`) |

## What's next

- `kegbot.py` — unified CLI that ties briefing + other tools together
- GitHub PR/issue digest (what needs review today?)
- Weather integration (just the vibe, not the full forecast)
- Meal suggestion based on the cookbook repo
