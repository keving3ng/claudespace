# idea-forge

AI-powered project idea generator. Watches what's trending on GitHub in your stack and suggests weekend projects you could actually build and ship.

```
💡 idea-forge suggest

[claude] Generating project ideas from what's trending...

─────────────────────────────────────────────────────────────
### Matcha Origin Tracer
**Pitch:** A CLI that takes a matcha product name and traces its likely origin
          region, cultivar, and harvest season from public tea databases.
**Stack:** Python, urllib, Claude API
**Build plan:**
  1. Scrape/parse public tea catalog data into a local JSON corpus
  2. Build a fuzzy-match lookup for product names → origin metadata
  3. Use Claude to generate a natural-language "tasting provenance" card
**Why Kevin:** Directly useful for matchamap.club — gives cafe data more depth.
─────────────────────────────────────────────────────────────
```

## Usage

```bash
# See what's trending in Python, TypeScript, Go
python3 projects/idea-forge/idea.py trending

# Claude-powered project ideas based on what's trending
python3 projects/idea-forge/idea.py suggest

# Ideas on any topic (no GitHub data needed — offline mode)
python3 projects/idea-forge/idea.py inspire "matcha + machine learning"
python3 projects/idea-forge/idea.py inspire "something a developer would love at 2am"

# Save an idea to your backlog
python3 projects/idea-forge/idea.py save "Matcha Strain Classifier" --note "CNN on matcha grades"

# List saved ideas
python3 projects/idea-forge/idea.py list
python3 projects/idea-forge/idea.py list --status backlog

# Mark done
python3 projects/idea-forge/idea.py done 3

# Via kegbot
kegbot idea trending
kegbot idea suggest
kegbot idea inspire "cooking automation"
kegbot idea list
```

## Commands

| Command | What it does |
|---------|-------------|
| `trending [--lang LANG] [--days N]` | Show trending GitHub repos (last N days) |
| `suggest [--lang LANG]` | Claude-powered weekend project ideas |
| `inspire <topic>` | Wild card: ideas on any topic, no GitHub needed |
| `save <title> [--note TEXT]` | Save an idea to `ideas.json` |
| `done <id>` | Mark an idea as done |
| `list [--status STATUS]` | Show saved ideas |

## Setup

```bash
# Copy your existing .env (same keys as kegbot-claude)
cp projects/kegbot-claude/.env projects/idea-forge/.env

# Or just set environment variables:
export ANTHROPIC_API_KEY=sk-...
export GITHUB_TOKEN=ghp_...   # optional but recommended
```

### Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `ANTHROPIC_API_KEY` | Yes (for `suggest`/`inspire`) | Claude API calls |
| `GITHUB_TOKEN` | No | Raises GitHub rate limit: 60 → 5000 req/hr |

Without `GITHUB_TOKEN`, `trending` and `suggest` still work but may hit GitHub's 10 search req/min limit.
`inspire` never needs GitHub — it's purely Claude.

## Ideas file

Saved ideas live in `projects/idea-forge/ideas.json`. Format:

```json
[
  {
    "id": 1,
    "title": "Matcha Strain Classifier",
    "note": "train a CNN on matcha grades",
    "status": "backlog",
    "saved_at": "2026-04-14"
  }
]
```

Statuses: `backlog`, `in-progress`, `done`, `dropped`

Built by Claude (Cycle 8). Ideas are free. Shipping is the hard part.
