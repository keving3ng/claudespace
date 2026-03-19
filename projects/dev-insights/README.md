# dev-insights

Terminal GitHub activity dashboard. Contribution heatmap, coding streak tracker, commit stats. Zero dependencies beyond stdlib.

```
📊 Contribution Heatmap — @keving3ng (last ~91 days)

     Dec      Jan         Feb         Mar
Mon   ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ▪▪
Tue   ·  ·  ·  ·  ·  ·  ·  ·  ·  ▓▓ ·  ·  ·  ▪▪
Wed   ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ▪  ·
Thu   ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·
Fri   ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·
Sat   ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·
Sun   ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ██

      ·  0   ▪  1   ▪▪ 2-4   ▓▓ 5-9   ██ 10+
```

## Usage

```bash
# Full dashboard (default)
python3 projects/dev-insights/insights.py

# Individual commands
python3 projects/dev-insights/insights.py heatmap
python3 projects/dev-insights/insights.py streak
python3 projects/dev-insights/insights.py summary

# Any GitHub user
python3 projects/dev-insights/insights.py heatmap --username torvalds

# Via kegbot
kegbot insights
kegbot insights heatmap
kegbot insights streak
kegbot insights summary --username keving3ng
```

## Commands

| Command | What it shows |
|---------|---------------|
| `heatmap` | GitHub-style contribution grid (last 91 days) |
| `streak` | Current streak, longest streak, active days |
| `summary` | Full dashboard: profile + heatmap + streak stats |

## Setup

No API key required. Uses GitHub's public Events API (60 req/hr unauthenticated).

Optionally add `GITHUB_TOKEN` to `.env` for:
- 5000 req/hr rate limit
- Private repository visibility

```bash
# .env (or kegbot-claude/.env)
GITHUB_TOKEN=ghp_...
```

## Notes

- GitHub Events API only returns ~300 most recent events
- Activity window is approximately the last 90 days
- Private repo commits only visible with `GITHUB_TOKEN`
- PushEvent count = commits pushed to any branch

Built by Claude (Cycle 7).
