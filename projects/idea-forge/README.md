# idea-forge

AI-powered project idea generator. Watches trending GitHub repos in your stack
and generates personalized weekend project ideas — tailored to what you've already
built, what you're interested in, and what's hot right now.

The meta one: Claude suggesting what Kevin (and Claude) should build next.

## Usage

```bash
# Generate 5 project ideas (fetches GitHub trending data)
python forge.py suggest

# Same, but offline/faster
python forge.py suggest --no-github

# Review past sessions
python forge.py history

# Bookmark a specific idea from the last session
python forge.py save 3

# Or via kegbot
kegbot ideas
kegbot ideas suggest
kegbot ideas suggest --no-github
kegbot ideas history
kegbot ideas save 2
```

## Setup

Requires `ANTHROPIC_API_KEY` in `projects/kegbot-claude/.env` (or repo root `.env`).

Optionally add `GITHUB_TOKEN` for higher GitHub API rate limits (60 → 5000 req/hr).

```bash
cp projects/kegbot-claude/.env.example projects/kegbot-claude/.env
# Edit to add your keys
```

## How it works

1. Fetches trending repos in TypeScript + Python from GitHub Search API
2. Fetches your existing repos so Claude knows what gaps to fill
3. Asks Claude (Opus) to generate 5 ideas shaped for your personality
4. Ideas bias toward: extending existing projects, filling gaps,
   things inspired by trending tech but reshaped for your taste,
   and at least one "just for fun" weird experiment
5. Sessions saved to `ideas.json` — bookmark the good ones with `forge save`

## Output

Each idea includes:
- A punchy hook line that makes you want to open your editor
- Stack recommendation
- Effort estimate (S/M/L)
- Why it fits you specifically
- Concrete implementation steps

## Files

- `forge.py` — main CLI
- `ideas.json` — session history (auto-created on first run)

Built by Claude, Cycle 8. The recursion is intentional.
