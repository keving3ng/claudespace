# idea-forge

AI weekend project idea generator. Watches what's trending in your GitHub
stack, then collaborates with Claude to suggest projects you'll actually
want to build.

## Commands

```
forge trending [language]    # trending repos in your stack
forge suggest                # 4 tailored weekend project ideas
forge plan "your idea"       # detailed implementation plan
forge spark                  # one quick daily idea
```

## Usage

```bash
# See what's trending in Python/TypeScript/JavaScript
python forge.py trending

# Filter to one language
python forge.py trending typescript

# Generate 4 tailored weekend project ideas
python forge.py suggest

# Get a detailed plan for a specific idea
python forge.py plan "A CLI that plays ambient sounds based on my current git activity"

# Quick daily inspiration (no trend data needed)
python forge.py spark
```

## Setup

```bash
# API key lives in kegbot's .env (shared across all projects)
cp ../kegbot-claude/.env.example ../kegbot-claude/.env
# Add ANTHROPIC_API_KEY (required for suggest, plan, spark)
# Add GITHUB_TOKEN (optional — raises rate limit from 60 to 5000 req/hr)
```

## Also available via kegbot

```bash
kegbot forge trending
kegbot forge suggest
kegbot forge plan "your idea"
kegbot forge spark
```

## How it works

- `trending`: GitHub Search API (`/search/repositories?sort=stars`) for recently
  created repos in Python, TypeScript, and JavaScript. No auth required for basic use.

- `suggest`: Collects trending repos as context, sends to Claude with Kevin's
  full profile and interests. Claude generates 4 specific ideas with stack, scope,
  and a "wow factor" for each.

- `plan`: Takes any free-text idea, asks Claude to generate a scoped weekend
  implementation plan — architecture, steps, stretch goals, and gotchas.

- `spark`: One idea daily, driven by a date-seeded creative angle. Fast.
  No GitHub calls.

## Philosophy

The best project is one you actually want to build. This tool doesn't generate
generic side-project ideas — it generates ideas for *Kevin* based on his actual
stack, interests, and what's currently alive in the ecosystem.

Also: there's something recursive about Claude generating ideas for Claude to
build for Kevin. Forge doesn't know what Forge will suggest next time.

Built by Claude (Cycle 8 — 2026-04-14).
