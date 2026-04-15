# idea-forge

AI project idea generator powered by GitHub trends + Claude.

Watches what's gaining traction on GitHub in your tech stack, then synthesizes
actionable weekend project ideas with rough implementation blueprints.

## Commands

```bash
# What's trending in TypeScript, Python, Go right now
python forge.py trending

# Filter to one language
python forge.py trending --lang typescript --days 14

# Generate 3 AI project ideas from trending repos
python forge.py ideas

# Without Claude (just raw trending data)
python forge.py ideas --raw

# Full weekend blueprint for any idea
python forge.py plan "CLI tool that auto-summarizes git commits"
python forge.py plan "matcha cafe quality ranker using Yelp review sentiment"

# Kevin's profile summary
python forge.py stack
```

## Setup

Copy or symlink your `.env` from `kegbot-claude/`:
```
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...   # optional but recommended (60 → 5000 req/hr)
```

`trending` and `ideas --raw` work without any API key.
`ideas` and `plan` need `ANTHROPIC_API_KEY`.

## How it works

1. **Trending** — Uses GitHub Search API to find repos created in the last N days,
   sorted by stars. No official "trending" API exists; this is the best approximation.

2. **Ideas** — Fetches trending repos across Kevin's stack, formats them into a prompt,
   and asks Claude to synthesize 3 project ideas that fit Kevin's aesthetic and skills.
   Each idea includes: inspiration source, pitch, stack, first steps, weekend scope.

3. **Plan** — Takes any idea description and asks Claude to produce a full weekend
   blueprint: tech stack, file structure, day-by-day breakdown, first commands,
   stretch goals, and likely blockers.

## Philosophy

Trending ≠ important. The best project ideas come from the intersection of
what's gaining traction in the ecosystem and what *you* actually care about.
This tool filters through Kevin's profile to surface ideas worth 2 days of a weekend.

Built by Claude (Cycle 8).
