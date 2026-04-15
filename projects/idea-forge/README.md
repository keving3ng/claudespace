# idea-forge

> AI weekend project idea generator, personalized to Kevin's stack.

Watches what's trending on GitHub in Python, TypeScript, and Go, then uses Claude to generate weekend project ideas *specifically for you* — not generic tutorials, not portfolio padding. Things you'd actually build and use.

The meta part: an AI suggesting what an AI should build next. It's recursive and I'm not apologizing.

---

## Commands

```bash
# Generate 3 project ideas from what's trending right now (default)
python idea_forge.py forge

# Narrower window — hotter, more recent repos
python idea_forge.py forge --days 7

# Focus on one language
python idea_forge.py forge --language python

# Preview the trending repos without calling Claude
python idea_forge.py forge --raw

# Just see what's trending (no idea generation, faster)
python idea_forge.py trending
python idea_forge.py trending --language typescript

# One quick off-the-cuff idea, no analysis needed
python idea_forge.py spark

# Save a good idea for later
python idea_forge.py save "Terminal Matcha Timer"
python idea_forge.py save "My CLI" --desc "does the thing"

# List saved ideas
python idea_forge.py list
```

## Via kegbot

```bash
kegbot ideas              # same as idea_forge.py forge
kegbot ideas trending
kegbot ideas spark
kegbot ideas list
```

## Setup

No API key needed for `trending` and `--raw` mode.

For full idea generation:

```bash
# Add to kegbot-claude/.env or repo root .env:
ANTHROPIC_API_KEY=your_key_here

# Optional — removes GitHub rate limit (60 → 5000 req/hr):
GITHUB_TOKEN=your_github_token
```

## How it works

1. Queries the GitHub Search API for repos created in the last N days with meaningful traction (≥5 stars), sorted by stars
2. Pulls the top 4 repos from each of Kevin's primary languages (Python, TypeScript, Go)
3. Sends the batch to Claude with Kevin's full profile as context
4. Claude generates 3 project ideas *inspired by* (not copies of) the trends, each with a pitch, weekend build plan, stack recommendation, and "Kevin's twist"

The ideas are personalized. If Claude sees a trending knowledge-base tool written in Go, it won't suggest "build a knowledge base." It might suggest "build a matcha-log that knows your flavor notes and suggests cafes," because that's the kind of thing Kevin would actually use.

---

Built by Claude (Cycle 8). Because the best project is the one you actually build.
